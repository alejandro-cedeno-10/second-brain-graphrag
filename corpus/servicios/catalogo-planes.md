---
titulo: catalogo-planes — Servicio de catálogo de planes y features
tipo: servicio
equipo: Plataforma
---

# catalogo-planes

`catalogo-planes` es la fuente de verdad de qué planes existen, qué
features incluye cada uno y cómo se relacionan con las tarifas que aplica
`core-billing`. Antes de este servicio, el catálogo de planes vivía
hardcodeado en `core-billing`; se extrajo como servicio propio para que
Producto pudiera versionar planes sin tocar el servicio de facturación.

## Endpoints

### `GET /catalogo/planes`

Lista todos los planes activos (`starter`, `pro`, `enterprise`) con su
descripción comercial.

### `GET /catalogo/planes/{id}/features`

Devuelve el detalle de features habilitadas para un plan, incluyendo si
los impuestos se muestran incluidos o desglosados en el precio mostrado
al cliente.

```json
{
  "plan_id": "pro",
  "features": ["multi_moneda", "exportacion_reportes", "soporte_prioritario"],
  "impuestos_incluidos": false
}
```

## Integraciones

`catalogo-planes` consume `GET /identidad/sesiones/{id}` de `identidad`
para validar la sesión de un administrador antes de publicar un cambio de
plan o de tarifa: solo una sesión activa con rol de administración puede
disparar `POST /catalogo/planes` (endpoint interno, uso restringido a
Producto y Plataforma).

## Consumidores de este servicio

`motor-impuestos` consume `GET /catalogo/planes/{id}/features` de
`catalogo-planes` para saber si el plan de la cuenta muestra impuestos
incluidos o desglosados antes de calcular el desglose fiscal de un cobro.

## Operación

`catalogo-planes` es propiedad del equipo de Plataforma. Cambios al
esquema de `features` requieren coordinación con Producto, dado que ese
esquema alimenta directamente `motor-impuestos` y, en consecuencia, el
flujo de cobro de `pagos`.
