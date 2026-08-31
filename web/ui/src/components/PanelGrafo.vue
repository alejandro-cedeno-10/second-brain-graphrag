<script setup>
import cytoscape from 'cytoscape'
import { onMounted, ref, watch } from 'vue'

const props = defineProps({
  caminos: { type: Array, default: () => [] },
})

const contenedor = ref(null)
const aristaSeleccionada = ref(null)
let cy = null

/**
 * Convierte los `Path` del blast radius (no dirigidos en el traversal, pero
 * con `direcciones[i]` marcando si la relación va `nodos[i] -> nodos[i+1]`
 * tal como la declara el corpus) a elementos de Cytoscape. `direcciones[i]
 * === false` invierte el par al armar la arista para que la flecha en
 * pantalla apunte igual que `_formatear_camino` en el CLI — no hay que
 * volver a razonar el sentido acá, solo respetarlo.
 */
function elementosDesdeCaminos(caminos) {
  const nodos = new Map()
  const aristas = new Map()
  const raiz = caminos[0]?.nodos?.[0]

  for (const camino of caminos) {
    camino.nodos.forEach((n) => nodos.set(n, { data: { id: n, raiz: n === raiz } }))
    camino.relaciones.forEach((relacion, i) => {
      const directa = camino.direcciones[i] ?? true
      const origen = directa ? camino.nodos[i] : camino.nodos[i + 1]
      const destino = directa ? camino.nodos[i + 1] : camino.nodos[i]
      const provenance = camino.provenance[i] ?? ''
      const id = `${origen}->${destino}:${relacion}`
      aristas.set(id, {
        data: { id, source: origen, target: destino, label: relacion, provenance },
      })
    })
  }
  return [...nodos.values(), ...aristas.values()]
}

function render() {
  if (!contenedor.value) return
  const elementos = elementosDesdeCaminos(props.caminos)
  cy?.destroy()
  cy = cytoscape({
    container: contenedor.value,
    elements: elementos,
    style: [
      {
        selector: 'node',
        style: {
          label: 'data(id)',
          'background-color': '#1c2734',
          'border-width': 2,
          'border-color': '#4fd1c5',
          color: '#eef2f7',
          'font-size': 14,
          'text-valign': 'center',
          'text-halign': 'center',
          width: 'label',
          height: 34,
          padding: '10px',
          shape: 'round-rectangle',
        },
      },
      {
        selector: 'node[?raiz]',
        style: {
          'background-color': '#0f766e',
          'border-color': '#22d3ee',
          'border-width': 3,
        },
      },
      {
        selector: 'edge',
        style: {
          label: 'data(label)',
          'curve-style': 'bezier',
          'target-arrow-shape': 'triangle',
          'target-arrow-color': '#9fb0c3',
          'line-color': '#3a4a5e',
          color: '#9fb0c3',
          'font-size': 11,
          width: 2,
        },
      },
      {
        selector: 'edge:selected',
        style: {
          'line-color': '#22d3ee',
          'target-arrow-color': '#22d3ee',
          color: '#22d3ee',
          width: 3,
        },
      },
    ],
  })

  cy.on('tap', 'edge', (evento) => {
    const d = evento.target.data()
    aristaSeleccionada.value = d
  })

  const layout = cy.layout({
    name: 'breadthfirst',
    directed: true,
    spacingFactor: 1.3,
    roots: [raizId()],
  })
  layout.on('layoutstop', () => {
    requestAnimationFrame(() => {
      cy.resize()
      cy.fit(undefined, 40)
    })
  })
  layout.run()
}

function raizId() {
  return props.caminos[0]?.nodos?.[0] ?? undefined
}

onMounted(render)
watch(() => props.caminos, render, { deep: true, flush: 'post' })
</script>

<template>
  <div class="panel grafo">
    <div class="etiqueta">Subgrafo recorrido</div>
    <p v-if="props.caminos.length === 0" class="placeholder">
      Esta pregunta no navegó el grafo (respuesta simple o abstención).
    </p>
    <div v-show="props.caminos.length > 0" ref="contenedor" class="lienzo"></div>
    <div v-if="aristaSeleccionada" class="detalle-arista">
      <strong>{{ aristaSeleccionada.source }} —{{ aristaSeleccionada.label }}→ {{ aristaSeleccionada.target }}</strong>
      <span class="etiqueta">provenance: {{ aristaSeleccionada.provenance }}</span>
    </div>
  </div>
</template>

<style scoped>
.grafo {
  display: flex;
  flex-direction: column;
}
.placeholder {
  color: var(--texto-tenue);
  font-style: italic;
}
.lienzo {
  flex: 1;
  min-height: 320px;
  border-radius: 10px;
  background: #0e141b;
}
.detalle-arista {
  margin-top: 0.75rem;
  padding-top: 0.75rem;
  border-top: 1px dashed var(--borde);
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}
</style>
