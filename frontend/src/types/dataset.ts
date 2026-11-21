export type Severity = 'critical' | 'high' | 'medium' | 'low' | 'info'
export type FindingStatus = 'confirmed_issue' | 'potential_risk' | 'suggestion'

export interface DatasetColumn {
  id: string
  name: string
  position: number
  inferred_type: string
  missing_count: number
  missing_rate: number
  unique_count: number
  sample_values: string[]
}

export interface DatasetMapping {
  record_id: string | null
  entity_id: string | null
  label: string | null
  split: string | null
  feature_columns: string[]
  split_mapping: Record<string, string>
  confirmed: boolean
}

export interface DatasetMappingRequest {
  record_id: string
  entity_id: string | null
  label: string
  split: string
  feature_columns: string[]
  split_mapping: Record<string, string>
}

export interface DatasetSummary {
  id: string
  filename: string
  file_size: number
  encoding: string
  delimiter: string
  row_count: number
  column_count: number
  missing_cells: number
  duplicate_rows: number
  status: string
  latest_audit_id: string | null
  created_at: string
  updated_at: string
}

export interface DatasetDetail extends DatasetSummary {
  columns: DatasetColumn[]
  mapping: DatasetMapping
  suggested_mapping: DatasetMapping
  preview: Array<{ row_number: number; values: Record<string, string> }>
}

export interface DatasetListResponse {
  items: DatasetSummary[]
  total: number
  ai_configured: boolean
  deterministic_engine: boolean
}

export interface EvidenceRecord {
  row_number: number
  record_id: string
  entity_id: string | null
  split: string
  values: Record<string, string>
}

export interface AuditFinding {
  finding_id: string
  rule_id: string
  severity: Severity
  title: string
  description: string
  affected_rows: number[]
  affected_record_ids: string[]
  evidence: {
    affected_count?: number
    truncated?: boolean
    records?: EvidenceRecord[]
    fields?: string[]
    [key: string]: unknown
  }
  recommendation: string
  status: FindingStatus
}

export interface ClassSlice {
  label: string
  count: number
  percentage: number
}

export interface AuditSummary {
  row_count: number
  column_count: number
  missing_cells: number
  duplicate_rows: number
  finding_count: number
  severity_counts: Record<Severity, number>
  status_counts: Record<string, number>
  deterministic: boolean
  ai_note: string
  class_distribution?: {
    overall?: ClassSlice[]
    by_split?: Record<string, ClassSlice[]>
    min_label?: string
    max_label?: string
    imbalance_ratio?: number
    train_test_difference?: number
    [key: string]: unknown
  }
  missing_by_column?: Array<{
    column: string
    missing_count: number
    missing_rate: number
    percentage?: number
    [key: string]: unknown
  }>
  split_distribution?: Array<{
    split: string
    count: number
    percentage: number
    [key: string]: unknown
  }>
  feature_statistics?: Array<Record<string, unknown>>
  [key: string]: unknown
}

export interface AuditRunSummary {
  id: string
  dataset_id: string
  status: string
  engine_version: string
  ai_status: string
  summary: AuditSummary
  finding_count: number
  created_at: string
  completed_at: string | null
}

export interface AuditRunDetail extends AuditRunSummary {
  findings: AuditFinding[]
}

export interface AuditListResponse {
  items: AuditRunSummary[]
  total: number
}
