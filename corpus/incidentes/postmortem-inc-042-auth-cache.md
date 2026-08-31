---
titulo: Postmortem INC-042 — Latencia elevada en auth-cache
tipo: incidente
equipo: Identidad
---

# Postmortem INC-042 — Latencia elevada en `auth-cache`

## Resumen

`auth-cache` presentó latencia p99 de 4.2 segundos (contra un objetivo de
80 milisegundos) durante 22 minutos, por una mala distribución de claves
entre nodos de la caché tras un rebalanceo automático.

## Impacto

Los consumidores de `GET /auth-cache/verificar/{token}`
(`identidad`, `catalogo-planes`, `cola-eventos`) experimentaron latencia
elevada en las operaciones que dependen de esa verificación, sin caídas
de disponibilidad: ninguna de las tres devolvió error, solo respondieron
más lento mientras `auth-cache` estaba degradado.

## Timeline

- **09:14** — Alerta de latencia p99 en `auth-cache`.
- **09:17** — Guardia de Identidad (Mateo Rangel) confirma rebalanceo
  reciente de nodos como cambio más probable.
- **09:25** — Se confirma que el rebalanceo dejó un subconjunto de claves
  concentradas en dos nodos, saturando su CPU.
- **09:36** — Rebalanceo manual correctivo aplicado.
- **09:36** — Latencia p99 vuelve a valores normales.

## Causa raíz

El algoritmo de rebalanceo automático de `auth-cache` no considera el
tamaño real de cada partición de claves, solo la cantidad de particiones
por nodo: bajo cierta distribución de tráfico, eso concentra claves
"calientes" en pocos nodos.

## Acciones correctivas

- Cambiar el algoritmo de rebalanceo para ponderar por volumen de
  tráfico observado, no solo por cantidad de particiones (en progreso,
  asignado a Mateo Rangel).
- Agregar alerta de concentración de tráfico por nodo, antes de que
  llegue a saturar CPU (completado).

## Alcance de este postmortem

Este incidente es exclusivamente de `auth-cache` y sus tres consumidores
directos. No hay evidencia de que haya afectado a ningún otro servicio,
proyecto o iniciativa de producto fuera de esos tres — este documento no
evalúa el riesgo de ninguna dependencia declarada por una iniciativa de
producto sobre `auth-cache`, solo la causa raíz y el impacto de este
incidente puntual.

## Relación con Billing 2.0 y otras iniciativas

`billing-2-0` declaró una dependencia de `auth-cache` (ver
`producto/billing-2-0.md`) después de este incidente. Este postmortem no
explica ni evalúa el riesgo de que esa dependencia pueda retrasar
`billing-2-0`: esa es una decisión técnica y de coordinación entre el
equipo dueño de `billing-2-0` y el equipo de Identidad, no algo que este
documento resuelva por sí solo.
