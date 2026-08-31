# Second Brain GraphRAG — demo local

Demo dockerizada, 100% reproducible, de un agente GraphRAG con arquitectura
de puertos: el mismo código corre contra adapters 100% locales (sin AWS, sin
credenciales) o contra Bedrock/S3 Vectors en AWS real (con FalkorDB como
motor único de grafo en los dos casos), sin cambiar una línea de dominio.
Todo el contenido es de la empresa ficticia **Nexora Corp** — no hay
referencias a sistemas, equipos ni cuentas reales.

## Quickstart — todo con Docker (el camino principal)

Esta demo se levanta ENTERA con Docker: FalkorDB, la ingesta, la UI web, el
servidor A2A de la demo de cierre y el servidor MCP corren como servicios de
`docker-compose.yml`. Los scripts auxiliares son `.sh` (POSIX — Git Bash en
Windows, Linux o macOS), no PowerShell.

**Paso 0 — una sola vez, ANTES de viajar al venue** (el build tarda **más de
9 minutos**: instala llama-index, scikit-learn y spacy para el GraphRAG
Toolkit real de AWS Labs — no lo hagas con la red del lugar de la charla):

```bash
docker compose build           # o: make build (construye TODAS las imágenes, incluidas a2a/mcp)
```

**El día de la charla — un solo comando**, sin reconstruir nada:

```bash
scripts/start-demo.sh          # o: make start
```

Levanta FalkorDB + ingesta + la UI web y te deja la URL lista:
**http://localhost:8000**. Si falta Docker, si Docker no está corriendo, o
si el paso 0 nunca corrió, el script corta con un mensaje claro (nunca un
stacktrace) diciendo exactamente qué falta y qué comando correr.

Para arrancar de cero, borrando la ingesta y el grafo previos:

```bash
docker compose down -v && scripts/start-demo.sh
```

Los otros dos scripts de `scripts/` cubren el resto de la demo, también
100% en Docker — ver la sección "MCP ≠ A2A" más abajo para el detalle de
cada uno:

```bash
scripts/run-a2a-demo.sh    # la demo de cierre: servidor A2A + "agente de soporte"
scripts/run-mcp-server.sh  # el second brain como servidor MCP (streamable-http)
```

Equivalente mínimo sin script, en 3 comandos (lo que hace `docker compose
up`/`ingest`/`query` por dentro, para quien prefiera los comandos sueltos):

```bash
docker compose up -d --build                                          # levanta FalkorDB + arma el contenedor (auto-ingesta al arrancar)
docker compose run --rm demo python demo.py check                      # corre las 5 preguntas y valida el comportamiento esperado
docker compose run --rm demo python demo.py query --trace "¿Quién lidera el Proyecto Beta?"   # una pregunta con el pipeline paso a paso
```

Si además tenés `make` (Linux/macOS, o Git Bash con `make` instalado), estos
atajos corren la demo guiada completa por CLI (las 5 preguntas con
`--trace`, pausando entre cada una) — `make.ps1` sigue existiendo para
PowerShell nativo en Windows, pero dejó de ser el camino recomendado:

```bash
make ingest   # (re)ingesta el corpus — idempotente, barra de progreso
make demo     # las 5 preguntas con --trace, pausando entre cada una
```

Sin Docker (venv local — `python -m venv .venv` activado, luego
`pip install -e .[dev]` — y un FalkorDB corriendo en `localhost:6379`,
por ejemplo `docker compose up -d falkordb` del propio `docker-compose.yml`):

```bash
python demo.py ingest
python demo.py query --trace "¿Quién lidera el Proyecto Beta?"
```

## UI web para presentar en vivo (grabación / pantalla grande)

Además de la CLI, `demo/web/` trae una interfaz web (Vue 3 + FastAPI) pensada
para mostrar la demo en una charla y grabarla: barra de preguntas del guion
(un clic las dispara), respuesta en streaming con citas clicables, panel de
traza en vivo del pipeline (el mismo `--trace` de la CLI, pero apareciendo
paso a paso mientras corre) y visualización del subgrafo recorrido con el
sentido correcto de cada relación. Cuando el gate abstiene, la UI marca en
rojo que **el LLM nunca fue invocado** — el momento clave de la charla.

