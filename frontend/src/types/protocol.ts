export type InformationType = 'paper_fact' | 'derived_suggestion' | 'unknown'
export type StepStatus = 'planned' | 'running' | 'done' | 'blocked'
export type ProtocolParamType = 'number' | 'string' | 'boolean' | 'list' | 'unknown'
export type ProtocolSourceType = InformationType

export interface OpenQuestion {
  field: string
  question: string
}

export interface ProtocolStep {
  id: string
  step_id: string
  title: string
  description: string | null
  order_no: number
  dependencies: string[]
  required_inputs: string[]
  expected_outputs: string[]
  status: StepStatus
  information_type: InformationType
  evidence_refs: string[]
  created_at: string
  updated_at: string
}

export interface ProtocolParamHistoryEntry {
  at: string
  action: string
  from?: string | null
  to?: string | null
}

export interface ProtocolParameter {
  id: string
  name: string
  original_value: string | null
  value: string | null
  param_type: ProtocolParamType
  unit: string | null
  source_type: ProtocolSourceType
  page_number: number | null
  source_field: string | null
  evidence_id: string | null
  confirmed: boolean
  modified_value: string | null
  modified_at: string | null
  history: ProtocolParamHistoryEntry[]
  note: string | null
  created_at: string
  updated_at: string
}

export interface ProtocolSummary {
  id: string
  paper_id: string
  paper_title: string
  name: string
  goal: string | null
  status: string
  version_no: number
  agent_method: string
  ai_status: string
  ai_error: string | null
  steps_count: number
  parsed_paper: boolean
  created_at: string
  updated_at: string
}

export interface ProtocolDetail extends ProtocolSummary {
  steps: ProtocolStep[]
  parameters: ProtocolParameter[]
  open_questions: OpenQuestion[]
  summary: string | null
  source_fields: string[]
  ai_configured: boolean
}

export interface ProtocolVersion {
  id: string
  version_no: number
  message: string | null
  created_at: string
}

export interface ProtocolListResponse {
  items: ProtocolSummary[]
  total: number
}

export interface GenerateProtocolRequest {
  paper_id: string
  name?: string
}

export interface UpdateProtocolRequest {
  name?: string
  goal?: string | null
  status?: string
  steps?: Array<Partial<ProtocolStep> & { id: string; title: string }>
  parameters?: Array<Partial<ProtocolParameter> & { id: string; name: string }>
}
