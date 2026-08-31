"""Servidor A2A del second brain: publica una Agent Card y ejecuta el turno
completo (`agent.strands_agent.answer_agentic`, con su coverage gate y sus
guards de salida) por cada mensaje entrante — ver el docstring de
`second_brain.a2a` para el contraste con `second_brain.mcp`.

## Por qué NO se usa `strands.multiagent.a2a.A2AServer` directamente

`A2AServer` envuelve un `strands.Agent` crudo: transmite el TEXTO que ese
`Agent` va redactando, tal cual sale del modelo. Eso bypasea exactamente
la garantía que esta charla no puede perder — `apply_guards` (recorte de
citas inválidas, degradación de afirmaciones relacionales sin respaldo del
grafo) corre DESPUÉS de que el `Agent` interno termina, dentro de
`answer_agentic`, no dentro del loop que `A2AServer` transmitiría. Publicar
el `Agent` crudo por A2A dejaría salir una respuesta sin guardar, con
afirmaciones que el propio second brain ya sabe que no puede sostener.

Por eso `SecondBrainA2AExecutor` (un `a2a.server.agent_execution.AgentExecutor`
propio, construido sobre el mismo `a2a-sdk` que `A2AServer` usa por
dentro) llama a `answer_agentic` completo y recién publica el `Answer` YA
GUARDADO — citas y degradaciones incluidas — como resultado final. Lo que
SÍ se transmite en vivo, turno a turno, es la traza (`TraceStep`) de
`answer_agentic` como actualizaciones de estado A2A (`TaskState.working`):
progreso real del agente (qué tool corrió, qué dijo el coverage gate, qué
guard degradó qué afirmación), nunca tokens crudos del LLM — es
exactamente la distinción que la charla hace entre "mostrar streaming" y
"mostrar tokens".

## Cómo viajan las citas

La respuesta final se manda en DOS partes A2A, no una: un `TextPart` con
la prosa (marcas `[source:doc_id]` incluidas, por si el agente remoto
entiende esa convención) y un `DataPart` con `citations`/`abstained`
estructurados — un cliente A2A genérico no tiene por qué conocer la
convención de corchetes del second brain, así que las citas viajan también
como datos, no solo como texto formateado. `support_agent.py` lee el
`DataPart`, no re-parsea el texto.
"""

from __future__ import annotations

import asyncio
import logging

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.apps import A2AStarletteApplication
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import InMemoryTaskStore, TaskUpdater
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentSkill,
    DataPart,
    InternalError,
    Part,
    TaskState,
    TextPart,
    UnsupportedOperationError,
)
from a2a.utils import new_task
from a2a.utils.errors import ServerError
from starlette.applications import Starlette

from second_brain.agent.strands_agent import answer_agentic
from second_brain.config import Stack
from second_brain.ports import Answer, TraceStep
from second_brain.retrieval import LexicalIndex

logger = logging.getLogger(__name__)

AGENT_NAME = "second-brain-nexora"

AGENT_DESCRIPTION = (
    "Second brain GraphRAG de Nexora Corp: responde preguntas en español "
    "sobre su arquitectura, dependencias entre servicios y documentación "
    "interna, combinando búsqueda semántica sobre el corpus y traversal "
    "del grafo de dependencias. Cada afirmación cita su documento fuente; "
    "una relación que el grafo no respalda se degrada en vez de afirmarse; "
    "sin evidencia suficiente, se abstiene en vez de inventar."
)

ANSWER_ARTIFACT_NAME = "second_brain_answer"
"""Nombre del artifact final: `support_agent.py` lo usa para distinguir la
respuesta guardada de cualquier otro artifact que un `AgentExecutor` más
elaborado pudiera agregar en el futuro (archivos, por ejemplo).
"""


