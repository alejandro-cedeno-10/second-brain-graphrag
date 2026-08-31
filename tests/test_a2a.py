"""El second brain expuesto como AGENTE A2A (`second_brain.a2a`): la
demo de cierre de la charla, verificada de verdad — un servidor uvicorn
real escuchando en loopback y un cliente A2A real hablándole por HTTP
(sin mocks de transporte). El round-trip por DOS PROCESOS de sistema
operativo separados (en vez de un servidor en un hilo del mismo proceso
de test) se verificó a mano; ver el reporte de la tarea que agregó este
archivo para esa transcripción.

La propiedad que este archivo existe para proteger: la respuesta que
`support_agent.ask` recibe conserva sus citas Y sus degradaciones
(`agent.guards.validate_relational_claims`) después de cruzar la red — un
agente remoto que recibiera la respuesta sin eso destruiría la tesis de la
charla (ver `test_a2a_answer_preserves_citations_and_degraded_claims`,
mismo escenario Billing 2.0 que ya cubre `tests/test_agent.py`).
"""

from __future__ import annotations

import asyncio
import contextlib
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import uvicorn

from second_brain.a2a.server import build_a2a_app
from second_brain.a2a.support_agent import ask, discover
from second_brain.adapters.local.fake_embeddings import FakeEmbeddings
from second_brain.adapters.local.fake_rerank import FakeRerank
from second_brain.adapters.local.memory_graph_store import MemoryGraphStore
from second_brain.adapters.local.memory_vector_store import MemoryVectorStore
from second_brain.adapters.local.scripted_llm import ScriptedLlm, ScriptedRule
from second_brain.config import Stack
from second_brain.graph.build import build_graph
from second_brain.ingestion import chunk_document, index, load_corpus
from second_brain.ports import LlmResponse, ToolCall
from second_brain.retrieval import LexicalIndex, build_lexical_index

CORPUS = Path(__file__).resolve().parent.parent / "corpus"

P2 = "Si modifico la API de core-billing, ¿qué módulos se rompen?"
P_BILLING = (
    "¿Qué dependencia puede retrasar Billing 2.0, qué equipo debe resolverla "
    "y qué decisión técnica explica el riesgo?"
)


def _stack_and_index() -> tuple[Stack, LexicalIndex]:
    stack = Stack(
        embeddings=FakeEmbeddings(),
        vector_store=MemoryVectorStore(),
        graph_store=MemoryGraphStore(),
        rerank=FakeRerank(),
        llm=None,
    )
    corpus = load_corpus(CORPUS)
    index(corpus, stack)
    chunks = [chunk for doc in corpus for chunk in chunk_document(doc)]
    lexical_index = build_lexical_index(chunks)
    build_graph(CORPUS, stack)
    return stack, lexical_index


def _agentic_llm_for(stack: Stack):
    """Reutiliza el guion de dos fases de `demo.py` (decidir tool, después
    redactar) para que el servidor A2A de este test corra el MISMO loop
    agéntico real que corre en vivo (`answer_agentic`), en vez de un
    `ScriptedLlm` de una sola respuesta que no lo ejercitaría de verdad.
    """
    import importlib.util
    import sys

    demo_path = Path(__file__).resolve().parent.parent / "demo.py"
    spec = importlib.util.spec_from_file_location("second_brain_demo_cli_test_a2a", demo_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.build_agentic_scripted_llm(stack)


def _decide_tool(*tool_calls: ToolCall) -> ScriptedRule:
    """Mismo helper que `tests/test_strands_agent.py::_decide_tool`: la
    primera fase del guion agéntico (decidir qué tool llamar) para un
    turno que este archivo quiere controlar a mano en vez de delegar en
    el guion canned de `demo.py`.
    """

    def cuando(system: str, messages: list[dict]) -> bool:
        return not any(
            "toolResult" in block for message in messages for block in message.get("content", [])
        )

    respuesta = LlmResponse(text="", tool_calls=list(tool_calls), stop_reason="tool_use")
    return ScriptedRule(when=cuando, response=respuesta)


def _draft(text: str) -> ScriptedRule:
    def cuando(system: str, messages: list[dict]) -> bool:
        return any(
            "toolResult" in block for message in messages for block in message.get("content", [])
        )

    return ScriptedRule(when=cuando, response=LlmResponse(text=text, stop_reason="end_turn"))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@contextlib.contextmanager
def _running_a2a_server(stack: Stack, lexical_index: LexicalIndex) -> Iterator[str]:
    """Levanta el servidor A2A real (uvicorn, socket de loopback real) en
    un hilo, para que los tests hablen HTTP de verdad en vez de contra un
    transporte simulado — la misma pieza que corre como proceso separado
    en la demo de cierre, solo que acá comparte proceso con pytest.
    """
    port = _free_port()
    app = build_a2a_app(stack, lexical_index, host="127.0.0.1", port=port)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 5.0
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)
        assert server.started, "el servidor A2A de test no arrancó a tiempo"
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)


