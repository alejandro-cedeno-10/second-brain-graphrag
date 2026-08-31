<script setup>
import { onMounted, ref } from 'vue'
import BarraPreguntas from './components/BarraPreguntas.vue'
import PanelAnclaje from './components/PanelAnclaje.vue'
import PanelGrafo from './components/PanelGrafo.vue'
import PanelRespuesta from './components/PanelRespuesta.vue'
import PanelTraza from './components/PanelTraza.vue'
import SelectorCamino from './components/SelectorCamino.vue'
import { streamAgUi } from './composables/useAgUiStream.js'

const preguntas = ref([])
const salud = ref(null)
const corriendo = ref(false)
const pasos = ref([])
const textoRespuesta = ref('')
const citas = ref([])
const abstencion = ref(false)
const caminosGrafo = ref([])
const error = ref(null)
const agenticoSeleccionado = ref(false)
const agenticoEjecutado = ref(null)
const ingenuoSeleccionado = ref(false)
const ingenuoEjecutado = ref(false)
const afirmacionesRelacionales = ref([])
const llamadasModelo = ref(0)
const detienePorModelo = ref(null)

async function cargarPreguntas() {
  const r = await fetch('/api/preguntas')
  preguntas.value = await r.json()
}

async function cargarSalud() {
  try {
    const r = await fetch('/api/salud')
    salud.value = await r.json()
  } catch {
    salud.value = { modo: 'desconocido', falkor_ok: false }
  }
}

function reiniciarEstadoDeTurno() {
  pasos.value = []
  textoRespuesta.value = ''
  citas.value = []
  abstencion.value = false
  caminosGrafo.value = []
  error.value = null
  afirmacionesRelacionales.value = []
  llamadasModelo.value = 0
  detienePorModelo.value = null
}

function procesarEstadoDelPaso(datos) {
  if (datos.stage === 'respuesta.final') {
    abstencion.value = !!datos.metadata?.abstencion
    citas.value = datos.metadata?.citas ?? []
    caminosGrafo.value = datos.metadata?.grafo ?? []
  } else if (datos.stage === 'guards.aplicados') {
    afirmacionesRelacionales.value = datos.metadata?.afirmaciones ?? []
  } else if (datos.stage === 'agente.llamadas_modelo') {
    llamadasModelo.value = datos.metadata?.llamadas_modelo ?? 0
    detienePorModelo.value = datos.metadata?.detiene_por ?? null
  } else if (datos.stage === 'sintesis.llm') {
    llamadasModelo.value = 1
  }
}

async function preguntar(pregunta) {
  reiniciarEstadoDeTurno()
  agenticoEjecutado.value = agenticoSeleccionado.value
  ingenuoEjecutado.value = ingenuoSeleccionado.value
  corriendo.value = true
  try {
    await streamAgUi(
      '/api/preguntar',
      { question: pregunta, agentic: agenticoSeleccionado.value, naive: ingenuoSeleccionado.value },
      (tipo, datos) => {
        if (tipo === 'STATE_DELTA') {
          pasos.value.push(datos)
          procesarEstadoDelPaso(datos)
        } else if (tipo === 'TOOL_CALL_START') {
          pasos.value.push(datos)
        } else if (tipo === 'TEXT_MESSAGE_CONTENT') {
          textoRespuesta.value += datos.delta
        } else if (tipo === 'RUN_ERROR') {
          error.value = datos.message
        }
      }
    )
  } catch (e) {
    error.value = String(e)
  } finally {
    corriendo.value = false
    cargarSalud()
  }
}

onMounted(() => {
  cargarPreguntas()
  cargarSalud()
})
</script>

<template>
  <div class="layout">
    <header class="encabezado">
      <div>
        <h1>Second Brain GraphRAG</h1>
        <p class="subtitulo">Demo en vivo — Nexora Corp</p>
      </div>
      <div v-if="salud" class="estado-salud">
        <span class="etiqueta">Modo</span>
        <strong>{{ salud.modo }}</strong>
        <span class="punto" :class="salud.falkor_ok ? 'ok' : 'error'"></span>
        <span>{{ salud.falkor_ok ? 'FalkorDB arriba' : 'FalkorDB caído' }}</span>
      </div>
    </header>

    <SelectorCamino
      v-model="agenticoSeleccionado"
      v-model:ingenuo="ingenuoSeleccionado"
      :disabled="corriendo"
      :camino-ejecutado="agenticoEjecutado"
      :ingenuo-ejecutado="ingenuoEjecutado"
    />

    <BarraPreguntas :preguntas="preguntas" :corriendo="corriendo" @preguntar="preguntar" />

    <div v-if="error" class="banner-error">{{ error }}</div>

    <main class="grilla">
      <PanelRespuesta
        class="celda-respuesta"
        :texto="textoRespuesta"
        :citas="citas"
        :abstencion="abstencion"
        :llamadas-modelo="llamadasModelo"
        :detiene-por-modelo="detienePorModelo"
        :camino-agentico="agenticoEjecutado"
        :corriendo="corriendo"
      />
      <PanelAnclaje
        class="celda-anclaje"
        :afirmaciones="afirmacionesRelacionales"
        :abstencion="abstencion"
        :corriendo="corriendo"
      />
      <PanelTraza class="celda-traza" :pasos="pasos" :corriendo="corriendo" />
      <PanelGrafo class="celda-grafo" :caminos="caminosGrafo" />
    </main>
  </div>
</template>

<style scoped>
.layout {
  max-width: 1600px;
  margin: 0 auto;
  padding: 1.5rem 2rem 3rem;
  display: flex;
  flex-direction: column;
  gap: 1.25rem;
}
.encabezado {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.subtitulo {
  color: var(--texto-tenue);
  margin: 0;
}
.estado-salud {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  background: var(--bg-panel);
  border: 1px solid var(--borde);
  border-radius: 999px;
  padding: 0.5rem 1rem;
}
.punto {
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
.punto.ok {
  background: var(--ok);
}
.punto.error {
  background: var(--error);
}
.banner-error {
  background: rgba(252, 129, 129, 0.15);
  border: 1px solid var(--error);
  color: var(--error);
  border-radius: 10px;
  padding: 0.8rem 1rem;
}
.grilla {
  display: grid;
  grid-template-columns: 1.3fr 1fr;
  grid-template-areas:
    'respuesta grafo'
    'anclaje grafo'
    'traza grafo';
  align-items: start;
  gap: 1.25rem;
}
.celda-respuesta {
  grid-area: respuesta;
}
.celda-anclaje {
  grid-area: anclaje;
}
.celda-traza {
  grid-area: traza;
}
.celda-grafo {
  grid-area: grafo;
}
@media (max-width: 1100px) {
  .grilla {
    grid-template-columns: 1fr;
    grid-template-areas:
      'respuesta'
      'anclaje'
      'grafo'
      'traza';
  }
}
</style>
