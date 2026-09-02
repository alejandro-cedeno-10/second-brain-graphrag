"""El camino agéntico real: un `Agent` de Strands con las tools de
`agent.strands_tools`, que decide por su cuenta cuándo y con qué argumentos
llamar `search_documents`/`traverse_graph`/`recall_memory` — a diferencia de
`agent.orchestrator.answer`, que las invoca siempre en el mismo orden fijo
(y que se queda sin memoria: cablearla ahí es otro workstream).

Lo que SÍ se conserva idéntico frente al pipeline fijo (mismo módulo,
`agent.postprocess`, para que no puedan divergir): la extracción de citas
y los guards de salida (`validate_citations`, `validate_relational_claims`,
`guard_urls`, el `canario`). La garantía anti-alucinación no depende de
quién decidió qué evidencia recolectar.

Lo que cambia es DÓNDE corre el coverage gate: ver
`agent.gate_hook.CoverageGateHook` para el punto de diseño delicado
(`AfterToolsEvent.end_turn`) y la limitación que motiva la red de
seguridad de acá abajo — un modelo que se salta las tools por completo no
dispara `AfterToolsEvent`, así que `answer_agentic` verifica DESPUÉS de
que el agente terminó que hubo evidencia real antes de dejar pasar
cualquier respuesta que no sea una abstención.

MEMORIA — por qué una tool explícita y no `MemoryManager(injection=True)`:
Strands ya trae `strands.memory.memory_manager.MemoryManager`, que puede
inyectar recuerdos en el contexto de forma automática (verificado por
introspección real contra `strands-agents==1.54.0`; ver también
`second_brain.memory.strands_compat.MemoryPortStrandsAdapter`, que prueba
esa compatibilidad pero no la usa). Se descarta acá a propósito por tres
razones: (1) no produce un tool call interceptable por
`agent.tool_trace_hook.ToolTraceHook`, así que la traza de la demo
("¿de dónde salió este recuerdo, cuántos entraron?") tendría que
reconstruirse por otro lado; (2) duplicaría el modelo de datos (`MemoryEntry`
de Strands vs. `ports.MemoryHint` propio) sin necesidad; (3) es más máquina
de la que el turno necesita — el invariante "memoria es pista, nunca
evidencia" ya lo garantiza el TIPO (`ports.MemoryHint` nunca se vuelve
`Evidence`), no dónde vive la inyección. En cambio, `recall_memory` es una
TERCERA tool más (`agent.strands_tools.build_tools`), y
`MEMORY_PROMPT_ADDENDUM` (`agent.memory`) le dice al modelo que la llame
PRIMERO cuando corresponda — el modelo decide, igual que decide cuándo
llamar `search_documents`/`traverse_graph`.

MEMORIA — activación: nunca por default, en tres capas obligatorias a la
vez (ver `config.Settings`/`config.build_stack` para las primeras dos):
`stack.memory` configurado (modo + flag + id de AgentCore, o flag en modo
local) Y `actor_id`/`session_id` explícitos pasados a esta función
(keyword-only, default `None`). Sin las tres, `recall_memory` ni se agrega
a la lista de tools — el modelo ni se entera de que existe, cero riesgo de
tráfico a AWS por accidente.

MEMORIA — después del turno: `remember_turn_fail_open` (`agent.memory`)
guarda pregunta+respuesta al final, SIEMPRE que la memoria esté activa
(incluso si el turno terminó en abstención: es contexto de conversación
legítimo). AgentCore Memory real es EVENTUALMENTE CONSISTENTE — un turno
guardado acá no se garantiza legible por un `recall_memory` del turno
siguiente, y mucho menos del mismo turno (ver el docstring de
`remember_turn_fail_open`).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from strands import Agent

from second_brain.agent.gate import ABSTENTION_MESSAGE, Coverage
from second_brain.agent.gate_hook import CoverageGateHook
from second_brain.agent.memory import MEMORY_PROMPT_ADDENDUM, remember_turn_fail_open
from second_brain.agent.observability import configure_observability
from second_brain.agent.postprocess import (
    apply_guards,
    entity_from_doc_id,
    extract_citations,
    measure_canary,
)
from second_brain.agent.strands_model import LlmPortModel
from second_brain.agent.strands_tools import EvidenceCollector, build_tools
from second_brain.agent.tool_trace_hook import ToolTraceHook
from second_brain.agent.trace import ObservableTrace
from second_brain.config import Stack
from second_brain.ports import Answer, TraceStep
from second_brain.retrieval import LexicalIndex

AGENTIC_SYSTEM_PROMPT = """\
Sos el agente GraphRAG de Nexora Corp. Tenés dos herramientas: \
`search_documents` (busca evidencia citable en la base de conocimiento \
indexada) y `traverse_graph` (recorre el grafo de dependencias entre \
servicios).

