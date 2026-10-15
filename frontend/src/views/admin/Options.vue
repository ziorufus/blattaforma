<template>
  <div>
    <h1 class="mb-4">Opzioni</h1>
    <p class="text-muted">
      Le opzioni non modificate usano il valore di default definito nel codice. Salvare un
      valore lo registra nel database; "Ripristina default" lo rimuove. Le modifiche valgono
      subito, senza riavviare il backend.
    </p>

    <div v-if="loading" class="text-muted">Caricamento...</div>

    <template v-else>
      <div v-for="s in scopes" :key="s.scope" class="card mb-4">
        <div class="card-header d-flex justify-content-between align-items-center">
          <div>
            <span class="fw-semibold">{{ s.label }}</span>
            <code v-if="s.is_module" class="ms-2 small">{{ s.scope }}</code>
          </div>
          <div v-if="s.is_module" class="form-check form-switch mb-0">
            <input
              :id="`enabled-${s.scope}`"
              class="form-check-input"
              type="checkbox"
              role="switch"
              :checked="s.enabled"
              :disabled="busy[s.scope]"
              @change="toggleModule(s, $event)"
            />
            <label class="form-check-label" :for="`enabled-${s.scope}`">
              {{ s.enabled ? 'Attivo' : 'Disattivato' }}
            </label>
          </div>
        </div>

        <ul v-if="s.options.length > 0" class="list-group list-group-flush" :class="{ 'opacity-50': !s.enabled }">
          <li v-for="o in s.options" :key="o.key" class="list-group-item py-3">
            <div class="row g-3 align-items-start">
              <div class="col-lg-5">
                <div class="fw-semibold">
                  {{ o.label }}
                  <span v-if="o.public" class="badge bg-info text-dark ms-1"><i class="bi bi-globe"></i></span>
                  <span v-if="!o.is_default" class="badge bg-primary ms-1"><i class="bi bi-pencil"></i></span>
                </div>
                <div class="small text-muted"><code>{{ o.key }}</code></div>
                <div v-if="o.description" class="small text-muted mt-1">{{ o.description }}</div>
              </div>

              <div class="col-lg-4">
                <div v-if="kind(o) === 'boolean'" class="form-check form-switch">
                  <input
                    :id="`opt-${s.scope}-${o.key}`"
                    v-model="drafts[id(s, o)]"
                    class="form-check-input"
                    type="checkbox"
                    role="switch"
                  />
                  <label class="form-check-label" :for="`opt-${s.scope}-${o.key}`">
                    {{ drafts[id(s, o)] ? 'Sì' : 'No' }}
                  </label>
                </div>
                <select v-else-if="kind(o) === 'enum'" v-model="drafts[id(s, o)]" class="form-select">
                  <option v-for="v in o.json_schema.enum" :key="v" :value="v">{{ v }}</option>
                </select>
                <input
                  v-else-if="kind(o) === 'number'"
                  v-model.number="drafts[id(s, o)]"
                  type="number"
                  class="form-control"
                  :min="o.json_schema.minimum ?? o.json_schema.exclusiveMinimum"
                  :max="o.json_schema.maximum ?? o.json_schema.exclusiveMaximum"
                  :step="o.json_schema.type === 'integer' ? 1 : 'any'"
                />
                <input
                  v-else-if="kind(o) === 'string'"
                  v-model="drafts[id(s, o)]"
                  type="text"
                  class="form-control"
                />
                <textarea
                  v-else
                  v-model="drafts[id(s, o)]"
                  class="form-control font-monospace"
                  rows="4"
                ></textarea>
                <div class="small text-muted mt-1">
                  Default: <code>{{ formatValue(o.default) }}</code>
                </div>
                <div v-if="o.updated_by" class="small text-muted">
                  Modificata da {{ o.updated_by }} il {{ formatDate(o.updated_at) }}
                </div>
              </div>

              <div class="col-lg-3 text-lg-end">
                <button
                  class="btn btn-sm btn-primary me-2"
                  :disabled="!isDirty(s, o) || busy[id(s, o)]"
                  @click="save(s, o)"
                >
                  Salva
                </button>
                <button
                  class="btn btn-sm btn-outline-secondary"
                  :disabled="o.is_default || busy[id(s, o)]"
                  @click="reset(s, o)"
                >
                  Ripristina default
                </button>
              </div>
            </div>
          </li>
        </ul>
        <div v-else class="card-body text-muted small">Questo modulo non ha opzioni configurabili.</div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../../api/axios'
