"""Los dos backends de `ports.MemoryPort`:
`adapters.local.fake_memory_store.FakeMemoryStore` (RAM pura, sin AWS) y
`adapters.aws.agentcore_memory_store.AgentCoreMemoryStore` (data plane
`bedrock-agentcore`, ejercitado acá SIEMPRE con un cliente boto3 FALSO —
ningún test de este archivo toca AWS real). El punto central del segundo
bloque es el fail-open: una excepción del cliente nunca debe propagar fuera
de `recall`/`remember_turn`, solo degradar a "sin memoria".
"""

from __future__ import annotations

from typing import Any

from second_brain.adapters.aws.agentcore_memory_store import AgentCoreMemoryStore
from second_brain.adapters.local.fake_memory_store import FakeMemoryStore
from second_brain.ports import MemoryPort

# --- FakeMemoryStore (modo local) -------------------------------------------


def test_fake_memory_store_implements_memory_port() -> None:
    assert isinstance(FakeMemoryStore(), MemoryPort)


def test_fake_memory_store_recalls_seeded_hecho() -> None:
    store = FakeMemoryStore()
    store.seed_hecho("actor-1", "el equipo de Identidad es responsable de auth-cache")

    hints = store.recall("actor-1", "sesion-1", "auth-cache")

    assert len(hints) == 1
    assert hints[0].kind == "hecho"
    assert hints[0].text == "el equipo de Identidad es responsable de auth-cache"
    assert hints[0].namespace == "second_brain/actor-1/hechos"


def test_fake_memory_store_recalls_seeded_preferencia_regardless_of_query() -> None:
    store = FakeMemoryStore()
    store.seed_preferencia("actor-1", "respuestas cortas, en viñetas")

    hints = store.recall("actor-1", "sesion-1", "una query sin relación léxica")

    preferencias = [h for h in hints if h.kind == "preferencia"]
    assert len(preferencias) == 1
    assert "viñetas" in preferencias[0].text
    assert preferencias[0].namespace == "second_brain/actor-1/preferencias"


def test_fake_memory_store_hechos_are_scoped_per_actor() -> None:
    store = FakeMemoryStore()
    store.seed_hecho("actor-1", "hecho de actor 1")
    store.seed_hecho("actor-2", "hecho de actor 2")

    hints_actor_1 = [h for h in store.recall("actor-1", "sesion-1", "hecho") if h.kind == "hecho"]

    assert len(hints_actor_1) == 1
    assert hints_actor_1[0].text == "hecho de actor 1"


def test_fake_memory_store_remembers_turns_within_the_session() -> None:
    store = FakeMemoryStore()
    store.remember_turn("actor-1", "sesion-1", "¿quién lidera el proyecto?", "María Salas.")

    hints = store.recall("actor-1", "sesion-1", "cualquier query")
    turnos = [h for h in hints if h.kind == "turno_stm"]

    assert len(turnos) == 1
    assert "María Salas" in turnos[0].text
    assert turnos[0].namespace is None


def test_fake_memory_store_turns_are_scoped_per_session() -> None:
    store = FakeMemoryStore()
    store.remember_turn("actor-1", "sesion-1", "P", "R")

    hints_otra_sesion = store.recall("actor-1", "sesion-2", "P")
    turnos_otra_sesion = [h for h in hints_otra_sesion if h.kind == "turno_stm"]

    assert turnos_otra_sesion == []


def test_fake_memory_store_does_not_persist_between_instances() -> None:
    """Decisión 10 de `design.md`: sin persistencia a disco, a propósito."""
    store = FakeMemoryStore()
    store.seed_hecho("actor-1", "hecho en ram")

    otro_proceso = FakeMemoryStore()
    hints = [h for h in otro_proceso.recall("actor-1", "sesion-1", "hecho") if h.kind == "hecho"]

    assert hints == []


# --- AgentCoreMemoryStore (modo aws, cliente boto3 falso) -------------------


