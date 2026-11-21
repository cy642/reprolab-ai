"""Experiment Insight API: import, comparison, stability, ablation, insight, export."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile

from ..config import get_settings
from ..db import connect
from ..schemas import (
    AnalyzeRequest,
    ComparisonOut,
    ComparisonRequest,
    ExperimentImportRequest,
    ExperimentImportResponse,
    ExperimentListResponse,
    ExperimentRecordOut,
    ImportPreviewResponse,
    InsightOut,
)
from ..services.ablation_analyzer import analyze_ablation
from ..services.comparison_engine import compare_records
from ..services.insight_engine import build_insight, enrich_with_llm
from ..services.insight_linkage import fetch_data_quality_warnings, fetch_protocol_alignment
from ..services.metrics_engine import (
    ExperimentParseError,
    normalize_records,
    parse_experiment_csv,
    parse_experiment_json,
    preview_records,
)
from ..services.report_builder import build_report_json, build_report_markdown
from ..services.stability_analyzer import analyze_stability

router = APIRouter(prefix="/api", tags=["Experiment Insight"])

BASE_DIR = Path(__file__).resolve().parents[2]
DEMO_PATH = BASE_DIR / "data" / "demo" / "ecg_experiments.json"


def _now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _json_load(text: str | None) -> Any:
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _row_to_out(row: Any) -> dict[str, Any]:
    return {
        "id": row["id"],
        "experiment_id": row["experiment_id"],
        "experiment_name": row["experiment_name"],
        "method": row["method"],
        "model_name": row["model_name"],
        "dataset": row["dataset"],
        "seed": row["seed"],
        "accuracy": row["accuracy"],
        "precision": row["precision"],
        "recall": row["recall"],
        "f1": row["f1"],
        "macro_f1": row["macro_f1"],
        "weighted_f1": row["weighted_f1"],
        "runtime": row["runtime"],
        "training_config": _json_load(row["training_config"]) or {},
        "confusion_matrix": _json_load(row["confusion_matrix"]),
        "confusion_labels": _json_load(row["confusion_labels"]),
        "per_class_metrics": _json_load(row["per_class_metrics"]) or {},
        "extra_fields": _json_load(row["extra_fields"]) or {},
        "metrics_scale": row["metrics_scale"],
        "raw_metrics": _json_load(row["raw_metrics"]) or {},
        "original_metrics_scale": row["original_metrics_scale"],
        "metric_source": row["metric_source"] or "imported_summary",
        "data_source": row["data_source"] or ("simulated" if row["is_simulated"] else "unknown"),
        "source_format": row["source_format"],
        "dataset_ref_id": row["dataset_ref_id"],
        "protocol_id": row["protocol_id"],
        "group_id": row["group_id"],
        "is_simulated": bool(row["is_simulated"]),
        "ai_status": row["ai_status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _insert_record(
    connection: Any,
    record: dict[str, Any],
    source_format: str,
    dataset_ref_id: str | None,
    protocol_id: str | None,
    group_id: str | None,
    is_simulated: bool,
    data_source: str = "unknown",
) -> str:
    record_id = f"exp_rec_{uuid.uuid4().hex[:16]}"
    now = _now()
    connection.execute(
        """
        INSERT INTO experiment_records (
            id, experiment_id, experiment_name, method, model_name, dataset, seed,
            accuracy, precision, recall, f1, macro_f1, weighted_f1, runtime,
            training_config, confusion_matrix, per_class_metrics, extra_fields,
            metrics_scale, original_metrics_scale, raw_metrics, metric_source, confusion_labels,
            data_source, source_format, dataset_ref_id, protocol_id, group_id,
            is_simulated, ai_status, created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            record_id,
            record["experiment_id"],
            record.get("experiment_name"),
            record["method"],
            record.get("model_name"),
            record["dataset"],
            record.get("seed"),
            record.get("accuracy"),
            record.get("precision"),
            record.get("recall"),
            record.get("f1"),
            record.get("macro_f1"),
            record.get("weighted_f1"),
            record.get("runtime"),
            json.dumps(record.get("training_config") or {}, ensure_ascii=False),
            json.dumps(record.get("confusion_matrix"), ensure_ascii=False) if record.get("confusion_matrix") is not None else None,
            json.dumps(record.get("per_class_metrics") or {}, ensure_ascii=False),
            json.dumps(record.get("extra_fields") or {}, ensure_ascii=False),
            record.get("metrics_scale") or "fraction",
            record.get("original_metrics_scale"),
            json.dumps(record.get("raw_metrics") or {}, ensure_ascii=False),
            record.get("metric_source") or "imported_summary",
            json.dumps(record.get("confusion_labels"), ensure_ascii=False) if record.get("confusion_labels") is not None else None,
            "simulated" if is_simulated else data_source,
            source_format,
            dataset_ref_id,
            protocol_id,
            group_id,
            1 if is_simulated else 0,
            "not_used",
            now,
            now,
        ),
    )
    return record_id


