"""`MemoryPortStrandsAdapter` cumple de verdad `strands.memory.types.MemoryStore`.

El protocolo de Strands no es `runtime_checkable`, así que la compatibilidad
se prueba donde importa: construyendo un `MemoryManager` real con el adapter
(el constructor valida la forma del store) y ejercitando `search`.
"""

from __future__ import annotations

import asyncio

from strands.memory.memory_manager import MemoryManager
from strands.memory.types import MemoryEntry

from second_brain.adapters.local.fake_memory_store import FakeMemoryStore
from second_brain.memory.strands_compat import MemoryPortStrandsAdapter

ACTOR = "presentador"
SESION = "sesion-charla"


def _adapter(port: FakeMemoryStore, **kwargs: object) -> MemoryPortStrandsAdapter:
    return MemoryPortStrandsAdapter(
        port, name="second-brain", actor_id=ACTOR, session_id=SESION, **kwargs
    )


def test_memory_manager_acepta_el_adapter() -> None:
    manager = MemoryManager(stores=[_adapter(FakeMemoryStore())])

    assert manager is not None


def test_search_devuelve_memory_entries_con_el_origen_del_recuerdo() -> None:
    port = FakeMemoryStore()
    port.seed_hecho(ACTOR, "core-billing depende de auth-cache", namespace="second_brain/hechos")

    entradas = asyncio.run(_adapter(port).search("¿de qué depende core-billing?"))

    assert entradas
    assert all(isinstance(entrada, MemoryEntry) for entrada in entradas)
    assert entradas[0].metadata["kind"] == "hecho"
    assert entradas[0].metadata["namespace"] == "second_brain/hechos"


def test_search_respeta_el_tope_de_resultados() -> None:
    port = FakeMemoryStore()
    for indice in range(4):
        port.seed_hecho(ACTOR, f"core-billing nota {indice}")

    entradas = asyncio.run(_adapter(port, max_search_results=2).search("core-billing"))

    assert len(entradas) <= 2


def test_el_adapter_es_de_solo_lectura() -> None:
    adapter = _adapter(FakeMemoryStore())

    assert adapter.writable is False
    assert not hasattr(adapter, "add")
