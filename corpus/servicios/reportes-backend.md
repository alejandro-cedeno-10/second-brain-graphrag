---
titulo: reportes-backend — Servicio de generación de reportes
tipo: servicio
equipo: Datos
---

# reportes-backend

`reportes-backend` genera los reportes financieros y operativos que
consume `dashboard` y `reportes-frontend`. Agrega datos de varios
servicios internos en un modelo de reporte unificado por cuenta y período.

## Endpoints propios

### `GET /reportes/mensual/{account_id}`

Devuelve el reporte mensual consolidado de una cuenta: facturación,
transacciones y ajustes.

### `POST /reportes/exportar`

Genera un export asíncrono (CSV/PDF) del reporte solicitado. Responde con
un `job_id` que se consulta vía `GET /reportes/exportar/{job_id}`.

## Integraciones

`reportes-backend` consume `POST /billing/summary` de `core-billing` para
obtener los totales de facturación del período que arma en cada reporte
mensual.

`reportes-backend` también depende de `pagos`: llama a
`GET /pagos/estado/{transaccion_id}` para reconstruir el historial de
transacciones que se incluye en la sección de conciliación del reporte.
Esta dependencia es transitiva hacia `core-billing`, ya que `pagos` a su
vez consume `GET /billing/rates` de `core-billing`.

## Consumidores de este servicio

`reportes-frontend` llama a `GET /reportes/mensual/{account_id}` para
renderizar el tablero de reportes de cara al usuario final. `dashboard`
usa `POST /reportes/exportar` para el botón de exportación de métricas.

## Operación

`reportes-backend` corre como job programado (cron diario) más una API
síncrona para consultas puntuales. Propiedad del equipo de Datos.
