---
titulo: Equipo Datos — Nexora Corp
tipo: organizacion
equipo: Datos
---

# Equipo Datos

El equipo de Datos construye los reportes, integraciones con ERPs de
clientes y el modelo analítico consolidado de Nexora Corp.

## Integrantes

- **Marcos Elguera** — Tech Lead de Datos. Reporta a Ana Ruiz (CTO).
- **Camila Rueda** — Ingeniera senior de backend. Dueña técnica de
  `reportes-backend` y `data-warehouse`.
- **Julián Ospina** — Ingeniero de backend. Dueño técnico de
  `integraciones-erp`.
- **Valentina Cano** — Ingeniera de frontend. Dueña técnica de
  `reportes-frontend`.

## Servicios que posee

`reportes-backend`, `reportes-frontend`, `integraciones-erp` y
`data-warehouse`.

## Guardia (on-call)

Rotación quincenal entre Camila Rueda y Julián Ospina. `reportes-backend`
corre principalmente como job programado (cron diario), así que la
mayoría de sus incidentes se detectan por alerta de job fallido, no por
tráfico caído — ver `soporte/matriz-severidad-escalamiento.md` para cómo
se clasifica esa diferencia.

## Canales

- `#equipo-datos` — canal de trabajo diario.
- `#guardia-datos` — alertas de guardia (jobs fallidos, exports
  atascados).

## A quién escalar

Para incidentes de `integraciones-erp` durante cierre de mes fiscal
(la ventana de mayor riesgo, ver `servicios/integraciones-erp.md`),
escalar directo a Julián Ospina además de la guardia, dado el impacto en
cuentas enterprise. Para pedidos de nuevos modelos analíticos en
`data-warehouse`, el canal es una solicitud en `#equipo-datos`, priorizada
en el planning quincenal del equipo.
