"""Numeric feature quality, IQR and Train/Test distribution statistics."""

from __future__ import annotations

import math
import statistics

from .audit_types import AuditMapping, AuditRow, Finding, is_missing, make_finding

SMD_THRESHOLD = 0.2
MIN_IQR_VALUES = 4
MAX_FEATURES_IN_EVIDENCE = 50
MAX_SAMPLES_IN_EVIDENCE = 10


def _number(value: str | None) -> float | None:
    if value is None or not value.strip():
        return None
    try:
        return float(value.strip())
    except ValueError:
        return None


def _rounded(value: float | None) -> float | None:
    return round(value, 6) if value is not None else None


def _summary(values: list[float]) -> dict:
    if not values:
        return {
            "count": 0, "mean": None, "median": None, "std": None,
            "min": None, "max": None,
        }
    return {
        "count": len(values),
        "mean": _rounded(statistics.fmean(values)),
        "median": _rounded(statistics.median(values)),
        "std": _rounded(statistics.stdev(values) if len(values) > 1 else 0.0),
        "min": _rounded(min(values)),
        "max": _rounded(max(values)),
    }


def _finite_values(rows: list[AuditRow], column: str) -> list[float]:
    values = []
    for row in rows:
        number = _number(row.values.get(column))
        if number is not None and math.isfinite(number):
            values.append(number)
    return values


def _deduplicate_rows(rows: list[AuditRow]) -> list[AuditRow]:
    return list({row.row_number: row for row in rows}.values())


