---
titulo: integraciones-erp — Servicio de sincronización con ERPs de clientes
tipo: servicio
equipo: Datos
---

# integraciones-erp

`integraciones-erp` sincroniza facturas, pagos e impuestos de una cuenta
Nexora Corp con el ERP externo del cliente (SAP, Oracle NetSuite u otros,
según el conector configurado). Es una feature exclusiva del plan
`enterprise`.

## Endpoints

### `POST /erp/sincronizaciones`

Dispara una sincronización manual para una cuenta y un rango de fechas.

### `GET /erp/exportaciones/fiscales`

Devuelve el export fiscal consolidado (facturas + impuestos) de una
cuenta en un período, en el formato que espera el conector ERP del
cliente.

## Integraciones

`integraciones-erp` consume `GET /impuestos/reporte-fiscal/{account_id}`
de `motor-impuestos` para construir el reporte fiscal trimestral que
exporta hacia los ERPs de los clientes enterprise.

`integraciones-erp` depende del evento `entrega.fallida` que emite
`webhooks` para marcar una sincronización con el ERP del cliente como
pendiente de reintento manual en vez de darla por completada.

## Consumidores de este servicio

`data-warehouse` consume `GET /erp/exportaciones/fiscales` de
`integraciones-erp` para consolidar el reporte fiscal trimestral en el
modelo analítico interno.

## Operación

`integraciones-erp` es propiedad del equipo de Datos. Es el servicio con
más incidentes reportados por cuentas enterprise durante el cierre de mes
fiscal, dado que depende de una cadena larga (`motor-impuestos` →
`catalogo-planes` → `identidad`) que rara vez se prueba de punta a punta
fuera de ese cierre. Ver `producto/prd-facturacion-por-uso.md` para el
roadmap que reduce esta dependencia.