def build_agent_card(url: str, *, version: str = "0.1.0") -> AgentCard:
    """La Agent Card pública: lo primero que un agente ajeno (el "agente de
    soporte" de `support_agent.py`, o cualquier otro cliente A2A) lee para
    saber qué sabe hacer este agente, sin conocer nada de su implementación.
    """
    return AgentCard(
        name=AGENT_NAME,
        description=AGENT_DESCRIPTION,
        url=url,
        version=version,
        capabilities=AgentCapabilities(streaming=True),
        default_input_modes=["text"],
        default_output_modes=["text", "data"],
        skills=[
            AgentSkill(
                id="responder_con_citas",
                name="Responder preguntas de Nexora Corp con citas trazables",
                description=(
                    "Responde preguntas sobre la arquitectura, las "
                    "dependencias entre servicios y la documentación "
                    "interna de Nexora Corp. Cada afirmación cita su "
                    "documento fuente; las relaciones no respaldadas por "
                    "el grafo se degradan en vez de afirmarse; sin "
                    "evidencia, se abstiene."
                ),
                tags=["graphrag", "citas", "nexora", "dependencias"],
            )
        ],
    )


def _progress_text(step: TraceStep) -> str:
    return f"[{step.stage}] {step.detail}"


def _answer_to_parts(answer: Answer) -> list[Part]:
    citations = [
        {
            "document": citation.document,
            "fragment": citation.fragment,
            "chunk_id": citation.chunk_id,
        }
        for citation in answer.citations
    ]
    return [
        Part(root=TextPart(text=answer.text)),
        Part(root=DataPart(data={"citations": citations, "abstained": answer.abstained})),
    ]


class SecondBrainA2AExecutor(AgentExecutor):
    """Ejecuta un turno completo de `answer_agentic` por mensaje A2A entrante.

    `progress_delay` no existe por necesidad técnica (el pipeline local
    corre en milisegundos con `ScriptedLlm`): existe para que el streaming
    de progreso sea VISIBLE en una demo en vivo frente a público — sin
    ella, las actualizaciones de estado llegarían todas juntas y el efecto
    de "dos agentes conversando en tiempo real" se pierde. Default 0.0
    (sin demora) para que los tests corran rápido.
    """

    def __init__(
        self,
        stack: Stack,
        lexical_index: LexicalIndex,
        *,
        progress_delay: float = 0.0,
    ) -> None:
        self._stack = stack
        self._lexical_index = lexical_index
        self._progress_delay = progress_delay

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task = context.current_task
        if not task:
            task = new_task(context.message)  # type: ignore[arg-type]
            await event_queue.enqueue_event(task)

        updater = TaskUpdater(event_queue, task.id, task.context_id)
        question = context.get_user_input().strip()
        if not question:
            raise ServerError(error=InternalError(message="El mensaje no trae ninguna pregunta"))

        await updater.start_work()
        try:
            answer = await self._run_with_progress(question, updater)
        except Exception:
            logger.exception("second_brain.a2a: fallo respondiendo el turno")
            texto_falla = "El second brain falló respondiendo esta pregunta."
            await updater.failed(
                message=updater.new_agent_message(parts=[Part(root=TextPart(text=texto_falla))])
            )
            return

        await updater.add_artifact(_answer_to_parts(answer), name=ANSWER_ARTIFACT_NAME)
        await updater.complete()

    async def _run_with_progress(self, question: str, updater: TaskUpdater) -> Answer:
        """Corre `answer_agentic` en un hilo (es síncrono) mientras retransmite
        cada `TraceStep` que produce como una actualización de estado A2A, a
        medida que se genera — no al final. `on_paso` corre DENTRO del hilo
        worker, así que no puede tocar el `event_queue` directo (no es
        thread-safe); `call_soon_threadsafe` es el puente hacia el loop de
        asyncio que sí puede.
        """
        loop = asyncio.get_running_loop()
        steps: asyncio.Queue[TraceStep | None] = asyncio.Queue()

        def on_paso(step: TraceStep) -> None:
            loop.call_soon_threadsafe(steps.put_nowait, step)

        async def run_agent() -> Answer:
            try:
                return await asyncio.to_thread(
                    answer_agentic, question, self._stack, self._lexical_index, on_paso
                )
            finally:
                loop.call_soon_threadsafe(steps.put_nowait, None)

        agent_future = asyncio.ensure_future(run_agent())
        while True:
            step = await steps.get()
            if step is None:
                break
            if self._progress_delay:
                await asyncio.sleep(self._progress_delay)
            await updater.update_status(
                TaskState.working,
                message=updater.new_agent_message(parts=[Part(root=TextPart(text=_progress_text(step)))]),
            )
        return await agent_future

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        raise ServerError(error=UnsupportedOperationError())


