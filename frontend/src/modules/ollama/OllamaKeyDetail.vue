<template>
  <div>
    <div class="d-md-flex justify-content-between align-items-center mb-4">
      <h1 class="mb-3 mb-md-0">Chiave: {{ key ? key.name : '' }}</h1>
      <router-link to="/modules/ollama/chiavi" class="btn btn-outline-secondary d-block d-md-inline">
        <i class="bi bi-arrow-left me-1"></i>Torna alle chiavi
      </router-link>
    </div>

    <div v-if="loading" class="text-muted">Caricamento...</div>

    <template v-else-if="key">
      <div class="mb-4">
        <span class="badge me-2" :class="key.active ? 'text-bg-success' : 'text-bg-secondary'">
          {{ key.active ? 'Attivo' : 'Disattivo' }}
        </span>
        <span v-if="key.all_machines" class="badge text-bg-info">Tutte le macchine</span>
        <span v-else-if="key.machine_names.length" class="text-muted">{{ key.machine_names.join(', ') }}</span>
      </div>

      <div class="row g-3 mb-4">
        <div class="col-12 col-lg-6">
          <UsageBarChart
            title="Utilizzi nelle ultime 24 ore"
            :buckets="usage.hourly"
            :format-label="formatHourLabel"
            :label-every="3"
          />
        </div>
        <div class="col-12 col-lg-6">
          <UsageBarChart
            title="Utilizzi nell'ultimo mese"
            :buckets="usage.daily"
            :format-label="formatDayLabel"
            :label-every="5"
          />
        </div>
      </div>

      <h5 class="mb-3">Ultimi 10 utilizzi</h5>
      <div class="table-responsive">
        <table class="table table-striped align-middle">
          <thead>
            <tr>
              <th>Data</th>
              <th>Macchina</th>
              <th>Esito</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(entry, i) in usage.recent" :key="i">
              <td>{{ formatDateTime(entry.created_at) }}</td>
              <td><code>{{ entry.code }}</code></td>
              <td>
                <span class="badge" :class="entry.response_code === 204 ? 'text-bg-success' : 'text-bg-danger'">
                  {{ entry.response_code === 204 ? 'Consentito' : 'Negato' }}
                </span>
              </td>
            </tr>
            <tr v-if="usage.recent.length === 0">
              <td colspan="3" class="text-muted">Nessun utilizzo registrato.</td>
            </tr>
          </tbody>
        </table>
      </div>
    </template>
  </div>
</template>

<script setup>
import { reactive, ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import api from '../../api/axios'
import { useAuthStore } from '../../stores/auth'
import { useToastStore } from '../../stores/toast'
import UsageBarChart from '../../components/UsageBarChart.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()
const toast = useToastStore()

const key = ref(null)
const usage = reactive({ recent: [], hourly: [], daily: [] })
const loading = ref(true)

function canManage() {
  if (auth.isAdmin) return true
  const mod = auth.modules.find((m) => m.name === 'ollama')
  return !!mod && mod.granted_roles.includes('machines')
}

function formatDateTime(iso) {
  return new Date(iso).toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })
}

function formatHourLabel(iso, full = false) {
  const d = new Date(iso)
  if (full) return d.toLocaleString('it-IT', { dateStyle: 'short', timeStyle: 'short' })
  return d.toLocaleTimeString('it-IT', { hour: '2-digit', minute: '2-digit' })
}

function formatDayLabel(iso, full = false) {
  const d = new Date(iso)
  if (full) return d.toLocaleDateString('it-IT', { day: '2-digit', month: 'long', year: 'numeric' })
  return d.toLocaleDateString('it-IT', { day: '2-digit', month: '2-digit' })
}

async function load() {
  loading.value = true
  try {
    const keyId = route.params.id
    const [keyRes, usageRes] = await Promise.all([
      api.get(`/api/modules/ollama/keys/${keyId}`),
      api.get(`/api/modules/ollama/keys/${keyId}/usage`),
    ])
    key.value = keyRes.data
    usage.recent = usageRes.data.recent
    usage.hourly = usageRes.data.hourly
    usage.daily = usageRes.data.daily
  } catch (e) {
    toast.apiError(e, 'Impossibile caricare i dati della chiave.')
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  if (!canManage()) {
    router.replace({ name: 'forbidden' })
    return
  }
  await load()
})
</script>
