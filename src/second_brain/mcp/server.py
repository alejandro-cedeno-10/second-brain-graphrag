"""Servidor MCP propio del second brain: las mismas dos manos
(`search_documents`/`traverse_graph` de `second_brain.agent.tools`) detrás
del protocolo MCP en vez de detrás del loop de un `Agent` de Strands.

Es la mitad "MCP" de la distinción MCP ≠ A2A (ver el docstring de
`second_brain.mcp` y de `second_brain.a2a`): un cliente MCP (Claude Code,
Strands, cualquier host que hable el protocolo) es quien decide cuándo y
con qué argumentos invocar cada tool — este módulo solo las publica y
devuelve evidencia estructurada, nunca redacta ni decide nada.

Corre local (`demo.py mcp-server`), por stdio (el transporte que espera un
cliente MCP de escritorio, como Claude Code) o por `streamable-http` (para
un cliente que hable HTTP en vez de lanzar un subproceso). El camino
gestionado equivalente — AgentCore Gateway con un target `mcpServer`
apuntando a ESTE servidor corriendo persistente — está declarado como
alternativa documentada en `infra/stacks/agentcore_stack.py` (sección
"Gateway — por qué Lambda y no OpenAPI/Smithy/mcpServer/apiGateway"); no se
despliega desde acá.
"""

from __future__ import annotations

import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from second_brain.agent.tools import Evidence, search_documents, traverse_graph
from second_brain.config import Stack
from second_brain.retrieval import LexicalIndex

SERVER_NAME = "second-brain-nexora"

SERVER_INSTRUCTIONS = (
    "Second brain GraphRAG de Nexora Corp, expuesto como herramienta MCP. "
    "Dos tools: `search_documents` (evidencia citable del corpus indexado) "
    "y `traverse_graph` (dependencias entre servicios). Ninguna de las dos "
    "redacta una respuesta: devuelven evidencia estructurada con su "
    "`doc_id` de origen para que quien llama arme su propia síntesis y cite "
    "la fuente. Si la pregunta nombra un sujeto claro (un slug como "
    "'core-billing'), pasalo en `target`/`entity` — ancla la búsqueda al "
    "documento correcto en vez de competir contra todo el corpus."
)


def _evidence_to_payload(items: list[Evidence]) -> list[dict[str, Any]]:
    return [
        {
            "doc_id": item.doc_id,
            "text": item.text,
            "score": item.score,
            "is_target": item.is_target,
            "source": item.source,
            "chunk_id": item.chunk_id,
        }
        for item in items
    ]


def _warm_up_graph_store(stack: Stack) -> None:
    """Fuerza AHORA (todavía en el hilo principal, antes de que
    `mcp_app.run()` arranque el loop de asyncio del transporte) la
    resolución perezosa del conector real del GraphRAG Toolkit
    (`FalkorGraphStore._toolkit_store`, ver su docstring). Sin este
    warm-up, la primera resolución ocurre recién dentro del hilo worker
    donde corre `traverse_graph` — la primera tool call real de un
    cliente MCP — y esa importación pesada (llama-index/spacy) compitiendo
    con el loop de `anyio` que ya está sirviendo la sesión deja el
    transporte stdio en un estado roto sin ninguna excepción de Python que
    capturar (verificado con un round-trip stdio real, no en teoría).
    Fail-open: si el grafo no está disponible todavía (por ejemplo, no se
    corrió `ingest`), esto no debe tumbar el arranque del servidor.
    """
    try:
        stack.graph_store.query("RETURN 1 AS ping", {})
    except Exception as error:
        logging.getLogger(__name__).warning(
            "No se pudo precalentar el graph store antes de servir MCP: %s", error
        )


def build_mcp_server(
    stack: Stack,
    lexical_index: LexicalIndex,
    *,
    name: str = SERVER_NAME,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> FastMCP:
    """Arma el `FastMCP` con las dos tools cerradas sobre `stack`/`lexical_index`.

    `host`/`port` solo importan para el transporte `streamable-http` (el
    transporte `stdio`, el que usa un cliente de escritorio como Claude
    Code, no abre ningún puerto).
    """
    mcp = FastMCP(name, instructions=SERVER_INSTRUCTIONS, host=host, port=port)
    _warm_up_graph_store(stack)

    @mcp.tool(
        name="search_documents",
        description=(
            "Busca evidencia citable en la base de conocimiento indexada de "
            "Nexora Corp. Devuelve una lista de fragmentos con su `doc_id` "
            "de origen, nunca prosa ya redactada."
        ),
    )
    def _search_documents_tool(question: str, target: str | None = None) -> list[dict[str, Any]]:
        """Args:
        question: La pregunta o sub-pregunta a buscar.
        target: Nombre del documento/entidad sobre el que ancla la
            pregunta si nombra un sujeto claro (p.ej. 'core-billing').
            Dejalo vacío si la pregunta no nombra un sujeto específico.
        """
        evidencia = search_documents(question, stack, lexical_index, target=target)
        return _evidence_to_payload(evidencia)

    @mcp.tool(
        name="traverse_graph",
        description=(
            "Recorre el grafo de dependencias entre servicios de Nexora "
            "Corp desde `entity`. Devuelve un ítem de evidencia por cada "
            "salto, con el `doc_id` que sostiene esa relación."
        ),
    )
    def _traverse_graph_tool(
        entity: str, kind: str = "blast_radius", max_hops: int = 3
    ) -> list[dict[str, Any]]:
        """Args:
        entity: Slug de la entidad raíz del traversal (p.ej. 'core-billing').
        kind: 'blast_radius' (default, quién depende de `entity`) o
            'vecinos' (vecindario directo).
        max_hops: Cuántos saltos como máximo recorrer.
        """
        evidencia = traverse_graph(entity, stack, kind=kind, max_hops=max_hops)
        return _evidence_to_payload(evidencia)

    return mcp
