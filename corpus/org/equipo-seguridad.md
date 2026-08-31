---
titulo: Equipo Seguridad — Nexora Corp
tipo: organizacion
equipo: Seguridad
---

# Equipo Seguridad

El equipo de Seguridad es dueño de `identidad` y de las políticas de
acceso interno de Nexora Corp (quién puede acceder a producción, cómo se
revoca acceso en un offboarding, cómo se gestionan credenciales).

## Integrantes

- **Rodrigo Fajardo** — Tech Lead de Seguridad. Reporta a Ana Ruiz (CTO).
- **Camilo Estévez** — Ingeniero de seguridad, dueño técnico de
  `identidad`.

## Servicios que posee

`identidad`. Seguridad también revisa (sin ser dueña) cualquier endpoint
nuevo de otro servicio que maneje datos sensibles de pago, como parte del
checklist de salida a producción.

## Guardia (on-call)

Rotación mensual, solo Camilo Estévez y Rodrigo Fajardo como
escalación. Una caída de `identidad` es automáticamente severidad 1 (ver
`soporte/matriz-severidad-escalamiento.md`) porque bloquea login nuevo en
toda la plataforma.

## Canales

- `#equipo-seguridad` — canal de trabajo diario.
- `#guardia-seguridad` — alertas de guardia de `identidad`.
- `#acceso-produccion` — solicitudes de acceso a producción, con
  aprobación de Rodrigo Fajardo o Camilo Estévez.

## A quién escalar

Para solicitudes de acceso a producción, ver
`rrhh/politicas-internas.md` (requiere aprobación de Seguridad y del Tech
Lead del equipo dueño del servicio). Para incidentes de `identidad`,
escalar directo a `#guardia-seguridad`; es severidad 1 automática y SRE
se suma como coordinador desde el primer minuto.
