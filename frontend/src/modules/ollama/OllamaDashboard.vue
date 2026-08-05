<template>
  <div>
    <div class="d-md-flex justify-content-between align-items-center mb-4">
      <h1 class="mb-3 mb-md-0">Ollama</h1>
      <div class="d-md-flex gap-2">
        <div class="dropdown">
          <a
            type="button"
            class="btn btn-outline-secondary dropdown-toggle mb-3 mb-md-0 d-block d-md-inline"
            data-bs-toggle="dropdown"
            id="dropdown-info"
          >
            <i class="bi bi-info-circle me-1"></i>
            Informazioni modello
        </a>
          <ul class="dropdown-menu dropdown-menu-end" aria-labelledby="dropdown-info">
            <li v-for="model in allAvailableModels" :key="model">
              <a
                class="dropdown-item"
                :href="`https://ollama.com/library/${model}`"
                target="_blank"
                rel="noopener"
              >
                {{ model }}
              </a>
            </li>
            <li v-if="allAvailableModels.length === 0">
              <span class="dropdown-item-text text-muted">Nessun modello disponibile</span>
            </li>
          </ul>
        </div>
        <router-link v-if="canManageMachines" to="/modules/ollama/macchine" class="btn btn-outline-secondary mb-3 mb-md-0 d-block d-md-inline">
          <i class="bi bi-cpu me-1"></i>
          Gestisci macchine
        </router-link>
        <router-link v-if="canManageMachines" to="/modules/ollama/chiavi" class="btn btn-outline-secondary d-block d-md-inline">
          <i class="bi bi-key-fill me-1"></i>
          Gestisci chiavi
        </router-link>
      </div>
    </div>

    <div v-if="errorMessage" class="alert alert-danger">{{ errorMessage }}</div>

    <div v-if="writableMachines.length" class="mt-4">
      <h5>Scarica nuovi modelli</h5>
      <div v-for="m in writableMachines" :key="m.id" class="card mb-2">
        <div class="card-body">
          <h6 class="card-title">{{ m.name }}</h6>
          <div class="input-group mb-2">
            <input
              v-model="m.pullModel"
              type="text"
              class="form-control"
              placeholder="es. llama3:8b"
              :disabled="m.pulling"
            />
            <button class="btn btn-primary" :disabled="!m.pullModel || m.pulling" @click="pullModel(m)">
              <span v-if="m.pulling" class="spinner-border spinner-border-sm me-1"></span>
              <i v-else class="bi bi-cloud-download me-1"></i>Scarica
            </button>
          </div>
          <div v-if="m.pulling" class="progress" style="height: 20px">
            <div
              class="progress-bar progress-bar-striped progress-bar-animated"
              :style="{ width: m.pullPct + '%' }"
            >
              {{ m.pullStatus }}
            </div>
          </div>
          <div v-if="m.pullError" class="alert alert-danger py-1 px-2 mt-2 mb-0 small">{{ m.pullError }}</div>
        </div>
      </div>
    </div>

    <h5 class="mt-4">Gestione macchine</h5>
    <div class="card mb-2">
      <div class="card-body">
        <div class="table-responsive">
          <table class="table table-striped align-middle">
            <thead>
              <tr>
                <th>Macchina</th>
                <th style="min-width: 240px">Utilizzo</th>
                <th>Modelli in RAM</th>
                <th style="min-width: 260px">Carica un modello</th>
                <th></th>
              </tr>
            </thead>
            <tbody class="placeholder-glow" aria-hidden="true" v-if="loading">
              <tr v-for="index in 4" :key="index">
                <td>
                  <span
                    class="placeholder rounded-circle d-block"
                    style="width: 32px; height: 32px;"
                  ></span>
                  <div class="d-flex align-items-start gap-2">

                    <div class="flex-grow-1">
                      <span class="placeholder col-8"></span>
                      <span class="placeholder col-6 placeholder-sm d-block mt-1"></span>
                    </div>
                  </div>
                </td>

                <td>
                  <span
                    class="placeholder col-12 rounded"
                    style="height: 8px;"
                  ></span>

                  <span class="placeholder col-10 placeholder-sm d-block mt-2"></span>

                  <span
                    class="placeholder col-12 rounded d-block mt-3"
                    style="height: 8px;"
                  ></span>

                  <span class="placeholder col-7 placeholder-sm d-block mt-2"></span>
                </td>

                <td>
                  <span class="placeholder col-6 placeholder-sm"></span>
                </td>

                <td>
                  <div class="d-flex gap-1">
                    <span
                      class="placeholder flex-grow-1 rounded"
                      style="height: 31px;"
                    ></span>

                    <span
                      class="placeholder rounded"
                      style="width: 38px; height: 31px;"
                    ></span>
                  </div>
                </td>

                <td class="text-end">
                  <span
                    class="placeholder rounded"
                    style="width: 32px; height: 31px;"
                  ></span>
                </td>            
              </tr>
            </tbody>
            <tbody v-else>
              <tr v-for="m in machines" :key="m.id">
                <td>
                  <span class="rounded-logo"><i class="bi" :class="{'bi-apple': m.os === 'macos', 'bi-tux': m.os === 'linux'}"></i></span>
                  <div class="fw-semibold">{{ m.name }}</div>
                  <div class="text-muted small">{{ m.ip_address }}</div>
                </td>
                <td>
                  <div class="progress-container">
                    <template v-if="m.total_bytes != null">
                      <div class="progress">
                        <div
                          class="progress-bar bg-danger"
                          :style="{ width: otherPct(m) + '%' }"
                          :title="`Altri processi: ${formatBytes(otherBytes(m))}`"
                        ></div>
                        <div
                          class="progress-bar bg-warning"
                          :style="{ width: ollamaPct(m) + '%' }"
                          :title="`Ollama: ${formatBytes(m.ollama_bytes)}`"
                        ></div>
                      </div>
                      <div class="text-muted small mt-1 progress-labels">
                        {{ formatBytes(otherBytes(m)) }} altro + {{ formatBytes(m.ollama_bytes) }} ollama /
                        {{ formatBytes(m.total_bytes) }} ({{ formatBytes(m.available_bytes) }} libera)
                      </div>
                    </template>
                    <span v-else class="text-muted small">N/D</span>

                    <template v-if="m.gpu_percent != null">
                      <div class="progress mt-2">
                        <div
                          class="progress-bar bg-primary"
                          :style="{ width: m.gpu_percent + '%' }"
                          :title="`GPU: ${formatPercent(m.gpu_percent)}`"
                        ></div>
                      </div>
                      <div class="text-muted small mt-1 progress-labels">
                        GPU {{ formatPercent(m.gpu_percent) }} · {{ formatTemp(m.gpu_temp_celsius) }} ·
                        {{ formatPower(m.gpu_power_watts) }}
                      </div>
                    </template>
                  </div>
                </td>
                <td>
                  <span
                    v-for="lm in m.loaded_models"
                    :key="lm.name"
                    class="badge text-bg-info me-1 mb-1 d-inline-flex align-items-center"
                  >
                    {{ lm.name }} ({{ formatBytes(lm.size_bytes) }}{{ lm.context_size ? ', ctx ' + formatContext(lm.context_size) : '' }})
                    <button
                      type="button"
                      class="btn btn-sm btn-link text-white p-0 ms-1"
                      style="line-height: 1"
                      title="Espelli dalla RAM"
                      :disabled="m.unloadingModel === lm.name"
                      @click="unloadModel(m, lm.name)"
                    >
                      <span v-if="m.unloadingModel === lm.name" class="spinner-border spinner-border-sm"></span>
                      <i v-else class="bi bi-trash"></i>
                    </button>
                  </span>
                  <span v-if="!m.loaded_models || m.loaded_models.length === 0" class="text-muted small">
                    Nessuno
                  </span>
                </td>
                <td>
                  <div class="input-group input-group-sm">
                    <select v-model="m.selectedModel" class="form-select" :disabled="m.loadingModel">
                      <option value="">[Seleziona il modello]</option>
                      <option
                        v-for="am in sortedAvailableModels(m)"
                        :key="am.name"
                        :value="am.name"
                        :disabled="modelTooBig(m, am)"
                        :title="modelTooBig(m, am) ? 'RAM insufficiente su questa macchina' : ''"
                      >
                        {{ am.name }} ({{ formatBytes(am.size_bytes) }})
                      </option>
                    </select>
                    <select
                      v-model.number="m.selectedContextSize"
                      class="form-select"
                      style="max-width: 90px"
                      :disabled="m.loadingModel"
                      title="Dimensione del contesto"
                    >
                      <option v-for="opt in CONTEXT_SIZE_OPTIONS" :key="opt.value" :value="opt.value">
                        {{ opt.label }}
                      </option>
                    </select>
                    <button
                      class="btn btn-primary"
                      :disabled="!m.selectedModel || m.loadingModel"
                      @click="loadModel(m)"
                    >
                      <span v-if="m.loadingModel" class="spinner-border spinner-border-sm"></span>
                      <i v-else class="bi bi-check-lg"></i>
                    </button>
                  </div>
                </td>
                <td class="text-end">
                  <button class="btn btn-sm btn-outline-secondary" :disabled="m.refreshing" @click="refreshMachine(m)">
                    <span v-if="m.refreshing" class="spinner-border spinner-border-sm"></span>
                    <i v-else class="bi bi-arrow-clockwise"></i>
                  </button>
                </td>
              </tr>
              <tr v-if="machines.length === 0">
                <td colspan="5" class="text-muted">Nessuna macchina configurata.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>

  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import api from '../../api/axios'
