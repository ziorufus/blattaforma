<template>
  <NavBar v-if="auth.isAuthenticated && auth.user" />
  <main class="container-xxl py-4">
    <router-view />
  </main>
  <ToastContainer />
</template>

<script setup>
import NavBar from './components/NavBar.vue'
import ToastContainer from './components/ToastContainer.vue'
import { useAuthStore } from './stores/auth'

const auth = useAuthStore()
</script>
