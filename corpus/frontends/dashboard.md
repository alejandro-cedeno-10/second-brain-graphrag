---
titulo: dashboard — Aplicación de panel de producto
tipo: frontend
equipo: Producto
---

# dashboard

`dashboard` es la aplicación principal donde los usuarios de Nexora Corp
gestionan su cuenta, ven métricas de uso y administran su plan. Es la
superficie de producto con mayor tráfico y, por eso, la de instrumentación
de analítica más exhaustiva de toda la compañía.

## Stack de analítica: Amplitude

`dashboard` integra el SDK de **Amplitude** (`@amplitude/analytics-browser`)
como sistema principal de analítica de producto. Cada interacción
relevante del usuario se registra como un evento de Amplitude con un
esquema de propiedades definido y versionado por Proyecto Beta (ver
`org/proyectos.md`).

## Catálogo de eventos de Amplitude

| Evento Amplitude | Disparador | Propiedades clave |
|---|---|---|
| `dashboard_viewed` | Carga inicial del panel | `account_id`, `plan` |
| `plan_upgrade_started` | Click en "Mejorar plan" | `plan_actual`, `plan_destino` |
| `plan_upgrade_completed` | Confirmación de upgrade | `plan_destino`, `monto` |
| `widget_added` | Usuario agrega un widget | `widget_type`, `posicion` |
| `widget_removed` | Usuario quita un widget | `widget_type` |
| `export_metrics_clicked` | Click en exportar métricas | `formato`, `rango_fechas` |
| `settings_updated` | Cambio en configuración de cuenta | `campo_modificado` |
| `invite_sent` | Invitación a nuevo miembro | `rol_invitado` |
| `search_performed` | Búsqueda dentro del panel | `query_length`, `resultados` |
| `notification_preference_changed` | Cambio de preferencias de notificación | `canal`, `activado` |

## Ejemplo de instrumentación con Amplitude

```js
import { track } from "@amplitude/analytics-browser";

track("plan_upgrade_completed", {
  plan_destino: "enterprise",
  monto: 199.0,
});
```

## Gobierno del catálogo de eventos de Amplitude

Proyecto Beta define las reglas de naming (snake_case, verbo en pasado
para acciones completadas) y las propiedades obligatorias por evento de
Amplitude. Todo evento nuevo pasa por revisión de María Salas antes de
mergear a producción.

## Integraciones

`dashboard` consume `POST /reportes/exportar` de `reportes-backend` para
la funcionalidad de exportación de métricas, además de su integración
central con Amplitude para analítica de producto.
