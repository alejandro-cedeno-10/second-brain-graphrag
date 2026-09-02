## ADDED Requirements

### Requirement: Activación explícita en tres capas independientes
El sistema DEBE (MUST) activar cualquier llamada real a AgentCore Memory solo
cuando se cumplen simultáneamente: (1) `SECOND_BRAIN_MODE=aws`, (2)
`Settings.memory_enabled` es verdadero Y `Settings.agentcore_memory_id` no
está vacío, y (3) quien invoca `answer`/`answer_agentic` para ese turno
pasa un `session_id` no vacío. La ausencia de cualquiera de las tres
condiciones DEBE dejar `stack.memory` en `None` o el turno sin actividad
de memoria, sin excepción y sin log de error.

#### Scenario: Sin ninguna variable de memoria configurada
- **WHEN** se construye `Settings.from_env()` sin `SECOND_BRAIN_MEMORY_ENABLED`
  ni `SECOND_BRAIN_AGENTCORE_MEMORY_ID` seteados, en cualquier `SECOND_BRAIN_MODE`
- **THEN** `build_stack(settings).memory` es `None`

#### Scenario: Bandera prendida sin id de recurso
- **WHEN** `SECOND_BRAIN_MODE=aws`, `SECOND_BRAIN_MEMORY_ENABLED=true` y
  `SECOND_BRAIN_AGENTCORE_MEMORY_ID` vacío o no seteado
- **THEN** `build_stack(settings).memory` es `None`

#### Scenario: Id de recurso presente sin la bandera
- **WHEN** `SECOND_BRAIN_MODE=aws`, `SECOND_BRAIN_AGENTCORE_MEMORY_ID` seteado
  a un id no vacío y `SECOND_BRAIN_MEMORY_ENABLED` sin setear (o `false`)
- **THEN** `build_stack(settings).memory` es `None`

#### Scenario: Las dos condiciones de configuración presentes, pero sin `session_id` en el turno
- **WHEN** `stack.memory` no es `None` (las dos variables anteriores están
  activas) y se llama `answer(question, stack, indice)` (o
  `answer_agentic(...)`) sin pasar `session_id`
- **THEN** el turno no invoca `MemoryPort.recall` ni `MemoryPort.remember_turn`,
  y la `Answer` resultante es idéntica a la que produciría el mismo turno
  con `stack.memory=None`

### Requirement: Modo local nunca depende de AWS para memoria
El sistema DEBE (MUST) ofrecer un adapter de memoria en RAM (`FakeMemoryStore`)
que implementa `MemoryPort` sin importar `boto3` ni abrir conexión de red,
y `build_stack` en `SECOND_BRAIN_MODE=local` NUNCA DEBE construir
`AgentCoreMemoryStore`.

#### Scenario: Modo local con memoria habilitada
- **WHEN** `SECOND_BRAIN_MODE=local` y `SECOND_BRAIN_MEMORY_ENABLED=true`
- **THEN** `build_stack(settings).memory` es una instancia de
  `FakeMemoryStore`, y construirla no importa el módulo `boto3`

#### Scenario: Modo local con memoria deshabilitada (default)
- **WHEN** `SECOND_BRAIN_MODE=local` sin `SECOND_BRAIN_MEMORY_ENABLED` seteado
- **THEN** `build_stack(settings).memory` es `None`

### Requirement: La memoria nunca se convierte en evidencia citable
El sistema DEBE (MUST) mantener el contenido recuperado de memoria
(`list[MemoryHint]`) completamente separado de `list[Evidence]` en todo
momento del turno: ninguna función que reciba `evidence`
(`agent.gate.evaluate_coverage`, `agent.postprocess.extract_citations`,
`agent.guards.validate_citations`, `agent.guards.validate_relational_claims`,
`agent.guards.canary`) DEBE recibir jamás un ítem derivado de memoria
mezclado en esa lista.

#### Scenario: Un `MemoryHint` nunca aparece como `Evidence`
- **WHEN** un turno con memoria activa recupera al menos un `MemoryHint`
  vía `recall_memory_fail_open`
