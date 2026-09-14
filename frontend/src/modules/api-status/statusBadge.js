export function statusBadgeClass(status) {
  if (status === 'up') return 'text-bg-success'
  if (status === 'down') return 'text-bg-danger'
  return 'text-bg-secondary'
}

export function statusLabel(status) {
  if (status === 'up') return 'Attiva'
  if (status === 'down') return 'Non raggiungibile'
  return 'In attesa'
}

export function formatDateTime(value) {
  if (!value) return 'Mai controllata'
  return new Date(value).toLocaleString('it-IT')
}
