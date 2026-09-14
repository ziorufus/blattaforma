import OllamaDashboard from './OllamaDashboard.vue'
import OllamaMachines from './OllamaMachines.vue'
import OllamaKeys from './OllamaKeys.vue'
import OllamaKeyDetail from './OllamaKeyDetail.vue'

export default {
  name: 'ollama',
  routes: [
    { path: '', name: 'dashboard', component: OllamaDashboard },
    { path: 'macchine', name: 'macchine', component: OllamaMachines },
    { path: 'chiavi', name: 'chiavi', component: OllamaKeys },
    { path: 'chiavi/:id', name: 'chiave-dettaglio', component: OllamaKeyDetail },
    // Stesso componente della route admin sopra: OllamaKeyDetail distingue
    // le due viste in base al nome della route (vedi commento nel componente).
    { path: 'mie-chiavi/:id', name: 'mia-chiave-dettaglio', component: OllamaKeyDetail },
  ],
}
