"""Deterministic Markdown/JSON experiment report builder.

All numbers come from the already-computed insight content; this module only
formats them. It never invents metrics.
"""

from __future__ import annotations

from typing import Any


def _fmt(value: Any, digits: int = 4) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _pp(value: Any) -> str:
    if value is None:
        return "—"
    sign = "+" if value > 0 else ""
    return f"{sign}{value:.2f} pp"


def build_report_json(content: dict[str, Any], insight_id: str | None = None) -> dict[str, Any]:
    payload = {
        "report_version": "1.0",
        "generated_by": "Experiment Insight deterministic engine",
        "insight_id": insight_id,
        "deterministic": True,
        **content,
    }
    return payload


def build_report_markdown(content: dict[str, Any], insight_id: str | None = None) -> str:
    summary = content.get("experimental_summary", {})
    is_simulated = bool(content.get("is_simulated") or summary.get("is_simulated"))
    data_label = "模拟数据（明确标注，仅用于功能演示，非真实训练结果）" if is_simulated else "真实实验数据"
    lines: list[str] = []
    lines.append("# Experiment Insight 科研分析报告")
    lines.append("")
    if insight_id:
        lines.append(f"> insight_id: `{insight_id}`  ")
    lines.append(f"> 数据标记：**{data_label}**  ")
    lines.append("> 本报告全部数值由 Python 确定性引擎计算，AI 仅补充叙述与建议，未生成指标。")
    lines.append("")

    protocol = content.get("protocol_alignment") or {}
    lines.append("## 1. 实验背景")
    lines.append("")
    if protocol:
        lines.append(f"- 关联协议：{protocol.get('protocol_name')} (`{protocol.get('protocol_id')}`)")
        if protocol.get("goal"):
            lines.append(f"- 实验目标：{protocol['goal']}")
    lines.append(f"- 数据集：{', '.join(summary.get('datasets', [])) or '—'}")
    lines.append(f"- 方法数：{len(summary.get('methods', []))}；baseline：`{summary.get('baseline') or '—'}`；主指标：`{summary.get('primary_metric')}`")
    lines.append("")

    lines.append("## 2. 实验设置")
    lines.append("")
    lines.append(f"- 实验记录数：{summary.get('experiment_count', 0)}")
    lines.append(f"- 方法：{', '.join(summary.get('methods', []))}")
    lines.append("")

    warnings = content.get("data_quality_warnings", [])
    lines.append("## 3. 数据质量审计")
    lines.append("")
    if not warnings:
        lines.append("未关联 Data Guardian 审计结果，或未发现匹配的高风险 finding。")
    else:
        lines.append("| audit_id | finding_id | rule_id | severity | 标题 |")
        lines.append("|---|---|---|---|---|")
        for f in warnings:
            lines.append(f"| {f.get('audit_id')} | {f.get('finding_id')} | {f.get('rule_id')} | {f.get('severity')} | {f.get('title')} |")
    lines.append("")

    comparison = content.get("metric_comparisons", {})
    metric_rows = comparison.get("metric_comparison", [])
    primary = comparison.get("primary_metric")
    lines.append("## 4. 实验结果与指标对比")
    lines.append("")
    if metric_rows:
        metrics_in_table = [m for m in ("accuracy", "macro_f1", "weighted_f1", "precision", "recall") if any(m in row for row in metric_rows)]
        header = "| 方法 | " + " | ".join(metrics_in_table) + " |"
        sep = "|" + "|".join(["---"] * (len(metrics_in_table) + 1)) + "|"
        lines.append(header)
        lines.append(sep)
        for row in metric_rows:
            cells = [row["method"]]
            for m in metrics_in_table:
                block = row.get(m, {})
                cells.append(f"{_fmt(block.get('mean'))} ({_pp(block.get('delta_vs_baseline_pp'))})")
            lines.append("| " + " | ".join(cells) + " |")
        lines.append("")
        lines.append("（括号内为相对 baseline 的百分点变化。）")
    lines.append("")

    rankings = comparison.get("rankings", [])
    if rankings:
        lines.append("### 排名（按主指标）")
        lines.append("")
        lines.append("| 排名 | 方法 | 指标 | 值 |")
        lines.append("|---|---|---|---|")
        for r in rankings:
            lines.append(f"| {r['rank']} | {r['method']} | {r.get('metric')} | {_fmt(r.get('value'))} |")
        lines.append("")

    stability = content.get("stability_analysis", {})
    lines.append("## 5. 多随机种子稳定性分析")
    lines.append("")
    groups = stability.get("groups", [])
    if not groups:
        lines.append("无可评估的分组。")
    for g in groups:
        lines.append(f"### {g['method']}（seeds={g.get('seeds')}, n={g['run_count']}）")
        lines.append("")
        lines.append("| 指标 | mean | std | min | max | 95% CI | 可评估 |")
        lines.append("|---|---|---|---|---|---|---|")
        for metric, stats in (g.get("metrics") or {}).items():
            ci = stats.get("confidence_interval") or {}
            ci_text = f"[{_fmt(ci.get('lower'))}, {_fmt(ci.get('upper'))}]" if ci else "— (n<2)"
            lines.append(f"| {metric} | {_fmt(stats.get('mean'))} | {_fmt(stats.get('std'))} | {_fmt(stats.get('min'))} | {_fmt(stats.get('max'))} | {ci_text} | {'是' if g.get('can_assess_stability') else '否'} |")
        lines.append("")
        lines.append(f"> {g.get('note')}")
        lines.append("")
    if stability.get("summary"):
        lines.append(f"> 置信区间方法：{stability['summary'].get('ci_method')}")
        lines.append("")

    ablation = content.get("ablation_analysis", {})
    lines.append("## 6. 消融实验分析")
    lines.append("")
    lines.append(f"- baseline：`{ablation.get('baseline') or '—'}`")
    lines.append(f"- 含组件开关字段：{'是' if ablation.get('has_component_flags') else '否'}")
    for item in ablation.get("comparisons", []):
        lines.append(f"- **{item['method']}** vs baseline：")
        for metric, delta in (item.get("deltas") or {}).items():
            lines.append(f"  - {metric}: {_pp(delta.get('delta_pp'))}")
        if item.get("config_changes"):
            lines.append(f"  - 配置变化：{'; '.join(item['config_changes'])}")
    lines.append("")
    for lim in ablation.get("limitations", []):
        lines.append(f"- 局限：{lim}")
    lines.append("")

    lines.append("## 7. AI 科研洞察（确定性生成）")
    lines.append("")
    for claim in content.get("key_observations", []):
        lines.append(f"- **[{claim.get('claim_type')}]** {claim.get('claim')}")
        lines.append(f"  - 证据：{claim.get('evidence')}")
        lines.append(f"  - 计算：{claim.get('calculation')}")
        lines.append(f"  - 置信度：{claim.get('confidence_level')}；局限：{claim.get('limitation')}")
    lines.append("")

    lines.append("## 8. 局限性")
    lines.append("")
    for lim in content.get("limitations", []):
        lines.append(f"- {lim}")
    lines.append("")

    lines.append("## 9. 后续实验建议")
    lines.append("")
    for rec in content.get("recommendations", []):
        tag = "[AI]" if rec.get("ai_generated") else "[确定性]"
        lines.append(f"- {tag} {rec.get('message')}")
    lines.append("")

    return "\n".join(lines)
