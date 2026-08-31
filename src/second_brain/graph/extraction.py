"""Extracción del grafo léxico de tres niveles (LINAJE, RESUMEN, ENTIDADES).

El grafo es un ARTEFACTO DERIVADO del corpus, nunca una fuente de verdad
independiente. Las tres capas replican el diseño del LexicalGraphIndex del
GraphRAG Toolkit que muestra la charla:

  LINAJE:    Documento -> Chunk           (de qué documento salió cada chunk)
  RESUMEN:   Chunk -> Statement           (una afirmación puntual, con su
                                            chunk de origen — el provenance
                                            de fábrica de cualquier hecho)
  ENTIDADES: Entidad -[RELACION]-> Entidad (lo que permite el traversal
                                            multi-hop de `graph/traversal.py`)

Si una relación que la demo necesita no aparece en el grafo extraído, la
corrección es reescribir la frase del documento fuente para que use un verbo
explícito ("consume", "depende de", "llama a") — nunca parchear el grafo a
mano. Un grafo con aristas que no vienen del corpus es peor que un grafo
incompleto: dejaría de ser auditable.

Dos modos, misma interfaz (`extract_entities_and_relations`): determinista
por patrones (sin red, para que la demo se arme y testee offline) o abierto
vía `LlmPort`. La decisión de cuál usar es del LLAMADOR (típicamente
`graph.build.build_graph`, según config) — esta función no lee ninguna
variable de entorno ni Settings, solo reacciona a si le pasaron un `llm`.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

from second_brain.ports import Chunk, LlmPort

_CODE_BLOCK_PATTERN = re.compile(r"```.*?```", re.DOTALL)
_CODE_SPAN_PATTERN = re.compile(r"`[^`]*`")
_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<!\d)\.(?!\d)\s+")
_PROTECTED_DOT_MARKER = "␀"

_NEGATION_PATTERN = re.compile(
    r"\bno\b\s+(?:\w+\s+){0,2}(?:consume|depende|llama)", re.IGNORECASE
)

_RELATION_VERBS: list[tuple[str, re.Pattern[str]]] = [
    (
        "DEPENDE_DE",
        re.compile(
            r"`(?P<origen>[\w\-]+)`\s+depende del evento[\s\S]*?emite\s+`(?P<destino>[\w\-]+)`",
            re.IGNORECASE,
        ),
    ),
    (
        "DEPENDE_DE",
        re.compile(
            r"`(?P<origen>[\w\-]+)`\s+(?:también\s+)?depende de\s+`(?P<destino>[\w\-]+)`",
            re.IGNORECASE,
        ),
    ),
    (
        "CONSUME",
        re.compile(
            r"`(?P<origen>[\w\-]+)`\s+(?:también\s+)?consume\b[\s\S]*?\bde\s+`(?P<destino>[\w\-]+)`",
            re.IGNORECASE,
        ),
    ),
    (
        "LLAMA_A",
        re.compile(
            r"`(?P<origen>[\w\-]+)`[\s\S]*?\bllama a\s+`(?P<destino>[\w\-]+)`",
            re.IGNORECASE,
        ),
    ),
]

_LLM_EXTRACTION_SYSTEM = (
    "Extraés relaciones de dependencia entre servicios/frontends de un "
    "documento técnico. Devolvé EXCLUSIVAMENTE un array JSON (sin texto "
    "alrededor) de objetos {\"origen\": str, \"tipo\": str, \"destino\": "
    "str, \"fragmento\": str}. `tipo` es uno de CONSUME, DEPENDE_DE, "
    "LLAMA_A. `fragmento` es la frase exacta del documento que sostiene la "
    "relación. Si no hay relaciones, devolvé []."
)


@dataclass
class StatementNode:
    """Nivel RESUMEN: una afirmación puntual, trazable a su chunk de origen."""

    id: str
    text: str
    chunk_id: str
    document_id: str


@dataclass
class Relation:
    """Una arista del nivel ENTIDADES, con el provenance para poder citarla."""

    source: str
    type: str
    target: str
    document_id: str
    chunk_id: str
    fragment: str


@dataclass
class LexicalGraph:
    """Las tres capas del grafo léxico, listas para hacer upsert a un `GraphStorePort`."""

    lineage: list[tuple[str, str]] = field(default_factory=list)
    statements: list[StatementNode] = field(default_factory=list)
    entities: set[str] = field(default_factory=set)
    relations: list[Relation] = field(default_factory=list)


def extract_entities_and_relations(
    chunks: list[Chunk], llm: LlmPort | None = None
) -> LexicalGraph:
    """Construye el `LexicalGraph` de tres niveles a partir de chunks del corpus.

    `llm=None` (default) corre el extractor determinista por patrones, sin
    red: es el modo que usan los tests y el ensayo local. Pasar un `LlmPort`
    real (p.ej. `stack.llm` en modo AWS) activa la extracción abierta vía
    Nova, misma firma, mismo `LexicalGraph` de salida.
    """
    if llm is not None:
        return _extract_with_llm(chunks, llm)
    return _extract_by_patterns(chunks)


def _extract_by_patterns(chunks: list[Chunk]) -> LexicalGraph:
    known_entities = {chunk.document_id for chunk in chunks}
    graph = LexicalGraph()
    seen: set[tuple[str, str, str]] = set()
    for chunk in chunks:
        graph.lineage.append((chunk.document_id, chunk.id))
        code_free_text = _CODE_BLOCK_PATTERN.sub("", chunk.text)
        for sentence in _split_into_sentences(code_free_text):
            _extract_relations_from_sentence(sentence, chunk, known_entities, seen, graph)
    return graph


def _extract_relations_from_sentence(
    sentence: str,
    chunk: Chunk,
    known_entities: set[str],
    seen: set[tuple[str, str, str]],
    graph: LexicalGraph,
) -> None:
    if _NEGATION_PATTERN.search(sentence):
        return
    for tipo, patron in _RELATION_VERBS:
        for match in patron.finditer(sentence):
            source, target = match.group("origen"), match.group("destino")
            if source == target:
                continue
            if source not in known_entities or target not in known_entities:
                continue
            clave = (source, tipo, target)
            if clave in seen:
                continue
            seen.add(clave)
            _add_relation(graph, chunk, source, tipo, target, match.group(0).strip())


def _add_relation(
    graph: LexicalGraph, chunk: Chunk, source: str, kind: str, target: str, fragmento: str
) -> None:
    graph.entities.add(source)
    graph.entities.add(target)
    graph.relations.append(
        Relation(
            source=source,
            type=kind,
            target=target,
            document_id=chunk.document_id,
            chunk_id=chunk.id,
            fragment=fragmento,
        )
    )
    graph.statements.append(
        StatementNode(
            id=f"{chunk.id}#{len(graph.statements)}",
            text=fragmento,
            chunk_id=chunk.id,
            document_id=chunk.document_id,
        )
    )


def _split_into_sentences(text: str) -> list[str]:
    """Corta en oraciones por punto, sin partir los spans entre backticks.

    Un identificador como `` `billing.updated` `` tiene un punto adentro; si
    se cortara ahí, el patrón de "depende del evento X que emite Y" quedaría
    partido en dos oraciones y la relación se perdería. Por eso los puntos
    dentro de spans `` `...` `` se enmascaran antes de partir y se restauran
    después.
    """
    protegido = _CODE_SPAN_PATTERN.sub(
        lambda m: m.group(0).replace(".", _PROTECTED_DOT_MARKER), text
    )
    piezas = _SENTENCE_SPLIT_PATTERN.split(protegido)
    return [
        pieza.replace(_PROTECTED_DOT_MARKER, ".").strip()
        for pieza in piezas
        if pieza.strip()
    ]


def _extract_with_llm(chunks: list[Chunk], llm: LlmPort) -> LexicalGraph:
    graph = LexicalGraph()
    for chunk in chunks:
        graph.lineage.append((chunk.document_id, chunk.id))
        response = llm.generate(
            system=_LLM_EXTRACTION_SYSTEM,
            messages=[{"role": "user", "content": chunk.text}],
        )
        for raw_relation in _parse_relations_json(response.text):
            _add_llm_relation(graph, chunk, raw_relation)
    return graph


def _add_llm_relation(graph: LexicalGraph, chunk: Chunk, raw_relation: dict[str, Any]) -> None:
    source = raw_relation.get("origen")
    tipo = raw_relation.get("tipo")
    target = raw_relation.get("destino")
    if not source or not tipo or not target:
        return
    fragmento = raw_relation.get("fragmento", "")
    _add_relation(graph, chunk, str(source), str(tipo), str(target), str(fragmento))


def _parse_relations_json(text: str) -> list[dict[str, Any]]:
    """Tolerante a que Nova no devuelva JSON perfecto: nunca rompe la extracción.

    Si el LLM se desvía del contrato (agrega prosa, markdown, JSON inválido),
    esta función devuelve una lista vacía en vez de propagar la excepción —
    perder una relación es preferible a tumbar la construcción del grafo.
    """
    try:
        datos = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return []
    return datos if isinstance(datos, list) else []
