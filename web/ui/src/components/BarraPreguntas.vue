<script setup>
import { ref } from 'vue'

const props = defineProps({
  preguntas: { type: Array, default: () => [] },
  corriendo: { type: Boolean, default: false },
})
const emit = defineEmits(['preguntar'])

const texto = ref('')

function enviar() {
  const pregunta = texto.value.trim()
  if (!pregunta) return
  emit('preguntar', pregunta)
}

function enviarChip(pregunta) {
  texto.value = pregunta
  emit('preguntar', pregunta)
}
</script>

<template>
  <div class="panel barra">
    <form class="fila-input" @submit.prevent="enviar">
      <input
        v-model="texto"
        type="text"
        placeholder="Escribí una pregunta para el second brain…"
        :disabled="props.corriendo"
      />
      <button class="primario" type="submit" :disabled="props.corriendo || !texto.trim()">
        {{ props.corriendo ? 'Pensando…' : 'Preguntar' }}
      </button>
    </form>
    <div class="chips">
      <button
        v-for="p in props.preguntas"
        :key="p.pregunta"
        class="chip"
        type="button"
        :disabled="props.corriendo"
        :title="p.nombre"
        @click="enviarChip(p.pregunta)"
      >
        {{ p.pregunta }}
      </button>
    </div>
  </div>
</template>

<style scoped>
.barra {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
.fila-input {
  display: flex;
  gap: 0.75rem;
}
.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}
</style>
