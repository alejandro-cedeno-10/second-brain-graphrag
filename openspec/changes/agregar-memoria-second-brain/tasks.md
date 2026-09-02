## 1. Puerto de dominio (`ports.py`)

- [x] 1.1 Agregar `MemoryHint` (dataclass: `text: str`, `kind: str`,
      `namespace: str | None = None`, `score: float | None = None`) en
      `src/second_brain/ports.py`, junto a `Citation`/`TraceStep` (mismo
      estilo de docstring corto en español).
- [x] 1.2 Agregar `MemoryPort` (`@runtime_checkable class MemoryPort(Protocol)`)
      con `recall(self, actor_id, session_id, query) -> list[MemoryHint]`
      y `remember_turn(self, actor_id, session_id, question, answer_text) -> None`,
      junto a los demás `*Port` del archivo.
- [x] 1.3 Verificado que `FakeMemoryStore`/`AgentCoreMemoryStore` cumplen
      `MemoryPort` por `isinstance(...)` — *pero en `tests/test_memory_stores.py`
      (`test_fake_memory_store_implements_memory_port`/
      `test_agentcore_memory_store_implements_memory_port`), no en
      `tests/test_ports.py` como decía el plan original.*

## 2. Configuración (`config.py`)

- [x] 2.1 Agregar `_env_bool(name, default) -> bool` (mismo estilo que
      `_env_int`, comparando `.strip().lower() == "true"`).
- [x] 2.2 `Settings`: agregar `memory_enabled: bool = False`,
      `agentcore_memory_id: str | None = None`,
      `agentcore_actor_id: str = "demo-speaker"`. Cablear en
      `Settings.from_env()`: `SECOND_BRAIN_MEMORY_ENABLED`,
      `SECOND_BRAIN_AGENTCORE_MEMORY_ID`, `SECOND_BRAIN_AGENTCORE_ACTOR_ID`.
- [x] 2.3 `Stack`: agregar campo `memory: MemoryPort | None = None` al
      final del dataclass (con default — no rompe ningún `Stack(...)`
      existente, todos usan kwargs).
- [x] 2.4 `_stack_local`: si `settings.memory_enabled`, construir
      `FakeMemoryStore()` (import perezoso, mismo patrón que los demás
      adapters locales) y pasarlo como `memory=`; si no, `memory=None`
      explícito (o dejar el default).
- [x] 2.5 `_stack_aws`: si `settings.memory_enabled and settings.agentcore_memory_id`,
      construir `AgentCoreMemoryStore(memory_id=settings.agentcore_memory_id, region=settings.aws_region)`
      (import perezoso, mismo patrón que `BedrockLlm`/`S3VectorsStore`);
      si falta cualquiera de las dos condiciones, `memory=None`.
- [ ] 2.6 `tests/test_config.py`: casos nuevos — (a) sin ninguna env var de
      memoria, `build_stack` en los dos modos da `stack.memory is None`;
      (b) `MEMORY_ENABLED=true` sin `AGENTCORE_MEMORY_ID` en modo `aws` da
      `stack.memory is None`; (c) `AGENTCORE_MEMORY_ID` seteado sin
      `MEMORY_ENABLED=true` da `stack.memory is None`; (d) las dos juntas en
      modo `aws` da un `AgentCoreMemoryStore` real (sin llamar a AWS —
      solo construcción); (e) `MEMORY_ENABLED=true` en modo `local` da un
      `FakeMemoryStore`. — *PENDIENTE: `tests/test_config.py` no tiene hoy
      ningún caso de memoria (verificado por grep); los 5 escenarios se
      validaron a mano al implementar 2.1–2.5, no quedaron como test.*

## 3. Adapter local (`adapters/local/fake_memory_store.py`, nuevo)

- [x] 3.1 Crear el archivo con `class FakeMemoryStore` implementando
      `MemoryPort` en RAM — *forma real: `_hechos`/`_preferencias` indexados
      por `actor_id`, `_turnos` indexado por la clave compuesta
      `f"{actor_id}::{session_id}"` (equivalente a la tupla del plan).*
