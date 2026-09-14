<template>
  <div>
    <div class="d-flex align-items-center mb-4">
      <img src="/blattaforma-logo.png" alt="Blattaforma" height="32" class="me-2" />
      <h1 class="mb-0">Stato delle API</h1>
    </div>

    <div v-if="loading" class="text-muted">Caricamento...</div>
    <div v-else-if="error" class="alert alert-danger">{{ error }}</div>
    <div v-else-if="targets.length === 0" class="text-muted">Nessuna API pubblicata.</div>
    <ul v-else class="list-group">
      <li
        v-for="t in targets"
        :key="t.name"
        class="list-group-item d-flex justify-content-between align-items-center"
      >
        <div>
          <div class="fw-semibold">{{ t.name }}</div>
          <div class="text-muted small">{{ formatDateTime(t.last_checked_at) }}</div>
        </div>
        <div class="text-end">
          <span class="badge" :class="statusBadgeClass(t.last_status)">
            {{ statusLabel(t.last_status) }}
          </span>
          <div v-if="t.last_response_time_ms != null" class="text-muted small mt-1">
            {{ t.last_response_time_ms }} ms
          </div>
        </div>
      </li>
    </ul>
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
})
</script>
