import { NavLink } from 'react-router-dom'
import { ChevronRight, FolderKanban, PanelLeftClose, PanelLeftOpen, Plus, Settings, X } from 'lucide-react'
import { navigationItems } from '../../data/navigation'
import { useWorkspace } from '../../hooks/useWorkspace'
import { cn } from '../../lib/utils'
import { ProgressBar } from '../ui/ProgressBar'

interface SidebarProps {
  collapsed: boolean
  mobileOpen: boolean
  onCollapse: () => void
  onCloseMobile: () => void
  onOpenProjects: () => void
  onCreateProject: () => void
  onOpenSettings: () => void
}

export function Sidebar({ collapsed, mobileOpen, onCollapse, onCloseMobile, onOpenProjects, onCreateProject, onOpenSettings }: SidebarProps) {
  const { activeProject } = useWorkspace()
  const labelVisibility = collapsed ? 'lg:hidden' : ''

  return (
    <aside className={cn(
      'fixed inset-y-0 left-0 z-50 flex w-[252px] -translate-x-full flex-col border-r border-white/[.06] bg-[#0D1425]/95 backdrop-blur-xl transition-[transform,width] duration-300 lg:translate-x-0',
      mobileOpen && 'translate-x-0',
      collapsed ? 'lg:w-[84px]' : 'lg:w-[252px]',
    )}>
      <div className={cn('flex h-[72px] shrink-0 items-center gap-3 border-b border-white/[.055] px-5', collapsed && 'lg:justify-center lg:px-3')}>
        <NavLink to="/" onClick={onCloseMobile} className="flex min-w-0 items-center gap-3">
          <img src={`${import.meta.env.BASE_URL}logo.svg`} alt="ReproLab AI" className="h-9 w-9 shrink-0" />
          <div className={cn('min-w-0', labelVisibility)}>
            <div className="font-display text-[16px] font-bold tracking-[-.035em] text-ink">ReproLab <span className="text-primary">AI</span></div>
            <p className="mt-0.5 text-[9px] tracking-[.2em] text-muted">研途复现官</p>
          </div>
        </NavLink>
        <button onClick={onCloseMobile} className="ml-auto rounded-lg p-2 text-muted hover:bg-white/5 lg:hidden" aria-label="关闭导航"><X size={18} /></button>
      </div>

      <div className="custom-scrollbar flex-1 overflow-y-auto px-3 py-5">
        <p className={cn('mb-2.5 px-3 font-mono text-[9px] uppercase tracking-[.18em] text-[#64718A]', labelVisibility)}>Research workspace</p>
        <nav className="space-y-1" aria-label="主导航">
          {navigationItems.map((item) => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.path === '/'}
              onClick={onCloseMobile}
              title={collapsed ? item.english : undefined}
              className={({ isActive }) => cn(
                'group relative flex h-11 items-center gap-3 rounded-xl border px-3 text-[13px] transition-all duration-200',
                isActive
                  ? 'border-primary/20 bg-primary/[.11] text-[#C8B8FA]'
                  : 'border-transparent text-muted hover:border-white/[.04] hover:bg-white/[.035] hover:text-ink',
                collapsed && 'lg:justify-center lg:px-0',
              )}
            >
              <item.icon size={18} strokeWidth={1.8} className="shrink-0" />
              <span className={cn('truncate', labelVisibility)}>{item.english}</span>
              <span className={cn('ml-auto h-1.5 w-1.5 rounded-full bg-current opacity-0 group-[.active]:opacity-100', labelVisibility)} />
            </NavLink>
          ))}
        </nav>

        <div className="my-5 h-px bg-white/[.055]" />
        <p className={cn('mb-2.5 px-3 font-mono text-[9px] uppercase tracking-[.18em] text-[#64718A]', labelVisibility)}>Current research</p>
        <button onClick={onOpenProjects} title={collapsed ? activeProject.name : undefined} className={cn('w-full rounded-xl border border-white/[.06] bg-white/[.025] p-3 text-left transition hover:border-primary/25 hover:bg-primary/[.05]', collapsed && 'lg:flex lg:justify-center lg:p-2.5')}>
          <div className={cn('flex items-center gap-2.5', collapsed && 'lg:hidden')}>
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary"><FolderKanban size={16} /></span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium text-ink">{activeProject.name}</span>
              <span className="mt-0.5 block font-mono text-[9px] text-muted">{activeProject.code} · {activeProject.progress}%</span>
            </span>
            <ChevronRight size={14} className="text-muted" />
          </div>
          <FolderKanban size={18} className={cn('hidden text-primary', collapsed && 'lg:block')} />
          <ProgressBar value={activeProject.progress} className={cn('mt-3 h-1', labelVisibility)} />
        </button>
        <button onClick={onCreateProject} className={cn('mt-2 flex h-10 w-full items-center gap-3 rounded-xl px-3 text-xs text-muted transition hover:bg-white/[.035] hover:text-ink', collapsed && 'lg:justify-center lg:px-0')} title="新建科研项目">
          <Plus size={17} /><span className={labelVisibility}>新建科研项目</span>
        </button>
      </div>

      <div className="shrink-0 border-t border-white/[.055] p-3">
        <button onClick={onOpenSettings} className={cn('flex h-10 w-full items-center gap-3 rounded-xl px-3 text-xs text-muted transition hover:bg-white/[.035] hover:text-ink', collapsed && 'lg:justify-center lg:px-0')}>
          <Settings size={17} /><span className={labelVisibility}>工作区设置</span>
        </button>
        <button onClick={onCollapse} className="mt-1 hidden h-9 w-full items-center gap-3 rounded-xl px-3 text-[11px] text-[#64718A] transition hover:bg-white/[.035] hover:text-muted lg:flex" title={collapsed ? '展开侧栏' : '收起侧栏'}>
          {collapsed ? <PanelLeftOpen size={17} className="mx-auto" /> : <><PanelLeftClose size={17} /><span>收起导航</span><span className="ml-auto font-mono text-[9px]">⌘ B</span></>}
        </button>
      </div>
    </aside>
  )
}
