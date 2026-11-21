export type WorkflowStatus = 'pending' | 'running' | 'waiting_approval' | 'completed' | 'failed' | 'cancelled'
export type NodeStatus = 'pending' | 'running' | 'waiting_approval' | 'completed' | 'failed' | 'skipped'

export interface WorkflowProgress {
  total: number
  completed: number
  skipped: number
  failed: number
  waiting: number
}

export interface WorkflowNode {
  id: string
  workflow_id: string
  node_key: string
  agent_name: string
  title: string
  order_no: number
  depends_on: string[]
  requires_approval: boolean
  optional: boolean
  status: NodeStatus
  input_ref: Record<string, unknown>
  output_ref: Record<string, unknown>
  error: string | null
  retry_count: number
  max_retries: number
  started_at: string | null
  completed_at: string | null
  duration: number | null
}

export interface WorkflowSummary {
  id: string
  name: string
  workflow_type: string
  status: WorkflowStatus
  created_at: string
  updated_at: string
  completed_at: string | null
  error: string | null
  progress: WorkflowProgress
  report_finalized: boolean
}

export interface WorkflowApproval {
  id: string
  node_id: string
  decision: string
  comment: string | null
  reviewer: string | null
  created_at: string
}

export interface Workflow extends WorkflowSummary {
  config: Record<string, unknown>
  context: Record<string, unknown>
  idempotency_key: string | null
  nodes: WorkflowNode[]
  approvals: WorkflowApproval[]
}

export interface WorkflowEvent {
  id: string
  workflow_id: string
  node_id: string | null
  event_type: string
  message: string
  payload: Record<string, unknown>
  created_at: string
}

export interface WorkflowReportSection {
  title: string
  kind: string
  lines: string[]
  refs: string[]
}

export interface WorkflowReport {
  workflow: Record<string, unknown>
  sections: WorkflowReportSection[]
  references: Record<string, unknown>
  is_simulated: boolean
  data_validation_skipped: boolean
  ai_status: string
  data_source: string
  data_sources: string[]
  execution_modes: Record<string, string>
  risk_summary: Record<string, unknown>
  snapshot_version: string | null
  finalization_scope: string
}

export interface CreateWorkflowPayload {
  name?: string
  workflow_type?: 'full_reproduction' | 'analysis_only'
  paper_id?: string | null
  dataset_id?: string | null
  experiment_ids?: string[]
  comparison_id?: string | null
  mapping?: Record<string, unknown> | null
  protocol_name?: string | null
  baseline_method?: string | null
  primary_metric?: string
  use_llm?: boolean
  reuse_audit?: boolean
  idempotency_key?: string | null
  auto_start?: boolean
}
