---
titulo: data-warehouse — Modelo analítico consolidado
tipo: servicio
equipo: Datos
---

# data-warehouse

`data-warehouse` consolida en un modelo analítico único los datos que
hoy viven repartidos entre `reportes-backend` e `integraciones-erp`, para
que Producto y Ventas puedan correr análisis histórico sin pegarle
directo a las APIs operativas de esos dos servicios.

## Endpoints

### `GET /data-warehouse/consultas/{modelo}`

Ejecuta una consulta predefinida sobre un modelo analítico (`churn`,
`ingresos_por_plan`, `uso_por_feature`).

### `POST /data-warehouse/refrescar/{modelo}`

Fuerza el refresco de un modelo fuera de su ventana programada
(normalmente, carga incremental nocturna).

## Integraciones

`data-warehouse` consume `POST /reportes/exportar` de `reportes-backend`
para nutrir el modelo analítico consolidado con los reportes mensuales de
facturación y conciliación.

`data-warehouse` también consume `GET /erp/exportaciones/fiscales` de
`integraciones-erp` para consolidar el reporte fiscal trimestral en el
mismo modelo.

## Operación

`data-warehouse` es propiedad del equipo de Datos. Corre como job nocturno
de carga incremental; no expone datos en tiempo real. Ventas usa sus
modelos (`ingresos_por_plan`, `churn`) como fuente para los casos de
cuentas ganadas y perdidas (ver `ventas/casos-cuentas.md`).
