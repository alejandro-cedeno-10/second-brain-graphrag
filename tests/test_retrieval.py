"""Tests offline del retrieval híbrido (patrón 1: retrieve-then-rerank).

Todo corre con los adapters fake/locales — sin red, sin Docker, sin AWS —
salvo el test end-to-end, que además carga el corpus real del repo para
probar que el pipeline completo trae la evidencia correcta de verdad.
"""

from __future__ import annotations

from pathlib import Path

from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
from second_brain.adapters.local.fake_rerank import FakeRerank
from second_brain.adapters.local.falkor_graph_store import FalkorGraphStore
from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
from second_brain.adapters.local.scripted_llm import ScriptedLlm
from second_brain.config import Stack
from second_brain.ingestion import chunk_document, index, load_corpus
from second_brain.ports import Chunk, Hit
from second_brain.retrieval import (
    build_lexical_index,
    fuse_rrf,
    resolve_targets,
    retrieve,
    search_lexical,
    search_semantic,
)

_RUTA_CORPUS = Path(__file__).resolve().parents[1] / "corpus"


def _local_stack(dim: int = 256) -> Stack:
    return Stack(
        embeddings=FakeEmbeddings(dim=dim),
        vector_store=MemoryVectorStore(),
        graph_store=FalkorGraphStore(),
        rerank=FakeRerank(),
        llm=ScriptedLlm(),
    )


def _index_chunks(stack: Stack, chunks: list[Chunk]) -> None:
    for chunk in chunks:
        (chunk.embedding,) = stack.embeddings.embed([chunk.text])
    stack.vector_store.upsert(chunks)


def test_rrf_rewards_agreement_across_rankings_over_winning_a_single_one() -> None:
    ranking_semantico = [
        Hit(chunk_id="X", text="x", score=0.9),
        Hit(chunk_id="Y", text="y", score=0.8),
        Hit(chunk_id="Z", text="z", score=0.7),
        Hit(chunk_id="W", text="w", score=0.6),
    ]
    ranking_lexico = [
        Hit(chunk_id="Q", text="q", score=9.0),
        Hit(chunk_id="R", text="r", score=8.0),
        Hit(chunk_id="S", text="s", score=7.0),
        Hit(chunk_id="Y", text="y", score=6.0),
    ]

    fusionados = fuse_rrf([ranking_semantico, ranking_lexico], k=60)

    assert fusionados[0].chunk_id == "Y"
    assert fusionados[0].score > fusionados[1].score


def test_bm25_finds_the_exact_identifier_that_semantic_search_loses() -> None:
    objetivo = Chunk(
        id="obj", document_id="d-obj", text="La referencia de la operacion es TX-90210"
    )
    distractores = [
        Chunk(
            id=f"dist{i}",
            document_id=f"d-dist{i}",
            text="reporte de pagos y transacciones concilia mensualmente el equipo",
        )
        for i in range(5)
    ]
    chunks = [objetivo, *distractores]
    stack = _local_stack()
    _index_chunks(stack, chunks)
    indice_lexico = build_lexical_index(chunks)
    pregunta = "reporte de pagos y transacciones concilia mensualmente TX-90210"

    resultado_semantico = search_semantic(pregunta, stack, top_k=3)
    resultado_lexico = search_lexical(pregunta, indice_lexico, top_k=3)

    assert "obj" not in {hit.chunk_id for hit in resultado_semantico}
    assert resultado_lexico[0].chunk_id == "obj"


def test_ambiguous_is_not_nonexistent() -> None:
    corpus = load_corpus(_RUTA_CORPUS)
    stack = _local_stack()
    index(corpus, stack)

    objetivos = resolve_targets("reportes", stack)

    assert len(objetivos) > 1
    assert "servicios/reportes-backend.md" in objetivos
    assert "frontends/reportes-frontend.md" in objetivos


def test_resolve_targets_exact_slug_gives_a_single_candidate() -> None:
    corpus = load_corpus(_RUTA_CORPUS)
    stack = _local_stack()
    index(corpus, stack)

    assert resolve_targets("core-billing", stack) == ["servicios/core-billing.md"]


def test_resolve_targets_with_no_evidence_returns_empty() -> None:
    stack = _local_stack()

    assert resolve_targets("cualquier-cosa", stack) == []


def test_retrieve_end_to_end_brings_the_proyectos_chunk_in_the_top_3() -> None:
    corpus = load_corpus(_RUTA_CORPUS)
    stack = _local_stack()
    index(corpus, stack)
    todos_los_chunks = [chunk for doc in corpus for chunk in chunk_document(doc)]
    indice_lexico = build_lexical_index(todos_los_chunks)

    resultados = retrieve(
        "¿Quién lidera el Proyecto Beta?",
        stack,
        indice_lexico,
        top_k_per_method=5,
        top_n_final=3,
    )

    doc_ids = {resultado.metadata.get("doc_id") for resultado in resultados}
    assert "org/proyectos.md" in doc_ids
