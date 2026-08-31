---
titulo: cola-eventos — Bus de eventos interno
tipo: servicio
equipo: Plataforma
---

# cola-eventos

`cola-eventos` es la infraestructura de mensajería interna sobre la que
corren los eventos de dominio que `core-billing`, `pagos` e `identidad`
publican. No tiene lógica de negocio propia: es la tubería, no el
contenido. Servicios como `notificaciones` se suscriben a eventos
puntuales de `cola-eventos` para reaccionar sin acoplarse al productor.

## Endpoints

### `GET /cola-eventos/salud`

Health check operativo: profundidad de cola por tópico y lag de consumo
del consumidor más atrasado.

### `POST /cola-eventos/topicos/{topico}/republicar`

Republica manualmente los últimos N mensajes de un tópico, usado por
soporte/SRE para recuperar consumidores que perdieron eventos por una
caída (ver `soporte/guia-escalamiento.md`).

## Eventos de dominio

`cola-eventos` no emite eventos de negocio propios: transporta los que
publican `core-billing`, `pagos` e `identidad`. Publica sí un evento
operativo, **`evento.publicado`**, cuando confirma la entrega de un
mensaje a todos los consumidores suscritos a un tópico — es el evento que
usan los consumidores que necesitan saber que el bus procesó su mensaje,
no el contenido del mensaje mismo.

## Consumidores de este servicio

`webhooks` depende del evento `evento.publicado` que emite `cola-eventos`
para saber cuándo reenviar un evento de negocio como webhook saliente a
un cliente.

## Operación

`cola-eventos` es propiedad del equipo de Plataforma. Es infraestructura
compartida de alta criticidad: una degradación en `cola-eventos` no
rompe los servicios productores (`core-billing`, `pagos`, `identidad`
siguen respondiendo), pero sí retrasa a todo consumidor asíncrono
(`notificaciones`, `webhooks`). Ver
`incidentes/postmortem-webhooks-retraso.md` para el incidente donde esta
degradación se manifestó.
