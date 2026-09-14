import PublicStatus from './PublicStatus.vue'

export default {
  name: 'api-status',
  routes: [{ path: '', name: 'status', label: 'Stato dei servizi', component: PublicStatus }],
}
