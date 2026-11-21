import { useMemo, useState, type ReactNode } from 'react'
import { initialProjects } from '../data/demo'
import type { Project } from '../types'
import { WorkspaceContext, type WorkspaceContextValue } from './workspace-store'

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [projects, setProjects] = useState(initialProjects)
  const [activeProjectId, setActiveProjectId] = useState(initialProjects[0].id)
  const [totalProjectCount, setTotalProjectCount] = useState(12)

  const value = useMemo<WorkspaceContextValue>(() => ({
    projects,
    activeProject: projects.find((project) => project.id === activeProjectId) ?? projects[0],
    totalProjectCount,
    createProject: (input) => {
      const project: Project = {
        id: `project-${Date.now()}`,
        code: `RL-${String(21 + projects.length).padStart(3, '0')}`,
        name: input.name.trim(),
        description: input.description.trim() || '尚未添加项目描述，可在项目设置中继续完善。',
        status: '复现中',
        progress: 0,
        paperCount: 0,
        experimentCount: 0,
        updated: '刚刚',
        nextTask: '导入第一篇论文',
        tags: [input.researchField],
        accent: 'violet',
      }
      setProjects((current) => [project, ...current])
      setActiveProjectId(project.id)
      setTotalProjectCount((count) => count + 1)
      return project
    },
    selectProject: (id) => setActiveProjectId(id),
  }), [activeProjectId, projects, totalProjectCount])

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}
