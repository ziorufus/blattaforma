<template>
  <div>
    <div class="d-flex align-items-center mb-4">
      <router-link to="/login" title="Torna alla home">
        <img src="/blattaforma-logo.png" alt="Blattaforma" height="32" class="me-2" />
      </router-link>
      <h1 class="mb-0">Stato delle API</h1>
    </div>

    <div v-if="loading" class="text-muted">Caricamento...</div>
    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-else-if="targets.length === 0" class="text-muted">Nessuna API pubblicata.</div>
    <div v-else class="row g-2">
      <div v-for="t in targets" :key="t.name" class="col-12 col-lg-6">
        <div class="card h-100">
          <div class="card-body py-2 px-3 d-flex justify-content-between align-items-start">
            <div class="me-3 text-break">
              <div class="fw-semibold">{{ t.name }}</div>
              <div class="small d-flex align-items-start">
                <code>{{ t.url }}</code>
                <button
                  type="button"
                  class="btn btn-link btn-sm p-0 ms-1 lh-1 text-muted"
                  :title="copiedName === t.name ? 'Copiato!' : 'Copia URL'"
                  :aria-label="`Copia URL di ${t.name}`"
                  @click="copyUrl(t)"
                >
                  <i class="bi" :class="copiedName === t.name ? 'bi-check-lg text-success' : 'bi-clipboard'"></i>
                </button>
              </div>
              <div class="text-muted meta">
                Ultimo controllo: {{ formatDateTime(t.last_checked_at) }}
                -
                {{ t.last_response_time_ms != null ? `${t.last_response_time_ms} ms` : '-' }}
              </div>
            </div>
            <div class="text-end text-nowrap">
              <span class="badge" :class="statusBadgeClass(t.last_status)">
                {{ statusLabel(t.last_status) }}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../../api/axios'
import { statusBadgeClass, statusLabel, formatDateTime } from './statusBadge'

const POLL_INTERVAL_MS = 20000

const targets = ref([])
const loading = ref(true)
const error = ref('')
let pollTimer = null
const copiedName = ref(null)
let copiedTimer = null

async function copyUrl(target) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(target.url)
    } else {
      // Fallback per contesti non sicuri (HTTP), dove navigator.clipboard non è disponibile
      const ta = document.createElement('textarea')
      ta.value = target.url
      ta.style.position = 'fixed'
      ta.style.opacity = '0'
      document.body.appendChild(ta)
      ta.select()
      document.execCommand('copy')
      document.body.removeChild(ta)
    }
  } catch (e) {
    return
  }
  copiedName.value = target.name
  clearTimeout(copiedTimer)
  copiedTimer = setTimeout(() => { copiedName.value = null }, 1500)
}

async function loadTargets({ silent = false } = {}) {
  if (!silent) loading.value = true
  try {
    const { data } = await api.get('/api/modules/api-status/public')
    targets.value = data
    error.value = ''
  } catch (e) {
    if (!silent) error.value = 'Impossibile caricare lo stato delle API al momento.'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadTargets()
  pollTimer = setInterval(() => loadTargets({ silent: true }), POLL_INTERVAL_MS)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  clearTimeout(copiedTimer)
})
</script>

<style scoped>
.meta {
  font-size: 0.75rem;
}
</style>
