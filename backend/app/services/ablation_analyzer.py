"""Ablation analysis: observed config-level metric deltas, no causal overclaim."""

from __future__ import annotations

from typing import Any

from .comparison_engine import compare_records
from .experiment_types import CORE_METRICS
from .stats_helpers import safe_mean

PP = 100.0


def analyze_ablation(records: list[dict[str, Any]], baseline_method: str | None = None) -> dict[str, Any]:
    comparison = compare_records(records, baseline_method=baseline_method)
    methods = comparison["methods"]
    if not methods:
        return {"baseline": None, "comparisons": [], "config_differences": [], "limitations": []}

    baseline = comparison["baseline"]
    by_method_runs: dict[str, list[dict[str, Any]]] = {}
    for record in records:
        by_method_runs.setdefault(record["method"], []).append(record)

    config_differences = _diff_configs(by_method_runs)
    comparisons: list[dict[str, Any]] = []
    for method in methods:
        if method == baseline:
            continue
        deltas: dict[str, Any] = {}
        for metric in CORE_METRICS:
            base = safe_mean([r.get(metric) for r in by_method_runs.get(baseline, [])])
            current = safe_mean([r.get(metric) for r in by_method_runs.get(method, [])])
            if base is not None and current is not None:
                deltas[metric] = {
                    "baseline_mean": round(base, 6),
                    "method_mean": round(current, 6),
                    "delta_pp": round((current - base) * PP, 4),
                }
        comparisons.append({
            "method": method,
            "baseline": baseline,
            "deltas": deltas,
            "config_changes": config_differences.get(method, []),
            "source_record_ids": [r.get("id") or r.get("experiment_id") for r in by_method_runs.get(method, [])],
        })

    has_component_flags = any(
        any(_looks_like_component_flag(key) for key in (r.get("training_config") or {}).keys())
        for runs in by_method_runs.values() for r in runs
    )
    limitations = [
        "未提供显式组件开关（ablation flags）时，不推断任一组件的独立贡献；上述差异为观察到的指标相关性。",
        "指标差异可能由随机种子、数据划分、超参数或实现细节共同导致，相关性不等于因果关系。",
        "单次或低重复实验的差异不得外推为稳定结论；请结合稳定性分析的置信区间判断。",
    ]
    if not has_component_flags:
        limitations.insert(0, "当前配置未包含组件开关字段，本分析仅比较方法整体指标变化，不拆解组件贡献。")

    return {
        "baseline": baseline,
        "comparisons": comparisons,
        "config_differences": config_differences,
        "has_component_flags": has_component_flags,
        "limitations": limitations,
    }


def _looks_like_component_flag(key: str) -> bool:
    lowered = str(key).lower()
    return any(token in lowered for token in ("ablation", "use_", "enable", "disable", "with_", "without", "module", "component", "loss_", "augment"))


def _diff_configs(by_method_runs: dict[str, list[dict[str, Any]]]) -> dict[str, list[str]]:
    """List training_config keys whose values differ across methods."""
    representative: dict[str, Any] = {}
    for method, runs in by_method_runs.items():
        config = next((r.get("training_config") for r in runs if r.get("training_config")), {})
        representative[method] = config or {}
    all_keys: set[str] = set()
    for config in representative.values():
        all_keys.update(config.keys())
    methods = sorted(representative.keys())
    if len(methods) < 2:
        return {m: [] for m in methods}
    baseline_method = methods[0]
    base_config = representative[baseline_method]
    result: dict[str, list[str]] = {m: [] for m in methods}
    for key in sorted(all_keys):
        base_value = base_config.get(key)
        for method in methods[1:]:
            value = representative[method].get(key)
            if value != base_value:
                result[method].append(f"{key}: {base_value!r} → {value!r}")
    return result
