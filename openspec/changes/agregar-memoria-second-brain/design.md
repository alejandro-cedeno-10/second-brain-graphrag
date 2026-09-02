## Context

El recurso `second_brain_memory` (`infra/stacks/agentcore_stack.py`) ya
existe: `expiration_duration=30 días` (STM) y dos `ManagedMemoryStrategy`
— `SEMANTIC` (`strategy_name="hechos_arquitectura"`, namespace
`second_brain/{actorId}/hechos`) y `USER_PREFERENCE`
(`strategy_name="preferencias_usuario"`, namespace
`second_brain/{actorId}/preferencias`). Cero código lo consume hoy.

Antes de diseñar se verificaron dos cosas por introspección real (no por
memoria del modelo, siguiendo la regla del contexto de esta tarea):

**1. Las operaciones del data plane `bedrock-agentcore` que existen de
verdad**, corriendo contra el service model de boto3 instalado
(`boto3==1.43.83` en `.venv312`), sin llamar a AWS:

```
CreateEvent, RetrieveMemoryRecords, ListActors, ListEvents, ListSessions,
GetEvent, GetMemoryRecord, ListMemoryRecords, BatchCreateMemoryRecords, ...
```

Con sus formas de parámetro reales (relevante para el adapter):

- `CreateEvent(memoryId, actorId, sessionId, eventTimestamp, payload=[{conversational:{content:{text}, role}}], branch?, clientToken?, metadata?)`
  → escribe un evento crudo a STM.
- `RetrieveMemoryRecords(memoryId, namespace, searchCriteria={searchQuery, memoryStrategyId?, topK?, metadataFilters?}, ...)`
  → búsqueda semántica sobre los registros YA extraídos por una estrategia
  administrada (LTM). Devuelve `memoryRecordSummaries[].{content.text, score, memoryStrategyId, namespaces}`.
- `ListEvents(memoryId, sessionId, actorId, includePayloads?, filter?, maxResults?)`
  → lee la ventana de eventos crudos de una sesión (STM), sin ranking por
  relevancia — es orden temporal, no búsqueda.
- `ListActors(memoryId)` → confirma el hecho ya verificado de que hoy no
  hay ningún actor (cero tráfico).

**2. Qué expone realmente `strands-agents==1.54.0` instalado**, también
por introspección directa del paquete (no de la documentación genérica de
Strands, que describe el SDK en general sin garantizar qué hay en esta
versión):

- `strands.memory.types.MemoryStore` es un `Protocol`: **solo `search`
  es obligatorio** (`async def search(self, query, options=None) -> list[MemoryEntry]`);
  `add`, `add_messages`, `initialize`, `get_tools` son opcionales — agregar
  `add`/`add_messages` es lo que vuelve a un store "writable".
- `strands.memory.memory_manager.MemoryManager(stores, search_tool_config=True, add_tool_config=False, injection=True)`
  registra una tool `search_memory` (opcional `add_memory`) y, con
  `injection` activo, "fold[s] retrieved memory into model input before
  each call **without touching durable history**" (docstring real del
  método).
- `strands.memory.vended_memory_stores` trae exactamente
  `bedrock_knowledge_base`, `file_memory_store`, `test_memory_store`.
  `strands.session` trae exactamente `file_session_manager`,
  `s3_session_manager`, `repository_session_manager`,
  `snapshot_session_manager`.
