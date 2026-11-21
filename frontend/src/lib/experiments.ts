import { apiFetch } from './api'
import type {
  ComparisonOut,
  ComparisonResult,
  ImportPreviewResponse,
  ImportResult,
  InsightOut,
  ExperimentListResponse,
  ExperimentRecord,
} from '../types/experiment'

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
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export async function listExperiments(dataset?: string, method?: string, sourceScope: 'all' | 'research' | 'demo' = 'research'): Promise<ExperimentListResponse> {
  const params = new URLSearchParams()
  params.set('source_scope', sourceScope)
  if (dataset) params.set('dataset', dataset)
  if (method) params.set('method', method)
  const suffix = params.toString() ? `?${params.toString()}` : ''
  return request<ExperimentListResponse>(`/api/experiments${suffix}`)
}

export async function getExperiment(id: string): Promise<ExperimentRecord> {
  return request<ExperimentRecord>(`/api/experiments/${id}`)
}

export async function previewImportFile(file: File): Promise<ImportPreviewResponse> {
  const form = new FormData()
  form.append('file', file)
  return request<ImportPreviewResponse>('/api/experiments/import/preview', { method: 'POST', body: form })
}

export async function previewImportJson(records: Array<Record<string, unknown>>): Promise<ImportPreviewResponse> {
  return request<ImportPreviewResponse>('/api/experiments/import/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(records),
  })
}

export async function confirmImport(payload: {
  records: Array<Record<string, unknown>>
  source_format: string
  metrics_scale?: string | null
  dataset_ref_id?: string | null
  protocol_id?: string | null
  is_simulated?: boolean
  data_source?: 'real' | 'simulated' | 'test' | 'unknown'
}): Promise<ImportResult> {
  return request<ImportResult>('/api/experiments/import', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function seedDemoExperiments(): Promise<ImportResult> {
  return request<ImportResult>('/api/experiments/demo/seed', { method: 'POST' })
}

export async function compareExperiments(experimentIds: string[], baselineMethod?: string, primaryMetric = 'macro_f1'): Promise<ComparisonOut> {
  return request<ComparisonOut>('/api/experiments/compare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ experiment_ids: experimentIds, baseline_method: baselineMethod, primary_metric: primaryMetric }),
  })
}

export async function getComparison(id: string): Promise<ComparisonOut> {
  return request<ComparisonOut>(`/api/experiments/comparisons/${id}`)
}

export async function analyzeExperiments(payload: {
  experiment_ids?: string[]
  comparison_id?: string
  protocol_id?: string | null
  audit_id?: string | null
  dataset_ref_id?: string | null
  baseline_method?: string | null
  primary_metric?: string
  use_llm?: boolean
}): Promise<InsightOut> {
  return request<InsightOut>('/api/experiments/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export async function getInsight(id: string): Promise<InsightOut> {
  return request<InsightOut>(`/api/insights/${id}`)
}

export async function exportInsight(insightId: string, format: 'markdown' | 'json'): Promise<void> {
  const response = await apiFetch(`/api/insights/${insightId}/export?format=${format}`)
  if (!response.ok) throw new Error(`导出失败（${response.status}）`)
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `experiment-insight-${insightId}.${format === 'json' ? 'json' : 'md'}`
  anchor.click()
  URL.revokeObjectURL(url)
}

export async function listProtocolOptions(): Promise<Array<{ id: string; name: string }>> {
  try {
    const data = await request<{ items: Array<{ id: string; name: string }> }>('/api/protocols')
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

export function comparisonMetricCell(row: ComparisonResult['metric_comparison'][number], metric: string): { mean: number | null; delta_vs_baseline_pp: number | null; values: number[] } {
  const cell = row[metric]
  if (cell && typeof cell === 'object' && 'mean' in cell) {
    return cell as { mean: number | null; delta_vs_baseline_pp: number | null; values: number[] }
  }
  return { mean: null, delta_vs_baseline_pp: null, values: [] }
}
