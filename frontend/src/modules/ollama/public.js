import OllamaPublicMachines from './OllamaPublicMachines.vue'

export default {
  name: 'ollama',
  routes: [{ path: '', name: 'macchine', label: 'Macchine Ollama', component: OllamaPublicMachines }],
}