- **THEN** ese `MemoryHint` no aparece en `collector.items` (camino
  agéntico) ni en la lista `evidencia` pasada a `evaluate_coverage`/
  `_synthesize` (camino fijo)

#### Scenario: Una respuesta sostenida solo por memoria se abstiene igual
- **WHEN** `search_documents`/`traverse_graph` no devuelven evidencia
  relevante para la pregunta del turno (evidencia real vacía o por debajo
  de `RELEVANT_SCORE_THRESHOLD`), y memoria SÍ devuelve una o más pistas
  para esa misma pregunta
- **THEN** `evaluate_coverage` clasifica el turno como `Coverage.NO_EVIDENCE`
  y la `Answer` resultante es la abstención (`ABSTENTION_MESSAGE`,
  `abstained=True`), exactamente igual que si memoria no hubiera devuelto
  nada

#### Scenario: Ninguna cita proviene de memoria
- **WHEN** el texto redactado por el LLM contiene una marca
  `[source:X]` donde `X` es un identificador que solo existe en el bloque
  de pistas de memoria (nunca fue un `doc_id` de `Evidence` de ese turno)
- **THEN** `agent.guards.validate_citations` recorta esa marca del texto
  final y ninguna `Citation` con ese `document` aparece en `answer.citations`

### Requirement: El gate de cobertura no corta un turno agéntico que solo consultó memoria
El sistema DEBE (MUST) evitar que `CoverageGateHook` termine un turno agéntico
(`event.end_turn`) mientras el único tool invocado hasta ese punto haya
sido `recall_memory` — es decir, mientras ningún tool call a
`search_documents`/`traverse_graph` haya ocurrido todavía en ese turno.

#### Scenario: Batch inicial solo con `recall_memory`
- **WHEN** el modelo, en su primer batch de tool calls, invoca únicamente
  `recall_memory` (cero llamadas a `search_documents`/`traverse_graph`
  todavía)
- **THEN** `CoverageGateHook` NO fija `event.end_turn`, agrega una
  `TraceStep(stage="gate.cobertura.diferido", ...)`, y el loop del agente
  continúa hacia una segunda llamada al modelo

#### Scenario: Segundo batch con evidencia real después de memoria
- **WHEN**, en el mismo turno del escenario anterior, el modelo hace una
  segunda llamada de tool que SÍ incluye `search_documents` (con un
  `target` informado por lo que `recall_memory` devolvió) y esa búsqueda
  encuentra evidencia relevante
- **THEN** el turno continúa hasta redactar una respuesta con citas
  reales, sin haber sido abortado en el batch anterior

#### Scenario: El gate sigue cortando cuando la evidencia real es genuinamente insuficiente
- **WHEN** el modelo llama `recall_memory` y luego `search_documents`, y
  esta última no encuentra evidencia relevante para la pregunta
- **THEN** `CoverageGateHook` evalúa `Coverage.NO_EVIDENCE` sobre la
  evidencia real acumulada y corta el turno con `ABSTENTION_MESSAGE`,
  exactamente como hace hoy sin memoria de por medio

### Requirement: Continuidad de sesión (STM) resuelve referencias entre turnos
El sistema DEBE (MUST) recuperar, para un turno con `session_id` compartido con un
turno previo de la misma sesión, el contexto necesario para que una
pregunta de seguimiento sin sujeto explícito (referencia anafórica) se
responda sobre el sujeto correcto establecido en el turno anterior, sin
que el usuario deba repetirlo.

#### Scenario: Pregunta de seguimiento sin sujeto explícito
- **WHEN** en la sesión `S`, el turno 1 es "Si modifico la API de
  core-billing, ¿qué módulos se rompen?" (mismo texto que `demo.P2`) y el
  turno 2, en la MISMA sesión `S`, es "¿y quién es el dueño?" (sin nombrar
  `core-billing`)
- **THEN** la respuesta del turno 2 identifica al equipo dueño de
  `core-billing` (Plataforma, según `corpus/servicios/core-billing.md`)
  citando un `doc_id` real de la evidencia de ESE turno, sin que el
  usuario haya vuelto a mencionar `core-billing`