def _load_records(connection: Any, record_ids: list[str]) -> list[dict[str, Any]]:
    if not record_ids:
        return []
    placeholders = ",".join("?" for _ in record_ids)
    rows = connection.execute(
        f"SELECT * FROM experiment_records WHERE id IN ({placeholders}) ORDER BY created_at, rowid",
        tuple(record_ids),
    ).fetchall()
    found = {row["id"] for row in rows}
    missing = [record_id for record_id in record_ids if record_id not in found]
    if missing:
        raise HTTPException(
            status_code=404,
            detail={"code": "experiment_not_found", "message": f"实验记录不存在：{', '.join(missing)}"},
        )
    return [_row_to_out(row) for row in rows]


@router.post("/experiments/import/preview", response_model=ImportPreviewResponse)
async def preview_import(request: Request, file: UploadFile | None = File(default=None)) -> ImportPreviewResponse:
    """Parse and validate without persisting. Accepts an uploaded file or a JSON body of records."""
    source_format = "json"
    if file is not None:
        raw = await file.read()
        filename = (file.filename or "").lower()
        source_format = "csv" if filename.endswith(".csv") else "json"
    else:
        raw = await request.body()
    try:
        if source_format == "csv":
            raw_records = parse_experiment_csv(raw)
        else:
            raw_records = parse_experiment_json(raw)
    except ExperimentParseError as exc:
        raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
    result = normalize_records(raw_records)
    return ImportPreviewResponse(
        ok=result.ok,
        row_count=len(result.records),
        records=result.records,
        preview=preview_records(result),
        warnings=result.warnings,
        errors=result.errors,
        source_format=source_format,
    )


@router.post("/experiments/import", response_model=ExperimentImportResponse)
def confirm_import(payload: ExperimentImportRequest) -> ExperimentImportResponse:
    result = normalize_records(payload.records, explicit_scale=payload.metrics_scale)
    if result.errors:
        raise HTTPException(status_code=422, detail={"code": "validation_failed", "errors": result.errors, "warnings": result.warnings})
    data_source = payload.data_source or ("simulated" if payload.is_simulated else "unknown")
    if data_source not in {"real", "simulated", "test", "unknown"}:
        raise HTTPException(status_code=422, detail={"code": "invalid_data_source", "message": "data_source 必须为 real、simulated、test 或 unknown。"})
    if payload.is_simulated and data_source != "simulated":
        raise HTTPException(status_code=422, detail={"code": "data_source_conflict", "message": "is_simulated=true 时 data_source 必须为 simulated。"})
    with connect() as connection:
        if payload.dataset_ref_id and not connection.execute("SELECT 1 FROM datasets WHERE id = ?", (payload.dataset_ref_id,)).fetchone():
            raise HTTPException(status_code=404, detail={"code": "dataset_not_found", "message": "关联数据集不存在。"})
        if payload.protocol_id and not connection.execute("SELECT 1 FROM protocols WHERE id = ?", (payload.protocol_id,)).fetchone():
            raise HTTPException(status_code=404, detail={"code": "protocol_not_found", "message": "关联协议不存在。"})
        group_id = None
        if payload.group_name:
            group_id = f"exp_grp_{uuid.uuid4().hex[:16]}"
            connection.execute(
                "INSERT INTO experiment_groups (id, name, dataset, record_ids, created_at) VALUES (?,?,?,?,?)",
                (group_id, payload.group_name, result.records[0]["dataset"] if result.records else None, "[]", _now()),
            )
        ids = [
            _insert_record(
                connection, record, payload.source_format, payload.dataset_ref_id,
                payload.protocol_id, group_id, payload.is_simulated, data_source,
            )
            for record in result.records
        ]
        if group_id:
            connection.execute("UPDATE experiment_groups SET record_ids = ? WHERE id = ?", (json.dumps(ids), group_id))
        connection.commit()
    return ExperimentImportResponse(ids=ids, count=len(ids), warnings=result.warnings, group_id=group_id)


