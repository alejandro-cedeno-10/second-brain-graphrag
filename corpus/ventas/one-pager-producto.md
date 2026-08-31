---
titulo: One-pager de producto — Nexora Corp
tipo: ventas
equipo: Ventas
---

# One-pager de producto

## Qué es Nexora Corp

Plataforma de facturación y cobro para empresas SaaS: automatiza
facturación recurrente, cobro, conciliación, cálculo de impuestos
multi-región y sincronización con el ERP del cliente.

## Diferenciales para una llamada de ventas

- **Multi-moneda con impuestos correctos por región**: `motor-impuestos`
  calcula el desglose fiscal automático, no una tabla estática (ver
  `producto/prd-multi-moneda.md`). Actualmente en piloto en la región CO.
- **Sincronización nativa con ERP**: `integraciones-erp` exporta facturas
  e impuestos directo al ERP del cliente (SAP, Oracle NetSuite), sin
  scripts manuales. Feature exclusiva del plan `enterprise`.
- **Webhooks confiables**: reintentos automáticos con backoff exponencial
  y panel de diagnóstico de entregas (`GET
  /webhooks/entregas/{account_id}`) para que el equipo técnico del
  cliente no dependa de soporte para depurar una integración.
- **SLA por plan**: primera respuesta en 1 hora 24/7 para cuentas
  enterprise (ver `soporte/politicas-sla.md`).

## Para quién NO es (todavía)

Cuentas que necesitan facturación por uso (no solo por plan fijo) deben
saber que esa feature está en desarrollo (ver
`producto/prd-facturacion-por-uso.md`), no disponible hoy en producción.
No prometer fecha de lanzamiento en una llamada de ventas sin confirmar
con Producto.

## Material relacionado

`ventas/matriz-competitiva.md` para comparación directa con competidores,
`ventas/objeciones-precio.md` para objeciones frecuentes.
