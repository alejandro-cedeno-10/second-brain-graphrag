<script setup>
import { computed, ref } from 'vue'

const props = defineProps({
  texto: { type: String, default: '' },
  citas: { type: Array, default: () => [] },
  abstencion: { type: Boolean, default: false },
  llamadasModelo: { type: Number, default: 0 },
  detienePorModelo: { type: String, default: null },
  caminoAgentico: { type: Boolean, default: null },
  corriendo: { type: Boolean, default: false },
})

const citaAbierta = ref(null)

const PATRON_CITA = /\[source:([^\]]+)\]/g

const segmentos = computed(() => {
  const partes = []
  let ultimo = 0
  let m
  PATRON_CITA.lastIndex = 0
  while ((m = PATRON_CITA.exec(props.texto)) !== null) {
    if (m.index > ultimo) partes.push({ tipo: 'texto', valor: props.texto.slice(ultimo, m.index) })
    const docId = m[1].trim()
    const cita = props.citas.find((c) => c.documento === docId)
    partes.push({ tipo: 'cita', valor: docId, cita })
    ultimo = m.index + m[0].length
  }
  if (ultimo < props.texto.length) partes.push({ tipo: 'texto', valor: props.texto.slice(ultimo) })
  return partes
})

function abrirCita(cita) {
  citaAbierta.value = citaAbierta.value === cita ? null : cita
}

const mensajeAbstencion = computed(() => {
  if (props.llamadasModelo === 0) return 'El modelo NUNCA fue invocado para este turno.'
  const vez = props.llamadasModelo === 1 ? 'vez' : 'veces'
  const razon = props.detienePorModelo ? ` (detiene_por=${props.detienePorModelo})` : ''
  return `El modelo llamó ${props.llamadasModelo} ${vez} pero NUNCA redactó una respuesta${razon}.`
})

const mensajeLlm = computed(() =>
  props.caminoAgentico
    ? `El modelo fue invocado ${props.llamadasModelo} veces (decidir + redactar) para esta respuesta.`
    : 'El modelo fue invocado una vez para sintetizar esta respuesta.'
)
</script>

<template>
  <div class="panel respuesta" :class="{ abstencion: props.abstencion }">
    <div class="etiqueta">Respuesta</div>

    <div v-if="props.caminoAgentico !== null" class="fila-estado">
      <div class="badge-camino" :class="props.caminoAgentico ? 'agentico' : 'fijo'">
        {{ props.caminoAgentico ? '🤖 Modo agéntico' : '🧭 Modo fijo' }}
      </div>
      <div class="contador-llamadas" :class="{ cero: props.llamadasModelo === 0 }">
        <span class="numero">{{ props.llamadasModelo }}</span>
        <span class="etiqueta-contador">
          llamada{{ props.llamadasModelo === 1 ? '' : 's' }} al modelo
        </span>
      </div>
    </div>

    <div v-if="props.abstencion" class="banner-abstencion">
      <strong>ABSTENCIÓN</strong> — el gate de cobertura cortó antes de la síntesis.
      <span class="destacado">{{ mensajeAbstencion }}</span>
    </div>
    <div v-else-if="!props.corriendo && props.llamadasModelo > 0" class="banner-llm">
      {{ mensajeLlm }}
    </div>

    <p v-if="!props.texto && props.corriendo" class="placeholder">Generando respuesta…</p>

    <p class="cuerpo">
      <template v-for="(seg, i) in segmentos" :key="i">
        <span v-if="seg.tipo === 'texto'">{{ seg.valor }}</span>
        <button v-else class="cita-inline" type="button" @click="abrirCita(seg.cita)">
          [{{ seg.valor }}]
        </button>
      </template>
    </p>

    <div v-if="citaAbierta" class="fragmento">
      <div class="etiqueta">Fuente: {{ citaAbierta.documento }}</div>
      <p>{{ citaAbierta.fragmento }}</p>
    </div>
  </div>
</template>

<style scoped>
.respuesta {
  min-height: 180px;
}
.respuesta.abstencion {
  border-color: var(--abstencion);
}
.fila-estado {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
  margin-bottom: 1rem;
}
.badge-camino {
  font-weight: 700;
  font-size: 1rem;
  padding: 0.5rem 0.9rem;
  border-radius: 999px;
  border: 2px solid var(--borde);
}
.badge-camino.fijo {
  border-color: var(--camino-fijo);
  color: var(--camino-fijo);
  background: rgba(34, 211, 238, 0.12);
}
.badge-camino.agentico {
  border-color: var(--camino-agentico);
  color: var(--camino-agentico);
  background: rgba(192, 132, 252, 0.12);
}
.contador-llamadas {
  display: flex;
  align-items: baseline;
  gap: 0.45rem;
  padding: 0.4rem 0.9rem;
  border-radius: 999px;
  background: var(--bg-panel-alt);
  border: 1px solid var(--borde);
}
.contador-llamadas .numero {
  font-size: 1.4rem;
  font-weight: 800;
  color: var(--texto);
}
.contador-llamadas.cero .numero {
  color: var(--abstencion);
}
.contador-llamadas .etiqueta-contador {
  color: var(--texto-tenue);
  font-size: 0.9rem;
}
.banner-abstencion {
  background: rgba(246, 173, 85, 0.15);
  border: 1px solid var(--abstencion);
  color: var(--abstencion);
  border-radius: 10px;
  padding: 0.9rem 1.1rem;
  margin-bottom: 1rem;
  font-size: 1.05rem;
}
.banner-abstencion .destacado {
  display: block;
  margin-top: 0.3rem;
  font-weight: 700;
}
.banner-llm {
  background: rgba(104, 211, 145, 0.12);
  border: 1px solid var(--ok);
  color: var(--ok);
  border-radius: 10px;
  padding: 0.6rem 1rem;
  margin-bottom: 1rem;
  font-size: 0.95rem;
}
.cuerpo {
  font-size: 1.25rem;
  line-height: 1.7;
  white-space: pre-wrap;
}
.placeholder {
  color: var(--texto-tenue);
  font-style: italic;
}
.cita-inline {
  background: rgba(34, 211, 238, 0.15);
  border: 1px solid var(--acento-fuerte);
  color: var(--acento-fuerte);
  border-radius: 6px;
  padding: 0 0.35rem;
  font-size: 0.9em;
  cursor: pointer;
}
.fragmento {
  margin-top: 1.25rem;
  padding-top: 1rem;
  border-top: 1px dashed var(--borde);
}
.fragmento p {
  color: var(--texto-tenue);
}
</style>
