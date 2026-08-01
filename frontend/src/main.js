import { createApp } from 'vue'
import { createPinia } from 'pinia'

import 'bootstrap/dist/css/bootstrap.min.css'
import 'bootstrap-icons/font/bootstrap-icons.css'

import App from './App.vue'
import router from './router'
import { useAuthStore } from './stores/auth'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)

// Router is installed only once the stored token (if any) has been
// validated against the backend, so the very first navigation guard sees
// accurate auth state instead of racing the /api/auth/me call.
useAuthStore()
  .init()
  .finally(() => {
    app.use(router)
    app.mount('#app')
  })
