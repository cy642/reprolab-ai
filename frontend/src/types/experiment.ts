export interface ExperimentRecord {
  id: string
  experiment_id: string
  experiment_name: string | null
  method: string
  model_name: string | null
  dataset: string
  seed: string | null
  accuracy: number | null
  precision: number | null
  recall: number | null
  f1: number | null
  macro_f1: number | null
  weighted_f1: number | null
  runtime: number | null
  training_config: Record<string, unknown>
  confusion_matrix: number[][] | null
  confusion_labels: string[] | null
  per_class_metrics: Record<string, { precision: number | null; recall: number | null; f1: number | null }>
  extra_fields: Record<string, unknown>
  metrics_scale: string
  raw_metrics: Record<string, number | null>
  original_metrics_scale: string | null
  metric_source: 'imported_summary' | 'computed' | string
  data_source: 'real' | 'simulated' | 'test' | 'unknown' | string
  source_format: string
  dataset_ref_id: string | null
  protocol_id: string | null
  group_id: string | null
  is_simulated: boolean
  ai_status: string
  created_at: string
  updated_at: string
}

export interface ExperimentListResponse {
  items: ExperimentRecord[]
  total: number
  ai_configured: boolean
  deterministic_engine: boolean
}

export interface ValidationItem {
  code: string
  message: string
  [key: string]: unknown
}

export interface ImportPreviewResponse {
  ok: boolean
  row_count: number
  records: ExperimentRecord[]
  preview: Array<Record<string, unknown>>
  warnings: ValidationItem[]
  errors: ValidationItem[]
  source_format: string
  deterministic: boolean
}

export interface ImportResult {
  ids: string[]
  count: number
  warnings: ValidationItem[]
  group_id: string | null
}

export interface MetricCell {
  mean: number | null
  delta_vs_baseline_pp: number | null
  values: number[]
}

export interface ComparisonResult {
  methods: string[]
  baseline: string
  primary_metric: string
  metric_comparison: Array<{
    method: string
    is_baseline: boolean
    run_count: number
    [metric: string]: MetricCell | string | number | boolean
  }>
  rankings: Array<{ rank: number; method: string; metric: string; metric_label: string; value: number; comparability: string }>
  comparability: {
    status: 'unverified' | 'incompatible'
    ranking_allowed: boolean
    ranking_suppressed: boolean
    reasons: string[]
    note: string
  }
  confusion: {
    matrices: Record<string, number[][]>
    difference_vs_baseline: Record<string, number[][]>
    classes: Record<string, number>
    labels: Record<string, string[]>
    per_class: Record<string, Record<string, { precision: number; recall: number; f1: number; support: number }>>
    macro_f1_from_confusion: Record<string, number>
    issues: Array<{ code: string; message: string; method?: string }>
  }
  macro_f1_definitions: { run_level_mean: string; aggregate_confusion: string; note: string }
  per_class: {
    classes: string[]
    by_method: Record<string, Record<string, { precision: number | null; recall: number | null; f1: number | null; support: number }>>
  }
  method_stats: Record<string, { run_count: number; seeds: string[]; source_record_ids: string[]; macro_f1_mean_of_runs: number | null }>
}

export interface ComparisonOut {
  id: string
  experiment_ids: string[]
  baseline: string | null
  primary_metric: string
  result: ComparisonResult
  status: string
  created_at: string
}

export interface StabilityStats {
  count: number
  mean: number
  std: number
  min: number
  max: number
  confidence_interval: {
    lower: number
    upper: number
    mean: number
    std: number
    count: number
    confidence: number
    t_critical: number
    margin_of_error: number
    method: string
    sufficient_sample: boolean
    note: string
  } | null
}

export interface InsightClaim {
  claim_type: 'observed_fact' | 'statistical_finding' | 'hypothesis' | 'recommendation'
  claim: string
  evidence: string
  calculation: string
  confidence_level: string
  limitation: string
}

export interface DataQualityWarning {
  audit_id: string | null
  finding_id: string
  rule_id: string
  severity: string
  title: string
  description: string
  status: string
  affected_record_ids: string[]
}

export interface InsightContent {
  experimental_summary: {
    experiment_count: number
    methods: string[]
    datasets: string[]
    baseline: string | null
    primary_metric: string
    is_simulated: boolean
    has_demo_data: boolean
    data_sources: string[]
    metric_sources: string[]
    data_label: string
  }
  key_observations: InsightClaim[]
  metric_comparisons: ComparisonResult
  stability_analysis: {
    groups: Array<{
      method: string
      model_name: string | null
      dataset: string
      run_count: number
      independent_run_count: number
      seed_count: number
      independent_seed_count: number
      seeds: string[]
      duplicate_seeds: string[]
      excluded_record_ids: string[]
      source_record_ids: string[]
      metrics: Record<string, StabilityStats>
      can_assess_stability: boolean
      note: string
    }>
    summary: Record<string, unknown>
  }
  ablation_analysis: {
    baseline: string
    comparisons: Array<{
      method: string
      deltas: Record<string, { baseline_mean: number; method_mean: number; delta_pp: number }>
      config_changes: string[]
      source_record_ids: string[]
    }>
    limitations: string[]
    has_component_flags: boolean
  }
  data_quality_warnings: DataQualityWarning[]
  protocol_alignment: {
    protocol_id: string
    protocol_name: string
    goal: string | null
    checks: Array<{ type: string; message: string; calculation: string; confidence: string; limitation: string }>
    recommendations: Array<{ type: string; message: string; target?: string; evidence?: string }>
  } | null
  limitations: string[]
  recommendations: Array<{ type: string; message: string; target?: string; evidence?: string; ai_generated?: boolean }>
  is_simulated: boolean
  narrative?: string
  ai_note?: string
}

export interface InsightOut {
  id: string
  experiment_ids: string[]
  comparison_id: string | null
  protocol_id: string | null
  audit_id: string | null
  dataset_ref_id: string | null
  content: InsightContent
  ai_status: string
  created_at: string
}
