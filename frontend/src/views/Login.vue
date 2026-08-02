<template>
  <div class="d-flex justify-content-center align-items-center" style="min-height: 80vh">
    <div class="card shadow-sm" style="width: 24rem">
      <div class="logo-wrapper">
          <img src="/blattaforma-logo.png" alt="Logo" />
      </div>
      <div class="card-body text-center p-4">
        <h1 class="h3 mb-3">Blattaforma</h1>
        <p class="text-muted mb-4">Accedi con il tuo account Google per continuare.</p>
        <div v-if="errorMessage" class="alert alert-danger py-2">{{ errorMessage }}</div>
        <button class="btn btn-primary w-100" @click="login">
          <i class="bi bi-google me-2"></i>Accedi con Google
        </button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'

const route = useRoute()
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const errorMessage = computed(() => {
  if (route.query.error === 'unauthorized') {
    return "Il tuo account Google non è registrato su questa piattaforma. Contatta un amministratore."
  }
  if (route.query.error === 'oauth_failed') {
    return 'Accesso con Google non riuscito. Riprova.'
  }
  return ''
})

function login() {
  window.location.href = `${API_BASE}/api/auth/google/login`
}
</script>

<style scoped>
.logo-wrapper {
    width: 130px;
    height: 130px;
    margin: 1.5rem auto;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    background-color: #f8f9fa;
    border: 1px solid #e9ecef;
    box-shadow: 0 0.75rem 2rem rgba(0, 0, 0, 0.12);
}

.logo-wrapper img {
    max-width: 90px;
    max-height: 90px;
    width: auto;
    height: auto;
    object-fit: contain;
}

.card {
    border-radius: 0.75rem;
    padding: 1.5rem;
}
</style>