"""Rerank real vía Bedrock (Cohere Rerank 3.5).

Import de `boto3` lazy — ver docstring de `bedrock_embeddings.py`.
"""

from __future__ import annotations

from typing import Any

from second_brain.ports import ScoredDoc

_RERANK_MODEL_ARN = "cohere.rerank-v3-5:0"


class BedrockRerank:
    """Adapter de `RerankPort` sobre `bedrock-agent-runtime.rerank`."""

    def __init__(self, region: str = "us-east-1", model_id: str = _RERANK_MODEL_ARN) -> None:
        self._region = region
        self._model_id = model_id
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-agent-runtime", region_name=self._region)
        return self._client

    def rerank(self, question: str, documents: list[str], top_n: int) -> list[ScoredDoc]:
        client = self._get_client()
        model_arn = f"arn:aws:bedrock:{self._region}::foundation-model/{self._model_id}"
        response = client.rerank(
            queries=[{"type": "TEXT", "textQuery": {"text": question}}],
            sources=[self._as_source(doc) for doc in documents],
            rerankingConfiguration={
                "type": "BEDROCK_RERANKING_MODEL",
                "bedrockRerankingConfiguration": {
                    "modelConfiguration": {"modelArn": model_arn},
                    "numberOfResults": top_n,
                },
            },
        )
        return [
            ScoredDoc(
                text=documents[resultado["index"]],
                score=resultado["relevanceScore"],
            )
            for resultado in response["results"]
        ]

    def _as_source(self, document: str) -> dict[str, Any]:
        return {
            "type": "INLINE",
            "inlineDocumentSource": {"type": "TEXT", "textDocument": {"text": document}},
        }
