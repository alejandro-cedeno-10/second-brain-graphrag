# Plan — migración total del grafo al GraphRAG Toolkit

Objetivo aprobado: que el grafo lo construya y lo recorra **el toolkit de AWS
Labs**, no código propio. Reemplaza `graph/extraction.py` (regex) y
`graph/traversal.py` (BFS propio) por `LexicalGraphIndex` + los retrievers
del toolkit, y el esquema `Entidad`/`RELACION` por el propio del toolkit.

Costos aceptados al decidir el alcance, **revisados tras la Fase 0**:

| Costo asumido | Estado real |
|---|---|
| La demo requiere Bedrock; se termina el ensayo offline | ❌ **evitable** — `extract()`/`build()` + `FileBasedDocs` permiten extraer una vez con LLM y construir offline en cada ensayo |
| Las 20 verificaciones dejan de ser deterministas | ❌ **evitable** — por el mismo mecanismo |
| ~61 tests a reescribir | ✅ **se mantiene** — el esquema cambia y hay que adaptarlos |

Sigue en pie que hace falta **un LLM real una vez** (al generar los
artefactos de extracción), pero no en cada corrida ni el día de la charla.

## Estado de partida (auditado, no supuesto)

| Capa | Hoy | Tras la migración |
|---|---|---|
| Conexión / transporte | ✅ **ya es del toolkit** — `GraphStoreFactory.for_graph_store("falkordb://…")` + contrib, y todo el Cypher sale por `execute_query` (`adapters/local/falkor_graph_store.py:79`) | sin cambio |
| Cypher | ❌ propio, a mano (`falkor_graph_store.py:91,121,141`) | primitivas del toolkit |
| Extracción | ❌ propia, regex de verbos (`graph/extraction.py:50`) | `LexicalGraphIndex.extract_and_build` |
| Traversal | ❌ propio, BFS con guarda anti-hub (`graph/traversal.py:88`) | retrievers del toolkit |
| Esquema | ❌ `Entidad` / `RELACION` | `Document`/`Chunk`/`Topic`/`Statement`/`Fact`/`Entity` |
| `extract_and_build` | integrado pero **inerte** (`use_real_toolkit` nunca se activa) | camino principal |

## Contrato del frontend que hay que preservar

La UI depende del grafo por seis puntos. Los cinco primeros son de forma; el
sexto es de **identidad** y es el que la migración rompe de raíz.

| # | Punto | Exige |
|---|---|---|
| 1 | `GET /api/preguntas` | `demo._VERIFICATIONS` |
| 2 | SSE `STATE_DELTA` / `respuesta.final` | `metadata.grafo` con forma de `Path` |
| 3 | `GET /api/grafo/ultimo` | misma forma |
| 4 | `GET /api/salud` | `graph_store.query("RETURN 1")` — Cypher crudo |
| 5 | `PanelGrafo.vue:24` (cytoscape) | `direcciones[i]` por arista (flecha) y `provenance[i]` (click) |
| 6 | **`web/api.py:193`** | **`_entity_from_doc_id()` = `Path(doc_id).stem`** |

**El punto 6.** La UI saca la raíz del subgrafo del paso `objetivos.resueltos`
(doc ids tipo `servicios/pagos.md`), le aplica `.stem` → `pagos`, y asume que
ese string **es un id de nodo del grafo**. Hoy es cierto porque el extractor
propio solo admite entidades cuyo id es el nombre del documento
(`graph/extraction.py:130`). El toolkit extrae entidades con un LLM y les pone
los nombres que el LLM decida (`Core Billing`, `el servicio de pagos`), con
los documentos como nodos `Document` aparte. **Esa identidad desaparece** — y
con ella el punto 6, la raíz del cytoscape, `blast_radius` y `_verify_p2`
(`demo.py:1528`, que exige citar exactamente `{pagos, notificaciones,
reportes-backend}`).

