"""Deterministic multi-experiment comparison engine."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from .experiment_types import CORE_METRICS, METRIC_LABELS
from .stats_helpers import safe_mean

PP = 100.0  # percentage-point multiplier for deltas (metrics are stored in [0,1]).


def _record_label(record: dict[str, Any]) -> str:
    return record.get("experiment_id") or record.get("id") or "unknown"


def _group_runs(records: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[record["method"]].append(record)
    return grouped


def _comparability(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Describe whether ranking has a defensible common evaluation basis.

    A shared display name is not proof of a shared test set. Explicitly different
    known dataset/split/label/metric signatures suppress ranking; missing metadata
    keeps descriptive rankings but marks comparability as unverified.
    """
    reasons: list[str] = []
    incompatible = False
    dataset_ids = {r.get("dataset_ref_id") for r in records if r.get("dataset_ref_id")}
    dataset_names = {r.get("dataset") for r in records}
    if len(dataset_ids) > 1 or len(dataset_names) > 1:
        incompatible = True
        reasons.append("实验记录关联的数据集标识或名称不同，已禁止混合排名。")
    elif not dataset_ids or any(not r.get("dataset_ref_id") for r in records):
        reasons.append("部分记录缺少统一 dataset_ref_id；相同名称不能证明使用同一评估数据。")

    def extra_value(record: dict[str, Any], keys: tuple[str, ...]) -> Any:
        extra = record.get("extra_fields") or {}
        return next((extra[key] for key in keys if extra.get(key) not in (None, "")), None)

    splits = {str(value) for r in records if (value := extra_value(r, ("evaluation_split", "test_split", "split"))) is not None}
    if len(splits) > 1:
        incompatible = True
        reasons.append("评估样本/划分标识不同，已禁止混合排名。")
    elif len(splits) < 1:
        reasons.append("评估样本与划分未完整记录，可比性未核实。")

    metric_definitions = {
        str(value) for r in records
        if (value := extra_value(r, ("metric_definition", "metrics_definition"))) is not None
    }
    if len(metric_definitions) > 1:
        incompatible = True
        reasons.append("指标定义不同，已禁止混合排名。")
    elif not metric_definitions:
        reasons.append("指标均为 imported_summary；计算口径与评估样本未由预测结果重新核验。")

    label_sets: set[frozenset[str]] = set()
    for record in records:
        labels = record.get("confusion_labels") or list((record.get("per_class_metrics") or {}).keys())
        if labels:
            label_sets.add(frozenset(str(label) for label in labels))
    if len(label_sets) > 1:
        incompatible = True
        reasons.append("已声明的类别集合不同，已禁止混合排名。")

    return {
        "status": "incompatible" if incompatible else "unverified",
        "ranking_allowed": not incompatible,
        "ranking_suppressed": incompatible,
        "dataset_ids": sorted(dataset_ids),
        "evaluation_splits": sorted(splits),
        "metric_definitions": sorted(metric_definitions),
        "reasons": reasons or ["评估关联信息仍需人工复核。"],
        "note": "排名仅描述已录入汇总值，不证明统计显著、同一测试集或因果优势。",
    }


