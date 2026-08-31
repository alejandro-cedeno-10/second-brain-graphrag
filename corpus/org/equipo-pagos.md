---
titulo: Equipo Pagos — Nexora Corp
tipo: organizacion
equipo: Pagos
---

# Equipo Pagos

El equipo de Pagos es dueño del camino crítico de checkout: cobro,
conciliación y, desde la feature de multi-moneda, cálculo de impuestos.

## Integrantes

- **Renata Cifuentes** — Tech Lead de Pagos. Reporta a Ana Ruiz (CTO) y
  es la sponsor técnica de la feature "facturación por uso" (ver
  `producto/prd-facturacion-por-uso.md`).
- **Tomás Vidal** — Ingeniero senior de backend. Dueño técnico de
  `pagos`.
- **Sofía Prada** — Ingeniera de backend. Dueña técnica de
  `motor-impuestos`.

## Servicios que posee

`pagos` y `motor-impuestos`. El equipo también participa como revisor
obligatorio de cualquier cambio en `core-billing` que toque el contrato
de `GET /billing/rates`, dado que `pagos` es su consumidor de mayor
tráfico.

## Guardia (on-call)

Rotación semanal entre Tomás Vidal y Sofía Prada, con Renata Cifuentes
como escalación secundaria. `pagos` tiene SLA de disponibilidad 99.9%
(camino crítico de checkout): cualquier degradación dispara alerta de
severidad 1 automática.

## Canales

- `#equipo-pagos` — canal de trabajo diario.
- `#guardia-pagos` — alertas de guardia.
- `#incidentes-nexora` — canal compartido con SRE para incidentes activos.

## A quién escalar

Incidentes de `pagos` o `motor-impuestos` escalan primero a la guardia de
Pagos (`#guardia-pagos`); si el incidente involucra también a
`core-billing` (por la dependencia de tarifas), se abre puente conjunto
con la guardia de Plataforma. Para reclamos de facturación de un cliente
puntual, ver `soporte/guia-escalamiento.md`.
