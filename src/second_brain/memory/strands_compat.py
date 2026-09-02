"""Adapter para enganchar un `MemoryPort` a `strands.memory.memory_manager.MemoryManager`.

Verificado por introspección real contra `strands-agents==1.54.0`
(`strands/memory/types.py`): `MemoryStore` es un `Protocol` ASYNC donde
solo `search` es obligatorio (`add`/`add_messages`/`initialize`/
`get_tools` son opcionales y se detectan mirando la CLASE, no la
instancia — heredar el stub del `Protocol` no cuenta como implementarlo),
más cuatro atributos declarativos (`name`, `description`,
`max_search_results`, `writable`, `extraction`).

Esta clase es un ADAPTER, no una reimplementación: envuelve un
`MemoryPort` (síncrono, con la forma propia del dominio — ver
`second_brain.ports`) para que cumpla esa forma, sin que `MemoryPort`
tenga que conocer nada de Strands. Existe para dejar probada la
compatibilidad que pide la fase base del proyecto; el camino agéntico
real de la demo NO la usa hoy (usa `recall_memory` como tool explícita
interceptable en vez de `MemoryManager(injection=True)` — ver
`agent.strands_tools`), así que esta clase no tiene llamador en el resto
del paquete todavía.
"""

from __future__ import annotations

import asyncio

from strands.memory.extraction.types import ExtractionConfig
from strands.memory.types import MemoryEntry, SearchOptions

from second_brain.ports import MemoryPort

_DEFAULT_MAX_SEARCH_RESULTS = 5


class MemoryPortStrandsAdapter:
    """Envuelve un `MemoryPort` para cumplir `strands.memory.types.MemoryStore`.

    `actor_id`/`session_id` quedan fijos por instancia (a diferencia de
    `MemoryPort.recall`, que los recibe por llamada) porque
    `MemoryManager.search` no tiene forma de pasarlos por invocación: los
    conoce el turno del agente, no el store.

    `add` NO se implementa a propósito: `MemoryPort.remember_turn` pide
    una pregunta Y una respuesta (un turno completo), mientras que el
    `add(content, metadata)` de Strands solo ofrece un string suelto —
    mapear uno al otro forzaría rellenar una pregunta o respuesta vacía
    sin sentido semántico. Sin `add`, la instancia queda de solo lectura
    (`writable = False`), que es exactamente lo que corresponde: memoria
    es pista para LEER, la escritura real del turno pasa por
    `agent.memory.remember_turn_fail_open`, no por `MemoryManager`.
    """

    def __init__(
        self,
        port: MemoryPort,
        *,
        name: str,
        actor_id: str,
        session_id: str = "",
        description: str | None = None,
        max_search_results: int | None = None,
    ) -> None:
        self._port = port
        self._actor_id = actor_id
        self._session_id = session_id
        self.name = name
        self.description = description
        self.max_search_results = max_search_results
        self.writable = False
        self.extraction: ExtractionConfig | bool | None = None

    async def search(self, query: str, options: SearchOptions | None = None) -> list[MemoryEntry]:
        """Delega en `MemoryPort.recall`, corrido en un hilo aparte.

        `MemoryPort.recall` es síncrono (puede ser una llamada de red real
        contra AgentCore); correrlo directo bloquearía el loop de eventos
        de Strands, así que se despacha vía `asyncio.to_thread`.
        """
        max_resultados = (
            (options or {}).get("max_search_results")
            or self.max_search_results
            or _DEFAULT_MAX_SEARCH_RESULTS
        )
        pistas = await asyncio.to_thread(
            self._port.recall, self._actor_id, self._session_id, query
        )
        return [
            MemoryEntry(
                content=pista.text,
                metadata={"kind": pista.kind, "namespace": pista.namespace, "score": pista.score},
            )
            for pista in pistas[:max_resultados]
        ]
