<script setup>
/**
 * El panel más importante de la demo: renderiza el veredicto de
 * `agent.guards.validate_relational_claims` (paso `guards.aplicados`,
 * `metadata.afirmaciones`) para que se lea desde el fondo del salón que
 * "si un salto no está respaldado, no se convierte en un hecho".
 *
 * `respaldada: true`  → la arista existe en el grafo, la afirmación queda.
 * `respaldada: false` → sin respaldo, la afirmación se declinó (degradada).
 */
const props = defineProps({
  afirmaciones: { type: Array, default: () => [] },
  abstencion: { type: Boolean, default: false },
  corriendo: { type: Boolean, default: false },
})
</script>

<template>
  <div class="panel anclaje">
    <div class="etiqueta">Anclaje al grafo — afirmaciones relacionales</div>

    <p v-if="props.abstencion" class="placeholder">
      Sin síntesis en este turno (abstención): no hay afirmaciones que anclar.
    </p>
    <p v-else-if="props.corriendo && props.afirmaciones.length === 0" class="placeholder">
      Esperando el guard de anclaje…
    </p>
    <p v-else-if="props.afirmaciones.length === 0" class="placeholder">
      Esta respuesta no hizo afirmaciones relacionales para anclar contra el grafo.
    </p>

    <ul v-else class="lista-afirmaciones">
      <li
        v-for="(afirmacion, i) in props.afirmaciones"
        :key="i"
        class="afirmacion"
        :class="afirmacion.respaldada ? 'respaldada' : 'degradada'"
      >
        <span class="veredicto">{{ afirmacion.respaldada ? '✅ RESPALDADA' : '⚠️ DEGRADADA' }}</span>
        <span class="detalle-afirmacion">
          <strong>{{ afirmacion.sujeto }}</strong>
          <span class="tipo-relacion">{{ afirmacion.tipo }}</span>
          <strong>{{ afirmacion.objeto }}</strong>
        </span>
        <span v-if="!afirmacion.respaldada" class="nota-degradada">
          Sin respaldo en el grafo: la afirmación se declinó.
        </span>
      </li>
    </ul>
  </div>
</template>

<style scoped>
.anclaje {
  display: flex;
  flex-direction: column;
  gap: 0.9rem;
}
.placeholder {
  color: var(--texto-tenue);
  font-style: italic;
}
.lista-afirmaciones {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.afirmacion {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
  padding: 0.9rem 1.1rem;
  border-radius: 12px;
  font-size: 1.15rem;
  border: 2px solid var(--borde);
  overflow-wrap: anywhere;
}
.afirmacion.respaldada {
  border-color: var(--ok);
  background: rgba(104, 211, 145, 0.12);
}
.afirmacion.degradada {
  border-color: var(--abstencion);
  background: rgba(246, 173, 85, 0.14);
}
.veredicto {
  font-weight: 800;
  font-size: 1rem;
  letter-spacing: 0.02em;
  white-space: nowrap;
}
.afirmacion.respaldada .veredicto {
  color: var(--ok);
}
.afirmacion.degradada .veredicto {
  color: var(--abstencion);
}
.detalle-afirmacion {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.4rem;
}
.tipo-relacion {
  color: var(--texto-tenue);
  font-style: italic;
}
.nota-degradada {
  flex-basis: 100%;
  color: var(--abstencion);
  font-size: 0.95rem;
  font-weight: 600;
}
</style>