def compare_records(
    records: list[dict[str, Any]],
    baseline_method: str | None = None,
    primary_metric: str = "macro_f1",
) -> dict[str, Any]:
    if not records:
        return {"methods": [], "baseline": None, "metric_comparison": [], "rankings": [], "confusion": {}, "per_class": {}}

    grouped = _group_runs(records)
    methods = sorted(grouped.keys())
    baseline = baseline_method if baseline_method in grouped else methods[0]

    available_metrics = [m for m in CORE_METRICS if any(r.get(m) is not None for r in records)]
    if primary_metric not in available_metrics:
        primary_metric = available_metrics[0] if available_metrics else CORE_METRICS[0]

    method_stats: dict[str, dict[str, Any]] = {}
    for method in methods:
        runs = grouped[method]
        metrics: dict[str, Any] = {}
        for metric in available_metrics:
            values = [r.get(metric) for r in runs]
            metrics[metric] = {
                "mean": safe_mean(values),
                "values": [v for v in values if v is not None],
                "run_count": sum(1 for v in values if v is not None),
            }
        method_stats[method] = {
            "method": method,
            "model_name": next((r.get("model_name") for r in runs if r.get("model_name")), None),
            "dataset": runs[0]["dataset"],
            "run_count": len(runs),
            "seeds": sorted({r.get("seed") for r in runs if r.get("seed")}),
            "source_record_ids": [r.get("id") or r.get("experiment_id") for r in runs],
            "metrics": metrics,
        }

    baseline_stats = method_stats[baseline]
    metric_comparison: list[dict[str, Any]] = []
    for method in methods:
        stats = method_stats[method]
        row: dict[str, Any] = {"method": method, "is_baseline": method == baseline, "run_count": stats["run_count"]}
        for metric in available_metrics:
            mean_value = stats["metrics"][metric]["mean"]
            baseline_mean = baseline_stats["metrics"][metric]["mean"]
            delta_pp = None
            if mean_value is not None and baseline_mean is not None:
                delta_pp = round((mean_value - baseline_mean) * PP, 4)
            row[metric] = {
                "mean": round(mean_value, 6) if mean_value is not None else None,
                "delta_vs_baseline_pp": delta_pp,
                "values": [round(v, 6) for v in stats["metrics"][metric]["values"]],
            }
        metric_comparison.append(row)

    ranking_metric = primary_metric
    comparability = _comparability(records)
    rankable = [
        (method, method_stats[method]["metrics"][ranking_metric]["mean"])
        for method in methods
        if comparability["ranking_allowed"]
        and method_stats[method]["metrics"].get(ranking_metric, {}).get("mean") is not None
    ]
    rankable.sort(key=lambda item: item[1], reverse=True)
    rankings = [
        {
            "rank": idx + 1, "method": method, "metric": ranking_metric,
            "metric_label": METRIC_LABELS.get(ranking_metric, ranking_metric), "value": round(value, 6),
            "comparability": comparability["status"],
        }
        for idx, (method, value) in enumerate(rankable)
    ]

    confusion = _confusion_comparison(grouped, methods, baseline)
    per_class = _per_class_comparison(grouped, methods)

    return {
        "methods": methods,
        "baseline": baseline,
        "primary_metric": ranking_metric,
        "metric_comparison": metric_comparison,
        "rankings": rankings,
        "comparability": comparability,
        "confusion": confusion,
        "per_class": per_class,
        "macro_f1_definitions": {
            "run_level_mean": "metric_comparison[].macro_f1.mean：各 run 导入 Macro-F1 的算术均值",
            "aggregate_confusion": "confusion.macro_f1_from_confusion：先汇总混淆矩阵，再计算各类 F1 的算术均值",
            "note": "两者口径不同，不互相替代；单个方法的均值区间也不能证明方法间差异显著。",
        },
        "method_stats": {
            m: {
                "run_count": s["run_count"], "seeds": s["seeds"], "source_record_ids": s["source_record_ids"],
                "macro_f1_mean_of_runs": s["metrics"].get("macro_f1", {}).get("mean"),
            }
            for m, s in method_stats.items()
        },
    }


def _confusion_comparison(grouped: dict[str, list[dict[str, Any]]], methods: list[str], baseline: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "matrices": {}, "difference_vs_baseline": {}, "classes": {}, "labels": {},
        "per_class": {}, "macro_f1_from_confusion": {}, "issues": [],
        "aggregation": "先按有序 labels 同时重排行和列，再对各 run 矩阵逐单元格取均值。",
    }
    baseline_info = _mean_confusion(grouped.get(baseline, []))
    for method in methods:
        info = _mean_confusion(grouped[method])
        if info is None:
            continue
        matrix = info["matrix"]
        labels = info["labels"]
        result["issues"].extend(info["issues"])
        result["matrices"][method] = matrix
        result["labels"][method] = labels
        result["classes"][method] = len(matrix)
        per_class = _matrix_per_class(matrix, labels)
        result["per_class"][method] = per_class
        result["macro_f1_from_confusion"][method] = round(
            safe_mean(row["f1"] for row in per_class.values()) or 0.0, 6,
        )
        if baseline_info is not None and method != baseline:
            baseline_labels = baseline_info["labels"]
            if set(labels) != set(baseline_labels) or len(labels) != len(baseline_labels):
                result["issues"].append({
                    "method": method, "code": "incompatible_confusion_labels",
                    "message": "与 baseline 的类别集合不同，未计算矩阵差值。",
                })
                continue
            aligned = _reorder_matrix(matrix, labels, baseline_labels)
            baseline_matrix = baseline_info["matrix"]
            result["difference_vs_baseline"][method] = [
                [round(aligned[i][j] - baseline_matrix[i][j], 6) for j in range(len(aligned))]
                for i in range(len(aligned))
            ]
    return result