def _warm_up_graph_store(stack: Stack) -> None:
    """Mismo warm-up defensivo que `second_brain.mcp.server` (ver su
    docstring para el bug real que motiva esto): fuerza AHORA, todavía en
    el hilo principal y antes de que uvicorn arranque su loop de asyncio,
    la resolución perezosa del conector real del GraphRAG Toolkit
    (`FalkorGraphStore._toolkit_store`). No se importa el warm-up de
    `second_brain.mcp` a propósito — los dos paquetes no se importan entre
    sí (ver el docstring de `second_brain.a2a`), así que esta duplicación
    de tres líneas es más barata que acoplarlos por un detalle interno.
    Fail-open: si el grafo no está disponible todavía, no debe tumbar el
    arranque del servidor.
    """
    try:
        stack.graph_store.query("RETURN 1 AS ping", {})
    except Exception as error:
        logger.warning("No se pudo precalentar el graph store antes de servir A2A: %s", error)


def build_a2a_app(
    stack: Stack,
    lexical_index: LexicalIndex,
    *,
    host: str = "127.0.0.1",
    port: int = 9500,
    progress_delay: float = 0.0,
    public_url: str | None = None,
) -> Starlette:
    """Arma la app Starlette servible por uvicorn: Agent Card en
    `/.well-known/agent-card.json` + el request handler JSON-RPC de A2A.

    `host`/`port` son la dirección de BIND de uvicorn — en Docker eso es
    `0.0.0.0` para que el puerto publicado sea alcanzable desde fuera del
    contenedor. Esa dirección NO sirve como `url` de la Agent Card: un
    cliente A2A remoto (`support_agent.py`, corriendo en otro contenedor o
    en otra red) usa ese campo para saber A DÓNDE conectarse después de
    descubrir la card, y `0.0.0.0` no es una dirección a la que nadie más
    pueda conectarse (verificado con un round-trip real: el cliente falla
    con `ConnectError` intentando `0.0.0.0`). `public_url` es la dirección
    REALMENTE alcanzable (`http://a2a-server:9500/` en Docker, el nombre
    del servicio de compose) — si no se pasa, cae al viejo default
    `http://{host}:{port}/`, que sigue siendo correcto para el caso local
    (`--host 127.0.0.1`, servidor y cliente en la misma máquina).
    """
    _warm_up_graph_store(stack)
    agent_card = build_agent_card(url=public_url or f"http://{host}:{port}/")
    executor = SecondBrainA2AExecutor(stack, lexical_index, progress_delay=progress_delay)
    handler = DefaultRequestHandler(agent_executor=executor, task_store=InMemoryTaskStore())
    return A2AStarletteApplication(agent_card=agent_card, http_handler=handler).build()


def serve(
    stack: Stack,
    lexical_index: LexicalIndex,
    *,
    host: str = "127.0.0.1",
    port: int = 9500,
    progress_delay: float = 0.0,
    public_url: str | None = None,
) -> None:
    """Punto de entrada para `demo.py a2a-server`: un proceso uvicorn real,
    el primero de los DOS procesos locales de la demo de cierre (el
    segundo es `support_agent.py`, corriendo aparte). Ver `build_a2a_app`
    para por qué `public_url` es un parámetro aparte de `host`/`port`.
    """
    import uvicorn

    app = build_a2a_app(
        stack,
        lexical_index,
        host=host,
        port=port,
        progress_delay=progress_delay,
        public_url=public_url,
    )
    uvicorn.run(app, host=host, port=port, log_level="warning")
