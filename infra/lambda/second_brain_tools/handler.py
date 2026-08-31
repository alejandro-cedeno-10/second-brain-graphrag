"""Lambda target del AgentCore Gateway: expone `buscar_documentos` y
`navegar_grafo` como herramientas MCP sin reescribir la lógica del dominio.

Stub deliberado: el Gateway invoca esta función con el nombre de la tool en
`event["toolName"]` según el contrato de targets Lambda de
`bedrock-agentcore-control` (`SPIKE_COMPATIBILIDAD.md` §5, "CreateGatewayTarget
... targetConfiguration.mcp ... lambda"). La implementación real (llamar a
`second_brain.agente.herramientas`) es tarea de la Fase 6 del
`PLAN_SERVICIOS_REALES.md`, no de este spike de infraestructura — acá solo se
declara el recurso y el contrato de entrada/salida para que `cdk synth`
tenga algo real que empaquetar.
"""

from __future__ import annotations

from typing import Any

TOOL_NAMES = ("buscar_documentos", "navegar_grafo")


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    tool_name = event.get("toolName", "")
    if tool_name not in TOOL_NAMES:
        return {"error": f"herramienta desconocida: {tool_name}"}
    return {
        "error": f"'{tool_name}' aún no está conectada al dominio real "
        "(second_brain.agente.herramientas) — pendiente de Fase 6."
    }
