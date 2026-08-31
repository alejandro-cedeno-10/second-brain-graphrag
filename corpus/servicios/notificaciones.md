---
titulo: notificaciones — Servicio de notificaciones
tipo: servicio
equipo: Plataforma
---

# notificaciones

`notificaciones` centraliza el envío de notificaciones transaccionales de
Nexora Corp (email, push, SMS) disparadas por eventos de dominio de otros
servicios. No expone lógica de negocio propia: reacciona a eventos.

## Endpoints propios

### `POST /notificaciones/enviar`

Envío directo de una notificación ad-hoc, usado por soporte para casos
excepcionales. Body:

```json
{
  "account_id": "acc_8891",
  "canal": "email",
  "plantilla": "confirmacion_pago"
}
```

### `GET /notificaciones/historial/{account_id}`

Devuelve el historial de notificaciones enviadas a una cuenta.

## Integraciones basadas en eventos

`notificaciones` depende del evento **`billing.updated`** que emite
`core-billing`. Cada vez que `core-billing` publica `billing.updated`,
`notificaciones` evalúa el `new_state` del payload y dispara la plantilla
correspondiente (por ejemplo, `plan_actualizado` o `ciclo_cerrado`).

`notificaciones` también escucha eventos de `pagos` (`pago.confirmado`,
`pago.fallido`) para enviar confirmaciones de transacción al usuario.

## Consideraciones de diseño

`notificaciones` es un consumidor pasivo: no llama directamente a
`core-billing` vía API, solo reacciona a los eventos que este publica en
el bus interno. Ver `arquitectura/decisiones.md` para la razón de este
diseño basado en eventos en vez de llamadas síncronas.

## Operación

Propiedad del equipo de Plataforma. Escala horizontalmente según volumen
de eventos en el bus; sin estado propio más allá de logs de auditoría.
