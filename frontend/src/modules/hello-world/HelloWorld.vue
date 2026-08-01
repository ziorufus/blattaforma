<template>
  <div>
    <h1 class="mb-3">Hello world</h1>
    <div v-if="loading" class="text-muted">Caricamento...</div>
    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>
    <p v-else class="fs-3">{{ message }}</p>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../../api/axios'

const message = ref('')
const loading = ref(true)
const error = ref('')

onMounted(async () => {
  try {
    const { data } = await api.get('/api/modules/hello-world/greeting')
    message.value = data.message
  } catch (e) {
    error.value = 'Impossibile caricare il messaggio del modulo.'
  } finally {
    loading.value = false
  }
})
</script>
