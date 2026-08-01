<template>
  <NavBar v-if="auth.isAuthenticated && auth.user" />
  <main class="container-fluid py-4">
    <router-view />
  </main>
</template>

<script setup>
import NavBar from './components/NavBar.vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
</script>
