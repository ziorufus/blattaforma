<template>
  <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
    <div class="container-xxl">
      <router-link class="navbar-brand d-flex align-items-center" to="/">
        <img src="/blattaforma-logo.png" alt="Blattaforma" height="32" class="me-2" />
        Blattaforma
      </router-link>
      <button class="navbar-toggler" type="button" data-bs-toggle="collapse"
        data-bs-target="#navContent" aria-controls="navContent"
        aria-expanded="false" aria-label="Toggle navigation"
      >
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" id="navContent">
        <ul class="navbar-nav me-auto mb-2 mb-lg-0">
          <li class="nav-item">
            <router-link class="nav-link" to="/">Dashboard</router-link>
          </li>
          <li class="nav-item" v-for="m in auth.accessibleModules" :key="m.name">
            <router-link class="nav-link" :to="`/modules/${m.name}`">
              {{ m.label }}
            </router-link>
          </li>
          <li class="nav-item dropdown" v-if="auth.isAdmin">
            <a
              class="nav-link dropdown-toggle"
              href="#"
              role="button"
              data-bs-toggle="dropdown"
              aria-expanded="false"
            >
              Amministrazione
            </a>
            <ul class="dropdown-menu">
              <li>
                <router-link class="dropdown-item" to="/admin/users">
                  Utenti
                </router-link>
              </li>
              <li>
                <router-link class="dropdown-item" to="/admin/groups">
                  Gruppi
                </router-link>
              </li>
              <li>
                <router-link class="dropdown-item" to="/admin/modules">
                  Moduli
                </router-link>
              </li>
            </ul>
          </li>
        </ul>
        <ul class="navbar-nav">
          <li class="nav-item dropdown">
            <a
              class="nav-link dropdown-toggle d-flex align-items-center"
              href="#"
              role="button"
              data-bs-toggle="dropdown"
              aria-expanded="false"
            >
              <img
                v-if="auth.user?.picture"
                :src="auth.user.picture"
                class="rounded-circle me-2"
                width="24"
                height="24"
                referrerpolicy="no-referrer"
              />
              {{ auth.user?.name || auth.user?.email }}
              <span v-if="auth.isAdmin" class="badge bg-warning text-dark ms-2">admin</span>
            </a>
            <ul class="dropdown-menu dropdown-menu-end">
              <li><button class="dropdown-item" type="button" @click="doLogout">Esci</button></li>
            </ul>
          </li>
        </ul>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

function doLogout() {
  auth.logout()
  router.push({ name: 'login' })
}
</script>

<style scoped>
.bg-dark {
  background-color: #020A10 !important;
}
</style>