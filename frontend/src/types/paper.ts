export type PaperStatus = 'uploaded' | 'extracting' | 'parsed' | 'needs_ocr' | 'failed'
export type ParseStatus = 'pending' | 'parsing' | 'completed' | 'needs_ocr' | 'failed'
export type PaperAIStatus = 'pending' | 'unconfigured' | 'not_used' | 'success' | 'failed'
export type FieldStatus = 'found' | 'pending' | 'unknown'
export type FieldCategory = 'basics' | 'research' | 'experiment' | 'outcome'

export interface AIInfo {
  configured: boolean
  model: string | null
  base_url: string | null
}

export interface Evidence {
  id: string
  field: string
  page: number
  quote: string
}

export interface PaperField {
  field: string
  label: string
  category: FieldCategory
  value: string | null
  status: FieldStatus
  source: 'heuristic' | 'llm' | 'none'
  confidence: number | null
  evidence: Evidence[]
}

export interface PaperPageMeta {
  page: number
  chars: number
}

export interface PaperSummary {
  id: string
  filename: string
  title: string
  page_count: number
  file_size: number
  status: PaperStatus
  parse_status: ParseStatus
  ai_status: PaperAIStatus
  ai_error: string | null
  extraction_method: 'none' | 'heuristic' | 'hybrid'
  text_chars: number
  created_at: string
  updated_at: string
}

export interface PaperDetail extends PaperSummary {
  fields: PaperField[]
  evidence: Evidence[]
  pages: PaperPageMeta[]
  ai_configured: boolean
  parse_message: string | null
}

export interface PaperListResponse {
  items: PaperSummary[]
  total: number
  ai: AIInfo
}

export interface PageTextResponse {
  paper_id: string
  page: number
  page_count: number
  text: string
}
