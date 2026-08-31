---
titulo: auth-cache — Caché distribuida de verificación de sesión
tipo: servicio
equipo: Identidad
---

# auth-cache

`auth-cache` es la caché distribuida que guarda, con una expiración
corta, el resultado de verificar una sesión contra el proveedor de
identidad, para que un servicio no tenga que resolver esa verificación
completa en cada llamada. Nace de la decisión ADR-017 (ver
`arquitectura/decisiones.md`).

## Endpoints

### `GET /auth-cache/verificar/{token}`

Devuelve el resultado cacheado de la última verificación de un token, si
todavía está vigente, sin recalcularla.

### `POST /auth-cache/invalidar/{token}`

Fuerza la invalidación de una entrada cacheada, usado cuando una sesión
se revoca antes de que la entrada expire por sí sola.

## Consumidores de este servicio

`identidad` consume `GET /auth-cache/verificar/{token}` de `auth-cache`
para evitar recalcular la verificación completa de sesión en cada
llamada de alta frecuencia.

`catalogo-planes` consume `GET /auth-cache/verificar/{token}` de
`auth-cache` con el mismo objetivo, dado el volumen de validaciones de
sesión de administrador que recibe.

`cola-eventos` consume `GET /auth-cache/verificar/{token}` de
`auth-cache` para validar rápido las credenciales de servicio que
publican en un tópico protegido, sin depender de una verificación
completa por cada mensaje.

## Operación

`auth-cache` es propiedad del **equipo de Identidad**, no del equipo de
Plataforma — aunque la mayoría de sus consumidores directos
(`identidad`, `catalogo-planes`, `cola-eventos`) sean servicios de
Plataforma o adyacentes a Plataforma, la caché en sí se separó como
servicio propio, con su propio ciclo de despliegue y su propia guardia,
precisamente para que un problema de latencia ahí no quede escondido
dentro de la guardia de otro equipo. Ver
`incidentes/postmortem-inc-042-auth-cache.md` para el incidente de
latencia más reciente registrado sobre este servicio.

## Riesgo de dependencia para iniciativas nuevas

Cualquier iniciativa de producto que declare una dependencia de
`auth-cache` (como `billing-2-0`, ver `producto/billing-2-0.md`) debe
coordinar el riesgo de fecha con el **equipo de Identidad**, dueño de la
decisión técnica de arquitectura de este servicio — no con Plataforma ni
con el equipo dueño de la iniciativa. Esa es la regla general que
resuelve la ambigüedad de a qué equipo escalar un riesgo sobre esta
dependencia.
