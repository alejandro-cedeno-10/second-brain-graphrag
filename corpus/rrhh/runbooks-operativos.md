---
titulo: Runbooks operativos — Nexora Corp
tipo: rrhh
equipo: SRE
---

# Runbooks operativos

Procedimientos paso a paso para operaciones frecuentes que no ameritan un
incidente, pero sí un procedimiento documentado en vez de reinventarlo
cada vez.

## Reintentar eventos perdidos de un tópico

1. Confirmar con `GET /cola-eventos/salud` qué tópico tiene lag o
   pérdida.
2. Confirmar con el equipo dueño del consumidor afectado que ya corrigió
   la causa (no republicar contra un consumidor todavía roto).
3. Ejecutar `POST /cola-eventos/topicos/{topico}/republicar` (requiere
   acceso de guardia de Plataforma).
4. Confirmar en el dashboard de `cola-eventos` que el lag vuelve a cero.

## Rotar credenciales de un servicio

1. Solicitar acceso temporal vía `#acceso-produccion` (ver
   `rrhh/politicas-internas.md`).
2. Generar la credencial nueva sin invalidar la vieja todavía.
3. Desplegar el cambio al servicio con ambas credenciales válidas.
4. Confirmar que el servicio usa la credencial nueva (métricas de
   autenticación exitosa) antes de invalidar la vieja.
5. Invalidar la credencial vieja y cerrar el acceso temporal.

## Onboarding de un nuevo conector ERP en integraciones-erp

1. Confirmar con el cliente el formato de export esperado.
2. Configurar el mapeo en `integraciones-erp` (config por cuenta, no por
   despliegue global).
3. Correr una sincronización manual (`POST /erp/sincronizaciones`) contra
   el ambiente de staging del cliente, si lo tiene.
4. Activar en producción solo después de que el cliente confirme que el
   export de staging es correcto.

## Verificar salud de una cadena de dependencias antes de un cambio breaking

Antes de un cambio breaking en cualquier servicio, correr el blast radius
del servicio (`grafo/traversal.py::blast_radius`, o el comando `graph-top`
de la demo interna) para confirmar qué servicios lo consumen
transitivamente, no solo directamente. Un cambio en `identidad`, por
ejemplo, puede afectar en cadena a `catalogo-planes` y de ahí a
`motor-impuestos` e `integraciones-erp`, aunque ninguno de esos dos
últimos llame a `identidad` directo.