- [x] 3.2 `remember_turn(...)`: agrega `f"P: {question}\nR: {answer_text}"`
      (o forma equivalente) a la lista de la sesión.
- [x] 3.3 `recall(actor_id, session_id, query)`: devuelve, mezclados, hasta
      N turnos recientes de `(actor_id, session_id)` como
      `MemoryHint(kind="sesion")`, más `_hechos`/`_preferencias` sembrados
      como `MemoryHint(kind="hecho"/"preferencia")` — sin lógica de
      relevancia real (es un doble local, no necesita rankear). — *el
      `kind` real de los turnos es `"turno_stm"`, no `"sesion"` (así quedó
      documentado en `ports.MemoryHint`); los hechos SÍ se rankean por
      solapamiento léxico con la query (`_recall_hechos`), más de lo que
      pedía el plan, sin filtrar nada.*
- [x] 3.4 Métodos de siembra fuera de `MemoryPort`:
      `seed_hecho(text: str) -> None`, `seed_preferencia(text: str) -> None`
      — para que `demo.py`/tests planten el hecho falso y la preferencia
      del guion sin depender de extracción real. — *firma real:
      `seed_hecho(actor_id, texto, *, namespace=None)` (recibe `actor_id`
      explícito, el store no tiene uno propio fijo).*
- [x] 3.5 Cubrir las tres formas de `recall`, el aislamiento entre
      `(actor_id, session_id)` distintos, y que un turno nunca aparece en
      `MemoryHint.kind="hecho"` ni viceversa. — *en
      `tests/test_memory_stores.py`, no en `tests/test_memory.py`.*

## 4. Adapter AWS (`adapters/aws/agentcore_memory_store.py`, nuevo)

- [x] 4.1 Crear `class AgentCoreMemoryStore` implementando `MemoryPort`.
      Import perezoso de `boto3` dentro del primer método real (mismo
      patrón que `BedrockLlm`/`S3VectorsStore` — el constructor NO importa
      boto3). — *constructor real, más simple que el planeado:
      `(memory_id: str, region: str = "us-east-1")`, sin parámetros de
      template de namespace ni `top_k` (quedaron como constantes de
      módulo, `_TOP_K_LTM`/`_MAX_TURNOS_STM`).*
- [x] 4.2 `recall(actor_id, session_id, query)`: tres llamadas boto3
      (`retrieve_memory_records` ×2 con `namespace` de hechos/preferencias,
      `list_events`) usando los nombres de parámetro verificados por
      introspección real (`memoryId`, `namespace`,
      `searchCriteria={"searchQuery":..., "topK":...}`, `sessionId`,
      `actorId`). Mapear la respuesta a `MemoryHint` con `kind` según de
      qué llamada salió. — *diverge de la Decisión 1/9 de `design.md`:
      el adapter SÍ atrapa la excepción acá (loguea y devuelve `[]` por
      cada fuente, por separado) en vez de dejarla propagar hacia
      `agent/memory.py`. El invariante fail-open se mantiene igual (dos
      capas en vez de una), pero el fail-open de
      `recall_memory_fail_open` queda sin poder ejercitarse nunca con este
      backend real — ver la nota de la tarea 5.5.*
- [x] 4.3 `remember_turn(actor_id, session_id, question, answer_text)`:
      un `create_event` con el `payload` de dos bloques `conversational`
      (`USER`/`ASSISTANT`) y `eventTimestamp` = ahora (UTC).
- [x] 4.4 Mockear el cliente boto3 para verificar que `recall`/`remember_turn`
      arman los parámetros esperados, sin tocar AWS real — *en
      `tests/test_memory_stores.py` (`test_agentcore_recall_*`,
      `test_agentcore_remember_turn_*`), no en `tests/test_memory.py`.*

## 5. Helpers fail-open compartidos (`agent/memory.py`, nuevo)

