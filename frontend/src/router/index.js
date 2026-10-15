import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '../stores/auth'
import { useConfigStore } from '../stores/config'

import Login from '../views/Login.vue'
import LoginCallback from '../views/LoginCallback.vue'
import Dashboard from '../views/Dashboard.vue'
import Forbidden from '../views/Forbidden.vue'
import NotFound from '../views/NotFound.vue'
import AdminUsers from '../views/admin/Users.vue'
import AdminGroups from '../views/admin/Groups.vue'
import AdminModules from '../views/admin/Modules.vue'
import AdminOptions from '../views/admin/Options.vue'

// Auto-discover feature modules dropped under src/modules/<name>/index.js.
// Each manifest exports { name, routes: [{ path, name, component }] }.
const moduleManifests = import.meta.glob('../modules/*/index.js', { eager: true })

const moduleRoutes = []
for (const path in moduleManifests) {
  const manifest = moduleManifests[path].default
  for (const r of manifest.routes) {
    const fullPath = `/modules/${manifest.name}/${r.path}`.replace(/\/+$/, '')
    moduleRoutes.push({
      path: fullPath,
      name: `module-${manifest.name}-${r.name || r.path || 'index'}`,
      component: r.component,
      meta: { requiresAuth: true, requiresModule: manifest.name, module: manifest.name },
    })
  }
}

// Auto-discover unauthenticated pages under src/modules/<name>/public.js
// (same manifest shape as index.js). Anything exported there is reachable
// without login, so a module opts in explicitly by creating this file.
// Each route `name` must also be a key of the backend MODULE_PUBLIC_PAGES,
// which gives admins an on/off switch for the page.
const publicManifests = import.meta.glob('../modules/*/public.js', { eager: true })

const publicRoutes = []
export const publicPages = []
for (const path in publicManifests) {
  const manifest = publicManifests[path].default
  for (const r of manifest.routes) {
    const fullPath = `/public/${manifest.name}/${r.path}`.replace(/\/+$/, '')
    const page = r.name || r.path || 'index'
    publicRoutes.push({
      path: fullPath,
      name: `public-${manifest.name}-${page}`,
      component: r.component,
      meta: { requiresAuth: false, module: manifest.name, publicPage: page },
    })
    publicPages.push({ path: fullPath, label: r.label || manifest.name, module: manifest.name, page })
  }
}

const routes = [
  { path: '/login', name: 'login', component: Login, meta: { requiresAuth: false } },
  {
    path: '/login/callback',
    name: 'login-callback',
    component: LoginCallback,
    meta: { requiresAuth: false },
  },
  { path: '/', name: 'dashboard', component: Dashboard, meta: { requiresAuth: true } },
  {
    path: '/admin/users',
    name: 'admin-users',
    component: AdminUsers,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/groups',
    name: 'admin-groups',
    component: AdminGroups,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/modules',
    name: 'admin-modules',
    component: AdminModules,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  {
    path: '/admin/options',
    name: 'admin-options',
    component: AdminOptions,
    meta: { requiresAuth: true, requiresAdmin: true },
  },
  ...moduleRoutes,
  ...publicRoutes,
  { path: '/403', name: 'forbidden', component: Forbidden, meta: { requiresAuth: true } },
  { path: '/:pathMatch(.*)*', name: 'not-found', component: NotFound, meta: { requiresAuth: true } },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to) => {
  const auth = useAuthStore()

  if (to.name === 'login' && auth.isAuthenticated && !to.query.error) {
    return { path: '/' }
  }

  // Un modulo disattivato sparisce per tutti, admin compresi, pagine
  // pubbliche incluse (il backend risponde 404 alle sue API).
  const config = useConfigStore()
  if (
    to.meta.module &&
    (!config.isModuleEnabled(to.meta.module) ||
      (to.meta.publicPage && !config.isPublicPageEnabled(to.meta.module, to.meta.publicPage)))
  ) {
    return { name: 'not-found', params: { pathMatch: to.path.substring(1).split('/') } }
  }

  if (to.meta.requiresAuth === false) {
    return true
  }

  if (!auth.isAuthenticated) {
    return { name: 'login', query: { redirect: to.fullPath } }
  }

  if (to.meta.requiresAdmin && !auth.isAdmin) {
    return { name: 'forbidden' }
  }

  if (to.meta.requiresModule && !auth.isAdmin && !auth.hasModuleAccess(to.meta.requiresModule)) {
    return { name: 'forbidden' }
  }

  return true
})

export default router
