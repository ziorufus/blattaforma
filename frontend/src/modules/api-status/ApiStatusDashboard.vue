<template>
  <div>
    <div class="d-md-flex justify-content-between align-items-center mb-4">
      <h1 class="mb-3 mb-md-0">API Status</h1>
      <a v-if="canManage" class="btn btn-primary d-block d-md-inline" @click="openCreate">
        <i class="bi bi-plus-lg me-1"></i>Nuova API
      </a>
    </div>

    <div v-if="!canManage" class="alert alert-info">
      Puoi vedere lo stato delle API, ma non hai il permesso per modificarle.
    </div>

    <div v-if="loading" class="text-muted">Caricamento...</div>
    <div v-else class="table-responsive">
      <table class="table table-striped align-middle">
        <thead>
          <tr>
            <th>Stato</th>
            <th>Nome</th>
            <th>URL</th>
            <th>Ultimo controllo</th>
            <th>Tempo di risposta</th>
            <th v-if="canManage" class="text-end">Azioni</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="t in targets" :key="t.id">
            <td>
              <span class="badge" :class="statusBadgeClass(t.enabled ? t.last_status : 'unknown')">
                {{ t.enabled ? statusLabel(t.last_status) : 'Disabilitata' }}
              </span>
            </td>
            <td>{{ t.name }}</td>
            <td class="text-break"><code>{{ t.url }}</code></td>
            <td>{{ formatDateTime(t.last_checked_at) }}</td>
            <td>{{ t.last_response_time_ms != null ? `${t.last_response_time_ms} ms` : '-' }}</td>
            <td v-if="canManage" class="text-end nobr">
              <button
                class="btn btn-sm btn-outline-secondary me-2"
                title="Controlla ora"
                @click="checkNow(t)"
                :disabled="checkingId === t.id"
              >
                <i class="bi bi-arrow-clockwise"></i>
              </button>
              <button class="btn btn-sm btn-outline-secondary me-2" @click="openEdit(t)">
                <i class="bi bi-pencil-fill"></i>
              </button>
              <button class="btn btn-sm btn-outline-danger" @click="removeTarget(t)">
                <i class="bi bi-trash-fill"></i>
              </button>
            </td>
          </tr>
          <tr v-if="targets.length === 0">
            <td :colspan="canManage ? 6 : 5" class="text-muted">Nessuna API configurata.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create / Edit modal -->
    <div class="modal fade" tabindex="-1" ref="modalEl">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ form.id ? 'Modifica API' : 'Nuova API' }}</h5>
            <button type="button" class="btn-close" @click="modalInstance.hide()"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">Nome</label>
              <input v-model="form.name" type="text" class="form-control" required />
            </div>
            <div class="mb-3">
              <label class="form-label">URL</label>
              <input
                v-model="form.url"
                type="text"
                class="form-control"
                placeholder="https://..."
                required
              />
            </div>
            <div class="row">
              <div class="col-4 mb-3">
                <label class="form-label">Status code atteso</label>
                <input
                  v-model.number="form.expected_status_code"
                  type="number"
                  class="form-control"
                  min="100"
                  max="599"
                  required
                />
              </div>
              <div class="col-4 mb-3">
                <label class="form-label">Intervallo (s)</label>
                <input
                  v-model.number="form.check_interval_seconds"
                  type="number"
                  class="form-control"
                  min="10"
                  max="86400"
                  required
                />
              </div>
              <div class="col-4 mb-3">
                <label class="form-label">Timeout (s)</label>
                <input
                  v-model.number="form.timeout_seconds"
                  type="number"
                  class="form-control"
                  min="1"
                  max="60"
                  required
                />
              </div>
            </div>
            <div class="form-check">
              <input id="target-enabled" v-model="form.enabled" class="form-check-input" type="checkbox" />
              <label class="form-check-label" for="target-enabled">Abilitata</label>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="modalInstance.hide()">Annulla</button>
            <button type="button" class="btn btn-primary" @click="save" :disabled="saving">Salva</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
import { Modal } from 'bootstrap'
import api from '../../api/axios'
import { useAuthStore } from '../../stores/auth'
import { useToastStore } from '../../stores/toast'
import { statusBadgeClass, statusLabel, formatDateTime } from './statusBadge'

const POLL_INTERVAL_MS = 20000

const auth = useAuthStore()
const toast = useToastStore()
const canManage = computed(() => {
  if (auth.isAdmin) return true
  const mod = auth.modules.find((m) => m.name === 'api-status')
  return !!mod && mod.granted_roles.includes('manager')
})

const targets = ref([])
const loading = ref(true)
const saving = ref(false)
const checkingId = ref(null)

const modalEl = ref(null)
let modalInstance = null
let pollTimer = null

const form = reactive({
  id: null,
  name: '',
  url: '',
  expected_status_code: 200,
  check_interval_seconds: 60,
  timeout_seconds: 10,
  enabled: true,
})

async function loadTargets({ silent = false } = {}) {
  if (!silent) loading.value = true
  try {
    const { data } = await api.get('/api/modules/api-status')
    targets.value = data
  } catch (e) {
    toast.apiError(e, 'Impossibile caricare le API.')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.id = null
  form.name = ''
  form.url = ''
  form.expected_status_code = 200
  form.check_interval_seconds = 60
  form.timeout_seconds = 10
  form.enabled = true
}

function openCreate() {
  resetForm()
  modalInstance.show()
}

function openEdit(target) {
  form.id = target.id
  form.name = target.name
  form.url = target.url
  form.expected_status_code = target.expected_status_code
  form.check_interval_seconds = target.check_interval_seconds
  form.timeout_seconds = target.timeout_seconds
  form.enabled = target.enabled
  modalInstance.show()
}

async function save() {
  saving.value = true
  const isNew = !form.id
  try {
    const payload = {
      name: form.name,
      url: form.url,
      expected_status_code: form.expected_status_code,
      check_interval_seconds: form.check_interval_seconds,
      timeout_seconds: form.timeout_seconds,
      enabled: form.enabled,
    }
    if (isNew) {
      await api.post('/api/modules/api-status', payload)
    } else {
      await api.patch(`/api/modules/api-status/${form.id}`, payload)
    }

    modalInstance.hide()
    await loadTargets()
    toast.success(isNew ? `API "${form.name}" creata.` : `API "${form.name}" aggiornata.`)
  } catch (e) {
    toast.apiError(e, 'Salvataggio non riuscito.')
  } finally {
    saving.value = false
  }
}

async function removeTarget(target) {
  if (!confirm(`Eliminare l'API "${target.name}"?`)) return
  try {
    await api.delete(`/api/modules/api-status/${target.id}`)
    await loadTargets()
    toast.success(`API "${target.name}" eliminata.`)
  } catch (e) {
    toast.apiError(e, 'Impossibile eliminare l\'API.')
  }
}

async function checkNow(target) {
  checkingId.value = target.id
  try {
    await api.post(`/api/modules/api-status/${target.id}/check`)
    await loadTargets({ silent: true })
  } catch (e) {
    toast.apiError(e, 'Controllo non riuscito.')
  } finally {
    checkingId.value = null
  }
}

onMounted(async () => {
  modalInstance = new Modal(modalEl.value)
  await loadTargets()
  pollTimer = setInterval(() => loadTargets({ silent: true }), POLL_INTERVAL_MS)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.nobr {
  white-space: nowrap;
}
</style>
