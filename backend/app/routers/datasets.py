"""Data Guardian dataset, mapping, deterministic audit and report endpoints."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.responses import Response
from starlette.status import HTTP_201_CREATED

from ..config import get_settings
from ..db import connect
from ..schemas import (
    AuditFindingOut,
    AuditListResponse,
    AuditRunDetail,
    AuditRunSummary,
    DatasetColumnOut,
    DatasetDetail,
    DatasetListResponse,
    DatasetMappingOut,
    DatasetMappingRequest,
    DatasetSummary,
)
from ..services.audit_types import AuditMapping
from ..services.audit_engine import run_audit
from ..services.csv_service import CsvError, read_csv, suggest_mapping

router = APIRouter(tags=["Data Guardian"])
ENGINE_VERSION = "1.1.0"
SEVERITIES = ("critical", "high", "medium", "low", "info")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _display_filename(raw: str | None) -> str:
    return Path((raw or "dataset.csv").replace("\\", "/")).name.strip()[:180] or "dataset.csv"


def _safe_file_path(stored_filename: str) -> Path:
    root = get_settings().datasets_dir.resolve()
    path = (root / stored_filename).resolve()
    if root not in path.parents or path.suffix.lower() != ".csv":
        raise HTTPException(status_code=400, detail={"code": "invalid_path", "message": "非法数据集文件路径。"})
    return path


def _dataset_row(connection: sqlite3.Connection, dataset_id: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "dataset_not_found", "message": "数据集不存在。"})
    return row


def _summary(connection: sqlite3.Connection, row: sqlite3.Row) -> DatasetSummary:
    latest = connection.execute(
        "SELECT id FROM audit_runs WHERE dataset_id = ? ORDER BY created_at DESC LIMIT 1",
        (row["id"],),
    ).fetchone()
    return DatasetSummary(
        id=row["id"],
        filename=row["original_filename"],
        file_size=row["file_size"],
        encoding=row["encoding"],
        delimiter=row["delimiter"],
        row_count=row["row_count"],
        column_count=row["column_count"],
        missing_cells=row["missing_cells"],
        duplicate_rows=row["duplicate_rows"],
        status=row["status"],
        latest_audit_id=latest["id"] if latest else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _column_models(connection: sqlite3.Connection, dataset_id: str) -> list[DatasetColumnOut]:
    rows = connection.execute(
        "SELECT * FROM dataset_columns WHERE dataset_id = ? ORDER BY position", (dataset_id,)
    ).fetchall()
    return [
        DatasetColumnOut(
            id=item["id"],
            name=item["name"],
            position=item["position"],
            inferred_type=item["inferred_type"],
            missing_count=item["missing_count"],
            missing_rate=item["missing_rate"],
            unique_count=item["unique_count"],
            sample_values=json.loads(item["sample_values"] or "[]"),
        )
        for item in rows
    ]


def _mapping_model(connection: sqlite3.Connection, dataset_id: str) -> DatasetMappingOut | None:
    row = connection.execute(
        "SELECT * FROM dataset_mappings WHERE dataset_id = ?", (dataset_id,)
    ).fetchone()
    if row is None:
        return None
    return DatasetMappingOut(
        record_id=row["record_id"],
        entity_id=row["entity_id"],
        label=row["label"],
        split=row["split"],
        feature_columns=json.loads(row["feature_columns"] or "[]"),
        split_mapping=json.loads(row["split_mapping"] or "{}"),
        confirmed=bool(row["confirmed"]),
    )


def _detail(connection: sqlite3.Connection, row: sqlite3.Row) -> DatasetDetail:
    columns = _column_models(connection, row["id"])
    suggested = DatasetMappingOut(**suggest_mapping(columns))
    mapping = _mapping_model(connection, row["id"]) or suggested.model_copy()
    path = _safe_file_path(row["stored_filename"])
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "dataset_file_missing", "message": "数据集原始文件不存在。"})
    try:
        preview = read_csv(path).preview
    except CsvError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"code": exc.code, "message": exc.message},
        ) from exc
    return DatasetDetail(
        **_summary(connection, row).model_dump(),
        columns=columns,
        mapping=mapping,
        suggested_mapping=suggested,
        preview=preview,
    )


@router.post("/api/datasets/upload", response_model=DatasetDetail, status_code=HTTP_201_CREATED)
def upload_dataset(file: UploadFile = File(...)) -> DatasetDetail:
    settings = get_settings()
    filename = _display_filename(file.filename)
    if not filename.lower().endswith(".csv"):
        raise HTTPException(status_code=415, detail={"code": "invalid_type", "message": "仅支持 CSV 文件。"})
    allowed_types = {
        "", "text/csv", "text/plain", "application/csv", "application/vnd.ms-excel",
        "application/octet-stream",
    }
    if file.content_type and file.content_type.lower() not in allowed_types:
        raise HTTPException(status_code=415, detail={"code": "invalid_type", "message": "文件 MIME 类型不是 CSV。"})

    settings.datasets_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, dir=settings.datasets_dir, suffix=".csv") as temp:
            temp_path = Path(temp.name)
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.dataset_max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "code": "file_too_large",
                            "message": f"CSV 超过 {settings.dataset_max_bytes:,} 字节安全上限。",
                        },
                    )
                digest.update(chunk)
                temp.write(chunk)
        try:
            parsed = read_csv(temp_path)
        except CsvError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail={"code": exc.code, "message": exc.message},
            ) from exc

        stored_filename = f"{uuid.uuid4().hex}.csv"
        final_path = _safe_file_path(stored_filename)
        os.replace(temp_path, final_path)
        temp_path = None
        dataset_id = f"dataset_{uuid.uuid4().hex[:16]}"
        now = _now()
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO datasets (
                    id, original_filename, stored_filename, sha256, file_size, encoding,
                    delimiter, row_count, column_count, missing_cells, duplicate_rows,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'uploaded', ?, ?)
                """,
                (
                    dataset_id, filename, stored_filename, digest.hexdigest(), total,
                    parsed.encoding, parsed.delimiter, len(parsed.rows), len(parsed.columns),
                    parsed.missing_cells, parsed.duplicate_rows, now, now,
                ),
            )
            connection.executemany(
                """
                INSERT INTO dataset_columns (
                    id, dataset_id, name, position, inferred_type, missing_count,
                    missing_rate, unique_count, sample_values
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        f"dscol_{uuid.uuid4().hex[:16]}", dataset_id, column.name,
                        column.position, column.inferred_type, column.missing_count,
                        column.missing_rate, column.unique_count,
                        json.dumps(column.sample_values, ensure_ascii=False),
                    )
                    for column in parsed.columns
                ],
            )
            return _detail(connection, _dataset_row(connection, dataset_id))
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


@router.get("/api/datasets", response_model=DatasetListResponse)
def list_datasets() -> DatasetListResponse:
    with connect() as connection:
        rows = connection.execute("SELECT * FROM datasets ORDER BY created_at DESC").fetchall()
        items = [_summary(connection, row) for row in rows]
    return DatasetListResponse(
        items=items,
        total=len(items),
        ai_configured=get_settings().llm_configured,
    )


@router.get("/api/datasets/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: str) -> DatasetDetail:
    with connect() as connection:
        return _detail(connection, _dataset_row(connection, dataset_id))


@router.put("/api/datasets/{dataset_id}/mapping", response_model=DatasetDetail)
def save_mapping(dataset_id: str, payload: DatasetMappingRequest) -> DatasetDetail:
    with connect() as connection:
        row = _dataset_row(connection, dataset_id)
        columns = {item.name for item in _column_models(connection, dataset_id)}
        entity_id = payload.entity_id or None
        required = [payload.record_id, payload.label, payload.split]
        unknown = [name for name in required + ([entity_id] if entity_id else []) if name not in columns]
        features = list(dict.fromkeys(payload.feature_columns))
        unknown.extend(name for name in features if name not in columns)
        if unknown or not features:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_mapping", "message": f"字段映射无效：{', '.join(unknown) or '至少选择一个特征列'}。"},
            )
        reserved = {payload.record_id, payload.label, payload.split, entity_id}
        overlap = sorted(reserved.intersection(features))
        if overlap:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_mapping", "message": f"ID、标签和划分字段不能同时作为特征：{', '.join(overlap)}。"},
            )
        split_mapping = {str(key): str(value) for key, value in payload.split_mapping.items()}
        unsupported = sorted({value for value in split_mapping.values() if value not in {"Train", "Validation", "Test"}})
        if unsupported:
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_split_mapping", "message": "自定义划分目标仅支持 Train、Validation、Test。"},
            )
        now = _now()
        connection.execute(
            """
            INSERT INTO dataset_mappings (
                dataset_id, record_id, entity_id, label, split, feature_columns,
                split_mapping, confirmed, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)
            ON CONFLICT(dataset_id) DO UPDATE SET
                record_id=excluded.record_id, entity_id=excluded.entity_id,
                label=excluded.label, split=excluded.split,
                feature_columns=excluded.feature_columns,
                split_mapping=excluded.split_mapping, confirmed=1, updated_at=excluded.updated_at
            """,
            (
                dataset_id, payload.record_id, entity_id, payload.label, payload.split,
                json.dumps(features, ensure_ascii=False), json.dumps(split_mapping, ensure_ascii=False), now,
            ),
        )
        connection.execute("UPDATE datasets SET status = 'mapped', updated_at = ? WHERE id = ?", (now, dataset_id))
        return _detail(connection, _dataset_row(connection, dataset_id))


def _finding_model(row: sqlite3.Row) -> AuditFindingOut:
    return AuditFindingOut(
        finding_id=row["id"],
        rule_id=row["rule_id"],
        severity=row["severity"],
        title=row["title"],
        description=row["description"],
        affected_rows=json.loads(row["affected_rows"] or "[]"),
        affected_record_ids=json.loads(row["affected_record_ids"] or "[]"),
        evidence=json.loads(row["evidence"] or "{}"),
        recommendation=row["recommendation"],
        status=row["status"],
    )


def _audit_summary(connection: sqlite3.Connection, row: sqlite3.Row) -> AuditRunSummary:
    count = connection.execute(
        "SELECT COUNT(*) FROM audit_findings WHERE audit_id = ?", (row["id"],)
    ).fetchone()[0]
    return AuditRunSummary(
        id=row["id"],
        dataset_id=row["dataset_id"],
        status=row["status"],
        engine_version=row["engine_version"],
        ai_status=row["ai_status"],
        summary=json.loads(row["summary"] or "{}"),
        finding_count=count,
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )


def _audit_row(connection: sqlite3.Connection, audit_id: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM audit_runs WHERE id = ?", (audit_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "audit_not_found", "message": "审计记录不存在。"})
    return row


def _audit_detail(connection: sqlite3.Connection, row: sqlite3.Row) -> AuditRunDetail:
    findings = connection.execute(
        """
        SELECT * FROM audit_findings WHERE audit_id = ?
        ORDER BY CASE severity WHEN 'critical' THEN 1 WHEN 'high' THEN 2
            WHEN 'medium' THEN 3 WHEN 'low' THEN 4 ELSE 5 END, rule_id, rowid
        """,
        (row["id"],),
    ).fetchall()
    return AuditRunDetail(
        **_audit_summary(connection, row).model_dump(),
        findings=[_finding_model(item) for item in findings],
    )


@router.post("/api/datasets/{dataset_id}/audit", response_model=AuditRunDetail, status_code=HTTP_201_CREATED)
def create_audit(dataset_id: str, operation_key: str | None = None) -> AuditRunDetail:
    if operation_key:
        with connect() as connection:
            existing = connection.execute(
                "SELECT id FROM audit_runs WHERE operation_key = ?", (operation_key,)
            ).fetchone()
            if existing:
                return _audit_detail(connection, _audit_row(connection, existing["id"]))
    with connect() as connection:
        if operation_key:
            existing = connection.execute(
                "SELECT id FROM audit_runs WHERE operation_key = ?", (operation_key,)
            ).fetchone()
            if existing:
                return _audit_detail(connection, _audit_row(connection, existing["id"]))
        dataset = _dataset_row(connection, dataset_id)
        stored = _mapping_model(connection, dataset_id)
        if stored is None or not stored.confirmed:
            raise HTTPException(
                status_code=400,
                detail={"code": "mapping_not_confirmed", "message": "请先确认并保存字段映射，再运行审计。"},
            )
        path = _safe_file_path(dataset["stored_filename"])
        if not path.is_file():
            raise HTTPException(status_code=404, detail={"code": "dataset_file_missing", "message": "数据集原始文件不存在。"})
        try:
            parsed = read_csv(path)
        except CsvError as exc:
            raise HTTPException(status_code=exc.status_code, detail={"code": exc.code, "message": exc.message}) from exc
        mapping = AuditMapping(
            record_id=stored.record_id or "",
            entity_id=stored.entity_id,
            label=stored.label or "",
            split=stored.split or "",
            feature_columns=stored.feature_columns,
            split_mapping=stored.split_mapping,
        )
        result = run_audit(parsed.rows, [column.name for column in parsed.columns], mapping)
        summary = dict(result.statistics)
        severity_counts = Counter(finding.severity for finding in result.findings)
        status_counts = Counter(finding.status for finding in result.findings)
        summary.update({
            "row_count": len(parsed.rows),
            "column_count": len(parsed.columns),
            "missing_cells": parsed.missing_cells,
            "duplicate_rows": parsed.duplicate_rows,
            "finding_count": len(result.findings),
            "severity_counts": {name: severity_counts.get(name, 0) for name in SEVERITIES},
            "status_counts": dict(status_counts),
            "deterministic": True,
            "rule_coverage": {
                "duplicates": "completed", "record_overlap": "completed", "feature_overlap": "completed",
                "entity_overlap": "completed" if stored.entity_id else "not_evaluated_missing_entity_mapping",
                "class_balance": "completed", "missing_values": "completed", "splits": "completed", "features": "completed",
            },
            "ai_note": "全部发现由 Python 确定性规则计算；本次未调用 LLM。",
        })
        audit_id = f"audit_{uuid.uuid4().hex[:16]}"
        now = _now()
        connection.execute(
            """
            INSERT INTO audit_runs (
                id, dataset_id, status, engine_version, ai_status, summary, created_at, completed_at,
                operation_key, dataset_sha256, mapping_snapshot
            ) VALUES (?, ?, 'completed', ?, 'not_used', ?, ?, ?, ?, ?, ?)
            """,
            (
                audit_id, dataset_id, ENGINE_VERSION, json.dumps(summary, ensure_ascii=False), now, now,
                operation_key, dataset["sha256"],
                json.dumps(stored.model_dump(), ensure_ascii=False, sort_keys=True, separators=(",", ":")),
            ),
        )
        for finding in result.findings:
            connection.execute(
                """
                INSERT INTO audit_findings (
                    id, audit_id, rule_id, severity, title, description, affected_rows,
                    affected_record_ids, evidence, recommendation, status, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    finding.finding_id, audit_id, finding.rule_id, finding.severity,
                    finding.title, finding.description,
                    json.dumps(finding.affected_rows), json.dumps(finding.affected_record_ids, ensure_ascii=False),
                    json.dumps(finding.evidence, ensure_ascii=False), finding.recommendation,
                    finding.status, now,
                ),
            )
        connection.execute("UPDATE datasets SET status = 'audited', updated_at = ? WHERE id = ?", (now, dataset_id))
        return _audit_detail(connection, _audit_row(connection, audit_id))