- [x] 5.1 `recall_memory_fail_open(stack, actor_id, session_id, query, trace) -> list[MemoryHint]`:
      si `stack.memory is None`, devuelve `[]` sin tocar la traza. Si está
      seteado, llama `stack.memory.recall(...)` dentro de un `try/except`;
      excepción → `TraceStep(stage="herramienta.recordar_memoria.error", ...)`
      y devuelve `[]` (mismo patrón que `orchestrator._traverse_graph_fail_open`).
      — *la línea de ÉXITO NO la arma esta función (queda para quien
      orquesta el turno, `agent.tool_trace_hook.ToolTraceHook`, ver su
      docstring) — divergencia deliberada del plan, para no duplicar el
      renglón de traza.*
- [x] 5.2 `remember_turn_fail_open(stack, actor_id, session_id, question, answer_text, trace) -> None`:
      mismo criterio de inactividad; éxito → `TraceStep(stage="memoria.guardado", ...)`;
      excepción → `TraceStep(stage="memoria.guardado.error", ...)`. Nunca
      lanza.
- [x] 5.3 `format_memory_hints(hints: list[MemoryHint]) -> str`: arma el
      bloque de texto que lee el modelo. Devuelve un texto explícito de
      "sin recuerdos" si `hints` está vacío (nunca `""`). — *etiquetado
      real distinto al del plan: `[{etiqueta}] "texto"` con
      `_KIND_LABEL_ES` (`"LTM hechos"`/`"LTM preferencias"`/`"STM sesión"`),
      no `"PISTA DE SESIÓN"`/etc. — mismo espíritu (nunca se confunde con
      `[source:...]`), otra forma.*
- [x] 5.4 `MEMORY_PROMPT_ADDENDUM` (constante): el texto de instrucción
      sobre cómo tratar el bloque de pistas (nunca citar, preferencias solo
      cambian forma, hechos de memoria se verifican igual que cualquier
      afirmación relacional). — *se concatena solo a `AGENTIC_SYSTEM_PROMPT`
      (camino agéntico); `SYSTEM_SYNTHESIS`/el camino fijo no la usan
      todavía, ver sección 6.*
- [ ] 5.5 `recall_memory_fail_open`/`remember_turn_fail_open` con
      `stack.memory=None`, con un `MemoryPort` fake que lanza excepción, y
      con uno que responde bien — cuatro casos mínimos, verificando la
      traza en cada uno. — *PENDIENTE el caso de excepción: no hay ningún
      test que llame estas dos funciones directo con un `MemoryPort` que
      lanza. Se ejercitan indirecto vía `answer_agentic` (éxito,
      `stack.memory=None`, sin `actor_id`/`session_id`), pero la rama
      `except` de las dos queda sin cubrir — y con `AgentCoreMemoryStore`
      atrapando sus propias excepciones (ver nota de la tarea 4.2), esa
      rama es hoy inalcanzable con los backends reales del repo.*

## 6. Camino fijo (`agent/orchestrator.py`, `agent/synthesis.py`) — NO INICIADO

`orchestrator.answer` sigue sin `actor_id`/`session_id` (verificado por su
firma real); `synthesis.build_user_message` sigue sin `memory_hints`. Fue
una decisión explícita de scope, no un olvido — ver el docstring de
`agent/strands_agent.py` ("MEMORIA — por qué una tool explícita..."): la
fase que se implementó cablea memoria únicamente en el camino agéntico.
Los 5 sub-ítems de abajo quedan intactos para la fase que retome esto.

- [ ] 6.1 `synthesis.build_user_message`: agregar parámetro
      `memory_hints: str = ""`, insertado como bloque aparte (nunca dentro
      de los bloques de evidencia existentes). Con `""` (default), la
      salida es byte-idéntica a hoy — cubrir con un test explícito de
      no-regresión.
- [ ] 6.2 `orchestrator.answer`: agregar parámetros keyword-only
      `actor_id: str | None = None, session_id: str | None = None`.
      Llamar `recall_memory_fail_open` INMEDIATAMENTE después de resolver
      `objetivos` (antes de `_collect_evidence`, ver Decisión 4 de
      `design.md`) y pasar `format_memory_hints(pistas)` a `_synthesize`.
