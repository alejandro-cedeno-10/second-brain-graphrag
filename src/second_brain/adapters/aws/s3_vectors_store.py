"""Vector store real vía S3 Vectors.

Import de `boto3` lazy — ver docstring de `bedrock_embeddings.py`.
"""

from __future__ import annotations

from typing import Any

from second_brain.ports import Chunk, Hit


class S3VectorsStore:
    """Adapter de `VectorStorePort` sobre el cliente `s3vectors`."""

    def __init__(self, bucket: str, index_name: str, region: str = "us-east-1") -> None:
        self._bucket = bucket
        self._index_name = index_name
        self._region = region
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("s3vectors", region_name=self._region)
        return self._client

    def upsert(self, items: list[Chunk]) -> None:
        client = self._get_client()
        vectors = [self._as_vector(item) for item in items]
        client.put_vectors(
            vectorBucketName=self._bucket, indexName=self._index_name, vectors=vectors
        )

    def _as_vector(self, item: Chunk) -> dict[str, Any]:
        metadata = {**item.metadata, "texto": item.text, "documento_id": item.document_id}
        return {"key": item.id, "data": {"float32": item.embedding}, "metadata": metadata}

    def search(
        self, vector: list[float], top_k: int, filter: dict[str, Any] | None = None
    ) -> list[Hit]:
        client = self._get_client()
        arguments: dict[str, Any] = {
            "vectorBucketName": self._bucket,
            "indexName": self._index_name,
            "queryVector": {"float32": vector},
            "topK": top_k,
            "returnMetadata": True,
        }
        if filter:
            arguments["filter"] = filter
        response = client.query_vectors(**arguments)
        return [self._to_hit(resultado) for resultado in response["vectors"]]

    def _to_hit(self, result: dict[str, Any]) -> Hit:
        metadata = dict(result.get("metadata", {}))
        texto = metadata.pop("texto", "")
        return Hit(
            chunk_id=result["key"],
            text=texto,
            score=float(result.get("distance", 0.0)),
            metadata=metadata,
        )
