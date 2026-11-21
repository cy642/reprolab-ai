import type { HTMLAttributes, ReactNode } from 'react'
import { cn } from '../../lib/utils'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  padded?: boolean
}

export function Card({ children, className, padded = true, ...props }: CardProps) {
  return (
    <div
      className={cn(
        'rounded-2xl border border-white/[.065] bg-surface shadow-card',
        padded && 'p-5',
        className,
      )}
      {...props}
    >
      {children}
    </div>
  )
}

interface SectionHeaderProps {
  title: string
  description?: string
  action?: ReactNode
  eyebrow?: string
}

export function SectionHeader({ title, description, action, eyebrow }: SectionHeaderProps) {
  return (
    <div className="mb-5 flex items-start justify-between gap-4">
      <div>
        {eyebrow && <p className="mb-1.5 font-mono text-[10px] uppercase tracking-[.18em] text-primary">{eyebrow}</p>}
        <h2 className="font-display text-[15px] font-semibold tracking-[-.01em] text-ink">{title}</h2>
        {description && <p className="mt-1 text-xs leading-5 text-muted">{description}</p>}
      </div>
      {action}
    </div>
  )
}