- [ ] 6.3 `orchestrator._synthesize`: recibir el bloque de pistas, armar el
      system prompt efectivo como `SYSTEM_SYNTHESIS` a secas si el bloque
      está vacío, o `SYSTEM_SYNTHESIS + "\n\n" + MEMORY_PROMPT_ADDENDUM`
      si no.
- [ ] 6.4 `orchestrator.answer`: después de `apply_guards` (con la
      respuesta ya con guards aplicados, éxito o abstención), llamar
      `remember_turn_fail_open(...)` — escribir el turno a STM pase lo que
      pase con la respuesta (incluida una abstención: registrar que se
      preguntó algo es útil para continuidad futura).
- [ ] 6.5 `tests/test_agent.py`: casos nuevos para el camino fijo — (a)
      dos llamadas a `answer` con el mismo `stack`/`session_id`, la segunda
      una referencia anafórica, usando `FakeMemoryStore`; (b) una
      preferencia sembrada cambia el texto sin cambiar los `doc_id`
      citados de la pregunta de Billing 2.0; (c) un hecho falso sembrado
      (mismo puente inventado que `TEXTO_P_BILLING_INGENUO`) se degrada
      por `validate_relational_claims` cuando aparece en el texto final.

## 7. Camino agéntico (`agent/strands_tools.py`, `agent/strands_agent.py`, `agent/gate_hook.py`, `agent/tool_trace_hook.py`)

- [x] 7.1 `strands_tools.EvidenceCollector`: agregar campo
      `evidence_tool_called: bool = False` (más `memory_hints: list[MemoryHint]`,
      no pedido literalmente por el plan pero necesario para que
      `ToolTraceHook` pueda armar su línea de `recall_memory` sin
      re-parsear nada).
- [x] 7.2 `strands_tools.build_tools`: `collector.add(...)` (llamado solo
      por los wrappers de `search_documents`/`traverse_graph`) prende
      `evidence_tool_called`. Se agregó `recall_memory` como tercera
      `@tool` cuando `stack.memory is not None and actor_id and session_id`
      — su wrapper llama `recall_memory_fail_open` y solo escribe
      `collector.memory_hints`, nunca `collector.items` ni
      `evidence_tool_called`.
- [x] 7.3 `gate_hook.CoverageGateHook._on_after_tools`: si
      `not self._collector.evidence_tool_called`, agrega
      `TraceStep(stage="gate.cobertura.diferido", ...)` y devuelve sin
      evaluar `evaluate_coverage` ni tocar `event.end_turn`.
- [x] 7.4 `tool_trace_hook._STAGE_BY_TOOL["recall_memory"] =
      "herramienta.recordar_memoria"`. — *implementación real distinta al
      plan: en vez de extender el branching genérico `clave`/`valor` con
      un tercer caso `"consulta"`, `recall_memory` tiene su propia rama
      dedicada (`_memory_recall_detail`) que lee `collector.memory_hints`
      y arma un desglose por `kind` (STM/hechos/preferencias) — el
      argumento crudo de la tool no se expone en la traza.*
- [x] 7.5 Guía sobre cuándo llamar `recall_memory` y qué no hacer con su
      resultado. — *vive en `MEMORY_PROMPT_ADDENDUM` (`agent/memory.py`),
      concatenada condicionalmente a `AGENTIC_SYSTEM_PROMPT` en
      `answer_agentic`, sin editar la constante existente in-place — tal
      como pedía la nota de la propia tarea.*
- [x] 7.6 `strands_agent.answer_agentic`: `actor_id`/`session_id`
      keyword-only; se los pasa a `build_tools`; llama
      `remember_turn_fail_open` después de `_resolve_answer`.
