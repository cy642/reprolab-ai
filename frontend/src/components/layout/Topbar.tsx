import { useLocation } from 'react-router-dom'
import { Check, ChevronDown, Cloud, CloudOff, LoaderCircle, Menu, RefreshCw, Search, Settings } from 'lucide-react'
import { useState } from 'react'
import { navigationItems } from '../../data/navigation'
import { useWorkspace } from '../../hooks/useWorkspace'
import type { useHealth } from '../../hooks/useHealth'
import { Badge } from '../ui/Badge'

interface TopbarProps {
  health: ReturnType<typeof useHealth>
  onOpenMobile: () => void
  onOpenSearch: () => void
  onOpenProjects: () => void
  onOpenSettings: () => void
}

export function Topbar({ health, onOpenMobile, onOpenSearch, onOpenProjects, onOpenSettings }: TopbarProps) {
  const location = useLocation()
  const { activeProject } = useWorkspace()
  const [profileOpen, setProfileOpen] = useState(false)
  const page = navigationItems.find((item) => item.path === location.pathname) ?? navigationItems[0]
  const statusTone = activeProject.status === '已归档' ? 'neutral' : activeProject.status === '待验证' ? 'amber' : 'green'

  return (
    <header className="sticky top-0 z-30 flex h-[72px] items-center gap-4 border-b border-white/[.055] bg-canvas/85 px-4 backdrop-blur-xl sm:px-6 xl:px-8">
      <button onClick={onOpenMobile} className="rounded-lg p-2 text-muted hover:bg-white/5 hover:text-ink lg:hidden" aria-label="打开导航"><Menu size={20} /></button>
      <div className="min-w-0">
        <div className="flex items-center gap-2 text-[10px] text-muted">
          <span className="hidden sm:inline">Workspace</span><span className="hidden text-[#46536C] sm:inline">/</span>
          <span className="font-mono tracking-wide text-primary">{page.english}</span>
        </div>
        <h2 className="mt-0.5 truncate text-[13px] font-medium text-ink">{page.label}</h2>
      </div>

      <button onClick={onOpenProjects} className="ml-4 hidden min-w-0 items-center gap-2 rounded-lg border border-white/[.06] bg-white/[.025] px-3 py-2 transition hover:border-white/[.12] md:flex">
        <span className="max-w-40 truncate text-[11px] text-muted">{activeProject.name}</span>
        <Badge tone={statusTone} dot>{activeProject.status}</Badge>
        <ChevronDown size={12} className="text-muted" />
      </button>

      <div className="ml-auto flex items-center gap-2">
        <button
          onClick={() => void health.refresh()}
          title={health.error ?? (health.data ? `${health.data.service} v${health.data.version}` : '检查后端连接')}
          className="hidden h-9 items-center gap-2 rounded-lg border border-white/[.06] bg-white/[.02] px-3 text-[11px] text-muted transition hover:border-white/[.12] hover:text-ink sm:flex"
        >
          {health.status === 'checking' ? <LoaderCircle size={14} className="animate-spin text-primary" /> : health.status === 'online' ? <Cloud size={14} className="text-success" /> : <CloudOff size={14} className="text-danger" />}
          <span>{health.status === 'checking' ? '连接中' : health.status === 'online' ? `API v${health.data?.version}` : 'API 离线'}</span>
          <span className={`h-1.5 w-1.5 rounded-full ${health.status === 'online' ? 'bg-success' : health.status === 'offline' ? 'bg-danger' : 'animate-pulse-soft bg-primary'}`} />
          <RefreshCw size={11} className="ml-0.5 opacity-50" />
        </button>
        <button onClick={onOpenSearch} className="flex h-9 items-center gap-2 rounded-lg border border-white/[.06] bg-white/[.02] px-2.5 text-muted transition hover:border-white/[.12] hover:text-ink" aria-label="全局搜索">
          <Search size={16} /><span className="hidden font-mono text-[9px] text-[#64718A] xl:inline">CTRL K</span>
        </button>
        <div className="relative ml-1">
          <button onClick={() => setProfileOpen((open) => !open)} className="flex items-center gap-2 rounded-xl p-1.5 transition hover:bg-white/[.035]" aria-expanded={profileOpen}>
            <span className="flex h-8 w-8 items-center justify-center rounded-lg border border-primary/25 bg-[#292044] font-display text-xs font-semibold text-[#C8B5FA]">LY</span>
            <span className="hidden text-left xl:block"><span className="block text-[11px] font-medium text-ink">林研</span><span className="block text-[9px] text-muted">研究生工作区</span></span>
            <ChevronDown size={12} className="hidden text-muted xl:block" />
          </button>
          {profileOpen && (
            <>
              <button className="fixed inset-0 z-10 cursor-default" onClick={() => setProfileOpen(false)} aria-label="关闭用户菜单" />
              <div className="absolute right-0 top-12 z-20 w-52 animate-fade-up rounded-xl border border-white/10 bg-elevated p-2 shadow-lift">
                <div className="border-b border-white/[.06] px-3 py-2.5"><p className="text-xs font-medium text-ink">林研</p><p className="mt-1 text-[10px] text-muted">linyan@reprolab.demo</p></div>
                <button onClick={() => { setProfileOpen(false); onOpenProjects() }} className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-xs text-muted hover:bg-white/5 hover:text-ink"><Check size={14} />切换当前项目</button>
                <button onClick={() => { setProfileOpen(false); onOpenSettings() }} className="flex w-full items-center gap-2 rounded-lg px-3 py-2.5 text-left text-xs text-muted hover:bg-white/5 hover:text-ink"><Settings size={14} />偏好设置</button>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  )
}
