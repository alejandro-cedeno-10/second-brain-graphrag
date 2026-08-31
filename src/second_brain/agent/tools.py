"""Las dos manos del agente: buscar documentos y navegar el grafo.

Ninguna de las dos devuelve prosa — devuelven `Evidence`, la misma forma
para ambas, con la fuente pegada. Esa uniformidad es la que permite que
`gate.py`, `synthesis.py` y `guards.py` traten evidencia documental y
evidencia de grafo con el mismo código: ninguno necesita saber de qué
herramienta salió cada ítem, solo si es relevante, si es sobre el sujeto
preguntado (`is_target`) y de qué documento se puede citar.

`is_target` es la señal que sostiene el patrón 3 (anclaje al sujeto):
`search_documents` la prende para los chunks que salen de una búsqueda
ANCLADA al `objetivo` resuelto (no solo por aparecer alto en el ranking
genérico), y `traverse_graph` la prende siempre, porque lo que un vecino del
grafo hace CON la entidad consultada es, por definición, evidencia sobre esa
entidad — nunca evidencia de otro tema que haya que marcar como comparación.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path as _RutaArchivo
from typing import Any

from second_brain.config import Stack
from second_brain.graph.traversal import blast_radius, neighbors_of, path_between
from second_brain.ports import Path, ScoredDoc
from second_brain.retrieval import LexicalIndex, resolve_targets, retrieve

_ANCHORED_SEARCH_TOP_K = 5
_GRAPH_EVIDENCE_SCORE = 1.0
"""Las aristas del grafo salen de un patrón determinista sobre una frase
explícita del corpus (ver `graph/extraction.py`): no hay una escala de
similitud que puntuarlas, así que se les da un score fijo por encima del
umbral de relevancia del gate (`agent.gate.RELEVANT_SCORE_THRESHOLD`) — el
grafo confirmando una relación siempre cuenta como evidencia relevante.
"""

_RELATION_LABEL = {
    "CONSUME": "consume a",
    "DEPENDE_DE": "depende de",
    "LLAMA_A": "llama a",
}


@dataclass
class Evidence:
    """Ítem de evidencia citable: la misma forma para las dos herramientas.

    `doc_id` es el identificador que se cita textualmente como
    `[source:doc_id]`: para evidencia documental es la ruta relativa del
    corpus (`org/proyectos.md`), para evidencia de grafo es el slug de la
    entidad (`pagos`) — dos namespaces distintos que ya conviven en el resto
    del sistema (`ingestion.Document.doc_id` vs `graph.build` slugs); esta
    clase no los unifica, solo los transporta con su fuente pegada.
    """

    doc_id: str
    text: str
    score: float = 0.0
    is_target: bool = False
    source: str = "documentos"
    chunk_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def search_documents(
    question: str,
    stack: Stack,
    lexical_index: LexicalIndex,
    target: str | None = None,
    top_k_per_method: int = 20,
    top_n_final: int = 12,
) -> list[Evidence]:
    """Recupera evidencia citable para `question`, opcionalmente anclada a `target`.

    Los defaults de recall (`top_k_per_method`, `top_n_final`) se
    recalibraron junto con `RELEVANT_SCORE_THRESHOLD` (ver `agent.gate`)
    cuando el corpus creció a ~50 documentos: con la ventana original
    (10/5), un vecino real del sujeto preguntado (p.ej. `pagos` para P2)
    podía quedar fuera del top-K genérico simplemente por haber más
    documentos compitiendo por los mismos primeros puestos, no por dejar
    de ser relevante.

    `target` es una mención en lenguaje natural (no necesariamente un
    `doc_id` exacto) que esta función resuelve por su cuenta vía
    `resolve_targets` — así, tanto un tool-call de un LLM real ("buscá
    sobre core-billing") como el `doc_id` ya resuelto por el orquestador
    funcionan igual de bien como argumento.

    Combina dos búsquedas: la genérica (`retrieve`, todo el corpus) y, si
    hay target, una ANCLADA a cada documento resuelto (búsqueda semántica
    filtrada por `doc_id`, sin competir contra el resto del corpus). La
    anclada es la que sostiene el patrón 3: sin ella, un sujeto con poca
    evidencia (`reportes-frontend` en la P5 de la demo) puede perder contra
    sujetos con más volumen de contenido (`dashboard`, `onboarding`) en el
    ranking genérico, aunque sea exactamente el documento que hay que citar.
    """
    target_doc_ids = resolve_targets(target, stack) if target else []
    generales = retrieve(question, stack, lexical_index, top_k_per_method, top_n_final)
    evidencia = [_evidence_from_scored_doc(doc, target_doc_ids) for doc in generales]
    for doc_id in target_doc_ids:
        anclada = _search_anchored(question, stack, doc_id)
        evidencia.extend(anclada)
    return _dedupe_evidence(evidencia)


def _evidence_from_scored_doc(doc: ScoredDoc, target_doc_ids: list[str]) -> Evidence:
    doc_id = str(doc.metadata.get("doc_id", ""))
    return Evidence(
        doc_id=doc_id,
        text=doc.text,
        score=doc.score,
        is_target=doc_id in target_doc_ids,
        source="documentos",
        chunk_id=doc.chunk_id,
        metadata=doc.metadata,
    )


def _search_anchored(question: str, stack: Stack, doc_id: str) -> list[Evidence]:
    (vector,) = stack.embeddings.embed([question])
    hits = stack.vector_store.search(
        vector, top_k=_ANCHORED_SEARCH_TOP_K, filter={"doc_id": doc_id}
    )
    if not hits:
        return []
    hit_por_texto = {hit.text: hit for hit in hits}
    puntuados = stack.rerank.rerank(question, list(hit_por_texto), top_n=len(hit_por_texto))
    return [
        Evidence(
            doc_id=doc_id,
            text=puntuado.text,
            score=puntuado.score,
            is_target=True,
            source="documentos",
            chunk_id=hit_por_texto[puntuado.text].chunk_id,
            metadata=hit_por_texto[puntuado.text].metadata,
        )
        for puntuado in puntuados
    ]


def traverse_graph(
    entity: str,
    stack: Stack,
    kind: str = "blast_radius",
    destino: str | None = None,
    max_hops: int = 3,
) -> list[Evidence]:
    """Traversal del grafo de dependencias, devuelto como evidencia por salto.

    `kind` selecciona la operación de `graph.traversal`: `"blast_radius"`
    (default, quién depende de `entity`), `"camino_entre"` (requiere
    `destino`) o `"vecinos"` (vecindario directo, sin la guarda anti-hub).
    Cada salto de cada camino se convierte en un `Evidence` propio, para que
    una respuesta pueda citar el documento exacto que sostiene ESE salto
    (`camino.provenance[i]`), no el camino completo como un bloque.
    """
    caminos = _paths(entity, stack, kind, destino, max_hops)
    return _dedupe_evidence(_paths_to_evidence(caminos))


def _paths(entity: str, stack: Stack, kind: str, destino: str | None, max_hops: int) -> list[Path]:
    if kind == "blast_radius":
        return blast_radius(entity, stack, max_hops=max_hops)
    if kind == "camino_entre":
        if not destino:
            raise ValueError("traverse_graph: kind='camino_entre' requiere 'destino'")
        return path_between(entity, destino, stack, max_hops=max_hops)
    if kind == "vecinos":
        return neighbors_of(entity, stack, max_hops=max_hops)
    raise ValueError(f"traverse_graph: kind desconocido '{kind}'")


def _paths_to_evidence(paths: list[Path]) -> list[Evidence]:
    """Verbaliza cada salto como una afirmacion citable, EN SU SENTIDO REAL.

    Un camino de blast radius se recorre contra la flecha (de la entidad
    hacia quienes dependen de ella), asi que tomar los nodos en orden de
    recorrido produce la afirmacion invertida. `Path.directions` dice, salto
    a salto, cual de los dos extremos es el origen que declara el corpus.
    """
    evidencia: list[Evidence] = []
    for camino in paths:
        for indice, relacion in enumerate(camino.relations):
            desde, hacia = camino.nodes[indice], camino.nodes[indice + 1]
            directa = camino.directions[indice] if indice < len(camino.directions) else True
            origen, destino = (desde, hacia) if directa else (hacia, desde)
            doc_id = camino.provenance[indice] if indice < len(camino.provenance) else ""
            etiqueta = _RELATION_LABEL.get(relacion, relacion.lower())
            evidencia.append(
                Evidence(
                    doc_id=doc_id,
                    text=f"`{origen}` {etiqueta} `{destino}`.",
                    score=_GRAPH_EVIDENCE_SCORE,
                    is_target=True,
                    source="grafo",
                )
            )
    return evidencia


def _dedupe_evidence(items: list[Evidence]) -> list[Evidence]:
    fusionadas: dict[tuple[str, str], Evidence] = {}
    orden: list[tuple[str, str]] = []
    for item in items:
        clave = (item.doc_id, item.text)
        existente = fusionadas.get(clave)
        if existente is None:
            fusionadas[clave] = item
            orden.append(clave)
            continue
        existente.is_target = existente.is_target or item.is_target
        existente.score = max(existente.score, item.score)
    return [fusionadas[clave] for clave in orden]


def _entity_from_doc_id(doc_id: str) -> str:
    """El grafo indexa por slug de archivo (`core-billing`), no por ruta
    relativa del corpus (`servicios/core-billing.md`): esta conversión es la
    que le permite al orquestador pasarle a `traverse_graph` la entidad
    correcta a partir de un `doc_id` ya resuelto por `resolve_targets`.
    """
    return _RutaArchivo(doc_id).stem
