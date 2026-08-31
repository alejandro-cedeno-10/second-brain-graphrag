---
titulo: pagos — Servicio de procesamiento de pagos
tipo: servicio
equipo: Pagos
---

# pagos

`pagos` procesa transacciones de cobro de Nexora Corp: autorización,
captura y conciliación con las pasarelas externas configuradas por
cuenta. Es el servicio de referencia para cualquier flujo de checkout.

## Endpoints propios

### `POST /pagos/cobrar`

Inicia un cobro para una cuenta y un método de pago. Body:

```json
{
  "account_id": "acc_8891",
  "amount": 49.90,
  "currency": "USD",
  "payment_method_id": "pm_2210"
}
```

### `GET /pagos/estado/{transaccion_id}`

Devuelve el estado actual de una transacción (`pending`, `captured`,
`failed`, `refunded`).

## Integraciones

`pagos` consume `GET /billing/rates` de `core-billing` antes de autorizar
un cobro, para validar que la tarifa aplicada al plan de la cuenta esté
vigente. Si `core-billing` no responde, `pagos` usa la última tarifa
cacheada durante un máximo de 15 minutos.

`pagos` también notifica al servicio `notificaciones` cuando una
transacción cambia de estado, para que el usuario reciba confirmación.

## Consumidores de este servicio

El servicio `reportes-backend` consume los datos de `pagos` para construir
los reportes de conciliación mensual: llama a `GET /pagos/estado/{id}`
en lote para reconstruir el historial de transacciones del período.

## Operación

`pagos` es propiedad del equipo de Pagos. Tiene SLA de disponibilidad
99.9% dado que está en el camino crítico del checkout.
