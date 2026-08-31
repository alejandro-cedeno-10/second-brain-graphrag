# RENAMES.md — mapa completo español → inglés

Refactor de identificadores (funciones, clases, dataclasses, enums,
variables, parámetros, atributos, constantes, archivos, tests) a inglés,
manteniendo docstrings, comentarios, mensajes de traza, textos de UI y el
guion de preguntas/respuestas de la demo en español.

## Archivos y carpetas renombrados

| Ruta vieja | Ruta nueva |
|---|---|
| `src/second_brain/ingesta.py` | `src/second_brain/ingestion.py` |
| `src/second_brain/grafo/` | `src/second_brain/graph/` |
| `src/second_brain/grafo/extraccion.py` | `src/second_brain/graph/extraction.py` |
| `src/second_brain/agente/` | `src/second_brain/agent/` |
| `src/second_brain/agente/_texto.py` | `src/second_brain/agent/facets.py` |
| `src/second_brain/agente/herramientas.py` | `src/second_brain/agent/tools.py` |
| `src/second_brain/agente/sintesis.py` | `src/second_brain/agent/synthesis.py` |
| `src/second_brain/agente/orquestador.py` | `src/second_brain/agent/orchestrator.py` |
| `src/second_brain/adapters/local/_texto.py` | `src/second_brain/adapters/local/tokenization.py` |
| `tests/test_agente.py` | `tests/test_agent.py` |
| `tests/test_grafo.py` | `tests/test_graph.py` |
| `tests/test_guion_demo.py` | `tests/test_demo_script.py` |

`src/second_brain/grafo/traversal.py` se mantuvo (ya estaba en inglés, según consigna).
No se tocó nada en `corpus/**`, `web/ui/**` (frontend Vue), ni `infra/**`
(fuera del alcance pedido).

## `src/second_brain/ports.py`

| Viejo | Nuevo |
|---|---|
| `Chunk.documento_id` | `Chunk.document_id` |
| `Chunk.texto` | `Chunk.text` |
| `Hit.texto` | `Hit.text` |
| `ScoredDoc.texto` | `ScoredDoc.text` |
| `Path.nodos` | `Path.nodes` |
| `Path.relaciones` | `Path.relations` |
| `Path.direcciones` | `Path.directions` |
| `Cita` | `Citation` |
| `Cita.documento` | `Citation.document` |
| `Cita.fragmento` | `Citation.fragment` |
| `PasoTraza` | `TraceStep` (campos `etapa`/`detalle` → `stage`/`detail`, ver "Ronda 2" más abajo) |
| `Respuesta` | `Answer` |
| `Respuesta.texto` | `Answer.text` |
| `Respuesta.citas` | `Answer.citations` |
| `Respuesta.abstencion` | `Answer.abstained` |
| `Respuesta.traza` | `Answer.trace` |
| `ToolCall.nombre` | `ToolCall.name` |
| `ToolCall.argumentos` | `ToolCall.arguments` |
| `LlmResponse.texto` | `LlmResponse.text` |
| `LlmResponse.detiene_por` | `LlmResponse.stop_reason` |
| `LlmResponse.uso_tokens` | `LlmResponse.token_usage` |
| `VectorStorePort.search(..., filtro=)` | `search(..., filter=)` |
| `GraphStorePort.upsert_nodes(nodos)` | `upsert_nodes(nodes)` |
| `GraphStorePort.upsert_edges(aristas)` | `upsert_edges(edges)` |
| `GraphStorePort.neighbors(entidad, max_saltos)` | `neighbors(entity, max_hops)` |
| `RerankPort.rerank(pregunta, documentos, ...)` | `rerank(question, documents, ...)` |

## `src/second_brain/config.py`

| Viejo | Nuevo |
|---|---|
| `_PREFIJO` | `_PREFIX` |
| `_env(nombre, ...)` | `_env(name, ...)` |
| `Settings.modo` | `Settings.mode` |
| `MemoryVectorStore(ruta_persistencia=...)` | `MemoryVectorStore(persistence_path=...)` |

## `src/second_brain/ingestion.py` (ex `ingesta.py`)

| Viejo | Nuevo |
|---|---|
| `Documento` | `Document` |
| `Documento.titulo` | `Document.title` |
| `Documento.cuerpo` | `Document.body` |
| `IndiceStats` | `IndexStats` |
| `IndiceStats.documentos` | `IndexStats.documents` |
| `IndiceStats.dim_embeddings` | `IndexStats.embeddings_dim` |
| `cargar_corpus` | `load_corpus` |
| `_cargar_documento` | `_load_document` |
| `_parsear_frontmatter` | `_parse_frontmatter` |
| `chunkear` | `chunk_document` |
| `_parrafos` | `_paragraphs` |
| `_piezas_acotadas` | `_bounded_pieces` |
| `_empacar_piezas` | `_pack_pieces` |
| `_crear_chunk` | `_create_chunk` |
| `indexar` | `index` |
| `_PATRON_FRONTMATTER` | `_FRONTMATTER_PATTERN` |
| `_PATRON_SECCION` | `_SECTION_PATTERN` |

## `src/second_brain/retrieval.py`

| Viejo | Nuevo |
|---|---|
| `buscar_semantico` | `search_semantic` |
| `IndiceLexico` | `LexicalIndex` |
| `IndiceLexico.frecuencias` | `LexicalIndex.frequencies` |
| `IndiceLexico.longitudes` | `LexicalIndex.lengths` |
| `IndiceLexico.longitud_promedio` | `LexicalIndex.average_length` |
| `construir_indice_lexico` | `build_lexical_index` |
| `buscar_lexico` | `search_lexical` |
| `_puntuar_bm25` | `_score_bm25` |
| `fusion_rrf` | `fuse_rrf` |
| `recuperar` | `retrieve` |
| `resolver_objetivos` | `resolve_targets` |
| `_candidatos_por_doc_id` | `_candidates_by_doc_id` |
| `_nombre_corto` | `_short_name` |
| `_coincidencias_lexicas_fuertes` | `_strong_lexical_matches` |
| `_CAP_OBJETIVOS_DEFAULT` | `_TARGETS_CAP_DEFAULT` |
| `_TOP_K_CANDIDATOS_OBJETIVO` | `_TOP_K_TARGET_CANDIDATES` |

