"""Glue de construcción del grafo: extracción + upsert al `GraphStorePort`.

Este módulo es intencionalmente delgado. Toda la inteligencia de la
extracción vive en `graph.extraction`; acá solo se decide DE DÓNDE vienen
los chunks (un directorio de corpus en disco, o una lista ya armada por un
pipeline de ingesta) y se los entrega al `GraphStorePort` del stack.
`build_graph` es idempotente porque tanto `FalkorGraphStore` como
`MemoryGraphStore` upsertean por MERGE sobre `(origen, tipo, destino)`:
reconstruir el grafo desde el mismo corpus nunca duplica aristas.

`build_graph` también puede correr, en paralelo y de forma aditiva, la
extracción REAL del GraphRAG Toolkit de AWS Labs (`use_real_toolkit=True` +
`toolkit_graph_store_uri`) vía `adapters.graphrag_toolkit`. Ese camino
escribe en el esquema propio del toolkit, en un namespace separado del
grafo `Entidad`/`RELACION` que responde las preguntas de la demo — nunca
reemplaza ni mezcla el grafo que el resto de este módulo construye. Ver el
docstring de `adapters.graphrag_toolkit.attempt_toolkit_extraction` para el
motivo: adoptar esas relaciones en el grafo de respuestas es una decisión
que el usuario tiene que revisar a mano, no algo que este módulo decida solo.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from pathlib import Path as RutaArchivo
from typing import Any

from second_brain.config import Stack
from second_brain.graph.extraction import LexicalGraph, extract_entities_and_relations
from second_brain.ports import Chunk

logger = logging.getLogger(__name__)


def load_chunks_from_corpus(raiz: RutaArchivo | str) -> list[Chunk]:
    """Un chunk por documento Markdown: alcanza para la extracción de relaciones.

    El corpus de la demo se diseñó con las oraciones de relación completas
    dentro de un mismo documento (ver `corpus/README.md`), así que no hace
    falta la granularidad fina que sí necesitaría el chunking para el vector
    store (eso lo resuelve el pipeline de ingesta, no este módulo).

    Excluye `README.md` por el mismo motivo que `ingestion.load_corpus`
    (`ingestion.py:57`): es el contrato de diseño del corpus para humanos, no
    contenido indexable. Sin esta exclusión el grafo terminaba con una arista
    (`billing-2-0 -DEPENDE_DE-> auth-cache`) extraída de una TABLA de ese
    README, con provenance `README` — un documento que el vector store no
    contiene, así que la cita no se podía resolver. Peor: contradecía el
    principio de `graph/extraction.py` (una arista que no viene del corpus
    vuelve el grafo no auditable).
    """
    archivos = sorted(p for p in RutaArchivo(raiz).rglob("*.md") if p.name != "README.md")
    return [_load_chunk(ruta) for ruta in archivos]


def _load_chunk(path: RutaArchivo) -> Chunk:
    crudo = path.read_text(encoding="utf-8")
    metadata, cuerpo = _split_frontmatter(crudo)
    slug = path.stem
    metadata["ruta"] = str(path)
    return Chunk(id=slug, document_id=slug, text=cuerpo, metadata=metadata)


def _split_frontmatter(crudo: str) -> tuple[dict[str, Any], str]:
    if not crudo.startswith("---\n"):
        return {}, crudo
    fin = crudo.find("\n---\n", 4)
    if fin == -1:
        return {}, crudo
    bloque = crudo[4:fin]
    cuerpo = crudo[fin + 5 :]
    metadata = dict(
        _split_frontmatter_line(linea) for linea in bloque.splitlines() if ":" in linea
    )
    return metadata, cuerpo


def _split_frontmatter_line(linea: str) -> tuple[str, str]:
    clave, _, valor = linea.partition(":")
    return clave.strip(), valor.strip()


def build_graph(
    corpus: RutaArchivo | str | Iterable[Chunk],
    stack: Stack,
    *,
    use_llm: bool = False,
    use_real_toolkit: bool = False,
    toolkit_graph_store_uri: str | None = None,
) -> LexicalGraph:
    """Extrae el grafo léxico y lo upsertea al `GraphStorePort` del stack.

    `use_llm=False` (default) corre el extractor determinista — el modo
    seguro para CI y para el ensayo local, sin red. `use_llm=True` pasa
    `stack.llm` a la extracción (modo AWS con Nova). La firma no lee
    `Settings` directamente a propósito: quien arma el `Stack` ya decidió el
    modo, y este módulo no debe redecidirlo por su cuenta.

    `use_real_toolkit=True` (default `False`, siempre off en local y en los
    tests) intenta ADEMÁS `LexicalGraphIndex.extract_and_build` del GraphRAG
    Toolkit real, sobre `toolkit_graph_store_uri` — un namespace separado
    del grafo que este módulo upsertea. No cambia el `LexicalGraph`
    devuelto ni lo que queda en `stack.graph_store`: es un intento aditivo,
    pensado para correr solo cuando hay un LLM generativo real disponible
    (modo AWS). Si `toolkit_graph_store_uri` es `None`, o el intento falla
    por cualquier motivo, no pasa nada más que un log — el grafo principal
    de esta función se construye igual, con el camino determinista/LLM
    propio de siempre.
    """
    chunks = _resolve_chunks(corpus)
    llm = stack.llm if use_llm else None
    graph = extract_entities_and_relations(chunks, llm)
    _upsert_graph(graph, stack)
    if use_real_toolkit and toolkit_graph_store_uri:
        _attempt_real_toolkit_extraction(chunks, toolkit_graph_store_uri, stack)
    return graph


def _attempt_real_toolkit_extraction(
    chunks: list[Chunk], graph_store_uri: str, stack: Stack
) -> None:
    from second_brain.adapters.graphrag_toolkit import attempt_toolkit_extraction

    exito = attempt_toolkit_extraction(chunks, graph_store_uri, stack.llm)
    if exito:
        logger.info(
            "GraphRAG Toolkit: extracción real completada en '%s' (namespace propio, "
            "no mezclada con el grafo de respuestas)",
            graph_store_uri,
        )
    else:
        logger.info(
            "GraphRAG Toolkit: no se pudo correr la extracción real, sigue el camino propio"
        )


def _resolve_chunks(corpus: RutaArchivo | str | Iterable[Chunk]) -> list[Chunk]:
    if isinstance(corpus, (str, RutaArchivo)):
        return load_chunks_from_corpus(corpus)
    return list(corpus)


def _upsert_graph(graph: LexicalGraph, stack: Stack) -> None:
    stack.graph_store.upsert_nodes([{"id": entidad} for entidad in sorted(graph.entities)])
    stack.graph_store.upsert_edges(
        [
            {
                "origen": relacion.source,
                "destino": relacion.target,
                "tipo": relacion.type,
                "documento_id": relacion.document_id,
                "fragmento": relacion.fragment,
            }
            for relacion in graph.relations
        ]
    )
