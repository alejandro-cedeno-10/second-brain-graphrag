"""Puente entre `LlmPort` (el puerto propio, agnóstico de proveedor) y
`strands.models.Model` (el proveedor de modelo que un `Agent` de Strands
necesita para correr su loop).

Existe para que el mismo `LlmPort` — `ScriptedLlm` en tests/CLI local,
`BedrockLlm` en modo AWS — sirva TAMBIÉN al loop agéntico, sin que
`agent.strands_agent` tenga que conocer Bedrock ni el SDK de Strands le
tenga que pedir credenciales por su cuenta. Es la misma razón de ser que
`agent.orchestrator` ya tenía para `LlmPort`: un solo seam, ningún `import`
de proveedor en el dominio.

El formato de `Messages`/`ToolSpec` de Strands ya está modelado sobre la
API `bedrock-runtime.converse` (bloques `text`/`toolUse`/`toolResult`,
`toolSpec` con `inputSchema.json`): por eso este puente NO aplana los
mensajes a texto plano, los pasa casi sin tocar — es lo que hace que
`BedrockLlm.generate` (que ya sabe hablar `converse`, ver
`adapters/aws/bedrock_llm.py`) funcione detrás de un `Agent` de Strands sin
un adapter aparte. `ScriptedLlm` en los tests recibe la misma forma, así
que las condiciones de un guion agéntico se escriben contra bloques de
contenido reales, no contra un texto reconstruido a mano.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterable
from typing import Any

from strands.models.model import Model
from strands.types.content import Messages
from strands.types.streaming import StreamEvent
from strands.types.tools import ToolSpec

from second_brain.ports import LlmPort


def _to_tool_config(tool_specs: list[ToolSpec] | None) -> list[dict[str, Any]] | None:
    """Envuelve cada `ToolSpec` de Strands en el `toolSpec` que espera
    `converse` — `BedrockLlm._build_arguments` mete esta lista tal cual en
    `toolConfig.tools`.
    """
    if not tool_specs:
        return None
    return [
        {
            "toolSpec": {
                "name": spec["name"],
                "description": spec.get("description", ""),
                "inputSchema": spec["inputSchema"],
            }
        }
        for spec in tool_specs
    ]


class LlmPortModel(Model):
    """Adapter de `strands.models.Model` sobre cualquier `LlmPort`.

    `call_count` es el contador de invocaciones REALES al modelo — la
    métrica que el punto de diseño delicado de la charla necesita medir
    (ver `agent.gate_hook.CoverageGateHook`): "una llamada de decisión, cero
    de redacción" cuando no hay evidencia, dos llamadas cuando sí la hay.
    Se cuenta acá, en el único punto por el que pasa toda invocación al
    modelo sin importar qué `LlmPort` haya detrás.
    """

    def __init__(self, llm_port: LlmPort) -> None:
        self._llm_port = llm_port
        self._config: dict[str, Any] = {}
        self.call_count = 0

    def update_config(self, **model_config: Any) -> None:
        self._config.update(model_config)

    def get_config(self) -> dict[str, Any]:
        return self._config

    async def structured_output(
        self, output_model: type, prompt: Messages, system_prompt: str | None = None, **kwargs: Any
    ) -> AsyncIterable[dict[str, Any]]:
        raise NotImplementedError(
            "LlmPortModel no soporta structured_output: el loop agéntico de la "
            "demo solo necesita tool calling + texto libre citado."
        )

    async def stream(
        self,
        messages: Messages,
        tool_specs: list[ToolSpec] | None = None,
        system_prompt: str | None = None,
        **kwargs: Any,
    ) -> AsyncIterable[StreamEvent]:
        self.call_count += 1
        respuesta = self._llm_port.generate(
            system=system_prompt or "",
            messages=list(messages),
            tools=_to_tool_config(tool_specs),
        )
        yield {"messageStart": {"role": "assistant"}}
        if respuesta.tool_calls:
            for llamada in respuesta.tool_calls:
                tool_use_id = llamada.id or str(uuid.uuid4())
                yield {
                    "contentBlockStart": {
                        "start": {"toolUse": {"name": llamada.name, "toolUseId": tool_use_id}}
                    }
                }
                yield {
                    "contentBlockDelta": {
                        "delta": {"toolUse": {"input": json.dumps(llamada.arguments)}}
                    }
                }
                yield {"contentBlockStop": {}}
            yield {"messageStop": {"stopReason": "tool_use"}}
            return
        if respuesta.text:
            yield {"contentBlockStart": {"start": {}}}
            yield {"contentBlockDelta": {"delta": {"text": respuesta.text}}}
            yield {"contentBlockStop": {}}
        yield {"messageStop": {"stopReason": "end_turn"}}
