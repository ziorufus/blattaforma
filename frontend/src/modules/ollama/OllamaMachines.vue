<template>
  <div>
    <div class="d-md-flex justify-content-between align-items-center mb-4">
      <h1 class="mb-3 mb-md-0">Macchine Ollama</h1>
      <div class="d-md-flex gap-2">
        <router-link to="/modules/ollama" class="btn btn-outline-secondary mb-3 mb-md-0 d-block d-md-inline">
          <i class="bi bi-arrow-left me-1"></i>Torna alla dashboard
        </router-link>
        <a v-if="canManage" class="btn btn-primary d-block d-md-inline" @click="openCreate">
          <i class="bi bi-plus-lg me-1"></i>Nuova macchina
        </a>
      </div>
    </div>

    <div v-if="!canManage" class="alert alert-info">
      Puoi vedere l'elenco delle macchine, ma non hai il permesso per modificarlo.
    </div>

    <div v-if="loading" class="text-muted">Caricamento...</div>
    <div v-else class="table-responsive">
      <table class="table table-striped align-middle">
        <thead>
          <tr>
            <th>Nome</th>
            <th>ID macchina</th>
            <th>Indirizzo IP</th>
            <th>Sistema operativo</th>
            <th>Chiave di scrittura</th>
            <th v-if="canManage" class="text-end">Azioni</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in machines" :key="m.id">
            <td>{{ m.name }}</td>
            <td><code>{{ m.slug }}</code></td>
            <td>{{ m.ip_address }}</td>
            <td>{{ m.os === 'macos' ? 'macOS' : 'Linux' }}</td>
            <td>
              <span class="badge" :class="m.has_write_key ? 'text-bg-success' : 'text-bg-secondary'">
                {{ m.has_write_key ? 'Configurata' : 'Non configurata' }}
              </span>
            </td>
            <td v-if="canManage" class="text-end nobr">
              <button class="btn btn-sm btn-outline-secondary me-2" @click="openEdit(m)">
                <i class="bi bi-pencil-fill"></i>
              </button>
              <button class="btn btn-sm btn-outline-danger" @click="removeMachine(m)">
                <i class="bi bi-trash-fill"></i>
              </button>
            </td>
          </tr>
          <tr v-if="machines.length === 0">
            <td :colspan="canManage ? 6 : 5" class="text-muted">Nessuna macchina configurata.</td>
          </tr>
        </tbody>
      </table>
    </div>

    <!-- Create / Edit modal -->
    <div class="modal fade" tabindex="-1" ref="modalEl">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ form.id ? 'Modifica macchina' : 'Nuova macchina' }}</h5>
            <button type="button" class="btn-close" @click="modalInstance.hide()"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">Nome</label>
              <input v-model="form.name" type="text" class="form-control" required @input="onNameInput" />
            </div>
            <div class="mb-3">
              <label class="form-label">ID macchina</label>
              <input
                v-model="form.slug"
                type="text"
                class="form-control"
                pattern="[a-z0-9-]+"
                title="Solo lettere minuscole, numeri e trattini"
                required
                @input="slugTouched = true"
              />
            </div>
            <div class="mb-3">
              <label class="form-label">Indirizzo IP</label>
              <input v-model="form.ip_address" type="text" class="form-control" required />
            </div>
            <div class="mb-3">
              <label class="form-label">Sistema operativo</label>
              <select v-model="form.os" class="form-select" required>
                <option value="linux">Linux</option>
                <option value="macos">macOS</option>
              </select>
            </div>
            <div class="mb-3">
              <label class="form-label">Chiave API in lettura</label>
              <input
                v-model="form.api_key_read"
                type="text"
                class="form-control"
                :placeholder="form.id ? 'Lascia vuoto per non modificarla' : ''"
                :required="!form.id"
              />
            </div>
            <div class="mb-3">
              <label class="form-label">Chiave API in scrittura (facoltativa)</label>
              <input
                v-model="form.api_key_write"
                type="text"
                class="form-control"
                :disabled="form.clear_api_key_write"
                :placeholder="form.id ? 'Lascia vuoto per non modificarla' : ''"
              />
              <div class="form-check mt-2" v-if="form.id">
                <input
                  id="clear-write-key"
                  v-model="form.clear_api_key_write"
                  class="form-check-input"
                  type="checkbox"
                />
                <label class="form-check-label" for="clear-write-key">Rimuovi la chiave di scrittura</label>
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
import { ref, reactive, computed, onMounted } from 'vue'
import { Modal } from 'bootstrap'
import api from '../../api/axios'
import { useAuthStore } from '../../stores/auth'
import { useToastStore } from '../../stores/toast'

