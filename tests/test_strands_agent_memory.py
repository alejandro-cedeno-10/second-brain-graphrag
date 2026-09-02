"""Cableado de memoria en el camino agéntico (`agent.strands_agent.answer_agentic`
+ `agent.strands_tools.build_tools` + `agent.gate_hook.CoverageGateHook` +
`agent.tool_trace_hook.ToolTraceHook`), offline y contra el corpus real.

Cubre el invariante central de la charla: memoria es PISTA, nunca EVIDENCIA.
- Un turno cuya ÚNICA base es memoria sigue abstiniéndose (no genera citas,
  no mueve el veredicto del gate).
- Una afirmación relacional falsa que llega vía memoria se degrada por el
  MISMO anclaje al grafo que una alucinación del modelo — el guard no sabe
  ni le importa de dónde salió la prosa.
- Con memoria apagada (por cualquiera de las tres capas: `stack.memory`
  ausente, o `actor_id`/`session_id` no pasados), la salida es idéntica a
  la de antes de que existiera memoria.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
from second_brain.adapters.local.fake_memory_store import FakeMemoryStore
from second_brain.adapters.local.fake_rerank import FakeRerank
from second_brain.adapters.local.memory_graph_store import MemoryGraphStore
from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
from second_brain.adapters.local.scripted_llm import ScriptedLlm, ScriptedRule
from second_brain.agent.gate import ABSTENTION_MESSAGE
from second_brain.agent.strands_agent import answer_agentic
from second_brain.agent.strands_tools import EvidenceCollector, build_tools
from second_brain.config import Stack
from second_brain.graph.build import build_graph
from second_brain.ingestion import chunk_document, index, load_corpus
from second_brain.ports import LlmResponse, ToolCall, TraceStep
from second_brain.retrieval import LexicalIndex, build_lexical_index

RUTA_CORPUS = Path(__file__).resolve().parent.parent / "corpus"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from demo import TEXTO_P_BILLING_INGENUO  # noqa: E402

P1 = "¿Quién lidera el Proyecto Beta?"
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


# --- build_tools: la tercera capa de activación -----------------------------


def test_build_tools_only_registers_recall_memory_when_fully_active() -> None:
    stack, indice = _stack_and_corpus(None)
    collector = EvidenceCollector()

    sin_memoria = build_tools(stack, indice, collector)
    assert {t.tool_name for t in sin_memoria} == {"search_documents", "traverse_graph"}

    stack.memory = FakeMemoryStore()
    con_memoria_pero_sin_actor = build_tools(
        stack, indice, collector, actor_id=None, session_id="sesion-1"
    )
    assert {t.tool_name for t in con_memoria_pero_sin_actor} == {
        "search_documents",
        "traverse_graph",
    }
    con_memoria_pero_sin_sesion = build_tools(
        stack, indice, collector, actor_id="actor-1", session_id=None
    )
    assert {t.tool_name for t in con_memoria_pero_sin_sesion} == {
        "search_documents",
        "traverse_graph",
    }

    con_memoria_activa = build_tools(
        stack, indice, collector, actor_id="actor-1", session_id="sesion-1"
    )
    assert {t.tool_name for t in con_memoria_activa} == {
        "search_documents",
        "traverse_graph",
        "recall_memory",
    }


# --- invariante: memoria nunca es evidencia ---------------------------------


def test_memory_only_recall_never_becomes_evidence_and_still_abstains() -> None:
    """Si la ÚNICA base del turno es un recuerdo (el modelo llama
    `recall_memory` y redacta directo, sin `search_documents`/
    `traverse_graph`), la respuesta sigue siendo abstención — aunque el
    modelo haya intentado marcar el recuerdo como si fuera una cita real.
    """
    llm = ScriptedLlm(
        rules=[
            _decide_tool(ToolCall(name="recall_memory", arguments={"query": P1}, id="m1")),
            _draft("María Salas lidera el Proyecto Beta [source:memoria]."),
        ]
    )
    stack, indice = _stack_and_corpus(llm)
    stack.memory = FakeMemoryStore()
    stack.memory.seed_hecho("actor-1", "María Salas lidera el Proyecto Beta")

    respuesta = answer_agentic(P1, stack, indice, actor_id="actor-1", session_id="sesion-1")

    assert respuesta.abstained is True
    assert respuesta.text == ABSTENTION_MESSAGE
    assert respuesta.citations == []

    paso_memoria = _step(respuesta.trace, "herramienta.recordar_memoria")
    assert paso_memoria is not None
    assert paso_memoria.detail == "1 recuerdo (STM sesión=0, LTM hechos=1, LTM preferencias=0)"
    assert paso_memoria.metadata == {
        "resultados": 1,
        "turno_stm": 0,
        "hecho": 1,
        "preferencia": 0,
    }

    assert _step(respuesta.trace, "gate.cobertura.diferido") is not None
    assert _step(respuesta.trace, "herramienta.buscar_documentos") is None
    assert _step(respuesta.trace, "gate.abstencion") is not None


def test_relational_claim_sourced_from_memory_is_degraded_by_graph_anchoring() -> None:
    """Un hecho FALSO sembrado en memoria ("Plataforma es responsable de
    auth-cache") pasa por el MISMO anclaje al grafo
    (`validate_relational_claims`) que una alucinación del modelo — el
    mismo antes/después que
    `test_strands_agent.py::test_agentic_billing_2_0_degrades_the_invented_bridge_like_the_fixed_path`,
    ahora con el modelo apoyándose en un recuerdo (no en su propia
    invención) para llegar al mismo texto malo (`demo.TEXTO_P_BILLING_INGENUO`).
    """
    llm = ScriptedLlm(
        rules=[
            _decide_tool(
                ToolCall(name="recall_memory", arguments={"query": P_BILLING}, id="m1"),
                ToolCall(
                    name="search_documents",
                    arguments={"question": P_BILLING, "target": "billing-2-0"},
                    id="t1",
                ),
                ToolCall(name="traverse_graph", arguments={"entity": "billing-2-0"}, id="t2"),
            ),
            _draft(TEXTO_P_BILLING_INGENUO),
        ]
    )
    stack, indice = _stack_and_corpus(llm)
    stack.memory = FakeMemoryStore()
    stack.memory.seed_hecho(
        "actor-1",
        "El equipo de Plataforma debe resolver la dependencia de billing-2-0 con auth-cache.",
    )

    respuesta = answer_agentic(P_BILLING, stack, indice, actor_id="actor-1", session_id="sesion-1")

    assert respuesta.abstained is False
    assert _step(respuesta.trace, "herramienta.recordar_memoria") is not None

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
    assert not any(cita.document == "memoria" for cita in respuesta.citations)


# --- invariante: apagada, byte a byte igual que hoy -------------------------


def _p1_script() -> ScriptedLlm:
    return ScriptedLlm(
        rules=[
            _decide_tool(ToolCall(name="search_documents", arguments={"question": P1}, id="t1")),
            _draft("María Salas lidera el Proyecto Beta [source:org/proyectos.md]."),
        ]
    )


def test_memory_configured_but_without_session_id_behaves_like_memory_off() -> None:
    """`stack.memory` configurado (una `FakeMemoryStore` con hechos
    sembrados) pero SIN `session_id` explícito: la tercera capa de
    activación sigue apagada (ver docstring de `answer_agentic`), así que
    el resultado tiene que ser idéntico al de un `Stack` sin memoria en
    absoluto — ni una tool de más, ni un renglón de traza de más.
    """
    stack_sin_memoria, indice_1 = _stack_and_corpus(_p1_script())
    respuesta_base = answer_agentic(P1, stack_sin_memoria, indice_1)

    stack_con_memoria, indice_2 = _stack_and_corpus(_p1_script())
    stack_con_memoria.memory = FakeMemoryStore()
    stack_con_memoria.memory.seed_hecho("actor-1", "cualquier hecho sembrado")
    respuesta_sin_session_id = answer_agentic(P1, stack_con_memoria, indice_2, actor_id="actor-1")

    assert respuesta_sin_session_id.text == respuesta_base.text
    assert respuesta_sin_session_id.citations == respuesta_base.citations
    assert respuesta_sin_session_id.abstained == respuesta_base.abstained

    for traza in (respuesta_base.trace, respuesta_sin_session_id.trace):
        assert _step(traza, "herramienta.recordar_memoria") is None
        assert _step(traza, "memoria.guardado") is None
        assert _step(traza, "gate.cobertura.diferido") is None


def test_memory_configured_but_without_actor_id_behaves_like_memory_off() -> None:
    stack_con_memoria, indice = _stack_and_corpus(_p1_script())
    stack_con_memoria.memory = FakeMemoryStore()
    stack_con_memoria.memory.seed_hecho("actor-1", "cualquier hecho sembrado")

    respuesta = answer_agentic(P1, stack_con_memoria, indice, session_id="sesion-1")

    assert _step(respuesta.trace, "herramienta.recordar_memoria") is None
    assert _step(respuesta.trace, "memoria.guardado") is None


# --- después del turno: se guarda para la sesión siguiente ------------------


def test_active_memory_remembers_the_turn_after_answering() -> None:
    memoria = FakeMemoryStore()
    stack, indice = _stack_and_corpus(_p1_script())
    stack.memory = memoria

    respuesta = answer_agentic(P1, stack, indice, actor_id="actor-1", session_id="sesion-1")

    assert _step(respuesta.trace, "memoria.guardado") is not None
    turnos = [
        h
        for h in memoria.recall("actor-1", "sesion-1", "cualquier query")
        if h.kind == "turno_stm"
    ]
    assert len(turnos) == 1
    assert P1 in turnos[0].text
    assert "María Salas" in turnos[0].text
