"""Traduce cada llamada a tool que el modelo decidió hacer a los mismos
nombres de etapa (`herramienta.buscar_documentos`, `herramienta.navegar_grafo`,
`herramienta.recordar_memoria`) que ya usa (o usaría) el pipeline fijo — así
`demo.py --trace` y el mapeo AG-UI de `web/api.py` (`herramienta.*` →
TOOL_CALL_*) funcionan igual sin importar qué camino generó la traza.

`recall_memory` tiene una rama propia en `_on_after_tool` en vez de caer en
la lógica genérica de las otras dos: esa lógica lee el delta de
`collector.items` (`EvidenceCollector.add`), y `recall_memory` A PROPÓSITO
nunca llama a `add` (memoria es pista, nunca evidencia — ver
`agent.strands_tools.EvidenceCollector`), así que no hay delta que leer.
En cambio lee `collector.memory_hints` (lo último que trajo esa tool) para
decir cuántos recuerdos entraron y de qué origen (STM de la sesión, LTM de
hechos, LTM de preferencias).
"""

from __future__ import annotations

from collections import Counter

from strands.hooks.events import AfterToolCallEvent
from strands.hooks.registry import HookProvider, HookRegistry

from second_brain.agent.strands_tools import EvidenceCollector
from second_brain.ports import MemoryHint, TraceStep

_STAGE_BY_TOOL = {
    "search_documents": "herramienta.buscar_documentos",
    "traverse_graph": "herramienta.navegar_grafo",
    "recall_memory": "herramienta.recordar_memoria",
}

_MEMORY_KIND_LABELS = (
    ("turno_stm", "STM sesión"),
    ("hecho", "LTM hechos"),
    ("preferencia", "LTM preferencias"),
)


def _memory_recall_detail(hints: list[MemoryHint]) -> tuple[str, dict[str, int]]:
    conteos = Counter(hint.kind for hint in hints)
    desglose = ", ".join(
        f"{etiqueta}={conteos.get(clave, 0)}" for clave, etiqueta in _MEMORY_KIND_LABELS
    )
    total = len(hints)
    sufijo = "s" if total != 1 else ""
    detalle = f"{total} recuerdo{sufijo} ({desglose})"
    metadata = {
        "resultados": total,
        **{clave: conteos.get(clave, 0) for clave, _ in _MEMORY_KIND_LABELS},
    }
    return detalle, metadata


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
        if nombre == "recall_memory":
            detalle, metadata = _memory_recall_detail(self._collector.memory_hints)
            self._trace.append(TraceStep(stage=stage, detail=detalle, metadata=metadata))
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
