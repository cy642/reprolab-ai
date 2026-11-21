"""SQLite persistence for papers, extracted fields, page text, evidence, and protocols."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS papers (
    id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    sha256 TEXT NOT NULL UNIQUE,
    file_size INTEGER NOT NULL,
    page_count INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL,
    status TEXT NOT NULL,
    parse_status TEXT NOT NULL,
    ai_status TEXT NOT NULL,
    ai_error TEXT,
    extraction_method TEXT NOT NULL DEFAULT 'none',
    text_chars INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_pages (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    page INTEGER NOT NULL,
    text TEXT NOT NULL,
    PRIMARY KEY (paper_id, page)
);

CREATE TABLE IF NOT EXISTS paper_fields (
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    value TEXT,
    status TEXT NOT NULL,
    source TEXT NOT NULL,
    confidence REAL,
    PRIMARY KEY (paper_id, field)
);

CREATE TABLE IF NOT EXISTS paper_evidence (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    field TEXT NOT NULL,
    page INTEGER NOT NULL,
    quote TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_paper_evidence_paper ON paper_evidence(paper_id);

CREATE TABLE IF NOT EXISTS protocols (
    id TEXT PRIMARY KEY,
    paper_id TEXT NOT NULL REFERENCES papers(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    goal TEXT,
    summary TEXT,
    open_questions TEXT,
    source_fields TEXT,
    status TEXT NOT NULL,
    version_no INTEGER NOT NULL DEFAULT 1,
    latest_version_id TEXT,
    agent_method TEXT NOT NULL,
    ai_status TEXT NOT NULL,
    ai_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS protocol_steps (
    id TEXT PRIMARY KEY,
    protocol_id TEXT NOT NULL REFERENCES protocols(id) ON DELETE CASCADE,
    step_id TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    order_no INTEGER NOT NULL,
    dependencies TEXT NOT NULL DEFAULT '[]',
    required_inputs TEXT NOT NULL DEFAULT '[]',
    expected_outputs TEXT NOT NULL DEFAULT '[]',
    status TEXT NOT NULL,
    information_type TEXT NOT NULL,
    evidence_refs TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(protocol_id, step_id)
);

CREATE TABLE IF NOT EXISTS protocol_parameters (
    id TEXT PRIMARY KEY,
    protocol_id TEXT NOT NULL REFERENCES protocols(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    original_value TEXT,
    value TEXT,
    param_type TEXT NOT NULL,
    unit TEXT,
    source_type TEXT NOT NULL,
    page_number INTEGER,
    source_field TEXT,
    evidence_id TEXT,
    confirmed INTEGER NOT NULL DEFAULT 0,
    modified_value TEXT,
    modified_at TEXT,
    history TEXT NOT NULL DEFAULT '[]',
    note TEXT,
    order_no INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(protocol_id, name)
);

CREATE TABLE IF NOT EXISTS protocol_versions (
    id TEXT PRIMARY KEY,
    protocol_id TEXT NOT NULL REFERENCES protocols(id) ON DELETE CASCADE,
    version_no INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    message TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(protocol_id, version_no)
);

CREATE INDEX IF NOT EXISTS idx_protocols_paper ON protocols(paper_id);
CREATE INDEX IF NOT EXISTS idx_protocol_steps_protocol ON protocol_steps(protocol_id);
CREATE INDEX IF NOT EXISTS idx_protocol_params_protocol ON protocol_parameters(protocol_id);
CREATE INDEX IF NOT EXISTS idx_protocol_versions_protocol ON protocol_versions(protocol_id);

CREATE TABLE IF NOT EXISTS datasets (
    id TEXT PRIMARY KEY,
    original_filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    file_size INTEGER NOT NULL,
    encoding TEXT NOT NULL,
    delimiter TEXT NOT NULL,
    row_count INTEGER NOT NULL,
    column_count INTEGER NOT NULL,
    missing_cells INTEGER NOT NULL DEFAULT 0,
    duplicate_rows INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS dataset_columns (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    position INTEGER NOT NULL,
    inferred_type TEXT NOT NULL,
    missing_count INTEGER NOT NULL,
    missing_rate REAL NOT NULL,
    unique_count INTEGER NOT NULL,
    sample_values TEXT NOT NULL DEFAULT '[]',
    UNIQUE(dataset_id, name)
);

CREATE TABLE IF NOT EXISTS dataset_mappings (
    dataset_id TEXT PRIMARY KEY REFERENCES datasets(id) ON DELETE CASCADE,
    record_id TEXT NOT NULL,
    entity_id TEXT,
    label TEXT NOT NULL,
    split TEXT NOT NULL,
    feature_columns TEXT NOT NULL,
    split_mapping TEXT NOT NULL DEFAULT '{}',
    confirmed INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_runs (
    id TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL REFERENCES datasets(id) ON DELETE CASCADE,
    status TEXT NOT NULL,
    engine_version TEXT NOT NULL,
    ai_status TEXT NOT NULL,
    summary TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS audit_findings (
    id TEXT PRIMARY KEY,
    audit_id TEXT NOT NULL REFERENCES audit_runs(id) ON DELETE CASCADE,
    rule_id TEXT NOT NULL,
    severity TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    affected_rows TEXT NOT NULL DEFAULT '[]',
    affected_record_ids TEXT NOT NULL DEFAULT '[]',
    evidence TEXT NOT NULL DEFAULT '{}',
    recommendation TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_dataset_columns_dataset ON dataset_columns(dataset_id);
CREATE INDEX IF NOT EXISTS idx_audit_runs_dataset ON audit_runs(dataset_id);
CREATE INDEX IF NOT EXISTS idx_audit_findings_audit ON audit_findings(audit_id);

CREATE TABLE IF NOT EXISTS experiment_records (
    id TEXT PRIMARY KEY,
    experiment_id TEXT NOT NULL,
    experiment_name TEXT,
    method TEXT NOT NULL,
    model_name TEXT,
    dataset TEXT NOT NULL,
    seed TEXT,
    accuracy REAL,
    precision REAL,
    recall REAL,
    f1 REAL,
    macro_f1 REAL,
    weighted_f1 REAL,
    runtime REAL,
    training_config TEXT,
    confusion_matrix TEXT,
    per_class_metrics TEXT,
    extra_fields TEXT,
    metrics_scale TEXT NOT NULL DEFAULT 'fraction',
    source_format TEXT NOT NULL,
    dataset_ref_id TEXT,
    protocol_id TEXT,
    group_id TEXT,
    is_simulated INTEGER NOT NULL DEFAULT 0,
    ai_status TEXT NOT NULL DEFAULT 'not_used',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment_groups (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    dataset TEXT,
    record_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS experiment_comparisons (
    id TEXT PRIMARY KEY,
    group_id TEXT,
    name TEXT,
    experiment_ids TEXT NOT NULL DEFAULT '[]',
    metrics TEXT NOT NULL DEFAULT '{}',
    rankings TEXT NOT NULL DEFAULT '{}',
    stability TEXT NOT NULL DEFAULT '{}',
    ablation TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS insight_reports (
    id TEXT PRIMARY KEY,
    experiment_ids TEXT NOT NULL DEFAULT '[]',
    comparison_id TEXT,
    protocol_id TEXT,
    dataset_ref_id TEXT,
    audit_id TEXT,
    content TEXT NOT NULL DEFAULT '{}',
    ai_status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS research_workflows (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    workflow_type TEXT NOT NULL DEFAULT 'full_reproduction',
    status TEXT NOT NULL,
    config TEXT NOT NULL DEFAULT '{}',
    context TEXT NOT NULL DEFAULT '{}',
    idempotency_key TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS workflow_nodes (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES research_workflows(id) ON DELETE CASCADE,
    node_key TEXT NOT NULL,
    agent_name TEXT NOT NULL,
    title TEXT NOT NULL,
    order_no INTEGER NOT NULL,
    depends_on TEXT NOT NULL DEFAULT '[]',
    requires_approval INTEGER NOT NULL DEFAULT 0,
    optional INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    input_ref TEXT NOT NULL DEFAULT '{}',
    output_ref TEXT NOT NULL DEFAULT '{}',
    error TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    max_retries INTEGER NOT NULL DEFAULT 2,
    started_at TEXT,
    completed_at TEXT,
    duration REAL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(workflow_id, node_key)
);

CREATE TABLE IF NOT EXISTS workflow_events (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES research_workflows(id) ON DELETE CASCADE,
    node_id TEXT,
    event_type TEXT NOT NULL,
    message TEXT NOT NULL,
    payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS workflow_approvals (
    id TEXT PRIMARY KEY,
    workflow_id TEXT NOT NULL REFERENCES research_workflows(id) ON DELETE CASCADE,
    node_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    comment TEXT,
    reviewer TEXT,
    created_at TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_research_workflows_idem ON research_workflows(idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_workflow_nodes_workflow ON workflow_nodes(workflow_id);
CREATE INDEX IF NOT EXISTS idx_workflow_events_workflow ON workflow_events(workflow_id);
CREATE INDEX IF NOT EXISTS idx_workflow_approvals_workflow ON workflow_approvals(workflow_id);

CREATE INDEX IF NOT EXISTS idx_experiment_records_method ON experiment_records(method);
CREATE INDEX IF NOT EXISTS idx_experiment_records_dataset ON experiment_records(dataset);
CREATE INDEX IF NOT EXISTS idx_experiment_records_group ON experiment_records(group_id);
CREATE INDEX IF NOT EXISTS idx_experiment_records_protocol ON experiment_records(protocol_id);
CREATE INDEX IF NOT EXISTS idx_experiment_comparisons_group ON experiment_comparisons(group_id);
CREATE INDEX IF NOT EXISTS idx_insight_reports_protocol ON insight_reports(protocol_id);
CREATE INDEX IF NOT EXISTS idx_insight_reports_dataset ON insight_reports(dataset_ref_id);
"""


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """Open a short-lived connection with foreign keys and row access enabled."""
    settings = get_settings()
    settings.storage_dir.mkdir(parents=True, exist_ok=True)
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    settings.datasets_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(settings.database_path, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def init_db() -> None:
    """Create storage directories and the schema if missing. Existing tables are ALTERed to append
    newly required columns; nothing is ever dropped."""
    settings = get_settings()
    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    with connect() as connection:
        connection.executescript(SCHEMA)
        added_columns = _migrate_add_missing_columns(connection)
        if ("protocol_parameters", "original_value") in added_columns:
            _backfill_protocol_original_values(connection)
        connection.execute(
            "UPDATE experiment_records SET data_source = 'simulated' "
            "WHERE is_simulated = 1 AND COALESCE(data_source, 'unknown') = 'unknown'"
        )
        for table in ("protocols", "audit_runs", "experiment_comparisons", "insight_reports"): 
            connection.execute(
                f"CREATE UNIQUE INDEX IF NOT EXISTS idx_{table}_operation_key "
                f"ON {table}(operation_key) WHERE operation_key IS NOT NULL"
            )
        _recover_interrupted_workflows(connection)


def _migrate_add_missing_columns(connection: sqlite3.Connection) -> set[tuple[str, str]]:
    """Incrementally append columns and return the columns added by this run."""
    add_columns = [
        ("protocols", "summary", "TEXT"),
        ("protocols", "open_questions", "TEXT"),
        ("protocols", "source_fields", "TEXT"),
        ("protocol_parameters", "order_no", "INTEGER NOT NULL DEFAULT 0"),
        ("protocol_parameters", "note", "TEXT"),
        ("protocol_parameters", "original_value", "TEXT"),
        ("protocols", "operation_key", "TEXT"),
        ("audit_runs", "operation_key", "TEXT"),
        ("audit_runs", "dataset_sha256", "TEXT"),
        ("audit_runs", "mapping_snapshot", "TEXT"),
        ("experiment_comparisons", "operation_key", "TEXT"),
        ("insight_reports", "operation_key", "TEXT"),
        ("experiment_records", "data_source", "TEXT NOT NULL DEFAULT 'unknown'"),
        ("experiment_records", "metric_source", "TEXT NOT NULL DEFAULT 'imported_summary'"),
        ("experiment_records", "confusion_labels", "TEXT"),
        ("experiment_records", "raw_metrics", "TEXT NOT NULL DEFAULT '{}'"),
        ("experiment_records", "original_metrics_scale", "TEXT"),
        ("research_workflows", "input_snapshot", "TEXT NOT NULL DEFAULT '{}'"),
        ("research_workflows", "report_snapshot", "TEXT"),
        ("research_workflows", "runner_token", "TEXT"),
        ("research_workflows", "runner_started_at", "TEXT"),
        ("research_workflows", "cancel_requested", "INTEGER NOT NULL DEFAULT 0"),
        ("workflow_approvals", "audit_id", "TEXT"),
        ("workflow_approvals", "finding_ids", "TEXT NOT NULL DEFAULT '[]'"),
        ("workflow_approvals", "input_version", "TEXT"),
        ("workflow_approvals", "risk_acknowledged", "INTEGER NOT NULL DEFAULT 0"),
        ("workflow_approvals", "semantics", "TEXT"),
    ]
    added: set[tuple[str, str]] = set()
    for table, column, type_decl in add_columns:
        cols = {row[1] for row in connection.execute(f"PRAGMA table_info({table})").fetchall()}
        if column not in cols:
            connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {type_decl}")
            added.add((table, column))
    return added


def _backfill_protocol_original_values(connection: sqlite3.Connection) -> None:
    """Recover baselines from initial snapshots, falling back to the migration-time value."""
    import json

    rows = connection.execute(
        "SELECT id, protocol_id, name, value FROM protocol_parameters"
    ).fetchall()
    for row in rows:
        baseline = row["value"]
        version = connection.execute(
            "SELECT snapshot FROM protocol_versions WHERE protocol_id = ? ORDER BY version_no LIMIT 1",
            (row["protocol_id"],),
        ).fetchone()
        if version:
            try:
                snapshot = json.loads(version["snapshot"])
                original = next(
                    (item for item in snapshot.get("parameters", []) if item.get("name") == row["name"]),
                    None,
                )
                if original is not None:
                    baseline = original.get("original_value", original.get("value"))
            except (TypeError, ValueError, AttributeError):
                pass
        connection.execute(
            "UPDATE protocol_parameters SET original_value = ? WHERE id = ?",
            (baseline, row["id"]),
        )


def _recover_interrupted_workflows(connection: sqlite3.Connection) -> None:
    """Turn orphaned runners into an explicit recoverable failure at process startup."""
    from datetime import datetime, timezone
    import uuid

    rows = connection.execute(
        "SELECT id FROM research_workflows WHERE runner_token IS NOT NULL OR status = 'running'"
    ).fetchall()
    for row in rows:
        workflow_id = row["id"]
        now = datetime.now(timezone.utc).isoformat()
        message = "执行进程中断；重试将按稳定操作标识找回已保存结果，不会盲目重复插入。"
        running_nodes = connection.execute(
            "SELECT id FROM workflow_nodes WHERE workflow_id = ? AND status = 'running'",
            (workflow_id,),
        ).fetchall()
        connection.execute(
            "UPDATE workflow_nodes SET status = 'failed', error = ?, completed_at = ?, updated_at = ? "
            "WHERE workflow_id = ? AND status = 'running'",
            (message, now, now, workflow_id),
        )
        connection.execute(
            "UPDATE research_workflows SET status = 'failed', error = ?, runner_token = NULL, "
            "runner_started_at = NULL, updated_at = ? WHERE id = ?",
            (message, now, workflow_id),
        )
        connection.execute(
            "INSERT INTO workflow_events (id, workflow_id, node_id, event_type, message, payload, created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            (
                f"wfe_{uuid.uuid4().hex[:16]}",
                workflow_id,
                running_nodes[0]["id"] if running_nodes else None,
                "workflow_interrupted",
                message,
                "{}",
                now,
            ),
        )


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None
