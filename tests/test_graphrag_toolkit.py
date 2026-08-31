"""Adapter del GraphRAG Toolkit de AWS Labs (`adapters.graphrag_toolkit`).

Cubre el contrato de fallback que sostiene el resto del sistema: si el
toolkit no está instalado, no puede conectar, o el nombre del grafo no es
alfanumérico, estas funciones devuelven `None`/`False` — nunca levantan una
excepción. La demo local tiene que arrancar igual sin el toolkit.
"""

from __future__ import annotations

from pathlib import Path as RutaArchivo

import pytest
import redis

from second_brain.adapters.graphrag_toolkit import (
    attempt_toolkit_extraction,
    falkordb_graph_store,
    is_lexical_graph_index_available,
)
from second_brain.adapters.local.falkor_graph_store import FalkorGraphStore
from second_brain.adapters.local.scripted_llm import ScriptedLlm
from second_brain.graph.build import build_graph
from second_brain.ports import LlmResponse

RUTA_CORPUS = RutaArchivo(__file__).resolve().parent.parent / "corpus"


def test_falkordb_graph_store_rejects_non_alphanumeric_database_names() -> None:
    """`second_brain_test_grafo` tiene guiones bajos: el contrib del toolkit lo rechaza.

    No es una limitación inventada por este repo: `FalkorDBDatabaseClient`
    exige `database.isalnum()`. Este test documenta esa restricción real y
    confirma que el adapter la respeta devolviendo `None` en vez de fallar.
    """
    assert falkordb_graph_store("localhost", 6379, "second_brain_test_grafo") is None


def test_falkor_graph_store_falls_back_without_the_toolkit_for_hyphenated_names() -> None:
    store = FalkorGraphStore(host="localhost", port=6379, graph_name="algo_con_guion_bajo")

    assert store._toolkit_store is None


def test_attempt_toolkit_extraction_never_raises_on_a_bad_graph_store_uri() -> None:
    llm = ScriptedLlm(sequence=[LlmResponse(text="cualquier cosa")])

    exito = attempt_toolkit_extraction([], "no-es-una-uri-valida://x", llm)

    assert exito is False


def test_build_graph_default_behavior_is_unaffected_by_the_toolkit_flags() -> None:
    """`use_real_toolkit=False` (el default) no debe tocar el grafo de respuestas."""
    from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
    from second_brain.adapters.local.fake_rerank import FakeRerank
    from second_brain.adapters.local.memory_graph_store import MemoryGraphStore
    from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
    from second_brain.config import Stack

    stack = Stack(
        embeddings=FakeEmbeddings(),
        vector_store=MemoryVectorStore(),
        graph_store=MemoryGraphStore(),
        rerank=FakeRerank(),
        llm=ScriptedLlm(),
    )

    grafo = build_graph(RUTA_CORPUS, stack)

    assert grafo.entities
    assert grafo.relations


def _falkor_available(host: str = "localhost", port: int = 6379) -> bool:
    try:
        cliente = redis.Redis(host=host, port=port, socket_connect_timeout=1)
        return bool(cliente.ping())
    except redis.exceptions.RedisError:
        return False


@pytest.mark.docker
def test_falkor_graph_store_uses_the_real_toolkit_connector_when_available() -> None:
    """Contra un FalkorDB real, con un nombre alfanumérico, el conector es el del toolkit."""
    if not _falkor_available():
        pytest.skip("no hay un FalkorDB corriendo en localhost:6379")
    if not is_lexical_graph_index_available():
        pytest.skip("graphrag-lexical-graph no está instalado")

    nombre_grafo = "secondbraintestgrafo"
    graph_store = FalkorGraphStore(graph_name=nombre_grafo)

    try:
        assert graph_store._toolkit_store is not None

        graph_store.upsert_nodes([{"id": "core-billing"}, {"id": "pagos"}])
        graph_store.upsert_edges(
            [{"origen": "pagos", "destino": "core-billing", "tipo": "CONSUME"}]
        )
        caminos = graph_store.neighbors("core-billing", 1)

        assert {camino.nodes[-1] for camino in caminos} == {"pagos"}
        assert caminos[0].directions == [False]
    finally:
        redis.Redis(host="localhost", port=6379).execute_command("GRAPH.DELETE", nombre_grafo)
