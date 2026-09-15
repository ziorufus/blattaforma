<template>
  <div>
    <div class="d-md-flex justify-content-between align-items-center mb-4">
      <h1 class="mb-3 mb-md-0">Macchine</h1>
      <div class="d-md-flex gap-2">
        <router-link to="/modules/macos-daemons" class="btn btn-outline-secondary mb-3 mb-md-0 d-block d-md-inline">
          <i class="bi bi-arrow-left me-1"></i>Torna alla dashboard
        </router-link>
        <a class="btn btn-primary d-block d-md-inline" @click="openCreate">
          <i class="bi bi-plus-lg me-1"></i>Nuova macchina
        </a>
      </div>
    </div>

    <div v-if="loading" class="text-muted">Caricamento...</div>
    <div v-else class="table-responsive">
      <table class="table table-striped align-middle">
        <thead>
          <tr>
            <th>Nome</th>
            <th>ID macchina</th>
            <th>Indirizzo IP</th>
            <th>Chiave di controllo</th>
            <th class="text-end">Azioni</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="m in machines" :key="m.id">
            <td>{{ m.name }}</td>
            <td><code>{{ m.slug }}</code></td>
            <td>{{ m.ip_address }}</td>
            <td>
              <span class="badge text-bg-success">Configurata</span>
            </td>
            <td class="text-end nobr">
              <button class="btn btn-sm btn-outline-secondary me-2" @click="openEdit(m)">
                <i class="bi bi-pencil-fill"></i>
              </button>
              <button class="btn btn-sm btn-outline-danger" @click="removeMachine(m)">
                <i class="bi bi-trash-fill"></i>
              </button>
            </td>
          </tr>
          <tr v-if="machines.length === 0">
            <td colspan="5" class="text-muted">Nessuna macchina configurata.</td>
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
              <div class="form-text">
                Deve coincidere con l'header <code>Code</code> impostato nello snippet nginx di questa
                macchina (vedi <code>nginx-conf/macos-daemons</code>).
              </div>
            </div>
            <div class="mb-3">
              <label class="form-label">Indirizzo IP</label>
              <input v-model="form.ip_address" type="text" class="form-control" required />
            </div>
            <div class="mb-3">
              <label class="form-label">Chiave di controllo</label>
              <div class="input-group">
                <input
                  v-model="form.control_key"
                  type="text"
                  class="form-control"
                  :placeholder="form.id ? 'Lascia vuoto per non modificarla' : ''"
                  :required="!form.id"
                />
                <button
                  type="button"
                  class="btn btn-outline-secondary"
                  title="Genera valore casuale"
                  @click="generateControlKey"
                >
                  <i class="bi bi-dice-5"></i>
                </button>
              </div>
              <div class="form-text">
                Deve coincidere con la chiave presentata dal backend a questa macchina (vedi
                <code>helpers/macos-daemons</code>).
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
import { Modal } from 'bootstrap'
import api from '../../api/axios'
import { useToastStore } from '../../stores/toast'

const toast = useToastStore()

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
  control_key: '',
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

function generateControlKey() {
  const bytes = new Uint8Array(32)
  crypto.getRandomValues(bytes)
  form.control_key = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('')
}

async function loadMachines() {
  loading.value = true
  try {
    const { data } = await api.get('/api/modules/macos-daemons/machines')
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
  form.control_key = ''
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
  form.control_key = ''
  slugTouched = true
  modalInstance.show()
}

async function save() {
  saving.value = true
  const isNew = !form.id
  try {
    if (!form.id) {
      await api.post('/api/modules/macos-daemons/machines', {
        name: form.name,
        slug: form.slug,
        ip_address: form.ip_address,
        control_key: form.control_key,
      })
    } else {
      const payload = {
        name: form.name,
        slug: form.slug,
        ip_address: form.ip_address,
      }
      if (form.control_key) payload.control_key = form.control_key
      await api.patch(`/api/modules/macos-daemons/machines/${form.id}`, payload)
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
  if (!confirm(`Eliminare la macchina ${machine.name}? Verranno eliminati anche i demoni configurati.`)) return
  try {
    await api.delete(`/api/modules/macos-daemons/machines/${machine.id}`)
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
