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
| `python demo.py chat --agentic --actor-id <id> --session-id <id>` | REPL de un solo proceso (un único `Stack`/sesión para todas las preguntas) — necesario para demostrar en vivo la memoria de sesión (STM), que no sobrevive entre invocaciones sueltas de `query`. Ver "Memoria del agente" abajo. |
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

## Memoria del agente: pista, nunca evidencia (STM de sesión + LTM de hechos/preferencias)

Capítulo opt-in de la charla: el agente puede recordar entre turnos y entre
sesiones, pero la memoria **nunca** se convierte en evidencia citable — es
una pista más para el LLM, sujeta al mismo escrutinio que su propia prosa.
Vive hoy **solo en el camino agéntico** (`--agentic`); `agent/orchestrator.py`
(el pipeline fijo) todavía no la usa.

| Pieza | Dónde vive |
|---|---|
| Contrato (`MemoryHint`, `MemoryPort`) | [`src/second_brain/ports.py`](src/second_brain/ports.py) |
| Backend local, RAM (sin AWS) | [`src/second_brain/adapters/local/fake_memory_store.py`](src/second_brain/adapters/local/fake_memory_store.py) — `FakeMemoryStore` |
| Backend AWS real | [`src/second_brain/adapters/aws/agentcore_memory_store.py`](src/second_brain/adapters/aws/agentcore_memory_store.py) — `AgentCoreMemoryStore`, sobre el data plane `bedrock-agentcore` (`CreateEvent`/`RetrieveMemoryRecords`/`ListEvents`) |
| Fail-open + formateo del bloque de pistas + addendum de prompt | [`src/second_brain/agent/memory.py`](src/second_brain/agent/memory.py) |
| La tool `recall_memory` (tercera tool, junto a `search_documents`/`traverse_graph`) | [`src/second_brain/agent/strands_tools.py`](src/second_brain/agent/strands_tools.py) — `build_tools` |
| Traza (`herramienta.recordar_memoria`, `memoria.guardado`) | [`src/second_brain/agent/tool_trace_hook.py`](src/second_brain/agent/tool_trace_hook.py) / `demo.py::_print_memory_trace` |

**Las tres capas**, todas detrás de `MemoryPort.recall`/`.remember_turn`:

| Capa | Qué guarda | Backend local (`FakeMemoryStore`) | Backend AWS (`AgentCoreMemoryStore`) |
|---|---|---|---|
| STM de sesión | Los últimos turnos (pregunta+respuesta) de un `(actor_id, session_id)` | Lista en RAM del proceso | AgentCore Memory — `ListEvents`/`CreateEvent` sobre la sesión |
| LTM de hechos | Afirmaciones sembradas/recordadas por actor | `seed_hecho(actor_id, texto)` | Estrategia administrada `SEMANTIC`, namespace `second_brain/{actorId}/hechos` |
| LTM de preferencias | Preferencias de formato del actor (nunca hechos) | `seed_preferencia(actor_id, texto)` | Estrategia administrada `USER_PREFERENCE`, namespace `second_brain/{actorId}/preferencias` |

El recurso AgentCore Memory (`second_brain_memory`, declarado en
[`infra/stacks/agentcore_stack.py`](infra/stacks/agentcore_stack.py), STM con
expiración de 30 días) ya existe en la cuenta de la charla — este repo nunca
hardcodea su id: lo lee de `SECOND_BRAIN_AGENTCORE_MEMORY_ID` (ver
"Activación" abajo).

### La regla de diseño: memoria es pista, nunca evidencia

Nada que salga de `recall_memory` puede volverse una `Citation` ni contar
para el coverage gate: el tipo que lo transporta, `ports.MemoryHint`, nunca
entra a la lista `Evidence` que consumen `evaluate_coverage`/
`extract_citations`/`validate_citations`/`validate_relational_claims` —
`agent/strands_tools.py::EvidenceCollector` los mantiene en campos
separados (`items` vs. `memory_hints`) a propósito, así que mezclarlos no es
solo improbable, es estructuralmente imposible. Dos consecuencias,
verificadas con tests, no solo prometidas:

1. **Un turno sostenido SOLO por memoria sigue abstiniéndose.** Si el
   modelo llama `recall_memory`, no llama ninguna tool de evidencia real, y
   redacta igual citando el recuerdo como si fuera una fuente
   (`[source:memoria]`), `answer_agentic` fuerza la abstención
   (`Coverage.NO_EVIDENCE`) e ignora por completo lo que el modelo escribió
   — `test_memory_only_recall_never_becomes_evidence_and_still_abstains`
   en `tests/test_strands_agent_memory.py`.
2. **La memoria mentirosa: una afirmación relacional que viene de memoria
   pasa por el MISMO anclaje al grafo** (`agent.postprocess.apply_guards` →
   `validate_relational_claims`) que una alucinación del modelo — el guard
   no sabe ni le importa de dónde salió la prosa. Sembrás en
   `FakeMemoryStore` el hecho FALSO *"El equipo de Plataforma debe resolver
   la dependencia de billing-2-0 con auth-cache"* (el mismo puente
   inventado que ya alucina `--naive`, ver más arriba); el modelo lo
   recuerda, lo repite en su respuesta, y `validate_relational_claims` lo
   degrada igual que si lo hubiera inventado él solo — el grafo real solo
   respalda `billing-2-0 DEPENDE_DE auth-cache` e `Identidad RESPONSABLE_DE
   auth-cache`, nunca a Plataforma. Verificado con el texto final real de
   la respuesta en
   `test_relational_claim_sourced_from_memory_is_degraded_by_graph_anchoring`.

### Activación — tres capas a la vez, nunca por default

```bash
# .env.example / .env — aplica a los DOS modos (local y aws)
SECOND_BRAIN_MEMORY_ENABLED=false          # 1) el backend existe (FakeMemoryStore en local, AgentCore en aws)
SECOND_BRAIN_AGENTCORE_MEMORY_ID=          # 2) solo en modo aws — específico de cuenta, nunca lo hardcodees
SECOND_BRAIN_AGENTCORE_ACTOR_ID=demo-speaker
```

```bash
# CLI — 3) actor_id/session_id explícitos PARA ESE TURNO, y --agentic
python demo.py query --agentic --actor-id demo-speaker --session-id sesion-1 "..."
```

Sin `SECOND_BRAIN_MEMORY_ENABLED=true`, `stack.memory` es `None`. Sin
`--actor-id` **y** `--session-id` en ese `query`/`chat` puntual,
`recall_memory` ni se agrega a las tools del turno — el comportamiento es
byte a byte el de antes de que existiera memoria (verificado en
`test_memory_configured_but_without_session_id_behaves_like_memory_off` y
su par de `actor_id`). Y sin `--agentic`, la memoria nunca se consulta ni
se guarda: el pipeline fijo no la usa todavía.

### Probar en LOCAL, sin AWS — las 3 escenas son deterministas

Con el venv activado y `ingest` ya corrido (ver el Quickstart): las tres
escenas de memoria del guion de charla (Acto 4, ver
[`../GUION_ACTO4_MEMORIA.md`](../GUION_ACTO4_MEMORIA.md)) se graban HOY
100% en local, sin AWS. `demo.build_agentic_scripted_llm` decide llamar
`recall_memory` por su cuenta para `P_BILLING` (`_decide_billing_con_memoria`)
y para el seguimiento anafórico de `chat` (`P_M1_SEGUIMIENTO`, `_m1_seguimiento_rules`)
— pero SOLO cuando memoria está REALMENTE activa para el turno (las tres
capas de "Activación" de arriba); sin ellas, ni una regla nueva se agrega y
el guion de las 10 preguntas queda byte a byte el de siempre. Comandos y
trazas reales, ejecutados contra este repo:

**M1 — seguimiento anafórico (STM, dentro de la misma sesión de `chat`):**

```bash
export SECOND_BRAIN_MEMORY_ENABLED=true   # PowerShell: $env:SECOND_BRAIN_MEMORY_ENABLED = "true"
python demo.py chat --agentic --trace --actor-id demo-speaker-m1 --session-id m1-take1
› Si modifico la API de core-billing, ¿qué módulos se rompen?
› ¿y quién es el dueño?
› :salir
```

Traza real del turno 2 (recortada):

```
🧠 orquestador → pregunta simple detectada
🧠 memoria    → 1 recuerdo (STM sesión=1, LTM hechos=0, LTM preferencias=0)
🔍 buscador   → híbrida + RRF + rerank → 12 statements
🚪 gate       → SUFICIENTE
🔗 anclaje    → ✅ respaldada — Plataforma RESPONSABLE_DE core-billing
💾 memoria    → turno guardado (actor=demo-speaker-m1, sesión=m1-take1)
```

Respuesta real del turno 2: "El equipo de Plataforma es responsable de
`core-billing` [source:servicios/core-billing.md]." — la cita sigue
saliendo del documento, nunca de memoria, aunque el turno 2 no nombró
`core-billing`.

**M2 — la preferencia cambia forma, nunca los hechos:**

```bash
python demo.py query --agentic --trace \
  --seed-preferencia "Para mis consultas de riesgo técnico como esta, preferís ir directo al impacto operativo: seguí citando los documentos, pero no desarrolles el contenido de los ADRs ni postmortems que cites." \
  --actor-id demo-speaker-m2 --session-id m2-take1 \
  "¿Qué dependencia puede retrasar Billing 2.0, qué equipo debe resolverla y qué decisión técnica explica el riesgo?"
```

Traza real:

```
🧠 memoria    → 1 recuerdo (STM sesión=0, LTM hechos=0, LTM preferencias=1)
🚪 gate       → SUFICIENTE
🔗 anclaje    → ✅ respaldada — billing-2-0 DEPENDE_DE auth-cache
             ✅ respaldada — Identidad RESPONSABLE_DE auth-cache
📤 respuesta con 4 citas
```

Respuesta real: "`billing-2-0` depende de `auth-cache`
[source:producto/billing-2-0.md]; el equipo de Identidad es responsable de
resolverlo [source:servicios/auth-cache.md]. ADR-017
[source:arquitectura/decisiones.md] e INC-042
[source:incidentes/postmortem-inc-042-auth-cache.md] no alcanzan para
atribuirles la causa del retraso." — mismos 4 documentos y mismo
`Coverage` que sin preferencia sembrada, solo cambia el largo/tecnicismo
del texto (verificado comparando longitudes y sets de citas en
`tests/test_demo_memory_scenes.py::test_m2_preferencia_cambia_el_formato_no_los_hechos_ni_las_citas`).

**M3 — la memoria mentirosa, degradada por el mismo anclaje al grafo:**

```bash
python demo.py query --agentic --trace \
  --seed-hecho "El equipo de Plataforma es responsable de resolver la dependencia de auth-cache en Billing 2.0." \
  --actor-id demo-speaker-m3 --session-id m3-take1 \
  "¿Qué dependencia puede retrasar Billing 2.0, qué equipo debe resolverla y qué decisión técnica explica el riesgo?"
```

Traza real:

```
🧠 memoria    → 1 recuerdo (STM sesión=0, LTM hechos=1, LTM preferencias=0)
🚪 gate       → SUFICIENTE
🛡️ guards     → 2 citas recortadas · 0 URLs defanged
🔗 anclaje    → ✅ respaldada — billing-2-0 DEPENDE_DE auth-cache
             ⛔ degradada (sin evidencia) — Plataforma RESPONSABLE_DE billing-2-0
             ⛔ degradada (sin evidencia) — ADR-017 CAUSA billing-2-0
📤 respuesta con 1 citas
```