## `src/second_brain/adapters/local/tokenization.py` (ex `_texto.py`)

| Viejo | Nuevo |
|---|---|
| `tokenizar` | `tokenize` |
| `_PATRON_TOKEN` | `_TOKEN_PATTERN` |

## `src/second_brain/adapters/local/fake_embeddings.py`

| Viejo | Nuevo |
|---|---|
| `_balde_y_signo` | `_bucket_and_sign` |
| `FakeEmbeddings._embed_uno` | `FakeEmbeddings._embed_one` |

## `src/second_brain/adapters/local/fake_rerank.py`

| Viejo | Nuevo |
|---|---|
| `FakeRerank._puntuar` | `FakeRerank._score` |

## `src/second_brain/adapters/local/scripted_llm.py`

| Viejo | Nuevo |
|---|---|
| `CondicionScripted` | `ScriptedCondition` |
| `ReglaScripted` | `ScriptedRule` |
| `ReglaScripted.cuando` | `ScriptedRule.when` |
| `ReglaScripted.respuesta` | `ScriptedRule.response` |
| `ScriptedLlm(reglas=...)` | `ScriptedLlm(rules=...)` |
| `ScriptedLlm(secuencia=...)` | `ScriptedLlm(sequence=...)` |
| `ScriptedLlm(respuesta_por_defecto=...)` | `ScriptedLlm(default_response=...)` |
| `self._reglas` / `self._secuencia` / `self._indice_secuencia` / `self._respuesta_por_defecto` | `self._rules` / `self._sequence` / `self._sequence_index` / `self._default_response` |

## `src/second_brain/adapters/local/falkor_graph_store.py` y `memory_graph_store.py`

| Viejo | Nuevo |
|---|---|
| `upsert_nodes(nodos)` | `upsert_nodes(nodes)` |
| `upsert_edges(aristas)` | `upsert_edges(edges)` |
| `neighbors(entidad, max_saltos)` | `neighbors(entity, max_hops)` |
| `FalkorGraphStore._convertir_camino` | `FalkorGraphStore._convert_path` |
| `MemoryGraphStore._Arista` | `MemoryGraphStore._Edge` |
| `_Arista.destino/tipo/propiedades/directa` | `_Edge.destination/type/properties/forward` |
| `MemoryGraphStore._adyacencia` | `MemoryGraphStore._adjacency` |
| `MemoryGraphStore._agregar_direccion` | `MemoryGraphStore._add_direction` |
| `MemoryGraphStore._explorar` | `MemoryGraphStore._explore` |

Nota de diseño: los dict keys que viajan como payload de grafo (`origen`,
`destino`, `tipo`, `documento_id`, `fragmento`) se dejaron en español a
propósito — son el esquema de datos que comparten `graph/build.py`,
`falkor_graph_store.py`, `memory_graph_store.py` y `neptune_graph_store.py`
(equivalente a nombres de propiedad de un grafo openCypher), no identificadores
Python locales a un solo módulo.

## `src/second_brain/adapters/local/memory_vector_store.py`

| Viejo | Nuevo |
|---|---|
| `MemoryVectorStore(ruta_persistencia=...)` | `MemoryVectorStore(persistence_path=...)` |
| `_ruta_persistencia` / `_ruta_vectores` / `_ruta_metadata` | `_persistence_path` / `_vectors_path` / `_metadata_path` |
| `_ids` / `_textos` / `_metadatos` / `_vectores` | `_ids` / `_texts` / `_metadatas` / `_vectors` |
| `_upsert_uno` | `_upsert_one` |
| `search(..., filtro=...)` | `search(..., filter=...)` |
| `_similitud_coseno` | `_cosine_similarity` |
| `_guardar` / `_cargar` | `_save` / `_load` |

## `src/second_brain/adapters/aws/*.py`

| Viejo | Nuevo |
|---|---|
| `_obtener_cliente` | `_get_client` |
| `BedrockRerank._ARN_MODELO_RERANK` (`_ARN_MODELO_RERANK`) | `_RERANK_MODEL_ARN` |
| `BedrockRerank._como_fuente` | `BedrockRerank._as_source` |
| `BedrockLlm._armar_argumentos` | `BedrockLlm._build_arguments` |
| `BedrockLlm._a_llm_response` | `BedrockLlm._to_llm_response` |
| `NeptuneGraphStore._convertir_camino` | `NeptuneGraphStore._convert_path` |
| `NeptuneGraphStore._ejecutar_opencypher` | `NeptuneGraphStore._run_opencypher` |
| `S3VectorsStore._como_vector` | `S3VectorsStore._as_vector` |
| `S3VectorsStore._a_hit` | `S3VectorsStore._to_hit` |
| `S3VectorsStore.search(..., filtro=...)` | `search(..., filter=...)` |

## `src/second_brain/graph/build.py`

| Viejo | Nuevo |
|---|---|
| `cargar_chunks_de_corpus` | `load_chunks_from_corpus` |
| `_cargar_chunk` | `_load_chunk` |
| `_separar_frontmatter` | `_split_frontmatter` |
| `_partir_linea_frontmatter` | `_split_frontmatter_line` |
| `construir_grafo` | `build_graph` |
| `construir_grafo(..., usar_llm=...)` | `build_graph(..., use_llm=...)` |
| `_resolver_chunks` | `_resolve_chunks` |
| `_upsert_grafo` | `_upsert_graph` |

## `src/second_brain/graph/extraction.py` (ex `extraccion.py`)