REGLA NO NEGOCIABLE: nunca redactes una respuesta sin haber llamado antes \
a `search_documents` — si no lo hacés, tu respuesta se descarta y se \
reemplaza por una abstención, sin importar qué hayas escrito. Si la \
pregunta es relacional (quién depende de, qué se rompe, qué consume, qué \
causa algo), llamá también a `traverse_graph` con la entidad \
correspondiente ANTES de redactar: el grafo es la fuente de verdad para \
esas relaciones, no la prosa suelta de un documento.

Pasále `target` a `search_documents` cuando la pregunta nombre un sujeto \
claro (un slug como 'core-billing', un nombre propio, una sigla): eso \
ancla la búsqueda al documento correcto en vez de competir contra todo \
el corpus.

FORMATO DE CITA: cada afirmación basada en evidencia lleva inmediatamente \
después la marca `[source:doc_id]`, usando EXACTAMENTE el `doc_id` que \
aparece en el resultado de la herramienta — no lo abrevies ni lo inventes. \
Una afirmación sin evidencia que la sostenga no lleva marca.

REGLA DE ANCLAJE AL SUJETO: abrí la respuesta con lo que la evidencia \
SOBRE EL SUJETO PREGUNTADO dice, aunque sea poco. Si es delgada, decilo \
explícitamente en vez de pivotear hacia un sujeto con más evidencia. La \
evidencia de otros sujetos entra solo como comparación EXPLÍCITAMENTE \
marcada ("a diferencia de...", "mientras que..."), nunca como si \
respondiera la pregunta original.

