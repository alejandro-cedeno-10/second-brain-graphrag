"""La lista de `TraceStep` observable: la comparten `agent.orchestrator`
(pipeline fijo) y `agent.strands_agent` (loop agéntico) para que un
consumidor externo (la UI web, vía SSE) reciba progreso incremental sin que
ninguno de los dos caminos deje de devolver la traza completa al final.
"""

from __future__ import annotations

from collections.abc import Callable

from second_brain.ports import TraceStep


class ObservableTrace(list):
    """Lista de `TraceStep` que además notifica cada `append` a un callback.

    Cada sitio del pipeline que hace `traza.append(...)` sigue siendo una
    lista común; el hook se agrega una sola vez acá, en la construcción.
    """

    def __init__(self, on_paso: Callable[[TraceStep], None] | None = None) -> None:
        super().__init__()
        self._on_paso = on_paso

    def append(self, paso: TraceStep) -> None:
        super().append(paso)
        if self._on_paso is not None:
            self._on_paso(paso)
