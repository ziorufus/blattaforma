<template>
  <div>
    <h1 class="mb-4">Benvenuto, {{ auth.user?.name || auth.user?.email }}</h1>

    <div v-if="auth.accessibleModules.length === 0" class="alert alert-info">
      Non hai ancora accesso a nessun modulo. Contatta un amministratore.
    </div>

    <div class="row g-3">
      <div class="col-md-4" v-for="m in auth.accessibleModules" :key="m.name">
        <router-link :to="`/modules/${m.name}`" class="text-decoration-none text-body">
          <div class="card h-100 shadow-sm">
            <div class="card-body">
              <h5 class="card-title">{{ m.label }}</h5>
              <p class="card-text text-muted mb-0">Ruoli: {{ m.granted_roles.join(', ') }}</p>
            </div>
          </div>
        </router-link>
      </div>
    </div>
  </div>
</template>

<script setup>
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
</script>
