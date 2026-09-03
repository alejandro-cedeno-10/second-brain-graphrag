"""Tests offline del recuperador gestionado (Bedrock Knowledge Bases).

Sin red: la KB se dobla con un stub que cumple `KnowledgeBasePort`. Lo que
se prueba acá es el CABLEADO — que la KB sume un ranking sin desplazar a los
otros dos, que apagada el pipeline quede idéntico, y que un fallo suyo
degrade en vez de romper.
"""

from __future__ import annotations

import pytest

from second_brain.adapters.aws.knowledge_base_store import KnowledgeBaseStore
from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
from second_brain.adapters.local.fake_rerank import FakeRerank
from second_brain.adapters.local.falkor_graph_store import FalkorGraphStore
from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
from second_brain.adapters.local.scripted_llm import ScriptedLlm
from second_brain.agent.gate import Coverage, evaluate_coverage
from second_brain.agent.tools import Evidence
from second_brain.config import Settings, Stack, build_stack
from second_brain.ports import Chunk, Hit, KnowledgeBasePort
from second_brain.retrieval import build_lexical_index, retrieve

_PREGUNTA = "¿Qué equipo opera core-billing?"


class _KbFalsa:
    """Doble de la KB: devuelve lo que se le dio, o explota si se le pidió."""

    def __init__(self, hits: list[Hit] | None = None, explota: bool = False) -> None:
        self._hits = hits or []
        self._explota = explota
        self.llamadas = 0

    def retrieve(self, question: str, top_k: int) -> list[Hit]:
        self.llamadas += 1
        if self._explota:
            raise RuntimeError("AccessDeniedException simulada")
        return self._hits[:top_k]


def _chunks() -> list[Chunk]:
    return [
        Chunk(id="c1", document_id="servicios/core-billing.md",
              text="`core-billing` es el servicio central de facturación."),
        Chunk(id="c2", document_id="org/equipo-plataforma.md",
              text="El equipo de Plataforma opera los servicios core."),
    ]


def _stack(knowledge_base: KnowledgeBasePort | None = None) -> Stack:
    stack = Stack(
        embeddings=FakeEmbeddings(dim=256),
        vector_store=MemoryVectorStore(),
        graph_store=FalkorGraphStore(),
        rerank=FakeRerank(),
        llm=ScriptedLlm(),
        knowledge_base=knowledge_base,
    )
    chunks = _chunks()
    for chunk in chunks:
        (chunk.embedding,) = stack.embeddings.embed([chunk.text])
    stack.vector_store.upsert(chunks)
    return stack


def test_el_puerto_lo_cumple_el_adapter_real() -> None:
    assert isinstance(KnowledgeBaseStore(knowledge_base_id="KB123"), KnowledgeBasePort)


def test_sin_kb_el_pipeline_no_la_consulta() -> None:
    stack = _stack(knowledge_base=None)
    resultados = retrieve(_PREGUNTA, stack, build_lexical_index(_chunks()))
    assert resultados


def test_con_kb_apagada_el_resultado_es_identico_al_de_siempre() -> None:
    """La KB es opt-in: apagada, `retrieve` debe dar exactamente lo mismo."""
    esperado = retrieve(_PREGUNTA, _stack(None), build_lexical_index(_chunks()))
    kb = _KbFalsa(hits=[Hit(chunk_id="s3://b/otro.md", text="ruido", score=0.99)])
    stack_con_kb = _stack(knowledge_base=kb)
    stack_con_kb.knowledge_base = None

    obtenido = retrieve(_PREGUNTA, stack_con_kb, build_lexical_index(_chunks()))

    assert [d.text for d in obtenido] == [d.text for d in esperado]
    assert kb.llamadas == 0


def test_la_kb_aporta_un_candidato_que_el_vector_store_no_tenia() -> None:
    kb = _KbFalsa(hits=[
        Hit(chunk_id="s3://bucket/arquitectura/decisiones.md",
            text="ADR-014: la analítica de reportes no adopta Amplitude.",
            score=0.88, metadata={"doc_id": "arquitectura/decisiones.md"}),
    ])
    stack = _stack(knowledge_base=kb)

    resultados = retrieve(_PREGUNTA, stack, build_lexical_index(_chunks()), top_n_final=10)

    assert kb.llamadas == 1
    assert any("ADR-014" in doc.text for doc in resultados)


