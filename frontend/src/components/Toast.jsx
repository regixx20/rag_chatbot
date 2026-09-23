import { useEffect } from 'react'
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react'

const ICONS = { success: CheckCircle2, error: AlertCircle, info: Info }

export function Toast({ toast, onDismiss }) {
  useEffect(() => {
    if (!toast) return undefined
    const timer = setTimeout(onDismiss, toast.tone === 'error' ? 7000 : 4000)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- restart the timer only for a new toast
  }, [toast])

  if (!toast) return null
  const Icon = ICONS[toast.tone] ?? Info

  return (
    <div className={`toast toast-${toast.tone}`} role="status" key={toast.id}>
      <Icon size={17} />
      <span>{toast.text}</span>
      <button className="icon-button" onClick={onDismiss} aria-label="Fermer">
        <X size={15} />
      </button>
    </div>
  )
}