#### Scenario: Sesión distinta no hereda contexto
- **WHEN** la misma pregunta de seguimiento ("¿y quién es el dueño?") se
  hace con un `session_id` que NUNCA tuvo un turno previo
- **THEN** el sistema no tiene sujeto que resolver por memoria y el
  comportamiento es el mismo que hoy sin memoria: evidencia insuficiente
  para identificar un sujeto produce `Coverage.NO_EVIDENCE`/abstención, o
  en el peor caso una respuesta que declara explícitamente no saber a
  qué/quién se refiere la pregunta — nunca una respuesta inventada

### Requirement: Las preferencias de usuario cambian la forma, nunca los hechos
El sistema DEBE (MUST) permitir que una preferencia de usuario recuperada de
memoria (LTM, `USER_PREFERENCE`) influya en la forma de una respuesta
futura (extensión, inclusión u omisión de ángulos opcionales de discusión)
sin alterar los hechos citables ni el veredicto de cobertura del turno.

#### Scenario: Preferencia activa no cambia qué se cita de fondo
- **WHEN** existe una preferencia recuperada equivalente a "no me des
  ADRs, solo impacto operativo" y se repite la pregunta de Billing 2.0
  (`demo.P_BILLING`)
- **THEN** la respuesta sigue citando `producto/billing-2-0.md` y
  `servicios/auth-cache.md` (la dependencia real y el equipo dueño real,
  Identidad), y `Coverage` evaluado por el gate es el mismo que sin la
  preferencia activa

#### Scenario: Preferencia activa puede omitir contenido opcional
- **WHEN** la misma preferencia del escenario anterior está activa
- **THEN** la respuesta puede omitir la discusión de
  `arquitectura/decisiones.md` (ADR-017)/el postmortem INC-042 que la
  versión sin preferencia sí incluye, sin que eso se interprete como un
  guard fallando — es la forma cambiando, no un hecho perdido

#### Scenario: Sin memoria activa, el comportamiento es el de hoy
- **WHEN** `stack.memory` es `None` o no hay ninguna preferencia sembrada
  para el `actor_id` del turno
- **THEN** el system prompt efectivo del turno (`SYSTEM_SYNTHESIS` o
  `AGENTIC_SYSTEM_PROMPT`) es exactamente el texto actual, sin ningún
  bloque de adenda concatenado, y el texto de la respuesta para
  `demo.P_BILLING` es byte-idéntico al que produce el sistema hoy

### Requirement: Un hecho falso recordado se degrada igual que una alucinación del modelo
El sistema DEBE (MUST) aplicar `agent.guards.validate_relational_claims` sobre el
texto final de la respuesta sin distinguir si una afirmación relacional se
originó en la evidencia real, en el razonamiento del modelo, o en una
pista de memoria — el mecanismo de detección y verificación existente
(patrones de verbo + verificación contra el grafo/evidencia del turno) DEBE
seguir siendo la única fuente de verdad, sin código nuevo de detección
específico para memoria.

#### Scenario: Hecho falso sembrado se cuela y se degrada
- **WHEN** se siembra en memoria (LTM, `hechos`) la afirmación falsa "el
  equipo de Plataforma debe resolver la dependencia de auth-cache" (el
  mismo puente inventado que `demo.TEXTO_P_BILLING_INGENUO`, cuyo dueño
  real es Identidad según `corpus/servicios/auth-cache.md`) y el modelo,
  al redactar la respuesta a `demo.P_BILLING`, repite esa afirmación en el
  texto
- **THEN** `validate_relational_claims` degrada esa oración a
  `[sin evidencia suficiente para afirmar que Plataforma es responsable de
  auth-cache]` (o mensaje equivalente), y la afirmación real y respaldada
  ("Identidad es responsable de auth-cache") permanece intacta si el
  modelo también la menciona

