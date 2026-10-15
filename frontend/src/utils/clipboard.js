import { useToastStore } from '../stores/toast'

// Copia il testo negli appunti mostrando un toast con l'esito; restituisce true se la copia è riuscita
export async function copyToClipboard(text) {
  const toast = useToastStore()
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      copyWithTextarea(text)
    }
  } catch (e) {
    toast.error('Impossibile copiare negli appunti')
    return false
  }
  toast.success('Valore copiato negli appunti')
  return true
}

function copyWithTextarea(text) {
  // Fallback per contesti non sicuri (HTTP), dove navigator.clipboard non è disponibile
  const ta = document.createElement('textarea')
  ta.value = text
  ta.style.position = 'fixed'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  try {
    if (!document.execCommand('copy')) throw new Error('Copia non riuscita')
  } finally {
    document.body.removeChild(ta)
  }
}
