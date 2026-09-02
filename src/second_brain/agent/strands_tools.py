"""Envuelve `agent.tools.search_documents`/`traverse_graph` (y, si la
memoria está activa, `recall_memory`) como tools de Strands: acá es donde
el loop agéntico deja de ser un pipeline con Strands encima y pasa a ser
el modelo el que decide CUÁNDO llamar cada una y CON QUÉ argumentos (qué
`target` ancla la búsqueda, si hace falta navegar el grafo y desde qué
entidad, o si conviene recordar contexto antes de buscar).

Las dos tools de evidencia devuelven texto plano (lo que el modelo necesita
leer para redactar) pero ADEMÁS acumulan la `Evidence` real en un
`EvidenceCollector` compartido: es lo que le permite a
`agent.gate_hook.CoverageGateHook` evaluar cobertura con el mismo
`agent.gate.evaluate_coverage` que usa el pipeline fijo, sin tener que
re-parsear el string que ya se le mandó al modelo.

`recall_memory` es DELIBERADAMENTE distinta: devuelve texto también, pero
NUNCA llama a `collector.add(...)` — ver el docstring de `EvidenceCollector`
para por qué esa separación de tipo es la que hace imposible (no solo
improbable) que un recuerdo termine siendo evidencia citable o moviendo el
coverage gate.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from strands import tool
from strands.tools.decorator import DecoratedFunctionTool

from second_brain.agent.memory import format_memory_hints, recall_memory_fail_open
from second_brain.agent.tools import Evidence, search_documents, traverse_graph
from second_brain.config import Stack
from second_brain.ports import MemoryHint, TraceStep
from second_brain.retrieval import LexicalIndex, resolve_targets


@dataclass
class EvidenceCollector:
    """Acumula toda la evidencia de este turno agéntico, más el rastro de
    qué `target`/entidad resolvió cada llamada — para que quien orquesta el
    turno (`agent.strands_agent.answer_agentic`) sepa, DESPUÉS de que el
    modelo terminó de decidir, cuál fue el sujeto sobre el que ancló los
    guards de salida (`agent.postprocess.apply_guards`), sin tener que
    resolverlo de nuevo por su cuenta.

    `memory_hints`/`evidence_tool_called` son la mitad del invariante
    "memoria es pista, nunca evidencia": `memory_hints` guarda lo último que
    trajo la tool `recall_memory` SOLO para que `agent.tool_trace_hook`
    arme su línea de traza (cuántos recuerdos, de qué origen) — nunca se
    mezcla con `items`, así que `agent.gate.evaluate_coverage`,
    `extract_citations` y `validate_relational_claims` (todos consumen
    `items`, nunca este campo) no pueden verlo ni por accidente.
    `evidence_tool_called` solo lo prende `add()` (llamado por
    `search_documents`/`traverse_graph`, nunca por `recall_memory`): es lo
    que le permite a `agent.gate_hook.CoverageGateHook` diferir su
    evaluación mientras el modelo todavía no llamó ninguna tool de
    evidencia real, sin que un turno que arrancó con `recall_memory` solo
    (el escenario de memoria de sesión) se aborte antes de tiempo.
    """

    items: list[Evidence] = field(default_factory=list)
    resolved_targets: list[str] = field(default_factory=list)
    evidence_tool_called: bool = False
    memory_hints: list[MemoryHint] = field(default_factory=list)

    def add(self, evidence: list[Evidence]) -> None:
        self.items.extend(evidence)
        self.evidence_tool_called = True

    def register_target(self, target: str | None, stack: Stack) -> None:
        if not target:
            return
        resueltos = resolve_targets(target, stack)
        if resueltos:
            self.resolved_targets = resueltos


def _format_evidence(items: list[Evidence]) -> str:
    if not items:
        return "Sin resultados: no hay evidencia indexada para esta búsqueda."
    return "\n".join(f'[source:{item.doc_id}] "{item.text}"' for item in items)


def build_tools(
    stack: Stack,
    lexical_index: LexicalIndex,
    collector: EvidenceCollector,
    *,
    actor_id: str | None = None,
    session_id: str | None = None,
    trace: list[TraceStep] | None = None,
) -> list[DecoratedFunctionTool]:
    """Arma las tools del turno, cerradas sobre `stack`/`lexical_index` y
    acumulando en `collector`. Se llama una vez POR TURNO (no se reutiliza
    entre preguntas) porque `collector` es específico de un turno.

    `recall_memory` (tercera tool) solo se agrega cuando la memoria está
    REALMENTE activa para este turno: `stack.memory` configurado Y
    `actor_id`/`session_id` explícitos, ambos truthy. Sin alguno de los
    tres, el modelo ni se entera de que la tool existe — nunca hay riesgo
    de que la intente llamar con un `actor_id`/`session_id` vacío y dispare
    tráfico a AWS por accidente (invariante de la charla: memoria solo se
    activa con configuración explícita, nunca por default). `actor_id`/
    `session_id` quedan fijos por turno (a diferencia de `MemoryPort.recall`,
    que los recibe por llamada) porque los conoce quien orquesta el turno
    (`agent.strands_agent.answer_agentic`), no el modelo.
    """

    @tool(name="search_documents")
    def _search_documents_tool(question: str, target: str | None = None) -> str:
        """Busca evidencia citable en la base de conocimiento indexada.

        Args:
            question: La pregunta o sub-pregunta a buscar.
            target: Nombre del documento/entidad sobre el que ancla la
                pregunta si la pregunta nombra un sujeto claro (por
                ejemplo 'core-billing', 'reportes-frontend'). Dejalo vacío
                si la pregunta no nombra un sujeto específico.
        """
        collector.register_target(target, stack)
        evidencia = search_documents(question, stack, lexical_index, target=target)
        collector.add(evidencia)
        return _format_evidence(evidencia)

    @tool(name="traverse_graph")
    def _traverse_graph_tool(
        entity: str, kind: str = "blast_radius", max_hops: int = 3
    ) -> str:
        """Recorre el grafo de dependencias de Nexora Corp desde `entity`.

        Args:
            entity: Slug de la entidad raíz del traversal (por ejemplo
                'core-billing', 'auth-cache').
            kind: 'blast_radius' (default, quién depende de `entity`),
                'vecinos' (vecindario directo) o 'camino_entre' (requiere
                pasar también un destino — no soportado desde esta tool,
                usá 'blast_radius' o 'vecinos').
            max_hops: Cuántos saltos como máximo recorrer.
        """
        evidencia = traverse_graph(entity, stack, kind=kind, max_hops=max_hops)
        collector.add(evidencia)
        return _format_evidence(evidencia)

    tools: list[DecoratedFunctionTool] = [_search_documents_tool, _traverse_graph_tool]

    if stack.memory is not None and actor_id and session_id:
        traza = trace if trace is not None else []

        @tool(name="recall_memory")
        def _recall_memory_tool(query: str) -> str:
            """Recupera recuerdos de esta sesión/actor: turnos previos de la
            conversación (STM), hechos guardados y preferencias declaradas
            (LTM). Es una PISTA, JAMÁS EVIDENCIA — nunca la cites con
            `[source:...]`.

            Args:
                query: Qué buscar en memoria — el tema de la pregunta
                    actual, o el antecedente de una referencia anafórica
                    ("eso", "el mismo que antes").
            """
            pistas = recall_memory_fail_open(stack, actor_id, session_id, query, traza)
            collector.memory_hints = pistas
            return format_memory_hints(pistas)

        tools.append(_recall_memory_tool)

    return tools
