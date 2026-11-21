import { Link } from 'react-router-dom'
import { Activity, AlertTriangle, ArrowRight, ArrowUpRight, Bot, CheckCircle2, Circle, Clock3, FilePlus2, Plus, ShieldCheck, UploadCloud } from 'lucide-react'
import { agents, initialRisks, taskGroups } from '../../data/demo'
import { useWorkspace } from '../../hooks/useWorkspace'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Card, SectionHeader } from '../ui/Card'
import { ProgressBar } from '../ui/ProgressBar'

export function TaskProgressPanel() {
  const { activeProject } = useWorkspace()
  const radius = 39
  const circumference = 2 * Math.PI * radius
  return (
    <Card className="h-full animate-fade-up" >
      <SectionHeader title="科研任务进度" description={`${activeProject.code} · 当前项目`} eyebrow="Milestones" />
      <div className="mb-5 flex items-center gap-5 rounded-xl border border-white/[.05] bg-canvas/40 p-4">
        <div className="relative h-24 w-24 shrink-0">
          <svg viewBox="0 0 96 96" className="h-24 w-24 -rotate-90"><circle cx="48" cy="48" r={radius} fill="none" stroke="rgba(255,255,255,.055)" strokeWidth="6" /><circle cx="48" cy="48" r={radius} fill="none" stroke="#8B5CF6" strokeWidth="6" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={circumference * (1 - activeProject.progress / 100)} className="transition-[stroke-dashoffset] duration-700" /></svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center"><span className="metric-number font-display text-xl font-semibold text-ink">{activeProject.progress}<span className="text-xs text-muted">%</span></span><span className="mt-0.5 text-[9px] text-muted">总体完成</span></div>
        </div>
        <div><Badge tone="green" dot>节奏正常</Badge><p className="mt-2 text-xs leading-5 text-[#B0BCD0]">本周已完成 <span className="font-medium text-ink">9 项</span> 研究任务</p><p className="mt-1 font-mono text-[9px] text-success">+8% FROM LAST WEEK</p></div>
      </div>
      <div className="space-y-4">{taskGroups.map((task) => <div key={task.label}><div className="mb-2 flex items-center text-[11px]"><span className="text-[#AAB6CA]">{task.label}</span><span className="ml-auto font-mono text-[9px] text-muted">{task.detail}</span><span className="ml-2 w-8 text-right font-mono text-[10px] text-ink">{task.value}%</span></div><ProgressBar value={task.value} color={task.color} /></div>)}</div>
      <Link to="/protocols" className="mt-5 flex items-center justify-center gap-2 border-t border-white/[.055] pt-4 text-[11px] text-muted transition hover:text-primary">查看实验里程碑<ArrowRight size={13} /></Link>
    </Card>
  )
}

export function AgentStatusPanel() {
  return (
    <Card className="h-full animate-fade-up">
      <SectionHeader title="Agent 运行状态" description="3 个科研智能体 · 2 个正在执行" eyebrow="Agent mesh" action={<span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary"><Bot size={16} /></span>} />
      <div className="space-y-2.5">{agents.map((agent) => <div key={agent.name} className="rounded-xl border border-white/[.05] bg-canvas/35 p-3.5"><div className="flex items-center gap-2.5"><span className={`h-2 w-2 rounded-full ${agent.state === '运行中' ? 'animate-pulse-soft bg-success' : 'bg-[#536079]'}`} /><span className="font-display text-xs font-medium text-ink">{agent.name}</span><Badge tone={agent.state === '运行中' ? 'green' : 'neutral'} className="ml-auto">{agent.state}</Badge></div><p className="mt-2 truncate text-[11px] text-muted">{agent.task}</p>{agent.state === '运行中' && <div className="mt-2.5 flex items-center gap-2"><ProgressBar value={agent.progress} color="cyan" className="h-1 flex-1" /><span className="font-mono text-[9px] text-accent">{agent.progress}%</span></div>}</div>)}</div>
      <div className="mt-4 flex items-center gap-2 text-[10px] text-muted"><Activity size={13} className="text-success" /><span>任务队列正常</span><span className="ml-auto font-mono text-[9px]">LATENCY 42ms</span></div>
    </Card>
  )
}

export function RiskPanel() {
  const pendingRisks = initialRisks.filter((risk) => risk.status === '待处理').slice(0, 3)
  return (
    <Card className="h-full animate-fade-up">
      <SectionHeader title="风险提醒" description="需要关注的复现偏差" eyebrow="Risk radar" action={<Link to="/guardian" className="text-muted transition hover:text-primary" aria-label="进入数据审计"><ArrowUpRight size={17} /></Link>} />
      <div className="space-y-3">{pendingRisks.map((risk) => <Link to="/guardian" key={risk.id} className="group flex gap-3 rounded-xl border border-white/[.05] bg-canvas/35 p-3.5 transition hover:border-warning/20"><span className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg ${risk.level === 'high' ? 'bg-danger/10 text-danger' : 'bg-warning/10 text-warning'}`}><AlertTriangle size={14} /></span><span className="min-w-0"><span className="block truncate text-[11px] font-medium text-[#C2CCDC] group-hover:text-ink">{risk.title}</span><span className="mt-1 block truncate font-mono text-[9px] text-muted">{risk.source}</span></span></Link>)}</div>
      <Link to="/guardian" className="mt-4 flex items-center justify-between border-t border-white/[.055] pt-4 text-[10px] text-muted hover:text-ink"><span className="flex items-center gap-1.5"><ShieldCheck size={13} className="text-success" />上次审计：今天 14:20</span><ArrowRight size={13} /></Link>
    </Card>
  )
}

export function QuickStartPanel() {
  return (
    <Card className="relative h-full animate-fade-up overflow-hidden border-primary/15 bg-[#151A30]">
      <div className="absolute -right-8 -top-8 h-32 w-32 rounded-full border border-primary/10" /><div className="absolute -right-3 -top-3 h-16 w-16 rounded-full border border-primary/10" />
      <p className="font-mono text-[9px] uppercase tracking-[.18em] text-primary">New reproduction</p><h2 className="mt-2 font-display text-lg font-semibold tracking-[-.025em] text-ink">让下一个结论<br />经得起复现。</h2><p className="mt-2 text-[11px] leading-5 text-muted">从一篇论文开始，构建可信的实验证据链。</p>
      <Link to="/workflows"><Button variant="primary" className="mt-5 w-full" icon={<Plus size={15} />}>启动复现工作流</Button></Link>
      <div className="mt-4 grid grid-cols-2 gap-2"><Link to="/papers" className="flex flex-col items-center gap-2 rounded-xl border border-white/[.06] bg-canvas/30 py-3 text-[10px] text-muted transition hover:border-accent/20 hover:text-accent"><UploadCloud size={16} />导入论文</Link><Link to="/reports" className="flex flex-col items-center gap-2 rounded-xl border border-white/[.06] bg-canvas/30 py-3 text-[10px] text-muted transition hover:border-primary/20 hover:text-primary"><FilePlus2 size={16} />查看已定稿报告</Link></div>
      <div className="mt-4 flex items-center justify-center gap-4 text-[9px] text-[#65738D]"><span className="flex items-center gap-1"><CheckCircle2 size={10} />结构化</span><span className="flex items-center gap-1"><Clock3 size={10} />可追溯</span><span className="flex items-center gap-1"><Circle size={8} />可验证</span></div>
    </Card>
  )
}
