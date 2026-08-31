# Corpus sintético — Nexora Corp

Corpus diseñado a mano para la demo de Second Brain GraphRAG. Cada pregunta
del guion tiene UN comportamiento correcto, sostenido por documentos
específicos de este corpus. Esta tabla es el contrato: el agente, el gate
y los guardrails deben producir el comportamiento descrito acá para cada
pregunta.

Todo el corpus es ficticio: "Nexora Corp" es una empresa SaaS inventada,
sus personas, incidentes, cuentas y decisiones no representan a ninguna
empresa real.

## Estructura

```
corpus/
  org/                 equipo.md, proyectos.md, equipo-<área>.md (9 equipos)
  servicios/            11 servicios backend (dependencias explícitas)
  frontends/            dashboard.md, onboarding.md, reportes-frontend.md
  producto/             4 PRDs de features en curso
  soporte/               catálogo de casos, SLA, severidad, escalamiento
  incidentes/            postmortems + near misses
  ventas/               one-pager, matriz competitiva, objeciones, casos
  rrhh/                 onboarding por área, políticas, runbooks, FAQ
  arquitectura/          decisiones.md (ADRs)
```

### Servicios (`corpus/servicios/`)

| Servicio | Equipo | Depende de |
|---|---|---|
| `core-billing` | Plataforma | — |
| `pagos` | Pagos | `core-billing`, `motor-impuestos` |
| `notificaciones` | Plataforma | evento `billing.updated` de `core-billing` |
| `reportes-backend` | Datos | `core-billing`, `pagos` |
| `identidad` | Seguridad | — |
| `auth-cache` | **Identidad** (equipo distinto de Seguridad y de Plataforma) | — |
| `catalogo-planes` | Plataforma | `identidad`, `auth-cache` |
| `motor-impuestos` | Pagos | `catalogo-planes` |
| `webhooks` | Plataforma | `identidad`, `cola-eventos` |
| `cola-eventos` | Plataforma | `auth-cache` |
| `integraciones-erp` | Datos | `motor-impuestos`, evento de `webhooks` |
| `data-warehouse` | Datos | `reportes-backend`, `integraciones-erp` |

Cadena de 3+ saltos nueva (no existía en el corpus original de 10 docs):
`identidad ← catalogo-planes ← motor-impuestos ← integraciones-erp`. La
cadena original de P2 (`core-billing ← pagos ← reportes-backend`) se
extendió a 3 saltos con `data-warehouse` como nuevo consumidor de
`reportes-backend`.

### Equipos (`corpus/org/equipo-*.md`)

Un doc por área: Plataforma, Pagos, Datos, Frontend, Soporte/CX, Ventas,
SRE, Seguridad, Identidad y People. Cada uno documenta integrantes
(nombres ficticios), servicios que posee, guardia, canales y a quién
escalar. La propiedad de servicios en estos docs es la única fuente de
verdad — nunca se contradice entre docs.

## Contrato pregunta → documento(s) → comportamiento esperado

| # | Pregunta | Documento(s) | Comportamiento esperado |
|---|---|---|---|
| P1 | ¿Quién lidera el Proyecto Beta? | `org/proyectos.md` | RAG simple: recupera la frase directa "María Salas lidera el Proyecto Beta" y cita la fuente. Sin necesidad de traversal de grafo. |
| P2 | Si modifico la API de core-billing, ¿qué módulos se rompen? | `servicios/core-billing.md` (nodo raíz, sin lista de consumidores) + `servicios/pagos.md` + `servicios/reportes-backend.md` + `servicios/notificaciones.md` | Traversal multi-hop (`--trace`) desde el nodo `core-billing`: 1 salto a `pagos` y `notificaciones`, 2 saltos a `reportes-backend` vía `pagos` (además de 1 salto directo). La respuesta nombra los 3 módulos y explica la cadena. La respuesta NO puede obtenerse leyendo solo `core-billing.md`. |
| P3 | ¿Cuál fue la facturación del Q4 2025? | ninguno | El coverage gate detecta ausencia de evidencia ANTES de invocar el LLM y responde "no lo sé" con 0 tokens de generación. El corpus no contiene ningún monto ni resultado de negocio para ningún período. |
| P4 | ¿Quién es la CTO y cuánto gana? | `org/equipo.md` | Respuesta parcial honesta: identifica a Ana Ruiz como CTO (con cita) y declara explícitamente que la base de conocimiento no tiene datos de nómina, en vez de inventar una cifra. |
| P5 | ¿Por qué el frontend de reportes no emite eventos de Amplitude? | `frontends/reportes-frontend.md` (ancla del sujeto) + `frontends/dashboard.md` y `frontends/onboarding.md` (trampa de drift) + `arquitectura/decisiones.md` (ADR-014) | Anclaje al sujeto: ABRE con `reportes-frontend` (GTM, cero Amplitude), menciona la abundancia de Amplitude en el resto del corpus SOLO como contraste marcado, cierra con la razón de ADR-014. |

## Casos "wow" (gancho + 4 casos de uso nuevos)

