## Why

Hoy el second brain responde cada pregunta como si fuera la primera vez que
alguien le habla: no hay sesión (`demo.py query` es un proceso de un solo
turno), no hay preferencias de usuario, y no hay memoria de hechos entre
conversaciones. El recurso AgentCore Memory `second_brain_memory` ya está
desplegado en la cuenta (`infra/stacks/agentcore_stack.py`, STM de 30 días +
dos `ManagedMemoryStrategy`: `SEMANTIC` en `second_brain/{actorId}/hechos` y
`USER_PREFERENCE` en `second_brain/{actorId}/preferencias`) pero **cero
código lo consume** — `ListActors` devuelve vacío.

La charla necesita mostrar en vivo la distinción que la separa de un GraphRAG
ingenuo: **la memoria acelera y personaliza, pero nunca reemplaza a la
evidencia citable**. Sin esta pieza, la charla no puede mostrar (a) que el
agente resuelve una referencia anafórica entre turnos ("¿y quién es el
dueño?"), (b) que una preferencia de usuario cambia el FORMATO de la
respuesta sin tocar los hechos, ni (c) el caso más importante para la tesis:
un hecho falso sembrado en memoria se recupera igual que uno verdadero, pero
el anclaje al grafo (`agent.guards.validate_relational_claims`) lo degrada
exactamente como degradaría una alucinación del modelo — porque esa capa ya
es ciega al origen de la afirmación, solo mira si el grafo la respalda.

Este cambio agrega esa pieza sin tocar ninguna garantía existente: el
coverage gate (`agent.gate.evaluate_coverage`), los guards de salida
(`agent.guards`) y las 116 pruebas verdes actuales quedan intactos byte a
byte cuando la memoria está apagada (default).

## What Changes

- **Puerto nuevo `MemoryPort`** en `src/second_brain/ports.py`, con su forma
  de datos `MemoryHint` (`text`, `kind` ∈ `{"sesion", "hecho",
  "preferencia"}`, `namespace`, `score`) — mismo estilo `Protocol` que
  `EmbeddingsPort`/`GraphStorePort`, para que `agent.orchestrator` (el
  camino fijo, que hoy no importa nada de `strands`) pueda consumir memoria
  sin acoplarse a `strands.memory.*`.
- **`Settings`/`Stack`/`build_stack`** (`config.py`): dos variables de
  entorno nuevas con default inerte (`SECOND_BRAIN_MEMORY_ENABLED=false`,
  `SECOND_BRAIN_AGENTCORE_MEMORY_ID=` vacío) más un actor id de demo
  (`SECOND_BRAIN_AGENTCORE_ACTOR_ID`); `Stack` gana un campo opcional
  `memory: MemoryPort | None = None` (con default, no rompe ningún
  constructor `Stack(...)` existente — todos usan kwargs).
- **Dos adapters nuevos**: `adapters/local/fake_memory_store.py`
  (`FakeMemoryStore`, en RAM, seedable para demostrar los 3 escenarios sin
  AWS) y `adapters/aws/agentcore_memory_store.py` (`AgentCoreMemoryStore`,
  boto3 `bedrock-agentcore` data plane: `CreateEvent` para escribir STM,
  `RetrieveMemoryRecords` para leer las dos estrategias LTM, `ListEvents`
  para leer la ventana de sesión — operaciones y forma de parámetros
  verificadas por introspección real del service model, ver `design.md`).
- **`agent/memory.py` (nuevo)**: las funciones fail-open compartidas por los
  dos caminos — `recall_memory_fail_open`, `remember_turn_fail_open`,
  `format_memory_hints` — mismo patrón que
  `orchestrator._traverse_graph_fail_open`.
- **Camino fijo** (`agent/orchestrator.py`): recall determinista de memoria
  ANTES de `resolve_targets` (para poder resolver la anáfora), bloque de
  pistas pasado a `agent.synthesis.build_user_message` (parámetro nuevo
  `memory_hints`) — nunca a la lista `evidence`. Escritura del turno a STM
  después de `apply_guards`.
- **Camino agéntico** (`agent/strands_tools.py`, `agent/strands_agent.py`,
  `agent/gate_hook.py`, `agent/tool_trace_hook.py`): tercera tool
  `recall_memory` que el modelo decide llamar (extensión de
  `AGENTIC_SYSTEM_PROMPT`); `EvidenceCollector` gana un flag
  `evidence_tool_called` para que `CoverageGateHook` no corte el turno
  cuando el único tool llamado hasta ahora es memoria (ver el riesgo
  detallado en `design.md`); `ToolTraceHook` reconoce la tool nueva.
- **Traza visible**: dos etapas nuevas, `herramienta.recordar_memoria`
  (+`.error`, mismo vocabulario que `herramienta.navegar_grafo`) y
  `memoria.guardado` (+`.error`). `web/api.py` no necesita cambios de
  mapeo: `_eventos_de_paso` ya trata cualquier `herramienta.*` como
  `TOOL_CALL_*` y cualquier otra etapa como `STATE_DELTA` — el prefijo
  nuevo entra gratis. `demo.py --trace` gana una línea `🧠 memoria → ...`.
- **CLI** (`demo.py`): opciones `--actor-id`/`--session-id` en `query`, 3
  escenarios guionados nuevos (STM, preferencia, hecho falso) reutilizando
  el elenco ya existente de Billing 2.0/auth-cache/Identidad, y soporte de
  verificación multi-turno en `check()` para el escenario STM.
- **`.env.example`** y `corpus/README.md`: documentar las variables nuevas
  y el contrato de los 3 escenarios guionados, mismo estilo que las
  entradas existentes.

## Capabilities

### New Capabilities
- `memoria`: memoria de sesión (STM), preferencias de usuario y hechos
  (LTM) sobre AgentCore Memory, con la garantía de que nada recuperado de
  memoria puede convertirse en evidencia citable ni en fundamento único de
  una respuesta.

### Modified Capabilities
(ninguna: el repo no tiene specs de OpenSpec previas para `agente`/`gate`/
`guards` — este es el primer change — así que no hay una capability
existente que este cambio esté modificando en el sentido de OpenSpec; el
comportamiento de esos módulos se extiende, pero sus requisitos actuales no
están documentados como spec y no se tocan.)

## Impact

Código (`src/second_brain/`): `ports.py`, `config.py`,
`adapters/local/fake_memory_store.py` (nuevo),
`adapters/aws/agentcore_memory_store.py` (nuevo), `agent/memory.py` (nuevo),
`agent/orchestrator.py`, `agent/synthesis.py`, `agent/strands_tools.py`,
`agent/strands_agent.py`, `agent/gate_hook.py`, `agent/tool_trace_hook.py`.

CLI/web: `demo.py`, `web/api.py` (solo el campo opcional `session_id` en
`PreguntaIn`, ver tareas — el mapeo de traza no cambia).

Config/documentación: `.env.example`, `corpus/README.md`.

Tests: `tests/test_ports.py`, `tests/test_config.py`, `tests/test_agent.py`,
`tests/test_strands_agent.py`, `tests/test_demo_script.py`,
`tests/test_memory.py` (nuevo).

Dependencias: ninguna nueva — `boto3` ya es el extra opcional `aws`
existente (`pyproject.toml`); `bedrock-agentcore` (el paquete boto3 de
alto nivel/SDK) NO se instala ni se necesita, porque el adapter habla
directo con el cliente boto3 genérico `bedrock-agentcore` (data plane),
igual que `BedrockLlm`/`S3VectorsStore` ya hacen con sus respectivos
clientes.

Infraestructura: ninguna. El recurso `second_brain_memory` ya existe
(`infra/stacks/agentcore_stack.py`); este change es puramente de
consumo, cero `cdk deploy`.

## Qué NO cambia

1. **Ninguna firma pública existente se rompe.** `answer()`/`answer_agentic()`
   ganan parámetros nuevos *keyword-only con default* (`actor_id=None`,
   `session_id=None`); todo caller actual (tests, `mcp/server.py`,
   `a2a/server.py`, `web/api.py`) sigue compilando y comportándose IGUAL sin
   tocar una línea.
2. **Las 116 pruebas actuales siguen en verde sin modificarse.** Con
   `SECOND_BRAIN_MEMORY_ENABLED` sin setear (default `false`),
   `stack.memory` es `None` en todo `Stack` construido hoy, y todo el
   código de memoria queda de baja (`if stack.memory is None: return`).
3. **`SYSTEM_SYNTHESIS` y `AGENTIC_SYSTEM_PROMPT` no cambian su texto base.**
   La guía sobre `recall_memory`/preferencias se agrega como un bloque
   condicional aparte (solo presente cuando hay pistas de memoria para ese
   turno), nunca editando las constantes existentes in-place — así
   cualquier test que compare contra su contenido literal no se ve afectado.
4. **El coverage gate no gana una cuarta señal.** `evaluate_coverage` sigue
   viendo únicamente `list[Evidence]` producida por
   `search_documents`/`traverse_graph`; memoria nunca aparece en esa lista
   (ver Invariante 1 en `specs/memoria/spec.md`).
5. **El modo local sigue funcionando sin Docker/AWS por default.** Sin
   `SECOND_BRAIN_MEMORY_ENABLED=true`, ni siquiera se instancia
   `FakeMemoryStore`; con esa bandera, `FakeMemoryStore` no importa
   `boto3` ni hace red.
6. **No se declara infraestructura nueva.** Este change no toca
   `infra/stacks/agentcore_stack.py` ni corre `cdk deploy`/`cdk synth`.

## Riesgos

1. **Corte prematuro del turno agéntico.** `CoverageGateHook` corta el
   turno en el primer `AfterToolsEvent` que ve `Coverage.NO_EVIDENCE`
   (`gate_hook.py`, docstring: "corta en el primer NO_EVIDENCE que ve").
   Si el modelo llama `recall_memory` SOLO (sin `search_documents` en el
   mismo batch) para resolver una anáfora antes de saber qué buscar, el
   `EvidenceCollector` sigue vacío y el gate abortaría el turno ANTES de
   que el modelo pueda usar lo que memoria le devolvió. Es un riesgo real,
   no hipotético — es exactamente el flujo que el escenario STM necesita.
   Mitigación obligatoria (ver `design.md` Decisión 5 y
   `specs/memoria/spec.md` Requirement "El gate no corta un turno que solo
   consultó memoria"): `EvidenceCollector` gana `evidence_tool_called`, y
   `CoverageGateHook` no evalúa/corta mientras siga en `False`.
2. **Consistencia eventual de las estrategias administradas.** `SEMANTIC`/
   `USER_PREFERENCE` extraen hechos/preferencias de los eventos STM de
   forma asíncrona (documentado por AWS; no hay una API síncrona
   "extraé ahora"). Un hecho o preferencia declarados en el turno N pueden
   no estar recuperables todavía en el turno N+1 inmediato en un ensayo en
   vivo. Mitigación: el escenario de demo para (b)/(c) siembra el
   hecho/preferencia con antelación (vía `FakeMemoryStore` en local, o una
   escritura de calentamiento antes de subir al escenario en modo AWS) en
   vez de depender de la extracción en vivo durante la charla.
3. **Costo y llamadas nuevas a AWS por turno.** Con memoria activa, cada
   turno en modo `aws` agrega hasta 3 llamadas de lectura
   (`RetrieveMemoryRecords` ×2, `ListEvents` ×1) y 1 de escritura
   (`CreateEvent`) — la tabla de costos de `agentcore_stack.py` ya cubre
   este volumen (`<$0.01` por 45 minutos de demo), pero es tráfico AWS que
   no existía. Mitigación: invariante 4 (activación explícita) y
   fail-open (invariante 3) acotan el radio del riesgo a "cuando el
   usuario lo pidió".
4. **`actorId`/`sessionId` son responsabilidad de quien llama.** `Stack` es
   un objeto compartido, construido una vez por proceso — no puede guardar
   estado de sesión sin romper su rol de "puertos ya cableados,
   reutilizables". El precio es que cada capa de entrada (CLI, `web/api.py`,
   MCP, A2A) tiene que decidir y pasar su propio `session_id` explícito;
   sin él, memoria queda inactiva para ese turno aunque `stack.memory`
   exista (ver invariante 4). Es una fricción de integración, documentada
   en tareas, no un riesgo de seguridad.
5. **`bedrock-agentcore` no tiene wrapper Python de alto nivel ni
   integración Strands publicada** (solo TypeScript, según el contexto
   verificado de esta tarea) — confirmado además por introspección directa
   de `strands-agents==1.54.0` instalado: `strands.memory.vended_memory_stores`
   solo trae `bedrock_knowledge_base`/`file_memory_store`/`test_memory_store`,
   y `strands.session` solo trae `file`/`s3`/`repository`/`snapshot`
   — ninguno para AgentCore Memory. El adapter se escribe a mano sobre
   boto3 genérico (`boto3.client("bedrock-agentcore")`), sin atajos de
   SDK. Riesgo de mantenimiento si AWS publica después un SDK oficial:
   documentado como camino de upgrade, no bloqueante hoy.

## Criterios de aceptación

1. `pytest -q` sobre `.venv312` sigue en 116/116 verde SIN modificar
   ningún test existente, más los tests nuevos de este change, todos
   verdes.
2. Con `SECOND_BRAIN_MEMORY_ENABLED` sin setear, el comportamiento de
   `demo.py check` (los 10×2 casos existentes) es byte-idéntico al de hoy.
3. Escenario (a): dos turnos consecutivos en la misma sesión
   (`--session-id` compartido) — el segundo, una referencia anafórica sin
   sujeto explícito — responde sobre el sujeto correcto sin que el usuario
   lo repita, y sin agregar ninguna cita cuyo `doc_id` no exista en
   `Evidence` de ESE turno.
4. Escenario (b): con una preferencia de formato activa, la misma pregunta
   de Billing 2.0 sigue citando la dependencia real (`auth-cache`) y el
   equipo real (`Identidad`) con `Coverage` sin cambios, pero cambia qué
   se verbaliza (p.ej. omite la discusión de ADRs) — nunca inventa ni
   omite un hecho verificable.
5. Escenario (c): un hecho falso sembrado en memoria (mismo tipo de puente
   inventado que `demo.TEXTO_P_BILLING_INGENUO`: "el equipo de Plataforma
   debe resolver `auth-cache`") que se cuela en el texto de la respuesta
   queda degradado por `agent.guards.validate_relational_claims` con el
   MISMO mecanismo, sin código nuevo en `guards.py`.
6. Ninguna `Citation` de ninguna respuesta, en ningún escenario de este
   change, referencia un `doc_id` que no provenga de
   `search_documents`/`traverse_graph`.
7. En modo local sin `SECOND_BRAIN_MEMORY_ENABLED=true`, `FakeMemoryStore`
   no se instancia y no hay ninguna importación de `boto3` en el camino de
   arranque de `_stack_local`.
8. `openspec validate --strict` sobre este change no reporta errores de
   estructura (ver resultado real reportado en el mensaje final de esta
   tarea).
