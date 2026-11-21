import { apiFetch } from './api'
import type { CreateWorkflowPayload, Workflow, WorkflowEvent, WorkflowReport, WorkflowSummary } from '../types/workflow'

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(path, init)
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`
    try {
      const body = await response.json()
      detail = body?.detail?.message || body?.detail || detail
    } catch {
      /* ignore */
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return (await response.json()) as T
}

function json(body: unknown): RequestInit {
  return { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
}

export async function listWorkflows(status?: string, signal?: AbortSignal): Promise<{ items: WorkflowSummary[]; total: number }> {
  const suffix = status ? `?status_filter=${encodeURIComponent(status)}` : ''
  return request(`/api/workflows${suffix}`, { signal })
}

export async function createWorkflow(payload: CreateWorkflowPayload): Promise<Workflow> {
  return request('/api/workflows', json(payload))
}

export async function getWorkflow(id: string): Promise<Workflow> {
  return request(`/api/workflows/${id}`)
}

export async function startWorkflow(id: string): Promise<Workflow> {
  return request(`/api/workflows/${id}/start`, { method: 'POST' })
}

export async function retryWorkflowNode(id: string, nodeRef: string): Promise<Workflow> {
  return request(`/api/workflows/${id}/nodes/${nodeRef}/retry`, { method: 'POST' })
}

export async function submitWorkflowApproval(
  id: string,
  payload: { node_id?: string; node_key?: string; decision: 'approve' | 'reject'; comment?: string; reviewer?: string },
): Promise<Workflow> {
  return request(`/api/workflows/${id}/approvals`, json(payload))
}

export async function cancelWorkflow(id: string): Promise<Workflow> {
  return request(`/api/workflows/${id}/cancel`, { method: 'POST' })
}

export async function listWorkflowEvents(id: string): Promise<WorkflowEvent[]> {
  return request(`/api/workflows/${id}/events`)
}

export async function getWorkflowReport(id: string, signal?: AbortSignal): Promise<WorkflowReport> {
  return request(`/api/workflows/${id}/report`, { signal })
}

export async function exportWorkflowReport(id: string, format: 'markdown' | 'json'): Promise<void> {
  const response = await apiFetch(`/api/workflows/${id}/report/export?format=${format}`)
  if (!response.ok) throw new Error(`导出失败（${response.status}）`)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `research-workflow-${id}.${format === 'json' ? 'json' : 'md'}`
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function listPaperOptions(): Promise<Array<{ id: string; title: string }>> {
  try {
    const data = await request<{ items: Array<{ id: string; title: string }> }>('/api/papers')
    return data.items
  } catch {
    return []
  }
}

export async function listDatasetOptions(): Promise<Array<{ id: string; filename: string }>> {
  try {
    const data = await request<{ items: Array<{ id: string; filename: string }> }>('/api/datasets')
    return data.items
  } catch {
    return []
  }
}

export async function listExperimentOptions(): Promise<Array<{ id: string; experiment_id: string; method: string; seed: string | null; is_simulated: boolean }>> {
  try {
    const data = await request<{ items: Array<{ id: string; experiment_id: string; method: string; seed: string | null; is_simulated: boolean }> }>('/api/experiments?source_scope=all')
    return data.items
  } catch {
    return []
  }
}

export async function seedDemoExperiments(): Promise<{ count: number }> {
  return request('/api/experiments/demo/seed', { method: 'POST' })
}
