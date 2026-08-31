---
titulo: PRD — Portal de autoservicio
tipo: producto
equipo: Producto
---

# Portal de autoservicio

## Resumen

Un portal donde el cliente puede resolver por su cuenta las consultas más
frecuentes que hoy generan tickets de soporte Nivel 1: descargar una
factura, ver el historial de notificaciones, reconfigurar un endpoint de
webhook caído. El objetivo es reducir volumen de Nivel 1 (ver
`soporte/catalogo-casos.md` para los casos que más se repiten).

## Owner

**Nicolás Peralta** (equipo de Frontend) es el owner técnico. Fernanda
Ríos (Líder de Soporte/CX) es la sponsor de negocio, dado que el impacto
principal es reducir carga de soporte.

## Servicios que toca

- `reportes-backend`: expone `GET /reportes/mensual/{account_id}` al
  portal para que el cliente descargue su propia factura.
- `notificaciones`: expone `GET /notificaciones/historial/{account_id}`
  para que el cliente vea su propio historial sin pedirlo a soporte.
- `webhooks`: expone `GET /webhooks/entregas/{account_id}` para que el
  cliente diagnostique por su cuenta un webhook fallido antes de abrir un
  ticket.
- `identidad`: el portal reutiliza la sesión ya autenticada del cliente en
  `dashboard`, sin un login separado.

## Estado

En curso, fase de definición de alcance. La primera versión solo cubre
descarga de factura e historial de notificaciones; el diagnóstico de
webhooks queda para una segunda iteración.

## Métrica de éxito

Reducción del 30% en tickets de Nivel 1 de los tres casos más frecuentes
del catálogo de soporte, medido a los 60 días de lanzamiento.
