"""Backend web de la demo: expone el pipeline de `second_brain` como eventos
AG-UI (Agent User Interaction Protocol, ver ag-ui.com) por Server-Sent Events.

`POST /api/preguntar` acepta `{"question": ..., "agentic": bool, "naive": bool}`:
con `agentic=false` (default) corre el pipeline fijo
(`second_brain.agent.orchestrator.answer`); con `agentic=true` corre el
loop de un `Agent` de Strands (`second_brain.agent.strands_agent.answer_agentic`).
`naive=true` (default `false`) swapea únicamente la síntesis local de la
pregunta de Billing 2.0 por el guion de demostración deliberadamente malo
(`demo.TEXTO_P_BILLING_INGENUO`, ver `demo._build_cli_stack`), en cualquiera
de los dos caminos — es la misma bandera que `demo.py query --naive`, para
que la UI pueda mostrar en vivo el mismo antes/después que la CLI.
Los dos son síncronos — este módulo NO los reescribe async, solo los corre
en un hilo y convierte cada `TraceStep` que producen — vía el hook `on_paso`
que ambos aceptan con la misma firma — en eventos AG-UI que se emiten a
medida que llegan, para que la UI muestre el trace en vivo. Los dos caminos
usan el MISMO vocabulario de etapas (`herramienta.*`, `gate.*`,
`guards.*`, `canario`, ...) a propósito: el mapeo de abajo no distingue
cuál generó la traza.

Mapeo pipeline → AG-UI (ver `_evento_de_paso` y `_eventos_finales`):

- Inicio del turno              → RUN_STARTED
- `herramienta.*`                → TOOL_CALL_START + TOOL_CALL_ARGS + TOOL_CALL_END
  (búsqueda de documentos, navegación de grafo: se modelan como llamadas a
  herramienta porque eso son, literalmente, en el pipeline)
- `objetivos.resueltos`,
  `gate.cobertura`, `gate.abstencion`,
  `sintesis.llm`, `guards.*`, `canario` → STATE_DELTA
  (progreso de estado interno del agente, no una tool call)
- Texto final de la respuesta     → TEXT_MESSAGE_START + TEXT_MESSAGE_CONTENT* + TEXT_MESSAGE_END
  (fragmentado en varios CONTENT para dar sensación de streaming aunque el
  pipeline entregue el texto completo de una vez — el LLM real detrás del
  `ScriptedLlm`/`BedrockLlm` no expone streaming a este nivel)
- Cierre del turno               → RUN_FINISHED (o RUN_ERROR si el hilo del
  pipeline lanzó una excepción no controlada)

Las preguntas del guion NO están hardcodeadas acá: se leen dinámicamente de
`demo._VERIFICATIONS` (el smoke test de `demo.py check`), que es la misma
lista que ese comando usa — así un guion ampliado en paralelo por otro
cambio no requiere tocar este archivo.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import queue
import sys
import threading
import time
import uuid
from pathlib import Path as RutaArchivo
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from second_brain.agent.orchestrator import answer
from second_brain.agent.strands_agent import answer_agentic
from second_brain.graph.traversal import blast_radius
from second_brain.ports import Answer, TraceStep
from second_brain.ports import Path as CaminoGrafo

RUTA_WEB = RutaArchivo(__file__).resolve().parent
RUTA_DEMO_DIR = RUTA_WEB.parent


def _importar_cli_demo() -> Any:
    """Importa `demo.py` (la CLI, en la raíz de `demo/`) como módulo Python.

    No es un paquete instalado (`demo.py` vive al lado de `pyproject.toml`,
    fuera de `src/`), así que se carga por ruta explícita en vez de un
    `import demo` que dependería de que el cwd del proceso sea `demo/`.
    Reutilizar este módulo (en lugar de duplicar el guion o el armado del
    stack) es lo que mantiene a la UI sincronizada con la CLI sin copiar
    lógica ni texto de preguntas.
    """
    ruta = RUTA_DEMO_DIR / "demo.py"
    spec = importlib.util.spec_from_file_location("second_brain_demo_cli", ruta)
    modulo = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = modulo
    spec.loader.exec_module(modulo)
    return modulo


_cli = _importar_cli_demo()

app = FastAPI(title="Second Brain GraphRAG — demo web")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_LOCK_PIPELINE = threading.Lock()
_ESTADO: dict[str, Any] = {
    "stack": None,
    "stack_agentico": None,
    "stack_naive": None,
    "stack_agentico_naive": None,
    "indice": None,
    "settings": None,
}
_ULTIMO_GRAFO: dict[str, Any] = {"pregunta": None, "caminos": []}


def _asegurar_stack() -> None:
    """Arma los CUATRO stacks (uno por combinación camino × guion) la
    primera vez que hacen falta.

    Comparten el mismo `settings`/`indice`; lo único que cambia entre ellos
    es el guion del `LlmPort` local (ver `demo._build_cli_stack`) — en modo
    `aws` los cuatro usan el mismo `BedrockLlm` real, así que `naive` no
    tiene efecto ahí (ver el docstring de `_build_cli_stack`). Se arman los
    cuatro de una vez, no de forma perezosa por combinación pedida, para
    que alternar el toggle "modo ingenuo" en la UI durante la demo no
    dispare una reconstrucción de stack (con su lectura de disco del vector
    store) en pleno turno.
    """
    if _ESTADO["stack"] is not None:
        return
    settings = _cli._resolve_settings()
    _ESTADO["settings"] = settings
    _ESTADO["stack"] = _cli._build_cli_stack(settings, agentic=False)
    _ESTADO["stack_agentico"] = _cli._build_cli_stack(settings, agentic=True)
    _ESTADO["stack_naive"] = _cli._build_cli_stack(settings, agentic=False, naive=True)
    _ESTADO["stack_agentico_naive"] = _cli._build_cli_stack(settings, agentic=True, naive=True)
    _ESTADO["indice"] = _cli._build_cli_lexical_index()


def _stack_for(agentic: bool, naive: bool) -> Any:
    if agentic:
        return _ESTADO["stack_agentico_naive"] if naive else _ESTADO["stack_agentico"]
    return _ESTADO["stack_naive"] if naive else _ESTADO["stack"]


class PreguntaIn(BaseModel):
    question: str
    agentic: bool = False
    naive: bool = False


def _evento(kind: str, datos: dict[str, Any]) -> dict[str, str]:
    return {"event": kind, "data": json.dumps(datos, ensure_ascii=False)}


def _entity_from_doc_id(doc_id: str) -> str:
    return RutaArchivo(doc_id).stem


def _eventos_de_paso(
    paso: TraceStep, run_id: str, tool_call_id: str, duracion_ms: int
) -> list[dict[str, str]]:
    base = {
        "runId": run_id,
        "stage": paso.stage,
        "detail": paso.detail,
        "duracionMs": duracion_ms,
    }
    if not paso.stage.startswith("herramienta."):
        return [_evento("STATE_DELTA", {**base, "metadata": paso.metadata or {}})]
    nombre_tool = paso.stage.removeprefix("herramienta.")
    return [
        _evento(
            "TOOL_CALL_START",
            {**base, "toolCallId": tool_call_id, "toolCallName": nombre_tool},
        ),
        _evento(
            "TOOL_CALL_ARGS",
            {**base, "toolCallId": tool_call_id, "args": paso.metadata or {}},
        ),
        _evento(
            "TOOL_CALL_END",
            {**base, "toolCallId": tool_call_id, "result": paso.detail},
        ),
    ]


def _path_to_dict(path: CaminoGrafo) -> dict[str, Any]:
    return {
        "nodos": path.nodes,
        "relaciones": path.relations,
        "provenance": path.provenance,
        "direcciones": path.directions,
    }


def _calcular_subgrafo(answer: Answer, stack: Any) -> list[CaminoGrafo]:
    """Recalcula el blast radius de la entidad objetivo, para el panel de grafo.

    El traversal ya corrió dentro de `answer` (vía `traverse_graph`), pero
    la traza solo guarda conteos, no los `Path` completos — se recalcula acá
    con la misma función (`blast_radius`) que usa el CLI en `--trace`, nunca
    se reinterpreta el sentido de las aristas a mano (ver `Path.directions`
    en `ports.py`: invertirlo a mano es el bug ya corregido que no hay que
    reintroducir). `stack` es el que efectivamente respondió el turno (fijo
    o agéntico): los dos comparten el mismo grafo, pero pasarlo explícito
    evita adivinar cuál de los dos `_ESTADO` usar.
    """
    paso_objetivos = next((p for p in answer.trace if p.stage == "objetivos.resueltos"), None)
    if paso_objetivos is None or not paso_objetivos.metadata:
        return []
    objetivos = paso_objetivos.metadata.get("objetivos") or []
    if not objetivos:
        return []
    entidad = _entity_from_doc_id(objetivos[0])
    try:
        return blast_radius(entidad, stack, max_hops=3)
    except Exception:
        return []


async def _generate_events(question: str, agentic: bool = False, naive: bool = False):
    _asegurar_stack()
    stack = _stack_for(agentic, naive)
    responder = answer_agentic if agentic else answer
    run_id = str(uuid.uuid4())
    message_id = str(uuid.uuid4())
    cola: queue.Queue = queue.Queue()
    _CENTINELA = object()

    def on_paso(paso: TraceStep) -> None:
        cola.put(("paso", paso))

    def trabajo() -> None:
        with _LOCK_PIPELINE:
            try:
                respuesta = responder(question, stack, _ESTADO["indice"], on_paso=on_paso)
                caminos = _calcular_subgrafo(respuesta, stack)
                _ULTIMO_GRAFO["pregunta"] = question
                _ULTIMO_GRAFO["caminos"] = caminos
                cola.put(("fin", respuesta))
            except Exception as error:  # noqa: BLE001
                cola.put(("error", error))
            finally:
                cola.put((_CENTINELA, None))

    hilo = threading.Thread(target=trabajo, daemon=True)
    hilo.start()

    yield _evento("RUN_STARTED", {"runId": run_id, "threadId": run_id, "pregunta": question})

    inicio = time.perf_counter()
    loop = asyncio.get_event_loop()
    tool_call_ids: dict[str, str] = {}
    while True:
        tipo, payload = await loop.run_in_executor(None, cola.get)
        if tipo is _CENTINELA:
            break
        if tipo == "paso":
            paso: TraceStep = payload
            tool_call_id = tool_call_ids.setdefault(paso.stage, str(uuid.uuid4()))
            duracion_ms = int((time.perf_counter() - inicio) * 1000)
            for ev in _eventos_de_paso(paso, run_id, tool_call_id, duracion_ms):
                yield ev
        elif tipo == "fin":
            respuesta: Answer = payload
            yield _evento(
                "STATE_DELTA",
                {
                    "runId": run_id,
                    "stage": "respuesta.final",
                    "detail": "abstencion" if respuesta.abstained else "sintesis",
                    "metadata": {
                        "abstencion": respuesta.abstained,
                        "citas": [
                            {"documento": c.document, "fragmento": c.fragment}
                            for c in respuesta.citations
                        ],
                        "grafo": [_path_to_dict(c) for c in _ULTIMO_GRAFO["caminos"]],
                    },
                },
            )
            yield _evento(
                "TEXT_MESSAGE_START",
                {"runId": run_id, "messageId": message_id, "role": "assistant"},
            )
            texto = respuesta.text
            tamano_chunk = 48
            for inicio in range(0, len(texto), tamano_chunk):
                yield _evento(
                    "TEXT_MESSAGE_CONTENT",
                    {
                        "runId": run_id,
                        "messageId": message_id,
                        "delta": texto[inicio : inicio + tamano_chunk],
                    },
                )
            yield _evento("TEXT_MESSAGE_END", {"runId": run_id, "messageId": message_id})
        elif tipo == "error":
            yield _evento("RUN_ERROR", {"runId": run_id, "message": str(payload)})

    yield _evento("RUN_FINISHED", {"runId": run_id, "threadId": run_id})


@app.post("/api/preguntar")
async def preguntar(cuerpo: PreguntaIn):
    if not cuerpo.question.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía.")
    return EventSourceResponse(
        _generate_events(cuerpo.question, agentic=cuerpo.agentic, naive=cuerpo.naive)
    )


@app.get("/api/preguntas")
async def preguntas() -> list[dict[str, str]]:
    return [
        {"nombre": v.name, "pregunta": v.question} for v in _cli._VERIFICATIONS
    ]


@app.get("/api/grafo/ultimo")
async def latest_graph() -> dict[str, Any]:
    return {
        "pregunta": _ULTIMO_GRAFO["pregunta"],
        "caminos": [_path_to_dict(c) for c in _ULTIMO_GRAFO["caminos"]],
    }


@app.get("/api/salud")
async def salud() -> dict[str, Any]:
    _asegurar_stack()
    settings = _ESTADO["settings"]
    falkor_ok = True
    falkor_error: str | None = None
    try:
        _ESTADO["stack"].graph_store.query("RETURN 1")
    except Exception as error:  # noqa: BLE001
        falkor_ok = False
        falkor_error = str(error)
    return {
        "modo": settings.mode,
        "falkor_ok": falkor_ok,
        "falkor_error": falkor_error,
        "falkor_host": settings.falkor_host,
        "falkor_port": settings.falkor_port,
    }


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Sirve el build de producción de Vue (`pnpm run build` en `web/ui`) desde
# el mismo proceso FastAPI: en Docker (`docker compose --profile web up`) un
# único contenedor expone la API y la UI en el mismo puerto, sin nginx de por
# medio. En dev (`pnpm run dev` en `web/ui`) esta carpeta no existe todavía,
# así que el mount no se registra y Vite sirve la UI aparte (con el proxy de
# `vite.config.js` apuntando a este backend).
_RUTA_DIST_UI = RUTA_WEB / "ui" / "dist"
if _RUTA_DIST_UI.exists():
    from fastapi.staticfiles import StaticFiles

    app.mount("/", StaticFiles(directory=_RUTA_DIST_UI, html=True), name="ui")