#### Scenario: El hecho falso nunca aparece como cita
- **WHEN** el mismo escenario anterior ocurre
- **THEN** ninguna `Citation` en `answer.citations` referencia un `doc_id`
  inexistente en la evidencia real del turno, aun si la pista de memoria
  falsa incluía un nombre de documento inventado

### Requirement: Fail-open ante memoria no disponible o con error
El sistema DEBE (MUST) degradar sin excepción visible al usuario cuando
`MemoryPort.recall`/`MemoryPort.remember_turn` fallan o no responden: el
turno DEBE completarse usando solo evidencia real, exactamente como si
memoria no estuviera configurada, dejando constancia del fallo en la
traza.

#### Scenario: `recall` lanza una excepción
- **WHEN** `stack.memory.recall(...)` lanza cualquier excepción durante un
  turno con memoria activa
- **THEN** el turno continúa sin pistas de memoria, se agrega
  `TraceStep(stage="herramienta.recordar_memoria.error", ...)` a la traza,
  y la respuesta final no cambia respecto de un turno sin memoria
  configurada

#### Scenario: `remember_turn` lanza una excepción
- **WHEN** `stack.memory.remember_turn(...)` lanza cualquier excepción
  después de que la respuesta ya fue calculada
- **THEN** la `Answer` ya calculada se devuelve sin cambios (la respuesta
  al usuario no se ve afectada por un fallo de escritura), y se agrega
  `TraceStep(stage="memoria.guardado.error", ...)` a la traza

### Requirement: Traza visible con el mismo vocabulario que las herramientas existentes
El sistema DEBE (MUST) producir líneas de traza para la actividad de memoria
usando el mismo prefijo `herramienta.*` que ya usan
`herramienta.buscar_documentos`/`herramienta.navegar_grafo`, para que el
mapeo existente de `web/api.py::_eventos_de_paso` (`herramienta.*` →
`TOOL_CALL_*`, cualquier otra etapa → `STATE_DELTA`) siga funcionando sin
modificarse.

#### Scenario: Recall exitoso genera una tool call visible
- **WHEN** `recall_memory_fail_open` recupera una o más pistas
- **THEN** la traza contiene `TraceStep(stage="herramienta.recordar_memoria", ...)`
  y, si el turno corre por `web/api.py`, esa etapa se traduce en eventos
  `TOOL_CALL_START`/`TOOL_CALL_ARGS`/`TOOL_CALL_END` sin ningún cambio de
  código en `_eventos_de_paso`

#### Scenario: `demo.py --trace` muestra una línea de memoria
- **WHEN** se corre `demo.py query --trace` con memoria activa y el turno
  recuperó pistas
- **THEN** la salida incluye una línea que empieza con `🧠 memoria` antes
  de la línea `📤 respuesta con N citas`, análoga en estilo a las líneas
  `🔍 buscador`/`🕸️ navegador`/`🛡️ guards` existentes

### Requirement: Compatibilidad total con las firmas públicas existentes
El sistema DEBE (MUST) aceptar `actor_id`/`session_id` como parámetros
keyword-only con default `None` en `agent.orchestrator.answer` y
`agent.strands_agent.answer_agentic`, de forma que ningún llamador
existente (`tests/`, `second_brain.mcp.server`, `second_brain.a2a.server`,
`web/api.py`) requiera modificación para seguir funcionando exactamente
igual que hoy.

#### Scenario: Llamada existente sin los parámetros nuevos
- **WHEN** se llama `answer(question, stack, lexical_index)` o
  `answer_agentic(question, stack, lexical_index)` sin `actor_id` ni
  `session_id`, con un `stack` que tiene `memory` configurado
- **THEN** el comportamiento (incluida la ausencia total de actividad de
  memoria) es idéntico al de un `Stack` con `memory=None`

#### Scenario: Las 116 pruebas existentes no se modifican
- **WHEN** se corre la suite de tests existente (`tests/test_agent.py`,
  `tests/test_strands_agent.py`, `tests/test_config.py`,
  `tests/test_demo_script.py`, etc.) sin editar ninguno de sus casos
  actuales
- **THEN** los 116 tests preexistentes siguen en verde
