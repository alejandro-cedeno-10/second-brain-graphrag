---
titulo: Matriz competitiva — Nexora Corp
tipo: ventas
equipo: Ventas
---

# Matriz competitiva

## Competidor A ("FacturaFlow")

Más barato en el plan de entrada, pero sin sincronización nativa con ERP:
requiere un conector de terceros que el cliente paga aparte. No tiene
cálculo de impuestos multi-región propio, delega en una integración
externa que Nexora Corp sí resuelve con `motor-impuestos` de forma
nativa.

## Competidor B ("BillPeak")

Tiene facturación por uso desde ya (Nexora Corp la tiene en desarrollo,
ver `producto/prd-facturacion-por-uso.md`) pero su SLA de soporte
enterprise es de 4 horas, contra la 1 hora de Nexora Corp (ver
`soporte/politicas-sla.md`). Su documentación pública de webhooks no
menciona reintentos automáticos.

## Cuándo usar esta matriz en una llamada

Solo quando el prospecto ya nombró un competidor puntual. Nunca abrir una
llamada comparando contra la competencia sin que el prospecto lo haya
mencionado primero — el one-pager (`ventas/one-pager-producto.md`) es el
material por defecto.

## Actualización de este documento

Esteban Duarte (Líder de Ventas) es responsable de mantener esta matriz
al día con cualquier cambio de producto reportado por Producto o
Ingeniería. Un diferencial que dejó de ser cierto (por ejemplo, si
Competidor B lanza sincronización ERP nativa) debe corregirse acá antes
de la próxima llamada donde se use.
