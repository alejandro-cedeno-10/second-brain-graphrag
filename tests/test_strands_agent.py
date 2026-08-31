"""El loop agéntico real (`agent.strands_agent.answer_agentic`), offline y
contra el corpus real: la comparación determinista-vs-agéntico que
`demo.py check` va a mostrar en el escenario.

La propiedad central de este archivo es la del punto de diseño más
delicado de la migración (ver `agent.gate_hook`): con evidencia, el modelo
se invoca DOS veces (decidir la tool + redactar); sin evidencia, UNA sola
vez — el coverage gate corta el turno sobre `AfterToolsEvent` y la
redacción nunca ocurre. Se mide con `LlmPortModel.call_count`, expuesto en
la traza (`agente.llamadas_modelo`), no se asume.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
from second_brain.adapters.local.fake_rerank import FakeRerank
from second_brain.adapters.local.memory_graph_store import MemoryGraphStore
from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
from second_brain.adapters.local.scripted_llm import ScriptedLlm, ScriptedRule
from second_brain.agent.strands_agent import answer_agentic
from second_brain.config import Stack
from second_brain.graph.build import build_graph
from second_brain.ingestion import chunk_document, index, load_corpus
from second_brain.ports import LlmResponse, ToolCall, TraceStep
from second_brain.retrieval import LexicalIndex, build_lexical_index

RUTA_CORPUS = Path(__file__).resolve().parent.parent / "corpus"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo import TEXTO_P_BILLING_INGENUO, build_agentic_scripted_llm  # noqa: E402

P1 = "¿Quién lidera el Proyecto Beta?"
P3 = "¿Cuál fue la facturación del Q4 2025?"
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


def _step(trace: list[TraceStep], stage: str) -> TraceStep | None:
    return next((paso for paso in trace if paso.stage == stage), None)


def _model_call_count(trace: list[TraceStep]) -> int:
    paso = _step(trace, "agente.llamadas_modelo")
    assert paso is not None and paso.metadata is not None
    return int(paso.metadata["llamadas_modelo"])


def _has_tool_result(messages: list[dict[str, Any]]) -> bool:
    return any(
        "toolResult" in block for message in messages for block in message.get("content", [])
    )


def _decide_tool(*tool_calls: ToolCall) -> ScriptedRule:
    return ScriptedRule(
        when=lambda system, messages: not _has_tool_result(messages),
        response=LlmResponse(text="", tool_calls=list(tool_calls), stop_reason="tool_use"),
    )


def _draft(text: str) -> ScriptedRule:
    return ScriptedRule(
        when=lambda system, messages: _has_tool_result(messages),
        response=LlmResponse(text=text, stop_reason="end_turn"),
    )


def test_agentic_with_evidence_makes_two_model_calls_and_applies_guards() -> None:
    texto = "María Salas lidera el Proyecto Beta [source:org/proyectos.md]."
    llm = ScriptedLlm(
        rules=[
            _decide_tool(ToolCall(name="search_documents", arguments={"question": P1}, id="t1")),
            _draft(texto),
        ]
    )
    stack, indice = _stack_and_corpus(llm)

    respuesta = answer_agentic(P1, stack, indice)

    assert respuesta.abstained is False
    assert "María Salas" in respuesta.text
    assert any(cita.document == "org/proyectos.md" for cita in respuesta.citations)
    assert _model_call_count(respuesta.trace) == 2
    assert _step(respuesta.trace, "herramienta.buscar_documentos") is not None
    assert _step(respuesta.trace, "guards.aplicados") is not None


def test_agentic_without_evidence_makes_one_model_call_and_never_drafts() -> None:
    llm = ScriptedLlm(
        rules=[
            _decide_tool(ToolCall(name="search_documents", arguments={"question": P3}, id="t1")),
            _draft("ESTO NUNCA DEBERÍA APARECER EN LA RESPUESTA"),
        ]
    )
    stack, indice = _stack_and_corpus(llm)

    respuesta = answer_agentic(P3, stack, indice)

    assert respuesta.abstained is True
    assert "NUNCA DEBERÍA APARECER" not in respuesta.text
    assert _model_call_count(respuesta.trace) == 1
    assert _step(respuesta.trace, "gate.abstencion") is not None


def test_agentic_model_that_skips_tools_is_forced_into_abstention() -> None:
    """La red de seguridad de `answer_agentic`: si el modelo redacta sin
    haber llamado ninguna tool, `AfterToolsEvent` nunca dispara (no hubo
    tools que ejecutar) y el hook no puede cortar nada — la verificación
    posterior determinista es la que evita que esa respuesta sin evidencia
    llegue a la sala.
    """
    respuesta_directa = LlmResponse(text="Un dato inventado.", stop_reason="end_turn")
    llm = ScriptedLlm(default_response=respuesta_directa)
    stack, indice = _stack_and_corpus(llm)

    respuesta = answer_agentic(P1, stack, indice)

    assert respuesta.abstained is True
    assert "Un dato inventado" not in respuesta.text
    assert _model_call_count(respuesta.trace) == 1


def test_agentic_billing_2_0_degrades_the_invented_bridge_like_the_fixed_path() -> None:
    """La misma propiedad que
    `test_agent.py::test_billing_2_0_bridge_is_degraded_but_the_real_dependency_and_team_survive`,
    ahora con el modelo decidiendo llamar a las dos tools: el anclaje al
    grafo (`validate_relational_claims`) no depende de qué camino generó
    la evidencia.

    `texto_malo` es `demo.TEXTO_P_BILLING_INGENUO` (importada, no
    retipeada) — la misma constante que usa
    `test_agent.py::test_billing_2_0_bridge_is_degraded_but_the_real_dependency_and_team_survive`
    y que arma `demo.py query --naive`.
    """
    texto_malo = TEXTO_P_BILLING_INGENUO
    llm = ScriptedLlm(
        rules=[
            _decide_tool(
                ToolCall(
                    name="search_documents",
                    arguments={"question": P_BILLING, "target": "billing-2-0"},
                    id="t1",
                ),
                ToolCall(
                    name="traverse_graph",
                    arguments={"entity": "billing-2-0"},
                    id="t2",
                ),
            ),
            _draft(texto_malo),
        ]
    )
    stack, indice = _stack_and_corpus(llm)

    respuesta = answer_agentic(P_BILLING, stack, indice)

    assert respuesta.abstained is False
    afirmaciones = (_step(respuesta.trace, "guards.aplicados").metadata or {})["afirmaciones"]
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
    assert _model_call_count(respuesta.trace) == 2


def test_naive_agentic_script_reproduces_the_bridge_degradation_end_to_end() -> None:
    """`demo.py query --naive --agentic`, ejercitado de verdad: el guion que
    arma `demo.build_agentic_scripted_llm(stack, naive=True)` (no uno
    armado a mano para el test) tiene que producir el mismo antes/después
    que el camino fijo — la garantía de anclaje no depende de cuál de los
    dos caminos generó la síntesis.
    """
    stack, indice = _stack_and_corpus(None)
    stack.llm = build_agentic_scripted_llm(stack, naive=True)

    respuesta = answer_agentic(P_BILLING, stack, indice)

    assert respuesta.abstained is False
    afirmaciones = (_step(respuesta.trace, "guards.aplicados").metadata or {})["afirmaciones"]
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


def test_naive_agentic_flag_leaves_other_questions_untouched() -> None:
    """El mismo contrato de `naive` que en el camino fijo: solo cambia la
    síntesis de `P_BILLING`, ninguna otra pregunta del guion agéntico.
    """
    stack, indice = _stack_and_corpus(None)
    stack.llm = build_agentic_scripted_llm(stack, naive=True)

    respuesta = answer_agentic(P1, stack, indice)

    assert respuesta.abstained is False
    assert "María Salas" in respuesta.text
