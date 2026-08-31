<script setup>
const props = defineProps({
  pasos: { type: Array, default: () => [] },
  corriendo: { type: Boolean, default: false },
})

const STAGE_INFO = {
  'objetivos.resueltos': { icono: '🎯', titulo: 'Objetivos resueltos' },
  'herramienta.buscar_documentos': { icono: '🔍', titulo: 'Búsqueda documental (híbrida + rerank)' },
  'herramienta.navegar_grafo': { icono: '🕸️', titulo: 'Navegación de grafo (openCypher [*1..3])' },
  'herramienta.navegar_grafo.error': { icono: '⚠️', titulo: 'Grafo no disponible — degradado a vectorial' },
  'grafo.traversal.guardia_anti_hub': { icono: '🚧', titulo: 'Guardia anti-hub (corta expansión de nodo saturado)' },
  'gate.cobertura': { icono: '🚪', titulo: 'Gate de cobertura' },
  'gate.abstencion': { icono: '🛑', titulo: 'Abstención — el modelo no redacta', clase: 'critico' },
  'sintesis.llm': { icono: '🤖', titulo: 'Síntesis — llamada de redacción al LLM' },
  'agente.llamadas_modelo': { icono: '🔢', titulo: 'Llamadas al modelo (loop agéntico)' },
  'guards.aplicados': { icono: '🛡️', titulo: 'Guards aplicados (citas, URLs, anclaje al grafo)' },
  'guards.error': { icono: '⚠️', titulo: 'Guards (fail-open: error registrado)' },
  canario: { icono: '🐤', titulo: 'Canario / métricas de observabilidad' },
  'respuesta.final': { icono: '📤', titulo: 'Respuesta final' },
}

function info(stage) {
  return STAGE_INFO[stage] ?? { icono: '•', titulo: stage }
}
</script>

<template>
  <div class="panel traza">
    <div class="etiqueta">Traza del pipeline en vivo</div>
    <p v-if="props.pasos.length === 0 && !props.corriendo" class="placeholder">
      Dispará una pregunta para ver el pipeline correr paso a paso.
    </p>
    <ol class="lista">
      <li
        v-for="(paso, i) in props.pasos"
        :key="i"
        class="paso"
        :class="{ critico: info(paso.stage).clase === 'critico' }"
      >
        <span class="icono">{{ info(paso.stage).icono }}</span>
        <div class="cuerpo-paso">
          <div class="titulo-paso">
            {{ info(paso.stage).titulo }}
            <span v-if="typeof paso.duracionMs === 'number'" class="tiempo">+{{ paso.duracionMs }}ms</span>
          </div>
          <div class="detalle-paso">{{ paso.detail }}</div>
        </div>
      </li>
      <li v-if="props.corriendo" class="paso pendiente">
        <span class="icono">⏳</span>
        <div class="cuerpo-paso"><div class="titulo-paso">corriendo…</div></div>
      </li>
    </ol>
  </div>
</template>

<style scoped>
.traza {
  min-height: 260px;
  max-height: 60vh;
  overflow-y: auto;
}
.placeholder {
  color: var(--texto-tenue);
  font-style: italic;
}
.lista {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}
.paso {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  padding: 0.5rem 0.6rem;
  border-radius: 8px;
  background: var(--bg-panel-alt);
  animation: aparecer 0.25s ease-out;
}
.paso.critico {
  border: 1px solid var(--abstencion);
  background: rgba(246, 173, 85, 0.1);
}
.paso.pendiente {
  opacity: 0.6;
}
.icono {
  font-size: 1.3rem;
}
.titulo-paso {
  font-weight: 600;
  display: flex;
  justify-content: space-between;
  gap: 0.5rem;
}
.tiempo {
  color: var(--texto-tenue);
  font-weight: 400;
  font-size: 0.85rem;
}
.detalle-paso {
  color: var(--texto-tenue);
  font-size: 0.92rem;
  margin-top: 0.15rem;
}
@keyframes aparecer {
  from {
    opacity: 0;
    transform: translateY(-4px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
