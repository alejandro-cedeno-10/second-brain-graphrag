"""Store real de memoria sobre AgentCore Memory (data plane `bedrock-agentcore`).

Nombres de operación y forma de parámetros verificados por INTROSPECCIÓN
REAL contra `boto3` instalado (`boto3.client("bedrock-agentcore",
region_name=...).meta.service_model`), no contra documentación ni memoria
del modelo:

- `CreateEvent(memoryId, actorId, sessionId, eventTimestamp, payload=[...])`
  escribe un turno en STM. Cada elemento de `payload` es
  `{"conversational": {"content": {"text": ...}, "role": "USER"|"ASSISTANT"}}`
  (`role` es un enum: `ASSISTANT`/`USER`/`TOOL`/`OTHER`).
- `RetrieveMemoryRecords(memoryId, namespace, searchCriteria={"searchQuery",
  "topK", ...})` lee LTM (hechos/preferencias) por namespace.
- `ListEvents(memoryId, sessionId, actorId, includePayloads, maxResults)`
  lee la ventana de STM de una sesión.

El recurso ya desplegado (`second_brain_memory`, ver
`infra/stacks/agentcore_stack.py`) declara dos `ManagedMemoryStrategy`:
SEMANTIC en el namespace `second_brain/{actor_id}/hechos` y
USER_PREFERENCE en `second_brain/{actor_id}/preferencias`. STM se lee vía
`ListEvents`, sin estrategia administrada de por medio.

Import de `boto3` lazy (mismo patrón que el resto de `adapters/aws`): este
módulo se importa libremente incluso sin `boto3` instalado o sin
credenciales, y el cliente solo se crea la primera vez que hace falta.

Fail-open a propósito (invariante de la charla: la memoria nunca puede
tumbar un turno): cualquier excepción al hablar con AgentCore se loguea y
`recall`/`remember_turn` degradan a "sin memoria" en vez de propagar.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from second_brain.ports import MemoryHint

_LOGGER = logging.getLogger(__name__)

_SUBNAMESPACE_HECHOS = "hechos"
_SUBNAMESPACE_PREFERENCIAS = "preferencias"
_TOP_K_LTM = 5
_MAX_TURNOS_STM = 6


class AgentCoreMemoryStore:
    """`MemoryPort` sobre `bedrock-agentcore` (data plane), fail-open.

    `memory_id` es el id del recurso AgentCore Memory ya desplegado — se
    recibe por parámetro, NUNCA hardcodeado acá (es específico de cuenta);
    lo resuelve `config.Settings` desde `SECOND_BRAIN_AGENTCORE_MEMORY_ID`.
    El cliente boto3 se inyecta seteando `._client` directamente (mismo
    patrón que `adapters.aws.bedrock_llm.BedrockLlm` y sus hermanos): sin
    parámetro de constructor dedicado, los tests reemplazan el atributo
    antes de llamar a `recall`/`remember_turn`.
    """

    def __init__(self, memory_id: str, region: str = "us-east-1") -> None:
        self._memory_id = memory_id
        self._region = region
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-agentcore", region_name=self._region)
        return self._client

    def recall(self, actor_id: str, session_id: str, query: str) -> list[MemoryHint]:
        return [
            *self._recall_ltm(actor_id, query, _SUBNAMESPACE_HECHOS, "hecho"),
            *self._recall_ltm(actor_id, query, _SUBNAMESPACE_PREFERENCIAS, "preferencia"),
            *self._recall_stm(actor_id, session_id),
        ]

    def remember_turn(
        self, actor_id: str, session_id: str, question: str, answer_text: str
    ) -> None:
        client = self._get_client()
        try:
            client.create_event(
                memoryId=self._memory_id,
                actorId=actor_id,
                sessionId=session_id,
                eventTimestamp=datetime.now(UTC),
                payload=[
                    {"conversational": {"content": {"text": question}, "role": "USER"}},
                    {
                        "conversational": {
                            "content": {"text": answer_text},
                            "role": "ASSISTANT",
                        }
                    },
                ],
            )
        except Exception as error:
            _LOGGER.warning(
                "AgentCoreMemoryStore.remember_turn: fallo guardando turno "
                "(actor=%r, sesión=%r): %s",
                actor_id,
                session_id,
                error,
            )

    def _recall_ltm(
        self, actor_id: str, query: str, subnamespace: str, kind: str
    ) -> list[MemoryHint]:
        namespace = self._namespace(actor_id, subnamespace)
        client = self._get_client()
        try:
            respuesta = client.retrieve_memory_records(
                memoryId=self._memory_id,
                namespace=namespace,
                searchCriteria={"searchQuery": query, "topK": _TOP_K_LTM},
            )
        except Exception as error:
            _LOGGER.warning(
                "AgentCoreMemoryStore.recall: fallo leyendo LTM (namespace=%r): %s",
                namespace,
                error,
            )
            return []
        return [
            MemoryHint(
                text=resumen["content"]["text"],
                kind=kind,
                namespace=namespace,
                score=resumen.get("score"),
            )
            for resumen in respuesta.get("memoryRecordSummaries", [])
            if resumen.get("content", {}).get("text")
        ]

    def _recall_stm(self, actor_id: str, session_id: str) -> list[MemoryHint]:
        client = self._get_client()
        try:
            respuesta = client.list_events(
                memoryId=self._memory_id,
                sessionId=session_id,
                actorId=actor_id,
                includePayloads=True,
                maxResults=_MAX_TURNOS_STM,
            )
        except Exception as error:
            _LOGGER.warning(
                "AgentCoreMemoryStore.recall: fallo leyendo STM (actor=%r, sesión=%r): %s",
                actor_id,
                session_id,
                error,
            )
            return []
        return [
            MemoryHint(text=texto, kind="turno_stm", namespace=None, score=None)
            for evento in respuesta.get("events", [])
            for texto in self._textos_del_evento(evento)
        ]

    @staticmethod
    def _textos_del_evento(evento: dict[str, Any]) -> list[str]:
        return [
            bloque["conversational"]["content"]["text"]
            for bloque in evento.get("payload", [])
            if bloque.get("conversational", {}).get("content", {}).get("text")
        ]

    @staticmethod
    def _namespace(actor_id: str, subnamespace: str) -> str:
        return f"second_brain/{actor_id}/{subnamespace}"
