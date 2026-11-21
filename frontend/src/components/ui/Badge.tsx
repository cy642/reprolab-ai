import type { ReactNode } from 'react'
import { cn } from '../../lib/utils'

export type BadgeTone = 'violet' | 'cyan' | 'green' | 'amber' | 'red' | 'neutral' | 'blue'

const tones: Record<BadgeTone, string> = {
  violet: 'border-primary/20 bg-primary/10 text-[#B9A0FA]',
  cyan: 'border-accent/20 bg-accent/10 text-accent',
  green: 'border-success/20 bg-success/10 text-success',
  amber: 'border-warning/20 bg-warning/10 text-warning',
  red: 'border-danger/20 bg-danger/10 text-danger',
  neutral: 'border-white/[.07] bg-white/[.035] text-muted',
  blue: 'border-blue-400/20 bg-blue-400/10 text-blue-300',
}

export function Badge({ children, tone = 'neutral', dot = false, className }: {
  children: ReactNode
  tone?: BadgeTone
  dot?: boolean
  className?: string
}) {
  return (
    <span className={cn('inline-flex items-center gap-1.5 rounded-md border px-2 py-1 text-[10px] font-medium leading-none', tones[tone], className)}>
      {dot && <span className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  )
}

export function DemoBadge() {
  return <Badge tone="neutral" className="font-mono tracking-wide">DEMO DATA</Badge>
}
