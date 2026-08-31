---
titulo: webhooks — Servicio de entrega de webhooks salientes
tipo: servicio
equipo: Plataforma
---

# webhooks

`webhooks` entrega eventos de negocio de Nexora Corp a los endpoints HTTP
que configuran los clientes enterprise (típicamente, su ERP o su propio
backend). Es la pieza que habilita integraciones sin que el cliente tenga
que hacer polling contra la API.

## Endpoints

### `POST /webhooks/endpoints`

Registra un endpoint de entrega para una cuenta, con el listado de
eventos a los que se suscribe.

### `GET /webhooks/entregas/{account_id}`

Historial de entregas (exitosas y fallidas) de webhooks para una cuenta,
usado por soporte para diagnosticar reclamos de "no me llegó el webhook".

## Eventos de dominio

`webhooks` publica **`entrega.fallida`** cuando agota los reintentos de
entrega a un endpoint de cliente (5 intentos con backoff exponencial).

## Integraciones

`webhooks` consume `GET /identidad/sesiones/{id}` de `identidad` para
validar la sesión del usuario que configura un endpoint de entrega antes
de habilitarlo.

`webhooks` depende del evento `evento.publicado` que emite `cola-eventos`
para saber cuándo reenviar un evento de negocio como webhook saliente a
un cliente.

## Consumidores de este servicio

`integraciones-erp` depende del evento `entrega.fallida` que emite
`webhooks` para marcar una sincronización con el ERP del cliente como
pendiente de reintento manual en vez de darla por completada.

## Operación

`webhooks` es propiedad del equipo de Plataforma. El caso de soporte más
frecuente relacionado con este servicio es la confusión entre "webhook no
llegó" y "webhook llegó pero el endpoint del cliente devolvió error" — ver
`soporte/catalogo-casos.md` para el diagnóstico paso a paso.