| Viejo | Nuevo |
|---|---|
| `NodoStatement` | `StatementNode` |
| `NodoStatement.texto` | `StatementNode.text` |
| `NodoStatement.documento_id` | `StatementNode.document_id` |
| `Relacion` | `Relation` |
| `Relacion.origen` | `Relation.source` |
| `Relacion.tipo` | `Relation.type` |
| `Relacion.destino` | `Relation.target` |
| `Relacion.documento_id` | `Relation.document_id` |
| `Relacion.fragmento` | `Relation.fragment` |
| `GrafoLexico` | `LexicalGraph` |
| `GrafoLexico.linaje` | `LexicalGraph.lineage` |
| `GrafoLexico.entidades` | `LexicalGraph.entities` |
| `GrafoLexico.relaciones` | `LexicalGraph.relations` |
| `extraer_entidades_y_relaciones` | `extract_entities_and_relations` |
| `_extraer_por_patrones` | `_extract_by_patterns` |
| `_extraer_relaciones_de_oracion` | `_extract_relations_from_sentence` |
| `_agregar_relacion` | `_add_relation` |
| `_dividir_en_oraciones` | `_split_into_sentences` |
| `_extraer_con_llm` | `_extract_with_llm` |
| `_agregar_relacion_llm` | `_add_llm_relation` |
| `_parsear_relaciones_json` | `_parse_relations_json` |
| `_PATRON_BLOQUE_CODIGO` | `_CODE_BLOCK_PATTERN` |
| `_PATRON_SPAN_CODIGO` | `_CODE_SPAN_PATTERN` |
| `_PATRON_CORTE_ORACION` | `_SENTENCE_SPLIT_PATTERN` |
| `_MARCADOR_PUNTO_PROTEGIDO` | `_PROTECTED_DOT_MARKER` |
| `_PATRON_NEGACION` | `_NEGATION_PATTERN` |
| `_VERBOS_RELACION` | `_RELATION_VERBS` |
| `_SYSTEM_EXTRACCION_LLM` | `_LLM_EXTRACTION_SYSTEM` |

Nota: `Relation.source/type/target` se tradujeron aunque el payload dict que
`graph/build.py` sube al `GraphStorePort` sigue usando las claves en español
(`origen`/`destino`/`tipo`) — ver nota de diseño arriba.

## `src/second_brain/graph/traversal.py`

| Viejo | Nuevo |
|---|---|
| `GRADO_MAXIMO_DEFAULT` | `MAX_DEGREE_DEFAULT` |
| `blast_radius(entidad, ..., max_saltos, grado_maximo, traza)` | `blast_radius(entity, ..., max_hops, max_degree, trace)` |
| `camino_entre` | `path_between` |
| `vecinos` | `neighbors_of` |
| `_expandir_un_salto` | `_expand_one_hop` |
| `_extender_camino` | `_extend_path` |
| `_registrar_guardia_anti_hub` | `_record_anti_hub_guard` |

## `src/second_brain/agent/facets.py` (ex `agente/_texto.py`)

| Viejo | Nuevo |
|---|---|
| `dividir_en_facetas` | `split_into_facets` |
| `_PATRON_CONJUNCION` | `_CONJUNCTION_PATTERN` |
| `_PATRON_BORDES` | `_EDGE_PATTERN` |

## `src/second_brain/agent/gate.py`

| Viejo | Nuevo |
|---|---|
| `Cobertura` | `Coverage` (valores del enum SIGUEN en español: `"sin_evidencia"`, `"parcial"`, `"suficiente"` — aparecen en la traza/UI, ver Trampas) |
| `Cobertura.SIN_EVIDENCIA` | `Coverage.NO_EVIDENCE` |
| `Cobertura.PARCIAL` | `Coverage.PARTIAL` |
| `Cobertura.SUFICIENTE` | `Coverage.SUFFICIENT` |
| `evaluar_cobertura` | `evaluate_coverage` |
| `_faceta_cubierta` | `_facet_covered` |
| `UMBRAL_SCORE_RELEVANTE` | `RELEVANT_SCORE_THRESHOLD` |
| `_STOPWORDS_COBERTURA` | `_COVERAGE_STOPWORDS` |

## `src/second_brain/agent/tools.py` (ex `agente/herramientas.py`)

| Viejo | Nuevo |
|---|---|
| `Evidencia` | `Evidence` |
| `Evidencia.texto` | `Evidence.text` |
| `Evidencia.es_objetivo` | `Evidence.is_target` |
| `Evidencia.fuente` | `Evidence.source` |
| `buscar_documentos` | `search_documents` |
| `navegar_grafo` | `traverse_graph` |
| `_evidencia_de_scored_doc` | `_evidence_from_scored_doc` |
| `_buscar_ancladas` | `_search_anchored` |
| `_caminos` | `_paths` |
| `_caminos_a_evidencia` | `_paths_to_evidence` |
| `_dedupe_evidencia` | `_dedupe_evidence` |
| `_TOP_K_BUSQUEDA_ANCLADA` | `_ANCHORED_SEARCH_TOP_K` |
| `_SCORE_EVIDENCIA_GRAFO` | `_GRAPH_EVIDENCE_SCORE` |
| `_ETIQUETA_RELACION` | `_RELATION_LABEL` |

`_entidad_desde_doc_id` (helper interno, no usado fuera del módulo) se dejó
con su nombre en español por ser código muerto heredado del original; ver
sección "Elecciones y ambigüedades" abajo.

## `src/second_brain/agent/guards.py`

| Viejo | Nuevo |
|---|---|
| `validar_citas` | `validate_citations` |
| `_normalizar_espacios` | `_normalize_spaces` |
| `_defanguear` | `_defang` |
| `Canario` | `Canary` |
| `Canario.citas` | `Canary.citations` |
| `Canario.objetivos_buscados` | `Canary.targets_searched` |
| `Canario.objetivos_citados` | `Canary.targets_cited` |
| `Canario.forma_de_abstencion` | `Canary.abstention_form` |
| `canario` (función) | `canary` |
| `_forma_de_abstencion` | `_abstention_form` |
| `_PATRON_CITA` | `_CITATION_PATTERN` |
| `_PATRON_ESPACIOS_SOBRANTES` | `_EXTRA_SPACES_PATTERN` |
| `_PATRON_ESPACIO_ANTES_DE_PUNTUACION` | `_SPACE_BEFORE_PUNCTUATION_PATTERN` |
| `_PATRON_URL` | `_URL_PATTERN` |

## `src/second_brain/agent/synthesis.py` (ex `agente/sintesis.py`)

