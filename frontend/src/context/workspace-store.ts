import { createContext } from 'react'
import type { NewProjectInput, Project } from '../types'

export interface WorkspaceContextValue {
  projects: Project[]
  activeProject: Project
  totalProjectCount: number
  createProject: (input: NewProjectInput) => Project
  selectProject: (id: string) => void
}

export const WorkspaceContext = createContext<WorkspaceContextValue | null>(null)
