"""`BedrockLlm`: la forma de los argumentos que se le manda a Converse.

No invoca Bedrock: sustituye el cliente por un doble y verifica el payload.
El caso central es el acoplamiento entre `guardContent` y `guardrailConfig`,
que rompía el modo `aws` sin guardrail configurado.
"""

from __future__ import annotations

from typing import Any

from second_brain.adapters.aws.bedrock_llm import BedrockLlm

_RESPUESTA_OK: dict[str, Any] = {
    "output": {"message": {"content": [{"text": "respuesta"}]}},
    "stopReason": "end_turn",
}


class _ClienteFalso:
    def __init__(self) -> None:
        self.llamadas: list[dict[str, Any]] = []

    def converse(self, **kwargs: Any) -> dict[str, Any]:
        self.llamadas.append(kwargs)
        return _RESPUESTA_OK


def _llm(cliente: _ClienteFalso, **kwargs: Any) -> BedrockLlm:
    llm = BedrockLlm(**kwargs)
    llm._client = cliente
    return llm


def _mensaje_con_grounding() -> list[dict[str, Any]]:
    """Un mensaje como el que arma la síntesis: texto + grounding + pregunta."""
    return [
        {
            "role": "user",
            "content": "Evidencia y pregunta",
            "grounding_source": "core-billing es consumido por pagos",
            "query": "¿qué se rompe si modifico core-billing?",
        }
    ]


def _bloques(cliente: _ClienteFalso) -> list[dict[str, Any]]:
    return cliente.llamadas[0]["messages"][0]["content"]


def test_sin_guardrail_no_manda_guardcontent() -> None:
    """`guardContent` sin `guardrailConfig` es un error DURO de Converse.

    Bedrock responde `ValidationException: The guardrail can't assess the
    content in the guardContent field. The guardrail configuration is
    missing.` Como `guardrail_id` es `None` por default, emitirlo igual
    rompía toda síntesis en modo `aws` sin guardrail — el camino principal.
    """
    cliente = _ClienteFalso()
    llm = _llm(cliente)

    llm.generate(system="s", messages=_mensaje_con_grounding())

    bloques = _bloques(cliente)
    assert bloques == [{"text": "Evidencia y pregunta"}]
    assert "guardrailConfig" not in cliente.llamadas[0]


def test_con_guardrail_manda_guardcontent_y_la_config_juntos() -> None:
    """Los dos van SIEMPRE de la mano: uno sin el otro es un turno inválido."""
    cliente = _ClienteFalso()
    llm = _llm(cliente, guardrail_id="gr-123", guardrail_version="1")

    llm.generate(system="s", messages=_mensaje_con_grounding())

    argumentos = cliente.llamadas[0]
    assert argumentos["guardrailConfig"]["guardrailIdentifier"] == "gr-123"
    qualifiers = [
        bloque["guardContent"]["text"]["qualifiers"]
        for bloque in _bloques(cliente)
        if "guardContent" in bloque
    ]
    assert qualifiers == [["grounding_source"], ["query"]]


def test_normaliza_content_string_a_lista_de_bloques() -> None:
    """Converse exige `content` como lista; `LlmPort` acepta el string plano."""
    cliente = _ClienteFalso()
    llm = _llm(cliente)

    llm.generate(system="s", messages=[{"role": "user", "content": "hola"}])

    assert _bloques(cliente) == [{"text": "hola"}]


def test_un_content_que_ya_es_lista_se_respeta() -> None:
    cliente = _ClienteFalso()
    llm = _llm(cliente)
    bloques_originales = [{"text": "ya normalizado"}]

    llm.generate(system="s", messages=[{"role": "user", "content": bloques_originales}])

    assert _bloques(cliente) == bloques_originales
