"""Read-only linkage between Insight and Data Guardian audits / Protocols."""

from __future__ import annotations

import json
import sqlite3
from typing import Any

HIGH_SEVERITIES = {"critical", "high"}
QUALITY_RULE_TOKENS = ("leakage", "cross_split", "class_imbalance", "imbalance", "missing")
DONE_STATUSES = {"done", "completed", "已完成", "finished", "complete"}


def fetch_data_quality_warnings(
    connection: sqlite3.Connection,
    audit_id: str | None = None,
    dataset_ref_id: str | None = None,
) -> tuple[str | None, list[dict[str, Any]]]:
    if not audit_id and dataset_ref_id:
        row = connection.execute(
            "SELECT id FROM audit_runs WHERE dataset_id = ? ORDER BY created_at DESC LIMIT 1",
            (dataset_ref_id,),
        ).fetchone()
        audit_id = row["id"] if row else None
    if not audit_id:
        return None, []
    rows = connection.execute(
        "SELECT * FROM audit_findings WHERE audit_id = ? ORDER BY rowid",
        (audit_id,),
    ).fetchall()
    findings: list[dict[str, Any]] = []
    for row in rows:
        rule_id = row["rule_id"]
        severity = row["severity"]
        relevant = severity in HIGH_SEVERITIES or any(token in rule_id for token in QUALITY_RULE_TOKENS)
        if not relevant:
            continue
        findings.append({
            "audit_id": audit_id,
            "finding_id": row["id"],
            "rule_id": rule_id,
            "severity": severity,
            "title": row["title"],
            "description": row["description"],
            "status": row["status"],
            "affected_record_ids": json.loads(row["affected_record_ids"] or "[]"),
        })
    return audit_id, findings


def fetch_protocol_alignment(
    connection: sqlite3.Connection,
    protocol_id: str | None,
    records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not protocol_id:
        return None
    row = connection.execute(
        "SELECT id, name, goal, status, open_questions, source_fields FROM protocols WHERE id = ?",
        (protocol_id,),
    ).fetchone()
    if row is None:
        return None
    steps = connection.execute(
        "SELECT step_id, title, status FROM protocol_steps WHERE protocol_id = ? ORDER BY order_no",
        (protocol_id,),
    ).fetchall()
    params = connection.execute(
        "SELECT name, value, param_type FROM protocol_parameters WHERE protocol_id = ? ORDER BY order_no, name",
        (protocol_id,),
    ).fetchall()
    open_questions = json.loads(row["open_questions"] or "[]")
    source_fields = json.loads(row["source_fields"] or "[]")

    checks: list[dict[str, Any]] = []
    recommendations: list[dict[str, Any]] = []

    incomplete = [s for s in steps if (s["status"] or "").strip().lower() not in DONE_STATUSES]
    if incomplete:
        checks.append({
            "type": "fact",
            "message": f"协议存在 {len(incomplete)} 个未标记完成的实验步骤：{', '.join(s['title'] for s in incomplete[:3])}",
            "calculation": "对照 protocol_steps.status，未落在完成态集合内的步骤计为未完成。",
            "confidence": "high",
            "limitation": "步骤状态由用户维护；只读读取，未修改协议。",
        })
    else:
        checks.append({
            "type": "fact",
            "message": f"协议 {len(steps)} 个步骤均标记为完成态。",
            "calculation": "所有 protocol_steps.status 属于完成态集合。",
            "confidence": "high",
            "limitation": "仅核对状态字段，不验证步骤产物真实性。",
        })

    methods = {r["method"] for r in records}
    if len(methods) < 2:
        recommendations.append({
            "type": "recommendation",
            "message": "当前实验仅有一种方法，缺少对照组/baseline，无法判定方法提升是否成立。",
            "target": "control_group",
            "evidence": f"methods={sorted(methods)}",
            "ai_generated": False,
        })

    missing_seed = [r.get("experiment_id") for r in records if not r.get("seed")]
    if missing_seed:
        checks.append({
            "type": "fact",
            "message": f"{len(missing_seed)} 条实验记录缺少随机种子，无法评估随机种子稳定性。",
            "calculation": "experiment_records.seed 为空的记录计数。",
            "confidence": "high",
            "limitation": "单次实验不得外推为稳定结论。",
        })

    config_keys: set[str] = set()
    for record in records:
        config_keys.update((record.get("training_config") or {}).keys())
    for param in params:
        name = param["name"]
        protocol_value = param["value"]
        if name in config_keys:
            experiment_values = sorted({
                str((r.get("training_config") or {}).get(name))
                for r in records
                if name in (r.get("training_config") or {})
            })
            if protocol_value is not None and experiment_values and any(v != str(protocol_value) for v in experiment_values):
                checks.append({
                    "type": "fact",
                    "message": f"参数 {name} 协议值={protocol_value}，实验配置={experiment_values}，存在偏离。",
                    "calculation": "对照 protocol_parameters.value 与 experiment_records.training_config 同名字段。",
                    "confidence": "medium",
                    "limitation": "仅匹配完全同名字段；未匹配的参数不判定偏离；不修改用户协议。",
                })

    metric_questions = [
        q for q in open_questions
        if isinstance(q, dict) and any(token in json.dumps(q, ensure_ascii=False).lower() for token in ("accuracy", "f1", "precision", "recall", "macro", "指标"))
    ]
    if not metric_questions:
        checks.append({
            "type": "fact",
            "message": "协议未明确量化评价指标阈值，无法判定实际指标是否符合预定要求。",
            "calculation": "扫描 protocol.open_questions 未发现指标相关条目。",
            "confidence": "medium",
            "limitation": "仅做关键词匹配；如指标记录在自由文本中可能漏检。",
        })

    return {
        "protocol_id": row["id"],
        "protocol_name": row["name"],
        "goal": row["goal"],
        "source_fields": source_fields,
        "checks": checks,
        "recommendations": recommendations,
    }
