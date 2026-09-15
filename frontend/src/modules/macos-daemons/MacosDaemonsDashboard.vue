<template>
  <div>
    <div class="d-md-flex justify-content-between align-items-center mb-4">
      <h1 class="mb-3 mb-md-0">Demoni macOS</h1>
      <div class="d-md-flex gap-2">
        <router-link to="/modules/macos-daemons/log" class="btn btn-outline-secondary mb-3 mb-md-0 d-block d-md-inline">
          <i class="bi bi-clock-history me-1"></i>Log azioni
        </router-link>
        <router-link to="/modules/macos-daemons/macchine" class="btn btn-outline-secondary d-block d-md-inline">
          <i class="bi bi-hdd-network me-1"></i>Macchine
        </router-link>
      </div>
    </div>

    <div v-if="loadingMachines" class="text-muted">Caricamento...</div>
    <div v-else-if="machines.length === 0" class="alert alert-info">
      Nessuna macchina configurata. Aggiungine una dalla pagina
      <router-link to="/modules/macos-daemons/macchine">Macchine</router-link>.
    </div>

    <div v-for="machine in machines" :key="machine.id" class="card mb-4">
      <div class="card-header d-flex justify-content-between align-items-center">
        <span>
          <strong>{{ machine.name }}</strong>
          <code class="ms-2">{{ machine.slug }}</code>
        </span>
        <div>
          <button class="btn btn-sm btn-outline-secondary me-2" @click="loadDaemons(machine.id)">
            <i class="bi bi-arrow-clockwise me-1"></i>Aggiorna
          </button>
          <button class="btn btn-sm btn-primary" @click="openAddDaemon(machine.id)">
            <i class="bi bi-plus-lg me-1"></i>Demone
          </button>
        </div>
      </div>
      <div class="card-body">
        <div v-if="loadingDaemons[machine.id]" class="text-muted">Caricamento...</div>
        <div v-else class="table-responsive">
          <table class="table table-sm align-middle mb-0">
            <thead>
              <tr>
                <th>Demone</th>
                <th>Label</th>
                <th>Stato</th>
                <th>Al boot</th>
                <th class="text-end">Azioni</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="d in daemonsByMachine[machine.id] || []" :key="d.id">
                <td>{{ d.display_name }}</td>
                <td><code>{{ d.label }}</code></td>
                <td>
                  <span v-if="d.error" class="badge text-bg-warning" :title="d.error">Non raggiungibile</span>
                  <span v-else-if="d.running" class="badge text-bg-success">In esecuzione</span>
                  <span v-else-if="d.loaded" class="badge text-bg-secondary">Caricato, fermo</span>
                  <span v-else class="badge text-bg-secondary">Fermo</span>
                </td>
                <td>
                  <div class="form-check form-switch mb-0">
                    <input
                      class="form-check-input"
                      type="checkbox"
                      role="switch"
                      :checked="!!d.enabled"
                      :disabled="busy[d.id] || d.error"
                      @change="toggleEnabled(machine.id, d)"
                    />
                  </div>
                </td>
                <td class="text-end nobr">
                  <button
                    class="btn btn-sm btn-outline-success me-2"
                    :disabled="busy[d.id] || d.running"
                    @click="runAction(machine.id, d, 'start')"
                  >
                    Avvia ora
                  </button>
                  <button
                    class="btn btn-sm btn-outline-danger me-2"
                    :disabled="busy[d.id] || !d.running"
                    @click="runAction(machine.id, d, 'stop')"
                  >
                    Ferma ora
                  </button>
                  <button class="btn btn-sm btn-outline-secondary" @click="removeDaemon(machine.id, d)">
                    <i class="bi bi-trash-fill"></i>
                  </button>
                </td>
              </tr>
              <tr v-if="(daemonsByMachine[machine.id] || []).length === 0">
                <td colspan="5" class="text-muted">Nessun demone configurato su questa macchina.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

    <!-- Add daemon modal -->
    <div class="modal fade" tabindex="-1" ref="modalEl">
      <div class="modal-dialog">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">Nuovo demone</h5>
            <button type="button" class="btn-close" @click="modalInstance.hide()"></button>
          </div>
          <div class="modal-body">
            <div class="alert alert-warning">
              La label deve esistere già nella whitelist root-only della macchina
              (<code>/opt/blattaforma-daemons/etc/daemons-whitelist.json</code>), altrimenti ogni
              azione fallirà.
            </div>
            <div class="mb-3">
              <label class="form-label">Nome visualizzato</label>
              <input v-model="form.display_name" type="text" class="form-control" required />
            </div>
            <div class="mb-3">
              <label class="form-label">Label</label>
              <input v-model="form.label" type="text" class="form-control" placeholder="com.azienda.miodemone" required />
            </div>
            <div class="mb-3">
              <label class="form-label">Percorso plist</label>
              <input
                v-model="form.plist_path"
                type="text"
                class="form-control"
                placeholder="/Library/LaunchDaemons/com.azienda.miodemone.plist"
                required
              />
            </div>
          </div>
          <div class="modal-footer">
            <button type="button" class="btn btn-secondary" @click="modalInstance.hide()">Annulla</button>
            <button type="button" class="btn btn-primary" @click="saveDaemon" :disabled="saving">Salva</button>
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
const loadingMachines = ref(true)
const loadingDaemons = reactive({})
const daemonsByMachine = reactive({})
const busy = reactive({})
const saving = ref(false)

