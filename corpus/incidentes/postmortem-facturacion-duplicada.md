---
titulo: Postmortem — Facturación duplicada en el piloto de multi-moneda
tipo: incidente
equipo: Pagos
---

# Postmortem — Facturación duplicada en el piloto de multi-moneda

## Resumen

Durante el piloto de la feature multi-moneda (ver
`producto/prd-multi-moneda.md`) en la región CO, 34 cuentas enterprise
recibieron dos cargos por el mismo período de facturación.

## Impacto

34 cuentas afectadas, todas en la región CO, todas en el piloto de
multi-moneda. Ningún cliente fuera del piloto se vio afectado.

## Timeline

- **Día 1, 03:00** — Job nocturno de `reportes-backend` genera el
  resumen mensual; `core-billing` recalcula tarifas y publica
  `billing.updated`.
- **Día 1, 03:04** — `pagos` reintenta un cobro que había quedado en
  estado `pending` por un timeout transitorio de `motor-impuestos`, sin
  darse cuenta de que el primer intento sí había capturado el cobro del
  lado de la pasarela externa.
- **Día 2** — Primeros reclamos de clientes vía soporte (caso 002 del
  catálogo, ver `soporte/catalogo-casos.md`).
- **Día 2, tarde** — Equipo de Pagos confirma el patrón: el problema
  aparece solo cuando `motor-impuestos` responde después del timeout de
  `pagos` pero antes de su propio timeout interno.

## Causa raíz

`pagos` trataba un timeout de `motor-impuestos` como señal de "el cobro
no se intentó" y reintentaba desde cero, sin verificar primero el estado
real de la transacción contra la pasarela externa. Cuando
`motor-impuestos` en realidad sí había respondido (tarde, pero a tiempo
para que `pagos` completara el primer intento), el reintento generaba un
segundo cargo real.

## Acciones correctivas

- `pagos` ahora verifica el estado de la transacción contra la pasarela
  externa antes de reintentar un cobro que salió de un timeout hacia
  `motor-impuestos` (completado).
- Créditos aplicados a las 34 cuentas afectadas vía `POST
  /billing/adjustments`, con referencia a este postmortem (completado).
- Reducir el timeout interno de `motor-impuestos` para que expire antes
  que el de `pagos`, no después (completado).

## Estado del piloto

El piloto de multi-moneda sigue activo en región CO; la expansión a
región MX quedó bloqueada hasta confirmar 30 días sin recurrencia (ver
`producto/prd-multi-moneda.md`).
