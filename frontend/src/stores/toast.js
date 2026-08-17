import { defineStore } from 'pinia'

let nextId = 1

export const useToastStore = defineStore('toast', {
  state: () => ({
    toasts: [],
  }),

  actions: {
    push(type, message) {
      const id = nextId++
      this.toasts.push({ id, type, message })
      return id
    },

    success(message) {
      return this.push('success', message)
    },

    error(message) {
      return this.push('danger', message)
    },

    apiError(e, fallback) {
      return this.error(e.response?.data?.detail || fallback)
    },

    dismiss(id) {
      this.toasts = this.toasts.filter((t) => t.id !== id)
    },
  },
})