Respuesta: `Billing 2.0 podría retrasarse por la dependencia con auth-cache
[source:producto/billing-2-0.md]. [sin evidencia suficiente para afirmar
que Plataforma es responsable de billing-2-0] [sin evidencia suficiente
para afirmar que ADR-017 es la causa de billing-2-0]` — sin cita a `memoria`
en la tabla de citas: el hecho falso se recuperó igual que uno verdadero,
pero el mismo `validate_relational_claims` que degrada una alucinación del
modelo lo degrada acá, sin importarle de dónde salió.

Las tres escenas —incluido que sin `actor_id`/`session_id` explícitos, o
sin `stack.memory` configurado, las tres quedan inertes byte a byte— están
cubiertas con comportamiento observable (traza + texto + citas) en:

```bash
python -m pytest tests/test_demo_memory_scenes.py -v
```

7 tests, todos en verde, ejercitando `demo.build_agentic_scripted_llm` real
(no un `ScriptedLlm` armado a mano para el test).

El CABLEADO de memoria en sí (independiente del guion de la CLI) tiene su
propia suite, con un `ScriptedLlm` de test más granular:

```bash
python -m pytest tests/test_strands_agent_memory.py -v
```

6 tests, todos en verde: activación de la tool según las tres capas,
memoria-sola-nunca-evidencia, la degradación de la memoria mentirosa,
memoria apagada por falta de `actor_id`/`session_id` (idéntico a antes de
que existiera memoria), y `remember_turn` después del turno.
`python -m pytest tests/test_memory_stores.py -v` (13 tests más) cubre los
dos backends —`FakeMemoryStore` y `AgentCoreMemoryStore` contra un cliente
`boto3` falso— por separado, sin tocar AWS real.

Para la continuidad de sesión (STM) en un solo proceso —`FakeMemoryStore`
vive en RAM, así que dos invocaciones sueltas de `query` nunca comparten
memoria— usá `chat` (como en M1), que mantiene un único `Stack` y una
única sesión mientras dure el REPL.

**Docker**: `docker-compose.yml` todavía no pasa `SECOND_BRAIN_MEMORY_ENABLED`
a los servicios `demo`/`web` (su bloque `environment:` está fijo, sin
interpolar variables de `.env`); hasta que eso se cablee, la forma de
probar memoria en un contenedor puntual es `docker compose run --rm -e
SECOND_BRAIN_MEMORY_ENABLED=true demo python demo.py query --agentic ...`
(con `ingest` ya corrido en ese volumen) — y necesita una imagen
reconstruida (`docker compose build demo`) si tu build es anterior a este
cambio, porque `--actor-id`/`--session-id`/`--seed-hecho`/`--seed-preferencia`
son opciones nuevas de la CLI.

### Variante: las mismas 3 escenas contra AWS real

Las tres escenas de arriba ya son deterministas en local — esto es la
VARIANTE con un modelo real, para mostrar que la decisión de llamar
`recall_memory` no depende de un guion, y con el gotcha real que el modo
local no tiene (consistencia eventual, ver abajo).

```bash
# .env (ver "Pasar a AWS real" más abajo para el resto de las variables)
SECOND_BRAIN_MODE=aws
SECOND_BRAIN_MEMORY_ENABLED=true
SECOND_BRAIN_AGENTCORE_MEMORY_ID=<id del recurso ya desplegado — infra/stacks/agentcore_stack.py>
SECOND_BRAIN_AGENTCORE_ACTOR_ID=demo-speaker
```

```bash
set -a && source .env && set +a   # la CLI no carga .env sola — ver la nota de "Pasar a AWS real"
python demo.py chat --agentic --trace --actor-id demo-speaker --session-id sesion-charla
```