@router.get("/experiments", response_model=ExperimentListResponse)
def list_experiments(
    dataset: str | None = None,
    method: str | None = None,
    data_source: str | None = None,
    source_scope: str = "all",
) -> ExperimentListResponse:
    if source_scope not in {"all", "research", "demo"}:
        raise HTTPException(status_code=422, detail={"code": "invalid_source_scope", "message": "source_scope 必须为 all、research 或 demo。"})
    with connect() as connection:
        query = "SELECT * FROM experiment_records WHERE 1=1"
        params: list[Any] = []
        if source_scope == "research":
            query += " AND is_simulated = 0 AND COALESCE(data_source, 'unknown') NOT IN ('simulated', 'test')"
        elif source_scope == "demo":
            query += " AND (is_simulated = 1 OR COALESCE(data_source, 'unknown') IN ('simulated', 'test'))"
        if data_source:
            query += " AND COALESCE(data_source, 'unknown') = ?"
            params.append(data_source)
        if dataset:
            query += " AND dataset = ?"
            params.append(dataset)
        if method:
            query += " AND method = ?"
            params.append(method)
        query += " ORDER BY created_at DESC, rowid"
        rows = connection.execute(query, tuple(params)).fetchall()
        items = [_row_to_out(row) for row in rows]
    return ExperimentListResponse(items=items, total=len(items), ai_configured=get_settings().llm_configured)


@router.get("/experiments/{experiment_id}", response_model=ExperimentRecordOut)
def get_experiment(experiment_id: str) -> ExperimentRecordOut:
    with connect() as connection:
        row = connection.execute("SELECT * FROM experiment_records WHERE id = ?", (experiment_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": f"实验记录 {experiment_id} 不存在。"})
        return _row_to_out(row)


@router.post("/experiments/compare", response_model=ComparisonOut)
def compare_experiments(payload: ComparisonRequest) -> ComparisonOut:
    if payload.operation_key:
        with connect() as connection:
            existing = connection.execute(
                "SELECT id FROM experiment_comparisons WHERE operation_key = ?", (payload.operation_key,)
            ).fetchone()
        if existing:
            return get_comparison(existing["id"])
    with connect() as connection:
        records = _load_records(connection, payload.experiment_ids)
        if not records:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "未找到指定的实验记录。"})
        result = compare_records(records, baseline_method=payload.baseline_method, primary_metric=payload.primary_metric)
        stability = analyze_stability(records)
        ablation = analyze_ablation(records, baseline_method=payload.baseline_method)
        comparison_id = f"cmp_{uuid.uuid4().hex[:16]}"
        connection.execute(
            """
            INSERT INTO experiment_comparisons (id, group_id, name, experiment_ids, metrics, rankings, stability, ablation, status, created_at, operation_key)
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, 'completed', ?, ?)
            """,
            (
                comparison_id,
                payload.name,
                json.dumps(payload.experiment_ids),
                json.dumps(result, ensure_ascii=False),
                json.dumps(result.get("rankings", []), ensure_ascii=False),
                json.dumps(stability, ensure_ascii=False),
                json.dumps(ablation, ensure_ascii=False),
                _now(),
                payload.operation_key,
            ),
        )
        connection.commit()
        return ComparisonOut(
            id=comparison_id,
            experiment_ids=payload.experiment_ids,
            baseline=result.get("baseline"),
            primary_metric=result.get("primary_metric"),
            result=result,
            status="completed",
            created_at=_now(),
        )


@router.get("/experiments/comparisons/{comparison_id}", response_model=ComparisonOut)
def get_comparison(comparison_id: str) -> ComparisonOut:
    with connect() as connection:
        row = connection.execute("SELECT * FROM experiment_comparisons WHERE id = ?", (comparison_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "比较结果不存在。"})
        return ComparisonOut(
            id=row["id"],
            experiment_ids=json.loads(row["experiment_ids"] or "[]"),
            baseline=(json.loads(row["metrics"] or "{}")).get("baseline"),
            primary_metric=(json.loads(row["metrics"] or "{}")).get("primary_metric"),
            result=json.loads(row["metrics"] or "{}"),
            status=row["status"],
            created_at=row["created_at"],
        )


