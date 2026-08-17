<template>
  <div>
    <div class="d-md-flex justify-content-between align-items-center mb-4">
      <h1 class="mb-3 mb-md-0">Chiavi API Ollama</h1>
      <div class="d-md-flex gap-2">
        <router-link to="/modules/ollama" class="btn btn-outline-secondary mb-3 mb-md-0 d-block d-md-inline">
          <i class="bi bi-arrow-left me-1"></i>Torna alla dashboard
        </router-link>
        <a class="btn btn-primary d-block d-md-inline" @click="openCreate">
          <i class="bi bi-plus-lg me-1"></i>Nuova chiave
        </a>
      </div>
    </div>

    <div v-if="errorMessage" class="alert alert-danger">{{ errorMessage }}</div>

    <div v-if="loading" class="text-muted">Caricamento...</div>
    <div v-else class="table-responsive">
      <table class="table table-striped align-middle">
        <thead>
          <tr>
            <th>Nome</th>
            <th>Macchine</th>
            <th>Utente</th>
            <th>Attivo</th>
            <th>Valore</th>
            <th class="text-end">Azioni</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="k in keys" :key="k.id">
            <td>
              <router-link :to="{ name: 'module-ollama-chiave-dettaglio', params: { id: k.id } }">
                {{ k.name }}
              </router-link>
            </td>
            <td>
              <span v-if="k.all_machines" class="badge text-bg-info">Tutte le macchine</span>
              <span v-else-if="k.machine_names.length">{{ k.machine_names.join(', ') }}</span>
              <span v-else class="text-muted">Nessuna</span>
            </td>
            <td>
              <span v-if="k.user_email">{{ k.user_email }}</span>
              <span v-else class="text-muted">Nessuno</span>
            </td>
            <td>
              <span class="badge" :class="k.active ? 'text-bg-success' : 'text-bg-secondary'">
                {{ k.active ? 'Attivo' : 'Disattivo' }}
              </span>
            </td>
            <td><code>{{ k.masked_value }}</code></td>
            <td class="text-end nobr">
              <button class="btn btn-sm btn-outline-secondary me-2" @click="openEdit(k)">
                <i class="bi bi-pencil-fill"></i>
              </button>
              <button class="btn btn-sm btn-outline-danger" @click="removeKey(k)">
                <i class="bi bi-trash-fill"></i>
              </button>
            </td>
          </tr>
          <tr v-if="keys.length === 0">
            <td colspan="6" class="text-muted">Nessuna chiave configurata.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create / Edit modal -->
    <div class="modal fade" tabindex="-1" ref="modalEl">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ form.id ? 'Modifica chiave' : 'Nuova chiave' }}</h5>
            <button type="button" class="btn-close" @click="modalInstance.hide()"></button>
          </div>
          <div class="modal-body">
            <div v-if="modalError" class="alert alert-danger">{{ modalError }}</div>

            <div class="mb-3">
              <label class="form-label">Nome</label>
              <input v-model="form.name" type="text" class="form-control" required />
            </div>
            <div class="mb-3">
              <label class="form-label">Valore chiave</label>
              <div class="input-group">
                <input v-model="form.value" type="text" class="form-control" required />
                <button
                  type="button"
                  class="btn btn-outline-secondary"
                  title="Genera valore casuale"
                  @click="generateValue"
                >
                  <i class="bi bi-dice-5"></i>
                </button>
              </div>
            </div>
            <div class="form-check mb-3">
              <input
                id="all-machines"
                v-model="form.all_machines"
                class="form-check-input"
                type="checkbox"
                @change="form.all_machines && (form.machine_ids = [])"
              />
              <label class="form-check-label" for="all-machines">Tutte le macchine</label>
            </div>
            <div class="form-check mb-3">
              <input id="active" v-model="form.active" class="form-check-input" type="checkbox" />
              <label class="form-check-label" for="active">Attivo</label>
            </div>
            <div class="mb-3">
              <label class="form-label">Utente associato</label>
              <select v-model="form.user_id" class="form-select">
                <option :value="null">Nessuno</option>
                <option v-for="u in assignableUsers" :key="u.id" :value="u.id">
                  {{ u.name }} ({{ u.email }})
                </option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">Macchine associate</label>
              <div v-if="availableMachines.length === 0" class="text-muted">
                Nessuna macchina configurata.
              </div>
              <div v-for="m in availableMachines" :key="m.id" class="form-check">
                <input
                  :id="`machine-${m.id}`"
                  v-model="form.machine_ids"
                  class="form-check-input"
                  type="checkbox"
                  :value="m.id"
                  :disabled="form.all_machines"
                />
                <label class="form-check-label" :for="`machine-${m.id}`">{{ m.name }}</label>
              </div>
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="modalInstance.hide()">
              Annulla
            </button>
            <button type="button" class="btn btn-primary" @click="save" :disabled="saving">
              Salva
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Modal } from 'bootstrap'
import api from '../../api/axios'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const router = useRouter()