Hace falta una **capa de resolución** entidad↔documento que hoy no existe.

## Fases

### Fase 0 — Descubrir la API real ✅ COMPLETA

Verificado contra el paquete instalado (`graphrag-lexical-graph 3.19.1`,
contrib FalkorDB `1.0.1`, `llama-index-core 0.14.24`), no contra
documentación ni memoria:

```bash
docker build --target base -t sb-base .
docker run --rm -v "$(pwd)/scripts:/app/scripts:ro" sb-base python scripts/introspect_toolkit.py
```

**Incógnita 1 — camino de lectura: RESUELTA.**
`LexicalGraphQueryEngine.for_traversal_based_search(graph_store, vector_store, retrievers=[...])`.
Retrievers disponibles: `EntityBasedSearch`, `EntityNetworkSearch`,
`EntityContextSearch`, `ChunkBasedSearch`, `TopicBasedSearch`, `BeamSearch`,
`CompositeTraversalBasedRetriever`. Los de `for_semantic_guided_search` viven
bajo `retrievers.deprecated` → el camino soportado es el traversal-based.

**Incógnita 2 — `Path.directions`: RESUELTA, sobrevive.**
`Fact` es un triple dirigido: `['complement', 'factId', 'object',
'predicate', 'statementId', 'subject']`. Y el Cypher del builder
(`entity_relation_graph_builder.py:78-82`) escribe la arista dirigida:

```cypher
MERGE (subject:`__Entity__` {entityId: params.s_id})
MERGE (object:`__Entity__`  {entityId: params.o_id})
MERGE (subject)-[r:`__RELATION__` {value: params.p}]->(object)
```

Es **la misma forma** que el `MERGE (a)-[r:RELACION {tipo: $tipo}]->(b)` de
`falkor_graph_store.py:121`: un único tipo de arista con el predicado como
propiedad. El código del builder que crearía aristas tipadas está comentado
— el toolkit tomó la misma decisión de diseño que este repo.

**Incógnita 3 — vector store local: RESUELTA, no queda atado a AWS.**
`VectorStoreFactory` ofrece `NeptuneAnalyticsVectorIndexFactory`,
`OpenSearchVectorIndexFactory`, **`PGVectorIndexFactory`** (Postgres +
pgvector, corre en Docker), `S3VectorIndexFactory` y
`DummyVectorIndexFactory`. Además `LexicalGraphIndex(vector_store=None)` es
opcional para **indexar** — solo `LexicalGraphQueryEngine` lo exige.

**Incógnita 4 — provenance por salto: RESUELTA, requiere join.**
No es una propiedad de la arista. La cadena es
`__Fact__ -[:__SUPPORTS__]-> __Statement__ (.chunkId) -> __Chunk__
-[:__EXTRACTED_FROM__]-> __Source__`. Es el único punto del contrato del
frontend que cuesta trabajo real.

#### Esquema real del toolkit (extraído del Cypher de los builders)

| Nodo | Clave | Propiedades |
|---|---|---|
| `__Source__` | `sourceId` | metadata del documento |
| `__Chunk__` | `chunkId` | `value` (texto) |
| `__Statement__` | `statementId` | `value`, `details` |
| `__Fact__` | `factId` | `relation`, `value` |
| `__Entity__` | `entityId` | `value`, `search_str`, `class` |
| `__SYS_Class__` | `sysClassId` | `value`, `count` (grafo resumen) |

Aristas: `__RELATION__{value}` (Entity→Entity), `__SUPPORTS__` (Fact→Statement),
`__EXTRACTED_FROM__` (Chunk→Source), `__SUBJECT__`/`__OBJECT__` (Entity→Fact),
`__SYS_RELATION__{value,count}` (Class→Class).

#### 🐛 Bug latente encontrado en el código actual