| Viejo | Nuevo |
|---|---|
| `SYSTEM_SINTESIS` | `SYSTEM_SYNTHESIS` (contenido del prompt sigue en español) |
| `SubPregunta` | `SubQuestion` |
| `SubPregunta.texto` | `SubQuestion.text` |
| `SubPregunta.sujeto` | `SubQuestion.subject` |
| `descomponer` | `decompose` |
| `_extraer_sujeto` | `_extract_subject` |
| `construir_mensaje_usuario` | `build_user_message` |
| `_linea_facetas` | `_facets_line` |
| `_formatear_evidencia` | `_format_evidence` |
| `_PATRON_KEBAB` | `_KEBAB_PATTERN` |
| `_PATRON_PROPIO` | `_PROPER_NOUN_PATTERN` |
| `_PATRON_ACRONIMO` | `_ACRONYM_PATTERN` |

## `src/second_brain/agent/orchestrator.py` (ex `agente/orquestador.py`)

| Viejo | Nuevo |
|---|---|
| `responder` | `answer` |
| `MENSAJE_ABSTENCION` | `ABSTENTION_MESSAGE` |
| `_INDICE_LEXICO_VACIO` | `_EMPTY_LEXICAL_INDEX` |
| `_PATRON_CITA` | `_CITATION_PATTERN` |
| `_TrazaObservable` | `_ObservableTrace` |
| `_recolectar_evidencia` | `_collect_evidence` |
| `_navegar_grafo_fail_open` | `_traverse_graph_fail_open` |
| `_entidad_desde_doc_id` | `_entity_from_doc_id` |
| `_reanclar_vecinos_del_grafo` | `_reanchor_graph_neighbors` |
| `_abstenerse` | `_abstain` |
| `_sintetizar` | `_synthesize` |
| `_extraer_citas` | `_extract_citations` |
| `_aplicar_guards` | `_apply_guards` |
| `_medir_canario` | `_measure_canary` |

## `demo.py`

| Viejo | Nuevo |
|---|---|
| `LlmConCaptura` | `CapturingLlm` |
| `construir_llm_guionado` | `build_scripted_llm` |
| `_forzar_utf8_en_stdio` | `_force_utf8_stdio` |
| `_RELLENO_DE_PREGUNTA` | `_QUESTION_FILLER_WORDS` |
| `_normalizar` | `_normalize` |
| `_terminos_distintivos` | `_distinctive_terms` |
| `_pregunta_del_mensaje` | `_question_from_message` |
| `_parecido` | `_similarity` |
| `_gana_el_guion` | `_script_wins` |
| `_resolver_settings` | `_resolve_settings` |
| `_construir_stack` | `_build_cli_stack` |
| `_construir_indice_lexico` | `_build_cli_lexical_index` |
| `_paso` | `_step` |
| `_cobertura_de` | `_coverage_of` |
| `_formatear_camino` | `_format_path` |
| `_medir_guards` | `_measure_guards` |
| `_imprimir_trace` | `_print_trace` |
| `_truncar` | `_truncate` |
| `_imprimir_respuesta` | `_print_answer` |
| `_Verificacion` | `_Verification` |
| `_Verificacion.nombre/pregunta/evaluar` | `_Verification.name/question/evaluate` |
| `_verificar_p1` .. `_verificar_p_incidente` | `_verify_p1` .. `_verify_p_incidente` |
| `_VERIFICACIONES` | `_VERIFICATIONS` |
| `_CYPHER_TOP_ENTIDADES` | `_CYPHER_TOP_ENTITIES` |
| `_PATRON_CITA` | `_CITATION_PATTERN` |