const modalEl = ref(null)
let modalInstance = null
const form = reactive({ machineId: null, display_name: '', label: '', plist_path: '' })

async function loadMachines() {
  loadingMachines.value = true
  try {
    const { data } = await api.get('/api/modules/macos-daemons/machines')
    machines.value = data
    await Promise.all(data.map((m) => loadDaemons(m.id)))
  } catch (e) {
    toast.apiError(e, 'Impossibile caricare le macchine.')
  } finally {
    loadingMachines.value = false
  }
}

async function loadDaemons(machineId) {
  loadingDaemons[machineId] = true
  try {
    const { data } = await api.get(`/api/modules/macos-daemons/machines/${machineId}/daemons`)
    daemonsByMachine[machineId] = data
  } catch (e) {
    toast.apiError(e, 'Impossibile caricare i demoni.')
  } finally {
    loadingDaemons[machineId] = false
  }
}

function replaceDaemon(machineId, updated) {
  const list = daemonsByMachine[machineId] || []
  const idx = list.findIndex((x) => x.id === updated.id)
  if (idx !== -1) list[idx] = updated
}

async function refreshDaemon(machineId, daemonId) {
  try {
    const { data } = await api.get(`/api/modules/macos-daemons/machines/${machineId}/daemons/${daemonId}/status`)
    replaceDaemon(machineId, data)
  } catch (e) {
    toast.apiError(e, 'Impossibile aggiornare lo stato del demone.')
  }
}

async function runAction(machineId, daemon, action) {
  if ((action === 'stop') && !confirm(`Fermare "${daemon.display_name}" adesso?`)) return
  busy[daemon.id] = true
  try {
    const { data } = await api.post(
      `/api/modules/macos-daemons/machines/${machineId}/daemons/${daemon.id}/${action}`,
    )
    if (!data.success) {
      toast.error(data.message || `Azione "${action}" non riuscita.`)
    }
    await refreshDaemon(machineId, daemon.id)
  } catch (e) {
    toast.apiError(e, `Azione "${action}" non riuscita.`)
  } finally {
    busy[daemon.id] = false
  }
}

async function toggleEnabled(machineId, daemon) {
  const action = daemon.enabled ? 'disable' : 'enable'
  if (action === 'disable' && !confirm(`Disabilitare "${daemon.display_name}" all'avvio della macchina?`)) return
  await runAction(machineId, daemon, action)
}

function openAddDaemon(machineId) {
  form.machineId = machineId
  form.display_name = ''
  form.label = ''
  form.plist_path = ''
  modalInstance.show()
}

async function saveDaemon() {
  saving.value = true
  try {
    await api.post(`/api/modules/macos-daemons/machines/${form.machineId}/daemons`, {
      display_name: form.display_name,
      label: form.label,
      plist_path: form.plist_path,
    })
    modalInstance.hide()
    await loadDaemons(form.machineId)
    toast.success(`Demone "${form.display_name}" aggiunto.`)
  } catch (e) {
    toast.apiError(e, 'Salvataggio non riuscito.')
  } finally {
    saving.value = false
  }
}

async function removeDaemon(machineId, daemon) {
  if (!confirm(`Rimuovere "${daemon.display_name}" dall'elenco? Non tocca nulla sulla macchina.`)) return
  try {
    await api.delete(`/api/modules/macos-daemons/machines/${machineId}/daemons/${daemon.id}`)
    await loadDaemons(machineId)
    toast.success(`Demone "${daemon.display_name}" rimosso.`)
  } catch (e) {
    toast.apiError(e, 'Impossibile rimuovere il demone.')
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
