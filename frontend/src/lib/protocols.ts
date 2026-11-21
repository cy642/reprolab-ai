import { apiFetch } from './api'
import type {
  GenerateProtocolRequest,
  ProtocolDetail,
  ProtocolListResponse,
  ProtocolVersion,
  UpdateProtocolRequest,
} from '../types/protocol'



export class ApiError extends Error {
  status: number
  code?: string

  constructor(message: string, status: number, code?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
  }
}

interface ErrorDetail {
  code?: string
  message?: string
}

async function readError(response: Response): Promise<ApiError> {
  let detail: string | ErrorDetail | undefined
  try {
    const payload = await response.json() as { detail?: string | ErrorDetail }
    detail = payload.detail
  } catch {
    // swallow — some errors return plain text
  }
  if (typeof detail === 'string') return new ApiError(detail, response.status)
  return new ApiError(
    detail?.message || `请求失败（${response.status}）`,
    response.status,
    detail?.code,
  )
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response
  try {
    response = await apiFetch(path, init)
  } catch {
    throw new ApiError('无法连接后端服务，请确认 FastAPI 已启动。', 0)
  }
  if (!response.ok) throw await readError(response)
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}

export function listProtocols(signal?: AbortSignal): Promise<ProtocolListResponse> {
  return request<ProtocolListResponse>('/api/protocols', { signal })
}

export function getProtocol(protocolId: string, signal?: AbortSignal): Promise<ProtocolDetail> {
  return request<ProtocolDetail>(`/api/protocols/${encodeURIComponent(protocolId)}`, { signal })
}

export function generateProtocol(payload: GenerateProtocolRequest): Promise<ProtocolDetail> {
  return request<ProtocolDetail>('/api/protocols/generate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function updateProtocol(
  protocolId: string,
  payload: UpdateProtocolRequest,
): Promise<ProtocolDetail> {
  return request<ProtocolDetail>(`/api/protocols/${encodeURIComponent(protocolId)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
}

export function saveProtocolVersion(
  protocolId: string,
  message?: string,
): Promise<ProtocolVersion> {
  return request<ProtocolVersion>(
    `/api/protocols/${encodeURIComponent(protocolId)}/versions`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: message ?? '用户手动保存' }),
    },
  )
}

export function listProtocolVersions(
  protocolId: string,
): Promise<ProtocolVersion[]> {
  return request<ProtocolVersion[]>(
    `/api/protocols/${encodeURIComponent(protocolId)}/versions`,
  )
}

export function deleteProtocol(protocolId: string): Promise<void> {
  return request<void>(`/api/protocols/${encodeURIComponent(protocolId)}`, {
    method: 'DELETE',
  })
}

export function protocolExportPath(
  protocolId: string,
  format: 'markdown' | 'json' = 'markdown',
): string {
  const url = `/api/protocols/${encodeURIComponent(protocolId)}/export?format=${format}`
  return url
}
