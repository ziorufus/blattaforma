import axios from 'axios'
import { useAuthStore } from '../stores/auth'
import { API_BASE_URL } from '../config'

const api = axios.create({
  baseURL: API_BASE_URL,
})

api.interceptors.request.use((config) => {
  const auth = useAuthStore()
  if (auth.token) {
    config.headers.Authorization = `Bearer ${auth.token}`
  }
  return config
})

api.interceptors.response.use(
  (response) => {
    const newToken = response.headers['x-new-token']
    const auth = useAuthStore()
    // Se nel frattempo è stato fatto logout (richiesta partita prima del
    // click su "Esci", risposta arrivata dopo), non bisogna resuscitare il
    // token: altrimenti il logout risulta solo apparente.
    if (newToken && auth.token) {
      auth.setToken(newToken)
    }
    return response
  },
  (error) => {
    if (error.response && error.response.status === 401) {
      useAuthStore().logout()
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  },
)

export default api
