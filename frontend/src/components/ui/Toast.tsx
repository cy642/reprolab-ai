import { useEffect } from 'react'
import { AlertTriangle, CheckCircle2, Info, X } from 'lucide-react'

export type ToastTone = 'success' | 'error' | 'info'

const toneStyles: Record<ToastTone, { border: string; icon: typeof CheckCircle2; color: string }> = {
  success: { border: 'border-success/20', icon: CheckCircle2, color: 'text-success' },
  error: { border: 'border-danger/25', icon: AlertTriangle, color: 'text-danger' },
  info: { border: 'border-accent/20', icon: Info, color: 'text-accent' },
}

export function Toast({ message, onClose, tone = 'success' }: {
  message: string
  onClose: () => void
  tone?: ToastTone
}) {
  useEffect(() => {
    const timer = window.setTimeout(onClose, 3600)
    return () => window.clearTimeout(timer)
  }, [message, onClose])

  const style = toneStyles[tone]
  const Icon = style.icon

  return (
    <div className={`fixed bottom-6 right-6 z-[120] flex max-w-sm animate-fade-up items-center gap-3 rounded-xl border ${style.border} bg-[#142330] px-4 py-3 text-sm text-ink shadow-lift`} role="status">
      <Icon size={18} className={`shrink-0 ${style.color}`} />
      <span className="leading-5">{message}</span>
      <button onClick={onClose} className="ml-2 text-muted hover:text-ink" aria-label="关闭提示"><X size={15} /></button>
    </div>
  )
}
