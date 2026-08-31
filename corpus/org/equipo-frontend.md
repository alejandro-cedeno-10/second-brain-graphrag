---
titulo: Equipo Frontend — Nexora Corp
tipo: organizacion
equipo: Frontend
---

# Equipo Frontend

El equipo de Frontend es el dueño técnico de las aplicaciones de cara al
usuario final que consumen los servicios core. Producto es el sponsor de
negocio de estas aplicaciones (ver `org/equipo.md`); Frontend es quien las
construye y mantiene en producción.

## Integrantes

- **María Salas** — Tech Lead de Frontend. Lidera Proyecto Beta (ver
  `org/proyectos.md`) y es la dueña del catálogo de eventos de Amplitude.
- **Gabriela Ortiz** — Ingeniera de frontend, parte del equipo asignado
  part-time a Proyecto Beta.
- **Nicolás Peralta** — Ingeniero de frontend, dueño técnico de
  `onboarding`.

## Aplicaciones que posee

`dashboard` y `onboarding`. `reportes-frontend` es una excepción
deliberada: aunque también es una aplicación de cara al usuario, es
propiedad técnica del equipo de Datos (sus ingenieros de frontend), no de
este equipo — ver `arquitectura/decisiones.md` (ADR-014) para la razón de
que use un stack de analítica distinto (GTM en vez de Amplitude).

## Guardia (on-call)

Frontend no tiene guardia nocturna dedicada: los incidentes de
`dashboard` u `onboarding` fuera de horario los atiende la guardia de
Plataforma como primer respondiente (ambas aplicaciones dependen de
servicios de Plataforma para su funcionalidad core), quien escala a
María Salas si el problema es de la capa de presentación.

## Canales

- `#equipo-frontend` — canal de trabajo diario.
- `#analitica-producto` — gobierno del catálogo de eventos de Amplitude,
  compartido con Producto.

## A quién escalar

Cambios al catálogo de eventos de Amplitude (naming, propiedades
obligatorias) pasan por revisión de María Salas antes de mergear, como ya
documenta `frontends/dashboard.md`. Para bugs de UI reportados por
soporte, el canal es un ticket etiquetado `frontend` en el sistema de
soporte (ver `soporte/catalogo-casos.md`).