def inspect_features(
    rows: list[AuditRow], mapping: AuditMapping
) -> tuple[list[Finding], list[dict]]:
    findings: list[Finding] = []
    statistics_by_feature: list[dict] = []
    missing_details: list[dict] = []
    missing_rows: list[AuditRow] = []
    constant_details: list[dict] = []
    constant_rows: list[AuditRow] = []
    outlier_details: list[dict] = []
    outlier_rows: list[AuditRow] = []
    distribution_details: list[dict] = []

    for feature in mapping.feature_columns:
        present = [
            (row, (row.values.get(feature) or "").strip())
            for row in rows if not is_missing(row.values.get(feature))
        ]
        parsed = [(row, text, _number(text)) for row, text in present]
        numeric = bool(present) and all(number is not None for _, _, number in parsed)
        finite_pairs = [
            (row, number) for row, _, number in parsed
            if number is not None and math.isfinite(number)
        ] if numeric else []
        values = [number for _, number in finite_pairs]
        missing_count = sum(is_missing(row.values.get(feature)) for row in rows)
        non_finite_count = sum(
            (number := _number(row.values.get(feature))) is not None and not math.isfinite(number)
            for row in rows
        )
        constant = numeric and bool(values) and len(set(values)) == 1
        feature_stats = {
            "feature": feature,
            "column": feature,
            "numeric": numeric,
            "missing_count": missing_count,
            "missing_rate": round(missing_count / len(rows), 6) if rows else 0.0,
            "missing_percentage": round(missing_count / len(rows) * 100, 6) if rows else 0.0,
            "non_finite_count": non_finite_count,
            "finite_count": len(values),
            "constant": constant,
            **_summary(values),
            "q1": None,
            "q3": None,
            "iqr": None,
            "lower_fence": None,
            "upper_fence": None,
            "outlier_count": 0,
        }

        if missing_count:
            current = [row for row in rows if is_missing(row.values.get(feature))]
            missing_rows.extend(current)
            missing_details.append({
                "feature": feature,
                "missing_count": missing_count,
                "missing_rate": feature_stats["missing_rate"],
                "row_numbers": [row.row_number for row in current[:MAX_SAMPLES_IN_EVIDENCE]],
            })

        if constant:
            current = [row for row, _ in finite_pairs]
            constant_rows.extend(current)
            constant_details.append({
                "feature": feature,
                "value": _rounded(values[0]),
                "count": len(values),
            })

        if numeric and len(values) >= MIN_IQR_VALUES:
            q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
            iqr = q3 - q1
            lower_fence = q1 - 1.5 * iqr
            upper_fence = q3 + 1.5 * iqr
            outliers = [
                (row, number) for row, number in finite_pairs
                if number < lower_fence or number > upper_fence
            ]
            feature_stats.update({
                "q1": _rounded(q1),
                "q3": _rounded(q3),
                "iqr": _rounded(iqr),
                "lower_fence": _rounded(lower_fence),
                "upper_fence": _rounded(upper_fence),
                "outlier_count": len(outliers),
            })
            if outliers:
                outlier_rows.extend(row for row, _ in outliers)
                outlier_details.append({
                    "feature": feature,
                    "q1": _rounded(q1),
                    "q3": _rounded(q3),
                    "iqr": _rounded(iqr),
                    "lower_fence": _rounded(lower_fence),
                    "upper_fence": _rounded(upper_fence),
                    "outlier_count": len(outliers),
                    "samples": [{
                        "row_number": row.row_number,
                        "record_id": row.values.get(mapping.record_id, ""),
                        "split": mapping.split_for(row),
                        "value": _rounded(number),
                    } for row, number in outliers[:MAX_SAMPLES_IN_EVIDENCE]],
                })

        train_rows = [row for row in rows if mapping.split_for(row) == "Train"]
        test_rows = [row for row in rows if mapping.split_for(row) == "Test"]
        train_values = _finite_values(train_rows, feature) if numeric else []
        test_values = _finite_values(test_rows, feature) if numeric else []
        train_summary = _summary(train_values)
        test_summary = _summary(test_values)
        smd = None
        pooled_std = None
        mean_difference = None
        if train_values and test_values:
            train_mean = statistics.fmean(train_values)
            test_mean = statistics.fmean(test_values)
            mean_difference = test_mean - train_mean
            train_std = statistics.stdev(train_values) if len(train_values) > 1 else 0.0
            test_std = statistics.stdev(test_values) if len(test_values) > 1 else 0.0
            pooled_std = math.sqrt((train_std ** 2 + test_std ** 2) / 2)
            if pooled_std > 0:
                smd = mean_difference / pooled_std
            elif mean_difference == 0:
                smd = 0.0
        feature_stats.update({
            "train": train_summary,
            "test": test_summary,
            "mean_difference": _rounded(mean_difference),
            "pooled_std": _rounded(pooled_std),
            "standardized_mean_difference": _rounded(smd),
            "absolute_standardized_mean_difference": _rounded(abs(smd)) if smd is not None else None,
        })
        statistics_by_feature.append(feature_stats)

        if train_values and test_values:
            shifted = (
                smd is not None and abs(smd) >= SMD_THRESHOLD
            ) or (
                pooled_std == 0 and mean_difference is not None and mean_difference != 0
            )
            if shifted:
                distribution_details.append({
                    "feature": feature,
                    "train": train_summary,
                    "test": test_summary,
                    "mean_difference": _rounded(mean_difference),
                    "pooled_std": _rounded(pooled_std),
                    "standardized_mean_difference": _rounded(smd),
                    "absolute_standardized_mean_difference": _rounded(abs(smd)) if smd is not None else None,
                    "threshold": SMD_THRESHOLD,
                })

    if missing_details:
        findings.append(make_finding(
            rule_id="feature_missing_values",
            severity="medium",
            title="特征列存在缺失值",
            description="已映射特征中存在缺失单元格，缺失比例和真实行号见证据。",
            rows=_deduplicate_rows(missing_rows),
            mapping=mapping,
            evidence={
                "fields": [item["feature"] for item in missing_details],
                "features": missing_details[:MAX_FEATURES_IN_EVIDENCE],
            },
            recommendation="根据特征含义和缺失机制制定处理策略，并分别验证 Train/Test 的处理一致性。",
            status="confirmed_issue",
        ))

    if constant_details:
        findings.append(make_finding(
            rule_id="feature_constant",
            severity="medium",
            title="数值特征为常量",
            description="部分数值特征的有限取值全部相同，对监督学习通常没有区分度。",
            rows=_deduplicate_rows(constant_rows),
            mapping=mapping,
            evidence={
                "fields": [item["feature"] for item in constant_details],
                "features": constant_details[:MAX_FEATURES_IN_EVIDENCE],
            },
            recommendation="确认常量是否源于采集或转换错误；无业务用途的常量特征应排除。",
            status="confirmed_issue",
        ))

    if outlier_details:
        findings.append(make_finding(
            rule_id="feature_iqr_outlier",
            severity="low",
            title="数值特征存在 IQR 异常值",
            description="部分数值超出 1.5 倍 IQR 边界。异常值是统计现象，不等同于错误数据。",
            rows=_deduplicate_rows(outlier_rows),
            mapping=mapping,
            evidence={
                "fields": [item["feature"] for item in outlier_details],
                "method": "1.5 * IQR, inclusive quartiles",
                "features": outlier_details[:MAX_FEATURES_IN_EVIDENCE],
            },
            recommendation="结合量纲、采集过程和业务合理范围核查异常值，避免仅凭统计边界直接删除。",
            status="potential_risk",
        ))

    if distribution_details:
        findings.append(make_finding(
            rule_id="feature_distribution_shift",
            severity="medium",
            title="Train 与 Test 的数值特征分布存在差异",
            description="部分特征的 Train/Test 标准化均值差达到阈值。该发现仅描述分布差异和潜在风险，不据此认定数据泄漏。",
            rows=[],
            mapping=mapping,
            evidence={
                "fields": [item["feature"] for item in distribution_details],
                "affected_count": len(distribution_details),
                "smd_threshold": SMD_THRESHOLD,
                "features": distribution_details[:MAX_FEATURES_IN_EVIDENCE],
            },
            recommendation="核查样本来源、划分方式和预处理流程，并结合样本量及其他分布指标判断差异是否可接受。",
            status="potential_risk",
        ))

    return findings, statistics_by_feature
