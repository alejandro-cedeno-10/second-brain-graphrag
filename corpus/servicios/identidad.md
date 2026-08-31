---
titulo: identidad — Servicio de autenticación y sesiones
tipo: servicio
equipo: Seguridad
---

# identidad

`identidad` centraliza la autenticación y el ciclo de vida de sesiones de
Nexora Corp: login, refresco de tokens y revocación. Es el servicio raíz
de confianza del que dependen, directa o indirectamente, casi todos los
flujos que requieren saber "quién está haciendo esto".

## Endpoints

### `POST /identidad/login`

Autentica usuario y contraseña (o SSO federado) y devuelve un par de
tokens (`access_token`, `refresh_token`).

### `POST /identidad/tokens/refrescar`

Renueva un `access_token` vencido a partir de un `refresh_token` válido.

### `GET /identidad/sesiones/{id}`

Devuelve el estado de una sesión (`activa`, `revocada`, `expirada`) y el
`account_id` asociado. Es el endpoint que otros servicios llaman para
validar que quien dispara una acción sensible tiene una sesión vigente.

## Eventos de dominio

`identidad` publica el evento **`sesion.revocada`** cuando un usuario
cierra sesión explícitamente o cuando soporte fuerza una revocación por
seguridad (equipo, dispositivo comprometido, offboarding).

## Consumidores de este servicio

`catalogo-planes` consume `GET /identidad/sesiones/{id}` de `identidad`
para validar la sesión de un administrador antes de publicar un cambio de
plan o de tarifa.

`webhooks` consume `GET /identidad/sesiones/{id}` de `identidad` para
validar la sesión del usuario que configura un endpoint de entrega antes
de habilitarlo.

## Operación

`identidad` es propiedad del equipo de Seguridad. Tiene SLA de
disponibilidad 99.95%: una caída de `identidad` bloquea login nuevo en
toda la plataforma, aunque las sesiones ya activas con token vigente
siguen funcionando hasta que expiren. Ver `incidentes/postmortem-identidad-caida.md`
para el postmortem de la única caída relevante registrada.
