"""LLM 100% offline para tests: sin red, sin modelo, respuestas deterministas.

Permite testear el agente completo (coverage gate, guards, regla de
anclaje, orquestación de tools) sin depender de Bedrock ni de la
variabilidad de un modelo real. Soporta simular tool-calls: una `rule` o
un paso de la `sequence` puede devolver un `LlmResponse` con `tool_calls`
poblado, tal como lo haría Nova Pro al decidir llamar `search_documents`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from second_brain.ports import LlmResponse

ScriptedCondition = Callable[[str, list[dict[str, Any]]], bool]


@dataclass
class ScriptedRule:
    """Condición sobre `(system, messages)` que dispara una respuesta fija."""

    when: ScriptedCondition
    response: LlmResponse


class ScriptedLlm:
    """Resuelve `generate` por reglas y, si ninguna aplica, por una secuencia fija.

    Las `rules` se evalúan en orden y ganan la primera que matchee — útil
    para condicionar la respuesta al contenido del prompt (p.ej. "si el
    system prompt tiene la regla de anclaje, responder citando el sujeto").
    La `sequence` cubre el caso de un flujo de varios turnos con el mismo
    LLM (primero decide llamar una tool, después sintetiza la respuesta
    final): cada llamada a `generate` que no matchea ninguna regla consume
    el próximo elemento de la secuencia, en orden.
    """

    def __init__(
        self,
        rules: list[ScriptedRule] | None = None,
        sequence: list[LlmResponse] | None = None,
        default_response: LlmResponse | None = None,
    ) -> None:
        self._rules = rules or []
        self._sequence = list(sequence or [])
        self._sequence_index = 0
        self._default_response = default_response or LlmResponse(text="")

    def generate(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        for rule in self._rules:
            if rule.when(system, messages):
                return rule.response
        if self._sequence_index < len(self._sequence):
            response = self._sequence[self._sequence_index]
            self._sequence_index += 1
            return response
        return self._default_response