| Caso | Pregunta | Documento(s) | Comportamiento esperado |
|---|---|---|---|
| **Gancho de apertura — abstención por afirmación** | ¿Qué dependencia puede retrasar Billing 2.0, qué equipo debe resolverla y qué decisión técnica explica el riesgo? | `producto/billing-2-0.md` + `servicios/auth-cache.md` + `arquitectura/decisiones.md` (ADR-017) + `incidentes/postmortem-inc-042-auth-cache.md` (INC-042) | Un RAG plano encuentra los 4 documentos pero puede inventar el PUENTE entre ellos ("la ADR-017 causó el retraso"). La respuesta correcta AFIRMA 2 saltos reales (`billing-2-0` depende de `auth-cache`; el equipo dueño es **Identidad**, no Plataforma) y DECLINA explícitamente el resto (ni ADR-017 ni INC-042 afirman causar el retraso) — abstención por afirmación DENTRO del mismo turno, no abstención de turno completo. Ver la nota de diseño más abajo: el gate mecánico clasifica este turno como evidencia suficiente; la honestidad de "afirmo 2, declino 2" depende del texto guionado (local) o de que el LLM siga `SYSTEM_SINTESIS` (AWS) — no hay un guard determinista que verifique la validez de un vínculo causal entre documentos igualmente citables. |
| **Customer Support Automation** | Un cliente dice que no le llegan los webhooks, ¿cuál es la causa más probable y cómo lo resuelvo? | `soporte/catalogo-casos.md` (Caso 001) + `servicios/webhooks.md` | Fundamenta la respuesta en el catálogo de casos históricos y en la documentación del servicio, con el endpoint de diagnóstico exacto. |
| **Employee Assistant / onboarding** | Soy nueva en el equipo de Pagos, ¿qué debo leer primero y cuál es mi entregable de la semana 1? | `rrhh/onboarding-por-area.md` + `org/equipo-pagos.md` | Responde con la guía de onboarding específica del área y la guardia real del equipo, sin inventar un proceso genérico. |
| **Sales Support** | Un prospecto dice que somos más caros que la competencia, ¿cómo respondo esa objeción? | `ventas/matriz-competitiva.md` + `ventas/objeciones-precio.md` | Usa el material de objeciones ya aprobado, con la salvedad de confirmar que el diferencial (ERP nativo) es relevante para el prospecto antes de usarlo. |
| **Issue Resolution** | ¿Qué causó el incidente de facturación duplicada durante el piloto de multi-moneda y qué se corrigió? | `incidentes/postmortem-facturacion-duplicada.md` | Busca en el postmortem real (causa raíz + acciones correctivas) en vez de generalizar sobre incidentes de facturación sin evidencia puntual. |

### Nota de diseño: qué SÍ y qué NO garantiza el sistema en el caso de apertura

El gate de cobertura (`agente.gate.evaluar_cobertura`) opera por FACETA de
la pregunta (¿hay alguna palabra clave cubierta?), no por validez de una
afirmación causal puntual. Para la pregunta de Billing 2.0, el gate real
clasifica el turno como `suficiente` — no existe un tercer estado
"parcialmente afirmado, parcialmente declinado" a nivel de sub-claim. Eso
significa que:

- La cadena de grafo `billing-2-0 --DEPENDE_DE--> auth-cache` SÍ existe
  como arista real (verificado con `graph-top` y el traversal), y NINGUNA
  arista conecta a `arquitectura/decisiones.md` (ADR-017) ni a
  `incidentes/postmortem-inc-042-auth-cache.md` (INC-042) con `billing-2-0`
  o `auth-cache` en el grafo — esas dos ausencias son el contenido
  pedagógico de la charla, no un accidente.
- Los 4 documentos SÍ llegan como evidencia real al LLM para esta pregunta
  exacta (verificado con `query --trace`).
- Pero ningún guard determinista (`agente.guards`) verifica que una
  afirmación causal citada con `[source:doc_id]` esté realmente sostenida
  por ESE documento — solo verifica que el `doc_id` citado exista en la
  evidencia del turno. En modo local, la respuesta correcta está
  garantizada porque es texto guionado (`ScriptedLlm`); en modo AWS (LLM
  real), la honestidad depende de que el modelo siga la regla de
  `SYSTEM_SINTESIS` ("declará el vacío en vez de inventar"), no de un
  mecanismo que la fuerce.

## Verificaciones de diseño (grep)

- Ningún documento contiene cifras de resultados financieros (montos de
  facturación de un período, cifras agregadas de negocio) — sostiene P3.
- Ningún documento contiene datos de nómina o remuneración individual de
  una persona (sostiene P4).
- `grep -ri "amplitude" corpus/frontends/reportes-frontend.md` → sin resultados (la clave de P5).
- `grep -ric "amplitude" corpus/frontends/dashboard.md corpus/frontends/onboarding.md` → conteos altos (la trampa de P5).
- `grep -ri "consume\|depende de\|llama a" corpus/servicios/` → relaciones explícitas, capturables por extracción de entidades sin ayuda manual.
- `grep -rn "auth-cache" corpus/arquitectura/decisiones.md corpus/incidentes/postmortem-inc-042-auth-cache.md` → ambos documentos hablan de `auth-cache`, ninguno menciona `billing-2-0` como causa de nada (la clave del gancho de apertura).

## Regla de diseño para el grafo (F2)

Las relaciones multi-hop están escritas con el verbo explícito en una
frase simple (sujeto + verbo + objeto: "X consume Y", "X depende de Y")
para que el extractor de entidades (`grafo/extraccion.py`) las capture sin
intervención manual. Si una relación no se captura en el grafo derivado,
la corrección es reescribir la frase del documento fuente — nunca
parchear el grafo a mano. La ausencia deliberada de una relación (como
ADR-017/INC-042 sin arista hacia `billing-2-0`) es igual de intencional:
no escribir la frase es lo que mantiene esa ausencia auditable.