HONESTIDAD: si las herramientas no devuelven evidencia, o solo cubren \
parte de lo preguntado, decilo en vez de inventar un dato, un nombre o \
una cifra. Nunca afirmes una relación (depende de, es responsable de, \
causó) que la evidencia no sostenga explícitamente, aunque cites \
documentos reales: un puente inventado entre dos citas reales sigue \
siendo una alucinación.\
"""

_EMPTY_LEXICAL_INDEX = LexicalIndex(
    chunks=[], frequencies=[], lengths=[], idf={}, average_length=0.0
)


def answer_agentic(
    question: str,
    stack: Stack,
    lexical_index: LexicalIndex | None = None,
    on_paso: Callable[[TraceStep], None] | None = None,
    *,
    actor_id: str | None = None,
    session_id: str | None = None,
) -> Answer:
    """Mismo contrato que `agent.orchestrator.answer` (misma firma, mismo
    `Answer`, misma traza compatible con `demo.py --trace` y `web/api.py`),
    con la recuperación de evidencia delegada al loop de un `Agent` de
    Strands en vez de a un orden fijo de llamadas.

    `actor_id`/`session_id` son keyword-only, default `None`, y son la
    TERCERA capa de activación de memoria (ver el docstring del módulo):
    con cualquiera de los dos ausente, `memoria_activa` da `False` y el
    comportamiento es byte a byte el de antes de que existiera memoria —
    ni se agrega la tool `recall_memory`, ni se toca `stack.memory` para
    nada, ni se concatena `MEMORY_PROMPT_ADDENDUM` al prompt.
    """
    configure_observability()
    trace: list[TraceStep] = ObservableTrace(on_paso)
    indice = lexical_index if lexical_index is not None else _EMPTY_LEXICAL_INDEX
    collector = EvidenceCollector()
    memoria_activa = stack.memory is not None and bool(actor_id) and bool(session_id)
    tools = build_tools(
        stack, indice, collector, actor_id=actor_id, session_id=session_id, trace=trace
    )
    gate_hook = CoverageGateHook(question, collector, trace)
    model = LlmPortModel(stack.llm)
    system_prompt = (
        AGENTIC_SYSTEM_PROMPT + MEMORY_PROMPT_ADDENDUM
        if memoria_activa
        else AGENTIC_SYSTEM_PROMPT
    )

    agent = Agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        hooks=[ToolTraceHook(collector, trace), gate_hook],
        callback_handler=None,
    )
    resultado = agent(question)
    texto = str(resultado).strip()

    trace.append(
        TraceStep(
            stage="objetivos.resueltos",
            detail=f"objetivos={collector.resolved_targets}",
            metadata={"objetivos": collector.resolved_targets},
        )
    )
    trace.append(
        TraceStep(
            stage="agente.llamadas_modelo",
            detail=f"{model.call_count} llamada(s) al modelo ({resultado.stop_reason})",
            metadata={"llamadas_modelo": model.call_count, "detiene_por": resultado.stop_reason},
        )
    )

    respuesta = _resolve_answer(texto, collector, gate_hook, trace)
    if memoria_activa:
        assert actor_id is not None and session_id is not None
        remember_turn_fail_open(stack, actor_id, session_id, question, respuesta.text, trace)
    metrica = measure_canary(respuesta, trace)
    trace.append(
        TraceStep(
            stage="canario",
            detail=(
                f"tool_calls={metrica.tool_calls} citas={metrica.citations} "
                f"drift={metrica.drift} abstencion={metrica.abstention_form}"
            ),
            metadata={
                "tool_calls": metrica.tool_calls,
                "citas": metrica.citations,
                "drift": metrica.drift,
            },
        )
    )
    return replace(respuesta, trace=list(trace))


def _resolve_answer(
    text: str,
    collector: EvidenceCollector,
    gate_hook: CoverageGateHook,
    trace: list[TraceStep],
) -> Answer:
    """Decide si lo que produjo el `Agent` se deja pasar o se reemplaza por
    abstención — ver el docstring del módulo para por qué esta red de
    seguridad es necesaria además del hook.
    """
    if gate_hook.cut_turn:
        return Answer(text=ABSTENTION_MESSAGE, citations=[], abstained=True, trace=list(trace))

    if not collector.items:
        trace.append(
            TraceStep(
                stage="gate.cobertura",
                detail=(
                    "cobertura=sin_evidencia (0 evidencias: el modelo no llamó ninguna "
                    "tool de evidencia — recall_memory, si lo llamó, no cuenta)"
                ),
                metadata={"cobertura": Coverage.NO_EVIDENCE.value},
            )
        )
        trace.append(
            TraceStep(
                stage="gate.abstencion",
                detail="sin evidencia: se fuerza abstención aunque el modelo redactó",
            )
        )
        return Answer(text=ABSTENTION_MESSAGE, citations=[], abstained=True, trace=list(trace))

    target_doc_id = collector.resolved_targets[0] if collector.resolved_targets else None
    turn_subject = entity_from_doc_id(target_doc_id) if target_doc_id else None
    citas = extract_citations(text, collector.items)
    respuesta = Answer(text=text, citations=citas, abstained=False, trace=list(trace))
    return apply_guards(respuesta, collector.items, turn_subject, trace)
