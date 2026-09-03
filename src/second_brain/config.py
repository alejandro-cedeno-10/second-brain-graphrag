"""Resuelve QUÉ adapters usar, según una única variable: `SECOND_BRAIN_MODE`.

Este módulo es la bisagra de todo el argumento de la charla: el mismo
`Stack` (mismos puertos, mismo código de dominio) se arma con adapters
locales o con adapters de AWS según configuración, nunca según una rama de
código distinta. `build_stack` es la única función que conoce ambos mundos;
todo lo demás en el paquete solo conoce `second_brain.ports`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from second_brain.ports import (
    EmbeddingsPort,
    GraphStorePort,
    KnowledgeBasePort,
    LlmPort,
    RerankPort,
    VectorStorePort,
)

if TYPE_CHECKING:
    # `MemoryPort` es del change `agregar-memoria-second-brain` (ver
    # openspec/), cableado por otro workstream: bajo `TYPE_CHECKING` este
    # import nunca corre en runtime (con `from __future__ import annotations`
    # activo, la anotación de `Stack.memory` es un string, no un símbolo
    # resuelto), así que `Stack`/`Settings` no dependen de que `ports.py` ya
    # lo defina para seguir importando hoy.
    from second_brain.ports import MemoryPort

_PREFIX = "SECOND_BRAIN_"


def _env(name: str, default: str | None = None) -> str | None:
    return os.environ.get(f"{_PREFIX}{name}", default)


def _env_int(name: str, default: int) -> int:
    valor = _env(name)
    return int(valor) if valor is not None else default


def _env_bool(name: str, default: bool) -> bool:
    valor = _env(name)
    return valor.strip().lower() == "true" if valor is not None else default


@dataclass(frozen=True)
class Settings:
    """Configuración completa del stack, resuelta desde variables de entorno.

    Todas las variables llevan el prefijo `SECOND_BRAIN_` (documentadas en
    `.env.example`). Los defaults son los que hacen que `Settings()` sin
    ningún env var configurado arranque en modo 100% local.
    """

    mode: str = "local"

    embeddings_dim: int = 256

    falkor_host: str = "localhost"
    falkor_port: int = 6379
    # Alfanumérico a propósito: el conector FalkorDB real del GraphRAG
    # Toolkit (`adapters.graphrag_toolkit.falkordb_graph_store`) rechaza
    # cualquier nombre de base con guiones bajos. Con este default, el
    # ensayo local corre de verdad sobre el conector del toolkit; un
    # `graph_name` con guión bajo (como usan algunos tests contra un
    # FalkorDB real) sigue funcionando por el fallback al cliente directo.
    falkor_graph_name: str = "secondbrain"

    vector_store_path: str | None = None

    aws_region: str = "us-east-1"
    # Nova 2 Multimodal Embeddings como default (elección del usuario: Nova
    # donde exista). Dim 1024 — la misma del índice de S3 Vectors, así que el
    # cambio no obligó a recrearlo. Cohere Embed Multilingual v3 queda a un
    # env var (SECOND_BRAIN_BEDROCK_EMBEDDINGS_MODEL_ID) y su camino sigue
    # implementado en el adapter. Cambiar de modelo de embeddings SIEMPRE
    # exige re-ingestar: los espacios vectoriales no son compatibles.
    bedrock_embeddings_model_id: str = "amazon.nova-2-multimodal-embeddings-v1:0"
    bedrock_embeddings_dim: int = 1024
    bedrock_rerank_model_id: str = "cohere.rerank-v3-5:0"
    # Nova MICRO como default de síntesis: ~20x más barato que Nova Pro
    # ($0.035 vs $0.80 por millón de tokens de entrada) y verificado contra la
    # pregunta más exigente del guion (el gancho de Billing 2.0): responde con
    # el equipo correcto, declina los puentes sin evidencia y cita. Misma
    # filosofía que la elección de FalkorDB: la opción más barata que hace
    # todo lo que se necesita. Nova Pro queda a un env var de distancia
    # (SECOND_BRAIN_BEDROCK_LLM_MODEL_ID=amazon.nova-pro-v1:0).
    bedrock_llm_model_id: str = "amazon.nova-micro-v1:0"
    bedrock_guardrail_id: str | None = None
    bedrock_guardrail_version: str | None = None
    bedrock_guardrail_trace: str = "enabled"

    s3_vectors_bucket: str | None = None
    s3_vectors_index_name: str | None = None

    # Memoria (AgentCore Memory en modo aws, FakeMemoryStore en modo local —
    # ver openspec/changes/agregar-memoria-second-brain/). Apagada por
    # default a propósito: activarla implica escritura (`CreateEvent`) además
    # de lectura, así que nunca debe encenderse sola. `agentcore_memory_id`
    # es específico de la cuenta: SIEMPRE vacío en `.env.example`, nunca
    # hardcodeado ni commiteado con un valor real.
    memory_enabled: bool = False

    # La KB gestionada es OPT-IN y suma un ranking al híbrido; apagada, el
    # pipeline queda idéntico al de siempre (ver `retrieval.retrieve`).
    knowledge_base_enabled: bool = False
    bedrock_kb_id: str | None = None
    agentcore_memory_id: str | None = None
    agentcore_actor_id: str = "demo-speaker"

    @classmethod
    def from_env(cls) -> Settings:
        return cls(
            mode=_env("MODE", "local"),
            embeddings_dim=_env_int("EMBEDDINGS_DIM", 256),
            falkor_host=_env("FALKOR_HOST", "localhost"),
            falkor_port=_env_int("FALKOR_PORT", 6379),
            falkor_graph_name=_env("FALKOR_GRAPH_NAME", "secondbrain"),
            vector_store_path=_env("VECTOR_STORE_PATH"),
            aws_region=_env("AWS_REGION", "us-east-1"),
            bedrock_embeddings_model_id=_env(
                "BEDROCK_EMBEDDINGS_MODEL_ID", "amazon.nova-2-multimodal-embeddings-v1:0"
            ),
            bedrock_embeddings_dim=_env_int("BEDROCK_EMBEDDINGS_DIM", 1024),
            bedrock_rerank_model_id=_env("BEDROCK_RERANK_MODEL_ID", "cohere.rerank-v3-5:0"),
            bedrock_llm_model_id=_env("BEDROCK_LLM_MODEL_ID", "amazon.nova-micro-v1:0"),
            bedrock_guardrail_id=_env("BEDROCK_GUARDRAIL_ID"),
            bedrock_guardrail_version=_env("BEDROCK_GUARDRAIL_VERSION"),
            bedrock_guardrail_trace=_env("BEDROCK_GUARDRAIL_TRACE", "enabled"),
            s3_vectors_bucket=_env("S3_VECTORS_BUCKET"),
            s3_vectors_index_name=_env("S3_VECTORS_INDEX_NAME"),
            memory_enabled=_env_bool("MEMORY_ENABLED", False),
            knowledge_base_enabled=_env_bool("KNOWLEDGE_BASE_ENABLED", False),
            bedrock_kb_id=_env("BEDROCK_KB_ID"),
            agentcore_memory_id=_env("AGENTCORE_MEMORY_ID"),
            agentcore_actor_id=_env("AGENTCORE_ACTOR_ID", "demo-speaker"),
        )


@dataclass
class Stack:
    """El conjunto de puertos ya cableados, listos para que el agente los use."""

    embeddings: EmbeddingsPort
    vector_store: VectorStorePort
    graph_store: GraphStorePort
    rerank: RerankPort
    llm: LlmPort
    # `None` por default: memoria es pista, nunca evidencia, y solo existe
    # cuando `Settings.memory_enabled` (+ el id de AgentCore, en modo aws) la
    # activan explícitamente — ver `build_stack`. Con default, ningún
    # `Stack(...)` existente (tests incluidos) se rompe.
    memory: MemoryPort | None = None
    # `None` salvo que modo aws + `knowledge_base_enabled` + id configurado
    # coincidan: sin los tres, `retrieve` no la consulta y no hay tráfico.
    knowledge_base: KnowledgeBasePort | None = None


def build_stack(settings: Settings) -> Stack:
    """Fábrica única: local u AWS según `settings.mode`, sin ramas en el resto del código.

    En modo `"local"` no se construye ningún cliente AWS ni se importa
    `boto3`. En modo `"aws"` se construyen los adapters reales, pero sus
    constructores tampoco llaman a `boto3` — cada uno lo importa recién
    en el primer método real (`embed`, `generate`, `query`, ...).
    """

    if settings.mode == "aws":
        return _stack_aws(settings)
    if settings.mode == "local":
        return _stack_local(settings)
    raise ValueError(f"SECOND_BRAIN_MODE inválido: '{settings.mode}' (use 'local' o 'aws')")


def _stack_local(settings: Settings) -> Stack:
    from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
    from second_brain.adapters.local.fake_rerank import FakeRerank
    from second_brain.adapters.local.falkor_graph_store import FalkorGraphStore
    from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
    from second_brain.adapters.local.scripted_llm import ScriptedLlm

    memory: MemoryPort | None = None
    if settings.memory_enabled:
        from second_brain.adapters.local.fake_memory_store import FakeMemoryStore

        memory = FakeMemoryStore()

    return Stack(
        embeddings=FakeEmbeddings(dim=settings.embeddings_dim),
        vector_store=MemoryVectorStore(persistence_path=settings.vector_store_path),
        graph_store=FalkorGraphStore(
            host=settings.falkor_host,
            port=settings.falkor_port,
            graph_name=settings.falkor_graph_name,
        ),
        rerank=FakeRerank(),
        llm=ScriptedLlm(),
        memory=memory,
    )


def _stack_aws(settings: Settings) -> Stack:
    """Bedrock + S3 Vectors reales; el grafo sigue siendo FalkorDB, apuntado por env var.

    `SECOND_BRAIN_FALKOR_HOST`/`FALKOR_PORT`/`FALKOR_GRAPH_NAME` son las
    mismas variables que usa el modo local — no hay un segundo juego de
    variables para "FalkorDB en AWS". Hoy, sin nada desplegado, apuntan por
    default a `localhost` (no alcanzable desde AgentCore Runtime); el día que
    haya un FalkorDB remoto (Docker en un host, Fargate, lo que sea), basta
    con setear esas tres variables — este adapter no cambia. Ver
    `demo/infra/README.md` para la consecuencia de no tener ese endpoint
    remoto todavía.
    """
    from second_brain.adapters.aws.bedrock_embeddings import BedrockEmbeddings
    from second_brain.adapters.aws.bedrock_llm import BedrockLlm
    from second_brain.adapters.aws.bedrock_rerank import BedrockRerank
    from second_brain.adapters.aws.s3_vectors_store import S3VectorsStore
    from second_brain.adapters.local.falkor_graph_store import FalkorGraphStore

    memory: MemoryPort | None = None
    if settings.memory_enabled and settings.agentcore_memory_id:
        from second_brain.adapters.aws.agentcore_memory_store import AgentCoreMemoryStore

        memory = AgentCoreMemoryStore(
            memory_id=settings.agentcore_memory_id, region=settings.aws_region
        )

    knowledge_base: KnowledgeBasePort | None = None
    if settings.knowledge_base_enabled and settings.bedrock_kb_id:
        from second_brain.adapters.aws.knowledge_base_store import KnowledgeBaseStore

        knowledge_base = KnowledgeBaseStore(
            knowledge_base_id=settings.bedrock_kb_id, region=settings.aws_region
        )

    return Stack(
        embeddings=BedrockEmbeddings(
            model_id=settings.bedrock_embeddings_model_id,
            region=settings.aws_region,
            dim=settings.bedrock_embeddings_dim,
        ),
        vector_store=S3VectorsStore(
            bucket=settings.s3_vectors_bucket or "",
            index_name=settings.s3_vectors_index_name or "",
            region=settings.aws_region,
        ),
        graph_store=FalkorGraphStore(
            host=settings.falkor_host,
            port=settings.falkor_port,
            graph_name=settings.falkor_graph_name,
        ),
        rerank=BedrockRerank(region=settings.aws_region, model_id=settings.bedrock_rerank_model_id),
        knowledge_base=knowledge_base,
        llm=BedrockLlm(
            model_id=settings.bedrock_llm_model_id,
            region=settings.aws_region,
            guardrail_id=settings.bedrock_guardrail_id,
            guardrail_version=settings.bedrock_guardrail_version,
            guardrail_trace=settings.bedrock_guardrail_trace,
        ),
        memory=memory,
    )
