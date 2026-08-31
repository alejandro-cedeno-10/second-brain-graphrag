"""Los adapters locales cumplen estructuralmente los puertos que declaran implementar.

No se testea contenido semántico exacto de FakeEmbeddings/FakeRerank acá
(eso viven en sus propios tests si hicieran falta) — el objetivo de este
archivo es blindar el CONTRATO: que la forma de cada adapter coincide con
el `Protocol` correspondiente, y que las propiedades básicas de dominio
(determinismo, cercanía semántica aproximada) se sostienen.
"""

from __future__ import annotations

from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
from second_brain.adapters.local.fake_rerank import FakeRerank
from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
from second_brain.adapters.local.scripted_llm import ScriptedLlm
from second_brain.ports import (
    Chunk,
    EmbeddingsPort,
    LlmPort,
    LlmResponse,
    RerankPort,
    VectorStorePort,
)


def test_fake_embeddings_satisfies_the_port() -> None:
    assert isinstance(FakeEmbeddings(), EmbeddingsPort)


def test_fake_embeddings_is_deterministic() -> None:
    embeddings = FakeEmbeddings(dim=64)
    primero = embeddings.embed(["María lidera el Proyecto Beta"])
    segundo = embeddings.embed(["María lidera el Proyecto Beta"])
    assert primero == segundo


def test_fake_embeddings_respects_the_configured_dimension() -> None:
    embeddings = FakeEmbeddings(dim=64)
    (vector,) = embeddings.embed(["cualquier texto"])
    assert embeddings.dim == 64
    assert len(vector) == 64


def test_fake_embeddings_brings_closer_texts_with_shared_words() -> None:
    embeddings = FakeEmbeddings(dim=256)
    ancla, cercano, lejano = embeddings.embed(
        [
            "María lidera el Proyecto Beta en Nexora Corp",
            "¿Quién lidera el Proyecto Beta?",
            "El clima en la ciudad estuvo templado durante la tarde",
        ]
    )
    similitud_cercana = _cosine(ancla, cercano)
    similitud_lejana = _cosine(ancla, lejano)
    assert similitud_cercana > similitud_lejana


def test_memory_vector_store_satisfies_the_port() -> None:
    assert isinstance(MemoryVectorStore(), VectorStorePort)


def test_memory_vector_store_returns_the_most_similar_first() -> None:
    embeddings = FakeEmbeddings(dim=128)
    store = MemoryVectorStore()
    textos = {
        "beta": "María lidera el Proyecto Beta",
        "clima": "El clima estuvo templado durante toda la tarde",
    }
    for chunk_id, texto in textos.items():
        (vector,) = embeddings.embed([texto])
        store.upsert([Chunk(id=chunk_id, document_id="doc-1", text=texto, embedding=vector)])

    (vector_pregunta,) = embeddings.embed(["¿Quién lidera el Proyecto Beta?"])
    resultados = store.search(vector_pregunta, top_k=2)

    assert resultados[0].chunk_id == "beta"


def test_memory_vector_store_applies_metadata_filter() -> None:
    embeddings = FakeEmbeddings(dim=32)
    store = MemoryVectorStore()
    (vector_a,) = embeddings.embed(["contenido A"])
    (vector_b,) = embeddings.embed(["contenido A"])
    chunk_a = Chunk(
        id="a",
        document_id="d1",
        text="contenido A",
        embedding=vector_a,
        metadata={"area": "billing"},
    )
    chunk_b = Chunk(
        id="b",
        document_id="d2",
        text="contenido A",
        embedding=vector_b,
        metadata={"area": "pagos"},
    )
    store.upsert([chunk_a, chunk_b])

    resultados = store.search(vector_a, top_k=5, filter={"area": "pagos"})

    assert [hit.chunk_id for hit in resultados] == ["b"]


def test_fake_rerank_satisfies_the_port() -> None:
    assert isinstance(FakeRerank(), RerankPort)


def test_fake_rerank_prioritizes_higher_lexical_overlap() -> None:
    rerank = FakeRerank()
    resultados = rerank.rerank(
        question="¿Quién lidera el Proyecto Beta?",
        documents=[
            "El clima estuvo templado durante la tarde",
            "María lidera el Proyecto Beta desde enero",
        ],
        top_n=2,
    )
    assert resultados[0].text == "María lidera el Proyecto Beta desde enero"


def test_scripted_llm_satisfies_the_port() -> None:
    assert isinstance(ScriptedLlm(), LlmPort)


def test_scripted_llm_consumes_the_sequence_in_order() -> None:
    llm = ScriptedLlm(
        sequence=[
            LlmResponse(text="primero"),
            LlmResponse(text="segundo"),
        ]
    )
    primera = llm.generate(system="s", messages=[])
    segunda = llm.generate(system="s", messages=[])

    assert primera.text == "primero"
    assert segunda.text == "segundo"


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b, strict=True))
