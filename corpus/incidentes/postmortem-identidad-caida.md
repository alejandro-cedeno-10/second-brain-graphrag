---
titulo: Postmortem — Caída de identidad
tipo: incidente
equipo: Seguridad
---

# Postmortem — Caída de `identidad`

## Resumen

`identidad` estuvo degradado durante 47 minutos: `POST /identidad/login`
devolvía error en el 80% de los intentos. Las sesiones ya activas con
token vigente no se vieron afectadas.

## Impacto

Login nuevo bloqueado para la mayoría de usuarios durante la ventana del
incidente. `catalogo-planes` y `webhooks` también degradaron (ambos
consumen `GET /identidad/sesiones/{id}` de `identidad` para validar
sesiones de administración), aunque su impacto fue menor porque esas
operaciones son de baja frecuencia comparadas con login de usuario final.

## Timeline

- **10:02** — Alerta de latencia elevada en `identidad`.
- **10:06** — Guardia de Seguridad (Camilo Estévez) confirma degradación
  y declara severidad 1 según `soporte/matriz-severidad-escalamiento.md`.
- **10:08** — SRE (Óscar Villalba) abre el incidente en
  `#incidentes-nexora` y asume Incident Commander.
- **10:15** — Se identifica saturación de conexiones a la base de datos
  de sesiones, causada por un despliegue reciente que no cerraba
  conexiones al reciclar el pool.
- **10:41** — Rollback del despliegue.
- **10:49** — `identidad` recupera latencia normal; incidente cerrado.

## Causa raíz

Un cambio en el manejo del pool de conexiones de `identidad` no cerraba
conexiones inactivas correctamente, agotando el límite de conexiones
disponibles bajo carga normal de mañana.

## Acciones correctivas

- Agregar métrica de conexiones abiertas por proceso a `identidad`, con
  alerta antes de llegar al límite (completado).
- Agregar smoke test de pool de conexiones al pipeline de despliegue de
  `identidad` antes de promover a producción (completado).
- Revisar si `catalogo-planes` y `webhooks` deberían cachear el resultado
  de `GET /identidad/sesiones/{id}` por un margen corto, para reducir su
  exposición a una futura degradación de `identidad` (pendiente,
  asignado a Iván Rodas).

## Near miss relacionado

Ver `incidentes/near-misses.md` para un near miss similar detectado en
staging dos semanas antes, que no se priorizó como señal temprana.
