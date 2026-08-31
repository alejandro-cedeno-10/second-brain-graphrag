"""El "agente de soporte": el SEGUNDO agente de la demo de cierre.

No sabe nada de la arquitectura de Nexora ni de `second_brain.agent.*` —
lo único que conoce es un endpoint HTTP y el protocolo A2A. Descubre al
second brain por su Agent Card (`discover`) y le pregunta (`ask`), en dos
PROCESOS separados (este módulo corre en el suyo, `second_brain.a2a.server`
en el otro) — es la demostración en vivo de que MCP y A2A son cosas
distintas: acá no hay ninguna tool que invocar, hay un agente completo al
que se le habla.

## Por qué no se usa `A2AAgent.__call__`/`invoke_async`

`strands.agent.a2a_agent.A2AAgent` (el cliente A2A del SDK de Strands) trae
un conversor de conveniencia, `convert_response_to_agent_result`, que solo
extrae `TextPart` de la respuesta final — cualquier `DataPart` (donde
`second_brain.a2a.server` manda las citas ESTRUCTURADAS, ver su docstring)
se descarta en silencio. Usar ese atajo acá haría que las citas se
"pierdan" en el cliente, no en el servidor — exactamente lo que este
archivo existe para demostrar que NO pasa. Por eso `ask` usa
`A2AAgent.stream_async` (eventos A2A crudos, sin ese conversor) y lee el
`DataPart` del artifact final a mano.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from a2a.types import AgentCard, DataPart, TaskArtifactUpdateEvent, TaskStatusUpdateEvent, TextPart
from strands.agent.a2a_agent import A2AAgent

SUPPORT_AGENT_INTRO = (
    "Soy el agente de soporte de Nexora: no conozco su arquitectura "
    "interna. Voy a descubrir al second brain por su Agent Card y "
    "preguntarle por A2A."
)


@dataclass
class SupportAgentAnswer:
    """Lo que el agente de soporte recibió del second brain, ya separado en
    prosa y citas ESTRUCTURADAS (no re-parseadas del texto) — ver el
    docstring del módulo para por qué importa la distinción.
    """

    text: str
    citations: list[dict[str, object]] = field(default_factory=list)
    abstained: bool = False


async def discover(endpoint: str) -> AgentCard:
    """Descubre la Agent Card del second brain: nombre, descripción,
    skills — todo lo que el agente de soporte necesita saber ANTES de
    preguntarle nada, sin haber leído una línea de `second_brain.agent.*`.
    """
    return await A2AAgent(endpoint).get_agent_card()


async def ask(
    endpoint: str,
    question: str,
    *,
    on_progress: Callable[[str], None] | None = None,
) -> SupportAgentAnswer:
    """Pregunta al second brain por A2A y devuelve la respuesta con sus citas.

    `on_progress` recibe cada actualización de estado A2A a medida que
    llega (el streaming de progreso del servidor, ver
    `second_brain.a2a.server.SecondBrainA2AExecutor._run_with_progress`) —
    nunca tokens crudos del LLM, siempre una línea de traza ya resuelta.
    """
    agent = A2AAgent(endpoint)
    text = ""
    citations: list[dict[str, object]] = []
    abstained = False

    async for wrapped in agent.stream_async(question):
        event = wrapped.get("event") if isinstance(wrapped, dict) else None
        if not (isinstance(event, tuple) and len(event) == 2):
            continue
        _task, update = event

        if isinstance(update, TaskStatusUpdateEvent) and update.status and update.status.message:
            for part in update.status.message.parts:
                if isinstance(part.root, TextPart) and on_progress:
                    on_progress(part.root.text)

        elif isinstance(update, TaskArtifactUpdateEvent) and update.artifact:
            for part in update.artifact.parts:
                if isinstance(part.root, TextPart):
                    text += part.root.text
                elif isinstance(part.root, DataPart):
                    data = part.root.data
                    citations = data.get("citations", citations)
                    abstained = bool(data.get("abstained", abstained))

    return SupportAgentAnswer(text=text, citations=citations, abstained=abstained)
