<template>
  <nav class="navbar navbar-expand-lg navbar-dark bg-dark">
    <div class="container-fluid">
      <router-link class="navbar-brand" to="/" @click="closeAll">Blattaforma</router-link>
      <button class="navbar-toggler" type="button" @click="navOpen = !navOpen">
        <span class="navbar-toggler-icon"></span>
      </button>
      <div class="collapse navbar-collapse" :class="{ show: navOpen }" id="navContent">
        <ul class="navbar-nav me-auto mb-2 mb-lg-0">
          <li class="nav-item">
            <router-link class="nav-link" to="/" @click="closeAll">Dashboard</router-link>
          </li>
          <li class="nav-item" v-for="m in auth.accessibleModules" :key="m.name">
            <router-link class="nav-link" :to="`/modules/${m.name}`" @click="closeAll">
              {{ m.label }}
            </router-link>
          </li>
          <li class="nav-item dropdown" v-if="auth.isAdmin" ref="adminDropdownEl">
            <a
              class="nav-link dropdown-toggle"
              href="#"
              role="button"
              @click.prevent="toggleDropdown('admin')"
            >
              Amministrazione
            </a>
            <ul class="dropdown-menu" :class="{ show: adminOpen }">
              <li>
                <router-link class="dropdown-item" to="/admin/users" @click="closeAll">
                  Utenti
                </router-link>
              </li>
              <li>
                <router-link class="dropdown-item" to="/admin/groups" @click="closeAll">
                  Gruppi
                </router-link>
              </li>
              <li>
                <router-link class="dropdown-item" to="/admin/modules" @click="closeAll">
                  Moduli
                </router-link>
              </li>
            </ul>
          </li>
        </ul>
        <ul class="navbar-nav">
          <li class="nav-item dropdown" ref="userDropdownEl">
            <a
              class="nav-link dropdown-toggle d-flex align-items-center"
              href="#"
              role="button"
              @click.prevent="toggleDropdown('user')"
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
            <ul class="dropdown-menu dropdown-menu-end" :class="{ show: userOpen }">
              <li><button class="dropdown-item" type="button" @click="doLogout">Esci</button></li>
            </ul>
          </li>
        </ul>
      </div>
    </div>
  </nav>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const router = useRouter()

// Bootstrap's own data-bs-toggle/data-bs-dismiss auto-wiring depends on
// document-level listeners registered as a side effect of importing its JS
// bundle. That import doesn't reliably survive the Vite/Rollup production
// build, so dropdowns/collapse are driven here with plain Vue state instead
// of relying on Bootstrap's JS at all.
const navOpen = ref(false)
const adminOpen = ref(false)
const userOpen = ref(false)

const adminDropdownEl = ref(null)
const userDropdownEl = ref(null)

function toggleDropdown(which) {
  if (which === 'admin') {
    adminOpen.value = !adminOpen.value
    userOpen.value = false
  } else {
    userOpen.value = !userOpen.value
    adminOpen.value = false
  }
}

function closeAll() {
  adminOpen.value = false
  userOpen.value = false
  navOpen.value = false
}

function onDocumentClick(event) {
  if (adminOpen.value && adminDropdownEl.value && !adminDropdownEl.value.contains(event.target)) {
    adminOpen.value = false
  }
  if (userOpen.value && userDropdownEl.value && !userDropdownEl.value.contains(event.target)) {
    userOpen.value = false
  }
}

onMounted(() => document.addEventListener('click', onDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', onDocumentClick))

function doLogout() {
  closeAll()
  auth.logout()
  router.push({ name: 'login' })
}
</script>