import { useAuthStore } from '../../stores/auth'
import { useConfigStore } from '../../stores/config'
import { useToastStore } from '../../stores/toast'

const auth = useAuthStore()
const config = useConfigStore()
const toast = useToastStore()

const scopes = ref([])
const loading = ref(true)
const drafts = reactive({})
const busy = reactive({})

const id = (s, o) => `${s.scope}.${o.key}`

// Il tipo di controllo si ricava dal JSON Schema del campo Pydantic; ciò che
// non è un tipo semplice (liste, oggetti, unioni) si modifica come JSON.
function kind(o) {
  const t = o.json_schema.type
  if (o.json_schema.enum) return 'enum'
  if (t === 'boolean') return 'boolean'
  if (t === 'integer' || t === 'number') return 'number'
  if (t === 'string') return 'string'
  return 'json'
}

function toDraft(o, value) {
  return kind(o) === 'json' ? JSON.stringify(value, null, 2) : value
}

function fromDraft(o, draft) {
  if (kind(o) !== 'json') return draft
  return JSON.parse(draft)
}

function isDirty(s, o) {
  try {
    return JSON.stringify(fromDraft(o, drafts[id(s, o)])) !== JSON.stringify(o.value)
  } catch (e) {
    return true
  }
}

function formatValue(v) {
  return typeof v === 'string' ? v : JSON.stringify(v)
}

function formatDate(v) {
  return v ? new Date(v).toLocaleString() : ''
}

function applyOption(s, updated) {
  const idx = s.options.findIndex((o) => o.key === updated.key)
  s.options[idx] = updated
  drafts[id(s, updated)] = toDraft(updated, updated.value)
}

async function load() {
  try {
    const { data } = await api.get('/api/options')
    scopes.value = data
    for (const s of data) {
      for (const o of s.options) drafts[id(s, o)] = toDraft(o, o.value)
    }
  } catch (e) {
    toast.apiError(e, 'Impossibile caricare le opzioni.')
  } finally {
    loading.value = false
  }
}

async function save(s, o) {
  let value
  try {
    value = fromDraft(o, drafts[id(s, o)])
  } catch (e) {
    toast.error(`"${o.label}": JSON non valido.`)
    return
  }
  if (kind(o) === 'number' && (value === '' || value === null || Number.isNaN(value))) {
    toast.error(`"${o.label}": inserisci un numero.`)
    return
  }

  busy[id(s, o)] = true
  try {
    const { data } = await api.put(`/api/options/${s.scope}/${o.key}`, { value })
    applyOption(s, data)
    toast.success(`"${o.label}" salvata.`)
    if (data.public) config.load()
  } catch (e) {
    toast.apiError(e, 'Impossibile salvare l\'opzione.')
  } finally {
    busy[id(s, o)] = false
  }
}

async function reset(s, o) {
  if (!confirm(`Ripristinare il valore di default per "${o.label}"?`)) return
  busy[id(s, o)] = true
  try {
    const { data } = await api.delete(`/api/options/${s.scope}/${o.key}`)
    applyOption(s, data)
    toast.success(`"${o.label}" riportata al default.`)
    if (data.public) config.load()
  } catch (e) {
    toast.apiError(e, 'Impossibile ripristinare l\'opzione.')
  } finally {
    busy[id(s, o)] = false
  }
}

async function toggleModule(s, event) {
  const enabled = event.target.checked
  if (
    !enabled &&
    !confirm(
      `Disattivare il modulo "${s.label}"? Le sue API (comprese pagine pubbliche e ` +
        'controlli automatici in background) smetteranno di funzionare per tutti.',
    )
  ) {
    event.target.checked = true
    return
  }

  busy[s.scope] = true
  try {
    const { data } = await api.put(`/api/modules/${s.scope}/enabled`, { enabled })
    s.enabled = data.enabled
    toast.success(`Modulo "${s.label}" ${data.enabled ? 'attivato' : 'disattivato'}.`)
    await Promise.allSettled([auth.fetchModules(), config.load()])
  } catch (e) {
    event.target.checked = s.enabled
    toast.apiError(e, 'Impossibile aggiornare il modulo.')
  } finally {
    busy[s.scope] = false
  }
}

onMounted(load)
</script>
