import { createApp } from 'vue'
import { createPinia } from 'pinia'

import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap-icons/font/bootstrap-icons.css'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'
import { useConfigStore } from './stores/config'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)

// Router is installed only once the stored token (if any) has been
// validated against the backend and the public config (login providers,
// enabled modules) has been loaded, so the very first navigation guard sees
// accurate state instead of racing those calls.
Promise.allSettled([useAuthStore().init(), useConfigStore().load()])
  .finally(() => {
    app.use(router)
    app.mount('#app')
  })
