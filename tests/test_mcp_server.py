"""El second brain expuesto como HERRAMIENTA MCP (`second_brain.mcp.server`):
un round-trip real de protocolo (`tools/list` + `tools/call`) contra el
`FastMCP` armado por `build_mcp_server`, usando el helper de testing del
propio SDK `mcp` (sesión cliente/servidor conectada en memoria, sin
subproceso — el subproceso real por stdio se verificó a mano, ver el
reporte de la tarea que agregó este archivo).

Contraste con `tests/test_a2a.py`: acá quien "decide" es el cliente MCP
(este test hace de uno), llamando una tool a la vez y leyendo evidencia
cruda — nunca una respuesta ya redactada con citas.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from mcp.shared.memory import create_connected_server_and_client_session

from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
from second_brain.adapters.local.fake_rerank import FakeRerank
from second_brain.adapters.local.memory_graph_store import MemoryGraphStore
from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
from second_brain.adapters.local.scripted_llm import ScriptedLlm
from second_brain.config import Stack
from second_brain.graph.build import build_graph
from second_brain.ingestion import chunk_document, index, load_corpus
from second_brain.mcp.server import build_mcp_server
from second_brain.retrieval import LexicalIndex, build_lexical_index

CORPUS = Path(__file__).resolve().parent.parent / "corpus"


def _stack_and_index() -> tuple[Stack, LexicalIndex]:
    stack = Stack(
        embeddings=FakeEmbeddings(),
        vector_store=MemoryVectorStore(),
        graph_store=MemoryGraphStore(),
        rerank=FakeRerank(),
        llm=ScriptedLlm(),
    )
    corpus = load_corpus(CORPUS)
    index(corpus, stack)
    chunks = [chunk for doc in corpus for chunk in chunk_document(doc)]
    lexical_index = build_lexical_index(chunks)
    build_graph(CORPUS, stack)
    return stack, lexical_index


def test_mcp_server_lists_exactly_the_two_second_brain_tools() -> None:
    stack, lexical_index = _stack_and_index()
    mcp_app = build_mcp_server(stack, lexical_index)

    async def _run() -> set[str]:
        async with create_connected_server_and_client_session(mcp_app._mcp_server) as session:
            result = await session.list_tools()
            return {tool.name for tool in result.tools}

    assert asyncio.run(_run()) == {"search_documents", "traverse_graph"}


def test_mcp_search_documents_call_returns_citable_evidence_with_doc_id() -> None:
    stack, lexical_index = _stack_and_index()
    mcp_app = build_mcp_server(stack, lexical_index)

    async def _run() -> list[dict]:
        async with create_connected_server_and_client_session(mcp_app._mcp_server) as session:
            result = await session.call_tool(
                "search_documents",
                {"question": "¿Quién lidera el Proyecto Beta?"},
            )
            return result.structuredContent["result"]

    evidencia = asyncio.run(_run())
    assert evidencia
    assert all("doc_id" in item and "text" in item for item in evidencia)
    assert any("proyectos" in item["doc_id"] for item in evidencia)


def test_mcp_traverse_graph_call_finds_core_billing_dependents() -> None:
    stack, lexical_index = _stack_and_index()
    mcp_app = build_mcp_server(stack, lexical_index)

    async def _run() -> list[dict]:
        async with create_connected_server_and_client_session(mcp_app._mcp_server) as session:
            result = await session.call_tool(
                "traverse_graph",
                {"entity": "core-billing", "kind": "blast_radius", "max_hops": 3},
            )
            return result.structuredContent["result"]

    evidencia = asyncio.run(_run())
    assert evidencia
    assert all(item["source"] == "grafo" for item in evidencia)
    assert any("pagos" in item["text"] for item in evidencia)
