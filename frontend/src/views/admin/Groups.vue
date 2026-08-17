<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h1 class="mb-0">Gruppi</h1>
      <button class="btn btn-primary" @click="openCreate">
        <i class="bi bi-plus-lg me-1"></i>Nuovo gruppo
      </button>
    </div>

    <div v-if="loading" class="text-muted">Caricamento...</div>
    <table v-else class="table table-striped align-middle">
      <thead>
        <tr>
          <th>Nome</th>
          <th>Descrizione</th>
          <th>Membri</th>
          <th class="text-end">Azioni</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="g in groups" :key="g.id">
          <td>{{ g.name }}</td>
          <td>{{ g.description || '-' }}</td>
          <td>{{ g.member_count }}</td>
          <td class="text-end">
            <button class="btn btn-sm btn-outline-secondary me-2" @click="openEdit(g)">
              Modifica
            </button>
            <button class="btn btn-sm btn-outline-danger" @click="removeGroup(g)">Elimina</button>
          </td>
        </tr>
        <tr v-if="groups.length === 0">
          <td colspan="4" class="text-muted">Nessun gruppo creato.</td>
        </tr>
      </tbody>
    </table>

    <!-- Create / Edit modal -->
    <div class="modal fade" tabindex="-1" ref="modalEl">
      <div class="modal-dialog modal-lg modal-dialog-scrollable">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ form.id ? 'Modifica gruppo' : 'Nuovo gruppo' }}</h5>
            <button type="button" class="btn-close" @click="modalInstance.hide()"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">Nome</label>
              <input v-model="form.name" type="text" class="form-control" required />
            </div>
            <div class="mb-4">
              <label class="form-label">Descrizione</label>
              <textarea v-model="form.description" class="form-control" rows="2"></textarea>
            </div>

            <div class="mb-4" v-if="form.id">
              <h6>Membri</h6>
              <div class="form-check" v-for="u in users" :key="u.id">
                <input
                  class="form-check-input"
                  type="checkbox"
                  :id="`member-${u.id}`"
                  :value="u.id"
                  v-model="form.user_ids"
                />
                <label class="form-check-label" :for="`member-${u.id}`">
                  {{ u.name || u.email }} <span class="text-muted">({{ u.email }})</span>
                </label>
              </div>
              <p v-if="users.length === 0" class="text-muted small">Nessun utente disponibile.</p>
            </div>

            <div v-if="form.id">
              <h6>Permessi sui moduli</h6>
              <p class="text-muted small">
                Questi permessi si sommano a quelli assegnati direttamente ai singoli utenti.
              </p>
              <table class="table table-sm">
                <thead>
                  <tr>
                    <th>Modulo</th>
                    <th v-for="role in allRoles" :key="role">{{ role }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="m in modules" :key="m.id">
                    <td>{{ m.label }}</td>
                    <td v-for="role in allRoles" :key="role">
                      <input
                        v-if="m.roles.includes(role)"
                        class="form-check-input"
                        type="checkbox"
                        :checked="form.permissions[m.name]?.has(role)"
                        @change="togglePermission(m.name, role)"
                      />
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-else class="text-muted small">
              Salva il gruppo per poter gestire membri e permessi.
            </p>
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
import { useToastStore } from '../../stores/toast'

const toast = useToastStore()

const groups = ref([])
const users = ref([])
const modules = ref([])
const loading = ref(true)
const saving = ref(false)

const modalEl = ref(null)
let modalInstance = null

const form = reactive({
  id: null,
  name: '',
  description: '',
  user_ids: [],
  permissions: {},
})

const allRoles = computed(() => {
  const set = new Set()
  modules.value.forEach((m) => m.roles.forEach((r) => set.add(r)))
  return Array.from(set)
})

function togglePermission(moduleName, role) {
  if (!form.permissions[moduleName]) {
    form.permissions[moduleName] = new Set()
  }
  const set = form.permissions[moduleName]
  if (set.has(role)) {
    set.delete(role)
  } else {
    set.add(role)
  }
}

async function loadAll() {
  loading.value = true
  try {
    const [groupsRes, usersRes, modulesRes] = await Promise.all([
      api.get('/api/groups'),
      api.get('/api/users'),
      api.get('/api/modules/all'),
    ])
    groups.value = groupsRes.data
    users.value = usersRes.data
    modules.value = modulesRes.data
  } catch (e) {
    toast.apiError(e, 'Impossibile caricare i dati.')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.id = null
  form.name = ''
  form.description = ''
  form.user_ids = []
  form.permissions = {}
}

function openCreate() {
  resetForm()
  modalInstance.show()
}

async function openEdit(group) {
  try {
    const { data } = await api.get(`/api/groups/${group.id}`)
    form.id = data.id
    form.name = data.name
    form.description = data.description || ''
    form.user_ids = data.members.map((u) => u.id)
    const perms = {}
    data.permissions.forEach((p) => {
      if (!perms[p.module_name]) perms[p.module_name] = new Set()
      perms[p.module_name].add(p.role)
    })
    form.permissions = perms
    modalInstance.show()
  } catch (e) {
    toast.apiError(e, 'Impossibile caricare il gruppo.')
  }
}

async function save() {
  saving.value = true
  const isNew = !form.id
  try {
    let groupId = form.id
    if (!groupId) {
      const { data } = await api.post('/api/groups', {
        name: form.name,
        description: form.description,
      })
      groupId = data.id
    } else {
      await api.patch(`/api/groups/${groupId}`, {
        name: form.name,
        description: form.description,
      })
      await api.put(`/api/groups/${groupId}/members`, { user_ids: form.user_ids })

      const permissions = []
      for (const [moduleName, roles] of Object.entries(form.permissions)) {
        roles.forEach((role) => permissions.push({ module_name: moduleName, role }))
      }
      await api.put(`/api/groups/${groupId}/permissions`, { permissions })
    }

    modalInstance.hide()
    await loadAll()
    toast.success(isNew ? `Gruppo "${form.name}" creato.` : `Gruppo "${form.name}" aggiornato.`)
  } catch (e) {
    toast.apiError(e, 'Salvataggio non riuscito.')
  } finally {
    saving.value = false
  }
}

async function removeGroup(group) {
  if (!confirm(`Eliminare il gruppo ${group.name}?`)) return
  try {
    await api.delete(`/api/groups/${group.id}`)
    await loadAll()
    toast.success(`Gruppo "${group.name}" eliminato.`)
  } catch (e) {
    toast.apiError(e, 'Impossibile eliminare il gruppo.')
  }
}

onMounted(async () => {
  modalInstance = new Modal(modalEl.value)
  await loadAll()
})
</script>