def test_a2a_agent_card_advertises_a_citing_answering_skill() -> None:
    stack, lexical_index = _stack_and_index()
    stack.llm = _agentic_llm_for(stack)

    with _running_a2a_server(stack, lexical_index) as endpoint:
        card = asyncio.run(discover(endpoint))

    assert card.name == "second-brain-nexora"
    assert card.capabilities.streaming is True
    assert any("cita" in skill.description.lower() for skill in card.skills)


def test_a2a_support_agent_receives_streamed_progress_and_a_cited_answer() -> None:
    """El escenario completo de la demo de cierre: el "agente de soporte"
    descubre la Agent Card, pregunta por A2A, recibe progreso (no tokens
    crudos) y una respuesta final CON CITAS — reproduciendo P2.
    """
    stack, lexical_index = _stack_and_index()
    stack.llm = _agentic_llm_for(stack)

    progreso: list[str] = []
    with _running_a2a_server(stack, lexical_index) as endpoint:
        respuesta = asyncio.run(ask(endpoint, P2, on_progress=progreso.append))

    assert progreso, "el second brain tiene que emitir progreso ANTES de la respuesta final"
    assert any("herramienta." in linea or "gate." in linea for linea in progreso)

    assert not respuesta.abstained
    assert respuesta.citations, "la respuesta de P2 tiene evidencia: no debería llegar sin citas"
    assert "[source:" in respuesta.text
    assert all("document" in cita for cita in respuesta.citations)


def test_a2a_answer_preserves_citations_and_degraded_claims() -> None:
    """La garantía crítica del cierre de la charla: el anclaje al grafo
    (`agent.guards.validate_relational_claims`) sigue degradando el puente
    inventado auth-cache→Plataforma / ADR-017→retraso DESPUÉS de que la
    respuesta cruzó la red por A2A — no es una propiedad que solo se
    sostenga dentro de un proceso. Mismo texto "malo" y mismo veredicto que
    `tests/test_strands_agent.py::test_agentic_billing_2_0_degrades_the_invented_bridge_like_the_fixed_path`,
    ahora leído del lado del cliente A2A, después de un viaje de red real.
    """
    texto_malo = (
        "Billing 2.0 podría retrasarse por la dependencia con auth-cache "
        "[source:producto/billing-2-0.md]. El equipo de Plataforma debe "
        "resolverlo, ya que la decisión ADR-017 introdujo una caché "
        "distribuida que ha causado problemas de latencia "
        "[source:arquitectura/decisiones.md] "
        "[source:incidentes/postmortem-inc-042-auth-cache.md]."
    )
    stack, lexical_index = _stack_and_index()
    stack.llm = ScriptedLlm(
        rules=[
            _decide_tool(
                ToolCall(
                    name="search_documents",
                    arguments={"question": P_BILLING, "target": "billing-2-0"},
                    id="t1",
                ),
                ToolCall(name="traverse_graph", arguments={"entity": "billing-2-0"}, id="t2"),
            ),
            _draft(texto_malo),
        ]
    )

    with _running_a2a_server(stack, lexical_index) as endpoint:
        respuesta = asyncio.run(ask(endpoint, P_BILLING))

    assert not respuesta.abstained
    assert respuesta.citations, "Billing 2.0 tiene evidencia real: la respuesta debe traer citas"
    assert "sin evidencia suficiente para afirmar que Plataforma" in respuesta.text, (
        "el puente inventado auth-cache -> Plataforma no debe sobrevivir la degradación, "
        "ni siquiera después de cruzar la red por A2A"
    )
    documentos_citados = {c["document"] for c in respuesta.citations}
    assert "producto/billing-2-0.md" in documentos_citados, (
        "la dependencia real (auth-cache) sí respaldada debe sobrevivir intacta"
    )


def test_answer_to_parts_carries_text_and_structured_citations() -> None:
    """Unitario del punto exacto donde viajan las citas: `_answer_to_parts`
    tiene que producir un `TextPart` (prosa, con las marcas `[source:...]`)
    Y un `DataPart` (citas estructuradas) — nunca solo uno de los dos.
    """
    from a2a.types import DataPart, TextPart

    from second_brain.a2a.server import _answer_to_parts
    from second_brain.ports import Answer, Citation

    fragmento = "`pagos` depende de `core-billing`."
    citas = [Citation(document="pagos", fragment=fragmento, chunk_id=None)]
    respuesta = Answer(
        text="`pagos` depende de `core-billing` [source:pagos].",
        citations=citas,
        abstained=False,
    )
    partes = _answer_to_parts(respuesta)

    assert len(partes) == 2
    assert isinstance(partes[0].root, TextPart)
    assert partes[0].root.text == respuesta.text
    assert isinstance(partes[1].root, DataPart)
    assert partes[1].root.data["citations"] == [
        {"document": "pagos", "fragment": "`pagos` depende de `core-billing`.", "chunk_id": None}
    ]
    assert partes[1].root.data["abstained"] is False