Sin cambios (por contrato con `corpus/README.md` / trap #3): `P1`..`P5`,
`P_BILLING`, `P_SOPORTE`, `P_ONBOARDING`, `P_VENTAS`, `P_INCIDENTE` (preguntas
del guion) y todas las constantes `_TEXTO_*` (respuestas guionadas): son
prosa/datos de demo, no identificadores de dominio.

## `web/api.py`

Solo referencias a símbolos renombrados (imports y llamadas); ningún string
de cara al usuario ni las etapas de traza se tocaron:

| Viejo | Nuevo |
|---|---|
| `from second_brain.agente.orquestador import responder` | `from second_brain.agent.orchestrator import answer` |
| `from second_brain.ports import PasoTraza, Respuesta` | `from second_brain.ports import TraceStep, Answer` |
| `_cli._resolver_settings()` | `_cli._resolve_settings()` |
| `_cli._construir_stack(...)` | `_cli._build_cli_stack(...)` |
| `_cli._construir_indice_lexico()` | `_cli._build_cli_lexical_index()` |
| `_cli._VERIFICACIONES` | `_cli._VERIFICATIONS` |
| `v.nombre, v.pregunta` (atributos de `_Verification`) | `v.name, v.question` |
| `camino.nodos/relaciones/direcciones` | `camino.nodes/relations/directions` |
| `respuesta.abstencion/citas/text` | `respuesta.abstained/citations/text` |
| `cita.documento/fragmento` | `cita.document/fragment` |
| `blast_radius(..., max_saltos=3)` | `blast_radius(..., max_hops=3)` |
| `settings.modo` | `settings.mode` |

Sin cambios: los strings de etapa (`"herramienta.buscar_documentos"`,
`"gate.cobertura"`, etc.) — son las etiquetas de trazabilidad, ver Trampas.
El matching por prefijo SÍ cambió de atributo (`etapa.startswith(...)` →
`stage.startswith(...)`) cuando se completó el rename de `TraceStep` en la
"Ronda 2" (ver más abajo): el contenido de los strings no se tocó, solo el
nombre del campo que los contiene.

## `tests/**`

Todos los imports/llamadas se actualizaron a los símbolos nuevos de arriba.
Además, siguiendo la consigna de traducir "nombres de tests y de fixtures",
se tradujeron los nombres de función de test y los helpers privados de cada
archivo (contenido de las aserciones, que sigue siendo sobre datos/prosa en
español, no se tocó). Ejemplos representativos (lista completa en el diff de
cada archivo):

- `test_agente.py` → `test_agent.py`: `_stack_y_corpus`→`_stack_and_corpus`,
  `_paso`→`_step`, `_cobertura_de`→`_coverage_of`, `_regla`→`_rule`, y los
  ~20 `def test_...` traducidos a inglés (p.ej.
  `test_p3_sin_evidencia_abstencion_y_cero_tokens_de_llm` →
  `test_p3_no_evidence_abstention_and_zero_llm_tokens`).
- `test_grafo.py` → `test_graph.py`: `_stack_con_grafo`→`_stack_with_graph`,
  `_construir_grafo_de_prueba`→`_build_test_graph`, `_falkor_disponible`→
  `_falkor_available`, y los `def test_...` correspondientes.
- `test_retrieval.py`: `_stack_local`→`_local_stack`, `_indexar_chunks`→
  `_index_chunks`, y los `def test_...` correspondientes.
- `test_guion_demo.py` → `test_demo_script.py`: `_responder`→`_get_answer`,
  y los `def test_...` correspondientes.
- `test_ports.py`, `test_config.py`: `_coseno`→`_cosine`, y los `def test_...`
  correspondientes.

## Trampas respetadas (NO tocadas)

- `TraceStep.etapa`/`.detalle`: renombrados a `.stage`/`.detail` en la
  "Ronda 2" (ver sección propia más abajo) — dejaron de ser trampa porque la
  consigna de esa ronda pidió explícitamente terminar este rename, incluida
  la clave JSON que `web/api.py` serializa para la UI. Lo que SIGUE sin
  tocarse, porque es contenido de traza y no un identificador, es el
  CONTENIDO de los strings de etapa (`"herramienta.buscar_documentos"`,
  `"gate.cobertura"`, `"objetivos.resueltos"`, `"sintesis.llm"`,
  `"guards.aplicados"`, `"canario"`, `"grafo.traversal.guardia_anti_hub"`):
  siguen siendo exactamente los mismos valores, solo cambió el nombre del
  campo/clave que los contiene (`stage` en vez de `etapa`, tanto en el
  `TraceStep` de Python como en la clave del evento AG-UI y en el JS del
  frontend).
- `Coverage` (antes `Cobertura`): la CLASE y sus MIEMBROS (`NO_EVIDENCE`,
  `PARTIAL`, `SUFFICIENT`) se tradujeron, pero los VALORES string del enum
  (`"sin_evidencia"`, `"parcial"`, `"suficiente"`) se dejaron en español
  porque viajan dentro de la traza (`gate.cobertura` → `cobertura.value`) y
  se muestran en `--trace` y en la UI web.
- Preguntas del guion (`P1`..`P5`, `P_BILLING`, etc.) y sus respuestas
  guionadas (`_TEXTO_*`) en `demo.py`: intactas, en español.
- `corpus/**`: no tocado.
- `web/ui/**` (frontend Vue): en la Ronda 1 no se tocó — ver la sección
  "Ronda 2" más abajo: sí se tocó ahí, puntualmente, para seguir el rename
  de `TraceStep.etapa/.detalle` hasta las claves JSON y los componentes Vue
  que las leen (`App.vue`, `PanelTraza.vue`), que de otro modo hubieran
  quedado leyendo una clave que ya no existe.

## Elecciones y ambigüedades — para que el usuario decida

- **`agent/tools.py`**: la función interna `_entidad_desde_doc_id` (código
  muerto, no se usa desde ningún otro punto del módulo — ver el bullet
  original de esta sección en la Ronda 1) se renombró a
  `_entity_from_doc_id` en la Ronda 2, para consistencia con la función
  homónima de `orchestrator.py`. Sigue siendo código muerto; no se borró
  porque borrar código no solicitado no formaba parte del pedido.
- **Dict keys del payload de grafo** (`origen`, `destino`, `tipo`,
  `documento_id`, `fragmento`): se dejaron en español, tratándolas como
  esquema de datos (equivalente a nombres de propiedad de un grafo
  openCypher) en vez de identificadores Python locales a un módulo — el
  mismo dict viaja sin cambios entre `graph/build.py`,
  `falkor_graph_store.py`, `memory_graph_store.py` y `neptune_graph_store.py`.
  Los ATRIBUTOS Python que sí envuelven esos valores en una dataclass
  (`Relation.source/type/target/fragment`) sí se tradujeron. Alternativa: se
  podría traducir también las claves de dict a `source`/`target`/`type` si
  se prefiere consistencia total con los atributos — no se hizo por ser un
  cambio más amplio (toca 4 archivos + las queries Cypher con `$origen`/`$destino`/`$tipo`)
  sin beneficio funcional adicional.
- **`Coverage` enum values**: ver "Trampas" arriba — se decidió que, al
  aparecer en la traza visible (`--trace`, UI), cuentan como contenido de
  traza y no como identificador puro, así que quedaron en español aunque
  los NOMBRES de los miembros del enum sí se tradujeron.
- **`MemoryVectorStore` y `S3VectorsStore`**: los campos internos de
  metadata que persisten a JSON (`"ids"`, `"textos"`, `"metadatos"` en
  `memory_vector_store.py`; `"texto"`, `"documento_id"` en
  `s3_vectors_store.py`) se dejaron en español por la misma razón que las
  claves de grafo: son formato de datos persistido/API externa, no
  identificadores Python.

---

# Ronda 2 — parámetros de función y campos de dataclass

La Ronda 1 (arriba) tradujo funciones, clases, archivos y carpetas, pero
dejó los PARÁMETROS de función y los CAMPOS de dataclass en español. Esta
ronda cierra esa brecha: un escaneo de AST (identificadores declarados —
`def`, parámetros, campos de dataclass — nunca strings ni docstrings)
encontró 94 identificadores en 20 archivos; los 94 quedaron traducidos
(el mismo escaneo corre en 0 después de esta ronda). Se mantiene la misma
regla que en la Ronda 1: identificadores en inglés, docstrings/comentarios/
mensajes de traza/texto de UI/guion en español, intactos.

## `src/second_brain/ports.py`

| Viejo | Nuevo |
|---|---|
| `TraceStep.etapa` | `TraceStep.stage` |
| `TraceStep.detalle` | `TraceStep.detail` |

Único campo de dataclass en español que quedaba en `ports.py` — el resto
ya había quedado en inglés en la Ronda 1.

## `src/second_brain/agent/orchestrator.py`

Todos los `TraceStep(etapa=..., detalle=...)` pasan a `TraceStep(stage=...,
detail=...)` (los VALORES de esos strings, p.ej. `"gate.cobertura"`, no
cambiaron). Parámetros:

| Viejo | Nuevo |
|---|---|
| `_collect_evidence(..., indice, objetivo_doc_id, ...)` | `_collect_evidence(..., index, target_doc_id, ...)` |
| `_traverse_graph_fail_open(entidad, ...)` | `_traverse_graph_fail_open(entity, ...)` |
| `_reanchor_graph_neighbors(documentos, de_grafo)` | `_reanchor_graph_neighbors(documents, from_graph)` |
| `_synthesize(..., evidencia, cobertura, ...)` | `_synthesize(..., evidence, coverage, ...)` |
| `_extract_citations(texto, evidencia)` | `_extract_citations(text, evidence)` |
| `_apply_guards(respuesta, evidencia, ...)` | `_apply_guards(answer, evidence, ...)` |
| `_measure_canary(respuesta, ...)` | `_measure_canary(answer, ...)` |

Cascada de llamadas: `search_documents(..., objetivo=...)` →
`search_documents(..., target=...)`, `traverse_graph(..., tipo=...)` →
`traverse_graph(..., kind=...)` (ver `agent/tools.py` abajo).

## `src/second_brain/agent/tools.py`

| Viejo | Nuevo |
|---|---|
| `search_documents(..., objetivo, top_k_por_metodo, ...)` | `search_documents(..., target, top_k_per_method, ...)` |
| `_evidence_from_scored_doc(doc, objetivo_doc_ids)` | `_evidence_from_scored_doc(doc, target_doc_ids)` |
| `traverse_graph(entidad, stack, tipo, ...)` | `traverse_graph(entity, stack, kind, ...)` |
| `_paths(entidad, stack, tipo, ...)` | `_paths(entity, stack, kind, ...)` |
| `_paths_to_evidence(caminos)` | `_paths_to_evidence(paths)` |
| `_entidad_desde_doc_id` (código muerto, ver "Elecciones") | `_entity_from_doc_id` |

## `src/second_brain/agent/guards.py`

| Viejo | Nuevo |
|---|---|
| `_normalize_spaces(texto)` | `_normalize_spaces(text)` |
| `guard_urls(texto, ...)` | `guard_urls(text, ...)` |
| `_apply_replacements(texto, ...)` | `_apply_replacements(text, ...)` |
| `_normalize_team(texto)` | `_normalize_team(text)` |
| `_mask_dots_in_protected_spans(texto)` | `_mask_dots_in_protected_spans(text)` |
| `_split_sentences(texto)` | `_split_sentences(text)` |
| `_extract_claims(texto, ...)` | `_extract_claims(text, ...)` |

Más las lecturas de `paso.etapa` en `canary`/`_abstention_form` →
`paso.stage` (cascada del rename de `TraceStep`).

## `src/second_brain/agent/synthesis.py`

| Viejo | Nuevo |
|---|---|
| `_extract_subject(texto)` | `_extract_subject(text)` |

## `src/second_brain/graph/traversal.py`

| Viejo | Nuevo |
|---|---|
| `_expand_one_hop(..., camino, ..., resultados)` | `_expand_one_hop(..., path, ..., results)` |
| `_extend_path(camino, ...)` | `_extend_path(path, ...)` |
| `_record_anti_hub_guard(..., nodo, ...)` | `_record_anti_hub_guard(..., node, ...)` |

Más el `TraceStep(etapa=..., detalle=...)` de la guarda anti-hub →
`TraceStep(stage=..., detail=...)`.

## `src/second_brain/graph/extraction.py`

| Viejo | Nuevo |
|---|---|
| `_add_relation(..., tipo, ...)` | `_add_relation(..., kind, ...)` |
| `_split_into_sentences(texto)` | `_split_into_sentences(text)` |
| `_parse_relations_json(texto)` | `_parse_relations_json(text)` |

## `src/second_brain/graph/build.py`

| Viejo | Nuevo |
|---|---|
| `_load_chunk(ruta)` | `_load_chunk(path)` |

La clave de metadata `metadata["ruta"]` (dato persistido, no identificador
Python) NO se tocó — mismo criterio que las claves de grafo documentadas en
"Elecciones y ambigüedades" arriba.

## `src/second_brain/ingestion.py`

| Viejo | Nuevo |
|---|---|
| `load_corpus(ruta)` | `load_corpus(path)` |
| `_load_document(raiz, archivo)` | `_load_document(raiz, file)` |
| `_parse_frontmatter(texto)` | `_parse_frontmatter(text)` |

## `src/second_brain/retrieval.py`

| Viejo | Nuevo |
|---|---|
| `retrieve(..., top_k_por_metodo, ...)` | `retrieve(..., top_k_per_method, ...)` |
| `_slug(texto)` | `_slug(text)` |

## `src/second_brain/adapters/**`

| Archivo | Viejo | Nuevo |
|---|---|---|
| `adapters/aws/neptune_graph_store.py` | `_convert_path(self, camino)` | `_convert_path(self, path)` |
| `adapters/aws/s3_vectors_store.py` | `_to_hit(self, resultado)` | `_to_hit(self, result)` |
| `adapters/local/fake_embeddings.py` | `_embed_one(self, texto)` | `_embed_one(self, text)` |
| `adapters/local/fake_rerank.py` | `_score(self, tokens_pregunta, documento)` | `_score(self, question_tokens, document)` |
| `adapters/local/falkor_graph_store.py` | `_convert_path(self, camino)` | `_convert_path(self, path)` |
| `adapters/local/memory_vector_store.py` | `_cosine_similarity(self, consulta, ...)` | `_cosine_similarity(self, query, ...)` |

## `demo.py`

| Viejo | Nuevo |
|---|---|
| `_normalize(texto)` | `_normalize(text)` |
| `_distinctive_terms(pregunta)` | `_distinctive_terms(question)` |
| `_similarity(terminos_guion, terminos_pregunta)` | `_similarity(script_terms, question_terms)` |
| `_script_wins(indice, terminos_por_guion, ...)` | `_script_wins(index, script_terms_by_entry, ...)` |
| `_step(traza, etapa)` | `_step(traza, stage)` (y su lectura `p.etapa` → `p.stage`) |
| `_coverage_of(respuesta)` | `_coverage_of(answer)` |
| `_format_path(camino)` | `_format_path(path)` |
| `_measure_guards(stack, respuesta)` | `_measure_guards(stack, answer)` |
| `_print_trace(stack, respuesta)` | `_print_trace(stack, answer)` |
| `_truncate(texto, largo)` | `_truncate(text, length)` |
| `_print_answer(respuesta)` | `_print_answer(answer)` |
| `query(pregunta: str = typer.Argument(...))` | `query(question: str = typer.Argument(...))` |
| `_verify_p1..p5, _verify_p_billing/soporte/onboarding/ventas/incidente(respuesta)` | ídem `(answer)` |

⚠️ `query(pregunta)` → `query(question)` es un parámetro de comando Typer:
cambia el nombre visible del argumento en `--help` (de `PREGUNTA` a
`QUESTION`) y en los mensajes de Typer. Verificado explícitamente con
`demo.py --help`, `demo.py query --help` y `demo.py query "..."` — el CLI
sigue funcionando igual, solo cambia el nombre del argumento mostrado.

## `web/api.py` — cascada del rename de `TraceStep` + parámetros propios

Esta es la pieza más sensible de la Ronda 2: `web/api.py` serializa
`TraceStep` a JSON para la UI web, así que renombrar el campo de Python
obliga a decidir qué hacer con la CLAVE JSON. Se tomó la opción
recomendada: renombrar también la clave (`"etapa"` → `"stage"`,
`"detalle"` → `"detail"`) y actualizar el frontend Vue para que siga
leyendo la clave correcta (ver `web/ui/**` abajo) — las claves JSON son
código, no texto visible, así que no están cubiertas por "mantené el texto
en español".

| Viejo | Nuevo |
|---|---|
| `PreguntaIn.pregunta` (campo pydantic, cuerpo del POST) | `PreguntaIn.question` |
| `_evento(tipo, datos)` | `_evento(kind, datos)` |
| `_entidad_desde_doc_id` | `_entity_from_doc_id` |
| `_camino_a_dict(camino)` | `_path_to_dict(path)` |
| `_calcular_subgrafo(respuesta)` | `_calcular_subgrafo(answer)` |
| `_generar_eventos(pregunta)` | `_generate_events(question)` |
| `grafo_ultimo()` (handler de `GET /api/grafo/ultimo`) | `latest_graph()` |
| clave JSON `"etapa"` en eventos `STATE_DELTA`/`TOOL_CALL_*` | clave JSON `"stage"` |
| clave JSON `"detalle"` en eventos `STATE_DELTA`/`TOOL_CALL_*` | clave JSON `"detail"` |

Sin cambios (a propósito, tratadas como esquema de datos/API, no como
identificadores): las claves `"pregunta"`, `"nombre"`, `"documento"`,
`"fragmento"`, `"nodos"`, `"relaciones"`, `"direcciones"`, `"runId"`,
`"toolCallId"`, etc. de los eventos AG-UI y de `GET /api/preguntas` /
`GET /api/grafo/ultimo` — ninguna de ellas es un campo de dataclass ni un
parámetro de función (son literales de dict), y no las alcanzó ni el
escaneo de AST ni el pedido explícito de la consigna (que solo pidió
`etapa`/`detalle`). El endpoint `POST /api/preguntar` SÍ cambió su
contrato porque `PreguntaIn.pregunta` es un campo de modelo pydantic
declarado (alcanzado por el escaneo): el body pasa de `{"pregunta": "..."}`
a `{"question": "..."}` — actualizado en `App.vue` (ver abajo).

## `web/ui/src/**` (frontend Vue) — SOLO lo necesario para seguir el rename de arriba

| Archivo | Viejo | Nuevo |
|---|---|---|
| `App.vue` | `p.etapa === 'sintesis.llm'` | `p.stage === 'sintesis.llm'` |
| `App.vue` | `streamAgUi('/api/preguntar', { pregunta }, ...)` | `streamAgUi('/api/preguntar', { question: pregunta }, ...)` |
| `App.vue` | `datos.etapa === 'respuesta.final'` | `datos.stage === 'respuesta.final'` |
| `PanelTraza.vue` | `INFO_ETAPA` (const) | `STAGE_INFO` |
| `PanelTraza.vue` | `info(etapa)` | `info(stage)` |
| `PanelTraza.vue` | `paso.etapa`, `paso.detalle` (template) | `paso.stage`, `paso.detail` |

Las claves de `STAGE_INFO`/`INFO_ETAPA` (`'objetivos.resueltos'`,
`'gate.cobertura'`, etc.) son los VALORES de etapa, contenido de traza, y
no se tocaron — igual que en `web/api.py`. Todo lo demás de `web/ui/**`
(clases CSS como `.detalle-paso`/`.detalle-arista`, la clave `"pregunta"`
del listado de `GET /api/preguntas` que consume `BarraPreguntas.vue`, el
payload de grafo `nodos`/`relaciones`/`direcciones` que consume
`PanelGrafo.vue`) quedó intacto, por la misma razón de "esquema de datos,
no identificador" documentada arriba.

## `tests/**` (Ronda 2)

| Archivo | Viejo | Nuevo |
|---|---|---|
| `test_agent.py` | `_step(traza, etapa)` | `_step(traza, stage)` |
| `test_agent.py` | `_coverage_of(respuesta)` | `_coverage_of(answer)` |
| `test_agent.py` | `_rule(contiene, texto)` | `_rule(contiene, text)` |
| `test_agent.py` | `_texto_por_etapa(traza, etapa)` | `_text_by_stage(traza, stage)` |
| `test_agent.py` | `TraceStep(etapa=..., detalle=...)`, `paso.etapa`, `paso.detalle` | `TraceStep(stage=..., detail=...)`, `paso.stage`, `paso.detail` |
| `test_agent.py` | `traverse_graph(..., tipo="blast_radius")` | `traverse_graph(..., kind="blast_radius")` |
| `test_agent.py` | `search_documents(..., objetivo="...")` | `search_documents(..., target="...")` |
| `test_graph.py` | `paso.etapa` / `p.etapa` | `paso.stage` / `p.stage` |
| `test_retrieval.py` | `retrieve(..., top_k_por_metodo=5, ...)` | `retrieve(..., top_k_per_method=5, ...)` |
| `test_demo_script.py` | `_get_answer(pregunta)` | `_get_answer(question)` |
| `test_demo_script.py` | `@pytest.mark.parametrize(("pregunta", "guion"), ...)` + firmas | `@pytest.mark.parametrize(("question", "script"), ...)` + firmas |

## Verificación de la Ronda 2

Con `.venv312/Scripts/python.exe`:

- `pytest -q` → **99 passed** (mismo número que antes de esta ronda; no se
  quitó ni se ablandó ningún test).
- `ruff check src tests demo.py web` → limpio.
- `demo.py ingest` → `49 documentos → 49 chunks (dim=256)`,
  `grafo: 14 entidades, 19 relaciones`.
- `demo.py check` → **10/10 OK**.
- `demo.py query "¿Qué dependencia puede retrasar Billing 2.0..." --trace`
  → muestra la línea `🔗 anclaje` con `billing-2-0 DEPENDE_DE auth-cache` e
  `Identidad RESPONSABLE_DE auth-cache` respaldadas, y la respuesta declina
  ADR-017/INC-042 como causa, igual que antes de la ronda.
- `demo.py --help` y `demo.py graph-top` sin cambios de comportamiento
  (el único cambio visible es `PREGUNTA` → `QUESTION` en la ayuda de
  `query`).
- UI web real: se instaló el extra `web` (`pip install -e ".[web]"`, no
  estaba instalado en `.venv312`) para poder levantar
  `uvicorn web.api:app`; se hizo `pnpm run build` en `web/ui`; se confirmó
  con `curl` contra `POST /api/preguntar` que los eventos AG-UI crudos
  usan las claves `"stage"`/`"detail"`; y se abrió la UI con Playwright
  MCP, se disparó la pregunta de Billing 2.0 desde un chip, y se confirmó
  por captura que el panel "Traza del pipeline en vivo" sigue mostrando
  todos los pasos (objetivos, búsqueda, navegación de grafo, gate, síntesis,
  guards, canario, respuesta final) con su detalle — si el JS hubiera
  seguido leyendo `paso.etapa`/`paso.detalle`, el panel habría quedado
  vacío; ese fue exactamente el riesgo que esta verificación descartó.
  Consola del navegador: 0 errores (3 warnings preexistentes de Cytoscape
  sobre `label`, no relacionados con este cambio).
- Escaneo de AST (`escanear_espanol.py`): **0 identificadores** en 0
  archivos (bajó de 94 en 20 archivos).

## Ronda 3 — loop agéntico real (Strands), módulos nuevos

Todos los identificadores de los módulos nuevos nacen en inglés (no hay
"rename" que documentar, se listan acá para que el mapa quede completo):

| Módulo nuevo | Qué agrega |
|---|---|
| `agent/trace.py` | `ObservableTrace` (movida de `orchestrator._ObservableTrace`, ahora pública y compartida) |
| `agent/postprocess.py` | `entity_from_doc_id`, `extract_citations`, `apply_guards`, `measure_canary` (movidas de `orchestrator.py`, compartidas por los dos caminos) |
| `agent/strands_model.py` | `LlmPortModel` — adapter de `strands.models.Model` sobre cualquier `LlmPort` |
| `agent/strands_tools.py` | `EvidenceCollector`, `build_tools` — `search_documents`/`traverse_graph` como tools de Strands |
| `agent/gate_hook.py` | `CoverageGateHook` — el coverage gate reenganchado sobre `AfterToolsEvent` |
| `agent/tool_trace_hook.py` | `ToolTraceHook` — traduce tool calls reales a los mismos nombres de etapa del pipeline fijo |
| `agent/strands_agent.py` | `answer_agentic` — el loop agéntico, mismo contrato que `orchestrator.answer` |
| `agent/observability.py` | `configure_observability` — exporter OTel nativo de Strands, opcional |

`orchestrator.py` conserva `answer` sin cambio de comportamiento (mismos
99 tests originales en verde); lo único que cambió ahí es de dónde vienen
`ABSTENTION_MESSAGE` (ahora en `agent/gate.py`) y las 4 funciones movidas a
`agent/postprocess.py`.

### Verificación de la Ronda 3

Con `.venv312/Scripts/python.exe` (Python 3.12.10):

- `pip install -e ".[dev]"` limpio, con `strands-agents==1.54.0` agregado a
  las dependencias base de `pyproject.toml` (sin conflictos con
  `graphrag-lexical-graph==3.19.1` ni con el resto del árbol).
- `pytest -q` → **103 passed** (99 originales + 4 en `test_strands_agent.py`).
- `ruff check src tests demo.py web` → limpio.
- `demo.py ingest` → `49 documentos → 49 chunks (dim=256)`,
  `grafo: 14 entidades, 19 relaciones` (sin cambios).
- `demo.py check` → **20/20 OK** (10 preguntas × 2 caminos: fijo y
  `--agentic`).
- Contadores reales de llamadas al modelo (`LlmPortModel.call_count`,
  medido corriendo las 10 preguntas del guion contra el loop agéntico
  real): **9 preguntas con evidencia → 2 llamadas cada una** (decidir la
  tool + redactar); **P3, sin evidencia → 1 llamada** (decidir buscar), el
  gate corta sobre `AfterToolsEvent` y el modelo nunca redacta.
- `demo.py query "..." --trace` (Billing 2.0) en los dos caminos muestra
  `🔗 anclaje` con `billing-2-0 DEPENDE_DE auth-cache` e
  `Identidad RESPONSABLE_DE auth-cache` respaldadas, declinando
  ADR-017/INC-042 como causa — idéntico en fijo y agéntico.
- UI web (backend directo, sin Docker): `POST /api/preguntar` con
  `{"agentic": true}` produce la misma secuencia de eventos AG-UI que
  `{"agentic": false}` (mismo vocabulario de `stage`), confirmado por
  `curl` contra el SSE crudo; se abrió la UI con Playwright MCP y se
  confirmó por captura que el panel de traza se ve igual (la UI no manda
  `agentic` todavía, así que ejercitó el camino fijo — el camino agéntico
  se verificó por `curl` directo al mismo endpoint).
- `docker compose --profile test run --rm test` → **103 passed** dentro
  del contenedor, contra FalkorDB real.
- Escaneo de AST (`escanear_espanol.py`): **0 identificadores** — el único
  que apareció durante el desarrollo (`_run_verifications(..., indice: ...)`)
  se corrigió a `lexical_index` antes de este corte.
