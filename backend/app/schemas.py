"""Pydantic response models for the paper intelligence and protocol API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class EvidenceOut(BaseModel):
    id: str
    field: str
    page: int
    quote: str


class FieldOut(BaseModel):
    field: str
    label: str
    category: str
    value: str | None
    status: str
    source: str
    confidence: float | None
    evidence: list[EvidenceOut]


class PageMeta(BaseModel):
    page: int
    chars: int


class PaperSummary(BaseModel):
    id: str
    filename: str
    title: str
    page_count: int
    file_size: int
    status: str
    parse_status: str
    ai_status: str
    ai_error: str | None
    extraction_method: str
    text_chars: int
    created_at: str
    updated_at: str


class PaperDetail(PaperSummary):
    fields: list[FieldOut]
    evidence: list[EvidenceOut]
    pages: list[PageMeta]
    ai_configured: bool
    parse_message: str | None


class AIInfo(BaseModel):
    configured: bool
    model: str | None
    base_url: str | None


class PaperListResponse(BaseModel):
    items: list[PaperSummary]
    total: int
    ai: AIInfo


class PageTextResponse(BaseModel):
    paper_id: str
    page: int
    page_count: int
    text: str


# ---------------- Protocol models ----------------


class ProtocolStepOut(BaseModel):
    id: str
    step_id: str
    title: str
    description: str | None
    order_no: int
    dependencies: list[str]
    required_inputs: list[str]
    expected_outputs: list[str]
    status: str
    information_type: str
    evidence_refs: list[str]
    created_at: str
    updated_at: str


class ProtocolParamOut(BaseModel):
    id: str
    name: str
    original_value: str | None = None
    value: str | None
    param_type: str
    unit: str | None
    source_type: str
    page_number: int | None
    source_field: str | None
    evidence_id: str | None
    confirmed: bool
    modified_value: str | None
    modified_at: str | None
    history: list[dict]
    note: str | None
    created_at: str
    updated_at: str


class OpenQuestionOut(BaseModel):
    field: str
    question: str


class ProtocolSummary(BaseModel):
    id: str
    paper_id: str
    paper_title: str
    name: str
    goal: str | None
    status: str
    version_no: int
    agent_method: str
    ai_status: str
    ai_error: str | None
    steps_count: int
    parsed_paper: bool
    created_at: str
    updated_at: str


class ProtocolDetail(ProtocolSummary):
    steps: list[ProtocolStepOut]
    parameters: list[ProtocolParamOut]
    open_questions: list[OpenQuestionOut]
    summary: str | None
    source_fields: list[str]
    ai_configured: bool


class ProtocolGenerateRequest(BaseModel):
    paper_id: str
    name: str | None = Field(default=None, max_length=120)
    operation_key: str | None = Field(default=None, max_length=240)


class ProtocolUpdateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=120)
    goal: str | None = None
    status: str | None = None
    steps: list[dict] | None = None
    parameters: list[dict] | None = None


class ProtocolSaveVersionRequest(BaseModel):
    message: str | None = Field(default=None, max_length=240)


class ProtocolVersionOut(BaseModel):
    id: str
    version_no: int
    message: str | None
    created_at: str


class ProtocolListResponse(BaseModel):
    items: list[ProtocolSummary]
    total: int


# ---------------- Data Guardian models ----------------


class DatasetColumnOut(BaseModel):
    id: str
    name: str
    position: int
    inferred_type: str
    missing_count: int
    missing_rate: float
    unique_count: int
    sample_values: list[str]


class DatasetMappingOut(BaseModel):
    record_id: str | None = None
    entity_id: str | None = None
    label: str | None = None
    split: str | None = None
    feature_columns: list[str] = Field(default_factory=list)
    split_mapping: dict[str, str] = Field(default_factory=dict)
    confirmed: bool = False


class DatasetMappingRequest(BaseModel):
    record_id: str = Field(min_length=1)
    entity_id: str | None = None
    label: str = Field(min_length=1)
    split: str = Field(min_length=1)
    feature_columns: list[str] = Field(min_length=1)
    split_mapping: dict[str, str] = Field(default_factory=dict)


class ExperimentRecordOut(BaseModel):
    id: str
    experiment_id: str
    experiment_name: str | None = None
    method: str
    model_name: str | None = None
    dataset: str
    seed: str | None = None
    accuracy: float | None = None
    precision: float | None = None
    recall: float | None = None
    f1: float | None = None
    macro_f1: float | None = None
    weighted_f1: float | None = None
    runtime: float | None = None
    training_config: dict[str, Any] = Field(default_factory=dict)
    confusion_matrix: list[list[float]] | None = None
    per_class_metrics: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    extra_fields: dict[str, Any] = Field(default_factory=dict)
    metrics_scale: str
    source_format: str
    dataset_ref_id: str | None = None
    protocol_id: str | None = None
    group_id: str | None = None
    is_simulated: bool = False
    data_source: str = "unknown"
    metric_source: str = "imported_summary"
    confusion_labels: list[str] | None = None
    raw_metrics: dict[str, Any] = Field(default_factory=dict)
    original_metrics_scale: str | None = None
    ai_status: str
    created_at: str
    updated_at: str


class ExperimentListResponse(BaseModel):
    items: list[ExperimentRecordOut]
    total: int
    ai_configured: bool
    deterministic_engine: bool = True


class ExperimentValidationItem(BaseModel):
    code: str
    message: str


class ImportPreviewResponse(BaseModel):
    ok: bool
    row_count: int
    records: list[dict[str, Any]]
    preview: list[dict[str, Any]]
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    source_format: str
    deterministic: bool = True


class ExperimentImportRequest(BaseModel):
    records: list[dict[str, Any]]
    source_format: str = "json"
    metrics_scale: str | None = None
    dataset_ref_id: str | None = None
    protocol_id: str | None = None
    group_name: str | None = None
    is_simulated: bool = False
    data_source: str | None = None


class ExperimentImportResponse(BaseModel):
    ids: list[str]
    count: int
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    group_id: str | None = None


class ComparisonRequest(BaseModel):
    experiment_ids: list[str] = Field(min_length=1)
    baseline_method: str | None = None
    primary_metric: str = "macro_f1"
    name: str | None = None
    operation_key: str | None = Field(default=None, max_length=240)


class ComparisonOut(BaseModel):
    id: str
    experiment_ids: list[str]
    baseline: str | None
    primary_metric: str
    result: dict[str, Any]
    status: str
    created_at: str


class AnalyzeRequest(BaseModel):
    experiment_ids: list[str] | None = None
    comparison_id: str | None = None
    protocol_id: str | None = None
    audit_id: str | None = None
    dataset_ref_id: str | None = None
    baseline_method: str | None = None
    primary_metric: str = "macro_f1"
    use_llm: bool = False
    operation_key: str | None = Field(default=None, max_length=240)


class InsightOut(BaseModel):
    id: str
    experiment_ids: list[str]
    comparison_id: str | None = None
    protocol_id: str | None = None
    audit_id: str | None = None
    dataset_ref_id: str | None = None
    content: dict[str, Any]
    ai_status: str
    created_at: str


class DatasetSummary(BaseModel):
    id: str
    filename: str
    file_size: int
    encoding: str
    delimiter: str
    row_count: int
    column_count: int
    missing_cells: int
    duplicate_rows: int
    status: str
    latest_audit_id: str | None = None
    created_at: str
    updated_at: str


class DatasetDetail(DatasetSummary):
    columns: list[DatasetColumnOut]
    mapping: DatasetMappingOut
    suggested_mapping: DatasetMappingOut
    preview: list[dict]


class DatasetListResponse(BaseModel):
    items: list[DatasetSummary]
    total: int
    ai_configured: bool
    deterministic_engine: bool = True


class AuditFindingOut(BaseModel):
    finding_id: str
    rule_id: str
    severity: str
    title: str
    description: str
    affected_rows: list[int]
    affected_record_ids: list[str]
    evidence: dict
    recommendation: str
    status: str


class AuditRunSummary(BaseModel):
    id: str
    dataset_id: str
    status: str
    engine_version: str
    ai_status: str
    summary: dict
    finding_count: int
    created_at: str
    completed_at: str | None


class AuditRunDetail(AuditRunSummary):
    findings: list[AuditFindingOut]


class AuditListResponse(BaseModel):
    items: list[AuditRunSummary]
    total: int


class WorkflowProgress(BaseModel):
    total: int
    completed: int
    skipped: int = 0
    failed: int = 0
    waiting: int = 0


class WorkflowNodeOut(BaseModel):
    id: str
    workflow_id: str
    node_key: str
    agent_name: str
    title: str
    order_no: int
    depends_on: list[str]
    requires_approval: bool
    optional: bool
    status: str
    input_ref: dict[str, Any] = Field(default_factory=dict)
    output_ref: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    retry_count: int
    max_retries: int
    started_at: str | None = None
    completed_at: str | None = None
    duration: float | None = None


class WorkflowSummary(BaseModel):
    id: str
    name: str
    workflow_type: str
    status: str
    created_at: str
    updated_at: str
    completed_at: str | None = None
    error: str | None = None
    progress: WorkflowProgress
    report_finalized: bool = False


class WorkflowListResponse(BaseModel):
    items: list[WorkflowSummary]
    total: int


class WorkflowApprovalOut(BaseModel):
    id: str
    node_id: str
    decision: str
    comment: str | None = None
    reviewer: str | None = None
    created_at: str
    audit_id: str | None = None
    finding_ids: list[str] = Field(default_factory=list)
    input_version: str | None = None
    risk_acknowledged: bool = False
    semantics: str | None = None


class WorkflowOut(WorkflowSummary):
    config: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None
    nodes: list[WorkflowNodeOut] = Field(default_factory=list)
    approvals: list[WorkflowApprovalOut] = Field(default_factory=list)
    input_version: str | None = None
    cancel_requested: bool = False
    report_finalized: bool = False


class WorkflowCreateRequest(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    workflow_type: str = "full_reproduction"
    paper_id: str | None = None
    dataset_id: str | None = None
    experiment_ids: list[str] = Field(default_factory=list)
    comparison_id: str | None = None
    mapping: dict[str, Any] | None = None
    protocol_name: str | None = None
    baseline_method: str | None = None
    primary_metric: str = "macro_f1"
    use_llm: bool = False
    reuse_audit: bool = True
    idempotency_key: str | None = Field(default=None, max_length=120)
    auto_start: bool = False


class WorkflowApprovalRequest(BaseModel):
    node_id: str | None = None
    node_key: str | None = None
    decision: str = Field(pattern="^(approve|reject)$")
    comment: str | None = None
    reviewer: str | None = None


class WorkflowEventOut(BaseModel):
    id: str
    workflow_id: str
    node_id: str | None = None
    event_type: str
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str


class WorkflowReportOut(BaseModel):
    workflow: dict[str, Any]
    sections: list[dict[str, Any]]
    references: dict[str, Any]
    is_simulated: bool
    data_validation_skipped: bool
    ai_status: str
    data_source: str = "unknown"
    data_sources: list[str] = Field(default_factory=list)
    execution_modes: dict[str, str] = Field(default_factory=dict)
    risk_summary: dict[str, Any] = Field(default_factory=dict)
    snapshot_version: str | None = None
    finalization_scope: str = "local_finalization"
