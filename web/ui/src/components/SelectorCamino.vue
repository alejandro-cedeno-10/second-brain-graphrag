<script setup>
/**
 * Control grande (pensado para proyector) que elige qué camino del backend
 * corre el próximo turno: el pipeline fijo (`agentic:false`) o el loop
 * agéntico de Strands (`agentic:true`) — ver `web/api.py`.
 *
 * Deliberadamente separa "qué está seleccionado" (`modelValue`, lo que
 * dispara la próxima pregunta) de "en qué corrió la última respuesta"
 * (`caminoEjecutado`): el speaker puede cambiar el selector antes de que
 * termine de imprimirse el turno anterior, así que el badge de abajo lee
 * el camino que efectivamente generó lo que se ve en pantalla, no el
 * estado actual del toggle.
 *
 * El toggle "Modo ingenuo" (`ingenuo`/`update:ingenuo`) vive en el mismo
 * panel, junto al selector de camino, a propósito: no es un tercer camino
 * del backend, es un guion de DEMOSTRACIÓN que reemplaza únicamente la
 * síntesis de Billing 2.0 por la respuesta deliberadamente mala de la
 * diapositiva de apertura (`demo.TEXTO_P_BILLING_INGENUO`), para que el
 * speaker muestre en vivo al `PanelAnclaje` degradándola — funciona igual
 * sobre cualquiera de los dos caminos. Nunca es el comportamiento por
 * defecto: arranca apagado y ninguna otra pregunta del guion cambia.
 */
const props = defineProps({
  modelValue: { type: Boolean, default: false },
  disabled: { type: Boolean, default: false },
  caminoEjecutado: { type: Boolean, default: null },
  ingenuo: { type: Boolean, default: false },
  ingenuoEjecutado: { type: Boolean, default: false },
})
const emit = defineEmits(['update:modelValue', 'update:ingenuo'])

function elegir(agentico) {
  if (props.disabled || props.modelValue === agentico) return
  emit('update:modelValue', agentico)
}

function alternarIngenuo() {
  if (props.disabled) return
  emit('update:ingenuo', !props.ingenuo)
}
</script>

<template>
  <div class="panel selector-camino">
    <div class="etiqueta">Camino del agente</div>
    <div class="botones" role="group" aria-label="Selector de camino del agente">
      <button
        type="button"
        class="opcion fijo"
        :class="{ activo: !props.modelValue }"
        :disabled="props.disabled"
        @click="elegir(false)"
      >
        🧭 Fijo
        <span class="sub">orden determinista</span>
      </button>
      <button
        type="button"
        class="opcion agentico"
        :class="{ activo: props.modelValue }"
        :disabled="props.disabled"
        @click="elegir(true)"
      >
        🤖 Agéntico
        <span class="sub">el modelo decide</span>
      </button>
    </div>
    <div
      v-if="props.caminoEjecutado !== null"
      class="ejecutado"
      :class="props.caminoEjecutado ? 'agentico' : 'fijo'"
    >
      Esta respuesta corrió en modo
      <strong>{{ props.caminoEjecutado ? 'AGÉNTICO' : 'FIJO' }}</strong>
    </div>

    <div class="separador"></div>

    <button
      type="button"
      class="toggle-ingenuo"
      :class="{ activo: props.ingenuo }"
      :disabled="props.disabled"
      :aria-pressed="props.ingenuo"
      @click="alternarIngenuo"
    >
      <span class="rotulo-ingenuo">🧪 Modo ingenuo</span>
      <span class="estado-ingenuo">{{ props.ingenuo ? 'ACTIVO' : 'apagado' }}</span>
    </button>
    <p class="nota-ingenuo">
      Guion de DEMOSTRACIÓN, no un modo de producción: fuerza una síntesis
      deliberadamente mala en la pregunta de Billing 2.0 (le echa la culpa a
      Plataforma y a ADR-017) para mostrar en vivo cómo el anclaje al grafo
      la degrada. Ninguna otra pregunta cambia.
    </p>
    <div v-if="props.ingenuoEjecutado" class="ejecutado ingenuo">
      Esta respuesta corrió con el <strong>GUION INGENUO</strong> activo
    </div>
  </div>
</template>

<style scoped>
.selector-camino {
  display: flex;
  flex-direction: column;
  gap: 0.85rem;
}
.botones {
  display: flex;
  gap: 0.85rem;
}
.opcion {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.25rem;
  padding: 1rem 1.25rem;
  font-size: 1.2rem;
  font-weight: 700;
  border-radius: 12px;
  border: 2px solid var(--borde);
  background: var(--bg-panel-alt);
  color: var(--texto-tenue);
  cursor: pointer;
  transition: all 0.15s ease;
}
.opcion .sub {
  font-size: 0.8rem;
  font-weight: 400;
  text-transform: none;
  letter-spacing: normal;
}
.opcion:hover:not(:disabled) {
  border-color: var(--texto-tenue);
  color: var(--texto);
}
.opcion:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.opcion.fijo.activo {
  border-color: var(--camino-fijo);
  background: rgba(34, 211, 238, 0.15);
  color: var(--camino-fijo);
}
.opcion.agentico.activo {
  border-color: var(--camino-agentico);
  background: rgba(192, 132, 252, 0.15);
  color: var(--camino-agentico);
}
.ejecutado {
  font-size: 1rem;
  color: var(--texto-tenue);
  padding: 0.6rem 0.9rem;
  border-radius: 10px;
  background: var(--bg-panel-alt);
  border: 1px solid var(--borde);
}
.ejecutado.fijo strong {
  color: var(--camino-fijo);
}
.ejecutado.agentico strong {
  color: var(--camino-agentico);
}
.separador {
  height: 1px;
  background: var(--borde);
}
.toggle-ingenuo {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  padding: 0.75rem 1.1rem;
  font-size: 1.05rem;
  font-weight: 700;
  border-radius: 10px;
  border: 2px dashed var(--borde);
  background: var(--bg-panel-alt);
  color: var(--texto-tenue);
  cursor: pointer;
  transition: all 0.15s ease;
}
.toggle-ingenuo:hover:not(:disabled) {
  border-color: var(--texto-tenue);
  color: var(--texto);
}
.toggle-ingenuo:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}
.toggle-ingenuo.activo {
  border-style: solid;
  border-color: var(--abstencion);
  background: rgba(246, 173, 85, 0.15);
  color: var(--abstencion);
}
.estado-ingenuo {
  font-size: 0.8rem;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  padding: 0.2rem 0.6rem;
  border-radius: 999px;
  background: var(--bg-panel);
  border: 1px solid var(--borde);
}
.toggle-ingenuo.activo .estado-ingenuo {
  border-color: var(--abstencion);
}
.nota-ingenuo {
  margin: 0;
  font-size: 0.85rem;
  color: var(--texto-tenue);
  line-height: 1.5;
}
.ejecutado.ingenuo {
  border-color: var(--abstencion);
  color: var(--abstencion);
}
.ejecutado.ingenuo strong {
  color: var(--abstencion);
}
</style>
