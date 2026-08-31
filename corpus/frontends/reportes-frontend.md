---
titulo: reportes-frontend — Aplicación de reportes
tipo: frontend
equipo: Datos
---

# reportes-frontend

`reportes-frontend` es la aplicación web donde los clientes de Nexora Corp
consultan sus reportes de facturación y conciliación. Consume la API de
`reportes-backend` y renderiza los reportes mensuales por cuenta.

## Stack

SPA en React, servida como sitio estático. Se autentica contra el gateway
de sesión de Nexora Corp y llama a `GET /reportes/mensual/{account_id}` de
`reportes-backend` para obtener los datos a mostrar.

## Analítica de producto

El seguimiento de uso de `reportes-frontend` se implementa con un
composable propio, `useTracking`, que empuja eventos a **Google Tag
Manager (GTM)**. Cada acción relevante de la interfaz (apertura de
reporte, exportación, cambio de filtro de fecha) dispara un `dataLayer.push`
con el nombre del evento y sus propiedades.

Ejemplo de uso del composable:

```js
const { track } = useTracking();
track("reporte_exportado", { formato: "csv", account_id });
```

El contenedor de GTM instalado en `reportes-frontend` enruta esos eventos
hacia las herramientas de analítica configuradas a nivel de contenedor
(actualmente, Google Analytics 4 para reportes agregados de uso).

## Integraciones

- `reportes-backend`: fuente de los datos de reportes.
- Google Tag Manager: único canal de tracking de eventos de producto.

## Notas de mantenimiento

El equipo de Datos es dueño de `reportes-frontend`. Cualquier cambio al
composable `useTracking` debe mantener el contrato de nombres de evento
documentado en el contenedor de GTM correspondiente, para no romper los
reportes de uso ya configurados en Google Analytics 4.