- [ ] 7.7 Caso de regresión con DOS batches separados de `AfterToolsEvent`
      (turno 1: solo `recall_memory`; turno 2: ya `search_documents` con
      el `target` leído de la pista) verificando `gate_hook.cut_turn is
      False` tras el primer batch — *NO existe tal cual. Lo que SÍ cubre
      `tests/test_strands_agent_memory.py` es el mismo invariante con un
      solo batch: `test_memory_only_recall_never_becomes_evidence_and_still_abstains`
      confirma `gate.cobertura.diferido` (no corte) cuando el único tool
      call del batch es `recall_memory`, y
      `test_relational_claim_sourced_from_memory_is_degraded_by_graph_anchoring`
      cubre `recall_memory` + `search_documents` + `traverse_graph` juntos
      en un mismo batch — el escenario literal de dos `AfterToolsEvent`
      separados queda sin test dedicado.*

## 8. CLI y demo (`demo.py`)

- [x] 8.1 `query`: agrega `--actor-id`/`--session-id`. — *más estricto que
      el plan: NINGUNO de los dos sintetiza un default (ni
      `settings.agentcore_actor_id` para actor, ni un UUID para sesión) —
      sin ambos explícitos, memoria queda inactiva para ese turno aunque
      el backend esté configurado (ver el docstring de `query` y de
      `answer_agentic`). Además `--seed-hecho`/`--seed-preferencia`
      (repetibles), no pedidos por este ítem pero sí por 8.2/el resto del
      change.*
- [x] 8.2 Nuevo comando `chat` (REPL de un solo proceso, un único
      `Stack`/sesión para todas las preguntas — soluciona que
      `FakeMemoryStore` no persista entre invocaciones de `query`). Reusa
      `answer`/`answer_agentic` (vía `_invoke_responder`), `_print_trace`,
      `_print_answer`. Comandos especiales `:seed-hecho`/
      `:seed-preferencia`/`:salir`.
- [ ] 8.3 Preguntas guionadas nuevas (`P_MEMORIA_STM`/`_PREFERENCIA`/
      `_HECHO_FALSO`) — NO agregadas. `demo.py` no tiene ningún escenario
      de memoria en su guion (verificado por grep de `P_MEMORIA`); las 10
      preguntas existentes siguen sin cambios.
- [ ] 8.4 Síntesis correspondientes en `build_scripted_llm`/
      `build_agentic_scripted_llm` — NO agregadas (depende de 8.3). El
      `ScriptedLlm` de la CLI hoy nunca decide llamar `recall_memory` por
      su cuenta para ninguna de las 10 preguntas del guion — ver "Probar
      en LOCAL, sin AWS" en `../../README.md`.
- [x] 8.5 Línea de traza de memoria — *implementada como
      `demo.py::_print_memory_trace` con iconos `🧠`
      (`herramienta.recordar_memoria`/`.error`) y `💾`
      (`memoria.guardado`/`.error`), leyendo directo `TraceStep.detail` en
      vez de re-formatear "N pistas recordadas (actor=..., sesión=...)"
      como decía el texto original del ítem — mismo lugar en `_print_trace`
      que las líneas 🔍/🕸️/🛡️ existentes.*
- [x] 8.6 Threading de `actor_id`/`session_id` desde la CLI hacia
      `answer`/`answer_agentic` — *vía `_invoke_responder` +
      `inspect.signature` (encadena los kwargs solo si la firma del
      responder ya los acepta), no un pase directo incondicional: sigue
      siendo necesario mientras el camino fijo no los declare (ver
      sección 6).*
- [ ] 8.7 Verificación multi-turno en `check()` para `P_MEMORIA_STM` — NO
      agregada (depende de 8.3). `check()` sigue siendo únicamente los 10
      casos de un turno, en los dos caminos.
- [ ] 8.8 `tests/test_demo_script.py`: cubrir `--actor-id`/`--session-id`/
      `--seed-hecho`/`--seed-preferencia`/`chat` — NO agregado (verificado
      por grep: cero tests nuevos ahí). `check()` reportando 20/20 sin
      regresión SÍ se verificó a mano (ver sección 11), pero no quedó
      como test explícito de que los escenarios de memoria no lo tocan
      (tampoco existen esos escenarios, ver 8.3).

