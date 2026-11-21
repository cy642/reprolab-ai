import { apiFetch } from './api'
import type {
  AuditFinding,
  AuditListResponse,
  AuditRunDetail,
  DatasetDetail,
  DatasetListResponse,
  DatasetMappingRequest,
} from '../types/dataset'



export class DatasetApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'DatasetApiError'
    this.status = status
    this.code = code
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await apiFetch(path, init)
  } catch {
    throw new DatasetApiError('无法连接后端服务，请确认 FastAPI 已启动。', 0)
  }
  if (!response.ok) {
    let message = `请求失败（${response.status}）`
    let code: string | undefined
    try {
      const payload = await response.json() as { detail?: string | { message?: string; code?: string } }
      if (typeof payload.detail === 'string') message = payload.detail
      else {
        message = payload.detail?.message || message
        code = payload.detail?.code
      }
    } catch {
      // Keep the HTTP fallback message for non-JSON errors.
    }
    throw new DatasetApiError(message, response.status, code)
  }
  return response.json() as Promise<T>
}

export function uploadDataset(file: File): Promise<DatasetDetail> {
  const form = new FormData()
  form.append('file', file)
  return request<DatasetDetail>('/api/datasets/upload', { method: 'POST', body: form })
}

export function listDatasets(signal?: AbortSignal): Promise<DatasetListResponse> {
  return request<DatasetListResponse>('/api/datasets', { signal })
}

export function getDataset(datasetId: string): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/datasets/${encodeURIComponent(datasetId)}`)
}

export function saveDatasetMapping(datasetId: string, mapping: DatasetMappingRequest): Promise<DatasetDetail> {
  return request<DatasetDetail>(`/api/datasets/${encodeURIComponent(datasetId)}/mapping`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(mapping),
  })
}

export function runDatasetAudit(datasetId: string): Promise<AuditRunDetail> {
  return request<AuditRunDetail>(`/api/datasets/${encodeURIComponent(datasetId)}/audit`, { method: 'POST' })
}

export function listDatasetAudits(datasetId: string): Promise<AuditListResponse> {
  return request<AuditListResponse>(`/api/datasets/${encodeURIComponent(datasetId)}/audits`)
}

export function getAudit(auditId: string): Promise<AuditRunDetail> {
  return request<AuditRunDetail>(`/api/audits/${encodeURIComponent(auditId)}`)
}

export function getAuditFindings(auditId: string): Promise<AuditFinding[]> {
  return request<AuditFinding[]>(`/api/audits/${encodeURIComponent(auditId)}/findings`)
}

export function auditExportPath(auditId: string, format: 'markdown' | 'json'): string {
  return `/api/audits/${encodeURIComponent(auditId)}/export?format=${format}`
}
