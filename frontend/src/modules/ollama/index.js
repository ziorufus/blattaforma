import OllamaDashboard from './OllamaDashboard.vue'
import OllamaMachines from './OllamaMachines.vue'

export default {
  name: 'ollama',
  routes: [
    { path: '', name: 'dashboard', component: OllamaDashboard },
    { path: 'macchine', name: 'macchine', component: OllamaMachines },
  ],
}