import { useAuthStore } from '../../stores/auth'

const auth = useAuthStore()
const canManageMachines = computed(() => {
  if (auth.isAdmin) return true
  const mod = auth.modules.find((mm) => mm.name === 'ollama')
  return !!mod && mod.granted_roles.includes('machines')
})
const canPull = computed(() => {
  if (auth.isAdmin) return true
  const mod = auth.modules.find((mm) => mm.name === 'ollama')
  return !!mod && mod.granted_roles.includes('models')
})

const AUTO_REFRESH_INTERVAL_MS = 15000
const DEFAULT_CONTEXT_SIZE = 65536
const CONTEXT_SIZE_OPTIONS = [
  { value: 4096, label: '4K' },
  { value: 8192, label: '8K' },
  { value: 16384, label: '16K' },
  { value: 32768, label: '32K' },
  { value: 65536, label: '64K' },
  { value: 131072, label: '128K' },
]

const machines = ref([])
const loading = ref(true)
const errorMessage = ref('')
let autoRefreshTimer = null

const writableMachines = computed(() => (canPull.value ? machines.value.filter((m) => m.has_write_key) : []))

const allAvailableModels = computed(() => {
  const names = new Set()
  for (const m of machines.value) {
    for (const am of m.available_models || []) {
      names.add(am.name)
    }
  }
  return [...names].sort()
})

