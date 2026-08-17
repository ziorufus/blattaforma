<template>
  <div>
    <h1 class="mb-4">Moduli</h1>
    <p class="text-muted">
      Elenco dei moduli scoperti dal backend all'avvio. Per assegnare l'accesso a un modulo,
      gestisci i permessi da <router-link to="/admin/users">Utenti</router-link> o
      <router-link to="/admin/groups">Gruppi</router-link>.
    </p>

    <div v-if="loading" class="text-muted">Caricamento...</div>
    <table v-else class="table table-striped align-middle">
      <thead>
        <tr>
          <th>Nome interno</th>
          <th>Nome descrittivo</th>
          <th>Ruoli disponibili</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="m in modules" :key="m.id">
          <td><code>{{ m.name }}</code></td>
          <td>{{ m.label }}</td>
          <td>
            <span v-for="r in m.roles" :key="r" class="badge bg-secondary me-1">{{ r }}</span>
          </td>
        </tr>
        <tr v-if="modules.length === 0">
          <td colspan="3" class="text-muted">Nessun modulo installato.</td>
        </tr>
      </tbody>
    </table>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../../api/axios'
import { useToastStore } from '../../stores/toast'

const toast = useToastStore()
const modules = ref([])
const loading = ref(true)

onMounted(async () => {
  try {
    const { data } = await api.get('/api/modules/all')
    modules.value = data
  } catch (e) {
    toast.apiError(e, 'Impossibile caricare i moduli.')
  } finally {
    loading.value = false
  }
})
</script>
