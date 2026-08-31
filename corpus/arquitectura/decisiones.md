---
titulo: Decisiones de arquitectura (ADRs) — Nexora Corp
tipo: decision
equipo: Arquitectura
---

# Registro de decisiones de arquitectura

Este documento agrupa las ADRs (Architecture Decision Records) cortas más
relevantes para los servicios y frontends descritos en esta base de
conocimiento.

## ADR-014: Google Tag Manager como canal de tracking en reportes-frontend

**Contexto:** `reportes-frontend` necesitaba tracking de uso básico
(aperturas de reporte, exportaciones) sin comprometer al equipo de Datos
a mantener un SDK de analítica de producto adicional.

**Decisión:** usar Google Tag Manager (GTM) como único canal de tracking
en `reportes-frontend`, en vez de integrar Amplitude como en `dashboard`
y `onboarding`.

**Razón:** `reportes-frontend` es una superficie de bajo tráfico y
alcance acotado (solo clientes que ya pagan, consultando su propio
reporte). El costo de mantener el catálogo de eventos de Amplitude y su
gobierno (ver Proyecto Beta) no se justificaba frente a las métricas
agregadas que ya provee GTM + Google Analytics 4. Se decidió no adoptar
Amplitude en este frontend salvo que el volumen o la necesidad de
funnels cambie.

**Estado:** vigente.

## ADR-021: Evento `billing.updated` en vez de llamadas síncronas

**Contexto:** antes de esta decisión, `notificaciones` llamaba de forma
síncrona a `core-billing` cada vez que necesitaba saber si el estado de
facturación de una cuenta había cambiado, generando acoplamiento y
timeouts en cascada cuando `core-billing` estaba bajo carga.

**Decisión:** `core-billing` publica el evento de dominio `billing.updated`
en el bus de eventos interno; `notificaciones` se suscribe a ese evento en
vez de invocar la API de `core-billing` directamente.

**Razón:** desacopla la disponibilidad de `notificaciones` de la de
`core-billing`, y permite agregar más consumidores del evento sin tocar
`core-billing`.

**Estado:** vigente.

## ADR-027: pagos como intermediario de tarifas para reportes-backend

**Contexto:** `reportes-backend` necesitaba el historial de transacciones
para la sección de conciliación de sus reportes mensuales.

**Decisión:** `reportes-backend` no llama directamente a `pagos` para
tarifas; consume el historial de transacciones vía `pagos`, que a su vez
valida tarifas contra `core-billing`. `reportes-backend` sigue llamando
directo a `core-billing` solo para `POST /billing/summary`.

**Estado:** vigente.

## ADR-017: Caché distribuida de verificación de sesión (`auth-cache`)

**Contexto:** los servicios que verifican sesión con alta frecuencia
(varias veces por segundo en horario pico) recalculaban la verificación
completa contra `identidad` en cada llamada, agregando latencia
innecesaria a operaciones que no cambian el resultado de esa verificación
de un milisegundo al otro.

**Decisión:** introducir `auth-cache`, una caché distribuida con
expiración corta, como servicio propio separado de `identidad`, con su
propio equipo dueño (Identidad) y su propia guardia. Los servicios de
alta frecuencia consultan primero `auth-cache` antes de recalcular contra
`identidad`.

**Razón:** separar la caché en un servicio propio, en vez de agregarla
como una capa interna de `identidad`, permite escalarla y operarla de
forma independiente del resto de la superficie de `identidad` (login,
refresco de tokens), que tiene un perfil de carga distinto.

**Alcance:** esta es la decisión técnica que documenta por qué
`auth-cache` existe como servicio propio del equipo de Identidad. No
evalúa por sí sola el riesgo de fecha de ninguna iniciativa de producto
que dependa de `auth-cache` — ese riesgo se coordina con el equipo dueño
de `auth-cache` caso por caso, no se desprende de esta ADR.

**Estado:** vigente.
