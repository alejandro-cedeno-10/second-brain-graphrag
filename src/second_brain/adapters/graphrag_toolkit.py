"""Único módulo del paquete que conoce al GraphRAG Toolkit de AWS Labs.

Toda referencia a `graphrag_toolkit` / `graphrag_toolkit_contrib` /
`llama_index` vive acá adentro. `adapters/local/falkor_graph_store.py` y
`graph/build.py` llaman a estas funciones — nunca importan el toolkit
directamente. Así "el toolkit entra por un adapter" es literal y
`second_brain.ports` no necesita saber que existe.

Cada función acá adentro está escrita para el escenario real de la charla:
si el toolkit no está instalado, si un import se rompe, o si la llamada
falla por cualquier motivo (sin red, versión incompatible, contrib
ausente), estas funciones devuelven `None`/`False` en vez de propagar la
excepción. Quien llama decide caer al camino propio determinista — nunca al
revés. La demo tiene que arrancar igual sin el toolkit instalado.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from second_brain.ports import Chunk, LlmPort

logger = logging.getLogger(__name__)

_falkordb_factory_registered = False


def falkordb_graph_store(host: str, port: int, database: str) -> Any | None:
    """Conector FalkorDB real del toolkit (`GraphStoreFactory` + contrib), o `None`.

    El grafo entra al sistema por un único puerto, `GraphStorePort`, y hoy lo
    implementa `FalkorGraphStore` tanto en modo local como en modo `aws` (ver
    `config.py::_stack_aws`): el motor de grafo no cambia entre los dos
    modos, solo el host al que apunta (`SECOND_BRAIN_FALKOR_HOST`).

    `database` tiene que ser alfanumérico: es una validación real del
    contrib (`FalkorDBDatabaseClient.__init__` rechaza cualquier otro
    nombre), no una limitación inventada acá. Un `graph_name` con guiones
    bajos (como el que usan los tests contra un FalkorDB real) no puede
    pasar por este camino y el llamador debe caer al cliente `falkordb`
    directo — mismo Cypher, mismo esquema `Entidad`/`RELACION`, sin que el
    resto del sistema note la diferencia.
    """
    global _falkordb_factory_registered
    if not database.isalnum():
        return None
    try:
        from graphrag_toolkit.lexical_graph.storage.graph_store_factory import (
            GraphStoreFactory,
        )
        from graphrag_toolkit_contrib.lexical_graph.storage.graph.falkordb import (
            FalkorDBGraphStoreFactory,
        )
    except ImportError as exc:
        logger.info(
            "GraphRAG Toolkit (contrib FalkorDB) no disponible, uso el cliente directo: %s", exc
        )
        return None

    if not _falkordb_factory_registered:
        GraphStoreFactory.register(FalkorDBGraphStoreFactory)
        _falkordb_factory_registered = True
    try:
        return GraphStoreFactory.for_graph_store(f"falkordb://{host}:{port}", database=database)
    except Exception as exc:  # noqa: BLE001 - cualquier falla cae al cliente directo
        logger.warning(
            "El GraphRAG Toolkit no pudo conectar a FalkorDB, uso el cliente directo: %s", exc
        )
        return None


def is_lexical_graph_index_available() -> bool:
    """`True` si `graphrag-lexical-graph` está instalado e importa sin error."""
    try:
        import graphrag_toolkit.lexical_graph  # noqa: F401
    except ImportError:
        return False
    return True


def attempt_toolkit_extraction(chunks: list[Chunk], graph_store_uri: str, llm: LlmPort) -> bool:
    """Corre `LexicalGraphIndex.extract_and_build` de verdad sobre el corpus.

    Escribe en el esquema PROPIO del toolkit (nodos Document/Chunk/
    Statement/Fact/Entity), en el namespace/base de datos que traiga
    `graph_store_uri` — nunca el `Entidad`/`RELACION` que responde las
    preguntas de la demo. Es intencional: adoptar automáticamente las
    relaciones que el toolkit extraiga (con un LLM real) hacia el grafo de
    respuestas es una decisión que el usuario tiene que revisar a mano
    (¿coinciden con lo que el corpus sostiene? ¿agregan aristas que no
    deberían existir, como algo que conecte ADR-017 o INC-042 con
    `billing-2-0`?) — este adapter deliberadamente NO hace ese merge.

    Devuelve `False` ante cualquier falla (import, red, LLM ausente, error
    interno del toolkit) — nunca levanta una excepción. `llm` tiene que ser
    un `LlmPort` real capaz de generar texto libre (p.ej. `BedrockLlm`);
    correrlo sin un LLM generativo real no tiene sentido y va a fallar acá
    adentro, con lo cual el llamador debe seguir con el camino determinista.
    """
    try:
        from graphrag_toolkit.lexical_graph import LexicalGraphIndex
        from llama_index.core import Settings as LlamaIndexSettings
        from llama_index.core.schema import Document as LlamaDocument

        from second_brain.adapters.graphrag_toolkit_llm import LlmPortAsLlamaIndexLlm
    except ImportError as exc:
        logger.info("GraphRAG Toolkit no disponible para extracción real: %s", exc)
        return False

    try:
        LlamaIndexSettings.llm = LlmPortAsLlamaIndexLlm(llm_port=llm)
        documents = [
            LlamaDocument(
                text=chunk.text, doc_id=chunk.id, metadata={"document_id": chunk.document_id}
            )
            for chunk in chunks
        ]
        index = LexicalGraphIndex(graph_store=graph_store_uri)
        index.extract_and_build(documents)
        return True
    except Exception as exc:  # noqa: BLE001 - cualquier falla cae al camino determinista
        logger.warning(
            "La extracción real del GraphRAG Toolkit falló, sigue el camino propio: %s", exc
        )
        return False