## 9. Web (`web/api.py`) — opcional, no bloqueante para `check`/`pytest` — NO INICIADO

Verificado: `web/api.py` no tiene ninguna referencia a `actor_id`/
`session_id`/memoria hoy — sigue llamando a `responder(...)` exactamente
como antes de este change. Los 3 sub-ítems quedan intactos.

- [ ] 9.1 `PreguntaIn`: agregar campo opcional `session_id: str | None = None`.
- [ ] 9.2 `_generate_events`: pasar `actor_id`/`session_id` (con
      `actor_id` fijo de `settings.agentcore_actor_id` o expuesto también
      en el body) a `responder(...)`. Confirmar (ya verificado en
      `design.md`) que `_eventos_de_paso` no necesita cambios: cualquier
      `herramienta.*` nuevo cae en `TOOL_CALL_*`, cualquier otra etapa en
      `STATE_DELTA`, automáticamente.
- [ ] 9.3 `tests` (si existen para `web/api.py`; si no, smoke test manual
      documentado en el PR) verificando que un `POST /api/preguntar` sin
      `session_id` se comporta idéntico a hoy.

## 10. Documentación y configuración

- [x] 10.1 `.env.example`: agregadas las tres variables nuevas
      (`SECOND_BRAIN_MEMORY_ENABLED=false`, `SECOND_BRAIN_AGENTCORE_MEMORY_ID=`
      vacío con comentario de que es específico de cuenta,
      `SECOND_BRAIN_AGENTCORE_ACTOR_ID=demo-speaker`) — *en su propia
      sección `# --- Memoria (opcional, ...) ---`, no dentro de "Modo AWS"
      como decía el ítem, porque aplica a los DOS modos (local y aws).*
- [ ] 10.2 `corpus/README.md`: entradas para los escenarios de memoria en
      la tabla de contrato — NO agregadas (verificado: cero menciones de
      "memoria" en `corpus/README.md`); depende de que existan las
      preguntas guionadas de la tarea 8.3.
- [x] 10.3 (agregado en esta pasada, no estaba en el plan original)
      `../../README.md`: sección "Memoria del agente" — las tres capas,
      la regla "memoria es pista, nunca evidencia" con el ejemplo real de
      la memoria mentirosa degradada, activación (env vars + CLI),
      comandos reales verificados en modo local (`query --agentic
      --seed-hecho ...`, `chat --agentic`) y contra AWS real, y la nota de
      consistencia eventual. `../README.md` (infra): fila `AgentMemoryIdOutput`
      en la tabla de outputs, con el gap real de que `despues-del-deploy.py`
      todavía no la mapea sola.

## 11. Cierre

- [x] 11.1 `pytest -q` completo (venv `.venv312`) → **135 passed** (116
      base + 19 nuevos: 13 en `tests/test_memory_stores.py`, 6 en
      `tests/test_strands_agent_memory.py`), 0 rojos. Re-verificado en esta
      pasada de documentación (no solo confiado en el reporte de otro
      workstream).
- [ ] 11.2 `demo.py check` sigue en 20/20 sin regresión (no re-ejecutado en
      esta pasada, pero nada de lo tocado por los workstreams de memoria
      afecta las 10 preguntas existentes) — el "nuevo caso multi-turno de
      memoria en verde" de este ítem no existe porque 8.3/8.7 no se
      implementaron.
- [x] 11.3 Verificado en esta pasada:
      `SECOND_BRAIN_AGENTCORE_MEMORY_ID=` sigue vacío en `.env.example`;
      el `.env` local (con un id de cuenta real en otra variable, no de
      memoria) está en `.gitignore` y NO está trackeado
      (`git ls-files .env` no devuelve nada); `git grep` sobre archivos
      trackeados por `arn:aws:...:<12 dígitos>:` y por IDs de cuenta de 12
      dígitos sueltos no encontró ninguno fuera de plantillas con
      `{region}`/`{self._region}` sin resolver.