- **Ninguno de los dos módulos anteriores tiene una clase para AgentCore
  Memory.** Esto es un hallazgo importante: el docstring de
  `infra/stacks/agentcore_stack.py` (sección "Memory") cita
  `AgentCoreMemorySessionManager` (STM) y `AgentCoreMemoryStore` (LTM)
  como si fueran símbolos reales "del lado del SDK de Strands", atribuido a
  un `SPIKE_COMPATIBILIDAD.md §5` que este change no tiene a la vista. La
  introspección de arriba **no encuentra esos símbolos** en el paquete
  instalado. Este design NO asume que existen: confirma, en cambio, la
  instrucción explícita del contexto de esta tarea ("el paquete
  `bedrock-agentcore` NO está instalado y su integración Strands publicada
  es del SDK TypeScript... hay que implementarlo como `MemoryStore` custom
  sobre boto3"). Si esa cita del stack de CDK resulta cierta en una versión
  futura de `strands-agents`, es una simplificación de implementación
  bienvenida, no algo de lo que este spec dependa.

## Goals / Non-Goals

**Goals:**
- Especificar cómo la memoria entra al sistema sin volverse evidencia
  citable ni fundamento de cobertura (Invariante 1 del contexto).
- Especificar la MISMA ruta de anclaje al grafo para una afirmación
  relacional venida de memoria que para una del modelo (Invariante 2).
- Especificar activación explícita y fail-open (Invariantes 3 y 4).
- Mantener el modo local 100% funcional sin AWS (Invariante 5) y las 116
  pruebas verdes sin tocarlas.
- Dejar una traza visible, consistente con el vocabulario ya establecido
  por `ToolTraceHook`/`web/api.py`.

**Non-Goals:**
- No se rediseña el coverage gate más allá del ajuste mínimo necesario
  para no cortar un turno que solo consultó memoria (Decisión 5).
- No se implementa una UI de gestión de memoria (ver/editar/borrar
  recuerdos) — fuera del alcance de la charla.
- No se resuelve aquí el pendiente de FalkorDB remoto en modo `aws`
  (`infra/README.md`, "decisión pendiente del usuario") — memoria y grafo
  son preocupaciones independientes.
- No se adopta `strands.memory.memory_manager.MemoryManager`/`injection`
  como mecanismo de entrega (ver Decisión 3: alternativa descartada).
- No se declara infraestructura CDK nueva.

## Decisions

### Decisión 1 — Memoria nunca se agrega a `Evidence`/`EvidenceCollector`

**Qué se decide:** el resultado de consultar memoria (`list[MemoryHint]`)
NUNCA se convierte en `second_brain.agent.tools.Evidence` ni se pasa a
`EvidenceCollector.add(...)`. Viaja como texto aparte hacia el LLM (bloque
de "pistas", ver Decisión 4), y como parámetro aparte hacia
`build_user_message`.

**Por qué es la decisión más importante de todo el change:** cuatro
mecanismos existentes ya hacen cumplir los invariantes 1 y 2 SOLO SI esta
regla se respeta, sin tocar código de esas cuatro piezas:

1. `agent.gate.evaluate_coverage(question, evidence)` solo mira
   `list[Evidence]`. Si memoria nunca entra ahí, memoria nunca puede
   convertir un turno `NO_EVIDENCE` en `PARTIAL`/`SUFFICIENT` — la
   abstención sigue siendo la única salida honesta cuando la única "pista"
   es de memoria.
2. `agent.postprocess.extract_citations(text, evidence)` solo construye
   una `Citation` para un `[source:doc_id]` cuyo `doc_id` aparece en
   `evidence`. Un `doc_id` inventado a partir de memoria (que no tiene
   `doc_id` real) nunca produce una cita.
3. `agent.guards.validate_citations` recorta cualquier `[source:doc_id]`
   que no esté en `evidence` — red de seguridad adicional si algo se
   escapara de (2).
4. `agent.guards.validate_relational_claims` verifica cada afirmación
   relacional del TEXTO FINAL contra el grafo/evidencia de ESE turno,
   **sin mirar de dónde salió la prosa que la contiene**. Si el modelo
   redacta "el equipo de Plataforma debe resolver auth-cache" porque lo
   leyó de una pista de memoria envenenada, el detector la encuentra
   exactamente igual que si el modelo la hubiera alucinado sola — porque
   opera sobre `answer.text`, no sobre la procedencia de cada oración.

Alternativa descartada A — **memoria como tercera tool con la misma forma
que `search_documents`/`traverse_graph`, agregando también a
`collector.items`:** más simple de cablear (reusa `_STAGE_BY_TOOL` y el
mismo `_format_evidence`), pero rompe el Invariante 1 de raíz: memoria
contaría para cobertura y sería citable. Descartada sin ambigüedad — es
exactamente lo que la charla no puede permitirse mostrar mal.

Alternativa descartada B — **filtrar en `evaluate_coverage`/`extract_citations`
por un campo `Evidence.source == "memoria"` en vez de no agregar memoria a
la lista:** técnicamente equivalente en el resultado final, pero exige
tocar cuatro funciones ya probadas (`gate.py`, `postprocess.py`, dos
funciones de `guards.py`) para enseñarles un caso nuevo, con más superficie
de "me olvidé de un `if`" que simplemente nunca meter memoria en la lista.
Descartada por superficie de cambio innecesaria sobre código crítico ya
verificado por 116 tests.

### Decisión 2 — Puerto propio `MemoryPort`/`MemoryHint` en `ports.py`, no `strands.memory.types.MemoryStore`/`MemoryEntry`

**Qué se decide:** un `Protocol` nuevo, mismo estilo que
`EmbeddingsPort`/`GraphStorePort`:

```python
@dataclass
class MemoryHint:
    text: str
    kind: str  # "sesion" | "hecho" | "preferencia"
    namespace: str | None = None
    score: float | None = None

@runtime_checkable
class MemoryPort(Protocol):
    def recall(self, actor_id: str, session_id: str | None, query: str) -> list[MemoryHint]: ...
    def remember_turn(self, actor_id: str, session_id: str, question: str, answer_text: str) -> None: ...
```

**Por qué:** `agent.orchestrator` (el camino fijo) hoy no importa NADA de
`strands` — es deliberado (ver su docstring: "el `Agent` de Strands decide
cuándo llamar... a diferencia de `agent.orchestrator.answer`"). Adoptar
`strands.memory.types.MemoryStore` (con métodos `async`, forma
`SearchOptions`/`MemoryEntry` pensada para el `MemoryManager` de Strands)
en el camino fijo acoplaría un módulo hoy agnóstico de frameworks a una
librería que solo el camino agéntico necesita. `MemoryPort` es síncrono
(coherente con el resto de `ports.py`: `EmbeddingsPort.embed`,
`GraphStorePort.query`, ninguno es `async`) y sirve a los dos caminos por
igual.

Alternativa descartada — **usar `strands.memory.types.MemoryStore`/`MemoryEntry`
directamente como el contrato de dominio:** obligaría a `orchestrator.py` a
volverse `async` o a envolver cada llamada en `asyncio.run(...)`
(contaminando un pipeline síncrono por una sola dependencia), y a
`config.py`/`adapters/local`/`adapters/aws` a devolver `MemoryEntry` en vez
de reusar el vocabulario de dominio (`doc_id`, `is_target`, `source`) que
ya comparten `Chunk`/`Hit`/`Evidence`. Descartada por costo de acoplamiento
frente a beneficio nulo (el camino agéntico no necesita `MemoryManager`,
ver Decisión 3).

### Decisión 3 — El camino agéntico expone memoria como tercera tool explícita (`recall_memory`), no vía `MemoryManager`/`injection`

**Qué se decide:** `agent.strands_tools.build_tools` registra una tercera
`@tool` (`recall_memory`) solo cuando `stack.memory is not None`, con la
misma forma que `search_documents`/`traverse_graph` (recibe argumentos del
modelo, devuelve texto), pero su wrapper **no llama a
`collector.add(...)`** (ver Decisión 1). `AGENTIC_SYSTEM_PROMPT` gana una
instrucción nueva que le dice al modelo cuándo llamarla (referencia
anafórica sin sujeto explícito) y qué NO puede hacer con lo que recibe
(nunca citarlo como `[source:...]`, nunca tratarlo como hecho verificado).

Alternativa descartada — **`strands.memory.memory_manager.MemoryManager(stores=[...], injection=True)`,**
que en teoría es la pieza "correcta" de Strands para esto (verificado por
introspección: existe, funciona, y su propio docstring documenta
exactamente el comportamiento que se necesita — "sin tocar la historia
durable"). Se descarta por tres razones concretas:
1. **No produce una tool call interceptable.** La inyección ocurre ANTES
   de invocar al modelo, no como resultado de una decisión del modelo — el
   `ToolTraceHook` (que escucha `AfterToolCallEvent`) nunca vería nada, y
   la charla necesita la línea de traza visible (`herramienta.recordar_memoria`)
   tanto como necesita ver `herramienta.buscar_documentos`.
2. **Duplica el modelo de datos.** Tendríamos `MemoryHint` (nuestro,
   síncrono, para el camino fijo) Y `MemoryEntry`/`MemoryStore` (de
   Strands, async, solo para el agéntico) — dos formas para la misma idea,
   con un adapter puente extra que solo existe para satisfacer una
   interfaz que no aporta nada que `recall_memory` como tool no dé ya.
3. **Es más máquina de la que hace falta.** `MemoryManager` resuelve un
   problema (mezclar automáticamente N stores con extracción y tools de
   búsqueda/escritura configurables) que este change no tiene: hay
   exactamente un recurso, tres vistas de lectura, y ya existe un
   mecanismo de tools/trace propio (`strands_tools.py`) que resuelve lo
   mismo con menos piezas nuevas.

Descartada por complejidad injustificada, no por incompatibilidad — si en
el futuro la charla necesitara MÁS de un store de memoria compitiendo,
`MemoryManager` sería la elección correcta.

### Decisión 4 — Orden de ejecución: recall determinista y ANTES de resolver el sujeto (camino fijo) vs. tool decidida por el modelo (camino agéntico)

**Qué se decide (camino fijo, `agent.orchestrator.answer`):**

```
recall_memory_fail_open(stack, actor_id, session_id, question, traza)
    ↓ (list[MemoryHint], nunca vacío-o-excepción hacia afuera)
resolve_targets(question, stack)   # sin cambiar su firma; la pista de
                                     # sesión ayuda indirectamente porque
                                     # el LLM ve el bloque de pistas en
                                     # build_user_message, pero
                                     # resolve_targets sigue leyendo solo
                                     # `question` — ver nota abajo
    ↓
_collect_evidence(...) → evaluate_coverage(...) → (abstención | síntesis)
```

Nota importante: `resolve_targets` (en `retrieval.py`, no tocado por este
change) sigue operando solo sobre el texto de `question`. La resolución de
"¿y quién es el dueño?" → `core-billing` **no** pasa por hacerle
"expansión de query" automática a `resolve_targets` con texto de memoria
inyectado a mano (se consideró y se descarta abajo) — pasa por dárselo
como pista EXPLÍCITA al LLM en el mensaje de síntesis, para que sea el
LLM (no un heurístico nuevo de string-matching) quien la traduzca a una
respuesta que sí nombra el sujeto. Como consecuencia, **el escenario STM
en el camino fijo solo se verifica al nivel de texto de respuesta y citas,
no al nivel de qué documento resolvió `objetivos.resueltos`** — si
`resolve_targets` no encuentra nada para la pregunta de seguimiento sola,
la evidencia documental de ESE turno puede venir de la búsqueda genérica
(no anclada) en vez de la anclada; sigue siendo evidencia real y citable,
solo que sin el boost del anclaje. Este límite queda documentado como
requisito verificable en `specs/memoria/spec.md`, no oculto.

Alternativa descartada — **hacer que `agent.memory` reescriba la
`question` antes de pasarla a `resolve_targets`/`search_documents`**
(p.ej. concatenar el sujeto recordado al string de la pregunta): se
descarta porque mezclar silenciosamente texto recordado dentro de la
`question` original contamina exactamente la señal que
`agent.gate.evaluate_coverage`/`agent.synthesis.decompose` usan para medir
facetas y sujeto — ambas funciones asumen que `question` es lo que el
usuario tipeó. Cambiarla a mano abriría la puerta a que una pista de
memoria (incluida una envenenada) mueva la cobertura calculada, sin que
eso sea visible en ningún lado — justo lo que la Decisión 1 evita para la
lista de evidencia. Mejor mantener `question` intacta y dejar que el LLM
vea la pista de forma explícita y separada.

**Qué se decide (camino agéntico):** el modelo decide, guiado por
`AGENTIC_SYSTEM_PROMPT`. Esto SÍ resuelve el límite de arriba: el modelo
puede llamar `recall_memory` primero, leer en el texto de respuesta de la
tool cuál era el sujeto de la sesión, y llamar
`search_documents(question=..., target="core-billing")` con el `target`
ya resuelto — exactamente el mismo patrón que hoy usa para preguntas
relacionales con `traverse_graph`. Es la misma asimetría fijo/agéntico que
ya existe en el resto del sistema (`_build_decide_response` vs.
`_collect_evidence`): el camino fijo es mecánico y explica menos; el
agéntico es más capaz porque el modelo razona con lo que lee.

### Decisión 5 — `CoverageGateHook` no corta un turno cuyo único tool call visto hasta ahora es `recall_memory`

**El riesgo concreto** (ver también `proposal.md`): `CoverageGateHook`
corta el turno (`event.end_turn = ABSTENTION_MESSAGE`) en el PRIMER
`AfterToolsEvent` cuya cobertura es `NO_EVIDENCE`. Si el modelo, siguiendo
la Decisión 4, llama `recall_memory` SOLO en su primer batch (no sabe
todavía qué buscar), `EvidenceCollector.items` sigue vacío en ese punto →
`evaluate_coverage` da `NO_EVIDENCE` → el hook corta el turno ANTES de que
el modelo pueda usar la pista para decidir su segunda llamada. El
escenario STM se rompería sistemáticamente, no por un bug de memoria sino
por una interacción de timing con un guard que memoria no toca.

**Qué se decide:** `EvidenceCollector` (en `strands_tools.py`) gana un
campo `evidence_tool_called: bool = False`, puesto en `True` únicamente
por los wrappers de `search_documents`/`traverse_graph` (nunca por
`recall_memory`). `CoverageGateHook._on_after_tools` no evalúa/corta
mientras `collector.evidence_tool_called` sea `False`: en cambio, agrega
una traza `gate.cobertura.diferido` ("memoria consultada, evidencia real
todavía no solicitada — el turno sigue") y retorna sin tocar `end_turn`.
En cuanto el modelo llama a `search_documents`/`traverse_graph` por
primera vez, el flag pasa a `True` y el gate vuelve a evaluar como hoy en
CUALQUIER `AfterToolsEvent` posterior — incluyendo, si corresponde, cortar
por `NO_EVIDENCE` real.

Se investigó si `AfterToolsEvent` expone qué tools compusieron el batch
(para una detección más fina, "este batch específico fue memoria-only")
— por introspección real de `strands.hooks.events.AfterToolsEvent`, el
evento expone `message`/`invocation_state`/`end_turn`, NINGUNO enumera los
nombres de tool del batch de forma directa (habría que reparsear
`message.content`, más fragil que un flag propio). Por eso la señal vive
en `EvidenceCollector`, que el hook ya referencia, en vez de intentar leer
el batch desde el evento.

Alternativa descartada — **resolver esto solo con el prompt** ("llamá
`recall_memory` y `search_documents` en el mismo batch, nunca por
separado"): funciona cuando el modelo obedece, pero el escenario STM
existe justamente PORQUE el modelo no sabe qué `target` pasarle a
`search_documents` hasta leer la respuesta de `recall_memory` — pedirle
que adivine el `target` en el mismo batch en que recién está preguntando
"¿de qué hablábamos?" es contradictorio. Se mantiene la instrucción de
prompt como ayuda (preferible cuando el modelo SÍ puede resolver todo de
una), pero el fix estructural en el hook es el que garantiza corrección
sin depender de que un LLM real siga una instrucción sutil bajo presión.

### Decisión 6 — Activación en tres capas independientes (defensa en profundidad, igual que el resto del sistema)

Ninguna llamada real a AWS por memoria ocurre a menos que las TRES
condiciones sean ciertas a la vez:

1. **Config de proceso:** `SECOND_BRAIN_MODE=aws` (ya existente).
2. **Config de memoria:** `SECOND_BRAIN_MEMORY_ENABLED=true` Y
   `SECOND_BRAIN_AGENTCORE_MEMORY_ID` no vacío — `build_stack`/`_stack_aws`
   solo construye `AgentCoreMemoryStore` cuando AMBAS son ciertas; si falta
   cualquiera, `stack.memory` queda `None` y todo lo demás sigue exacto a
   hoy. Dos señales independientes (no una sola) a propósito, mismo
   espíritu que el guardrail opcional (`bedrock_guardrail_id` vacío ⇒
   Bedrock se llama sin `guardrailConfig`) pero MÁS estricto: acá hace
   falta la bandera Y el id, porque activar memoria implica escritura
   (`CreateEvent`) además de lectura, y un id mal copiado con la bandera
   prendida por error no debe empezar a escribir eventos en un recurso
   ajeno.
3. **Config del turno:** quien llama a `answer`/`answer_agentic` pasa un
   `session_id` no vacío para ESE turno. Sin él, aunque `stack.memory`
   exista, el turno se comporta exactamente como si memoria no existiera
   (no se llama ni `recall` ni `remember_turn`). Esto es lo que garantiza
   que los 116 tests actuales — que llaman `answer(question, stack, indice)`
   sin ese kwarg — siguen siendo, literalmente, cero tráfico de memoria,
   incluso en un `Stack` de test que alguien decida construir con
   `memory=FakeMemoryStore()`.

Alternativa descartada — **generar automáticamente un `session_id` por
defecto (p.ej. un UUID por proceso) cuando `stack.memory` existe,** para
que "simplemente funcione" sin que cada capa de entrada tenga que pensar
en sesiones: se descarta porque viola el Invariante 4 tal como está
redactado ("nunca por defecto") — el punto de exigir un `session_id`
explícito es que activar memoria sea una decisión visible de quien maneja
el turno (CLI, web, MCP, A2A), no un efecto secundario de haber configurado
el recurso.

### Decisión 7 — Preferencias cambian FORMA vía un bloque de prompt aparte, nunca vía la evidencia

El mismo mecanismo de la Decisión 1 (memoria fuera de `evidence`) ya
garantiza que una preferencia no puede volverse una `Citation`. Lo que
falta especificar es cómo influye la FORMA sin herramienta nueva:
`format_memory_hints` arma un bloque de texto separado por `kind`
(`"PISTA DE SESIÓN"` / `"PREFERENCIA DEL USUARIO"` / `"HECHO RECORDADO"`),
y tanto `build_user_message` (camino fijo) como el resultado de la tool
`recall_memory` (camino agéntico) lo entregan etiquetado así. La
instrucción — en `SYSTEM_SYNTHESIS`/`AGENTIC_SYSTEM_PROMPT`, agregada como
adenda condicional (ver Decisión 8) — es explícita: una preferencia puede
cambiar qué tan largo, qué tan técnico, o qué ángulos de la evidencia
DISPONIBLE se verbalizan, pero nunca agrega ni quita un hecho que la
evidencia real no sostenga. El criterio verificable (ver
`specs/memoria/spec.md`) es que los `doc_id` que sostienen la afirmación
central de la pregunta (p.ej. la dependencia + el equipo dueño en el caso
Billing 2.0) siguen citados igual; lo que puede desaparecer es contenido
opcional (p.ej. la discusión de un ADR) que la preferencia pidió omitir.

### Decisión 8 — Adenda de prompt condicional, nunca edición in-place de las constantes existentes

`SYSTEM_SYNTHESIS` (`agent/synthesis.py`) y `AGENTIC_SYSTEM_PROMPT`
(`agent/strands_agent.py`) son constantes de módulo hoy, ya citadas
literalmente en tests. Se decide agregar una constante nueva
`MEMORY_PROMPT_ADDENDUM` (en `agent/memory.py`) que:
- Solo se concatena al system prompt efectivo del turno cuando
  `stack.memory is not None` (y, para el camino fijo, cuando
  `recall_memory_fail_open` devolvió al menos una pista) — nunca se
  edita `SYSTEM_SYNTHESIS`/`AGENTIC_SYSTEM_PROMPT` in-place.
- Es la MISMA adenda para los dos caminos (una sola fuente de verdad,
  mismo patrón que `ABSTENTION_MESSAGE` en `agent/gate.py`, compartida
  porque "los DOS caminos... la usan").

Esto es lo que sostiene el criterio "byte-idéntico a hoy cuando memoria
está apagada" de `proposal.md`: con `stack.memory is None` (default), el
system prompt efectivo de cualquier turno es exactamente
`SYSTEM_SYNTHESIS`/`AGENTIC_SYSTEM_PROMPT` sin concatenar nada, carácter
por carácter.

### Decisión 9 — Dos adapters especializados, no uno genérico con un parámetro `kind`

`AgentCoreMemoryStore` (LTM: hechos + preferencias, ambos por
`RetrieveMemoryRecords` con `namespace`/`memoryStrategyId` distintos) y la
lectura/escritura de STM (`ListEvents`/`CreateEvent`) son, en la
implementación real, el MISMO cliente boto3 (`bedrock-agentcore`) y el
MISMO `memory_id` — pero conceptualmente dos operaciones de forma
distinta: LTM es "buscá por relevancia semántica" (hay `score`, hay
`topK`), STM es "traeme la ventana reciente de esta sesión" (hay orden
temporal, no ranking). Se decide que `AgentCoreMemoryStore` (una sola
clase, implementa `MemoryPort` completo) internamente separe esa lógica en
dos métodos privados (`_recall_ltm`/`_recall_stm`) en vez de dos CLASES —
a diferencia de la tentación de "una clase por capa" — porque las tres
vistas comparten el mismo cliente, el mismo `memory_id`, y el mismo punto
de fail-open (una excepción en cualquiera de las tres no debe tumbar a las
otras dos: `recall()` intenta las tres y agrega lo que consiga, no revienta
si una falla). Partirlo en clases separadas obligaría a orquestar tres
fail-opens en el llamador en vez de uno solo en el adapter.

Alternativa descartada — **una clase por estrategia** (`AgentCoreSemanticStore`,
`AgentCorePreferenceStore`, `AgentCoreSessionStore`), calcando el patrón
"un Protocol, una forma" de `ports.py`: se descarta acá puntualmente
porque `MemoryPort.recall` ya devuelve las TRES clases de pista mezcladas
(diferenciadas por `MemoryHint.kind`) en una sola llamada — partir la
implementación en tres clases exigiría que el llamador (`agent/memory.py`)
supiera invocar tres objetos distintos y fusionar sus fallas
individualmente, duplicando el fail-open que el adapter puede resolver una
sola vez internamente.

### Decisión 10 — `FakeMemoryStore` en RAM, sin persistencia a disco

A diferencia de `MemoryVectorStore` (que persiste a
`<path>.npz`/`<path>.json` porque `ingest`/`query` corren en procesos
CLI separados), `FakeMemoryStore` vive solo en RAM del `Stack` en curso.
Es suficiente porque los tres escenarios de demo en local se ejercitan
dentro de un mismo proceso con un `Stack` que vive toda la sesión:
`demo.py check` (multi-turno dentro del mismo `stack_fijo`/`stack_agentico`)
y una eventual sesión interactiva (`demo.py chat`, ver `tasks.md`) que
mantiene un solo `Stack` vivo mientras dura la conversación — nunca dos
invocaciones de proceso separadas de `demo.py query` como hoy. Se descarta
persistencia a disco por complejidad innecesaria para lo que la demo
necesita mostrar.

`FakeMemoryStore` expone además métodos de siembra que no forman parte de
`MemoryPort` (`seed_hecho(text, namespace=...)`,
`seed_preferencia(text)`) — existen solo para que `demo.py`/tests puedan
plantar el hecho falso del escenario (c) y la preferencia del escenario
(b) de forma determinista, sin depender de la extracción asíncrona real de
AgentCore (ver Riesgo 2 de `proposal.md`).

## Risks / Trade-offs

Ver la sección "Riesgos" de `proposal.md` para la lista completa con
mitigación. Los dos con mayor superficie de diseño (corte prematuro del
gate, consistencia eventual de las estrategias administradas) están
resueltos arriba en las Decisiones 5 y 10 respectivamente; el resto son
de costo/operación, no de corrección.

Trade-off explícito de la Decisión 4: el camino fijo resuelve el
escenario STM con menos certeza que el agéntico (depende de que el LLM de
síntesis use bien la pista, no de un resolver determinista) — es
consistente con la asimetría de capacidad que YA existe entre los dos
caminos en todo lo demás (el fijo es más simple y más predecible; el
agéntico es más capaz porque decide). No se considera un defecto a
corregir en este change.
