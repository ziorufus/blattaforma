import { defineStore } from 'pinia'
import api from '../api/axios'

// Configurazione pubblica della piattaforma (opzioni marcate "public" lato
// backend e moduli attivi), caricata prima del mount dell'app e leggibile
// anche senza login.
export const useConfigStore = defineStore('config', {
  state: () => ({
    options: {},
    // null = non ancora caricata (o caricamento fallito): in quel caso si
    // considera tutto attivo, il backend resta comunque l'autorità finale.
    enabledModules: null,
  }),

  actions: {
    async load() {
      try {
        const { data } = await api.get('/api/options/public')
        this.options = data.options
        this.enabledModules = data.enabled_modules
      } catch (e) {
        // Lascia i default: meglio mostrare un pulsante in più che bloccare il login.
      }
    },

    option(scope, key, fallback = undefined) {
      return this.options[scope]?.[key] ?? fallback
    },

    isModuleEnabled(name) {
      return this.enabledModules === null || this.enabledModules.includes(name)
    },
  },
})
