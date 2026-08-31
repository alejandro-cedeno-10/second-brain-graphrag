"""Grafo de contexto (P2): extracción sobre el corpus real + traversal multi-hop.

"Si modifico la API de `core-billing`, ¿qué módulos se rompen?" es la
pregunta que sostiene este archivo. Los tests corren contra el corpus REAL
en `corpus/`, no contra fixtures inventadas, porque el contrato es que las
frases del corpus (verbo explícito: "consume", "depende de") alcanzan para
que la extracción por patrones arme el grafo sin ayuda manual.
"""

from __future__ import annotations

import json
from pathlib import Path as RutaArchivo

import pytest

from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
from second_brain.adapters.local.fake_rerank import FakeRerank
from second_brain.adapters.local.falkor_graph_store import FalkorGraphStore
from second_brain.adapters.local.memory_graph_store import MemoryGraphStore
from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
from second_brain.adapters.local.scripted_llm import ScriptedLlm
from second_brain.config import Stack
from second_brain.graph.build import build_graph, load_chunks_from_corpus
from second_brain.graph.extraction import extract_entities_and_relations
from second_brain.graph.traversal import blast_radius, neighbors_of, path_between
from second_brain.ports import Chunk, GraphStorePort, LlmResponse, TraceStep

RUTA_CORPUS = RutaArchivo(__file__).resolve().parent.parent / "corpus"


def _stack_with_graph(graph_store: GraphStorePort) -> Stack:
    return Stack(
        embeddings=FakeEmbeddings(),
        vector_store=MemoryVectorStore(),
        graph_store=graph_store,
        rerank=FakeRerank(),
        llm=ScriptedLlm(),
    )


def _build_test_graph() -> tuple[Stack, MemoryGraphStore]:
    graph_store = MemoryGraphStore()
    stack = _stack_with_graph(graph_store)
    build_graph(RUTA_CORPUS, stack)
    return stack, graph_store


def test_extraction_on_real_corpus_produces_the_p2_edges() -> None:
    chunks = load_chunks_from_corpus(RUTA_CORPUS)

    grafo = extract_entities_and_relations(chunks, None)

    aristas = {(r.source, r.type, r.target) for r in grafo.relations}
    assert ("pagos", "CONSUME", "core-billing") in aristas
    assert ("reportes-backend", "CONSUME", "core-billing") in aristas
    assert ("notificaciones", "DEPENDE_DE", "core-billing") in aristas


def test_extraction_does_not_capture_the_negation_from_notificaciones() -> None:
    """`notificaciones` NO llama directamente a `core-billing` (ADR-021): la
    frase que lo dice explícitamente está negada y no debe volverse arista.
    """
    chunks = load_chunks_from_corpus(RUTA_CORPUS)

    grafo = extract_entities_and_relations(chunks, None)

    aristas = {(r.source, r.type, r.target) for r in grafo.relations}
    assert ("notificaciones", "LLAMA_A", "core-billing") not in aristas


def test_extraction_records_lineage_and_statements_per_relation() -> None:
    chunks = load_chunks_from_corpus(RUTA_CORPUS)

    grafo = extract_entities_and_relations(chunks, None)

    documentos_en_linaje = {documento_id for documento_id, _ in grafo.lineage}
    assert "core-billing" in documentos_en_linaje
    assert len(grafo.statements) == len(grafo.relations)
    assert all(statement.text for statement in grafo.statements)


def test_build_graph_is_idempotent() -> None:
    stack, graph_store = _build_test_graph()

    build_graph(RUTA_CORPUS, stack)
    build_graph(RUTA_CORPUS, stack)

    caminos = graph_store.neighbors("core-billing", 1)
    destinos = [camino.nodes[-1] for camino in caminos]
    assert destinos.count("pagos") == 1
    assert destinos.count("reportes-backend") == 1


def test_blast_radius_core_billing_finds_the_3_consumers() -> None:
    stack, _ = _build_test_graph()

    caminos = blast_radius("core-billing", stack, max_hops=3)

    consumidores = {camino.nodes[-1] for camino in caminos}
    assert {"pagos", "notificaciones", "reportes-backend"}.issubset(consumidores)


def test_blast_radius_max_hops_2_includes_the_pagos_reportes_backend_chain() -> None:
    stack, _ = _build_test_graph()

    caminos = blast_radius("core-billing", stack, max_hops=2)

    cadena = [c for c in caminos if c.nodes == ["core-billing", "pagos", "reportes-backend"]]
    assert cadena, [c.nodes for c in caminos]


def test_blast_radius_with_max_hops_1_does_not_reach_the_2_hop_chain() -> None:
    stack, _ = _build_test_graph()

    caminos = blast_radius("core-billing", stack, max_hops=1)

    largos = {len(c.nodes) for c in caminos}
    assert largos == {2}


def test_every_blast_radius_path_carries_non_empty_provenance() -> None:
    stack, _ = _build_test_graph()

    caminos = blast_radius("core-billing", stack, max_hops=3)

    assert caminos
    for camino in caminos:
        assert len(camino.provenance) == len(camino.relations)
        assert all(documento for documento in camino.provenance)


def test_path_between_core_billing_and_reportes_backend_via_pagos() -> None:
    stack, _ = _build_test_graph()

    caminos = path_between("core-billing", "reportes-backend", stack, max_hops=2)

    largos = sorted(len(c.nodes) for c in caminos)
    assert 2 in largos
    assert 3 in largos


