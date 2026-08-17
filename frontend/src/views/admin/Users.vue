<template>
  <div>
    <div class="d-flex justify-content-between align-items-center mb-4">
      <h1 class="mb-0">Utenti</h1>
      <button class="btn btn-primary" @click="openCreate">
        <i class="bi bi-plus-lg me-1"></i>Nuovo utente
      </button>
    </div>

    <div v-if="loading" class="text-muted">Caricamento...</div>
    <table v-else class="table table-striped align-middle">
      <thead>
        <tr>
          <th>Email</th>
          <th>Nome</th>
          <th>Gruppi</th>
          <th>Stato</th>
          <th class="text-end">Azioni</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="u in users" :key="u.id">
          <td>{{ u.email }}</td>
          <td>{{ u.name || '-' }}</td>
          <td>
            <span v-for="gid in u.group_ids" :key="gid" class="badge bg-secondary me-1">
              {{ groupName(gid) }}
            </span>
          </td>
          <td>
            <span v-if="u.is_admin" class="badge bg-warning text-dark me-1">admin</span>
            <span v-if="!u.is_active" class="badge bg-danger">disattivato</span>
          </td>
          <td class="text-end">
            <button class="btn btn-sm btn-outline-secondary me-2" @click="openEdit(u)">
              Modifica
            </button>
            <button
              class="btn btn-sm btn-outline-danger"
              :disabled="u.id === auth.user?.id"
              @click="removeUser(u)"
            >
              Elimina
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- Create / Edit modal -->
    <div class="modal fade" tabindex="-1" ref="modalEl">
      <div class="modal-dialog modal-lg modal-dialog-scrollable">
        <div class="modal-content">
          <div class="modal-header">
            <h5 class="modal-title">{{ form.id ? 'Modifica utente' : 'Nuovo utente' }}</h5>
            <button type="button" class="btn-close" @click="modalInstance.hide()"></button>
          </div>
          <div class="modal-body">
            <div class="mb-3">
              <label class="form-label">Email</label>
              <input
                v-model="form.email"
                type="email"
                class="form-control"
                :disabled="!!form.id"
                required
              />
            </div>
            <div class="mb-3">
              <label class="form-label">Nome</label>
              <input v-model="form.name" type="text" class="form-control" />
            </div>

            <div class="form-check mb-3">
              <input
                v-model="form.is_admin"
                class="form-check-input"
                type="checkbox"
                id="isAdminCheck"
                :disabled="isSelf"
              />
              <label class="form-check-label" for="isAdminCheck">Amministratore</label>
              <div v-if="isSelf" class="form-text">
                Non puoi rimuovere i tuoi stessi privilegi di amministratore.
              </div>
            </div>

            <div class="form-check mb-4">
              <input
                v-model="form.is_active"
                class="form-check-input"
                type="checkbox"
                id="isActiveCheck"
                :disabled="isSelf"
              />
              <label class="form-check-label" for="isActiveCheck">Attivo</label>
            </div>

            <div class="mb-4">
              <h6>Gruppi</h6>
              <div class="form-check" v-for="g in groups" :key="g.id">
                <input
                  class="form-check-input"
                  type="checkbox"
                  :id="`group-${g.id}`"
                  :value="g.id"
                  v-model="form.group_ids"
                />
                <label class="form-check-label" :for="`group-${g.id}`">{{ g.name }}</label>
              </div>
              <p v-if="groups.length === 0" class="text-muted small">Nessun gruppo creato.</p>
            </div>

            <div>
              <h6>Permessi sui moduli</h6>
              <p class="text-muted small">
                I permessi diretti si sommano a quelli ereditati dai gruppi selezionati.
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

const users = ref([])
const groups = ref([])
const modules = ref([])
const loading = ref(true)
const saving = ref(false)

const modalEl = ref(null)
let modalInstance = null

const form = reactive({
  id: null,
  email: '',
  name: '',
  is_admin: false,
  is_active: true,
  group_ids: [],
  permissions: {},
})

const isSelf = computed(() => form.id != null && form.id === auth.user?.id)

const allRoles = computed(() => {
  const set = new Set()
  modules.value.forEach((m) => m.roles.forEach((r) => set.add(r)))
  return Array.from(set)
})

function groupName(id) {
  return groups.value.find((g) => g.id === id)?.name || `#${id}`
}

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
    const [usersRes, groupsRes, modulesRes] = await Promise.all([
      api.get('/api/users'),
      api.get('/api/groups'),
      api.get('/api/modules/all'),
    ])
    users.value = usersRes.data
    groups.value = groupsRes.data
    modules.value = modulesRes.data
  } catch (e) {
    toast.apiError(e, 'Impossibile caricare i dati.')
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.id = null
  form.email = ''
  form.name = ''
  form.is_admin = false
  form.is_active = true
  form.group_ids = []
  form.permissions = {}
}

function openCreate() {
  resetForm()
  modalInstance.show()
}

async function openEdit(user) {
  try {
    const { data } = await api.get(`/api/users/${user.id}`)
    form.id = data.id
    form.email = data.email
    form.name = data.name || ''
    form.is_admin = data.is_admin
    form.is_active = data.is_active
    form.group_ids = data.groups.map((g) => g.id)
    const perms = {}
    data.permissions.forEach((p) => {
      if (!perms[p.module_name]) perms[p.module_name] = new Set()
      perms[p.module_name].add(p.role)
    })
    form.permissions = perms
    modalInstance.show()
  } catch (e) {
    toast.apiError(e, "Impossibile caricare l'utente.")
  }
}

async function save() {
  saving.value = true
  const isNew = !form.id
  try {
    let userId = form.id
    if (!userId) {
      const { data } = await api.post('/api/users', {
        email: form.email,
        name: form.name,
        is_admin: form.is_admin,
      })
      userId = data.id
    } else {
      await api.patch(`/api/users/${userId}`, {
        name: form.name,
        is_admin: form.is_admin,
        is_active: form.is_active,
      })
    }

    await api.put(`/api/users/${userId}/groups`, { group_ids: form.group_ids })

    const permissions = []
    for (const [moduleName, roles] of Object.entries(form.permissions)) {
      roles.forEach((role) => permissions.push({ module_name: moduleName, role }))
    }
    await api.put(`/api/users/${userId}/permissions`, { permissions })

    modalInstance.hide()
    await loadAll()
    toast.success(isNew ? `Utente "${form.email}" creato.` : `Utente "${form.email}" aggiornato.`)
  } catch (e) {
    toast.apiError(e, 'Salvataggio non riuscito.')
  } finally {
    saving.value = false
  }
}

async function removeUser(user) {
  if (!confirm(`Eliminare l'utente ${user.email}?`)) return
  try {
    await api.delete(`/api/users/${user.id}`)
    await loadAll()
    toast.success(`Utente "${user.email}" eliminato.`)
  } catch (e) {
    toast.apiError(e, "Impossibile eliminare l'utente.")
  }
}

onMounted(async () => {
  modalInstance = new Modal(modalEl.value)
  await loadAll()
})
</script>
