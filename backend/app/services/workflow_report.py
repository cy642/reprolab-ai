"""Unified research report assembled from referenced business records.

The report is a pure projection of persisted business data: paper evidence,
protocol, audit findings, experiment comparison, and insight content. Every
number is copied (never recomputed) from the referenced record, and every
section lists the IDs it drew from so the report stays traceable.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from ..db import connect


def _loads(raw: Any) -> Any:
    if not raw:
        return {}
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, (int, float)):
        return f"{value:.{digits}f}"
    return str(value)


def _pct(value: Any) -> str:
    if value is None:
        return "—"
    try:
        return f"{float(value) * 100:.2f}%"
    except (TypeError, ValueError):
        return "—"


def _pp(value: Any) -> str:
    if value is None:
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:+.2f}pp"


def _fetch_one(sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
    with connect() as connection:
        row = connection.execute(sql, params).fetchone()
    return dict(row) if row else None


def _fetch_all(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def _json_columns(row: dict[str, Any], columns: tuple[str, ...]) -> dict[str, Any]:
    result = dict(row)
    for column in columns:
        if column in result:
            result[column] = _loads(result[column])
    return result


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def capture_workflow_snapshot(
    connection: Any,
    *,
    config: dict[str, Any],
    context: dict[str, Any],
    existing: dict[str, Any] | None = None,
    stage: str = "initial",
) -> dict[str, Any]:
    """Freeze the actual values needed to reproduce a report, not only references."""
    snapshot = json.loads(json.dumps(existing or {}, ensure_ascii=False))
    snapshot["schema_version"] = "workflow-input-v1"
    snapshot["config"] = dict(config)
    paper_id = context.get("paper_id") or config.get("paper_id")
    protocol_id = context.get("protocol_id")
    dataset_id = context.get("dataset_id") or config.get("dataset_id")
    audit_id = context.get("audit_id")
    comparison_id = context.get("comparison_id") or config.get("comparison_id")
    insight_id = context.get("insight_id")

    if paper_id and (stage == "paper_parse" or "paper" not in snapshot):
        row = connection.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if row:
            paper = dict(row)
            paper["fields"] = [dict(item) for item in connection.execute(
                "SELECT * FROM paper_fields WHERE paper_id = ? ORDER BY field", (paper_id,)
            ).fetchall()]
            paper["evidence"] = [dict(item) for item in connection.execute(
                "SELECT * FROM paper_evidence WHERE paper_id = ? ORDER BY page, rowid", (paper_id,)
            ).fetchall()]
            snapshot["paper"] = paper

    if protocol_id and (stage == "protocol_generate" or "protocol" not in snapshot):
        row = connection.execute("SELECT * FROM protocols WHERE id = ?", (protocol_id,)).fetchone()
        if row:
            protocol = _json_columns(dict(row), ("open_questions", "source_fields"))
            protocol["steps"] = [_json_columns(dict(item), ("dependencies", "required_inputs", "expected_outputs", "evidence_refs"))
                                 for item in connection.execute(
                "SELECT * FROM protocol_steps WHERE protocol_id = ? ORDER BY order_no, rowid", (protocol_id,)
            ).fetchall()]
            protocol["parameters"] = [_json_columns(dict(item), ("history",)) for item in connection.execute(
                "SELECT * FROM protocol_parameters WHERE protocol_id = ? ORDER BY order_no, rowid, name", (protocol_id,)
            ).fetchall()]
            snapshot["protocol"] = protocol

    if dataset_id and (stage == "data_audit" or "dataset" not in snapshot):
        row = connection.execute("SELECT * FROM datasets WHERE id = ?", (dataset_id,)).fetchone()
        if row:
            dataset = dict(row)
            mapping_row = connection.execute(
                "SELECT * FROM dataset_mappings WHERE dataset_id = ?", (dataset_id,)
            ).fetchone()
            dataset["mapping"] = (
                _json_columns(dict(mapping_row), ("feature_columns", "split_mapping")) if mapping_row else None
            )
            snapshot["dataset"] = dataset

    if audit_id and (stage == "data_audit" or "audit" not in snapshot):
        row = connection.execute("SELECT * FROM audit_runs WHERE id = ?", (audit_id,)).fetchone()
        if row:
            audit = _json_columns(dict(row), ("summary", "mapping_snapshot"))
            audit["findings"] = [_json_columns(
                dict(item), ("affected_rows", "affected_record_ids", "evidence")
            ) for item in connection.execute(
                "SELECT * FROM audit_findings WHERE audit_id = ? ORDER BY rowid", (audit_id,)
            ).fetchall()]
            snapshot["audit"] = audit

    if comparison_id and (stage == "experiment_analyze" or "comparison" not in snapshot):
        row = connection.execute("SELECT * FROM experiment_comparisons WHERE id = ?", (comparison_id,)).fetchone()
        if row:
            snapshot["comparison"] = _json_columns(
                dict(row), ("experiment_ids", "metrics", "rankings", "stability", "ablation")
            )

    experiment_ids = list(config.get("experiment_ids") or [])
    if not experiment_ids and snapshot.get("comparison"):
        experiment_ids = list(snapshot["comparison"].get("experiment_ids") or [])
    if experiment_ids and (stage == "experiment_analyze" or "experiments" not in snapshot):
        placeholders = ",".join("?" for _ in experiment_ids)
        rows = connection.execute(
            f"SELECT * FROM experiment_records WHERE id IN ({placeholders}) ORDER BY created_at, rowid",
            tuple(experiment_ids),
        ).fetchall()
        snapshot["experiments"] = [_json_columns(dict(item), (
            "training_config", "confusion_matrix", "per_class_metrics", "extra_fields",
            "confusion_labels", "raw_metrics",
        )) for item in rows]
        snapshot["requested_experiment_ids"] = experiment_ids

    if insight_id and (stage == "experiment_analyze" or "insight" not in snapshot):
        row = connection.execute("SELECT * FROM insight_reports WHERE id = ?", (insight_id,)).fetchone()
        if row:
            snapshot["insight"] = _json_columns(dict(row), ("experiment_ids", "content"))

    snapshot["captured_at"] = datetime.now(timezone.utc).isoformat()
    version_content = {key: value for key, value in snapshot.items() if key not in {"captured_at", "input_version"}}
    snapshot["input_version"] = hashlib.sha256(_canonical(version_content).encode("utf-8")).hexdigest()
    return snapshot


def build_workflow_report(
    context: dict[str, Any],
    *,
    workflow: dict[str, Any] | None = None,
    nodes: list[dict[str, Any]] | None = None,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    use_snapshot = bool(snapshot)
    snapshot = snapshot or {}
    paper_id = context.get("paper_id")
    protocol_id = context.get("protocol_id")
    dataset_id = context.get("dataset_id")
    audit_id = context.get("audit_id")
    comparison_id = context.get("comparison_id")
    insight_id = context.get("insight_id")

    sections: list[dict[str, Any]] = []
    references: dict[str, Any] = {
        "paper_id": paper_id,
        "evidence_ids": [],
        "protocol_id": protocol_id,
        "dataset_id": dataset_id,
        "audit_id": audit_id,
        "comparison_id": comparison_id,
        "insight_id": insight_id,
        "experiment_ids": [],
    }

    # 1. workflow overview -------------------------------------------------- #
    overview_lines = []
    if workflow:
        overview_lines.extend(
            [
                f"- 工作流：{workflow.get('name')}（`{workflow.get('id')}`）",
                f"- 类型：{workflow.get('workflow_type')}",
                f"- 状态：{workflow.get('status')}",
                f"- 创建时间：{workflow.get('created_at')}",
            ]
        )
    if nodes:
        skipped = [node["node_key"] for node in nodes if node["status"] == "skipped"]
        completed = [node["node_key"] for node in nodes if node["status"] == "completed"]
        overview_lines.append(f"- 完成节点：{', '.join(completed) if completed else '无'}")
        overview_lines.append(f"- 跳过节点：{', '.join(skipped) if skipped else '无'}")
    overview_lines.append("- 状态语义：workflow_completed 仅表示流程执行结束，不表示实验科学有效或训练复现已完成。")
    overview_lines.append("- 报告范围：本地报告定稿；未上传到任何外部服务。")
    if snapshot.get("input_version"):
        overview_lines.append(f"- 固定输入版本：`{snapshot['input_version']}`")
    sections.append(
        {
            "title": "工作流概览",
            "kind": "overview",
            "lines": overview_lines or ["- 无工作流元数据"],
            "refs": [workflow.get("id")] if workflow else [],
        }
    )

    # 2. paper evidence ----------------------------------------------------- #
    if use_snapshot:
        paper = snapshot.get("paper")
        evidence = (paper or {}).get("evidence", [])
    else:
        paper = _fetch_one("SELECT * FROM papers WHERE id = ?", (paper_id,)) if paper_id else None
        evidence = _fetch_all(
            "SELECT id, field, page, quote FROM paper_evidence WHERE paper_id = ? ORDER BY rowid ASC", (paper_id,)
        ) if paper_id else []
    references["evidence_ids"] = [item["id"] for item in evidence]
    paper_lines: list[str] = []
    if paper:
        paper_lines.append(f"- 论文：{paper['title']}（`{paper['id']}`）")
        paper_lines.append(f"- 解析状态：{paper['parse_status']} · 抽取方式：{paper['extraction_method']} · AI：{paper['ai_status']}")
        paper_lines.append(f"- 内容 SHA256：`{paper.get('sha256') or '未知'}`")
        paper_lines.append(f"- 证据条数：{len(evidence)}")
        for item in evidence[:12]:
            quote = (item["quote"] or "").replace("\n", " ")[:120]
            paper_lines.append(f"  - [{item['field']}] p.{item['page']}：{quote}（`{item['id']}`）")
        if len(evidence) > 12:
            paper_lines.append(f"  - …其余 {len(evidence) - 12} 条证据见论文证据库")
    else:
        paper_lines.append("- 未关联论文（该步骤被跳过或工作流为分析方法型）")
    sections.append({"title": "论文与证据", "kind": "paper", "lines": paper_lines, "refs": [paper_id] if paper_id else []})

    # 3. protocol ----------------------------------------------------------- #
    if use_snapshot:
        protocol = snapshot.get("protocol")
        steps = (protocol or {}).get("steps", [])
        params = (protocol or {}).get("parameters", [])
    else:
        protocol = _fetch_one("SELECT * FROM protocols WHERE id = ?", (protocol_id,)) if protocol_id else None
        steps = _fetch_all("SELECT * FROM protocol_steps WHERE protocol_id = ? ORDER BY order_no ASC", (protocol_id,)) if protocol_id else []
        params = _fetch_all("SELECT * FROM protocol_parameters WHERE protocol_id = ? ORDER BY order_no ASC", (protocol_id,)) if protocol_id else []
    protocol_lines: list[str] = []
    if protocol:
        protocol_lines.append(f"- 方案：{protocol['name']}（`{protocol['id']}`）")
        protocol_lines.append(f"- 固定协议版本：`{protocol.get('latest_version_id') or '内容快照（无版本 ID）'}`")
        protocol_lines.append(f"- 目标：{protocol['goal'] or '—'}")
        protocol_lines.append(f"- 步骤（{len(steps)}）：" + "；".join(f"{s['title']}[{s['status']}]" for s in steps))
        protocol_lines.append(
            f"- 参数（{len(params)}）：" + "；".join(f"{p['name']}={p['value']}" for p in params)
        )
    else:
        protocol_lines.append("- 未关联实验方案（该步骤被跳过或工作流为分析方法型）")
    sections.append({"title": "实验方案与参数", "kind": "protocol", "lines": protocol_lines, "refs": [protocol_id] if protocol_id else []})

    # 4. data audit --------------------------------------------------------- #
    if use_snapshot:
        audit = snapshot.get("audit")
        findings = (audit or {}).get("findings", [])
    else:
        audit = _fetch_one("SELECT * FROM audit_runs WHERE id = ?", (audit_id,)) if audit_id else None
        findings = _fetch_all("SELECT * FROM audit_findings WHERE audit_id = ? ORDER BY rowid ASC", (audit_id,)) if audit_id else []
    audit_lines: list[str] = []
    data_validation_skipped = audit is None
    if audit:
        by_severity: dict[str, int] = {}
        for finding in findings:
            by_severity[finding["severity"]] = by_severity.get(finding["severity"], 0) + 1
        audit_lines.append(f"- 审计记录：`{audit['id']}` · 数据集 `{audit['dataset_id']}`")
        audit_lines.append("- 严重度分布：" + "；".join(f"{k}={v}" for k, v in sorted(by_severity.items())))
        for finding in findings[:15]:
            rows = finding.get("affected_rows") or []
            records = finding.get("affected_record_ids") or []
            audit_lines.append(
                f"  - [{finding['severity']}] {finding['title']}（`{finding['id']}` / {finding['rule_id']}）"
                f" · 状态 {finding.get('status') or 'open'} · 行 {rows[:8]} · 记录 {records[:8]}"
            )
        if len(findings) > 15:
            audit_lines.append(f"  - …其余 {len(findings) - 15} 条见 Data Guardian 审计详情")
    else:
        audit_lines.append("- ⚠️ 未执行数据质量审计：本报告不包含数据泄漏/重复/不平衡等验证结论，不得据此声称数据可用。")
    sections.append({"title": "数据质量审计", "kind": "audit", "lines": audit_lines, "refs": [audit_id] if audit_id else []})

    # 5. comparison --------------------------------------------------------- #
    if use_snapshot:
        comparison = snapshot.get("comparison")
    else:
        comparison = _fetch_one(
            "SELECT * FROM experiment_comparisons WHERE id = ?", (comparison_id,)
        ) if comparison_id else None
    comparison_lines: list[str] = []
    if comparison:
        metrics = _loads(comparison["metrics"])
        rankings = _loads(comparison["rankings"])
        references["experiment_ids"] = _loads(comparison["experiment_ids"])
        comparison_lines.append(f"- 对比记录：`{comparison['id']}` · 状态：{comparison['status']}")
        comparison_lines.append(f"- 参与实验：{len(references['experiment_ids'])} 条")
        methods = metrics.get("metric_comparison", []) if isinstance(metrics, dict) else []
        for row in methods:
            mf1 = row.get("macro_f1") or {}
            acc = row.get("accuracy") or {}
            comparison_lines.append(
                f"  - {row.get('method')}：Accuracy {_pct(acc.get('mean'))} · Macro-F1 {_pct(mf1.get('mean'))}"
                f" · Δ(主指标) {_pp(mf1.get('delta_vs_baseline_pp'))}"
            )
        if isinstance(rankings, list) and rankings:
            top = rankings[0]
            comparison_lines.append(f"- 主指标排名第一：{top.get('method')}（{_fmt(top.get('value'))}）")
    else:
        comparison_lines.append("- 未生成实验对比记录。")
    sections.append({"title": "实验结果与指标对比", "kind": "comparison", "lines": comparison_lines, "refs": [comparison_id] if comparison_id else []})

    # 6. insight ------------------------------------------------------------ #
    if use_snapshot:
        insight = snapshot.get("insight")
    else:
        insight = _fetch_one("SELECT * FROM insight_reports WHERE id = ?", (insight_id,)) if insight_id else None
    insight_content = _loads(insight["content"]) if insight else {}
    insight_lines: list[str] = []
    ai_status = insight["ai_status"] if insight else "not_used"
    if insight:
        insight_lines.append(f"- 洞察记录：`{insight['id']}`")
        insight_lines.append(
            "- AI 状态：" + ("本次洞察使用确定性分析" if ai_status == "not_used" else ai_status)
        )
        for claim in insight_content.get("key_observations", []):
            insight_lines.append(f"  - [{claim.get('claim_type')}] {claim.get('claim')}（置信度 {claim.get('confidence_level')}）")
        stability = insight_content.get("stability_analysis", {}).get("groups", [])
        for group in stability:
            stats = group.get("metrics", {}).get("macro_f1")
            if not stats:
                continue
            ci = stats.get("confidence_interval")
            ci_text = f" 95% CI [{_fmt(ci['lower'])}, {_fmt(ci['upper'])}]" if ci else " 无置信区间（n<2）"
            insight_lines.append(
                f"  - 稳定性 {group.get('method')}：n={stats.get('count')} mean={_fmt(stats.get('mean'))} std={_fmt(stats.get('std'))}{ci_text}"
            )
        warnings = insight_content.get("data_quality_warnings", [])
        if warnings:
            insight_lines.append(f"- 数据质量风险（来自 Data Guardian）：{len(warnings)} 条")
            for warning in warnings[:8]:
                insight_lines.append(
                    f"  - [{warning.get('severity')}] {warning.get('title')}（audit `{warning.get('audit_id')}` / finding `{warning.get('finding_id')}`）"
                )
    else:
        insight_lines.append("- 未生成科研洞察。")
    sections.append({"title": "AI 科研洞察", "kind": "insight", "lines": insight_lines, "refs": [insight_id] if insight_id else []})

    # 7. risk, limitations, and provenance --------------------------------- #
    high_risk = [
        item for item in findings
        if item.get("severity") in {"critical", "high"} and item.get("status") not in {"resolved", "fixed"}
    ]
    high_risk_ids = [item["id"] for item in high_risk]
    approvals = (workflow or {}).get("approvals", [])
    risk_acknowledged = any(
        item.get("decision") == "approve"
        and item.get("risk_acknowledged")
        and item.get("audit_id") == audit_id
        and set(high_risk_ids).issubset(set(item.get("finding_ids") or []))
        for item in approvals
    )
    if risk_acknowledged:
        audit_lines.append("- 人工决定：已知悉上述风险并继续分析；该决定不代表 finding 已修复或审计通过。")

    limitation_lines: list[str] = [
        *[f"- {item}" for item in insight_content.get("limitations", [])],
    ]
    if nodes:
        for node in nodes:
            if node["status"] == "skipped":
                limitation_lines.append(f"- 跳过步骤：{node['title']}（{node.get('error') or '输入缺失或可选'}）")
    if data_validation_skipped:
        limitation_lines.append("- 数据验证未执行：结论不覆盖数据泄漏、重复样本与类别不平衡风险。")
    if high_risk:
        limitation_lines.append(
            f"- 仍有 {len(high_risk)} 条 critical/high 发现未解决；批准继续仅表示知悉风险。"
            "结论必须结合上述行/记录定位，不能解释为审计通过或研究设计已验证。"
        )
    limitation_lines.append("- 单方法均值区间不构成两方法差异显著的证据；本报告未执行显著性检验。")
    sections.append({"title": "局限性与未完成事项", "kind": "limitations", "lines": limitation_lines, "refs": []})

    if use_snapshot:
        experiments = snapshot.get("experiments", [])
    elif references["experiment_ids"]:
        ids = references["experiment_ids"]
        placeholders = ",".join("?" for _ in ids)
        experiments = [_json_columns(item, ("extra_fields",)) for item in _fetch_all(
            f"SELECT * FROM experiment_records WHERE id IN ({placeholders})", tuple(ids)
        )]
    else:
        experiments = []
    sources = sorted({
        "simulated" if item.get("is_simulated") else (item.get("data_source") or "unknown")
        for item in experiments
    })
    if not sources:
        sources = ["simulated"] if insight_content.get("experimental_summary", {}).get("is_simulated") else ["unknown"]
    data_source = sources[0] if len(sources) == 1 else "mixed"
    simulated = "simulated" in sources
    metric_sources = sorted({item.get("metric_source") or "imported_summary" for item in experiments})

    execution_modes: dict[str, str] = {}
    llm_requests: dict[str, list[dict[str, Any]]] = {}
    for node in nodes or []:
        output = node.get("output_ref") or {}
        if isinstance(output, str):
            output = _loads(output)
        mode = output.get("execution_mode")
        if not mode:
            if node["status"] == "skipped":
                mode = "skipped"
            elif node.get("requires_approval"):
                mode = "automatic_validation" if output.get("auto_approved") else "human_review"
            elif node["node_key"] == "data_audit":
                mode = "deterministic_rules"
            else:
                mode = "reused_rule" if output.get("reused") else "rule_compute"
        execution_modes[node["node_key"]] = mode
        if output.get("llm_requests"):
            llm_requests[node["node_key"]] = output["llm_requests"]

    provenance_lines = [
        f"- 论文：`{paper_id or '未关联'}`",
        f"- 证据：{len(references['evidence_ids'])} 条",
        f"- 协议：`{protocol_id or '未关联'}`",
        f"- 数据集：`{dataset_id or '未关联'}`",
        f"- 审计：`{audit_id or '未执行'}`",
        f"- 对比：`{comparison_id or '未生成'}`",
        f"- 洞察：`{insight_id or '未生成'}`",
        f"- 数据来源：{data_source}（明细：{', '.join(sources)}）；is_simulated=0 本身不证明真实来源。",
        f"- 指标记录来源：{', '.join(metric_sources) if metric_sources else 'unknown'}；对比计算由 Python 确定性引擎完成。",
        f"- 节点执行方式：{json.dumps(execution_modes, ensure_ascii=False, sort_keys=True)}",
        f"- 输入快照：`{snapshot.get('input_version') or '历史运行未保存快照'}`",
        "- 定稿范围：仅本地定稿，未执行外部发布。",
    ]
    if llm_requests:
        provenance_lines.append(f"- 模型请求记录：{json.dumps(llm_requests, ensure_ascii=False, sort_keys=True)}")
    sections.append({"title": "来源追溯与声明", "kind": "provenance", "lines": provenance_lines, "refs": []})

    coverage = _loads((audit or {}).get("summary")).get("rule_coverage", {})
    mapping_snapshot = _loads((audit or {}).get("mapping_snapshot")) or {}
    dataset_snapshot = snapshot.get("dataset") or {}
    audit_inputs_match = bool(
        audit
        and audit.get("dataset_sha256")
        and audit.get("dataset_sha256") == dataset_snapshot.get("sha256")
        and audit.get("engine_version") == "1.1.0"
    )
    audit_passed = bool(
        audit
        and audit.get("status") == "completed"
        and not high_risk
        and coverage
        and all(status == "completed" for status in coverage.values())
        and mapping_snapshot.get("entity_id")
        and audit_inputs_match
    )

    return {
        "workflow": workflow or {},
        "sections": sections,
        "references": references,
        "is_simulated": simulated,
        "data_validation_skipped": data_validation_skipped,
        "ai_status": ai_status,
        "data_source": data_source,
        "data_sources": sources,
        "execution_modes": execution_modes,
        "risk_summary": {
            "finding_count": len(findings),
            "unresolved_high_risk_count": len(high_risk),
            "unresolved_high_risk_ids": high_risk_ids,
            "risk_acknowledged": risk_acknowledged,
            "audit_passed": audit_passed,
        },
        "snapshot_version": snapshot.get("input_version"),
        "finalization_scope": "local_finalization",
    }


def build_workflow_report_markdown(report: dict[str, Any]) -> str:
    workflow = report.get("workflow") or {}
    title = workflow.get("name") or "科研复现报告"
    lines: list[str] = [f"# {title}", ""]
    data_source = report.get("data_source") or ("simulated" if report.get("is_simulated") else "unknown")
    lines.extend([f"> 数据来源：{data_source}；未知来源不会被解释为真实实验数据。", ""])
    if report.get("is_simulated"):
        lines.extend(["> 警告：本报告包含模拟数据（SIMULATED），仅用于流程演示，不代表真实实验结果。", ""])
    if report.get("data_validation_skipped"):
        lines.extend(["> 警告：本次工作流未执行数据质量审计，数据可用性未经验证。", ""])
    risk = report.get("risk_summary") or {}
    if risk.get("unresolved_high_risk_count"):
        lines.extend([
            f"> 警告：仍有 {risk['unresolved_high_risk_count']} 条 critical/high 风险未解决；批准继续不代表审计通过。",
            "",
        ])
    lines.extend(["> 本报告仅为本地定稿，未上传外部；流程完成不等于科学有效或训练复现完成。", ""])
    if report.get("ai_status") == "not_used":
        lines.extend(["> 说明：本次 Insight 未调用 LLM，结果为确定性分析；其他节点执行方式见来源追溯。", ""])

    for section in report.get("sections", []):
        lines.append(f"## {section['title']}")
        lines.extend(section.get("lines", []))
        refs = [ref for ref in section.get("refs", []) if ref]
        if refs:
            lines.append("")
            lines.append(f"*来源：{', '.join(f'`{ref}`' for ref in refs)}*")
        lines.append("")
    return "\n".join(lines).strip() + "\n"
