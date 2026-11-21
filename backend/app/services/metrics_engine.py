"""Parse, validate and normalize experiment result records (deterministic).

All metrics are stored normalized to the [0, 1] interval. Percentage inputs
(values > 1, or explicit ``metrics_scale='percent'``) are divided by 100 and the
conversion is recorded so percentages and fractions are never confused.
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from .experiment_types import (
    CORE_METRICS,
    FIELD_ALIASES,
    NormalizeResult,
    error,
    warn,
)

MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan", "-", "?"}


class ExperimentParseError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


def _decode(raw: bytes) -> str:
    if not raw:
        raise ExperimentParseError("empty_file", "文件为空，请上传包含实验记录的文件。")
    if b"\x00" in raw[:8192]:
        raise ExperimentParseError("binary_file", "文件包含二进制内容，不是有效的 CSV/JSON 文本。")
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ExperimentParseError("unsupported_encoding", "无法识别文件编码，请转换为 UTF-8 或 GB18030。")


def parse_experiment_csv(raw: bytes) -> list[dict[str, str]]:
    text = _decode(raw)
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    if not reader.fieldnames:
        raise ExperimentParseError("empty_file", "CSV 缺少表头。")
    rows = [dict(row) for row in reader]
    if not rows:
        raise ExperimentParseError("empty_dataset", "CSV 只有表头，没有数据行。")
    return rows


def parse_experiment_json(raw: bytes | str) -> list[dict[str, Any]]:
    if isinstance(raw, (bytes, bytearray)):
        text = _decode(bytes(raw))
    else:
        text = raw
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ExperimentParseError("invalid_json", f"JSON 解析失败：{exc.msg}") from exc
    if isinstance(data, dict):
        for key in ("records", "experiments", "data", "results"):
            if isinstance(data.get(key), list):
                data = data[key]
                break
        else:
            raise ExperimentParseError("invalid_json", "JSON 顶层必须是记录数组，或包含 records/experiments/data 数组。")
    if not isinstance(data, list):
        raise ExperimentParseError("invalid_json", "JSON 顶层必须是记录数组。")
    if not data:
        raise ExperimentParseError("empty_dataset", "JSON 记录数组为空。")
    if not all(isinstance(item, dict) for item in data):
        raise ExperimentParseError("invalid_json", "JSON 数组的每个元素必须是对象。")
    return data


def _lookup(raw: dict[str, Any], canonical: str) -> tuple[Any, str | None]:
    """Return (value, original_key) for the first matching alias (case-insensitive)."""
    lowered = {str(key).strip().lower(): key for key in raw.keys()}
    for alias in FIELD_ALIASES[canonical]:
        if alias in lowered:
            original = lowered[alias]
            return raw.get(original), original
    return None, None


def _to_float(value: Any) -> float | None | str:
    """Return float, None for missing, or the sentinel 'INVALID' for unparseable."""
    if value is None:
        return None
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if text.lower() in MISSING_TOKENS:
        return None
    if text.endswith("%"):
        text = text[:-1].strip()
    try:
        return float(text)
    except ValueError:
        return "INVALID"


def _parse_json_field(value: Any) -> Any:
    if value is None or value == "":
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            return None
    return None


def _normalize_per_class(raw: Any, as_percent: bool, row_index: int, warnings: list[dict]) -> dict[str, dict[str, float | None]] | None:
    parsed = _parse_json_field(raw)
    if parsed is None:
        return None
    if not isinstance(parsed, dict) or not parsed:
        warnings.append(warn("invalid_per_class", f"第 {row_index} 行 per_class_metrics 不是非空对象，已忽略。", row=row_index))
        return None
    out: dict[str, dict[str, float | None]] = {}
    for label, metrics in parsed.items():
        if not isinstance(metrics, dict):
            warnings.append(warn("invalid_per_class", f"类别 {label} 的指标不是对象，已忽略。", row=row_index))
            continue
        entry: dict[str, float | None] = {}
        for key in ("precision", "recall", "f1"):
            value = _to_float(metrics.get(key))
            if value == "INVALID":
                warnings.append(warn("invalid_per_class", f"类别 {label} 的 {key} 不是有效数字，已忽略。", row=row_index))
                value = None
            if isinstance(value, (int, float)):
                scaled = float(value) / 100.0 if as_percent else float(value)
                if not 0.0 <= scaled <= 1.0:
                    warnings.append(warn("out_of_range", f"类别 {label} 的 {key}={value} 超出 [0,1]（或 0-100）范围，已忽略。", row=row_index, field=key))
                    continue
                entry[key] = scaled
        if entry:
            out[str(label)] = entry
    return out or None


def _normalize_confusion_matrix(raw: Any, row_index: int, warnings: list[dict]) -> list[list[float]] | None:
    parsed = _parse_json_field(raw)
    if parsed is None:
        return None
    if not isinstance(parsed, list) or not parsed or not all(isinstance(row, list) for row in parsed):
        warnings.append(warn("invalid_confusion_matrix", f"第 {row_index} 行 confusion_matrix 不是二维数组，已忽略。", row=row_index))
        return None
    size = len(parsed)
    if any(len(row) != size for row in parsed):
        warnings.append(warn("invalid_confusion_matrix", f"第 {row_index} 行 confusion_matrix 不是方阵，已忽略。", row=row_index))
        return None
    matrix: list[list[float]] = []
    for row in parsed:
        clean: list[float] = []
        for cell in row:
            value = _to_float(cell)
            if value == "INVALID" or value is None:
                warnings.append(warn("invalid_confusion_matrix", f"第 {row_index} 行 confusion_matrix 含非法值，已忽略。", row=row_index))
                return None
            clean.append(float(value))
        matrix.append(clean)
    return matrix


def _confusion_labels(
    raw_labels: Any,
    matrix: list[list[float]] | None,
    per_class: dict[str, dict[str, float | None]] | None,
    row_index: int,
    warnings: list[dict],
) -> list[str] | None:
    if matrix is None:
        return None
    parsed = _parse_json_field(raw_labels)
    if parsed is None and per_class and len(per_class) == len(matrix):
        parsed = list(per_class.keys())
    if parsed is None:
        labels = [f"class_{index}" for index in range(len(matrix))]
        warnings.append(warn(
            "generated_confusion_labels",
            f"第 {row_index} 行未提供类别名称，按矩阵顺序生成 class_0… 标签；不代表真实类别语义。",
            row=row_index,
        ))
        return labels
    if not isinstance(parsed, list) or len(parsed) != len(matrix):
        warnings.append(warn(
            "invalid_confusion_labels", f"第 {row_index} 行 confusion_labels 数量与矩阵不一致，已生成顺序占位标签。",
            row=row_index,
        ))
        return [f"class_{index}" for index in range(len(matrix))]
    labels = [str(item).strip() for item in parsed]
    if any(not item for item in labels) or len(set(labels)) != len(labels):
        warnings.append(warn("invalid_confusion_labels", f"第 {row_index} 行类别标签为空或重复。", row=row_index))
        return [f"class_{index}" for index in range(len(matrix))]
    return labels


def normalize_records(raw_records: list[dict[str, Any]], explicit_scale: str | None = None) -> NormalizeResult:
    records: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen_keys: dict[tuple[str, str, str, str], dict[str, Any]] = {}

    for index, raw in enumerate(raw_records, start=1):
        method_value, _ = _lookup(raw, "method")
        dataset_value, _ = _lookup(raw, "dataset")
        method = str(method_value).strip() if method_value is not None else ""
        dataset = str(dataset_value).strip() if dataset_value is not None else ""
        if not method:
            errors.append(error("missing_required", f"第 {index} 行缺少必填字段 method。", row=index, field="method"))
            continue
        if not dataset:
            errors.append(error("missing_required", f"第 {index} 行缺少必填字段 dataset。", row=index, field="dataset"))
            continue

        experiment_id_value, _ = _lookup(raw, "experiment_id")
        experiment_id = str(experiment_id_value).strip() if experiment_id_value not in (None, "") else f"run_{index}"
        experiment_name_value, _ = _lookup(raw, "experiment_name")
        model_value, _ = _lookup(raw, "model_name")

        # Reuse original values when a preview record is confirmed, avoiding double conversion.
        stored_raw_metrics = raw.get("raw_metrics") if isinstance(raw.get("raw_metrics"), dict) else {}
        raw_metrics: dict[str, float | None] = {}
        invalid_fields: list[str] = []
        for metric in CORE_METRICS:
            raw_value = stored_raw_metrics.get(metric) if metric in stored_raw_metrics else _lookup(raw, metric)[0]
            parsed = _to_float(raw_value)
            if parsed == "INVALID":
                invalid_fields.append(metric)
                raw_metrics[metric] = None
            else:
                raw_metrics[metric] = parsed
        if invalid_fields:
            errors.append(error("invalid_metric_value", f"第 {index} 行指标不是有效数字：{', '.join(invalid_fields)}。", row=index, fields=invalid_fields))
            continue

        per_class_raw, _ = _lookup(raw, "per_class_metrics")
        has_per_class = per_class_raw not in (None, "")
        if not any(v is not None for v in raw_metrics.values()) and not has_per_class:
            errors.append(error("missing_metrics", f"第 {index} 行没有提供任何可识别的指标。", row=index))
            continue

        record_scale_field, _ = _lookup(raw, "metrics_scale")
        original_scale_field, _ = _lookup(raw, "original_metrics_scale")
        original_hint = str(original_scale_field).strip().lower() if original_scale_field not in (None, "") else None
        scale_hint = explicit_scale or original_hint
        if scale_hint in {"auto_percent", "auto_fraction"}:
            inferred_auto = scale_hint == "auto_percent"
            scale_hint = "percent" if inferred_auto else "fraction"
        else:
            inferred_auto = False
        if scale_hint in {None, ""}:
            scale_hint = str(record_scale_field).strip().lower() if record_scale_field not in (None, "") else None
        if scale_hint == "converted_from_percent":
            # Legacy preview values are already normalized; raw_metrics is the authoritative source when present.
            scale_hint = "percent" if stored_raw_metrics else "fraction"
            inferred_auto = True
        as_percent = scale_hint == "percent"
        ambiguous_scale = False
        if scale_hint not in (None, "", "percent", "fraction"):
            warnings.append(warn("unknown_scale", f"第 {index} 行 metrics_scale={scale_hint} 未知，需要明确确认。", row=index))
            scale_hint = None
        if scale_hint is None:
            as_percent = any(v is not None and v > 1.0 for v in raw_metrics.values())
            inferred_auto = as_percent
            ambiguous_scale = not as_percent and any(v == 1.0 for v in raw_metrics.values() if v is not None)
            if ambiguous_scale:
                errors.append(error(
                    "metrics_scale_confirmation_required",
                    f"第 {index} 行包含指标值 1；它可能表示 1% 或比例 1.0。请在导入确认时明确选择 percent 或 fraction。",
                    row=index,
                ))

        normalized_metrics: dict[str, float | None] = {}
        range_errors: list[str] = []
        for metric, raw_value in raw_metrics.items():
            if raw_value is None:
                normalized_metrics[metric] = None
                continue
            scaled = raw_value / 100.0 if as_percent else raw_value
            if not 0.0 <= scaled <= 1.0:
                range_errors.append(f"{metric}={raw_value}")
                normalized_metrics[metric] = None
            else:
                normalized_metrics[metric] = scaled
        if range_errors:
            errors.append(error("out_of_range", f"第 {index} 行指标超出合法范围 [0,1]（百分数应为 0-100）：{'; '.join(range_errors)}。", row=index, fields=range_errors))
            continue

        if scale_hint == "percent" and all(v is None or v <= 1.0 for v in raw_metrics.values() if v is not None) and any(v is not None for v in raw_metrics.values()):
            warnings.append(warn("percent_values_le_one", f"第 {index} 行标记为 percent，但数值均 ≤1，仍按百分数 ÷100 处理；请确认口径。", row=index))
        if scale_hint == "fraction" and any(v is not None and v > 1.0 for v in raw_metrics.values()):
            errors.append(error("out_of_range", f"第 {index} 行标记为 fraction，但存在 >1 的指标值。", row=index))
            continue

        seed_value, _ = _lookup(raw, "seed")
        seed: str | None = None
        if seed_value not in (None, ""):
            seed_text = str(seed_value).strip()
            try:
                int(seed_text)
                seed = seed_text
            except ValueError:
                try:
                    float(seed_text)
                    seed = seed_text
                    warnings.append(warn("non_integer_seed", f"第 {index} 行 seed={seed_text} 不是整数，已保留原值。", row=index))
                except ValueError:
                    warnings.append(warn("invalid_seed", f"第 {index} 行 seed={seed_text} 不是数字，已忽略；随机种子稳定性无法评估。", row=index))
                    seed = None
        else:
            warnings.append(warn("missing_seed", f"第 {index} 行缺少 random seed，无法评估随机种子稳定性。", row=index))

        per_class = _normalize_per_class(per_class_raw, as_percent, index, warnings)
        confusion_raw, _ = _lookup(raw, "confusion_matrix")
        confusion_matrix = _normalize_confusion_matrix(confusion_raw, index, warnings)
        labels_raw, _ = _lookup(raw, "confusion_labels")
        confusion_labels = _confusion_labels(labels_raw, confusion_matrix, per_class, index, warnings)
        training_raw, _ = _lookup(raw, "training_config")
        training_config = _parse_json_field(training_raw)
        if training_config is not None and not isinstance(training_config, dict):
            training_config = {"value": training_config}

        known_keys = {alias for aliases in FIELD_ALIASES.values() for alias in aliases}
        extra_fields = {key: value for key, value in raw.items() if str(key).strip().lower() not in known_keys}

        for metric, value in normalized_metrics.items():
            if value is None and metric not in ("f1",):
                warnings.append(warn("missing_metric", f"第 {index} 行缺少 {metric}。", row=index, field=metric))

        record: dict[str, Any] = {
            "experiment_id": experiment_id,
            "experiment_name": str(experiment_name_value).strip() if experiment_name_value not in (None, "") else None,
            "method": method,
            "model_name": str(model_value).strip() if model_value not in (None, "") else None,
            "dataset": dataset,
            "seed": seed,
            **normalized_metrics,
            "runtime": _to_float(_lookup(raw, "runtime")[0]) if _lookup(raw, "runtime")[0] not in (None, "") else None,
            "training_config": training_config or {},
            "confusion_matrix": confusion_matrix,
            "confusion_labels": confusion_labels,
            "per_class_metrics": per_class or {},
            "extra_fields": extra_fields,
            "metrics_scale": (
                "ambiguous_requires_confirmation" if ambiguous_scale
                else "converted_from_percent" if as_percent and inferred_auto
                else (scale_hint or "fraction")
            ),
            "raw_metrics": raw_metrics,
            "original_metrics_scale": (
                "ambiguous_requires_confirmation" if ambiguous_scale
                else (scale_hint if explicit_scale else original_hint or scale_hint)
                or ("auto_percent" if as_percent else "auto_fraction")
            ),
            "metric_source": "imported_summary",
        }
        if record["runtime"] == "INVALID":
            warnings.append(warn("invalid_runtime", f"第 {index} 行 runtime 不是有效数字，已忽略。", row=index))
            record["runtime"] = None

        key = (experiment_id, method, dataset, seed or "")
        if key in seen_keys:
            previous = seen_keys[key]
            same_metrics = all(record.get(m) == previous.get(m) for m in CORE_METRICS)
            if same_metrics:
                errors.append(error("duplicate_record", f"第 {index} 行与第 {previous['_row']} 行重复（experiment_id/method/dataset/seed 相同且指标一致）。", row=index, duplicate_of=previous["_row"]))
                continue
            warnings.append(warn("duplicate_key_different_metrics", f"第 {index} 行与第 {previous['_row']} 行 key 相同但指标不同。", row=index, duplicate_of=previous["_row"]))
        record["_row"] = index
        seen_keys[key] = record
        records.append(record)

    datasets = {r["dataset"] for r in records}
    if len(datasets) > 1:
        warnings.append(warn("mixed_datasets", f"本次导入包含多个数据集（{', '.join(sorted(datasets))}）；跨数据集比较无意义，请按 dataset 筛选。"))
    scales = {r.get("original_metrics_scale") for r in records}
    if len(scales) > 1:
        warnings.append(warn(
            "mixed_metrics_scales",
            "本次导入包含不同原始指标单位；每条记录按各自已确认单位独立归一化，原始值和单位均已保留。",
            scales=sorted(str(value) for value in scales),
        ))
    methods = {r["method"] for r in records}
    if len(methods) < 2:
        warnings.append(warn("single_method", "本次导入仅有一种方法，无法进行方法间对比。"))

    # Remove internal marker before returning.
    for record in records:
        record.pop("_row", None)
    return NormalizeResult(records=records, warnings=warnings, errors=errors)


def preview_records(result: NormalizeResult, limit: int = 20) -> list[dict[str, Any]]:
    """Return a display-safe preview subset (first `limit` records) with compact fields."""
    preview: list[dict[str, Any]] = []
    for record in result.records[:limit]:
        preview.append({
            "experiment_id": record["experiment_id"],
            "experiment_name": record.get("experiment_name"),
            "method": record["method"],
            "model_name": record.get("model_name"),
            "dataset": record["dataset"],
            "seed": record.get("seed"),
            "accuracy": record.get("accuracy"),
            "macro_f1": record.get("macro_f1"),
            "weighted_f1": record.get("weighted_f1"),
            "metrics_scale": record["metrics_scale"],
            "original_metrics_scale": record.get("original_metrics_scale"),
            "raw_metrics": record.get("raw_metrics") or {},
            "metric_source": record.get("metric_source") or "imported_summary",
            "confusion_labels": record.get("confusion_labels"),
            "has_confusion_matrix": bool(record.get("confusion_matrix")),
            "per_class_count": len(record.get("per_class_metrics") or {}),
        })
    return preview
