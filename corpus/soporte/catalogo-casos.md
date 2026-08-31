---
titulo: Catálogo de casos de soporte — Nexora Corp
tipo: soporte
equipo: Soporte
---

# Catálogo de casos de soporte

Casos históricos resueltos, con síntoma, causa raíz y solución. Soporte
Nivel 1 debe revisar este catálogo antes de escalar a Nivel 2.

## Caso 001 — "Mi webhook dejó de recibir eventos"

**Síntoma:** el cliente reporta que su endpoint de webhook no recibe
eventos hace horas, aunque antes funcionaba.

**Causa raíz:** en el 90% de los casos, el endpoint del cliente empezó a
devolver un código de error (timeout o 5xx) y `webhooks` agotó los 5
reintentos con backoff exponencial, publicando `entrega.fallida` y
deteniendo los envíos a ese endpoint hasta que el cliente lo reactive.

**Solución:** revisar `GET /webhooks/entregas/{account_id}` para
confirmar el patrón de fallas; si el endpoint del cliente ya responde
bien, pedirle al cliente que reactive el endpoint desde su configuración
o, si no puede, disparar `POST /cola-eventos/topicos/{topico}/republicar`
para reintentar los últimos eventos perdidos (requiere Nivel 2).

## Caso 002 — "Me cobraron dos veces este mes"

**Síntoma:** cliente enterprise en región CO ve dos cargos por el mismo
período de facturación.

**Causa raíz:** bug conocido de `motor-impuestos` durante el piloto de
multi-moneda (ver `incidentes/postmortem-facturacion-duplicada.md`), ya
corregido. Si el caso es de una fecha posterior a la corrección, no es
este bug: escalar a Nivel 2 para revisión manual de
`GET /pagos/estado/{transaccion_id}`.

**Solución:** para casos dentro de la ventana del incidente, aplicar el
crédito estándar vía `POST /billing/adjustments` (Nivel 2) sin pedir más
evidencia al cliente — la causa raíz ya está confirmada y documentada.

## Caso 003 — "No me llegó la notificación de pago confirmado"

**Síntoma:** cliente dice que pagó pero no recibió el email de
confirmación.

**Causa raíz:** casi siempre es un `pago.confirmado` cuyo email cayó en
spam, no un fallo de `notificaciones`. Confirmar primero con `GET
/notificaciones/historial/{account_id}` si el envío se registró como
exitoso.

**Solución:** si el historial muestra el envío como exitoso, pedir al
cliente revisar spam; si no aparece en el historial, es un caso real de
pérdida de evento y sí amerita escalar a Nivel 2 para reenvío manual vía
`POST /notificaciones/enviar`.

## Caso 004 — "No puedo iniciar sesión desde ayer"

**Síntoma:** cliente no puede loguearse, dice que la contraseña es
correcta.

**Causa raíz:** en la mayoría de los casos es una sesión revocada por
seguridad (cambio de contraseña reciente, o revocación manual por
sospecha de acceso indebido), no un problema de `identidad` en sí.

**Solución:** consultar `GET /identidad/sesiones/{id}` para confirmar el
estado; si está `revocada`, pedir al cliente que inicie sesión de nuevo
con `POST /identidad/login` (genera sesión nueva). Si el estado es
`activa` y aun así falla el login, sí es un caso para escalar a la
guardia de Seguridad.