A diferencia del local, acá el LLM es un Bedrock real: decide POR SU CUENTA
cuándo llamar `recall_memory` (guiado por `MEMORY_PROMPT_ADDENDUM` en el
system prompt), así que cualquier pregunta con una referencia anafórica
("¿y quién es el dueño?", después de preguntar por un servicio) puede
disparar el recuerdo en vivo — no hace falta que sea una de las tres
escenas guionadas, a diferencia del modo local con `ScriptedLlm`. La
contrapartida (ver el gotcha de abajo): sembrar un hecho/preferencia en LTM
real depende de que Bedrock AgentCore lo EXTRAIGA de una conversación,
asíncrono y sin API de "insertar ahora" — nada parecido a `--seed-hecho`,
que en local escribe directo en `FakeMemoryStore`. El guion completo de
grabación contra AWS (calentamiento, verificación de que la extracción ya
prendió, un `actor_id` por escena) vive en
[`../GUION_ACTO4_MEMORIA.md`](../GUION_ACTO4_MEMORIA.md).

**Consistencia eventual.** Un `remember_turn` (`CreateEvent`) exitoso NO
garantiza que un `recall_memory` inmediatamente después —mismo turno, turno
siguiente en la misma sesión, o la extracción a LTM de hechos/preferencias—
ya lo vea: la escritura y la extracción son asíncronas del lado del
servicio. El turno queda guardado igual; no asumas que es recuperable al
instante. (`FakeMemoryStore` en modo local sí ve su propio escrito de
inmediato, porque es RAM del mismo proceso — la inconsistencia es una
propiedad del backend real, no algo que el puerto simule a propósito.)

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
   detalle y los costos en `infra/README.md`). Por default no se despliega
   grafo; para el deploy completo con FalkorDB también en AWS (una EC2
   chica, opt-in), sumá `-c enable_graph_ec2=true -c
   falkor_allowed_cidr=<tu-ip>/32` — ver "Grafo en AWS (opcional)" en
   `infra/README.md`.
2. Generar el `.env` a partir de los outputs del deploy, sin copiar nada a
   mano: `make aws-env` (o `python infra/despues-del-deploy.py`). Escribe
   `SECOND_BRAIN_MODE=aws` y las variables `SECOND_BRAIN_*` (bucket/índice de
   S3 Vectors, id/versión del guardrail de Bedrock) leídas por
   `src/second_brain/config.py`. El grafo sigue las mismas
   `SECOND_BRAIN_FALKOR_HOST`/`FALKOR_PORT`/`FALKOR_GRAPH_NAME` que el modo
   local (default `localhost`); si desplegaste el `GraphStack` opcional, el
   script escribe `SECOND_BRAIN_FALKOR_HOST` con la IP de esa EC2 solo.
3. Instalar el extra `[aws]` (`pip install -e .[aws]`, o la imagen Docker con
   `target: aws`) — trae `boto3`, ausente de la imagen local por diseño.
4. **Ingestar en AWS**: `python demo.py ingest` con el entorno del `.env`
   cargado. El índice de S3 Vectors nace VACÍO — el `cdk deploy` crea el
   índice, no lo llena. Sin este paso el modo `aws` no resuelve objetivos ni
   navega el grafo: responde solo con lo que encuentre la búsqueda léxica y
   el grounding del guardrail se desploma (0.56 medido, contra 0.92 con el
   índice poblado). Verificado el 31-ago-2026 contra Bedrock real.
5. Correr con `SECOND_BRAIN_MODE=aws make demo-aws` (el target exige la
   variable explícita — nunca dispara una llamada a AWS por accidente).

> ⚠️ **La CLI no carga `demo/.env` sola**: eso lo hace `docker compose`. Desde
> una terminal, `python demo.py ...` corre en modo LOCAL aunque el `.env` diga
> `aws`, sin avisar. Es deliberado (ninguna corrida llama a AWS por accidente),
> pero se confunde fácil en vivo. Cargalo explícito antes de los pasos 4 y 5:
>
> ```bash
> set -a && source .env && set +a    # bash/zsh — sin esto, corre en local
> python demo.py query --trace "Si modifico la API de core-billing, ¿qué módulos se rompen?"
> ```
>
> Cómo saber que estás en AWS de verdad: el trace muestra la línea
> `🧯 guardrail → grounding=… · relevance=…`, que en modo local no existe.

