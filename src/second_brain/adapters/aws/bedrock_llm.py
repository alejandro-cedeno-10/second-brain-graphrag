"""LLM real vía Bedrock (Nova Pro, Converse API), con Guardrails opcionales.

Import de `boto3` lazy — ver docstring de `bedrock_embeddings.py`.
"""

from __future__ import annotations

from typing import Any

from second_brain.ports import LlmResponse, ToolCall


class BedrockLlm:
    """Adapter de `LlmPort` sobre `bedrock-runtime.converse`.

    `guardrail_id` es opcional a propósito: en ensayo sin AWS no aplica
    (se usa `ScriptedLlm`), y el día de la charla se enciende pasando el
    id y la versión del guardrail configurado en Bedrock. `guardrail_trace`
    queda en `"enabled"` por defecto porque el trace del guardrail es parte
    de lo que se muestra en pantalla (`--trace`).
    """

    def __init__(
        self,
        model_id: str = "amazon.nova-micro-v1:0",
        region: str = "us-east-1",
        guardrail_id: str | None = None,
        guardrail_version: str | None = None,
        guardrail_trace: str = "enabled",
    ) -> None:
        self._model_id = model_id
        self._region = region
        self._guardrail_id = guardrail_id
        self._guardrail_version = guardrail_version
        self._guardrail_trace = guardrail_trace
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self._region)
        return self._client

    def generate(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse:
        client = self._get_client()
        arguments = self._build_arguments(system, messages, tools)
        response = client.converse(**arguments)
        return self._to_llm_response(response)

    def _build_arguments(
        self, system: str, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "modelId": self._model_id,
            "system": [{"text": system}],
            "messages": [self._to_converse_message(message) for message in messages],
        }
        if tools:
            arguments["toolConfig"] = {"tools": tools}
        if self._guardrail_id:
            arguments["guardrailConfig"] = {
                "guardrailIdentifier": self._guardrail_id,
                "guardrailVersion": self._guardrail_version,
                "trace": self._guardrail_trace,
            }
        return arguments

    def _to_converse_message(self, message: dict[str, Any]) -> dict[str, Any]:
        """Normaliza al contrato de la API Converse, que exige `content` como
        LISTA de bloques (`[{"text": ...}]`) y rechaza un string plano con
        `ParamValidationError`. El contrato interno de `LlmPort` acepta el
        string directo (así lo usan la síntesis y los tests con `ScriptedLlm`,
        que nunca validan la forma), por eso la adaptación vive acá y no en
        cada call site — encontrado recién al invocar Bedrock real.

        Los bloques `guardContent` (contextual grounding) SOLO se emiten si
        hay un guardrail configurado. Sin esa condición, Converse rechaza el
        turno entero:

            ValidationException: The guardrail can't assess the content in
            the guardContent field. The guardrail configuration is missing.

        Es decir: `guardContent` sin `guardrailConfig` no es "una pista que
        Bedrock ignora", es un error duro. Y como `guardrail_id` es `None` por
        default, cualquier corrida en modo `aws` sin
        `SECOND_BRAIN_BEDROCK_GUARDRAIL_ID` fallaba en TODA síntesis que
        pasara `grounding_source`+`query` — o sea, el camino principal.
        Encontrado corriendo la UI contra Bedrock real sin guardrail.
        """
        content = message.get("content")
        if not isinstance(content, str):
            return message
        blocks: list[dict[str, Any]] = [{"text": content}]
        grounding_source = message.get("grounding_source")
        query = message.get("query")
        if grounding_source and query and self._guardrail_id:
            blocks.append(
                {
                    "guardContent": {
                        "text": {
                            "text": grounding_source,
                            "qualifiers": ["grounding_source"],
                        }
                    }
                }
            )
            blocks.append(
                {"guardContent": {"text": {"text": query, "qualifiers": ["query"]}}}
            )
        clean = {k: v for k, v in message.items() if k in ("role",)}
        return {**clean, "content": blocks}

    @staticmethod
    def _extract_guardrail_scores(response: dict[str, Any]) -> dict[str, float] | None:
        """Rescata los puntajes de contextual grounding del trace del guardrail.

        Con `trace: enabled`, Bedrock adjunta en `response["trace"]` la
        evaluación del guardrail; sin extraerlos acá, la capa 11 corre y paga
        pero su salida no se ve — exactamente el hueco que este método cierra.
        Fail-open: cualquier forma inesperada devuelve `None`, nunca rompe el
        turno (misma política que los guards).
        """
        try:
            assessments = response["trace"]["guardrail"]["outputAssessments"]
            scores: dict[str, float] = {}
            for lista in assessments.values():
                for assessment in lista:
                    grounding = assessment.get("contextualGroundingPolicy", {})
                    for filtro in grounding.get("filters", []):
                        scores[filtro["type"].lower()] = float(filtro["score"])
            return scores or None
        except Exception:
            return None

    def _to_llm_response(self, response: dict[str, Any]) -> LlmResponse:
        bloques = response["output"]["message"]["content"]
        texto = "".join(bloque["text"] for bloque in bloques if "text" in bloque)
        tool_calls = [
            ToolCall(
                name=bloque["toolUse"]["name"],
                arguments=bloque["toolUse"]["input"],
                id=bloque["toolUse"]["toolUseId"],
            )
            for bloque in bloques
            if "toolUse" in bloque
        ]
        usage = response.get("usage")
        return LlmResponse(
            text=texto,
            tool_calls=tool_calls,
            stop_reason=response.get("stopReason", "fin"),
            token_usage=dict(usage) if usage else None,
            guardrail_scores=self._extract_guardrail_scores(response),
        )
