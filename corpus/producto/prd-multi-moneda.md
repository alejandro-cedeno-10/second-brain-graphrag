---
titulo: PRD — Multi-moneda
tipo: producto
equipo: Producto
---

# Multi-moneda

## Resumen

Permite que una cuenta enterprise vea su factura y pague en su moneda
local (hoy todo se factura en USD), con el desglose de impuestos correcto
por región. Esta feature es la que originó la creación de
`motor-impuestos` como servicio propio.

## Owner

**Sofía Prada** (equipo de Pagos, dueña técnica de `motor-impuestos`) es
la owner técnica. Carlos Medina (VP Producto) es el sponsor de negocio.

## Servicios que toca

- `motor-impuestos`: servicio nuevo, creado específicamente para esta
  feature.
- `core-billing`: `GET /billing/rates` agrega el campo `currency` por
  cuenta.
- `catalogo-planes`: define si un plan muestra impuestos incluidos o
  desglosados por región.
- `pagos`: pasa la moneda de la cuenta al capturar el cobro y consulta a
  `motor-impuestos` el desglose antes de confirmar el monto final.
- `reportes-frontend` y `dashboard`: deben mostrar montos en la moneda de
  la cuenta, no solo en USD.

## Estado

Lanzado a un grupo piloto de cuentas enterprise en la región CO. Ver
`incidentes/postmortem-facturacion-duplicada.md` para el incidente que
surgió durante ese piloto y las acciones correctivas ya aplicadas.

## Próximos pasos

Expandir el piloto a la región MX una vez cerrado el postmortem, y
agregar a `reportes-frontend` el selector de moneda que hoy falta (issue
abierto con el equipo de Datos).