`adapters/graphrag_toolkit.py:113` hace
`LlamaIndexSettings.llm = LlmPortAsLlamaIndexLlm(...)`, pero **el toolkit no
lee `llama_index.Settings.llm`**: usa su propio `GraphRAGConfig.extraction_llm`,
cuyo default construye un `BedrockConverse`. Si `use_real_toolkit` se hubiera
activado, habría intentado Bedrock e ignorado el shim. Nunca se notó porque el
camino nunca corre.

Cableado correcto (verificado en el contenedor — acepta la instancia sin
envolverla):

```python
GraphRAGConfig.extraction_llm = LlmPortAsLlamaIndexLlm(llm_port=llm)
```

Corolario: la extracción **no está atada a Bedrock**. Cualquier LLM de
LlamaIndex sirve, incluido el `LlmPort` propio detrás del shim.

#### 🎯 Cómo se conserva el determinismo (nativo del toolkit)

`extract()` y `build()` son métodos separados, y `extract()` acepta un
`handler: NodeHandler`. `indexing.load` expone **`FileBasedDocs(docs_directory,
collection_id=...)`**, que es a la vez `NodeHandler` (`accept`) y fuente
(`docs()`):

```python
docs = FileBasedDocs(docs_directory='corpus_extraido')
index.extract(documentos, handler=docs)   # UNA vez, con LLM real → JSON a disco
index.build(docs.docs())                  # offline, sin LLM, en cada ensayo
```

**El grafo lo construye la librería, de forma determinista y sin LLM el día
de la charla**, y los artefactos de extracción se versionan en git. Esto
elimina dos de los tres costos que se habían aceptado: el ensayo sigue
offline y las 20 verificaciones siguen siendo deterministas.

### Fase 2 — Ejecutada sobre 2 documentos: qué extrae el toolkit de verdad

Extracción real con `amazon.nova-pro-v1:0` sobre `frontends/dashboard.md` y
`arquitectura/decisiones.md`, y `build()` **100% offline verificado** (sin
credenciales, sin región, con un LLM no-op que habría lanzado `RuntimeError`
si el build lo tocaba):

```
source: 2 · chunk: 8 · topic: 8 · statement: 77 · fact: 121 · entity: 40
globalConnectivity: 0.19008
```

El mecanismo de dos fases **funciona**: el grafo lo construye la librería,
sin invocar modelos. Pero el CONTENIDO que extrae rompe supuestos del guion:

**1. El vocabulario de relaciones es prosa libre, no controlado.**
Los predicados salen como frases en inglés generadas por el LLM, no del
vocabulario cerrado `CONSUME`/`DEPENDE_DE`/`LLAMA_A`. Para un mismo par de
entidades llegó a emitir tres predicados distintos que afirman lo mismo.
Consecuencia directa: `agent/guards.py::validate_relational_claims` (el
anclaje al grafo, `🔗 anclaje` en `--trace`) no tiene contra qué matchear.

**2. Entidades duplicadas por clasificación.** La misma entidad aparece como
dos nodos cuando el LLM le asigna clasificaciones distintas en documentos
distintos. El traversal devuelve caminos duplicados.

**3. Clasificación inconsistente del mismo tipo de documento.** Documentos
del mismo tipo recibieron tres clasificaciones diferentes entre sí.

**4. Entidades-ruido que actúan como hub.** El extractor promueve a entidad
cosas que no son servicios (la organización entera, equipos, personas,
atributos, cabeceras HTTP). Con 2 documentos ya aparecen; con 49 la de mayor
grado infla cualquier blast radius. La guarda anti-hub de `traversal.py` deja
de ser una anécdota de la charla y pasa a ser un requisito de funcionamiento.

**5. La identidad `entidad == nombre de archivo` se cumple a veces.** Algunas
entidades coinciden con el stem de su documento y muchas no. El gancho para
resolverlo existe: `__Source__` conserva la metadata que se le pasa
(`source`, `stem`), verificado en el grafo.