def _run_analysis(connection: Any, experiment_ids: list[str], comparison_id: str | None, baseline_method: str | None, primary_metric: str) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any], dict[str, Any]]:
    records = _load_records(connection, experiment_ids)
    if not records:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "未找到指定的实验记录。"})
    comparison = compare_records(records, baseline_method=baseline_method, primary_metric=primary_metric)
    stability = analyze_stability(records)
    ablation = analyze_ablation(records, baseline_method=baseline_method)
    return records, comparison, stability, ablation


@router.post("/experiments/analyze", response_model=InsightOut)
def analyze_experiments(payload: AnalyzeRequest) -> InsightOut:
    if payload.operation_key:
        with connect() as connection:
            existing = connection.execute(
                "SELECT id FROM insight_reports WHERE operation_key = ?", (payload.operation_key,)
            ).fetchone()
        if existing:
            return get_insight(existing["id"])
    with connect() as connection:
        experiment_ids = payload.experiment_ids or []
        if payload.comparison_id:
            cmp_row = connection.execute("SELECT experiment_ids FROM experiment_comparisons WHERE id = ?", (payload.comparison_id,)).fetchone()
            if cmp_row:
                experiment_ids = json.loads(cmp_row["experiment_ids"] or "[]")
            else:
                raise HTTPException(status_code=404, detail={"code": "comparison_not_found", "message": "比较结果不存在。"})
        if not experiment_ids:
            raise HTTPException(status_code=400, detail={"code": "missing_experiments", "message": "必须提供 experiment_ids 或 comparison_id。"})
        records, comparison, stability, ablation = _run_analysis(
            connection, experiment_ids, payload.comparison_id, payload.baseline_method, payload.primary_metric
        )
        if payload.protocol_id and not connection.execute("SELECT 1 FROM protocols WHERE id = ?", (payload.protocol_id,)).fetchone():
            raise HTTPException(status_code=404, detail={"code": "protocol_not_found", "message": "关联协议不存在。"})
        if payload.dataset_ref_id and not connection.execute("SELECT 1 FROM datasets WHERE id = ?", (payload.dataset_ref_id,)).fetchone():
            raise HTTPException(status_code=404, detail={"code": "dataset_not_found", "message": "关联数据集不存在。"})
        if payload.audit_id:
            audit_row = connection.execute("SELECT dataset_id FROM audit_runs WHERE id = ?", (payload.audit_id,)).fetchone()
            if audit_row is None:
                raise HTTPException(status_code=404, detail={"code": "audit_not_found", "message": "关联审计不存在。"})
            if payload.dataset_ref_id and audit_row["dataset_id"] != payload.dataset_ref_id:
                raise HTTPException(status_code=422, detail={"code": "audit_dataset_mismatch", "message": "审计与指定数据集不属于同一记录。"})
        for record in records:
            if payload.dataset_ref_id and record.get("dataset_ref_id") not in (None, payload.dataset_ref_id):
                raise HTTPException(status_code=422, detail={"code": "dataset_link_mismatch", "message": "实验记录与指定数据集关联不一致。"})
            if payload.protocol_id and record.get("protocol_id") not in (None, payload.protocol_id):
                raise HTTPException(status_code=422, detail={"code": "protocol_link_mismatch", "message": "实验记录与指定协议关联不一致。"})
        audit_id, data_quality = fetch_data_quality_warnings(connection, audit_id=payload.audit_id, dataset_ref_id=payload.dataset_ref_id)
        protocol_alignment = fetch_protocol_alignment(connection, payload.protocol_id, records)
        content = build_insight(records, comparison, stability, ablation, data_quality, protocol_alignment)
        ai_status = "not_used"
        if payload.use_llm:
            content, ai_status = enrich_with_llm(content)
        insight_id = f"ins_{uuid.uuid4().hex[:16]}"
        connection.execute(
            """
            INSERT INTO insight_reports (id, experiment_ids, comparison_id, protocol_id, dataset_ref_id, audit_id, content, ai_status, created_at, operation_key)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """,
            (
                insight_id,
                json.dumps(experiment_ids),
                payload.comparison_id,
                payload.protocol_id,
                payload.dataset_ref_id,
                audit_id,
                json.dumps(content, ensure_ascii=False),
                ai_status,
                _now(),
                payload.operation_key,
            ),
        )
        connection.commit()
        return InsightOut(
            id=insight_id,
            experiment_ids=experiment_ids,
            comparison_id=payload.comparison_id,
            protocol_id=payload.protocol_id,
            audit_id=audit_id,
            dataset_ref_id=payload.dataset_ref_id,
            content=content,
            ai_status=ai_status,
            created_at=_now(),
        )


