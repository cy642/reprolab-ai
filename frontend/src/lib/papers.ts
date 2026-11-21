import { API_BASE_URL, apiFetch, getDemoAccessCode } from './api'
import type {
  AIInfo,
  PaperDetail,
  PaperListResponse,
  PaperSummary,
  PageTextResponse,
} from '../types/paper'



export class ApiError extends Error {
  status: number
  code?: string
  paperId?: string

  constructor(message: string, status: number, code?: string, paperId?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.paperId = paperId
  }
}

interface ErrorDetail {
  code?: string
  message?: string
  paper_id?: string
}

async function readError(response: Response): Promise<ApiError> {
  let detail: string | ErrorDetail | undefined
  try {
    const payload = await response.json() as { detail?: string | ErrorDetail }
    detail = payload.detail
  } catch {
    detail = undefined
  }
  if (typeof detail === 'string') return new ApiError(detail, response.status)
  return new ApiError(detail?.message || `请求失败（${response.status}）`, response.status, detail?.code, detail?.paper_id)
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

export function listPapers(signal?: AbortSignal): Promise<PaperListResponse> {
  return request<PaperListResponse>('/api/papers', { signal })
}

export function getPaper(paperId: string, signal?: AbortSignal): Promise<PaperDetail> {
  return request<PaperDetail>(`/api/papers/${encodeURIComponent(paperId)}`, { signal })
}

export function parsePaper(paperId: string): Promise<PaperDetail> {
  return request<PaperDetail>(`/api/papers/${encodeURIComponent(paperId)}/parse`, { method: 'POST' })
}

export function getPaperFileUrl(paperId: string): string {
  return `${API_BASE_URL}/api/papers/${encodeURIComponent(paperId)}/file`
}

export function getPageText(paperId: string, page: number, signal?: AbortSignal): Promise<PageTextResponse> {
  return request<PageTextResponse>(
    `/api/papers/${encodeURIComponent(paperId)}/text?page=${page}`,
    { signal },
  )
}

export function deletePaper(paperId: string): Promise<void> {
  return request<void>(`/api/papers/${encodeURIComponent(paperId)}`, { method: 'DELETE' })
}

export function uploadPaper(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<PaperDetail> {
  return new Promise((resolve, reject) => {
    const form = new FormData()
    form.append('file', file)
    const xhr = new XMLHttpRequest()
    xhr.open('POST', `${API_BASE_URL}/api/papers/upload`)
    const accessCode = getDemoAccessCode()
    if (accessCode) xhr.setRequestHeader('Authorization', `Bearer ${accessCode}`)
    xhr.responseType = 'json'
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable) return
      onProgress?.(Math.round((event.loaded / event.total) * 100))
    }
    xhr.onerror = () => reject(new ApiError('上传失败，无法连接后端服务。', 0))
    xhr.onload = () => {
      const payload = xhr.response as { detail?: string | ErrorDetail } | PaperDetail | null
      if (xhr.status >= 200 && xhr.status < 300 && payload) {
        resolve(payload as PaperDetail)
        return
      }
      const detail = (payload as { detail?: string | ErrorDetail } | null)?.detail
      if (typeof detail === 'string') {
        reject(new ApiError(detail, xhr.status))
        return
      }
      reject(new ApiError(
        detail?.message || `上传失败（${xhr.status}）`,
        xhr.status,
        detail?.code,
        detail?.paper_id,
      ))
    }
    xhr.send(form)
  })
}

export type { AIInfo, PaperDetail, PaperListResponse, PaperSummary, PageTextResponse }
