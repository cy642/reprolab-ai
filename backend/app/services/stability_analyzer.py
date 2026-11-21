"""Multi-seed stability analysis (deterministic, stdlib statistics only)."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .experiment_types import CORE_METRICS
from .stats_helpers import describe

PRIMARY = "macro_f1"


def analyze_stability(records: list[dict[str, Any]]) -> dict[str, Any]:
    if not records:
        return {"groups": [], "summary": {"assessable_groups": 0, "single_seed_groups": 0, "total_runs": 0}}

    grouped: dict[tuple[str, str | None, str, str | None], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = (record["method"], record.get("model_name"), record["dataset"], record.get("dataset_ref_id"))
        grouped[key].append(record)

    groups: list[dict[str, Any]] = []
    assessable = 0
    single_seed = 0
    duplicate_seed_groups = 0
    for (method, model, dataset, dataset_ref_id), runs in sorted(
        grouped.items(), key=lambda item: tuple(str(value) for value in item[0]),
    ):
        by_seed: dict[str, list[dict[str, Any]]] = defaultdict(list)
        unseeded: list[dict[str, Any]] = []
        for run in runs:
            seed = run.get("seed")
            if seed in (None, ""):
                unseeded.append(run)
            else:
                by_seed[str(seed)].append(run)
        duplicate_seeds = sorted(seed for seed, seed_runs in by_seed.items() if len(seed_runs) > 1)
        independent_runs = [seed_runs[0] for seed, seed_runs in by_seed.items() if len(seed_runs) == 1]
        independent_runs.sort(key=lambda run: str(run.get("seed")))
        if duplicate_seeds:
            duplicate_seed_groups += 1

        metrics: dict[str, Any] = {}
        for metric in CORE_METRICS:
            stats = describe(run.get(metric) for run in independent_runs)
            if stats["count"] >= 1:
                metrics[metric] = stats
        independent_count = len(independent_runs)
        can_assess = independent_count >= 2 and any(stats["count"] >= 2 for stats in metrics.values())
        if can_assess:
            assessable += 1
        if independent_count <= 1:
            single_seed += 1

        if independent_count == 0:
            note = "没有可用于随机种子稳定性分析的非重复 seed 记录；重复评估不能扩大独立样本数。"
        elif independent_count == 1:
            note = "仅有 1 个非重复随机种子，无法评估随机种子稳定性，不输出区间，不能外推为稳定结论。"
        elif independent_count == 3:
            note = "仅基于 3 个非重复随机种子的有限描述；t 区间不代表统计显著或充分可靠。"
        else:
            note = (
                f"基于 {independent_count} 个非重复随机种子计算；n≥30 也不自动代表显著或可靠。"
                if independent_count >= 30
                else f"基于 {independent_count} 个非重复随机种子的有限描述；区间不证明统计显著。"
            )
        if duplicate_seeds:
            note += f" 重复 seed 已整组排除：{', '.join(duplicate_seeds)}。"
        if unseeded:
            note += f" {len(unseeded)} 条无 seed 记录未计入种子区间。"

        groups.append({
            "method": method,
            "model_name": model,
            "dataset": dataset,
            "dataset_ref_id": dataset_ref_id,
            "run_count": len(runs),
            "independent_run_count": independent_count,
            "seed_count": len(by_seed),
            "independent_seed_count": independent_count,
            "seeds": [str(run.get("seed")) for run in independent_runs],
            "duplicate_seeds": duplicate_seeds,
            "excluded_record_ids": [
                run.get("id") or run.get("experiment_id")
                for seed in duplicate_seeds for run in by_seed[seed]
            ] + [run.get("id") or run.get("experiment_id") for run in unseeded],
            "source_record_ids": [run.get("id") or run.get("experiment_id") for run in independent_runs],
            "metrics": metrics,
            "can_assess_stability": can_assess,
            "note": note,
        })

    return {
        "groups": groups,
        "summary": {
            "assessable_groups": assessable,
            "single_seed_groups": single_seed,
            "duplicate_seed_groups": duplicate_seed_groups,
            "total_runs": len(records),
            "independent_seeded_runs": sum(group["independent_run_count"] for group in groups),
            "method_count": len(grouped),
            "ci_method": "95% t-interval (mean ± t(α/2,n-1)·s/√n); n<2 不计算区间；重复/无 seed 记录不计入独立 n",
            "interpretation": "唯一 seed 只是去重规则，不能替代对独立实验设计与同一评估划分的核验。",
        },
    }
