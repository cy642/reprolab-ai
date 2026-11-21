import { useEffect, useId, type ReactNode } from 'react'
import { X } from 'lucide-react'
import { cn } from '../../lib/utils'

interface ModalProps {
  open: boolean
  onClose: () => void
  title: string
  description?: string
  children: ReactNode
  className?: string
}

export function Modal({ open, onClose, title, description, children, className }: ModalProps) {
  const titleId = useId()
  const hasCustomWidth = className?.split(/\s+/).some((name) => name.startsWith('max-w-'))
  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', handleKey)
    return () => {
      document.body.style.overflow = previousOverflow
      window.removeEventListener('keydown', handleKey)
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="fixed inset-0 z-[100] flex items-center justify-center p-4" role="dialog" aria-modal="true" aria-labelledby={titleId}>
      <button className="absolute inset-0 cursor-default bg-[#050914]/80 backdrop-blur-sm" onClick={onClose} aria-label="关闭弹窗" />
      <div className={cn('relative max-h-[90vh] w-full animate-fade-up overflow-y-auto rounded-2xl border border-white/10 bg-surface shadow-lift', !hasCustomWidth && 'max-w-lg', className)}>
        <div className="flex items-start justify-between gap-5 border-b border-white/[.06] px-6 py-5">
          <div>
            <h2 id={titleId} className="font-display text-lg font-semibold text-ink">{title}</h2>
            {description && <p className="mt-1 text-xs leading-5 text-muted">{description}</p>}
          </div>
          <button onClick={onClose} className="rounded-lg p-1.5 text-muted transition hover:bg-white/[.05] hover:text-ink" aria-label="关闭">
            <X size={18} />
          </button>
        </div>
        <div className="p-6">{children}</div>
      </div>
    </div>
  )
}
