"""Contratos del sistema (arquitectura de puertos).

Este módulo define el vocabulario común que comparten TODOS los adapters,
locales o de AWS. Es el único lugar del paquete que "sabe" qué es un chunk,
un hit o una respuesta — nada del dominio depende de boto3, redis o numpy.

Se usan `typing.Protocol` en lugar de clases abstractas (ABC) a propósito:
un adapter cumple un puerto por tener la forma correcta (duck typing
estructural, verificable estáticamente), sin necesidad de heredar de nada
ni de que el paquete de dominio conozca la jerarquía de sus implementaciones.
Eso es lo que permite que `adapters/local` y `adapters/aws` sean
intercambiables sin tocar una sola línea del código que los consume.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class Chunk:
    """Unidad de texto indexable: lo que viaja desde la ingesta hasta el vector store."""

    id: str
    document_id: str
    text: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None


@dataclass
class Hit:
    """Resultado crudo de una búsqueda vectorial, antes de rerank."""

    chunk_id: str
    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ScoredDoc:
    """Documento puntuado por el reranker, ya listo para entrar al LLM."""

    text: str
    score: float
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_id: str | None = None


@dataclass
class Path:
    """Camino de traversal en el grafo: secuencia de nodos unidos por relaciones.

    `relations` tiene largo `len(nodes) - 1`: `relations[i]` conecta
    `nodes[i]` con `nodes[i + 1]`.

    `provenance` es paralelo a `relations` (mismo largo cuando el adapter lo
    completa): `provenance[i]` es el `document_id` del que salió la arista
    `relations[i]`, para que una respuesta que cita un camino de grafo pueda
    señalar la fuente de cada salto. Un adapter que no lo soporte (p.ej. un
    `neighbors` viejo) puede dejarlo vacío sin romper nada, porque el default
    es una lista vacía.

    `directions` es igual de paralelo y existe porque el traversal es NO
    DIRIGIDO —"quien depende de X" se contesta caminando aristas al reves—
    pero la relacion SI tiene sentido: `directions[i]` es True cuando la
    arista va `nodes[i] -> nodes[i + 1]` tal como la declara el corpus, y
    False cuando el camino la recorrio en contra. Sin este dato, verbalizar
    un salto produce la afirmacion INVERTIDA ("core-billing depende de
    notificaciones" en vez de al reves): un sistema que promete no inventar
    no puede darse ese lujo. Vacio significa "el adapter no lo informa", y
    quien lo consuma debe asumir sentido directo.
    """

    nodes: list[str] = field(default_factory=list)
    relations: list[str] = field(default_factory=list)
    provenance: list[str] = field(default_factory=list)
    directions: list[bool] = field(default_factory=list)


@dataclass
class Citation:
    """Referencia trazable de una afirmación de la respuesta a su fuente."""

    document: str
    fragment: str
    chunk_id: str | None = None


@dataclass
class TraceStep:
    """Un renglón del `--trace`: qué etapa del pipeline corrió y con qué resultado."""

    stage: str
    detail: str
    metadata: dict[str, Any] | None = None


@dataclass
class Answer:
    """Salida final del agente, con abstención explícita y traza auditable."""

    text: str
    citations: list[Citation] = field(default_factory=list)
    abstained: bool = False
    trace: list[TraceStep] = field(default_factory=list)


@dataclass
class ToolCall:
    """Invocación de tool que el LLM decidió hacer, a interpretar por el agente."""

    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    id: str | None = None


@dataclass
class LlmResponse:
    """Respuesta cruda del LLM: texto y/o tool calls, agnóstica del proveedor."""

    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "fin"
    token_usage: dict[str, int] | None = None
    guardrail_scores: dict[str, float] | None = None
    """Puntajes del guardrail de Bedrock cuando el adapter los recibe (p.ej.
    {"grounding": 0.91, "relevance": 0.88}). `None` = sin guardrail o adapter
    que no los reporta. Solo puntúa — la acción del guardrail es NONE y la
    honestidad la hacen cumplir el gate y el anclaje, que son deterministas."""


@runtime_checkable
class EmbeddingsPort(Protocol):
    """Convierte texto en vectores. `dim` debe ser estable durante la vida del objeto."""

    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


@runtime_checkable
class VectorStorePort(Protocol):
    """Índice de vectores con búsqueda por similitud y filtro opcional por metadata."""

    def upsert(self, items: list[Chunk]) -> None: ...

    def search(
        self, vector: list[float], top_k: int, filter: dict[str, Any] | None = None
    ) -> list[Hit]: ...


@runtime_checkable
class GraphStorePort(Protocol):
    """Grafo de conocimiento con openCypher — hoy implementado por FalkorDB.

    El puerto no sabe (ni le importa) qué motor hay detrás: cualquier motor
    openCypher que cumpla esta forma es un adapter válido, en local o en AWS.
    """

    def upsert_nodes(self, nodes: list[dict[str, Any]]) -> None: ...

    def upsert_edges(self, edges: list[dict[str, Any]]) -> None: ...

    def query(self, cypher: str, params: dict[str, Any] | None = None) -> list[dict[str, Any]]: ...

    def neighbors(self, entity: str, max_hops: int) -> list[Path]: ...


@runtime_checkable
class RerankPort(Protocol):
    """Reordena documentos candidatos por relevancia real a la pregunta."""

    def rerank(self, question: str, documents: list[str], top_n: int) -> list[ScoredDoc]: ...


@runtime_checkable
class LlmPort(Protocol):
    """Modelo de lenguaje generativo, con soporte opcional de tool calling."""

    def generate(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> LlmResponse: ...
