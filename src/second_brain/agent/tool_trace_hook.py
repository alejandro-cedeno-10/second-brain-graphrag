"""Traduce cada llamada a tool que el modelo decidió hacer a los mismos
nombres de etapa (`herramienta.buscar_documentos`, `herramienta.navegar_grafo`)
que ya usa el pipeline fijo (`agent.orchestrator`) — así `demo.py --trace` y
el mapeo AG-UI de `web/api.py` (`herramienta.*` → TOOL_CALL_*) funcionan
igual sin importar qué camino generó la traza.
"""

from __future__ import annotations

from strands.hooks.events import AfterToolCallEvent
from strands.hooks.registry import HookProvider, HookRegistry

from second_brain.agent.strands_tools import EvidenceCollector
from second_brain.ports import TraceStep

_STAGE_BY_TOOL = {
    "search_documents": "herramienta.buscar_documentos",
    "traverse_graph": "herramienta.navegar_grafo",
}


class ToolTraceHook(HookProvider):
    """Un renglón de traza por cada tool call real que el modelo emitió.

    Limitación conocida: `objetivo` lee `collector.resolved_targets`, que
    `EvidenceCollector.register_target` solo REEMPLAZA cuando el `target`
    de esa llamada resuelve a algo — si un turno hiciera dos llamadas a
    `search_documents`, una con `target` y una sin, la segunda arrastraría
    el valor resuelto de la primera en vez de mostrar `None`. No ocurre en
    el guion de la demo (una sola `search_documents` por turno); una
    corrección completa necesitaría snapshotear el estado ANTES de cada
    tool call, no solo después.
    """

    def __init__(self, collector: EvidenceCollector, trace: list[TraceStep]) -> None:
        self._collector = collector
        self._trace = trace
        self._previous_count = 0

    def register_hooks(self, registry: HookRegistry, **kwargs: object) -> None:
        registry.add_callback(AfterToolCallEvent, self._on_after_tool)

    def _on_after_tool(self, event: AfterToolCallEvent) -> None:
        nombre = event.tool_use.get("name", "")
        stage = _STAGE_BY_TOOL.get(nombre)
        if stage is None:
            return
        agregada = self._collector.items[self._previous_count :]
        self._previous_count = len(self._collector.items)
        argumentos = event.tool_use.get("input") or {}
        if nombre == "search_documents":
            clave = "objetivo"
            # El `doc_id` YA RESUELTO (no el `target` crudo que pasó el
            # modelo): `agent.guards.canary` compara este valor contra
            # `Citation.document` para medir drift, y las citas siempre
            # llevan el `doc_id` resuelto — comparar contra el string sin
            # resolver del modelo generaría un "drift" falso en cada turno.
            resueltos = self._collector.resolved_targets
            valor = resueltos[0] if resueltos else None
        else:
            clave, valor = "entidad", argumentos.get("entity")
        self._trace.append(
            TraceStep(
                stage=stage,
                detail=f"{len(agregada)} evidencias ({clave}={valor})",
                metadata={clave: valor, "resultados": len(agregada)},
            )
        )
