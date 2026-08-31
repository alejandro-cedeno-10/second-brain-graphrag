---
titulo: Equipo Identidad — Nexora Corp
tipo: organizacion
equipo: Identidad
---

# Equipo Identidad

El equipo de Identidad es un equipo distinto del equipo de Seguridad y
del equipo de Plataforma: nació para dedicarse exclusivamente a la
performance y disponibilidad de la capa de verificación de sesión de
alta frecuencia, separada de las políticas de acceso que sí son
responsabilidad de Seguridad.

## Integrantes

- **Verónica Lara** — Tech Lead de Identidad. Reporta a Ana Ruiz (CTO).
- **Mateo Rangel** — Ingeniero senior de backend, dueño técnico de
  `auth-cache`.

## Servicios que posee

`auth-cache`. Este equipo NO posee `identidad` (el servicio de login y
sesiones, propiedad de Seguridad, ver `org/equipo-seguridad.md`): la
similitud de nombres entre el equipo y el servicio es una fuente
frecuente de confusión interna, por eso este documento la aclara
explícitamente.

## Por qué existe un equipo separado

`auth-cache` se extrajo de `identidad` (ver ADR-017 en
`arquitectura/decisiones.md`) porque el volumen de verificaciones de
sesión de alta frecuencia necesitaba una guardia y un ciclo de
despliegue propios, independientes del resto de la superficie de
`identidad`. La mayoría de los servicios que consumen `auth-cache` hoy
son de Plataforma (`catalogo-planes`, `cola-eventos`) o de Seguridad
(`identidad`), pero ninguno de esos dos equipos es dueño de `auth-cache`.

## Guardia (on-call)

Rotación semanal entre Verónica Lara y Mateo Rangel. Una degradación de
`auth-cache` no bloquea login (los servicios consumidores caen a
verificación completa sin caché), pero sí aumenta latencia en cadena
para todos sus consumidores.

## Canales

- `#equipo-identidad` — canal de trabajo diario.
- `#guardia-identidad` — alertas de guardia de `auth-cache`.

## A quién escalar

Incidentes de `auth-cache` escalan a la guardia de Identidad
(`#guardia-identidad`), nunca a la guardia de Plataforma ni a la de
Seguridad, aunque el síntoma aparezca primero como latencia en un
servicio de esos equipos.
