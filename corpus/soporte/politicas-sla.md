---
titulo: Políticas de SLA — Nexora Corp
tipo: soporte
equipo: Soporte
---

# Políticas de SLA

## Tiempos de primera respuesta por plan

| Plan | Primera respuesta | Canal |
|---|---|---|
| Starter | 24 horas hábiles | Email |
| Pro | 8 horas hábiles | Email + chat |
| Enterprise | 1 hora, 24/7 | Chat prioritario + teléfono |

## Alcance

El SLA cubre disponibilidad de los servicios de cara al cliente
(`dashboard`, `reportes-frontend`, `onboarding`) y de las APIs que un
cliente enterprise consume directo (`integraciones-erp`). No cubre
tiempos de respuesta a solicitudes de feature nueva, que siguen el
proceso de roadmap de Producto.

## Créditos por incumplimiento

Un incidente de severidad 1 (ver
`soporte/matriz-severidad-escalamiento.md`) que exceda el SLA de
resolución da derecho a crédito según el contrato del cliente. Andrés
Mora (Soporte Nivel 2) es quien registra el crédito vía `POST
/billing/adjustments` de `core-billing`, siempre con referencia al
postmortem del incidente (ver `incidentes/`) como evidencia de causa
raíz.

## Excepciones

Incidentes causados por una integración del propio cliente (por ejemplo,
un endpoint de webhook mal configurado que rechaza entregas de
`webhooks`) no computan contra el SLA de Nexora Corp, aunque el cliente
los reporte como caída del servicio.
