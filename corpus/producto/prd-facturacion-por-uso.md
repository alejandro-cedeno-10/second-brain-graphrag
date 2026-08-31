---
titulo: PRD — Facturación por uso
tipo: producto
equipo: Producto
---

# Facturación por uso

## Resumen

Hoy Nexora Corp factura por plan fijo (`starter`, `pro`, `enterprise`).
Esta feature agrega un componente de facturación por uso (llamadas API,
GB exportados en reportes) encima del plan fijo, para cuentas que superan
los límites incluidos.

## Owner

**Renata Cifuentes** (Tech Lead de Pagos) es la owner técnica. El sponsor
de negocio es Carlos Medina (VP Producto).

## Servicios que toca

- `core-billing`: agrega un nuevo tipo de línea a `POST
  /billing/summary` (`uso_excedente`).
- `pagos`: sin cambios en el flujo de cobro, pero el monto a cobrar ahora
  puede incluir el excedente calculado por `core-billing`.
- `catalogo-planes`: cada plan define un límite de uso incluido antes de
  empezar a facturar excedente.
- `reportes-backend`: el reporte mensual debe desglosar plan fijo vs.
  excedente por uso.
- `integraciones-erp`: reduce a mediano plazo la dependencia de la cadena
  larga (`motor-impuestos` → `catalogo-planes` → `identidad`) descrita en
  `servicios/integraciones-erp.md`, al mover parte del cálculo de límites
  a `catalogo-planes` directamente.

## Estado

En curso, fase de diseño técnico. `core-billing` y `catalogo-planes` ya
tienen el esquema de datos definido; falta el cambio en
`reportes-backend` para el desglose en el reporte mensual.

## Riesgo conocido

Si `catalogo-planes` no está disponible al momento de un cobro, `pagos`
no tiene forma de saber el límite de uso incluido del plan: el fallback
acordado es cobrar solo el plan fijo ese ciclo y reconciliar el excedente
en el ciclo siguiente, nunca bloquear el cobro por esta causa.