La CLI sigue siendo la fuente de verdad del guion: la UI lee las preguntas y
sus respuestas esperadas de `demo._VERIFICACIONES` (las mismas 5 que corre
`python demo.py check`), nunca las duplica a mano.

### Levantar la UI con Docker (recomendado para grabar)

```bash
scripts/start-demo.sh   # o: make start / make web / docker compose up -d falkordb web
```

Deja todo accesible en **http://localhost:8000** (FalkorDB arriba, corpus
ingestado, API + UI servidas por el mismo proceso FastAPI). `scripts/start-demo.sh`
es el comando pensado para el día de la charla (ver el Quickstart, arriba):
espera a que la UI esté sana antes de imprimir la URL y falla con un mensaje
claro si Docker no está corriendo o si la imagen no se construyó antes.
Equivalente en PowerShell (sin los checks del script): `.\make.ps1 web`.

### Levantar la UI en modo desarrollo (hot-reload)

Requiere un FalkorDB corriendo (`docker compose up -d falkordb`) y el venv
local con el extra `web` instalado (`pip install -e .[web]`):

```bash
make web-dev-api      # terminal 1: FastAPI (uvicorn --reload) en :8000
make web-dev-ui       # terminal 2: Vite dev server en :5173 (proxy a :8000)
```

Abrí `http://localhost:5173`. En Windows nativo: `.\make.ps1 web-dev-api` /
`.\make.ps1 web-dev-ui` (dos terminales PowerShell).

### Protocolo AG-UI

`demo/web/api.py` expone `POST /api/preguntar` como un stream de eventos
[AG-UI](https://ag-ui.com) por Server-Sent Events (`RUN_STARTED`,
`TOOL_CALL_START/ARGS/END` para cada herramienta del pipeline, `STATE_DELTA`
para el resto de las etapas, `TEXT_MESSAGE_START/CONTENT/END` para la
respuesta final, `RUN_FINISHED`/`RUN_ERROR` al cerrar) — el mapeo completo
está documentado en el docstring del módulo. El pipeline (`agente.orquestador.responder`)
sigue siendo síncrono y fijo: no se reescribió a async, solo se le agregó un
hook opcional (`on_paso`, sin efecto si no se pasa) para observar cada
`PasoTraza` a medida que se produce.

## Las 5 preguntas de la demo

| # | Pregunta | Qué demuestra | Patrón de la charla |
|---|---|---|---|
| P1 | ¿Quién lidera el Proyecto Beta? | RAG simple: recupera la frase directa y cita la fuente, sin traversal. | baseline |
| P2 | Si modifico la API de core-billing, ¿qué módulos se rompen? | Traversal multi-hop (`--trace` muestra el `[*1..3]` de openCypher): 3 consumidores repartidos en 1 y 2 saltos. | Patrón 2 — grafo de dependencias |
| P3 | ¿Cuál fue la facturación del Q4 2025? | El coverage gate detecta ausencia de evidencia ANTES de invocar el LLM: abstención honesta con 0 tokens de generación. | coverage gate |
| P4 | ¿Quién es la CTO y cuánto gana? | Respuesta parcial honesta: identifica a la CTO con cita y declara explícitamente el vacío de datos de nómina, sin inventar una cifra. | honestidad |
| P5 | ¿Por qué el frontend de reportes no emite eventos de Amplitude? | Anclaje al sujeto: el corpus tienta al modelo a pivotear hacia los sujetos con más evidencia (`dashboard`, `onboarding`); la síntesis abre igual con el sujeto preguntado y marca la comparación. | Patrón 3 — anclaje al sujeto ⭐ |

El contrato completo (qué documento sostiene cada respuesta, qué se verificó
por `grep` para garantizarlo) vive en [`corpus/README.md`](corpus/README.md).
`python demo.py check` corre las 5 y valida el comportamiento esperado de
cada una — es el smoke test para correr antes de subir al escenario.

## Los 3 patrones con nombre de la charla, en el código