const keys = ref([])
const availableMachines = ref([])
const assignableUsers = ref([])
const loading = ref(true)
const saving = ref(false)
const errorMessage = ref('')
const modalError = ref('')

const modalEl = ref(null)
let modalInstance = null

const form = reactive({
  id: null,
  name: '',
  value: '',
  all_machines: false,
  active: true,
  machine_ids: [],
  user_id: null,
})

function canManage() {
  if (auth.isAdmin) return true
  const mod = auth.modules.find((m) => m.name === 'ollama')
  return !!mod && mod.granted_roles.includes('machines')
}

async function loadKeys() {
  loading.value = true
  errorMessage.value = ''
  try {
    const { data } = await api.get('/api/modules/ollama/keys')
    keys.value = data
  } catch (e) {
    errorMessage.value = 'Impossibile caricare le chiavi.'
  } finally {
    loading.value = false
  }
}

async function loadMachines() {
  try {
    const { data } = await api.get('/api/modules/ollama/machines')
    availableMachines.value = data
  } catch (e) {
    // la lista macchine è secondaria: se fallisce, il form resta senza opzioni selezionabili
  }
}

async function loadAssignableUsers() {
  try {
    const { data } = await api.get('/api/modules/ollama/keys/assignable-users')
    assignableUsers.value = data
  } catch (e) {
    // lista utenti secondaria: se fallisce, il form resta senza opzioni selezionabili
  }
}

function resetForm() {
  form.id = null
  form.name = ''
  form.value = ''
  form.all_machines = false
  form.active = true
  form.machine_ids = []
  form.user_id = null
}

function generateValue() {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  form.value = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

function openCreate() {
  resetForm()
  modalError.value = ''
  modalInstance.show()
}

async function openEdit(key) {
  modalError.value = ''
  try {
    const { data } = await api.get(`/api/modules/ollama/keys/${key.id}`)
    form.id = data.id
    form.name = data.name
    form.value = data.value
    form.all_machines = data.all_machines
    form.active = data.active
    form.machine_ids = [...data.machine_ids]
    form.user_id = data.user_id
    modalInstance.show()
  } catch (e) {
    errorMessage.value = 'Impossibile caricare la chiave.'
  }
}

async function save() {
  modalError.value = ''
  if (!form.all_machines && form.machine_ids.length === 0) {
    modalError.value = 'Specificare almeno una tra: tutte le macchine o una macchina associata.'
    return
  }

  saving.value = true
  try {
    const payload = {
      name: form.name,
      value: form.value,
      all_machines: form.all_machines,
      active: form.active,
      machine_ids: form.all_machines ? [] : form.machine_ids,
      user_id: form.user_id,
    }
    if (!form.id) {
      await api.post('/api/modules/ollama/keys', payload)
    } else {
      await api.patch(`/api/modules/ollama/keys/${form.id}`, payload)
    }

    modalInstance.hide()
    await loadKeys()
  } catch (e) {
    modalError.value = e.response?.data?.detail || 'Salvataggio non riuscito.'
  } finally {
    saving.value = false
  }
}

async function removeKey(key) {
  if (!confirm(`Eliminare la chiave ${key.name}?`)) return
  try {
    await api.delete(`/api/modules/ollama/keys/${key.id}`)
    await loadKeys()
  } catch (e) {
    errorMessage.value = e.response?.data?.detail || 'Impossibile eliminare la chiave.'
  }
}

onMounted(async () => {
  if (!canManage()) {
    router.replace({ name: 'forbidden' })
    return
  }
  modalInstance = new Modal(modalEl.value)
  await Promise.all([loadKeys(), loadMachines(), loadAssignableUsers()])
})
</script>

<style scoped>
.nobr {
  white-space: nowrap;
}
</style>
