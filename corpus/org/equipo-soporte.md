---
titulo: Equipo Soporte/CX — Nexora Corp
tipo: organizacion
equipo: Soporte
---

# Equipo Soporte/CX

El equipo de Soporte/CX es el primer punto de contacto de cualquier
cliente de Nexora Corp con un problema. No escribe código de producto,
pero es dueño de las políticas de SLA, la matriz de severidades y el
catálogo de casos resueltos (ver `soporte/`).

## Integrantes

- **Fernanda Ríos** — Líder de Soporte/CX. Reporta a Carlos Medina (VP
  Producto).
- **Andrés Mora** — Agente de soporte nivel 2, con permisos para
  registrar ajustes manuales en `core-billing` (`POST
  /billing/adjustments`).
- **Bianca Salcedo** — Agente de soporte nivel 1, primera línea de
  atención por chat y email.

## Niveles de soporte

- **Nivel 1**: atiende reclamos frecuentes con solución documentada en el
  catálogo de casos. No tiene acceso a sistemas internos más allá de
  lectura.
- **Nivel 2**: escala de Nivel 1, tiene acceso a `POST
  /billing/adjustments` de `core-billing` y a `GET
  /notificaciones/historial/{account_id}` para reenviar notificaciones
  perdidas.

## Guardia (on-call)

Soporte/CX no tiene guardia técnica: para incidentes que requieren
intervención de ingeniería fuera de horario, escala a la guardia del
equipo dueño del servicio afectado, siguiendo
`soporte/guia-escalamiento.md`.

## Canales

- `#soporte-nivel1`, `#soporte-nivel2` — colas de atención por nivel.
- `#soporte-escalamiento` — canal de escalación a ingeniería.

## A quién escalar

Fernanda Ríos es punto de escalación para reclamos de cliente enterprise
que amenacen con cancelar. Para incidentes técnicos, el flujo completo
(severidad, tiempos de respuesta, a qué guardia escalar) está en
`soporte/politicas-sla.md` y `soporte/matriz-severidad-escalamiento.md`.
