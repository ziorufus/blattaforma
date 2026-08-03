import OllamaDashboard from './OllamaDashboard.vue'
import OllamaMachines from './OllamaMachines.vue'
import OllamaKeys from './OllamaKeys.vue'

export default {
  name: 'ollama',
  routes: [
    { path: '', name: 'dashboard', component: OllamaDashboard },
    { path: 'macchine', name: 'macchine', component: OllamaMachines },
    { path: 'chiavi', name: 'chiavi', component: OllamaKeys },
  ],
}
