---
titulo: onboarding — Guía de integración de analítica
tipo: frontend
equipo: Producto
---

# onboarding

`onboarding` es el flujo de bienvenida que guía a un usuario nuevo de
Nexora Corp desde el registro hasta su primera acción de valor dentro del
producto. Esta guía documenta cómo instrumentar Amplitude en cada paso.

## Por qué Amplitude en onboarding

El flujo de onboarding es el momento de mayor abandono de todo el
producto. Amplitude es el sistema elegido para medir el funnel paso a
paso, porque permite construir embudos (funnels) y cohortes sin trabajo
adicional de backend, a diferencia de otras herramientas evaluadas.

## Guía de integración paso a paso

### 1. Instalar el SDK de Amplitude

```bash
npm install @amplitude/analytics-browser
```

### 2. Inicializar Amplitude al arrancar la app

```js
import { init } from "@amplitude/analytics-browser";

init(AMPLITUDE_API_KEY, undefined, {
  defaultTracking: { sessions: true, pageViews: true },
});
```

### 3. Identificar al usuario en Amplitude

```js
import { identify, Identify } from "@amplitude/analytics-browser";

const identifyEvent = new Identify();
identifyEvent.set("plan", "trial");
identify(identifyEvent);
```

### 4. Instrumentar los pasos del funnel en Amplitude

| Paso del funnel | Evento Amplitude |
|---|---|
| Registro completado | `onboarding_signup_completed` |
| Verificación de email | `onboarding_email_verified` |
| Primer proyecto creado | `onboarding_first_project_created` |
| Primer widget configurado | `onboarding_first_widget_configured` |
| Onboarding completado | `onboarding_completed` |

### 5. Validar en el debugger de Amplitude

Amplitude expone un modo debug (`amplitude.debug()`) para verificar en
tiempo real que los eventos llegan con las propiedades esperadas antes de
publicar a producción.

## Checklist de salida a producción

- [ ] Todos los eventos de la tabla del funnel están instrumentados en Amplitude.
- [ ] Las propiedades de usuario están seteadas antes del primer evento.
- [ ] El funnel se ve completo en el dashboard de Amplitude de staging.
- [ ] Revisión de naming por el dueño del catálogo de eventos de Amplitude (Proyecto Beta).

## Referencias

Para el catálogo completo de eventos de producto ya instrumentados, ver
`frontends/dashboard.md`. Para quién gobierna el catálogo, ver
`org/proyectos.md`.