def test_neighbors_of_core_billing_at_one_hop() -> None:
    stack, _ = _build_test_graph()

    caminos = neighbors_of("core-billing", stack, max_hops=1)

    assert {c.nodes[-1] for c in caminos} == {"pagos", "notificaciones", "reportes-backend"}


def test_anti_hub_guard_bounds_the_expansion_and_leaves_it_in_the_trace() -> None:
    graph_store = MemoryGraphStore()
    graph_store.upsert_nodes([{"id": "origen"}, {"id": "hub"}, {"id": "detras-del-hub"}])
    graph_store.upsert_edges([{"origen": "origen", "destino": "hub", "tipo": "CONSUME"}])
    for indice in range(25):
        nodo = f"satelite-{indice}"
        graph_store.upsert_nodes([{"id": nodo}])
        graph_store.upsert_edges([{"origen": "hub", "destino": nodo, "tipo": "CONSUME"}])
    graph_store.upsert_edges(
        [{"origen": "hub", "destino": "detras-del-hub", "tipo": "CONSUME"}]
    )
    stack = _stack_with_graph(graph_store)
    traza: list[TraceStep] = []

    caminos = blast_radius("origen", stack, max_hops=2, max_degree=20, trace=traza)

    alcanzados = {c.nodes[-1] for c in caminos}
    assert "hub" in alcanzados
    assert "detras-del-hub" not in alcanzados
    assert any(paso.stage == "grafo.traversal.guardia_anti_hub" for paso in traza)
    paso_guardia = next(p for p in traza if p.stage == "grafo.traversal.guardia_anti_hub")
    assert paso_guardia.metadata is not None
    assert paso_guardia.metadata["nodo"] == "hub"
    assert paso_guardia.metadata["grado"] > 20


def test_extraction_with_llm_uses_the_same_interface_as_pattern_mode() -> None:
    chunk = Chunk(id="doc-1", document_id="doc-1", text="texto de prueba")
    respuesta = LlmResponse(
        text=json.dumps(
            [
                {
                    "origen": "servicio-a",
                    "tipo": "CONSUME",
                    "destino": "servicio-b",
                    "fragmento": "servicio-a consume servicio-b",
                }
            ]
        )
    )
    llm = ScriptedLlm(sequence=[respuesta])

    grafo = extract_entities_and_relations([chunk], llm)

    assert grafo.entities == {"servicio-a", "servicio-b"}
    assert grafo.relations[0].source == "servicio-a"
    assert grafo.relations[0].target == "servicio-b"


def test_extraction_with_llm_tolerates_a_non_json_response() -> None:
    chunk = Chunk(id="doc-1", document_id="doc-1", text="texto de prueba")
    llm = ScriptedLlm(sequence=[LlmResponse(text="no soy JSON")])

    grafo = extract_entities_and_relations([chunk], llm)

    assert grafo.relations == []


def _falkor_available(host: str = "localhost", port: int = 6379) -> bool:
    """Comprueba lo mismo que el adapter necesita: cliente instalado Y servidor vivo.

    Chequear solo el puerto con `redis` dejaba pasar el caso de un FalkorDB
    corriendo sin el cliente `falkordb` instalado: el test entraba y moría con
    `ModuleNotFoundError` en vez de saltarse, que es lo que un marcador
    `docker` promete.
    """
    try:
        import falkordb
    except ImportError:
        return False
    try:
        falkordb.FalkorDB(host=host, port=port, socket_connect_timeout=1)
    except Exception:
        return False
    return True


@pytest.mark.docker
def test_blast_radius_against_real_falkordb() -> None:
    if not _falkor_available():
        pytest.skip("no hay un FalkorDB corriendo en localhost:6379")

    nombre_grafo = "second_brain_test_grafo"
    graph_store = FalkorGraphStore(graph_name=nombre_grafo)
    stack = _stack_with_graph(graph_store)
    build_graph(RUTA_CORPUS, stack)

    try:
        caminos = blast_radius("core-billing", stack, max_hops=3)
        consumidores = {camino.nodes[-1] for camino in caminos}
        assert {"pagos", "notificaciones", "reportes-backend"}.issubset(consumidores)

        cadena = [
            c for c in caminos if c.nodes == ["core-billing", "pagos", "reportes-backend"]
        ]
        assert cadena, [c.nodes for c in caminos]
        assert all(documento for documento in cadena[0].provenance)
    finally:
        import falkordb

        falkordb.FalkorDB(host="localhost", port=6379).select_graph(nombre_grafo).delete()


def test_graph_evidence_does_not_invert_the_relation() -> None:
    """Un blast radius se recorre contra la flecha; verbalizarlo no puede invertirla.

    Antes de `Path.directions`, el camino `core-billing <-DEPENDE_DE- notificaciones`
    se verbalizaba como "core-billing depende de notificaciones": una afirmación
    falsa, exactamente lo que este sistema promete no hacer. El corpus dice lo
    contrario y la evidencia citable tiene que decir lo mismo que el corpus.
    """
    from second_brain.agent.tools import _paths_to_evidence

    stack, _ = _build_test_graph()
    caminos = blast_radius("core-billing", stack, max_hops=1)
    textos = [item.text for item in _paths_to_evidence(caminos)]

    assert any(t == "`notificaciones` depende de `core-billing`." for t in textos), textos
    assert not any(t == "`core-billing` depende de `notificaciones`." for t in textos), textos
    assert any(t == "`pagos` consume a `core-billing`." for t in textos), textos
