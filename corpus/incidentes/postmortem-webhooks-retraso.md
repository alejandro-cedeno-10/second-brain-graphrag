---
titulo: Postmortem — Retraso masivo de entregas de webhooks
tipo: incidente
equipo: Plataforma
---

# Postmortem — Retraso masivo de entregas de webhooks

## Resumen

Las entregas de `webhooks` se retrasaron hasta 40 minutos respecto del
evento de negocio original, durante una degradación de `cola-eventos`.
Ningún evento se perdió; todos llegaron, pero tarde.

## Impacto

Clientes enterprise con `integraciones-erp` activo vieron sus
sincronizaciones marcadas como pendientes de reintento (`integraciones-erp`
depende del evento `entrega.fallida` que emite `webhooks`, y varias
entregas tardías cruzaron el umbral de reintento antes de completarse).

## Timeline

- **14:10** — `cola-eventos` reporta lag creciente en el tópico de
  eventos de facturación.
- **14:18** — Guardia de Plataforma confirma que `core-billing` y
  `pagos` siguen respondiendo con normalidad (los productores no están
  degradados); el problema es de consumo, no de publicación.
- **14:22** — Se identifica un consumidor de `webhooks` estancado por un
  deadlock en su propio proceso de reintentos, sin liberar el lock del
  tópico.
- **14:35** — Reinicio del proceso estancado.
- **14:50** — Lag vuelve a niveles normales; `webhooks` se pone al día
  con la cola acumulada.

## Causa raíz

Un cambio reciente en el manejo de reintentos de `webhooks` introdujo un
deadlock cuando dos reintentos del mismo evento corrían en paralelo tras
un reinicio de proceso, bloqueando el consumo de todo el tópico
compartido.

## Acciones correctivas

- Agregar timeout de lock a nivel de proceso en `webhooks` (completado).
- Alertar sobre lag de consumidor, no solo sobre profundidad de cola, en
  `cola-eventos` (completado).
- Documentar en `soporte/catalogo-casos.md` cómo distinguir "evento
  perdido" de "evento retrasado" para que soporte no escale como severidad
  1 un retraso que ya está en proceso de autorecuperación.
