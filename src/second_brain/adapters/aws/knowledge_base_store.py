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
- La KB indexa TODO el prefijo del bucket, incluido el `README.md` que
  `ingestion.load_corpus` excluye por ser contrato de diseño para humanos.

RIESGO MEDIDO (03-sep-2026, contra la cuenta real): ese `README.md` le CUESTA
la abstención al sistema. Para "¿Cuál fue la facturación del Q4 2025?" —la
pregunta sin respuesta en el corpus— con la KB apagada el mejor score es 0.35
y el gate marca SIN_EVIDENCIA; con la KB prendida el README puntúa 0.82,
supera `gate.RELEVANT_SCORE_THRESHOLD` y el gate pasa a SUFICIENTE. El
documento no contiene ni un dato de Q4: lo único que hace es hablar de
servicios de facturación.

Por eso la KB es OPT-IN y viene apagada, y este adapter NO filtra el README a
mano: esconderlo taparía justamente la lección —sumar un recuperador
gestionado sobre el mismo corpus puede costar la propiedad que la charla
defiende—. Ver `tests/test_knowledge_base.py` para el test que lo fija.
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
