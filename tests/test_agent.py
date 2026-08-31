"""Las 5 preguntas de la demo, offline y contra el corpus real.

Este archivo es la prueba de las 3 propiedades no negociables de la charla:
cita fuentes, dice "no lo sé", y cruza documentos sin perder al sujeto por
el camino. Corre contra el corpus REAL en `corpus/` (como `test_graph.py` y
`test_retrieval.py`), con un `ScriptedLlm` por pregunta que fija la síntesis
esperada — así el test verifica el PIPELINE (gate, guards, canario, el
mensaje anclado que le llega al LLM), no la calidad de un modelo real.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
from second_brain.adapters.local.fake_rerank import FakeRerank
from second_brain.adapters.local.memory_graph_store import MemoryGraphStore
from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
from second_brain.adapters.local.scripted_llm import ScriptedLlm, ScriptedRule
from second_brain.agent.gate import Coverage, evaluate_coverage
from second_brain.agent.guards import canary, validate_citations, validate_relational_claims
from second_brain.agent.orchestrator import answer
from second_brain.agent.synthesis import build_user_message, decompose
from second_brain.agent.tools import Evidence, search_documents, traverse_graph
from second_brain.config import Stack
from second_brain.graph.build import build_graph
from second_brain.ingestion import chunk_document, index, load_corpus
from second_brain.ports import Answer, Citation, LlmResponse, TraceStep
from second_brain.retrieval import LexicalIndex, build_lexical_index

RUTA_CORPUS = Path(__file__).resolve().parent.parent / "corpus"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo import TEXTO_P_BILLING_INGENUO, build_scripted_llm  # noqa: E402

P1 = "¿Quién lidera el Proyecto Beta?"
P2 = "Si modifico la API de core-billing, ¿qué módulos se rompen?"
P3 = "¿Cuál fue la facturación del Q4 2025?"
P4 = "¿Quién es la CTO y cuánto gana?"
P5 = "¿Por qué el frontend de reportes no emite eventos de Amplitude?"
P_BILLING = (
    "¿Qué dependencia puede retrasar Billing 2.0, qué equipo debe resolverla "
    "y qué decisión técnica explica el riesgo?"
)


def _stack_and_corpus(llm: Any) -> tuple[Stack, LexicalIndex]:
    stack = Stack(
        embeddings=FakeEmbeddings(),
        vector_store=MemoryVectorStore(),
        graph_store=MemoryGraphStore(),
        rerank=FakeRerank(),
        llm=llm,
    )
    corpus = load_corpus(RUTA_CORPUS)
    index(corpus, stack)
    todos_los_chunks = [chunk for doc in corpus for chunk in chunk_document(doc)]
    indice = build_lexical_index(todos_los_chunks)
    build_graph(RUTA_CORPUS, stack)
    return stack, indice


def _step(traza: list[TraceStep], stage: str) -> TraceStep | None:
    return next((paso for paso in traza if paso.stage == stage), None)


def _coverage_of(answer: Answer) -> str | None:
    paso = _step(answer.trace, "gate.cobertura")
    return paso.metadata.get("cobertura") if paso and paso.metadata else None


class _LlmEspia:
    """Doble de `LlmPort` que cuenta invocaciones — la promesa del título de la charla."""

    def __init__(self) -> None:
        self.llamadas = 0

    def generate(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> LlmResponse:
        self.llamadas += 1
        return LlmResponse(text="esto no debería generarse nunca")


def _rule(contiene: str, text: str) -> ScriptedRule:
    return ScriptedRule(
        when=lambda system, messages: contiene in messages[-1]["content"],
        response=LlmResponse(text=text),
    )


def test_gate_classifies_the_5_demo_questions_against_the_real_corpus() -> None:
    """Fija la calibración del umbral de score y de la cobertura por faceta
    (ver docstring de `agent.gate`) contra el corpus real de la demo.
    """
    stack, indice = _stack_and_corpus(ScriptedLlm())
    esperado = {
        P1: Coverage.SUFFICIENT,
        P2: Coverage.SUFFICIENT,
        P3: Coverage.NO_EVIDENCE,
        P4: Coverage.PARTIAL,
        P5: Coverage.SUFFICIENT,
    }
    for pregunta, cobertura_esperada in esperado.items():
        respuesta = answer(pregunta, stack, indice)
        assert _coverage_of(respuesta) == cobertura_esperada.value, pregunta


def test_p1_simple_question_answers_with_citation_to_projects() -> None:
    texto = "María Salas lidera el Proyecto Beta [source:org/proyectos.md]."
    llm = ScriptedLlm(rules=[_rule("Proyecto Beta", texto)])
    stack, indice = _stack_and_corpus(llm)

    respuesta = answer(P1, stack, indice)

    assert respuesta.abstained is False
    assert "María Salas" in respuesta.text
    assert any(cita.document == "org/proyectos.md" for cita in respuesta.citations)


def test_p2_blast_radius_names_the_3_consumers_without_requiring_core_billing() -> None:
    texto = (
        "Tres módulos consumen `core-billing` y se romperían: `pagos` "
        "[source:pagos], `notificaciones` [source:notificaciones] y "
        "`reportes-backend` [source:reportes-backend]."
    )
    llm = ScriptedLlm(rules=[_rule("core-billing", texto)])
    stack, indice = _stack_and_corpus(llm)

    respuesta = answer(P2, stack, indice)

    documentos_citados = {cita.document for cita in respuesta.citations}
    assert {"pagos", "notificaciones", "reportes-backend"}.issubset(documentos_citados)
    assert "core-billing.md" not in documentos_citados
    assert _coverage_of(respuesta) == Coverage.SUFFICIENT.value


def test_p3_no_evidence_abstention_and_zero_llm_tokens() -> None:
    espia = _LlmEspia()
    stack, indice = _stack_and_corpus(espia)

    respuesta = answer(P3, stack, indice)

    assert respuesta.abstained is True
    assert espia.llamadas == 0
    assert _coverage_of(respuesta) == Coverage.NO_EVIDENCE.value


def test_p4_partial_answer_names_cto_and_declares_missing_salary() -> None:
    texto = (
        "Ana Ruiz es la CTO de Nexora Corp [source:org/equipo.md]. La base "
        "de conocimiento indexada no tiene datos de nómina de las personas, "
        "así que no puedo decir cuánto gana."
    )
    llm = ScriptedLlm(rules=[_rule("CTO", texto)])
    stack, indice = _stack_and_corpus(llm)

    respuesta = answer(P4, stack, indice)

    assert "Ana Ruiz" in respuesta.text
    assert "nómina" in respuesta.text
    assert not any(char.isdigit() for char in respuesta.text)
    assert _coverage_of(respuesta) == Coverage.PARTIAL.value


def test_p5_the_trap_anchors_to_reportes_frontend_and_marks_the_comparison() -> None:
    texto = (
        "En la documentación indexada de `reportes-frontend`, el tracking se "
        "implementa con el composable `useTracking`, que envía eventos a "
        "Google Tag Manager; no hay ninguna integración con Amplitude "
        "[source:frontends/reportes-frontend.md].\n\n"
        "A diferencia de `dashboard` y `onboarding`, que sí integran "
        "Amplitude, la decisión de arquitectura (ADR-014) fue no adoptarlo "
        "en `reportes-frontend` por ser una superficie de bajo tráfico "
        "[source:arquitectura/decisiones.md]."
    )
    llm = ScriptedLlm(rules=[_rule("frontend de reportes", texto)])
    stack, indice = _stack_and_corpus(llm)

    respuesta = answer(P5, stack, indice)

    primer_parrafo = respuesta.text.split("\n\n")[0]
    assert "reportes-frontend" in primer_parrafo
    assert "GTM" in respuesta.text or "Google Tag Manager" in respuesta.text
    assert "no hay ninguna integración con Amplitude" in primer_parrafo
    assert "dashboard" not in primer_parrafo
    assert "onboarding" not in primer_parrafo
    assert "A diferencia de" in respuesta.text


def test_relational_graph_evidence_carries_no_comparison_marker() -> None:
    """El test hermano de la excepción crítica: en una pregunta relacional
    (P2), lo que un vecino del grafo hace CON la entidad consultada entra
    como evidencia DIRECTA, nunca en el bloque de comparación.
    """
    stack, _ = _stack_and_corpus(ScriptedLlm())
    build_graph(RUTA_CORPUS, stack)

    evidencia = traverse_graph("core-billing", stack, kind="blast_radius")
    mensaje = build_user_message(P2, evidencia, decompose(P2), Coverage.SUFFICIENT)

    seccion_sujeto, seccion_comparacion = mensaje.split("EVIDENCIA DE COMPARACIÓN")
    assert "[source:pagos]" in seccion_sujeto
    assert "[source:notificaciones]" in seccion_sujeto
    assert "[source:pagos]" not in seccion_comparacion
    assert "[source:notificaciones]" not in seccion_comparacion


def test_evidence_of_other_subjects_goes_to_the_comparison_block() -> None:
    stack, indice = _stack_and_corpus(ScriptedLlm())

    evidencia = search_documents(P5, stack, indice, target="frontends/reportes-frontend.md")
    mensaje = build_user_message(P5, evidencia, decompose(P5), Coverage.SUFFICIENT)

    seccion_sujeto, seccion_comparacion = mensaje.split("EVIDENCIA DE COMPARACIÓN")
    assert "[source:frontends/reportes-frontend.md]" in seccion_sujeto
    assert "[source:frontends/reportes-frontend.md]" not in seccion_comparacion


def test_own_document_of_a_blast_radius_neighbor_does_not_fall_into_comparison() -> None:
    """Regresión del riesgo que el dueño marcó explícitamente: el chunk
    propio de `pagos` (búsqueda general, sin resolver de objetivo) describe
    en prosa la misma integración con `core-billing` que el grafo reporta
    como arista. Antes de `_reanchor_graph_neighbors`, esa evidencia
    llegaba con `is_target=False` y caía en el bloque de COMPARACIÓN del
    mensaje al LLM, contradiciendo la excepción relacional que pide
    presentarla sin esa marca.
    """
    mensajes: list[str] = []

    def _capturar(system: str, messages: list[dict[str, Any]]) -> bool:
        mensajes.append(messages[-1]["content"])
        return False

    llm = ScriptedLlm(rules=[ScriptedRule(when=_capturar, response=LlmResponse(text=""))])
    stack, indice = _stack_and_corpus(llm)

    answer(P2, stack, indice)

    (mensaje,) = mensajes
    seccion_sujeto, seccion_comparacion = mensaje.split("EVIDENCIA DE COMPARACIÓN")
    for vecino in ("`pagos` procesa transacciones", "`notificaciones` centraliza"):
        assert vecino in seccion_sujeto
        assert vecino not in seccion_comparacion


def test_traverse_graph_down_degrades_to_vector_only_without_breaking_the_turn() -> None:
    """El riesgo de disponibilidad del chequeo de robustez: si `graph_store`
    lanza (FalkorDB caído, en local o en modo `aws`), `answer` no debe
    propagar la excepción -- se degrada a la evidencia vectorial/léxica y
    deja constancia del fallo en la traza.
    """

    class _GraphStoreQueRompe:
        def query(self, *args: Any, **kwargs: Any) -> list[Any]:
            raise ConnectionError("FalkorDB no disponible (simulado)")

        def neighbors(self, *args: Any, **kwargs: Any) -> list[Any]:
            raise ConnectionError("FalkorDB no disponible (simulado)")

    stack, indice = _stack_and_corpus(ScriptedLlm())
    stack.graph_store = _GraphStoreQueRompe()

    respuesta = answer(P2, stack, indice)

    assert respuesta.abstained is False
    paso_error = next(
        (p for p in respuesta.trace if p.stage == "herramienta.navegar_grafo.error"), None
    )
    assert paso_error is not None
    assert "FalkorDB no disponible" in paso_error.detail


def test_validate_citations_trims_a_fabricated_citation_and_keeps_legitimate_ones() -> None:
    evidencia = [Evidence(doc_id="org/proyectos.md", text="María Salas lidera el Proyecto Beta.")]
    respuesta = Answer(
        text=(
            "María Salas lidera el Proyecto Beta [source:org/proyectos.md]. "
            "También dirige en secreto el área de seguridad [source:org/secreto.md]."
        ),
        citations=[
            Citation(document="org/proyectos.md", fragment="María Salas lidera el Proyecto Beta."),
            Citation(document="org/secreto.md", fragment="dato inventado"),
        ],
    )

    resultado = validate_citations(respuesta, evidencia)

    assert "[source:org/proyectos.md]" in resultado.text
    assert "[source:org/secreto.md]" not in resultado.text
    assert [cita.document for cita in resultado.citations] == ["org/proyectos.md"]


def test_canary_marks_drift_when_a_searched_target_with_results_is_not_cited() -> None:
    traza = [
        TraceStep(
            stage="herramienta.buscar_documentos",
            detail="2 evidencias",
            metadata={"objetivo": "frontends/reportes-frontend.md", "resultados": 2},
        ),
    ]
    respuesta = Answer(
        text="respuesta que terminó citando otra cosa",
        citations=[Citation(document="frontends/dashboard.md", fragment="...")],
    )

    metrica = canary(respuesta, traza)

    assert "frontends/reportes-frontend.md" in metrica.drift
    assert metrica.tool_calls == 1


def test_canary_does_not_mark_drift_if_the_searched_target_was_cited() -> None:
    traza = [
        TraceStep(
            stage="herramienta.buscar_documentos",
            detail="1 evidencia",
            metadata={"objetivo": "org/equipo.md", "resultados": 1},
        ),
    ]
    respuesta = Answer(
        text="Ana Ruiz es la CTO [source:org/equipo.md].",
        citations=[Citation(document="org/equipo.md", fragment="Ana Ruiz es la CTO.")],
    )

    metrica = canary(respuesta, traza)

    assert metrica.drift == []


def test_canary_ignores_the_traverse_graph_entity_for_drift() -> None:
    """`traverse_graph` trae documentos DISTINTOS a la entidad consultada a
    propósito (esa es la respuesta de un blast radius): no es drift.
    """
    traza = [
        TraceStep(
            stage="herramienta.navegar_grafo",
            detail="3 evidencias",
            metadata={"entidad": "core-billing", "resultados": 3},
        ),
    ]
    respuesta = Answer(
        text="`pagos` consume `core-billing` [source:pagos].",
        citations=[Citation(document="pagos", fragment="...")],
    )

    metrica = canary(respuesta, traza)

    assert metrica.targets_searched == []
    assert metrica.drift == []


def test_decompose_never_leaves_zero_anchored_facets_if_the_question_names_a_subject() -> None:
    subpreguntas = decompose(P4)

    assert any(sub.subject for sub in subpreguntas)
    assert all(sub.subject == "CTO" for sub in subpreguntas)


def test_decompose_warns_but_does_not_abort_without_a_recognizable_subject(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level("WARNING"):
        subpreguntas = decompose(P3)

    assert subpreguntas
    assert any("nombra un sujeto" in registro.message for registro in caplog.records)


def test_evaluate_coverage_with_no_relevant_evidence_is_no_evidence() -> None:
    assert evaluate_coverage(P1, []) is Coverage.NO_EVIDENCE


def _text_by_stage(traza: list[TraceStep], stage: str) -> list[dict[str, Any]]:
    paso = next((p for p in traza if p.stage == stage), None)
    return list((paso.metadata or {}).get("afirmaciones", [])) if paso else []


def test_billing_2_0_bridge_is_degraded_but_the_real_dependency_and_team_survive() -> None:
    """LA prueba de la tarea: un LLM que SÍ inventa el puente causal (le echa
    la culpa a Plataforma y a ADR-017, calcado del ejemplo malo de la
    charla) tiene que salir de `validate_relational_claims` con esas DOS
    afirmaciones degradadas — pero las dos que el grafo/catálogo sí
    respaldan (la dependencia real y el equipo real) sobreviven intactas,
    en la MISMA respuesta.

    Los 4 documentos son reales y se citan los 4 en el turno (roadmap,
    catálogo de servicios, ADR-017, postmortem INC-042) — el problema nunca
    fue la cita, fue el puente inventado entre `auth-cache` y "Plataforma"
    / entre ADR-017/INC-042 y el retraso de `billing-2-0`.

    `texto_malo` es `demo.TEXTO_P_BILLING_INGENUO`, el mismo guion que
    `demo.py query --naive` usa para mostrar esto en vivo: se importa en
    vez de retipearse para que las dos copias no puedan divergir en
    silencio (ver el docstring de esa constante).
    """
    texto_malo = TEXTO_P_BILLING_INGENUO
    llm = ScriptedLlm(rules=[_rule("Billing 2.0", texto_malo)])
    stack, indice = _stack_and_corpus(llm)

    respuesta = answer(P_BILLING, stack, indice)

    assert respuesta.abstained is False

    afirmaciones = _text_by_stage(respuesta.trace, "guards.aplicados")
    por_tipo = {(a["tipo"], a["objeto"]): a["respaldada"] for a in afirmaciones}
    assert por_tipo[("DEPENDE_DE", "auth-cache")] is True
    assert any(
        tipo == "RESPONSABLE_DE" and not respaldada
        for (tipo, _objeto), respaldada in por_tipo.items()
    )
    assert any(
        tipo == "CAUSA" and not respaldada for (tipo, _objeto), respaldada in por_tipo.items()
    )

    assert "dependencia con auth-cache" in respuesta.text
    assert "sin evidencia suficiente para afirmar que Plataforma" in respuesta.text
    assert "sin evidencia suficiente para afirmar que ADR-017 es la causa" in respuesta.text

    documentos_citados = {cita.document for cita in respuesta.citations}
    assert "producto/billing-2-0.md" in documentos_citados
    assert "arquitectura/decisiones.md" not in documentos_citados
    assert "incidentes/postmortem-inc-042-auth-cache.md" not in documentos_citados


def test_naive_script_reproduces_the_bridge_degradation_end_to_end() -> None:
    """`demo.py query --naive`, ejercitado de verdad: el guion que arma
    `demo.build_scripted_llm(naive=True)` (no un `ScriptedLlm` armado a
    mano para el test, como el de arriba) tiene que producir el mismo
    antes/después que el speaker muestra en vivo — dos afirmaciones
    respaldadas, dos degradadas, en la misma respuesta.
    """
    llm = build_scripted_llm(naive=True)
    stack, indice = _stack_and_corpus(llm)

    respuesta = answer(P_BILLING, stack, indice)

    assert respuesta.abstained is False
    afirmaciones = _text_by_stage(respuesta.trace, "guards.aplicados")
    por_tipo = {(a["tipo"], a["objeto"]): a["respaldada"] for a in afirmaciones}
    assert por_tipo[("DEPENDE_DE", "auth-cache")] is True
    assert any(
        tipo == "RESPONSABLE_DE" and not respaldada
        for (tipo, _objeto), respaldada in por_tipo.items()
    )
    assert any(
        tipo == "CAUSA" and not respaldada for (tipo, _objeto), respaldada in por_tipo.items()
    )
    assert "sin evidencia suficiente para afirmar que Plataforma" in respuesta.text
    assert "sin evidencia suficiente para afirmar que ADR-017 es la causa" in respuesta.text


def test_naive_flag_leaves_the_default_script_untouched() -> None:
    """`build_scripted_llm()` sin `naive` (el default que usa `demo.py query`
    y `demo.py check`) sigue respondiendo la síntesis honesta: agregar el
    guion ingenuo no puede cambiar el comportamiento por defecto.
    """
    llm = build_scripted_llm()
    stack, indice = _stack_and_corpus(llm)

    respuesta = answer(P_BILLING, stack, indice)

    assert respuesta.abstained is False
    assert "Identidad" in respuesta.text
    assert "no hay evidencia suficiente" in respuesta.text
    assert "es responsable de resolver esa dependencia, no Plataforma" in respuesta.text
    assert "El equipo de Plataforma debe resolverlo" not in respuesta.text


def test_correct_ownership_and_dependency_claims_are_kept_untouched() -> None:
    """El espejo del test anterior: cuando el LLM afirma exactamente lo que
    el grafo y el catálogo respaldan (Identidad, no Plataforma), el guard
    no toca una sola palabra ni recorta una sola cita.
    """
    evidencia = [
        Evidence(
            doc_id="producto/billing-2-0.md",
            text="`billing-2-0` depende de `auth-cache`.",
            score=0.9,
            is_target=True,
            source="documentos",
            metadata={"equipo": "Producto"},
        ),
        Evidence(
            doc_id="servicios/auth-cache.md",
            text="`auth-cache` es propiedad del equipo de Identidad.",
            score=0.9,
            is_target=True,
            source="documentos",
            metadata={"equipo": "Identidad"},
        ),
        Evidence(
            doc_id="producto/billing-2-0.md",
            text="`billing-2-0` depende de `auth-cache`.",
            score=1.0,
            is_target=True,
            source="grafo",
        ),
    ]
    texto = (
        "Hay evidencia de que billing-2-0 depende de auth-cache "
        "[source:producto/billing-2-0.md] y de que el equipo de Identidad "
        "es responsable de resolver esa dependencia "
        "[source:servicios/auth-cache.md]."
    )
    respuesta = Answer(
        text=texto,
        citations=[
            Citation(document="producto/billing-2-0.md", fragment=""),
            Citation(document="servicios/auth-cache.md", fragment=""),
        ],
    )

    resultado, veredictos = validate_relational_claims(respuesta, evidencia)

    assert resultado.text == texto
    assert [c.document for c in resultado.citations] == [
        "producto/billing-2-0.md",
        "servicios/auth-cache.md",
    ]
    assert all(v.supported for v in veredictos)


def test_relational_claims_guard_is_a_no_op_on_answers_without_relational_language() -> None:
    """Cero afirmaciones detectables ⇒ cero cambios: el guard no toca P1."""
    respuesta = Answer(
        text="María Salas lidera el Proyecto Beta [source:org/proyectos.md].",
        citations=[Citation(document="org/proyectos.md", fragment="")],
    )
    evidencia = [Evidence(doc_id="org/proyectos.md", text="María Salas lidera el Proyecto Beta.")]

    resultado, veredictos = validate_relational_claims(respuesta, evidencia)

    assert resultado is respuesta
    assert veredictos == []