| Patrón | Dónde vive | Qué pregunta lo demuestra |
|---|---|---|
| Retrieve-then-rerank para entidades | [`src/second_brain/retrieval.py`](src/second_brain/retrieval.py) — función `resolver_objetivos` | la ambigüedad detrás de P5 (`"reportes"` matchea dos documentos; el rerank arbitra) |
| Subject-anchored synthesis (anclaje al sujeto) | [`src/second_brain/agente/sintesis.py`](src/second_brain/agente/sintesis.py) — `SYSTEM_SINTESIS` + `construir_mensaje_usuario` | P5 — la trampa del drift |
| Defensa en profundidad con kill-switch por capa | [`src/second_brain/agente/gate.py`](src/second_brain/agente/gate.py) (capa de entrada, antes del LLM) + [`src/second_brain/agente/guards.py`](src/second_brain/agente/guards.py) (capas de salida, después) | P3 — el coverage gate ahorra el LLM entero; todas — `validar_citas`/`guard_urls` recortan lo no evidenciado |

Cada uno de los tres módulos de arriba nombra el patrón en la primera línea
de su docstring — es la forma de que alguien navegando el repo desde la
charla los encuentre sin tener que adivinar en qué archivo quedaron.

## GraphRAG Toolkit de AWS Labs — de verdad, no reimplementado

El grafo léxico de tres niveles que arma `graph/build.py` corre sobre el
mismo motor de conexión que usa el GraphRAG Toolkit real
(`graphrag-lexical-graph==3.19.1` + su contrib de FalkorDB): ver
[`src/second_brain/adapters/graphrag_toolkit.py`](src/second_brain/adapters/graphrag_toolkit.py),
el único módulo del paquete que importa el toolkit. `FalkorGraphStore` pide
su conexión a `GraphStoreFactory.for_graph_store("falkordb://...")` —
`FalkorGraphStore` es el único adapter de `GraphStorePort` del proyecto, en
los dos modos (`local` y `aws`; ver `config.py::_stack_aws`), así que este es
el único factory que este repo cablea — y solo cae al cliente `falkordb`
directo si el toolkit no está instalado, no pudo conectar, o el nombre del
grafo no es alfanumérico (una validación real del contrib, no inventada acá).

La extracción de entidades/relaciones (`graph/extraction.py`) sigue siendo
el extractor propio por patrones en modo local — es la parte que necesita
un LLM generativo, y el ensayo local es 100% offline a propósito. `build_graph`
puede además correr, de forma aditiva y en un namespace separado,
`LexicalGraphIndex.extract_and_build` real del toolkit
(`use_real_toolkit=True`, pensado para modo AWS con un LLM Bedrock real vía
`BedrockLlm`): no reemplaza ni mezcla el grafo `Entidad`/`RELACION` que
responde las preguntas de la demo — adoptar esas relaciones ahí es una
decisión que queda para revisión manual, no algo que este adapter decida
solo. Ver el docstring de `attempt_toolkit_extraction` para el detalle.

Instalación (no entra en `pip install -e ".[dev]"`, que se mantiene limpio y
sin red; el `Dockerfile` ya la hace en la capa `base`):

```bash
pip install -e ".[graphrag]"                       # graphrag-lexical-graph, PyPI real
pip install hatchling hatch-requirements-txt        # build deps del contrib, no se resuelven solos
pip install --no-build-isolation \
  "git+https://github.com/awslabs/graphrag-toolkit.git@218bf37382412cd1ff72d8a5f64755c012976bb4#subdirectory=lexical-graph-contrib/falkordb"
```

## Comandos de la CLI

| Comando | Qué hace |
|---|---|
| `python demo.py ingest` | Carga el corpus, indexa vectores y construye el grafo. Idempotente. |
| `python demo.py query "<pregunta>"` | Responde con sus citas, por el pipeline fijo (`agent.orchestrator.answer`). |
| `python demo.py query --agentic "<pregunta>"` | Igual, pero por el loop agéntico: un `Agent` de Strands decide cuándo llamar a las tools (ver la sección de abajo). |
| `python demo.py query --trace "<pregunta>"` | Muestra el pipeline paso a paso (orquestador → buscador → navegador → gate → guards → respuesta). Combina con `--agentic`. |
| `python demo.py graph-top` | Top entidades del grafo por conexiones — el cierre de la demo, señala el hub. |
| `python demo.py check` | Corre las 10 preguntas del guion en LOS DOS caminos (fijo y agéntico) y valida verde/rojo el comportamiento esperado de cada una — 20 verificaciones en total. |
| `python demo.py mcp-server` | El second brain como servidor MCP (sus tools, para otros agentes). Ver la sección de abajo. |
| `python demo.py a2a-server` | El second brain como servidor A2A (su agente completo, para otros agentes). Primer proceso de la demo de cierre. |
| `python demo.py a2a-client "<pregunta>"` | El "agente de soporte": descubre al second brain por A2A y le pregunta. Segundo proceso de la demo de cierre. |

