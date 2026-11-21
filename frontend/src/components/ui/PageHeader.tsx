import type { ReactNode } from 'react'
import { DemoBadge } from './Badge'

interface PageHeaderProps {
  eyebrow: string
  title: string
  description: string
  actions?: ReactNode
  showDemo?: boolean
}

export function PageHeader({ eyebrow, title, description, actions, showDemo = true }: PageHeaderProps) {
  return (
    <header className="mb-6 flex flex-col justify-between gap-5 lg:flex-row lg:items-end">
      <div className="max-w-3xl animate-fade-up">
        <div className="mb-2.5 flex items-center gap-3">
          <p className="font-mono text-[10px] font-medium uppercase tracking-[.2em] text-primary">{eyebrow}</p>
          {showDemo && <DemoBadge />}
        </div>
        <h1 className="font-display text-[26px] font-semibold tracking-[-.035em] text-ink sm:text-[30px]">{title}</h1>
        <p className="mt-2 max-w-2xl text-[13px] leading-6 text-muted">{description}</p>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2.5">{actions}</div>}
    </header>
  )
}
