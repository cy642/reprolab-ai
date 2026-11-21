import type { ExperimentRecord } from '../types/experiment'
import type { WorkflowSummary } from '../types/workflow'

export interface HealthResponse {
  status: 'ok'
  service: string
  version: string
  timestamp: string
}

export interface ResearchOverview {
  papers: { total: number; ai: { configured: boolean; model: string | null } }
  experiments: { research: number; real: number; unknown: number; demo: number }
  datasets: { total: number; audited: number }
  workflows: { items: WorkflowSummary[]; total: number }
}

export const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '')
export const HOSTED_DEMO = import.meta.env.MODE === 'pages'
const DEMO_SESSION_KEY = 'reprolab-demo-access'

export function getDemoAccessCode(): string {
  return HOSTED_DEMO ? (sessionStorage.getItem(DEMO_SESSION_KEY) ?? '') : ''
}

export function setDemoAccessCode(code: string): void {
  if (code) sessionStorage.setItem(DEMO_SESSION_KEY, code)
  else sessionStorage.removeItem(DEMO_SESSION_KEY)
}

export function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const code = getDemoAccessCode()
  if (!code) return fetch(`${API_BASE_URL}${path}`, init)
  const headers = new Headers(init?.headers)
  headers.set('Authorization', `Bearer ${code}`)
  return fetch(`${API_BASE_URL}${path}`, { ...init, headers })
}

export async function downloadApiFile(path: string, filename: string): Promise<void> {
  const response = await apiFetch(path)
  if (!response.ok) throw new Error(`导出失败（${response.status}）`)
  const url = URL.createObjectURL(await response.blob())
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}

async function request<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await apiFetch(path, { signal })
  if (!response.ok) {
    let detail = `请求失败（${response.status}）`
    try {
      const body = await response.json()
      detail = body?.detail?.message || body?.detail || detail
    } catch {
      // Keep the HTTP error when the response has no JSON detail.
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return (await response.json()) as T
}

export async function getHealth(signal?: AbortSignal): Promise<HealthResponse> {
  return request<HealthResponse>('/api/health', signal)
}

export async function getResearchOverview(signal?: AbortSignal): Promise<ResearchOverview> {
  const [papers, experiments, datasets, workflows] = await Promise.all([
    request<{ total: number; ai: { configured: boolean; model: string | null } }>('/api/papers', signal),
    request<{ items: ExperimentRecord[] }>('/api/experiments?source_scope=all', signal),
    request<{ total: number; items: Array<{ status: string }> }>('/api/datasets', signal),
    request<{ items: WorkflowSummary[]; total: number }>('/api/workflows', signal),
  ])
  const researchRecords = experiments.items.filter((item) => !item.is_simulated && !['simulated', 'test'].includes(item.data_source))
  return {
    papers,
    experiments: {
      research: researchRecords.length,
      real: researchRecords.filter((item) => item.data_source === 'real').length,
      unknown: researchRecords.filter((item) => item.data_source === 'unknown').length,
      demo: experiments.items.length - researchRecords.length,
    },
    datasets: {
      total: datasets.total,
      audited: datasets.items.filter((item) => item.status === 'audited').length,
    },
    workflows,
  }
}
