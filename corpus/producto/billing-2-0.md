---
titulo: PRD — Billing 2.0
tipo: producto
equipo: Producto
---

# Billing 2.0

## Resumen

Billing 2.0 es la re-arquitectura del núcleo de facturación de Nexora
Corp: consolida `core-billing`, `catalogo-planes` y `motor-impuestos`
detrás de un único contrato de API versionado, para que Producto pueda
lanzar cambios de pricing sin coordinar tres despliegues separados cada
vez.

## Owner

**Renata Cifuentes** (Tech Lead de Pagos) es la owner técnica de Billing
2.0. Carlos Medina (VP Producto) es el sponsor de negocio.

## Servicios que toca

- `core-billing`, `catalogo-planes` y `motor-impuestos`: se consolidan
  detrás del nuevo contrato versionado.
- `pagos` y `reportes-backend`: consumidores actuales de esos tres
  servicios, migran a la nueva API en la segunda fase.

## Dependencia crítica de la fecha de lanzamiento

`billing-2-0` depende de `auth-cache`: el nuevo contrato consolidado
valida sesión de administrador en cada operación de escritura (cambio de
plan, ajuste de tarifa, recálculo de impuestos) contra `GET
/auth-cache/verificar/{token}`, en vez de contra `identidad` directo,
para no repetir la carga de alta frecuencia que hoy ya maneja
`auth-cache` para `catalogo-planes`. Sin esa integración validada, Billing
2.0 no puede salir a producción con el volumen de escrituras que Producto
proyecta para el lanzamiento.

## Riesgo

El equipo dueño de `auth-cache` es el **equipo de Identidad**, no
Plataforma ni Pagos: cualquier retraso en la disponibilidad de `GET
/auth-cache/verificar/{token}` para el volumen que Billing 2.0 necesita
es un riesgo de fecha que debe coordinarse con el equipo de Identidad, no
con Plataforma (ver `org/equipo-identidad.md` para a quién escalar).

## Estado

En curso, fase de integración con `auth-cache`. La fecha de lanzamiento
está condicionada a que esa integración quede validada bajo carga.