## Loop agéntico real (Strands) vs. pipeline fijo

El abstract de la charla promete "Strands Agents para el loop agéntico".
`agent/orchestrator.py` (el pipeline original) es un orden FIJO de pasos —
nunca fue un loop agéntico. `agent/strands_agent.py::answer_agentic` sí lo
es: un `Agent` de la librería `strands-agents` decide, turno a turno, si
llama a `search_documents`, a `traverse_graph`, a las dos, o a ninguna —
las tools están en `agent/strands_tools.py`, decoradas con `@tool`. Los
dos caminos conviven bajo bandera (`--agentic` en la CLI, `agentic` en
`POST /api/preguntar`) para poder compararlos en vivo; `demo.py check`
verifica los dos.

**El coverage gate, reenganchado como hook.** En el pipeline fijo, el gate
corre ANTES de la única llamada al LLM y puede ahorrarla del todo
(`Coverage.NO_EVIDENCE` → 0 llamadas). En un loop agéntico eso ya no es
posible: el modelo decide cuándo buscar, así que la primera llamada
(la que decide llamar a una tool) ya pasó cuando hay evidencia para
evaluar. La solución — verificada con contadores reales, no estimados
(`agent/gate_hook.py::CoverageGateHook`, sobre `AfterToolsEvent` de
Strands) — corta el turno DESPUÉS de que las tools devuelven evidencia y
ANTES de que el modelo redacte:

- **Con evidencia: 2 llamadas al modelo** (decidir la tool + redactar).
- **Sin evidencia: 1 llamada** (decidir buscar) — el gate corta con
  `event.end_turn`, el modelo NUNCA redacta.

Medido corriendo las 10 preguntas del guion contra el loop agéntico real:
las 9 con evidencia hacen exactamente 2 llamadas; P3 (sin evidencia) hace
exactamente 1. El número que hay que decir en el escenario ya no es "cero
llamadas al LLM" — es **"una llamada de decisión, cero de redacción"**.

Un modelo que se saltee las tools por completo (redacte directo en su
primera respuesta) no dispara `AfterToolsEvent` — el hook no tiene nada
que cortar. `answer_agentic` cierra ese hueco con una verificación
posterior determinista: si no hubo evidencia real recolectada, la
respuesta se reemplaza por la misma abstención, sin importar qué haya
escrito el modelo (ver el docstring de `agent/strands_agent.py`).

Los guards de salida (`validate_citations`, `validate_relational_claims`
— el anclaje al grafo, `🔗 anclaje` en `--trace` — y `guard_urls`) viven
en `agent/postprocess.py` y corren IDÉNTICOS en los dos caminos: la
garantía anti-alucinación no depende de quién decidió qué evidencia
recolectar.

**Observabilidad: dos trazas que coexisten.** La traza propia
(`TraceStep`) sigue alimentando `--trace` y la UI web (eventos AG-UI por
SSE) con el mismo vocabulario de etapas en los dos caminos
(`herramienta.*`, `gate.*`, `guards.*`, `canario`...) — el mapeo de
`web/api.py` no distingue cuál lo generó. Además, Strands emite trazas
OpenTelemetry nativas para el loop agéntico; se configuran con variables
de entorno (`SECOND_BRAIN_OTEL_ENABLED`, `SECOND_BRAIN_OTEL_CONSOLE`,
`OTEL_EXPORTER_OTLP_ENDPOINT` — ver `.env.example` y
`agent/observability.py`) sin tocar una línea de `TraceStep`: la primera es
la vista pensada para la demo, la segunda es la vista operativa que un
backend real (CloudWatch GenAI Observability, Jaeger, cualquier collector
OTLP) consumiría en producción. Apagada por default — cero costo si no se
usa.

## MCP ≠ A2A — el second brain como herramienta y como agente (el cierre de la charla)