Al terminar: `cdk destroy --all` desde `infra/` limpia todo (ver la nota
sobre S3 Vectors no vacío en `infra/README.md`).

Todos los adapters de AWS importan `boto3` de forma perezosa (recién en su
primer método real, nunca en `__init__`): construir el `Stack` en modo `aws`
sin credenciales configuradas no falla hasta el primer uso real.

## Bedrock Knowledge Bases: el recuperador gestionado, al lado (opt-in)

El repo despliega —bajo `-c enable_knowledge_base=true`— una **Bedrock
Knowledge Base sobre el MISMO corpus**, en su propio índice de S3 Vectors.
No reemplaza el pipeline propio: entra como **un ranking más** de la fusión
RRF (`retrieval.retrieve`), junto al semántico y al léxico.

```bash
SECOND_BRAIN_KNOWLEDGE_BASE_ENABLED=true    # default: false
SECOND_BRAIN_BEDROCK_KB_ID=...              # lo escribe `make aws-env`
```

Apagada —el default— `retrieve` funde solo semántico + léxico y el
comportamiento es idéntico al de siempre. Sin las dos variables, la KB no se
cablea y no hay una sola llamada de red.

El `cdk deploy` crea la KB VACÍA y con el bucket de corpus vacío: llenarlos es
un paso aparte, igual que `demo.py ingest` del lado propio.

```bash
python infra/subir-corpus.py              # sube el corpus (excluye README.md)
python infra/ingestar-knowledge-base.py   # StartIngestionJob + espera
```

### Las dos ingestas tienen que cubrir el MISMO conjunto de documentos

`ingestion.load_corpus` excluye `corpus/README.md` (es contrato de diseño para
humanos, no contenido indexable). El data source de la KB **no puede excluir
archivos** —su `inclusionPrefixes` acepta un solo prefijo y el corpus tiene
nueve categorías en la raíz— así que la exclusión pasa antes, al subir:
`subir-corpus.py` aplica la misma regla y deja el README fuera del bucket.

No es cosmético. Medido contra la cuenta real (03-sep-2026), con el README
indexado por la KB:

| | KB apagada | KB prendida, README indexado | KB prendida, corpus alineado |
|---|---|---|---|
| P3 — "¿facturación del Q4 2025?" | `SIN_EVIDENCIA` ✅ | **`SUFICIENTE`** ❌ | `SIN_EVIDENCIA` ✅ |
| `demo.py check` (AWS, Nova Pro) | 9–10/20 | 6/20 | **9/20** |

Ese README puntúa **0.82** para una pregunta de facturación —habla de servicios
de facturación, sin un solo dato de Q4—, supera el umbral del coverage gate y
el sistema deja de abstenerse. Alineados los dos caminos, la paridad vuelve.

**La lección para la charla:** sumar un recuperador gestionado sobre "el mismo"
corpus solo es honesto si de verdad es el mismo conjunto de documentos. Dos
ingestas con contratos distintos no se comparan — una le puede costar a la otra
su garantía más fuerte. Queda fijado en `tests/test_knowledge_base.py`.

### Sobre `HYBRID`

Sobre S3 Vectors la KB **solo hace búsqueda semántica**: pedirle
`overrideSearchType=HYBRID` devuelve `ValidationException`. El híbrido
gestionado exige OpenSearch Serverless. Por eso la KB SUMA un ranking en vez de
reemplazar el pipeline: sustituirlo perdería el BM25.

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
  infra/                  # CDK (Python): 5 stacks (grafo opcional), `cdk deploy --all` (ver infra/README.md)
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
