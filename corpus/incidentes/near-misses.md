---
titulo: Registro de near misses — Nexora Corp
tipo: incidente
equipo: SRE
---

# Registro de near misses

Incidentes que casi ocurren pero se detectaron antes de tener impacto en
clientes. Se documentan con la misma disciplina que un postmortem, porque
son la señal más barata de un problema real.

## Near miss — Pool de conexiones de identidad en staging

Dos semanas antes de la caída documentada en
`incidentes/postmortem-identidad-caida.md`, el mismo síntoma (conexiones
sin cerrar tras un despliegue) apareció en el ambiente de staging de
`identidad`. Se resolvió reiniciando el servicio, sin investigar la causa
raíz porque no había impacto en producción. La causa raíz era la misma
que después causó el incidente real. Lección aplicada: un near miss en
staging que se resuelve con un reinicio, sin entender por qué pasó, no
está realmente cerrado.

## Near miss — Grado de conexión de catalogo-planes

Durante una prueba de carga interna, `catalogo-planes` alcanzó
temporalmente un grado de conexión inusualmente alto en el grafo de
dependencias (varios servicios nuevos consultándolo a la vez para
validar features de plan). No llegó a comportarse como un hub real
porque la mayoría de esas consultas eran de un mismo test que no
representaba tráfico real, pero motivó agregar el chequeo de guardia
anti-hub al traversal del grafo de dependencias, para que un caso real
similar no vuelva inservible un blast radius.

## Near miss — Reintento duplicado en motor-impuestos (pre-piloto)

Antes del piloto de multi-moneda, un test de integración detectó que
`pagos` podía reintentar un cobro sin verificar el estado real de la
transacción si `motor-impuestos` tardaba más de lo esperado. Se marcó
como "riesgo aceptado, baja probabilidad en producción" y no se corrigió
antes del lanzamiento del piloto. Es exactamente la causa raíz de
`incidentes/postmortem-facturacion-duplicada.md`. Lección aplicada: un
riesgo identificado en testing y no corregido antes de un piloto no deja
de ser un riesgo real solo porque el piloto ya se lanzó.
