<template>
  <div class="toast-container position-fixed bottom-0 end-0 p-3" style="z-index: 1080">
    <div
      v-for="t in toastStore.toasts"
      :key="t.id"
      :ref="(el) => registerToast(t.id, el)"
      class="toast align-items-center border-0"
      :class="`text-bg-${t.type}`"
      role="alert"
      aria-live="assertive"
      aria-atomic="true"
    >
      <div class="d-flex">
        <div class="toast-body">
          <i class="bi me-2" :class="t.type === 'success' ? 'bi-check-circle' : 'bi-exclamation-triangle'"></i>
          {{ t.message }}
        </div>
        <button
          type="button"
          class="btn-close btn-close-white me-2 m-auto"
          data-bs-dismiss="toast"
          aria-label="Chiudi"
        ></button>
      </div>
    </div>
  </div>
</template>

<script setup>
import { Toast } from 'bootstrap'
import { useToastStore } from '../stores/toast'

const toastStore = useToastStore()
const instances = new Map()

function registerToast(id, el) {
  if (!el || instances.has(id)) return
  const instance = new Toast(el, { delay: 5000 })
  instances.set(id, instance)
  el.addEventListener('hidden.bs.toast', () => {
    instances.delete(id)
    toastStore.dismiss(id)
  })
  instance.show()
}
</script>
