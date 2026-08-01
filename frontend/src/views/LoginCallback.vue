<template>
  <div class="d-flex justify-content-center align-items-center" style="min-height: 80vh">
    <div class="text-center">
      <div class="spinner-border text-primary mb-3" role="status"></div>
      <p class="text-muted">Accesso in corso...</p>
    </div>
  </div>
</template>

<script setup>
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const router = useRouter()
const auth = useAuthStore()

onMounted(async () => {
  const raw = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash
  const token = new URLSearchParams(raw).get('token')

  if (!token) {
    router.replace({ name: 'login', query: { error: 'oauth_failed' } })
    return
  }

  auth.setToken(token)
  try {
    await auth.fetchMe()
    await auth.fetchModules()
    router.replace({ path: '/' })
  } catch (e) {
    auth.logout()
    router.replace({ name: 'login', query: { error: 'unauthorized' } })
  }
})
</script>