**Conclusión honesta:** el problema no es el determinismo — eso está
resuelto. El problema es que la extracción del toolkit produce un grafo
**semánticamente distinto** del que el guion de la charla asume. Ningún
snapshot arregla eso: hay que reescribir las expectativas del guion (las 20
verificaciones), el guard de anclaje y la resolución de entidades.

### Fase 2 completa — corpus entero (49 docs), medido

```
source: 49 · chunk: 136 · topic: 144 · statement: 1355 · fact: 2054 · entity: 495
```
Contra el baseline propio: **14 entidades / 19 relaciones**. 35× más entidades.
Artefactos de extracción: 136 JSON, 3.9 MB (versionables). `build()` offline
verificado sobre el corpus completo.

#### 🔴 La pregunta de blast radius se rompe: la guarda anti-hub corta

```
grado directo del servicio consultado = 44   (MAX_DEGREE_DEFAULT = 20)
-> la guarda CORTA la expansión => blast_radius devuelve 0 caminos
```

Esa verificación exige cobertura `suficiente` citando los tres módulos
dependientes. Con 0 caminos el agente **abstiene**. Y no es un caso aislado:
**8 entidades** superan o rozan el umbral, con grados entre 21 y 36:


Las 3 entidades esperadas **sí aparecen** entre los vecinos (con provenance y
sentido correctos), así que el adapter funciona: lo que falla es que el grafo
del toolkit es demasiado denso para los umbrales del guion.

#### 🔴 Relaciones NEGADAS guardadas como aristas positivas

Sobre el corpus, el pipeline emitió **dos aristas cuyo predicado niega la
relación** (del tipo "no llama a" / "desacoplado de") entre un par de
servicios que el documento fuente describe como NO dependientes.

El extractor propio tiene `_NEGATION_PATTERN` (`extraction.py:44`)
exactamente para no crear estas aristas. El pipeline del toolkit no tiene esa
guarda: convierte una negación del documento en una arista afirmativa. Si
la síntesis
verbaliza ese salto como dependencia, **el sistema afirma lo contrario de lo
que dice el corpus**.

Es una **regresión de garantía**, no ruido estético: la charla promete
"no inventar", y `ports.py:66-74` documenta que invertir el sentido de un
salto es inaceptable. Reescribir las expectativas del guion no lo arregla —
haría falta una capa de filtrado de predicados negados, que es código propio
otra vez, sobre la salida del toolkit.

### Fase 1 — Camino de lectura sobre el esquema del toolkit ✅

`adapters/toolkit_graph_store.py` — `GraphStorePort` sobre
`__Entity__`/`__RELATION__`, con `directions` nativo (`startNode(r)`) y
provenance por join `__Fact__ → __Statement__ → __Chunk__ → __Source__.stem`.
Topología verificada empíricamente contra el grafo construido, no supuesta.
`upsert_nodes`/`upsert_edges` levantan `NotImplementedError`: escribir es
del toolkit.

### Fase 3 — Resolución entidad↔documento ✅ (núcleo)

`ToolkitGraphStore.resolve_entity(stem)`: match exacto si existe, si no las
entidades más mencionadas por ese documento. Medido:
`dashboard`/`reportes-backend`/`core-billing` resuelven exacto;
`decisiones` → `['notificaciones', 'core-billing', 'conciliación']`.

### Fase 5 — CI ✅ arreglado

Quitado `working-directory: demo` y el filtro `paths: demo/**` (no existe esa
carpeta: el proyecto es la raíz). Comentario actualizado a
`tests/test_graph.py::test_blast_radius_against_real_falkordb`.

### Bugs arreglados (independientes de la migración)

1. `graph/build.py` — `load_chunks_from_corpus` ahora excluye `README.md`,
   igual que `ingestion.load_corpus`. Eliminaba la arista
   `billing-2-0 -DEPENDE_DE-> auth-cache` con provenance `README`.
