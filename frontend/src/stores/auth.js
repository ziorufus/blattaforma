import { defineStore } from 'pinia'
import api from '../api/axios'

const TOKEN_KEY = 'blattaforma_token'

export const useAuthStore = defineStore('auth', {
  state: () => ({
    token: localStorage.getItem(TOKEN_KEY) || null,
    user: null,
    modules: [],
    ready: false,
  }),

  getters: {
    isAuthenticated: (state) => !!state.token,
    isAdmin: (state) => !!state.user?.is_admin,
    accessibleModules: (state) => state.modules.filter((m) => m.granted_roles.length > 0),
  },

  actions: {
    setToken(token) {
      this.token = token
      localStorage.setItem(TOKEN_KEY, token)
    },

    logout() {
      this.token = null
      this.user = null
      this.modules = []
      localStorage.removeItem(TOKEN_KEY)
    },

    async fetchMe() {
      const { data } = await api.get('/api/auth/me')
      this.user = data
      return data
    },

    async fetchModules() {
      const { data } = await api.get('/api/modules')
      this.modules = data
      return data
    },

    async init() {
      if (!this.token) {
        this.ready = true
        return
      }
      try {
        await this.fetchMe()
        await this.fetchModules()
      } catch (e) {
        this.logout()
      } finally {
        this.ready = true
      }
    },

    hasModuleAccess(moduleName) {
      const m = this.modules.find((mod) => mod.name === moduleName)
      return !!m && m.granted_roles.length > 0
    },
  },
})

// Il logout in una scheda scrive solo nel suo localStorage locale: le altre
// schede aperte sullo stesso sito hanno già il token in memoria (nel loro
// Pinia store) e continuerebbero a usarlo, resuscitandolo in localStorage
// alla prima chiamata autenticata. L'evento "storage" (che il browser invia
// automaticamente alle ALTRE schede quando cambia localStorage, mai a quella
// che ha fatto la modifica) permette di propagare subito il logout ovunque.
window.addEventListener('storage', (event) => {
  if (event.key === TOKEN_KEY && !event.newValue) {
    const auth = useAuthStore()
    if (auth.token) {
      auth.logout()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
  }
})
