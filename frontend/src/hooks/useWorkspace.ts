import { useContext } from 'react'
import { WorkspaceContext } from '../context/workspace-store'

export function useWorkspace() {
  const context = useContext(WorkspaceContext)
  if (!context) throw new Error('useWorkspace 必须在 WorkspaceProvider 内使用')
  return context
}
