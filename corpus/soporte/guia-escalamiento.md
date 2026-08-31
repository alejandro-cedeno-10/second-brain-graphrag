---
titulo: Guía de escalamiento — Nexora Corp
tipo: soporte
equipo: Soporte
---

# Guía de escalamiento

## Paso a paso para Soporte Nivel 1

1. Buscar el síntoma en `soporte/catalogo-casos.md`. La mayoría de los
   reclamos ya tienen causa raíz y solución documentada ahí.
2. Si no hay caso previo, o el caso previo no aplica, confirmar el
   servicio involucrado y consultar la severidad probable en
   `soporte/matriz-severidad-escalamiento.md`.
3. Escalar a Nivel 2 (Andrés Mora o Bianca Salcedo, según disponibilidad)
   con: cuenta afectada, servicio sospechoso, y evidencia ya recolectada
   (respuesta de los endpoints de solo lectura como `GET
   /pagos/estado/{id}` o `GET /webhooks/entregas/{account_id}`).

## Paso a paso para Soporte Nivel 2

1. Confirmar causa raíz con los endpoints internos correspondientes.
2. Si la causa raíz requiere un cambio en un servicio (no un ajuste
   puntual de cuenta), abrir el incidente en `#incidentes-nexora` y
   seguir la matriz de escalamiento a la guardia del equipo dueño.
3. Si la causa raíz ya está resuelta y solo falta compensar al cliente
   (crédito, reenvío de notificación), resolverlo directo sin escalar a
   ingeniería.

## Cuándo NO escalar a ingeniería

- El caso ya está en el catálogo con solución de Nivel 1 o Nivel 2.
- El problema es de configuración del propio cliente (endpoint de
  webhook que rechaza entregas, credenciales vencidas de su lado).
- Es una pregunta de producto/roadmap, no un incidente — esas van al
  canal `#ventas-vs-producto` o directo a Producto, no a una guardia de
  ingeniería.

## Contacto de última instancia

Si una guardia no responde en 15 minutos durante un incidente de
severidad 1, escalar a la guardia de SRE (`#sre-guardia`), que tiene
autoridad para nombrar Incident Commander y convocar a cualquier equipo.
