---
titulo: Objeciones frecuentes y pricing — Nexora Corp
tipo: ventas
equipo: Ventas
---

# Objeciones frecuentes y pricing

## Objeción: "Son más caros que Competidor A"

**Respuesta sugerida:** el plan de entrada de Competidor A es más barato,
pero no incluye sincronización ERP nativa (ver
`ventas/matriz-competitiva.md`) — para una cuenta que necesita esa
integración, el costo total con un conector de terceros suele terminar
por encima del plan `enterprise` de Nexora Corp. Preguntar primero si el
prospecto realmente necesita ERP antes de usar este argumento.

## Objeción: "No tienen facturación por uso"

**Respuesta sugerida:** es correcto hoy; está en desarrollo (ver
`producto/prd-facturacion-por-uso.md`). No comprometer fecha de
lanzamiento. Ofrecer el plan `enterprise` con límites de uso amplios
como alternativa mientras tanto, y anotar el pedido para Producto.

## Objeción: "¿Qué pasa si su servicio de pagos cae?"

**Respuesta sugerida:** `pagos` tiene SLA de disponibilidad 99.9% y es el
servicio con mayor inversión en confiabilidad de la compañía (ver
`org/equipo-pagos.md`). Cualquier incidente pasado se documenta
públicamente en un postmortem con causa raíz y acción correctiva — se
puede compartir el resumen de un postmortem reciente si el prospecto lo
pide, sin compartir detalles internos de arquitectura.

## Márgenes de descuento aprobados sin escalar

- Hasta 10% en contrato anual (vs. mensual), cualquier Account Executive.
- Hasta 15% adicional en cuentas de más de 3 años de permanencia
  proyectada, requiere aprobación de Esteban Duarte.
- Cualquier descuento mayor a 25% total requiere aprobación de Carlos
  Medina (VP Producto).

## Regla general para objeciones no cubiertas acá

Nunca improvisar una respuesta técnica sobre arquitectura interna o
disponibilidad no documentada acá. Escalar por `#ventas-vs-producto` y
responder al prospecto en un follow-up, no en la llamada.