@router.get("/api/datasets/{dataset_id}/audits", response_model=AuditListResponse)
def list_dataset_audits(dataset_id: str) -> AuditListResponse:
    with connect() as connection:
        _dataset_row(connection, dataset_id)
        rows = connection.execute(
            "SELECT * FROM audit_runs WHERE dataset_id = ? ORDER BY created_at DESC", (dataset_id,)
        ).fetchall()
        items = [_audit_summary(connection, row) for row in rows]
    return AuditListResponse(items=items, total=len(items))


@router.get("/api/audits/{audit_id}", response_model=AuditRunDetail)
def get_audit(audit_id: str) -> AuditRunDetail:
    with connect() as connection:
        return _audit_detail(connection, _audit_row(connection, audit_id))


@router.get("/api/audits/{audit_id}/findings", response_model=list[AuditFindingOut])
def get_audit_findings(audit_id: str) -> list[AuditFindingOut]:
    with connect() as connection:
        return _audit_detail(connection, _audit_row(connection, audit_id)).findings


@router.get("/api/audits/{audit_id}/export")
def export_audit(audit_id: str, format: str = "markdown") -> Response:
    if format not in {"markdown", "json"}:
        raise HTTPException(status_code=400, detail={"code": "invalid_export", "message": "仅支持 markdown 或 json。"})
    with connect() as connection:
        audit = _audit_detail(connection, _audit_row(connection, audit_id))
        dataset = _dataset_row(connection, audit.dataset_id)
        payload = {
            "dataset": {"id": dataset["id"], "filename": dataset["original_filename"]},
            **audit.model_dump(),
        }
    if format == "json":
        return Response(
            content=json.dumps(payload, ensure_ascii=False, indent=2),
            media_type="application/json; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="data-guardian-{audit_id}.json"'},
        )

    severity = payload["summary"].get("severity_counts", {})
    lines = [
        f"# Data Guardian 审计报告 · {dataset['original_filename']}",
        "",
        f"- 审计 ID：`{audit_id}`",
        f"- 规则引擎：Python Deterministic Audit Engine v{audit.engine_version}",
        f"- AI 状态：`{audit.ai_status}`（未使用 LLM 生成审计发现）",
        f"- 数据规模：{payload['summary'].get('row_count', 0)} 行 × {payload['summary'].get('column_count', 0)} 列",
        f"- 发现总数：{audit.finding_count}",
        f"- 严重程度：{json.dumps(severity, ensure_ascii=False)}",
        "",
        "## 审计发现",
        "",
    ]
    for finding in audit.findings:
        lines.extend([
            f"### {finding.title}",
            "",
            f"- 规则：`{finding.rule_id}`",
            f"- 严重程度：`{finding.severity}`；分类：`{finding.status}`",
            f"- 描述：{finding.description}",
            f"- 影响行：{finding.affected_rows}",
            f"- 记录 ID：{finding.affected_record_ids}",
            f"- 建议：{finding.recommendation}",
            "",
        ])
    return Response(
        content="\n".join(lines),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="data-guardian-{audit_id}.md"'},
    )