@router.post("/experiments/{experiment_id}/analyze", response_model=InsightOut)
def analyze_single_experiment(experiment_id: str, payload: AnalyzeRequest | None = None) -> InsightOut:
    body = payload or AnalyzeRequest()
    body.experiment_ids = [experiment_id]
    return analyze_experiments(body)


@router.get("/insights/{insight_id}", response_model=InsightOut)
def get_insight(insight_id: str) -> InsightOut:
    with connect() as connection:
        row = connection.execute("SELECT * FROM insight_reports WHERE id = ?", (insight_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "洞察报告不存在。"})
        return InsightOut(
            id=row["id"],
            experiment_ids=json.loads(row["experiment_ids"] or "[]"),
            comparison_id=row["comparison_id"],
            protocol_id=row["protocol_id"],
            audit_id=row["audit_id"],
            dataset_ref_id=row["dataset_ref_id"],
            content=json.loads(row["content"] or "{}"),
            ai_status=row["ai_status"],
            created_at=row["created_at"],
        )


@router.get("/insights/{insight_id}/export")
def export_insight(insight_id: str, format: str = "markdown") -> Response:
    with connect() as connection:
        row = connection.execute("SELECT content FROM insight_reports WHERE id = ?", (insight_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "not_found", "message": "洞察报告不存在。"})
        content = json.loads(row["content"] or "{}")
    if format == "json":
        body = json.dumps(build_report_json(content, insight_id), ensure_ascii=False, indent=2)
        media_type = "application/json"
        filename = f"experiment-insight-{insight_id}.json"
    else:
        body = build_report_markdown(content, insight_id)
        media_type = "text/markdown; charset=utf-8"
        filename = f"experiment-insight-{insight_id}.md"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/experiments/demo/seed", response_model=ExperimentImportResponse)
def seed_demo() -> ExperimentImportResponse:
    """Import the clearly-labeled simulated ECG demo dataset through the real pipeline."""
    if not DEMO_PATH.exists():
        raise HTTPException(status_code=404, detail={"code": "demo_missing", "message": "演示数据文件不存在。"})
    payload = json.loads(DEMO_PATH.read_text(encoding="utf-8"))
    raw_records = payload.get("records", []) if isinstance(payload, dict) else payload
    result = normalize_records(raw_records)
    if result.errors:
        raise HTTPException(status_code=422, detail={"code": "demo_invalid", "errors": result.errors})
    with connect() as connection:
        existing = connection.execute(
            "SELECT id, group_id FROM experiment_records WHERE source_format = 'demo' AND dataset = ? ORDER BY created_at, rowid",
            ("ECG-SixClass-Simulated",),
        ).fetchall()
        if existing:
            return ExperimentImportResponse(
                ids=[row["id"] for row in existing], count=len(existing),
                warnings=result.warnings, group_id=existing[0]["group_id"],
            )
        group_id = f"exp_grp_{uuid.uuid4().hex[:16]}"
        connection.execute(
            "INSERT INTO experiment_groups (id, name, dataset, record_ids, created_at) VALUES (?,?,?,?,?)",
            (group_id, "ECG 模拟演示（六分类）", "ECG-SixClass-Simulated", "[]", _now()),
        )
        ids = [_insert_record(connection, record, "demo", None, None, group_id, True, "simulated") for record in result.records]
        connection.execute("UPDATE experiment_groups SET record_ids = ? WHERE id = ?", (json.dumps(ids), group_id))
        connection.commit()
    return ExperimentImportResponse(ids=ids, count=len(ids), warnings=result.warnings, group_id=group_id)
