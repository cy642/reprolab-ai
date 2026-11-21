import { cn } from '../../lib/utils'

export function ProgressBar({ value, color = 'violet', className }: {
  value: number
  color?: 'violet' | 'cyan' | 'green' | 'amber'
  className?: string
}) {
  const colors = {
    violet: 'bg-primary',
    cyan: 'bg-accent',
    green: 'bg-success',
    amber: 'bg-warning',
  }
  return (
    <div className={cn('h-1.5 overflow-hidden rounded-full bg-white/[.055]', className)} aria-label={`进度 ${value}%`}>
      <div className={cn('h-full rounded-full transition-[width] duration-500', colors[color])} style={{ width: `${Math.min(100, Math.max(0, value))}%` }} />
    </div>
  )
}
