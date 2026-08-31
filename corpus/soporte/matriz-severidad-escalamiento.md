---
titulo: Matriz de severidad y escalamiento — Nexora Corp
tipo: soporte
equipo: Soporte
---

# Matriz de severidad y escalamiento

## Severidades

- **Severidad 1**: servicio de camino crítico caído o degradado para
  todas las cuentas (`pagos`, `identidad`, `core-billing`). Incident
  Commander de SRE obligatorio. Respuesta inmediata, 24/7.
- **Severidad 2**: servicio degradado para un subconjunto de cuentas, o
  servicio no crítico caído por completo (`webhooks`, `integraciones-erp`,
  `reportes-backend`). Respuesta en horario extendido.
- **Severidad 3**: bug conocido con workaround documentado en el
  catálogo de casos, sin impacto en disponibilidad. Se atiende en
  horario laboral.

## Quién declara la severidad

Cualquier persona de soporte o ingeniería puede proponer una severidad al
abrir el incidente en `#incidentes-nexora`; SRE la confirma o la ajusta
según `org/equipo-sre.md`.

## Escalamiento por servicio

| Servicio afectado | Guardia primaria | Escalación secundaria |
|---|---|---|
| `pagos`, `motor-impuestos` | Guardia de Pagos | Renata Cifuentes |
| `core-billing`, `catalogo-planes`, `webhooks`, `cola-eventos`, `notificaciones` | Guardia de Plataforma | Diego Torres |
| `identidad` | Guardia de Seguridad | Rodrigo Fajardo |
| `reportes-backend`, `reportes-frontend`, `integraciones-erp`, `data-warehouse` | Guardia de Datos | Marcos Elguera |
| `dashboard`, `onboarding` | Guardia de Plataforma (primer respondiente) | María Salas |
| Incidente que cruza más de una guardia | Guardia de SRE | Óscar Villalba |

## Regla de oro

Ante la duda de a quién escalar, escalar primero a la guardia de SRE
(`#sre-guardia`): coordinar de más nunca es el error caro en un
incidente de severidad 1; no escalar a tiempo sí lo es.