**MCP conecta un agente con SUS herramientas. A2A conecta agentes ENTRE
SÍ.** Hasta acá esa frase era una diapositiva conceptual; estos dos
paquetes la vuelven código que corre:

| | `src/second_brain/mcp/` | `src/second_brain/a2a/` |
|---|---|---|
| Qué expone | Las dos manos sueltas (`search_documents`, `traverse_graph`) | El agente completo (loop, coverage gate, guards) |
| Quién decide | El cliente MCP (elige qué tool llamar y con qué argumentos) | Nadie más que el second brain — el llamador solo ve pregunta → respuesta |
| Protocolo | [MCP](https://modelcontextprotocol.io/) — `tools/list` + `tools/call` | [A2A](https://a2aproject.github.io/A2A/latest/) — Agent Card + tareas JSON-RPC/streaming |
| Qué recibe el llamador | Evidencia cruda (`doc_id`, texto, score) — nunca prosa redactada | Una respuesta ya redactada, **con sus citas y degradaciones intactas** |

Ningún módulo de un paquete importa nada del otro: son dos superficies de
exposición independientes sobre el mismo dominio (`agent.tools`,
`config.Stack`) — abrir cualquiera de las dos carpetas alcanza para ver la
distinción sin que nadie la explique.

### Servidor MCP — el second brain como herramienta

**En Docker** (perfil `mcp`, `streamable-http`, puerto 8765 — para un
cliente MCP que hable HTTP contra un contenedor):

```bash
scripts/run-mcp-server.sh      # o: docker compose --profile mcp up -d mcp-server
```

Corre su propia ingesta antes de servir (comparte el volumen `demo-data`
con `demo`/`web`: ve la misma ingesta, no una vacía) y espera a que
FalkorDB esté sano. Queda escuchando en **http://localhost:8765/mcp**. Un
round-trip real contra ese endpoint: `tools/list` + `tools/call` con el SDK
`mcp` (`mcp.client.streamable_http.streamablehttp_client`) o cualquier
cliente que hable `streamable-http`.

**Local, sin Docker** (el transporte que espera un cliente MCP de
escritorio, como Claude Code — lanza el proceso él mismo y le habla por su
stdin/stdout; no tiene sentido detrás de un contenedor de compose):

```bash
python demo.py mcp-server                    # stdio (default)
python demo.py mcp-server --transport streamable-http --port 8765   # HTTP, para pegarle desde otro proceso local
```

Requiere `ingest` corrido antes (lee el mismo vector store y grafo que
`query`). No necesita ningún extra nuevo: el paquete `mcp` ya llega
transitivo de `strands-agents` (dependencia base) — por eso el servicio
Docker reusa la imagen `runtime` (`second-brain-demo:local`, la misma que
`demo`), sin una imagen aparte.

**Conectar Claude Code como cliente MCP real** — SIEMPRE por `stdio` local
(no contra el servicio Docker, que habla `streamable-http`) — bloque listo
para copiar en `.mcp.json` (o el equivalente de tu cliente MCP):

```json
{
  "mcpServers": {
    "second-brain-nexora": {
      "command": "C:\\ruta\\a\\demo\\.venv312\\Scripts\\python.exe",
      "args": ["demo.py", "mcp-server"],
      "cwd": "C:\\ruta\\a\\demo"
    }
  }
}
```

(en Linux/macOS, `command` es el `python` del venv activado —
`.venv/bin/python` — y `cwd` la carpeta `demo/`). Una vez conectado,
`search_documents`/`traverse_graph` aparecen como tools de Claude Code:
podés pedirle "buscá en el second brain de Nexora qué depende de
core-billing" y Claude decide por su cuenta cuándo y cómo llamarlas —
exactamente la mitad "MCP" de la distinción.

Verificado con un round-trip real (`tools/list` + dos `tools/call`, proceso
`stdio` separado, no en memoria) — ver el reporte de la tarea que agregó
este servidor para la transcripción completa; el spike original lo había
marcado como NO VERIFICADO.

**Camino gestionado equivalente**: AgentCore Gateway con un target
`mcpServer` apuntando a este mismo servidor corriendo persistente en AWS —
ya está declarado como alternativa documentada en
`infra/stacks/agentcore_stack.py` (sección "Gateway — por qué Lambda y no
OpenAPI/Smithy/mcpServer/apiGateway"); no se despliega desde este repo.

### Servidor + cliente A2A — el second brain como agente

**En Docker** (perfil `a2a` — DOS contenedores reales, `a2a-server` y
`a2a-client`, resolviéndose por nombre de servicio de compose):

```bash
scripts/run-a2a-demo.sh        # o: make a2a-demo
```

**Local, sin Docker** (dos procesos, cada uno en su terminal — requiere el
extra `[a2a]` instalado, `pip install -e ".[a2a]"`, y `ingest` corrido
antes):

```bash
python demo.py a2a-server                     # primer proceso: Agent Card + loop agéntico completo
python demo.py a2a-client "<pregunta>"        # segundo proceso: el "agente de soporte"
```

`a2a-server` NO envuelve un `strands.Agent` crudo con
`strands.multiagent.a2a.A2AServer` — envuelve `answer_agentic` completo
(`second_brain.a2a.server.SecondBrainA2AExecutor`), para que las citas y
las degradaciones del anclaje al grafo (`agent.guards`) viajen en la
respuesta final, no el texto sin guardar que el `Agent` interno redactó.
El progreso de cada turno (qué tool corrió, qué dijo el coverage gate, qué
guard degradó qué afirmación) se transmite en vivo como actualizaciones de
estado A2A — nunca tokens crudos del LLM, la misma distinción que hace la
charla entre "mostrar streaming" y "mostrar generación token a token".

`--host`/`--port` de `a2a-server` son la dirección de BIND (`0.0.0.0` en
Docker, para que el puerto publicado sea alcanzable desde fuera del
contenedor); la Agent Card necesita además `--public-url` (o la env var
`SECOND_BRAIN_A2A_PUBLIC_URL`) con la dirección REALMENTE alcanzable por
otros agentes — el nombre del servicio de compose (`http://a2a-server:9500/`),
nunca `0.0.0.0`. Sin `--public-url`, la Agent Card anuncia `0.0.0.0` como
`url` y `a2a-client` revienta con `ConnectError` al intentar conectarse ahí
después de descubrirla (verificado con un round-trip real) — ver el
docstring de `second_brain.a2a.server.build_a2a_app` para el detalle.

### La demo de cierre, en un solo comando

```bash
scripts/run-a2a-demo.sh   # o: make a2a-demo — Docker, el camino recomendado
```
```powershell
.\make.ps1 a2a-demo       # PowerShell nativo, DOS procesos locales sin Docker
```

Levanta el servidor A2A, espera a que su Agent Card responda, y corre el
"agente de soporte" contra él — el servicio `a2a-server` queda arriba
después (para Q&A en vivo o para repreguntar) hasta `docker compose stop
a2a-server` / `docker compose down`. El equivalente PowerShell corre los
DOS procesos como procesos de sistema operativo locales (sin Docker),
requiere el extra `[a2a]` instalado (`pip install -e ".[a2a]"`) y `ingest`
corrido antes.

## La arquitectura de puertos, en 10 líneas

`second_brain.ports` define los contratos (`EmbeddingsPort`, `VectorStorePort`,
`GraphStorePort`, `RerankPort`, `LlmPort`) como `Protocol` — no hay una clase
base que heredar, un adapter cumple el puerto por tener la forma correcta.
`second_brain.config.build_stack(settings)` es la ÚNICA función que decide,
según `SECOND_BRAIN_MODE`, si arma un `Stack` con adapters locales
(`FakeEmbeddings` + `MemoryVectorStore` + `FalkorGraphStore` + `FakeRerank`)
o con adapters de AWS (`BedrockEmbeddings` + `S3VectorsStore` +
`FalkorGraphStore` + `BedrockRerank` + `BedrockLlm`) — el grafo usa el mismo
adapter en los dos modos, apuntado por variable de entorno. Todo el resto del
paquete (ingesta, retrieval híbrido, traversal de grafo, el agente con su
coverage gate y sus guards) programa exclusivamente contra `second_brain.ports`
y nunca importa un adapter concreto ni sabe en qué modo está corriendo. Por
eso `demo.py` es la misma CLI para el ensayo local y para la charla en vivo
contra AWS: solo cambia una variable de entorno.

## Pasar a AWS real

1. Aprovisionar la infra con el CDK de [`infra/`](infra/README.md):
   `cdk bootstrap` + `cdk deploy --all` (4 stacks: storage, agente,
   observabilidad y, opcional bajo `enable_agentcore`, AgentCore — ver el
   detalle y los costos en `infra/README.md`). No hay stack de grafo: no se
   despliega ningún FalkorDB gestionado.
2. Generar el `.env` a partir de los outputs del deploy, sin copiar nada a
   mano: `make aws-env` (o `python infra/despues-del-deploy.py`). Escribe
   `SECOND_BRAIN_MODE=aws` y las variables `SECOND_BRAIN_*` (bucket/índice de
   S3 Vectors, id/versión del guardrail de Bedrock) leídas por
   `src/second_brain/config.py`. El grafo NO sale de un output de CDK: sigue
   las mismas `SECOND_BRAIN_FALKOR_HOST`/`FALKOR_PORT`/`FALKOR_GRAPH_NAME`
   que el modo local (default `localhost`) — completalas a mano si el grafo
   va a vivir en otro host.
3. Instalar el extra `[aws]` (`pip install -e .[aws]`, o la imagen Docker con
   `target: aws`) — trae `boto3`, ausente de la imagen local por diseño.
4. Correr con `SECOND_BRAIN_MODE=aws make demo-aws` (el target exige la
   variable explícita — nunca dispara una llamada a AWS por accidente).

Al terminar: `cdk destroy --all` desde `infra/` limpia todo (ver la nota
sobre S3 Vectors no vacío en `infra/README.md`).

Todos los adapters de AWS importan `boto3` de forma perezosa (recién en su
primer método real, nunca en `__init__`): construir el `Stack` en modo `aws`
sin credenciales configuradas no falla hasta el primer uso real.

## Costos (referencia del plan de la charla)

| Concepto | Costo |
|---|---|
| S3 Vectors + Knowledge Base (corpus mínimo) | ~$1 |
| Bedrock (ingesta + ensayos + charla) | ~$5–10 |
| FalkorDB local (Docker, para todo el ensayo sin AWS) | $0 |
| **Total del proyecto de demo** | **< $15** |

El modo local de este repo (el que corre `docker compose up`) es exactamente
el "FalkorDB local" de la fila de $0: todo lo que se ve en un ensayo o en la
sala de la charla puede correr sin tocar una cuenta de AWS.

## Estructura

```
demo/
  demo.py                 # la CLI (typer + rich)
  corpus/                 # el corpus sintético de Nexora Corp (ver su README)
  src/second_brain/       # dominio + puertos + adapters locales/AWS
    mcp/server.py          # el second brain como HERRAMIENTA MCP
    a2a/server.py          # el second brain como AGENTE A2A
    a2a/support_agent.py   # el "agente de soporte" (cliente A2A, demo de cierre)
  web/
    api.py                # backend FastAPI: pipeline -> eventos AG-UI por SSE
    ui/                   # frontend Vue 3 + Vite (preguntas, traza, grafo)
  infra/                  # CDK (Python): 4 stacks, `cdk deploy --all` (ver infra/README.md)
  tests/                  # pytest, incluye un test marcado `docker`
  Dockerfile              # multi-stage: base / runtime / test / aws / web / ui-build
  docker-compose.yml       # falkordb + demo + test (profile) + demo-aws (profile) + web (profile)
  Makefile / make.ps1     # atajos (bash / PowerShell)
  .github/workflows/ci.yml
```

## Tests y lint

```bash
make test     # pytest completo (incluidos los tests `docker`) dentro del contenedor
make lint     # ruff sobre src/, tests/ y demo.py
```

Equivalente sin `make` (los mismos dos targets, en Docker directo):

```bash
docker compose --profile test run --rm test
docker compose --profile test run --rm test python -m ruff check src tests demo.py
```

El workflow de CI (`.github/workflows/ci.yml`) corre exactamente lo mismo en
GitHub Actions, con FalkorDB como *service container* — es la prueba de que
la demo corre en cualquier lado, no solo en la máquina del speaker.

## Licencia

[MIT](../LICENSE) — sin dependencias de código de terceros más allá de los
paquetes de PyPI declarados en `pyproject.toml` (cada uno con su propia
licencia, gestionada por `pip`, no vendorizada en este repo).
