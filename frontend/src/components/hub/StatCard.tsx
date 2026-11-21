import { ArrowUpRight, type LucideIcon } from 'lucide-react'
import { Link } from 'react-router-dom'
import { cn } from '../../lib/utils'

export function StatCard({ label, value, note, icon: Icon, path, color, bars, delay = 0 }: {
  label: string
  value: number | string
  note: string
  icon: LucideIcon
  path: string
  color: 'violet' | 'cyan' | 'blue' | 'amber'
  bars: number[]
  delay?: number
}) {
  const palette = {
    violet: { icon: 'bg-primary/10 text-[#AA8DF8]', bar: 'bg-primary/60' },
    cyan: { icon: 'bg-accent/10 text-accent', bar: 'bg-accent/60' },
    blue: { icon: 'bg-blue-400/10 text-blue-300', bar: 'bg-blue-400/60' },
    amber: { icon: 'bg-warning/10 text-warning', bar: 'bg-warning/60' },
  }[color]
  return (
    <Link to={path} className="card-lift group relative animate-fade-up overflow-hidden rounded-2xl border border-white/[.065] bg-surface p-5 shadow-card" style={{ animationDelay: `${delay}ms` }}>
      <div className="flex items-start justify-between">
        <span className={cn('flex h-9 w-9 items-center justify-center rounded-xl', palette.icon)}><Icon size={18} strokeWidth={1.8} /></span>
        <ArrowUpRight size={15} className="text-[#4E5B73] transition group-hover:-translate-y-0.5 group-hover:translate-x-0.5 group-hover:text-muted" />
      </div>
      <div className="mt-5 flex items-end justify-between gap-4">
        <div><p className="metric-number font-display text-[30px] font-semibold leading-none tracking-[-.045em] text-ink">{value}</p><p className="mt-2 text-xs font-medium text-[#B2BDD0]">{label}</p></div>
        <div className="flex h-9 items-end gap-1" aria-hidden="true">{bars.map((height, index) => <span key={index} className={cn('w-1 rounded-sm opacity-70', palette.bar, index === bars.length - 1 && 'opacity-100')} style={{ height: `${height}%` }} />)}</div>
      </div>
      <p className="mt-3 border-t border-white/[.05] pt-3 font-mono text-[9px] tracking-wide text-muted">{note}</p>
    </Link>
  )
}
