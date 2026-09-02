"""EL COVERAGE GATE, REENGANCHADO COMO HOOK DE STRANDS — el punto de diseño
más delicado de la migración a un loop agéntico (ver PLAN_SERVICIOS_REALES.md
§3.2 y el spike que lo verificó primero con contadores reales).

En el pipeline fijo (`agent.orchestrator`), el gate corre ANTES de la única
llamada al LLM: sin evidencia, esa llamada ni se hace
(`Coverage.NO_EVIDENCE` es fail-closed, cero tokens de redacción). En un
loop agéntico eso ya no es posible — es el MODELO el que decide cuándo
buscar, así que la primera llamada al LLM ya pasó (fue la que decidió
llamar a la tool) antes de que haya evidencia para evaluar.

La migración que sostiene la misma garantía: `CoverageGateHook` se
suscribe a `AfterToolsEvent` — el evento que Strands dispara justo después
de que las tools de un batch devolvieron sus resultados y ANTES de que el
loop vuelva a invocar al modelo para que redacte. Si la evidencia
acumulada hasta ahora es `Coverage.NO_EVIDENCE`, el hook fija
`event.end_turn` con el mensaje de abstención: eso corta el loop ahí mismo,
`stop_reason` queda en `"end_turn"` y el modelo NUNCA hace la segunda
llamada de redacción.

El número que hay que decir en el escenario cambia en consecuencia: ya no
es "cero llamadas al LLM" — es **una llamada de decisión, cero de
redacción**. Verificado con `LlmPortModel.call_count` (contador real, no
estimado) en `tests/test_strands_agent.py`: con evidencia, 2 llamadas
(decidir + redactar); sin evidencia, 1 llamada (decidir buscar), el gate
corta, la redacción nunca ocurre.

Limitación conocida: el hook evalúa cobertura después de CADA batch de
tools, y corta en el primer `NO_EVIDENCE` que ve — un modelo que quisiera
reintentar con una búsqueda distinta tras un primer resultado vacío no
tiene esa oportunidad acá (mismo espíritu fail-closed que el pipeline
fijo: ante la duda, abstenerse, no dejar que seguir intentando genere una
llamada de más). Si el modelo se salta las tools por completo y redacta
directo en su primera respuesta, `AfterToolsEvent` no llega a dispararse
—no hubo tools que ejecutar— así que esta capa por sí sola no lo cubre:
`agent.strands_agent.answer_agentic` cierra ese hueco con una verificación
posterior determinista (ver su docstring), para que ninguna respuesta
salga sin evidencia real sin importar qué haga el modelo.

MEMORIA (`recall_memory`, ver `agent.strands_tools`/`agent.memory`): el
escenario de continuidad de sesión necesita que el modelo pueda llamar
`recall_memory` SOLO, en su primer batch, antes de saber siquiera qué
buscar — si este hook evaluara cobertura ahí (cero `Evidence`, porque
`recall_memory` nunca llama a `collector.add(...)`) cortaría el turno con
`Coverage.NO_EVIDENCE` antes de que el modelo llegara a `search_documents`.
Por eso el hook DIFIERE su evaluación (no corta, pero tampoco evalúa)
mientras `EvidenceCollector.evidence_tool_called` siga en `False` — ese
flag solo lo prende `add()`, que solo llaman `search_documents`/
`traverse_graph`, nunca `recall_memory`. La red de seguridad de
`answer_agentic` sigue cubriendo el caso límite de un modelo que llamara
SOLO `recall_memory` y redactara igual sin evidencia real: `collector.items`
queda vacío, así que esa respuesta se fuerza a abstención lo mismo.
"""

from __future__ import annotations

from strands.hooks.events import AfterToolsEvent
from strands.hooks.registry import HookProvider, HookRegistry

from second_brain.agent.gate import ABSTENTION_MESSAGE, Coverage, evaluate_coverage
from second_brain.agent.strands_tools import EvidenceCollector
from second_brain.ports import TraceStep


class CoverageGateHook(HookProvider):
    """Evalúa cobertura después de cada batch de tools y corta el turno
    (sin dejar que el modelo redacte) si la evidencia acumulada es
    `Coverage.NO_EVIDENCE`.

    `last_coverage` y `cut_turn` quedan expuestos para que quien orquesta
    el turno (`answer_agentic`) y los tests puedan verificar el veredicto
    sin tener que re-leer la traza.
    """

    def __init__(self, question: str, collector: EvidenceCollector, trace: list[TraceStep]) -> None:
        self._question = question
        self._collector = collector
        self._trace = trace
        self.last_coverage: Coverage | None = None
        self.cut_turn = False

    def register_hooks(self, registry: HookRegistry, **kwargs: object) -> None:
        registry.add_callback(AfterToolsEvent, self._on_after_tools)

    def _on_after_tools(self, event: AfterToolsEvent) -> None:
        if not self._collector.evidence_tool_called:
            self._trace.append(
                TraceStep(
                    stage="gate.cobertura.diferido",
                    detail=(
                        "cobertura diferida: todavía no se llamó una tool de "
                        "evidencia (solo recall_memory hasta ahora)"
                    ),
                )
            )
            return
        cobertura = evaluate_coverage(self._question, self._collector.items)
        self.last_coverage = cobertura
        self._trace.append(
            TraceStep(
                stage="gate.cobertura",
                detail=f"cobertura={cobertura.value} ({len(self._collector.items)} evidencias)",
                metadata={"cobertura": cobertura.value},
            )
        )
        if cobertura is Coverage.NO_EVIDENCE:
            event.end_turn = ABSTENTION_MESSAGE
            self.cut_turn = True
            self._trace.append(
                TraceStep(
                    stage="gate.abstencion",
                    detail="sin evidencia: el modelo no redacta (end_turn cortado post-tools)",
                )
            )
