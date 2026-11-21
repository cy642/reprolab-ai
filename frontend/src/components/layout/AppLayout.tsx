import { Suspense, useCallback, useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { useHealth } from '../../hooks/useHealth'
import { HOSTED_DEMO } from '../../lib/api'
import { cn } from '../../lib/utils'
import { Toast } from '../ui/Toast'
import { CreateProjectModal } from './CreateProjectModal'
import { HostedDemoAccess } from './HostedDemoAccess'
import { Sidebar } from './Sidebar'
import { Topbar } from './Topbar'
import { ProjectSwitcherModal, SearchModal, SettingsModal } from './WorkspaceDialogs'

export interface LayoutOutletContext {
  openCreateProject: () => void
}

export function AppLayout() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [projectsOpen, setProjectsOpen] = useState(false)
  const [searchOpen, setSearchOpen] = useState(false)
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [motionEnabled, setMotionEnabled] = useState(true)
  const [toast, setToast] = useState<string | null>(null)
  const health = useHealth()

  useEffect(() => {
    document.documentElement.classList.toggle('reduce-motion', !motionEnabled)
  }, [motionEnabled])

  useEffect(() => {
    const handleShortcut = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setSearchOpen(true)
      }
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'b') {
        event.preventDefault()
        setCollapsed((value) => !value)
      }
    }
    window.addEventListener('keydown', handleShortcut)
    return () => window.removeEventListener('keydown', handleShortcut)
  }, [])

  const closeToast = useCallback(() => setToast(null), [])

  return (
    <div className="min-h-screen">
      <Sidebar collapsed={collapsed} mobileOpen={mobileOpen} onCollapse={() => setCollapsed((value) => !value)} onCloseMobile={() => setMobileOpen(false)} onOpenProjects={() => setProjectsOpen(true)} onCreateProject={() => setCreateOpen(true)} onOpenSettings={() => setSettingsOpen(true)} />
      {mobileOpen && <button onClick={() => setMobileOpen(false)} className="fixed inset-0 z-40 bg-[#050914]/75 backdrop-blur-sm lg:hidden" aria-label="关闭导航遮罩" />}
      <div className={cn('min-h-screen transition-[padding] duration-300', collapsed ? 'lg:pl-[84px]' : 'lg:pl-[252px]')}>
        <Topbar health={health} onOpenMobile={() => setMobileOpen(true)} onOpenSearch={() => setSearchOpen(true)} onOpenProjects={() => setProjectsOpen(true)} onOpenSettings={() => setSettingsOpen(true)} />
        <main className="page-content mx-auto w-full max-w-[1600px] p-4 sm:p-6 xl:p-8">
          {HOSTED_DEMO && <HostedDemoAccess />}
          <Suspense fallback={<div className="flex min-h-[60vh] items-center justify-center"><div className="flex items-center gap-3 text-xs text-muted"><span className="h-4 w-4 animate-spin rounded-full border-2 border-primary/20 border-t-primary" />正在加载研究模块…</div></div>}>
            <Outlet context={{ openCreateProject: () => setCreateOpen(true) } satisfies LayoutOutletContext} />
          </Suspense>
        </main>
        <footer className="mx-auto flex max-w-[1600px] items-center justify-between px-6 pb-6 pt-2 font-mono text-[9px] tracking-wide text-[#526079] xl:px-8">
          <span>REPROLAB AI · BUILD 0.1.0</span><span>科研复现，从可信开始。</span>
        </footer>
      </div>
      <CreateProjectModal open={createOpen} onClose={() => setCreateOpen(false)} onCreated={(name) => setToast(`项目“${name}”已创建`)}/>
      <ProjectSwitcherModal open={projectsOpen} onClose={() => setProjectsOpen(false)} onCreate={() => setCreateOpen(true)} />
      <SearchModal open={searchOpen} onClose={() => setSearchOpen(false)} />
      <SettingsModal open={settingsOpen} onClose={() => setSettingsOpen(false)} collapsed={collapsed} onCollapsedChange={setCollapsed} motionEnabled={motionEnabled} onMotionChange={setMotionEnabled} onSave={() => setToast('工作区偏好已保存')} />
      {toast && <Toast message={toast} onClose={closeToast} />}
    </div>
  )
}
