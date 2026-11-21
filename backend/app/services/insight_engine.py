"""Insight Agent: structured, traceable scientific insight from computed results.

Every numeric claim is derived from the deterministic engines. The LLM (when
configured) may only add free-text narrative and recommendations; it never
alters computed metrics. Without an LLM the full structured output is produced
deterministically (ai_status='not_used').
"""

from __future__ import annotations

import json
from typing import Any

from ..config import get_settings
from .llm_provider import LLMError, LLMProvider

OBSERVED = "observed_fact"
STATISTICAL = "statistical_finding"
HYPOTHESIS = "hypothesis"
RECOMMENDATION = "recommendation"

SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3, "info": 4}


def _confidence_for(run_count: int, claim_type: str) -> str:
    if claim_type == HYPOTHESIS:
        return "low"
    if claim_type == RECOMMENDATION:
        return "medium"
    if run_count >= 5:
        return "high"
    if run_count >= 2:
        return "medium"
    return "low"


def _claim(claim_type: str, text: str, evidence: str, calculation: str, limitation: str, confidence: str) -> dict[str, Any]:
    return {
        "claim_type": claim_type,
        "claim": text,
        "evidence": evidence,
        "calculation": calculation,
        "confidence_level": confidence,
        "limitation": limitation,
    }


def build_insight(
    records: list[dict[str, Any]],
    comparison: dict[str, Any],
    stability: dict[str, Any],
    ablation: dict[str, Any],
    data_quality_warnings: list[dict[str, Any]],
    protocol_alignment: dict[str, Any] | None,
) -> dict[str, Any]:
    methods = comparison.get("methods", [])
    baseline = comparison.get("baseline")
    primary = comparison.get("primary_metric", "macro_f1")
    metric_rows = {row["method"]: row for row in comparison.get("metric_comparison", [])}
    claims: list[dict[str, Any]] = []

    # --- experimental summary ---
    datasets = sorted({r["dataset"] for r in records})
    data_sources = sorted({
        r.get("data_source") or ("simulated" if r.get("is_simulated") else "unknown")
        for r in records
    })
    simulated = bool(records) and data_sources == ["simulated"]
    has_demo_data = any(source in {"simulated", "test"} for source in data_sources)
    if len(data_sources) > 1:
        data_label = f"混合来源（{', '.join(data_sources)}），未视为统一真实实验集合"
    elif simulated:
        data_label = "模拟数据（明确标注，仅用于功能演示）"
    elif data_sources == ["test"]:
        data_label = "测试数据（仅用于验收）"
    elif data_sources == ["real"]:
        data_label = "用户声明为真实实验；系统未独立核验来源"
    else:
        data_label = "数据来源未知，不能据 is_simulated=0 推断为真实"
    summary = {
        "experiment_count": len(records),
        "methods": methods,
        "datasets": datasets,
        "baseline": baseline,
        "primary_metric": primary,
        "is_simulated": simulated,
        "has_demo_data": has_demo_data,
        "data_sources": data_sources,
        "metric_sources": sorted({r.get("metric_source") or "imported_summary" for r in records}),
        "data_label": data_label,
    }

    # --- observed facts: method vs baseline deltas ---
    for method in methods:
        row = metric_rows.get(method, {})
        run_count = row.get("run_count", 0)
        metric_block = row.get(primary, {})
        mean_value = metric_block.get("mean")
        delta = metric_block.get("delta_vs_baseline_pp")
        if method == baseline:
            claims.append(_claim(
                OBSERVED,
                f"{method} 作为 baseline，{primary} 均值为 {mean_value}。",
                f"baseline={method}; source_record_ids={comparison.get('method_stats', {}).get(method, {}).get('source_record_ids')}",
                f"mean({primary}) = 该方法 {run_count} 次运行的算术平均",
                "均值不代表跨种子稳定性，需结合置信区间判断。",
                _confidence_for(run_count, OBSERVED),
            ))
        else:
            direction = "提升" if (delta or 0) >= 0 else "下降"
            claims.append(_claim(
                OBSERVED,
                f"{method} 的 {primary} 均值为 {mean_value}，相对 baseline {baseline} {direction} {abs(delta) if delta is not None else '?'} 个百分点。",
                f"methods=[{baseline}, {method}]; source_record_ids={comparison.get('method_stats', {}).get(method, {}).get('source_record_ids')}",
                f"delta_pp = (mean_{method} - mean_{baseline}) × 100 = {delta}",
                "百分点差异为观察值，不构成统计显著或因果结论。",
                _confidence_for(run_count, OBSERVED),
            ))

    # --- statistical findings: multi-seed stability ---
    for group in stability.get("groups", []):
        if not group.get("can_assess_stability"):
            continue
        metric = group["metrics"].get(primary)
        if not metric or metric.get("mean") is None:
            continue
        ci = metric.get("confidence_interval") or {}
        claims.append(_claim(
            STATISTICAL,
            f"{group['method']} 在 {group['independent_seed_count']} 个非重复随机种子上 {primary} 均值={metric['mean']:.6f}，标准差={metric['std']:.6f}，95% CI=[{ci.get('lower'):.6f}, {ci.get('upper'):.6f}]。",
            f"seeds={group['seeds']}; source_record_ids={group['source_record_ids']}",
            f"n={metric['count']}; std(ddof=1)={metric['std']:.6f}; CI={ci.get('method')}",
            ci.get("note", "样本量有限，区间宽度可能不稳定，不得外推为统计显著。"),
            _confidence_for(group["independent_run_count"], STATISTICAL),
        ))

    # --- ablation: observed deltas + guarded hypotheses ---
    for item in ablation.get("comparisons", []):
        deltas = item.get("deltas", {})
        primary_delta = deltas.get(primary, {})
        if primary_delta:
            claims.append(_claim(
                OBSERVED,
                f"消融对比：{item['method']} 相对 baseline {ablation.get('baseline')} 的 {primary} 变化 {primary_delta.get('delta_pp')} pp。",
                f"source_record_ids={item.get('source_record_ids')}",
                f"delta_pp = (method_mean - baseline_mean) × 100 = {primary_delta.get('delta_pp')}",
                "未提供组件开关时不推断独立贡献；相关性不等于因果。",
                _confidence_for(len(item.get("source_record_ids", [])), OBSERVED),
            ))
        if item.get("config_changes") and primary_delta:
            claims.append(_claim(
                HYPOTHESIS,
                f"假设：{item['method']} 的配置变化（{'; '.join(item['config_changes'][:2])}）可能与 {primary} 变化相关，但需组件级消融验证。",
                f"config_differences={item['config_changes']}",
                "观察到配置差异与指标差异共存；未做孤立变量控制。",
                "这是待验证假设，不是实验事实；不得写入结论性表述。",
                "low",
            ))

    # --- data quality warnings (from Data Guardian) ---
    sorted_warnings = sorted(data_quality_warnings, key=lambda f: SEVERITY_RANK.get(f.get("severity", "info"), 9))
    for finding in sorted_warnings:
        claims.append(_claim(
            OBSERVED,
            f"[数据质量] {finding.get('title')}：{finding.get('description')}",
            f"audit_id={finding.get('audit_id')}; finding_id={finding.get('finding_id')}; rule_id={finding.get('rule_id')}; severity={finding.get('severity')}",
            "由 Data Guardian 确定性规则计算得出，定位到具体 finding。",
            "即使实验指标较高，该数据质量风险仍可能影响结论可信度。",
            "high" if finding.get("severity") in ("critical", "high") else "medium",
        ))

    # --- protocol alignment ---
    limitations: list[str] = list(ablation.get("limitations", []))
    limitations.extend(comparison.get("comparability", {}).get("reasons", []))
    limitations.append("方法间差值仅为观察结果；单个方法的均值区间不能作为两方法差异显著的证明。")
    recommendations: list[dict[str, Any]] = []
    if protocol_alignment:
        for item in protocol_alignment.get("checks", []):
            claim_type = OBSERVED if item.get("type") == "fact" else (RECOMMENDATION if item.get("type") == "recommendation" else HYPOTHESIS)
            claims.append(_claim(
                claim_type,
                item["message"],
                f"protocol_id={protocol_alignment.get('protocol_id')}",
                item.get("calculation", "对照协议目标/参数/步骤与实际实验记录"),
                item.get("limitation", "只读读取协议，未修改用户原有实验方案。"),
                item.get("confidence", "medium"),
            ))
        recommendations.extend(protocol_alignment.get("recommendations", []))

    # --- generic recommendations from stability gaps ---
    for group in stability.get("groups", []):
        if group.get("independent_seed_count", 0) < 3:
            recommendations.append({
                "type": RECOMMENDATION,
                "target": group["method"],
                "message": f"为 {group['method']} 增加至少 3 个（建议 5+）独立随机种子，以评估稳定性并缩小置信区间。",
                "evidence": f"current_independent_seed_count={group['independent_seed_count']}",
                "ai_generated": False,
            })
    if not any(w.get("severity") in ("critical", "high") for w in data_quality_warnings) and data_quality_warnings:
        recommendations.append({"type": RECOMMENDATION, "target": "data", "message": "复核 Data Guardian 审计中的中低风险项，并在报告中披露数据局限性。", "evidence": f"audit_findings={len(data_quality_warnings)}", "ai_generated": False})

    content = {
        "experimental_summary": summary,
        "key_observations": claims,
        "metric_comparisons": comparison,
        "stability_analysis": stability,
        "ablation_analysis": ablation,
        "data_quality_warnings": sorted_warnings,
        "protocol_alignment": protocol_alignment,
        "limitations": limitations,
        "recommendations": recommendations,
        "is_simulated": simulated,
    }
    return content


