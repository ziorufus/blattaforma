<template>
  <div>
    <div class="d-md-flex justify-content-between align-items-center mb-4">
      <h1 class="mb-3 mb-md-0">Log azioni</h1>
      <router-link to="/modules/macos-daemons" class="btn btn-outline-secondary d-block d-md-inline">
        <i class="bi bi-arrow-left me-1"></i>Torna alla dashboard
      </router-link>
    </div>

    <div v-if="loading" class="text-muted">Caricamento...</div>
    <div v-else class="table-responsive">
      <table class="table table-striped align-middle">
        <thead>
          <tr>
            <th>Data</th>
            <th>Macchina</th>
            <th>Demone</th>
            <th>Azione</th>
            <th>Utente</th>
            <th>Esito</th>
            <th>Messaggio</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(entry, i) in entries" :key="i">
            <td class="nobr">{{ formatDateTime(entry.created_at) }}</td>
            <td>{{ entry.machine_name }}</td>
            <td><code>{{ entry.label }}</code></td>
            <td>{{ entry.action }}</td>
            <td>{{ entry.user_email || '—' }}</td>
            <td>
              <span class="badge" :class="entry.success ? 'text-bg-success' : 'text-bg-danger'">
                {{ entry.success ? 'OK' : 'Errore' }}
              </span>
            </td>
            <td class="text-truncate" style="max-width: 300px" :title="entry.message || ''">
              {{ entry.message || '—' }}
            </td>
          </tr>
          <tr v-if="entries.length === 0">
            <td colspan="7" class="text-muted">Nessuna azione registrata.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../../api/axios'
import { useToastStore } from '../../stores/toast'

const toast = useToastStore()
const entries = ref([])
const loading = ref(true)

function formatDateTime(iso) {
  return new Date(iso).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })
}

onMounted(async () => {
  try {
    const { data } = await api.get('/api/modules/macos-daemons/logs')
    entries.value = data
  } catch (e) {
    toast.apiError(e, 'Impossibile caricare il log.')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.nobr {
  white-space: nowrap;
}
</style>
