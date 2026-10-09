<template>
  <div class="d-flex justify-content-center align-items-center" style="min-height: 80vh">
    <div class="card shadow-sm" style="width: 24rem">
      <div class="logo-wrapper">
          <img src="/blattaforma-logo.png" alt="Logo" />
      </div>
      <div class="card-body text-center p-4">
        <h1 class="h3 mb-3">Blattaforma</h1>
        <p class="text-muted mb-4">Accedi per continuare.</p>
        <button class="btn btn-outline-primary w-100 mb-2" @click="loginGoogle">
          <i class="bi bi-google me-2"></i>Accedi con Google
        </button>
        <button class="btn btn-outline-primary w-100" @click="loginMicrosoft">
          <i class="bi bi-microsoft me-2"></i>Accedi con Microsoft
        </button>
      </div>
      <div class="card-body border-top pt-3" v-if="publicPages.length > 0">
        <p class="text-muted small mb-2">Pagine pubbliche disponibili senza account:</p>
        <ul class="list-unstyled mb-0">
          <li v-for="p in publicPages" :key="p.path">
            <router-link :to="p.path">{{ p.label }}</router-link>
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { publicPages } from '../router'
import { useAuthStore } from '../stores/auth'
import { useToastStore } from '../stores/toast'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useToastStore()

const ERROR_MESSAGES = {
  unauthorized: 'Il tuo account non è registrato su questa piattaforma. Contatta un amministratore.',
  oauth_failed: 'Accesso non riuscito. Riprova.',
}

onMounted(() => {
  const error = route.query.error
  if (!error) return

  // Un nuovo tentativo di login è stato appena rifiutato dal backend: non
  // deve restare silenziosamente attiva un'eventuale sessione precedente
  // ancora valida nel browser, altrimenti l'utente non si accorge del rifiuto.
  auth.logout()
  toast.error(ERROR_MESSAGES[error] || 'Accesso non riuscito. Riprova.')
  router.replace({ name: 'login' })
})

function loginGoogle() {
  window.location.href = `${API_BASE}/api/auth/google/login`
}

function loginMicrosoft() {
  window.location.href = `${API_BASE}/api/auth/microsoft/login`
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