const auth = useAuthStore()
const toast = useToastStore()
const canManage = computed(() => {
  if (auth.isAdmin) return true
  const mod = auth.modules.find((m) => m.name === 'ollama')
  return !!mod && mod.granted_roles.includes('machines')
})

const machines = ref([])
const loading = ref(true)
const saving = ref(false)

const modalEl = ref(null)
let modalInstance = null

const form = reactive({
  id: null,
  name: '',
  slug: '',
  ip_address: '',
  os: 'linux',
  api_key_read: '',
  api_key_write: '',
  clear_api_key_write: false,
})

let slugTouched = false

function slugify(value) {
  return value.toLowerCase().replace(/\s+/g, '-')
}

function onNameInput() {
  if (!form.id && !slugTouched) {
    form.slug = slugify(form.name)
  }
}

async function loadMachines() {
  loading.value = true
  try {
    const { data } = await api.get('/api/modules/ollama/machines')
    machines.value = data
  } catch (e) {
    toast.apiError(e, 'Impossibile caricare le macchine.')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.id = null
  form.name = ''
  form.slug = ''
  form.ip_address = ''
  form.os = 'linux'
  form.api_key_read = ''
  form.api_key_write = ''
  form.clear_api_key_write = false
  slugTouched = false
}

function openCreate() {
  resetForm()
  modalInstance.show()
}

function openEdit(machine) {
  form.id = machine.id
  form.name = machine.name
  form.slug = machine.slug
  form.ip_address = machine.ip_address
  form.os = machine.os
  form.api_key_read = ''
  form.api_key_write = ''
  form.clear_api_key_write = false
  slugTouched = true
  modalInstance.show()
}

async function save() {
  saving.value = true
  const isNew = !form.id
  try {
    if (!form.id) {
      await api.post('/api/modules/ollama/machines', {
        name: form.name,
        slug: form.slug,
        ip_address: form.ip_address,
        os: form.os,
        api_key_read: form.api_key_read,
        api_key_write: form.api_key_write || null,
      })
    } else {
      const payload = {
        name: form.name,
        slug: form.slug,
        ip_address: form.ip_address,
        os: form.os,
      }
      if (form.api_key_read) payload.api_key_read = form.api_key_read
      if (form.clear_api_key_write) {
        payload.api_key_write = null
      } else if (form.api_key_write) {
        payload.api_key_write = form.api_key_write
      }
      await api.patch(`/api/modules/ollama/machines/${form.id}`, payload)
    }

    modalInstance.hide()
    await loadMachines()
    toast.success(isNew ? `Macchina "${form.name}" creata.` : `Macchina "${form.name}" aggiornata.`)
  } catch (e) {
    toast.apiError(e, 'Salvataggio non riuscito.')
  } finally {
    saving.value = false
  }
}

async function removeMachine(machine) {
  if (!confirm(`Eliminare la macchina ${machine.name}?`)) return
  try {
    await api.delete(`/api/modules/ollama/machines/${machine.id}`)
    await loadMachines()
    toast.success(`Macchina "${machine.name}" eliminata.`)
  } catch (e) {
    toast.apiError(e, 'Impossibile eliminare la macchina.')
  }
}

onMounted(async () => {
  modalInstance = new Modal(modalEl.value)
  await loadMachines()
})
</script>

<style scoped>
.nobr {
  white-space: nowrap;
}
</style>
