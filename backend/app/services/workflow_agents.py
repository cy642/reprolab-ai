"""Agent handlers that bridge the orchestrator to existing business services.

Every handler delegates to an already-tested Phase 1-5 service or router
function. No metric, evidence, or audit logic is reimplemented here: the
orchestrator only sequences calls, records resulting business IDs, and logs
provenance for the final report.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from fastapi import HTTPException

from ..db import connect
from .workflow_state import WorkflowInputError

HIGH_RISK_SEVERITIES = ("critical", "high")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _loads(raw: Any) -> Any:
    if not raw:
        return {}
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


def _paper_row(paper_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    return dict(row) if row else None


def _audit_findings(audit_id: str) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT id, rule_id, severity, title, status FROM audit_findings WHERE audit_id = ? ORDER BY rowid ASC",
            (audit_id,),
        ).fetchall()
    return [dict(row) for row in rows]


def _dataset_mapping(dataset_id: str) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute("SELECT * FROM dataset_mappings WHERE dataset_id = ?", (dataset_id,)).fetchone()
    if row is None:
        return None
    return {
        "record_id": row["record_id"],
        "entity_id": row["entity_id"],
        "label": row["label"],
        "split": row["split"],
        "feature_columns": _loads(row["feature_columns"]),
        "split_mapping": _loads(row["split_mapping"]),
        "confirmed": bool(row["confirmed"]),
    }


def _mapping_text(mapping: dict[str, Any]) -> str:
    return json.dumps(mapping, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _latest_audit(
    dataset_id: str, dataset_sha256: str, mapping: dict[str, Any], engine_version: str
) -> dict[str, Any] | None:
    """Reuse only an audit whose data, mapping, and rule version all match."""
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM audit_runs WHERE dataset_id = ? AND status = 'completed' ORDER BY created_at DESC, rowid DESC",
            (dataset_id,),
        ).fetchall()
    mapping_text = _mapping_text(mapping)
    for row in rows:
        if (
            row["dataset_sha256"] == dataset_sha256
            and row["mapping_snapshot"] == mapping_text
            and row["engine_version"] == engine_version
        ):
            return dict(row)
    return None


def _mode(ai_status: str | None, reused: bool, *, deterministic: bool = False) -> str:
    if deterministic:
        return "reused_rule" if reused else "deterministic_rules"
    if ai_status in {"success", "llm_enriched"}:
        return "reused_llm" if reused else "live_llm"
    if ai_status in {"failed", "failed_fallback"}:
        return "fallback"
    return "reused_rule" if reused else "rule_compute"


# --------------------------------------------------------------------------- #
# Paper Agent
# --------------------------------------------------------------------------- #
def run_paper_parse(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    paper_id = config.get("paper_id") or context.get("paper_id")
    if not paper_id:
        raise WorkflowInputError("missing_paper_id", "缺少 paper_id，无法运行 Paper Agent。")

    row = _paper_row(paper_id)
    if row is None:
        raise WorkflowInputError("paper_not_found", f"论文 {paper_id} 不存在。")

    reused = row["parse_status"] == "completed"
    if not reused:
        # Reuse the existing Phase 2 parse route (deterministic + optional LLM).
        from ..routers.papers import parse_paper

        try:
            parse_paper(paper_id, use_llm=bool(config.get("use_llm")))
        except HTTPException as exc:
            raise WorkflowInputError("paper_parse_failed", str(exc.detail)) from exc
        row = _paper_row(paper_id) or row

    with connect() as connection:
        evidence_rows = connection.execute(
            "SELECT id, field, page FROM paper_evidence WHERE paper_id = ? ORDER BY rowid ASC",
            (paper_id,),
        ).fetchall()

    fields = sorted({item["field"] for item in evidence_rows})
    return {
        "paper_id": paper_id,
        "title": row["title"],
        "parse_status": row["parse_status"],
        "extraction_method": row["extraction_method"],
        "ai_status": row["ai_status"],
        "evidence_ids": [item["id"] for item in evidence_rows],
        "evidence_count": len(evidence_rows),
        "fields": fields,
        "content_sha256": row["sha256"],
        "reused": reused,
        "execution_mode": _mode(row["ai_status"], reused),
    }


# --------------------------------------------------------------------------- #
# Protocol Agent
# --------------------------------------------------------------------------- #
def run_protocol_generate(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    paper_id = context.get("paper_id") or config.get("paper_id")
    if not paper_id:
        raise WorkflowInputError("missing_paper_id", "缺少论文证据，无法生成实验方案。")

    existing = context.get("protocol_id")
    if existing and not config.get("force_protocol"):
        with connect() as connection:
            row = connection.execute("SELECT id, name FROM protocols WHERE id = ?", (existing,)).fetchone()
        if row is not None:
            with connect() as connection:
                stored = connection.execute(
                    "SELECT ai_status, latest_version_id FROM protocols WHERE id = ?", (row["id"],)
                ).fetchone()
            return {
                "protocol_id": row["id"], "name": row["name"], "reused": True,
                "protocol_version_id": stored["latest_version_id"],
                "execution_mode": _mode(stored["ai_status"], True),
            }

    from ..routers.protocols import generate_protocol
    from ..schemas import ProtocolGenerateRequest

    operation_key = context.get("_operation_key")
    recovered = False
    if operation_key:
        with connect() as connection:
            recovered = connection.execute(
                "SELECT 1 FROM protocols WHERE operation_key = ?", (operation_key,)
            ).fetchone() is not None
    try:
        detail = generate_protocol(
            ProtocolGenerateRequest(
                paper_id=paper_id, name=config.get("protocol_name"), operation_key=operation_key
            ),
            use_llm=bool(config.get("use_llm")),
        )
    except HTTPException as exc:
        raise WorkflowInputError("protocol_generate_failed", str(exc.detail)) from exc

    return {
        "protocol_id": detail.id,
        "name": detail.name,
        "step_count": len(detail.steps),
        "parameter_count": len(detail.parameters),
        "ai_status": detail.ai_status,
        "reused": recovered,
        "execution_mode": _mode(detail.ai_status, recovered),
    }


# --------------------------------------------------------------------------- #
# Data Guardian
# --------------------------------------------------------------------------- #
def run_data_audit(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    dataset_id = config.get("dataset_id") or context.get("dataset_id")
    if not dataset_id:
        raise WorkflowInputError("missing_dataset_id", "缺少 dataset_id，无法运行 Data Guardian。")

    with connect() as connection:
        dataset = connection.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    if dataset is None:
        raise WorkflowInputError("dataset_not_found", f"数据集 {dataset_id} 不存在。")

    if config.get("mapping"):
        from ..routers.datasets import save_mapping
        from ..schemas import DatasetMappingRequest

        try:
            save_mapping(dataset_id, DatasetMappingRequest(**config["mapping"]))
        except HTTPException as exc:
            raise WorkflowInputError("mapping_invalid", str(exc.detail)) from exc

    mapping = _dataset_mapping(dataset_id)
    if not mapping or not mapping["confirmed"]:
        raise WorkflowInputError(
            "mapping_not_confirmed",
            "数据集尚未确认列映射；请在 Data Guardian 页面保存映射，或在创建工作流时提供 mapping 配置。",
        )

    from ..routers.datasets import ENGINE_VERSION, create_audit

    latest = _latest_audit(dataset_id, dataset["sha256"], mapping, ENGINE_VERSION)
    operation_key = context.get("_operation_key")
    recovered = False
    if operation_key:
        with connect() as connection:
            existing = connection.execute(
                "SELECT * FROM audit_runs WHERE operation_key = ?", (operation_key,)
            ).fetchone()
        if existing:
            if (
                existing["dataset_id"] != dataset_id
                or existing["dataset_sha256"] != dataset["sha256"]
                or existing["mapping_snapshot"] != _mapping_text(mapping)
                or existing["engine_version"] != ENGINE_VERSION
            ):
                raise WorkflowInputError(
                    "audit_recovery_input_mismatch",
                    "中断前保存的审计与当前数据内容、字段映射或规则版本不匹配；请基于新内容创建新工作流。",
                )
            latest = dict(existing)
            recovered = True
    if (config.get("reuse_audit", True) or recovered) and latest is not None:
        findings = _audit_findings(latest["id"])
        high_risk = [f for f in findings if f["severity"] in HIGH_RISK_SEVERITIES]
        return {
            "dataset_id": dataset_id,
            "dataset_filename": dataset["original_filename"],
            "dataset_sha256": dataset["sha256"],
            "mapping_snapshot": mapping,
            "engine_version": ENGINE_VERSION,
            "audit_id": latest["id"],
            "finding_count": len(findings),
            "high_risk_count": len(high_risk),
            "high_risk_rule_ids": sorted({f["rule_id"] for f in high_risk}),
            "reused": True,
            "recovered": recovered,
            "reuse_match_validated": True,
            "execution_mode": _mode("not_used", True, deterministic=True),
        }

    try:
        detail = create_audit(dataset_id, operation_key=operation_key)
    except HTTPException as exc:
        raise WorkflowInputError("audit_failed", str(exc.detail)) from exc

    high_risk = [f for f in detail.findings if f.severity in HIGH_RISK_SEVERITIES]
    return {
        "dataset_id": dataset_id,
        "dataset_filename": dataset["original_filename"],
        "dataset_sha256": dataset["sha256"],
        "mapping_snapshot": mapping,
        "engine_version": detail.engine_version,
        "audit_id": detail.id,
        "finding_count": len(detail.findings),
        "high_risk_count": len(high_risk),
        "high_risk_rule_ids": sorted({f.rule_id for f in high_risk}),
        "reused": False,
        "reuse_match_validated": True,
        "execution_mode": _mode("not_used", False, deterministic=True),
    }


def audit_requires_approval(context: dict[str, Any]) -> tuple[bool, str]:
    """Auto-pass only a successful, current, fully covered audit without high risk."""
    audit_id = context.get("audit_id")
    if not audit_id:
        return False, "未执行数据审计，跳过高风险确认。"
    findings = _audit_findings(audit_id)
    high_risk = [
        f for f in findings
        if f["severity"] in HIGH_RISK_SEVERITIES and f.get("status") not in {"resolved", "fixed"}
    ]
    if high_risk:
        rules = sorted({f["rule_id"] for f in high_risk})
        return True, f"检测到 {len(high_risk)} 条高风险发现（{', '.join(rules)}），批准仅表示知悉风险并继续。"

    with connect() as connection:
        audit = connection.execute("SELECT * FROM audit_runs WHERE id = ?", (audit_id,)).fetchone()
        if audit is None or audit["status"] != "completed":
            return True, "审计缺失或未成功完成，禁止自动通过。"
        dataset = connection.execute("SELECT sha256 FROM datasets WHERE id = ?", (audit["dataset_id"],)).fetchone()
    mapping = _dataset_mapping(audit["dataset_id"])
    from ..routers.datasets import ENGINE_VERSION

    coverage = _loads(audit["summary"]).get("rule_coverage", {})
    if not mapping or not mapping.get("entity_id"):
        return True, "缺少 entity_id 映射，实体跨集合检查未覆盖，禁止自动通过。"
    if not coverage or any(status != "completed" for status in coverage.values()):
        return True, "审计必要规则覆盖不完整或仅有空结果，禁止自动通过。"
    if (
        dataset is None
        or audit["dataset_sha256"] != dataset["sha256"]
        or audit["mapping_snapshot"] != _mapping_text(mapping)
        or audit["engine_version"] != ENGINE_VERSION
    ):
        return True, "审计与当前数据内容、字段映射或规则版本不匹配，禁止自动通过。"
    return False, "审计成功、必要检查已覆盖、输入与规则版本匹配，且无 critical/high 发现，自动通过。"


# --------------------------------------------------------------------------- #
# Insight Agent
# --------------------------------------------------------------------------- #
def run_experiment_analyze(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    experiment_ids = config.get("experiment_ids") or []
    comparison_id = config.get("comparison_id")

    if not experiment_ids and comparison_id:
        from ..routers.experiments import get_comparison

        try:
            stored = get_comparison(comparison_id)
        except HTTPException as exc:
            raise WorkflowInputError("comparison_not_found", str(exc.detail)) from exc
        experiment_ids = stored.experiment_ids

    if not experiment_ids:
        raise WorkflowInputError(
            "missing_experiment_ids",
            "缺少实验记录：请提供 experiment_ids 或 comparison_id，否则无法生成真实指标洞察。",
        )

    from ..routers.experiments import analyze_experiments, compare_experiments
    from ..schemas import AnalyzeRequest, ComparisonRequest

    baseline = config.get("baseline_method")
    metric = config.get("primary_metric") or "macro_f1"
    operation_base = context.get("_operation_key") or f"analysis:{uuid.uuid4().hex}"
    comparison_key = f"{operation_base}:comparison"
    insight_key = f"{operation_base}:insight"
    with connect() as connection:
        comparison_recovered = connection.execute(
            "SELECT 1 FROM experiment_comparisons WHERE operation_key = ?", (comparison_key,)
        ).fetchone() is not None
        insight_recovered = connection.execute(
            "SELECT 1 FROM insight_reports WHERE operation_key = ?", (insight_key,)
        ).fetchone() is not None
    try:
        comparison = compare_experiments(
            ComparisonRequest(
                experiment_ids=experiment_ids, baseline_method=baseline,
                primary_metric=metric, operation_key=comparison_key,
            )
        )
        insight = analyze_experiments(
            AnalyzeRequest(
                experiment_ids=experiment_ids,
                comparison_id=comparison.id,
                protocol_id=context.get("protocol_id"),
                audit_id=context.get("audit_id"),
                dataset_ref_id=context.get("dataset_id"),
                baseline_method=baseline,
                primary_metric=metric,
                use_llm=bool(config.get("use_llm")),
                operation_key=insight_key,
            )
        )
    except HTTPException as exc:
        raise WorkflowInputError("analysis_failed", str(exc.detail)) from exc

    content = insight.content or {}
    summary = content.get("experimental_summary", {})
    return {
        "comparison_id": comparison.id,
        "insight_id": insight.id,
        "ai_status": insight.ai_status,
        "baseline": comparison.baseline,
        "primary_metric": comparison.primary_metric,
        "method_count": len(comparison.result.get("methods", [])),
        "experiment_count": summary.get("experiment_count", len(experiment_ids)),
        "is_simulated": bool(summary.get("is_simulated")),
        "claim_count": len(content.get("key_observations", [])),
        "data_quality_warning_count": len(content.get("data_quality_warnings", [])),
        "comparison_reused": comparison_recovered,
        "reused": insight_recovered,
        "execution_mode": _mode(insight.ai_status, insight_recovered),
    }


# --------------------------------------------------------------------------- #
# Report assembler (no LLM: deterministic assembly of referenced records)
# --------------------------------------------------------------------------- #
def run_report_publish(context: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    from .workflow_report import build_workflow_report

    report = build_workflow_report(context)
    return {
        "report_sections": [section["title"] for section in report["sections"]],
        "insight_id": context.get("insight_id"),
        "is_simulated": report["is_simulated"],
        "data_validation_skipped": report["data_validation_skipped"],
        "ai_status": report["ai_status"],
    }


HANDLERS = {
    "paper_parse": run_paper_parse,
    "protocol_generate": run_protocol_generate,
    "data_audit": run_data_audit,
    "experiment_analyze": run_experiment_analyze,
    "report_publish": run_report_publish,
}
