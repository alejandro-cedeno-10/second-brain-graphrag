---
titulo: core-billing — Servicio de facturación
tipo: servicio
equipo: Plataforma
---

# core-billing

`core-billing` es el servicio central de facturación de Nexora Corp.
Calcula tarifas, genera resúmenes de facturación y emite los eventos de
dominio que representan cambios en el estado de facturación de una cuenta.

## Endpoints

### `GET /billing/rates`

Devuelve las tarifas vigentes por plan y región. Respuesta:

```json
{
  "plan": "pro",
  "region": "LATAM",
  "rate": 0.014,
  "currency": "USD",
  "updated_at": "2026-01-15T00:00:00Z"
}
```

### `POST /billing/summary`

Genera un resumen de facturación para una cuenta en un rango de fechas.
Body de la petición:

```json
{
  "account_id": "acc_8891",
  "from": "2026-01-01",
  "to": "2026-01-31"
}
```

Respuesta: totales agregados por concepto (uso, addons, ajustes).

### `POST /billing/adjustments`

Registra ajustes manuales sobre una cuenta (créditos, correcciones).
Uso restringido a soporte nivel 2.

## Eventos de dominio

`core-billing` publica el evento **`billing.updated`** en el bus de
eventos interno cada vez que se recalcula el estado de facturación de una
cuenta (cambio de plan, ajuste manual, cierre de ciclo). El payload
incluye `account_id`, `previous_state` y `new_state`.

## Contrato y versionado

La API sigue versionado semántico en el header `X-Billing-Contract`.
Cambios breaking en `GET /billing/rates` o `POST /billing/summary`
requieren aprobación del comité de arquitectura, dado que ambos endpoints
son de alto tráfico interno.

## Operación

`core-billing` corre en el clúster de Plataforma con autoscaling estándar.
El equipo dueño es Plataforma; para incidentes, escalar por el canal de
guardia de Plataforma.
