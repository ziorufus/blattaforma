import MacosDaemonsDashboard from './MacosDaemonsDashboard.vue'
import MacosDaemonsMachines from './MacosDaemonsMachines.vue'
import MacosDaemonsLog from './MacosDaemonsLog.vue'

export default {
  name: 'macos-daemons',
  routes: [
    { path: '', name: 'dashboard', component: MacosDaemonsDashboard },
    { path: 'macchine', name: 'macchine', component: MacosDaemonsMachines },
    { path: 'log', name: 'log', component: MacosDaemonsLog },
  ],
}