class _FakeAgentCoreClient:
    """Doble de `boto3.client('bedrock-agentcore')`: registra lo que recibe
    `create_event` y devuelve respuestas fijas (o lanza) para
    `retrieve_memory_records`/`list_events`, según lo que el test configure.
    Ninguna llamada de este archivo sale a la red.
    """

    def __init__(self) -> None:
        self.create_event_calls: list[dict[str, Any]] = []
        self.retrieve_memory_records_calls: list[dict[str, Any]] = []
        self.list_events_calls: list[dict[str, Any]] = []
        self.retrieve_response: dict[str, Any] = {"memoryRecordSummaries": []}
        self.list_events_response: dict[str, Any] = {"events": []}
        self.raise_on: set[str] = set()

    def create_event(self, **kwargs: Any) -> dict[str, Any]:
        if "create_event" in self.raise_on:
            raise RuntimeError("bedrock-agentcore no disponible")
        self.create_event_calls.append(kwargs)
        return {}

    def retrieve_memory_records(self, **kwargs: Any) -> dict[str, Any]:
        self.retrieve_memory_records_calls.append(kwargs)
        if "retrieve_memory_records" in self.raise_on:
            raise RuntimeError("AccessDeniedException")
        return self.retrieve_response

    def list_events(self, **kwargs: Any) -> dict[str, Any]:
        self.list_events_calls.append(kwargs)
        if "list_events" in self.raise_on:
            raise RuntimeError("ThrottlingException")
        return self.list_events_response


def _store_with_fake_client(client: _FakeAgentCoreClient) -> AgentCoreMemoryStore:
    store = AgentCoreMemoryStore(memory_id="mem-fake")
    store._client = client  # type: ignore[assignment]
    return store


def test_agentcore_memory_store_implements_memory_port() -> None:
    assert isinstance(AgentCoreMemoryStore(memory_id="mem-fake"), MemoryPort)


def test_agentcore_recall_reads_ltm_hechos_preferencias_and_stm() -> None:
    client = _FakeAgentCoreClient()
    client.retrieve_response = {
        "memoryRecordSummaries": [{"content": {"text": "hecho recuperado"}, "score": 0.9}]
    }
    client.list_events_response = {
        "events": [
            {
                "payload": [
                    {
                        "conversational": {
                            "content": {"text": "P: algo\nR: otro"},
                            "role": "USER",
                        }
                    }
                ]
            }
        ]
    }
    store = _store_with_fake_client(client)

    hints = store.recall("actor-1", "sesion-1", "auth-cache")

    kinds = [h.kind for h in hints]
    assert kinds.count("hecho") == 1
    assert kinds.count("preferencia") == 1
    assert kinds.count("turno_stm") == 1
    assert len(client.retrieve_memory_records_calls) == 2
    namespaces = {call["namespace"] for call in client.retrieve_memory_records_calls}
    assert namespaces == {"second_brain/actor-1/hechos", "second_brain/actor-1/preferencias"}


def test_agentcore_recall_degrades_to_empty_when_client_raises_everywhere() -> None:
    client = _FakeAgentCoreClient()
    client.raise_on = {"retrieve_memory_records", "list_events"}
    store = _store_with_fake_client(client)

    hints = store.recall("actor-1", "sesion-1", "auth-cache")

    assert hints == []


def test_agentcore_recall_degrades_only_the_failing_source() -> None:
    """Fail-open por FUENTE: si solo STM falla, LTM (hechos/preferencias)
    sigue llegando — una fuente caída no debe tapar a las otras dos.
    """
    client = _FakeAgentCoreClient()
    client.retrieve_response = {
        "memoryRecordSummaries": [{"content": {"text": "hecho recuperado"}}]
    }
    client.raise_on = {"list_events"}
    store = _store_with_fake_client(client)

    hints = store.recall("actor-1", "sesion-1", "auth-cache")

    assert "hecho" in {h.kind for h in hints}
    assert "turno_stm" not in {h.kind for h in hints}


def test_agentcore_remember_turn_calls_create_event_with_expected_shape() -> None:
    client = _FakeAgentCoreClient()
    store = _store_with_fake_client(client)

    store.remember_turn("actor-1", "sesion-1", "¿pregunta?", "respuesta.")

    assert len(client.create_event_calls) == 1
    llamada = client.create_event_calls[0]
    assert llamada["memoryId"] == "mem-fake"
    assert llamada["actorId"] == "actor-1"
    assert llamada["sessionId"] == "sesion-1"
    roles = [bloque["conversational"]["role"] for bloque in llamada["payload"]]
    textos = [bloque["conversational"]["content"]["text"] for bloque in llamada["payload"]]
    assert roles == ["USER", "ASSISTANT"]
    assert textos == ["¿pregunta?", "respuesta."]


def test_agentcore_remember_turn_is_fail_open_on_client_error() -> None:
    client = _FakeAgentCoreClient()
    client.raise_on = {"create_event"}
    store = _store_with_fake_client(client)

    store.remember_turn("actor-1", "sesion-1", "¿pregunta?", "respuesta.")  # no debe lanzar

    assert client.create_event_calls == []
