"""Shared contracts for Experiment Insight deterministic engines.

A normalized record is a plain dict with the keys below so every engine and the
API layer can serialize it directly to JSON and SQLite text columns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CORE_METRICS = ("accuracy", "precision", "recall", "f1", "macro_f1", "weighted_f1")
METRIC_LABELS = {
    "accuracy": "Accuracy",
    "precision": "Precision",
    "recall": "Recall",
    "f1": "F1",
    "macro_f1": "Macro-F1",
    "weighted_f1": "Weighted-F1",
}

# Keys are stored normalized to these canonical names.
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "experiment_id": ("experiment_id", "run_id", "exp_id", "id"),
    "experiment_name": ("experiment_name", "name", "run_name"),
    "method": ("method", "approach", "strategy"),
    "model_name": ("model_name", "model", "backbone", "architecture"),
    "dataset": ("dataset", "dataset_name", "data"),
    "seed": ("seed", "random_seed", "seed_value"),
    "accuracy": ("accuracy", "acc"),
    "precision": ("precision", "prec"),
    "recall": ("recall", "rec", "sensitivity"),
    "f1": ("f1", "f1_score", "f1-score", "f1score"),
    "macro_f1": ("macro_f1", "macro_f1_score", "macro-f1", "macro_f1-score", "macrof1"),
    "weighted_f1": ("weighted_f1", "weighted_f1_score", "weighted-f1", "weighted_f1-score", "weightedf1"),
    "runtime": ("runtime", "run_time", "time", "duration"),
    "training_config": ("training_config", "config", "hyperparameters"),
    "confusion_matrix": ("confusion_matrix", "cm", "confusion"),
    "confusion_labels": ("confusion_labels", "class_labels", "labels"),
    "per_class_metrics": ("per_class_metrics", "class_metrics", "per_class"),
    "metrics_scale": ("metrics_scale", "scale"),
    "raw_metrics": ("raw_metrics",),
    "original_metrics_scale": ("original_metrics_scale",),
}


@dataclass(slots=True)
class NormalizeResult:
    records: list[dict[str, Any]]
    warnings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


def warn(code: str, message: str, **extra: Any) -> dict[str, Any]:
    item = {"code": code, "message": message}
    item.update(extra)
    return item


def error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    item = {"code": code, "message": message}
    item.update(extra)
    return item