2. `adapters/graphrag_toolkit.py` — `GraphRAGConfig.extraction_llm` en vez de
   `llama_index.Settings.llm` (que el toolkit ignora), más
   `vector_store="dummy://"` (obligatorio en la práctica).

Suite completa tras los fixes: **154 passed, 2 skipped**.

### Fase 1 (histórico) — diseño original

Reimplementar `GraphStorePort.neighbors` (y con él `blast_radius`) contra
`Entity`/`Fact`, derivando `directions` de la orientación del `Fact`. Mantener
la forma de `Path` intacta: es lo que sostiene los puntos 2, 3 y 5.

### Fase 2 — Extracción por el toolkit

`extract_and_build` como camino principal. Requiere `BedrockLlm`; el shim
`LlmPortAsLlamaIndexLlm` (`adapters/graphrag_toolkit_llm.py`) hoy solo
implementa `complete`/`stream_complete` **síncronos** — hay que verificar si
el pipeline del toolkit pide `acomplete`/`chat` y completarlo.

### Fase 3 — Resolución entidad↔documento

Resolver el punto 6: mapear el objetivo (doc id) a la entidad que el LLM
extrajo. Sin esto la UI no encuentra la raíz del subgrafo.

### Fase 4 — Determinismo para el guion y CI

Sin esto, la charla depende de que el LLM extraiga hoy igual que ayer.
Propuesta: **snapshot** de la extracción del toolkit (grabar una vez la
salida real de `extract_and_build` y reproducirla en tests/CI). Conserva la
librería como productora del grafo y devuelve la reproducibilidad al ensayo.

### Fase 5 — CI (hoy inerte)

`.github/workflows/ci.yml` tiene `working-directory: demo` y
`paths: - "demo/**"`, pero el proyecto **es** la raíz del repo — no hay
carpeta `demo/`. El filtro nunca matchea (no corre en push ni PR) y por
`workflow_dispatch` fallaría. El comentario referencia `tests/test_grafo.py`,
que ya no existe.

### Fase 6 — Validación end-to-end

`pytest` completo, `docker compose build`, build del Vue y las 10 preguntas
por las dos vías contra la UI.

## Entorno — estado de esta máquina

| Requisito | Estado |
|---|---|
| Python `>=3.10,<3.13` | ❌ solo 3.9.6; sin `pyenv`/`uv`/Homebrew Python |
| `pip` | ❌ no está en el `PATH` |
| Docker daemon | ⚠️ CLI ok, daemon apagado |
| `node`/`pnpm`/`npm` | ❌ no instalados |
| `web/ui/dist` | ❌ nunca se buildeó |

Todo se corre **dentro de Docker**, que es el camino oficial del README.

---

## Resultado final — migración completa y medida en local

Los dos backends coexisten y **los dos dan 20/20** en `demo.py check`
(las 10 preguntas × pipeline fijo y loop agéntico):

| | `propio` (default) | `toolkit` |
|---|---|---|
| Quién construye el grafo | `graph/extraction.py` (patrones) | `LexicalGraphIndex` del toolkit |
| Esquema | `Entidad`/`RELACION` | `__Entity__`/`__RELATION__` |
| `demo.py check` | **20/20** | **20/20** |
| Entidades | 14 | 495 (7 tras proyectar a las citables) |
| Grado máx. tras filtros | — | 11 (era 61 sin filtrar) |
| Panel de grafo (P2, `max_hops=3`) | 9 nodos / 11 aristas / 4 KB | 17 nodos / 56 aristas / 80 KB |
| LLM el día de la charla | no | **no** (`build()` offline) |

Suite: **164 passed, 2 skipped**. `ruff` limpio sobre `src tests demo.py scripts`.

### Cómo se conservó la calidad del guion

`ToolkitGraphStore.neighbors` aplica tres filtros, cada uno contra un
comportamiento medido de la extracción por LLM:

1. **Negados** — sin esto, una arista cuyo predicado NIEGA la relación se
   publica como dependencia: la afirmación inversa a la del corpus.
2. **Proyección a entidades con documento** — sin esto `core-billing` tiene
   grado 44 y `auth-cache` 61, la guarda anti-hub corta y P2 **abstiene**.
3. **Dedup por (vecino, sentido)** — el toolkit emite hasta cuatro
   predicados sinónimos para el mismo par de entidades.

### Lo que la migración cuesta, medido

- **El panel de grafo se densifica**: 11 → 56 aristas. Sigue siendo legible,
  pero es más ruidoso que el diagrama limpio de hoy. Se puede bajar con
  `max_hops` (1 → 7 aristas, 2 → 39, 3 → 56) en `web/api.py::_calcular_subgrafo`.
- **P2 pierde fuerza pedagógica**: en el grafo del toolkit los tres módulos
  son vecinos DIRECTOS de `core-billing` (el LLM aplanó la transitividad —
  llegó a emitir un predicado que nombra la transitividad de forma literal).
  La respuesta
  es correcta, pero "traversal multi-hop" deja de ser lo que la demuestra.
- **El vocabulario deja de ser controlado**: las relaciones son prosa
  (`REACTS TO`, `PUBLISHES TO`, `INVOLVES`), no `CONSUME`/`DEPENDE_DE`.
- **Hace falta un LLM real una vez** para regenerar los artefactos si cambia
  el corpus (3.9 MB de JSON, hoy en `.data/` y **gitignorados**: si el ensayo
  offline depende de ellos, hay que versionarlos).

### Pendiente

- Versionar `.data/extraccion_toolkit/` (o moverlo fuera de `.gitignore`).
- `README.md` del repo sigue describiendo solo el camino `propio`.
- Los docs que el README cita y no existen: `SPIKE_COMPATIBILIDAD.md`,
  `PLAN_SERVICIOS_REALES.md`.

---

## 🐛 Bug crítico encontrado al validar la UI con un LLM real

`adapters/aws/bedrock_llm.py` emitía bloques `guardContent` (contextual
grounding) siempre que el mensaje trajera `grounding_source` + `query`,
mientras `guardrailConfig` solo se agregaba si había `guardrail_id`.
Converse rechaza esa combinación con un error DURO:

```
ValidationException: The guardrail can't assess the content in the
guardContent field. The guardrail configuration is missing.
```

`bedrock_guardrail_id` es `None` por default, así que **cualquier corrida en
modo `aws` sin `SECOND_BRAIN_BEDROCK_GUARDRAIL_ID` fallaba en toda síntesis
que pasara grounding+query** — el camino principal de la demo. Nunca se
detectó porque el ensayo local usa `ScriptedLlm` y nunca llega a Converse.

Arreglado: `guardContent` solo se emite si hay guardrail configurado
(`_to_converse_message` pasó de `@staticmethod` a método de instancia).
Cubierto por `tests/test_bedrock_llm.py`.

## Modo híbrido: LLM real sin escribir en AWS

`SECOND_BRAIN_LOCAL_LLM=bedrock` reemplaza SOLO el `LlmPort` del modo local
por `BedrockLlm`, dejando embeddings, vector store y rerank locales. Permite
ver en la UI texto generado de verdad **sin que nada se escriba en AWS**: la
inferencia de Bedrock no crea recursos, a diferencia de
`SECOND_BRAIN_MODE=aws`, que escribe embeddings en S3 Vectors.

⚠️ Con este modo `demo.py check` deja de tener sentido: las 20 verificaciones
afirman contenido del guion (`ScriptedLlm`), no lo que redacte un modelo.

⚠️ La imagen `aws` del Dockerfile trae `ENV SECOND_BRAIN_MODE=aws`: correrla
sin pensarlo va a modo AWS y su `ingest` escribe en S3 Vectors.