def _labels_for_run(run: dict[str, Any], size: int) -> list[str]:
    labels = run.get("confusion_labels")
    if isinstance(labels, list) and len(labels) == size and len(set(labels)) == size:
        return [str(label) for label in labels]
    per_class = list((run.get("per_class_metrics") or {}).keys())
    if len(per_class) == size:
        return [str(label) for label in per_class]
    return [f"class_{index}" for index in range(size)]


def _reorder_matrix(matrix: list[list[float]], source_labels: list[str], target_labels: list[str]) -> list[list[float]]:
    indices = [source_labels.index(label) for label in target_labels]
    return [[matrix[row][column] for column in indices] for row in indices]


def _mean_confusion(runs: list[dict[str, Any]]) -> dict[str, Any] | None:
    aligned: list[list[list[float]]] = []
    labels: list[str] | None = None
    issues: list[dict[str, Any]] = []
    for run in runs:
        matrix = run.get("confusion_matrix")
        if not matrix:
            continue
        size = len(matrix)
        if any(len(row) != size for row in matrix):
            issues.append({"code": "invalid_confusion_matrix", "message": "跳过非方阵混淆矩阵。", "record_id": _record_label(run)})
            continue
        run_labels = _labels_for_run(run, size)
        if labels is None:
            labels = run_labels
        if set(run_labels) != set(labels) or len(run_labels) != len(labels):
            issues.append({
                "code": "incompatible_confusion_labels", "record_id": _record_label(run),
                "message": "该 run 的类别集合与同方法其他 run 不同，未纳入汇总矩阵。",
            })
            continue
        aligned.append(_reorder_matrix(matrix, run_labels, labels))
    if not aligned or labels is None:
        return None
    size = len(labels)
    matrix = [
        [round(sum(item[i][j] for item in aligned) / len(aligned), 6) for j in range(size)]
        for i in range(size)
    ]
    return {"matrix": matrix, "labels": labels, "issues": issues, "run_count": len(aligned)}


def _matrix_per_class(matrix: list[list[float]], labels: list[str]) -> dict[str, dict[str, float]]:
    output: dict[str, dict[str, float]] = {}
    for index, label in enumerate(labels):
        tp = matrix[index][index]
        actual = sum(matrix[index])
        predicted = sum(row[index] for row in matrix)
        precision = tp / predicted if predicted else 0.0
        recall = tp / actual if actual else 0.0
        f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
        output[label] = {
            "precision": round(precision, 6), "recall": round(recall, 6),
            "f1": round(f1, 6), "support": round(actual, 6),
        }
    return output


def _per_class_comparison(grouped: dict[str, list[dict[str, Any]]], methods: list[str]) -> dict[str, Any]:
    classes: set[str] = set()
    for runs in grouped.values():
        for run in runs:
            classes.update((run.get("per_class_metrics") or {}).keys())
    class_list = sorted(classes)
    by_method: dict[str, Any] = {}
    for method in methods:
        runs = grouped[method]
        class_rows: dict[str, dict[str, float | None]] = {}
        for label in class_list:
            values_p = [r["per_class_metrics"][label]["precision"] for r in runs if label in (r.get("per_class_metrics") or {}) and "precision" in r["per_class_metrics"][label]]
            values_r = [r["per_class_metrics"][label]["recall"] for r in runs if label in (r.get("per_class_metrics") or {}) and "recall" in r["per_class_metrics"][label]]
            values_f = [r["per_class_metrics"][label]["f1"] for r in runs if label in (r.get("per_class_metrics") or {}) and "f1" in r["per_class_metrics"][label]]
            class_rows[label] = {
                "precision": round(safe_mean(values_p), 6) if values_p else None,
                "recall": round(safe_mean(values_r), 6) if values_r else None,
                "f1": round(safe_mean(values_f), 6) if values_f else None,
                "support": len(values_f),
            }
        by_method[method] = class_rows
    return {"classes": class_list, "by_method": by_method}
