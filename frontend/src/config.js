// Configurazione runtime: public/config.js (window.__APP_CONFIG__) ha la
// precedenza su VITE_API_BASE_URL, che viene fissato a build time.
const runtime = window.__APP_CONFIG__ || {}

export const API_BASE_URL =
  runtime.API_BASE_URL || import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
