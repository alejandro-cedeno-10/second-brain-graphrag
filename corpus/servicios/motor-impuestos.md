---
titulo: motor-impuestos — Servicio de cálculo de impuestos
tipo: servicio
equipo: Pagos
---

# motor-impuestos

`motor-impuestos` calcula el desglose fiscal de un cobro según la región
y el tipo de cuenta (persona natural o jurídica). Nace de la feature
"multi-moneda" (ver `producto/prd-multi-moneda.md`), que exige mostrar
impuestos correctos en la moneda de cada país donde Nexora Corp opera.

## Endpoints

### `POST /impuestos/calcular`

Recibe un monto, moneda y región, y devuelve el desglose de impuestos
aplicables.

```json
{
  "monto": 49.90,
  "moneda": "USD",
  "region": "CO",
  "impuestos": [{"tipo": "IVA", "tasa": 0.19, "monto": 9.48}]
}
```

### `GET /impuestos/reporte-fiscal/{account_id}`

Devuelve el acumulado de impuestos calculados para una cuenta en un
período, usado por `integraciones-erp` para el reporte fiscal trimestral.

## Integraciones

`motor-impuestos` consume `GET /catalogo/planes/{id}/features` de
`catalogo-planes` para saber si el plan de la cuenta muestra impuestos
incluidos o desglosados antes de calcular el desglose fiscal de un cobro.

## Consumidores de este servicio

`pagos` consume `POST /impuestos/calcular` de `motor-impuestos` antes de
capturar un cobro en una región con impuestos aplicables: si
`motor-impuestos` no responde, `pagos` usa la última tasa cacheada por
región durante un máximo de 30 minutos, con la misma política de
degradación que ya aplica para `core-billing`.

`integraciones-erp` consume `GET /impuestos/reporte-fiscal/{account_id}`
de `motor-impuestos` para construir el reporte fiscal trimestral que
exporta hacia los ERPs de los clientes enterprise.

## Operación

`motor-impuestos` es propiedad del equipo de Pagos. Ver
`incidentes/postmortem-facturacion-duplicada.md` para el incidente en el
que un bug de `motor-impuestos` generó cobros duplicados en la región CO.
