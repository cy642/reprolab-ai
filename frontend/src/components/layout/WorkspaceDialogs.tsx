import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ArrowUpRight, Check, FolderKanban, Plus, Search } from 'lucide-react'
import { navigationItems } from '../../data/navigation'
import { useWorkspace } from '../../hooks/useWorkspace'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { ProgressBar } from '../ui/ProgressBar'

export function ProjectSwitcherModal({ open, onClose, onCreate }: { open: boolean; onClose: () => void; onCreate: () => void }) {
  const { projects, activeProject, selectProject } = useWorkspace()
  return (
    <Modal open={open} onClose={onClose} title="科研项目" description={`${projects.length} 个最近项目 · 选择后切换当前工作上下文`} className="max-w-2xl">
      <div className="space-y-2.5">
        {projects.map((project) => (
          <button key={project.id} onClick={() => { selectProject(project.id); onClose() }} className={`w-full rounded-xl border p-4 text-left transition ${project.id === activeProject.id ? 'border-primary/30 bg-primary/[.07]' : 'border-white/[.06] bg-canvas/35 hover:border-white/[.13]'}`}>
            <div className="flex items-center gap-3">
              <span className="font-mono text-[10px] text-primary">{project.code}</span>
              <span className="truncate text-sm font-medium text-ink">{project.name}</span>
              {project.id === activeProject.id ? <Badge tone="violet"><Check size={11} />当前项目</Badge> : <Badge>{project.status}</Badge>}
              <span className="ml-auto font-mono text-xs text-muted">{project.progress}%</span>
            </div>
            <ProgressBar value={project.progress} className="mt-3" />
          </button>
        ))}
      </div>
      <Button onClick={() => { onClose(); onCreate() }} className="mt-5 w-full border-dashed" icon={<Plus size={15} />}>创建新的科研项目</Button>
    </Modal>
  )
}

export function SearchModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [query, setQuery] = useState('')
  const { projects, selectProject } = useWorkspace()
  const navigate = useNavigate()
  const normalizedQuery = query.trim().toLowerCase()
  const pages = navigationItems.filter((item) => `${item.label} ${item.english}`.toLowerCase().includes(normalizedQuery))
  const matchedProjects = projects.filter((project) => `${project.name} ${project.code}`.toLowerCase().includes(normalizedQuery))
  const hasResults = pages.length + matchedProjects.length > 0

  const go = (path: string) => { navigate(path); setQuery(''); onClose() }
  return (
    <Modal open={open} onClose={onClose} title="全局检索" description="跳转功能模块，或定位并切换科研项目。" className="max-w-xl">
      <div className="relative mb-5"><Search size={17} className="absolute left-3.5 top-3.5 text-muted" /><input autoFocus value={query} onChange={(event) => setQuery(event.target.value)} className="field h-12 pl-11" placeholder="搜索页面、项目名称或编号…" /></div>
      <div className="custom-scrollbar max-h-[45vh] space-y-5 overflow-y-auto">
        {pages.length > 0 && <section><p className="mb-2 font-mono text-[9px] uppercase tracking-[.16em] text-muted">Modules</p><div className="space-y-1">{pages.map((item) => <button key={item.path} onClick={() => go(item.path)} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-white/[.04]"><item.icon size={17} className="text-primary" /><span className="text-xs text-ink">{item.english}</span><span className="text-[10px] text-muted">{item.label}</span><ArrowUpRight size={14} className="ml-auto text-muted" /></button>)}</div></section>}
        {matchedProjects.length > 0 && <section><p className="mb-2 font-mono text-[9px] uppercase tracking-[.16em] text-muted">Projects</p><div className="space-y-1">{matchedProjects.map((project) => <button key={project.id} onClick={() => { selectProject(project.id); go('/') }} className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left hover:bg-white/[.04]"><FolderKanban size={17} className="text-accent" /><span className="truncate text-xs text-ink">{project.name}</span><span className="ml-auto font-mono text-[10px] text-muted">{project.code}</span></button>)}</div></section>}
        {!hasResults && <div className="py-10 text-center"><Search size={24} className="mx-auto text-[#4E5C76]" /><p className="mt-3 text-xs text-muted">没有找到“{query}”相关内容</p></div>}
      </div>
    </Modal>
  )
}

export function SettingsModal({ open, onClose, collapsed, onCollapsedChange, motionEnabled, onMotionChange, onSave }: {
  open: boolean
  onClose: () => void
  collapsed: boolean
  onCollapsedChange: (value: boolean) => void
  motionEnabled: boolean
  onMotionChange: (value: boolean) => void
  onSave: () => void
}) {
  return (
    <Modal open={open} onClose={onClose} title="工作区设置" description="调整本地工作台的显示与交互偏好。">
      <div className="divide-y divide-white/[.06]">
        <SettingRow title="紧凑侧边导航" description="桌面端仅显示模块图标，扩大研究内容区域。" value={collapsed} onChange={onCollapsedChange} />
        <SettingRow title="界面轻量动效" description="控制页面进入、状态变化与弹窗过渡动画。" value={motionEnabled} onChange={onMotionChange} />
      </div>
      <div className="mt-5 rounded-xl border border-accent/10 bg-accent/[.035] p-4"><p className="text-xs font-medium text-accent">演示工作区</p><p className="mt-1.5 text-[11px] leading-5 text-muted">当前版本仅使用本地演示数据，设置不会上传至外部服务。</p></div>
      <div className="mt-6 flex justify-end"><Button variant="primary" onClick={() => { onSave(); onClose() }}>保存偏好</Button></div>
    </Modal>
  )
}

function SettingRow({ title, description, value, onChange }: { title: string; description: string; value: boolean; onChange: (value: boolean) => void }) {
  return (
    <div className="flex items-center gap-5 py-5 first:pt-0 last:pb-0"><div><p className="text-xs font-medium text-ink">{title}</p><p className="mt-1.5 text-[11px] leading-5 text-muted">{description}</p></div><button onClick={() => onChange(!value)} aria-pressed={value} aria-label={title} className={`relative ml-auto h-6 w-11 shrink-0 rounded-full border transition ${value ? 'border-primary/50 bg-primary' : 'border-line bg-elevated'}`}><span className={`absolute top-[3px] h-4 w-4 rounded-full bg-white transition-transform ${value ? 'translate-x-[22px]' : 'translate-x-[3px]'}`} /></button></div>
  )
}