function sortedAvailableModels(m) {
  return [...(m.available_models || [])].sort((a, b) => a.name.localeCompare(b.name))
}

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return '-'
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`
}

function otherBytes(m) {
  if (m.total_bytes == null || m.available_bytes == null) return 0
  return Math.max(0, m.total_bytes - m.available_bytes - (m.ollama_bytes || 0))
}

function otherPct(m) {
  return m.total_bytes ? (otherBytes(m) / m.total_bytes) * 100 : 0
}

function ollamaPct(m) {
  return m.total_bytes ? ((m.ollama_bytes || 0) / m.total_bytes) * 100 : 0
}

function modelTooBig(m, am) {
  return am.size_bytes != null && m.available_bytes != null && am.size_bytes > m.available_bytes
}

function formatPercent(v) {
  if (v === null || v === undefined) return '-'
  return `${Math.round(v)}%`
}

function formatTemp(v) {
  if (v === null || v === undefined) return '-'
  return `${v.toFixed(1)} °C`
}

function formatPower(v) {
  if (v === null || v === undefined) return '-'
  return `${v.toFixed(1)} W`
}

function formatContext(v) {
  if (v === null || v === undefined) return '-'
  return `${Math.round(v / 1024)}K`
}

async function fetchStatus(machine) {
  try {
    const { data } = await api.get(`/api/modules/ollama/machines/${machine.id}/status`)
    Object.assign(machine, data)
  } catch (e) {
    machine.error = 'Impossibile contattare la macchina.'
  }
}

async function loadMachines() {
  loading.value = true
  errorMessage.value = ''
  try {
    const { data } = await api.get('/api/modules/ollama/machines')
    machines.value = data.map((m) => ({
      ...m,
      selectedModel: '',
      selectedContextSize: DEFAULT_CONTEXT_SIZE,
      loadingModel: false,
      unloadingModel: null,
      refreshing: false,
      pullModel: '',
      pulling: false,
      pullPct: 0,
      pullStatus: '',
      pullError: '',
      loaded_models: [],
      available_models: [],
    }))
    await Promise.all(machines.value.map((m) => fetchStatus(m)))
  } catch (e) {
    errorMessage.value = 'Impossibile caricare le macchine.'
  } finally {
    loading.value = false
  }
}

async function refreshMachine(m) {
  m.refreshing = true
  m.error = ''
  await fetchStatus(m)
  m.refreshing = false
}

async function loadModel(m) {
  m.loadingModel = true
  m.error = ''
  try {
    await api.post(`/api/modules/ollama/machines/${m.id}/load`, {
      model: m.selectedModel,
      context_size: m.selectedContextSize,
    })
    m.selectedModel = ''
    await fetchStatus(m)
  } catch (e) {
    m.error = e.response?.data?.detail || 'Impossibile caricare il modello.'
  } finally {
    m.loadingModel = false
  }
}

async function unloadModel(m, modelName) {
  m.unloadingModel = modelName
  m.error = ''
  try {
    await api.post(`/api/modules/ollama/machines/${m.id}/unload`, { model: modelName })
    await fetchStatus(m)
  } catch (e) {
    m.error = e.response?.data?.detail || 'Impossibile espellere il modello.'
  } finally {
    m.unloadingModel = null
  }
}

async function pullModel(m) {
  m.pulling = true
  m.pullError = ''
  m.pullPct = 0
  m.pullStatus = ''
  try {
    const base = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
    const resp = await fetch(`${base}/api/modules/ollama/machines/${m.id}/pull`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${auth.token}`,
      },
      body: JSON.stringify({ model: m.pullModel }),
    })

    if (!resp.ok || !resp.body) {
      let detail = 'Download non riuscito.'
      try {
        detail = (await resp.json()).detail || detail
      } catch (e) {
        // response body wasn't JSON, keep the generic message
      }
      throw new Error(detail)
    }

    const reader = resp.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.trim()) continue
        const evt = JSON.parse(line)
        if (evt.error) throw new Error(evt.error)
        m.pullStatus = evt.status || ''
        if (evt.total && evt.completed) {
          m.pullPct = Math.round((evt.completed / evt.total) * 100)
          m.pullStatus += ` (${m.pullPct}%)`
        }
      }
    }

    m.pullModel = ''
    m.pullPct = 100
    await fetchStatus(m)
  } catch (e) {
    m.pullError = e.message || 'Download non riuscito.'
  } finally {
    m.pulling = false
  }
}

async function refreshAll() {
  await Promise.all(machines.value.map((m) => fetchStatus(m)))
}

onMounted(async () => {
  await loadMachines()
  autoRefreshTimer = setInterval(refreshAll, AUTO_REFRESH_INTERVAL_MS)
})

onUnmounted(() => {
  if (autoRefreshTimer) clearInterval(autoRefreshTimer)
})
</script>

<style scoped>
.progress {
  border: 1px solid #aaa;
  height: 10px;
}
.progress-labels {
  font-size: 0.8rem;
}
.progress-container {
  padding-top: 5px;
}
.rounded-logo {
  display: inline-block;
  font-size: 1.3rem;
}
</style>
