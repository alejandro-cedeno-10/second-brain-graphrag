---
titulo: Equipo SRE — Nexora Corp
tipo: organizacion
equipo: SRE
---

# Equipo SRE

El equipo de SRE (Site Reliability Engineering) no es dueño de ningún
servicio de negocio: es responsable de la confiabilidad transversal de
toda la plataforma (observabilidad, capacidad, respuesta a incidentes) y
de coordinar entre los equipos dueños de servicio durante un incidente
de severidad 1.

## Integrantes

- **Óscar Villalba** — Tech Lead de SRE. Reporta a Ana Ruiz (CTO).
- **Daniela Restrepo** — Ingeniera de SRE, dueña de la guardia
  transversal fuera de horario laboral.

## Rol durante un incidente

Cuando un incidente cruza la guardia de más de un equipo (por ejemplo, un
incidente que empieza en `identidad` y termina afectando `pagos` y
`reportes-backend` en cadena), SRE es quien abre el canal de incidente,
nombra un Incident Commander y coordina el timeline que después alimenta
el postmortem (ver `incidentes/`).

## Guardia (on-call)

Rotación semanal entre Óscar Villalba y Daniela Restrepo. Es la guardia
que recibe la alerta transversal cuando dos o más guardias de equipo
reportan degradación simultánea — el primer indicio de que el problema es
de infraestructura compartida (`cola-eventos`, red interna) y no de un
servicio puntual.

## Canales

- `#sre-guardia` — guardia transversal.
- `#incidentes-nexora` — canal donde SRE abre y cierra cada incidente
  activo, con el timeline en vivo.

## A quién escalar

Cualquier persona de ingeniería puede abrir un incidente en
`#incidentes-nexora` y pingear a la guardia de SRE si sospecha que el
alcance cruza más de un equipo. SRE decide si declara severidad 1 según
`soporte/matriz-severidad-escalamiento.md` y arma el puente con las
guardias de los equipos dueños de los servicios involucrados.