def test_un_fallo_de_la_kb_degrada_en_vez_de_romper() -> None:
    """Fail-open: la KB es evidencia ADICIONAL, su caída no puede tumbar el turno."""
    kb = _KbFalsa(explota=True)
    stack = _stack(knowledge_base=kb)

    resultados = retrieve(_PREGUNTA, stack, build_lexical_index(_chunks()))

    assert kb.llamadas == 1
    assert resultados


def test_el_adapter_traduce_la_uri_de_s3_al_doc_id_que_se_cita() -> None:
    """`[source:doc_id]` es contrato del sintetizador: la KB no puede citar URLs."""
    store = KnowledgeBaseStore(knowledge_base_id="KB123")
    hit = store._to_hit({
        "content": {"text": "texto"},
        "score": 0.8,
        "location": {"s3Location": {"uri": "s3://mi-bucket/servicios/core-billing.md"}},
        "metadata": {"x-amz-bedrock-kb-chunk-id": "chunk-1"},
    })

    assert hit.metadata["doc_id"] == "servicios/core-billing.md"
    assert hit.metadata["origen"] == "knowledge_base"
    assert hit.chunk_id == "chunk-1"


def test_dos_chunks_del_mismo_documento_no_comparten_chunk_id() -> None:
    """Con la URI como id, `fuse_rrf` sumaba dos veces al mismo documento."""
    store = KnowledgeBaseStore(knowledge_base_id="KB123")
    uri = "s3://mi-bucket/arquitectura/decisiones.md"
    a = store._to_hit({"content": {"text": "a"}, "score": 0.9,
                       "location": {"s3Location": {"uri": uri}},
                       "metadata": {"x-amz-bedrock-kb-chunk-id": "c-1"}})
    b = store._to_hit({"content": {"text": "b"}, "score": 0.8,
                       "location": {"s3Location": {"uri": uri}},
                       "metadata": {"x-amz-bedrock-kb-chunk-id": "c-2"}})

    assert a.chunk_id != b.chunk_id
    assert a.metadata["doc_id"] == b.metadata["doc_id"]


@pytest.mark.parametrize(
    ("enabled", "kb_id", "espera_kb"),
    [(False, "KB123", False), (True, None, False), (True, "KB123", True)],
)
def test_la_kb_necesita_las_dos_condiciones_para_cablearse(
    enabled: bool, kb_id: str | None, espera_kb: bool
) -> None:
    settings = Settings(mode="aws", knowledge_base_enabled=enabled, bedrock_kb_id=kb_id)
    assert (build_stack(settings).knowledge_base is not None) is espera_kb


def test_un_doc_fuera_del_contrato_del_corpus_le_cuesta_la_abstencion_al_gate() -> None:
    """Fija POR QUE las dos ingestas tienen que cubrir el mismo conjunto de documentos.

    `ingestion.load_corpus` excluye `README.md` a propósito (es contrato de
    diseño para humanos, no contenido indexable). La KB indexa el prefijo
    completo del bucket, así que sí lo trae — y para "¿Cuál fue la facturación
    del Q4 2025?" el reranker lo puntúa 0.82 porque habla de servicios de
    facturación, aunque no contenga ni un dato de Q4. Con la KB apagada el
    mejor score es 0.35 y el gate marca SIN_EVIDENCIA; con la KB prendida ese
    0.82 pasa el umbral y el gate marca SUFICIENTE.

    Resuelto en la capa correcta: `infra/subir-corpus.py` no sube el README al
    bucket del data source, así que la KB ya no lo indexa y P3 vuelve a
    abstenerse con la KB PRENDIDA (verificado, 03-sep-2026). Este test se
    queda como candado: fija que un documento fuera del contrato del corpus,
    entre por donde entre, le cuesta la abstención al gate.
    """
    ruido = Evidence(
        doc_id="README.md",
        text="Corpus diseñado a mano para la demo: servicios de facturación, equipos y ADRs.",
        score=0.8198,
        source="documentos",
    )
    solo_del_corpus = Evidence(
        doc_id="servicios/core-billing.md",
        text="`core-billing` es el servicio central de facturación.",
        score=0.3502,
        source="documentos",
    )
    pregunta = "¿Cuál fue la facturación del Q4 2025?"

    assert evaluate_coverage(pregunta, [solo_del_corpus]) is Coverage.NO_EVIDENCE
    assert evaluate_coverage(pregunta, [solo_del_corpus, ruido]) is not Coverage.NO_EVIDENCE