def enrich_with_llm(content: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Optionally enrich narrative text with an LLM. Never mutates metrics."""
    settings = get_settings()
    if not settings.llm_configured:
        content["ai_note"] = "未配置 LLM；全部洞察由确定性引擎生成，未调用 AI。"
        return content, "not_used"
    summary = content.get("experimental_summary", {})
    prompt_payload = {
        "summary": summary,
        "top_observations": [c["claim"] for c in content.get("key_observations", [])[:8]],
        "data_quality_warnings": content.get("data_quality_warnings", [])[:8],
        "protocol_alignment": content.get("protocol_alignment", {}),
        "limitations": content.get("limitations", [])[:5],
        "instructions": "仅基于上述已计算结果撰写 3-5 句中文科研叙述（narrative）并补充 1-3 条下一步实验建议（recommendations）。保留审计风险和统计限制，不得编造任何数值，不得把假设写成事实，必须标注模拟数据。返回 JSON：{narrative, recommendations:[{message}]}.",
    }
    try:
        parsed = LLMProvider().complete_json(
            "你是严谨的科研分析助手，只能复述已给的计算结果，禁止编造数值。",
            json.dumps(prompt_payload, ensure_ascii=False),
        )
    except LLMError:
        content["ai_note"] = "LLM 调用失败或未配置；已回退到确定性洞察，数值未受影响。"
        return content, "failed_fallback"
    if not isinstance(parsed, dict):
        content["ai_note"] = "LLM 返回格式无效；已忽略 AI 文本，保留确定性结果。"
        return content, "failed_fallback"
    narrative = parsed.get("narrative")
    if not isinstance(narrative, str) or not narrative.strip():
        content["ai_note"] = "LLM 未返回可用叙述；已保留确定性结果。"
        return content, "failed_fallback"
    content["narrative"] = narrative.strip()
    extra = parsed.get("recommendations")
    if isinstance(extra, list):
        for item in extra:
            if isinstance(item, dict) and item.get("message"):
                content.setdefault("recommendations", []).append({
                    "type": RECOMMENDATION,
                    "message": str(item["message"])[:400],
                    "target": "general",
                    "evidence": "ai_generated_from_computed_results",
                    "ai_generated": True,
                })
    content["ai_note"] = "LLM 仅补充叙述与建议；所有数值仍由 Python 确定性引擎计算。"
    return content, "llm_enriched"
