"""Recuperador gestionado vía Bedrock Knowledge Bases (`bedrock-agent-runtime.Retrieve`).

Import de `boto3` lazy — ver docstring de `bedrock_embeddings.py`.

Esta KB indexa el MISMO corpus que la ingesta propia, pero en su propio
índice de S3 Vectors y con su propio chunking (ver
`infra/stacks/storage_stack.py::_build_kb_vector_index`). Existe para que la
charla pueda comparar, sobre datos reales, un recuperador gestionado contra
el pipeline propio — no para reemplazarlo.

Dos límites medidos contra la cuenta real, que explican por qué la KB entra
como UN ranking más y no como el recuperador único:

- `overrideSearchType=HYBRID` es rechazado cuando el storage es S3 Vectors
  (`ValidationException: HYBRID search type is not supported`). El híbrido
  gestionado exige OpenSearch Serverless. Por eso este adapter no lo pide:
  sobre S3 Vectors la KB es semántica pura, y el BM25 lo sigue poniendo
  `retrieval.search_lexical`.
- La KB indexa TODO lo que haya en el bucket del data source: no puede
  excluir archivos (su `inclusionPrefixes` acepta UN solo prefijo, y el
  corpus tiene nueve categorias en la raiz). Por eso la exclusion pasa ANTES,
  al subir: `infra/subir-corpus.py` aplica la misma regla que
  `ingestion.load_corpus` y deja el `README.md` fuera del bucket.

  No es cosmetico. Medido contra la cuenta real el 03-sep-2026, con ese
  README indexado la pregunta sin respuesta del corpus ("la facturacion del
  Q4 2025") lo recuperaba con score 0.82, superaba
  `gate.RELEVANT_SCORE_THRESHOLD` y el sistema DEJABA DE ABSTENERSE — la
  propiedad que la demo defiende. Alineados los dos caminos de ingesta, el
  gate vuelve a marcar SIN_EVIDENCIA con la KB prendida.

  La leccion que queda para la charla: sumar un recuperador gestionado sobre
  "el mismo" corpus solo es honesto si de verdad es el mismo conjunto de
  documentos. Dos ingestas con contratos distintos no se comparan: una le
  puede costar a la otra su garantia mas fuerte.
"""

from __future__ import annotations

from typing import Any

from second_brain.ports import Hit


class KnowledgeBaseStore:
    """Adapter de `KnowledgeBasePort` sobre `bedrock-agent-runtime.retrieve`."""

    def __init__(self, knowledge_base_id: str, region: str = "us-east-1") -> None:
        self._knowledge_base_id = knowledge_base_id
        self._region = region
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import boto3

            self._client = boto3.client("bedrock-agent-runtime", region_name=self._region)
        return self._client

    def retrieve(self, question: str, top_k: int) -> list[Hit]:
        client = self._get_client()
        response = client.retrieve(
            knowledgeBaseId=self._knowledge_base_id,
            retrievalQuery={"text": question},
            retrievalConfiguration={"vectorSearchConfiguration": {"numberOfResults": top_k}},
        )
        return [self._to_hit(resultado) for resultado in response.get("retrievalResults", [])]

    def _to_hit(self, result: dict[str, Any]) -> Hit:
        """Traduce un resultado de la KB al `Hit` que el resto del pipeline espera.

        `doc_id` se deriva de la URI de S3 relativa al prefijo del corpus para
        que la cita salga igual que la de la ingesta propia
        (`servicios/core-billing.md`), no como una URL de bucket: el formato
        `[source:doc_id]` es un contrato del sintetizador, no un detalle de
        este adapter.
        """
        uri = result.get("location", {}).get("s3Location", {}).get("uri", "")
        return Hit(
            chunk_id=uri,
            text=result.get("content", {}).get("text", ""),
            score=float(result.get("score", 0.0)),
            metadata={"doc_id": _doc_id_from_uri(uri), "origen": "knowledge_base"},
        )


def _doc_id_from_uri(uri: str) -> str:
    sin_esquema = uri.removeprefix("s3://")
    _, _, ruta = sin_esquema.partition("/")
    return ruta or sin_esquema
