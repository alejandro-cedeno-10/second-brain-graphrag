---
titulo: Equipo Plataforma — Nexora Corp
tipo: organizacion
equipo: Plataforma
---

# Equipo Plataforma

El equipo de Plataforma construye y opera los servicios core de los que
depende casi toda la compañía: facturación, notificaciones, catálogo de
planes y la infraestructura de mensajería interna.

## Integrantes

- **Diego Torres** — Tech Lead de Plataforma. Lidera Proyecto Alfa (ver
  `org/proyectos.md`). Reporta a Ana Ruiz (CTO).
- **Lucía Fonseca** — Ingeniera senior de backend. Dueña técnica de
  `core-billing`.
- **Iván Rodas** — Ingeniero senior de backend. Dueño técnico de
  `catalogo-planes` y `cola-eventos`.
- **Paula Nieto** — Ingeniera de backend. Dueña técnica de `webhooks` y
  `notificaciones`.

## Servicios que posee

`core-billing`, `notificaciones`, `catalogo-planes`, `cola-eventos` y
`webhooks`. Cualquier cambio breaking en alguno de estos servicios pasa
por revisión de Diego Torres antes de mergear a producción.

## Guardia (on-call)

Rotación semanal entre Lucía Fonseca, Iván Rodas y Paula Nieto. El
calendario de guardia vive en el canal `#guardia-plataforma`. La guardia
de Plataforma es la primera escalación para cualquier incidente que
involucre `core-billing`, `catalogo-planes`, `cola-eventos`, `webhooks` o
`notificaciones` fuera de horario laboral.

## Canales

- `#equipo-plataforma` — canal de trabajo diario.
- `#guardia-plataforma` — alertas de guardia (PagerDuty conectado).
- `#incidentes-nexora` — canal compartido con SRE para incidentes activos.

## A quién escalar

Para incidentes de severidad 1 o 2 (ver
`soporte/matriz-severidad-escalamiento.md`) que involucren un servicio de
Plataforma, escalar primero a la guardia (`#guardia-plataforma`) y, si no
hay respuesta en 15 minutos, a Diego Torres directo. Para decisiones de
arquitectura que afecten a otros equipos, el foro es el comité de
arquitectura mensual (ver `org/equipo.md`).
