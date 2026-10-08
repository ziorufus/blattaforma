<template>
  <div>
    <div class="d-flex align-items-center mb-4">
      <router-link to="/login" title="Torna alla home">
        <img src="/blattaforma-logo.png" alt="Blattaforma" height="32" class="me-2" />
      </router-link>
      <h1 class="mb-0">Macchine Ollama</h1>
    </div>

    <div class="card mb-2">
      <div class="card-body">
        <div class="table-responsive">
          <table class="table table-striped align-middle">
            <thead>
              <tr>
                <th>Macchina</th>
                <th style="min-width: 240px">Utilizzo</th>
              </tr>
            </thead>
            <tbody v-if="loading">
              <tr v-for="index in 4" :key="index" class="placeholder-glow" aria-hidden="true">
                <td><span class="placeholder col-8"></span></td>
                <td>
                  <span class="placeholder col-12 rounded d-block" style="height: 8px;"></span>
                  <span class="placeholder col-10 placeholder-sm d-block mt-2"></span>
                </td>
              </tr>
            </tbody>
            <tbody v-else-if="error">
              <tr>
                <td colspan="2" class="text-danger">{{ error }}</td>
              </tr>
            </tbody>
            <tbody v-else>
              <tr v-for="m in machines" :key="m.name">
                <td>
                  <span class="rounded-logo"><i class="bi" :class="{'bi-apple': m.os === 'macos', 'bi-tux': m.os === 'linux'}"></i></span>
                  <div class="fw-semibold">{{ m.name }}</div>
                </td>
                <td>
                  <div class="progress-container">
                    <template v-if="m.total_bytes != null">
                      <div class="progress">
                        <div
                          class="progress-bar bg-danger"
                          :style="{ width: usedPct(m) + '%' }"
                          :title="`In uso: ${formatBytes(usedBytes(m))}`"
                        ></div>
                      </div>
                      <div class="text-muted small mt-1 progress-labels">
                        {{ formatBytes(usedBytes(m)) }} / {{ formatBytes(m.total_bytes) }}
                        ({{ formatBytes(m.available_bytes) }} libera)
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
              </tr>
              <tr v-if="machines.length === 0">
                <td colspan="2" class="text-muted">Nessuna macchina configurata.</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import api from '../../api/axios'

const AUTO_REFRESH_INTERVAL_MS = 15000

const machines = ref([])
const loading = ref(true)
const error = ref('')
let pollTimer = null

function formatBytes(bytes) {
  if (bytes === null || bytes === undefined) return '-'
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`
}

function usedBytes(m) {
  if (m.total_bytes == null || m.available_bytes == null) return 0
  return Math.max(0, m.total_bytes - m.available_bytes)
}

function usedPct(m) {
  return m.total_bytes ? (usedBytes(m) / m.total_bytes) * 100 : 0
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

async function loadMachines({ silent = false } = {}) {
  if (!silent) loading.value = true
  try {
    const { data } = await api.get('/api/modules/ollama/public/machines')
    machines.value = data
    error.value = ''
  } catch (e) {
    if (!silent) error.value = 'Impossibile caricare lo stato delle macchine al momento.'
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  await loadMachines()
  pollTimer = setInterval(() => loadMachines({ silent: true }), AUTO_REFRESH_INTERVAL_MS)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
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
