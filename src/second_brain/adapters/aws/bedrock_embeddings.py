"""Embeddings reales vía Bedrock (Cohere Embed Multilingual v3).

El import de `boto3` es lazy (dentro de `_get_client`) a propósito:
así este módulo se puede importar libremente en modo local, y el cliente
solo se crea (y solo entonces hace falta `boto3` instalado y credenciales
válidas) la primera vez que se llama a `embed`.
"""

from __future__ import annotations

import json
from typing import Any

_MAX_TEXT_CHARS = 2048
"""El esquema de Bedrock para Cohere Embed v3 RECHAZA (ValidationException,
"expected maxLength: 2048") cualquier texto de entrada que supere los 2048
caracteres — no lo trunca por su cuenta, ni siquiera pasando `truncate`.
Encontrado ingiriendo el corpus real: el chunker corta por ~512 PALABRAS,
que en español superan los 3000 caracteres en párrafos densos. Truncar acá
es correcto para retrieval: el modelo igual solo mira sus primeros 512
tokens, así que lo que se pierde no participaba del embedding de todas
formas. El texto completo del chunk viaja intacto en la metadata del
vector — solo el vector se calcula sobre el prefijo."""


class BedrockEmbeddings:
    """Adapter de `EmbeddingsPort` sobre `bedrock-runtime.invoke_model`."""

    def __init__(
        self,
        model_id: str = "cohere.embed-multilingual-v3",
        region: str = "us-east-1",
        dim: int = 1024,
    ) -> None:
        self._model_id = model_id
        self._region = region
        self.dim = dim
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-runtime", region_name=self._region)
        return self._client

    def embed(self, texts: list[str]) -> list[list[float]]:
        if self._model_id.startswith("amazon.nova"):
            return [self._embed_nova(text) for text in texts]
        return self._embed_cohere(texts)

    def _embed_cohere(self, texts: list[str]) -> list[list[float]]:
        client = self._get_client()
        bounded = [text[:_MAX_TEXT_CHARS] for text in texts]
        body = json.dumps({"texts": bounded, "input_type": "search_document"})
        response = client.invoke_model(modelId=self._model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["embeddings"]

    def _embed_nova(self, text: str) -> list[float]:
        """Nova 2 Multimodal Embeddings habla otro esquema que Cohere: un texto
        por invocación (`SINGLE_EMBEDDING`), `embeddingDimension` explícita
        (256/384/1024/3072 — acá viaja `self.dim`, que debe coincidir con la
        dimensión del índice de S3 Vectors), y truncado propio
        (`truncationMode: END`, contexto de 8K tokens) — por eso este camino
        no aplica el recorte de 2048 caracteres que exige el esquema de
        Cohere. `GENERIC_INDEX` es el propósito para indexar; el mismo valor
        sirve para la consulta porque el adapter no distingue quién embebe.
        """
        client = self._get_client()
        body = json.dumps(
            {
                "taskType": "SINGLE_EMBEDDING",
                "singleEmbeddingParams": {
                    "embeddingPurpose": "GENERIC_INDEX",
                    "embeddingDimension": self.dim,
                    "text": {"truncationMode": "END", "value": text},
                },
            }
        )
        response = client.invoke_model(modelId=self._model_id, body=body)
        payload = json.loads(response["body"].read())
        return payload["embeddings"][0]["embedding"]
