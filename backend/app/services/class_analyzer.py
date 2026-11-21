"""Class distribution statistics and non-categorical risk findings."""

from __future__ import annotations

from collections import Counter

from .audit_types import AuditMapping, AuditRow, Finding, is_missing, make_finding, split_of

MAX_CLASS_ITEMS = 200
MAX_SPLITS_IN_STATISTICS = 50
IMBALANCE_RATIO_THRESHOLD = 3.0
DISTRIBUTION_DIFFERENCE_THRESHOLD = 0.1


def _slices(counts: Counter[str], total: int) -> list[dict]:
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return [
        {
            "label": label,
            "count": count,
            "percentage": round(count / total * 100, 6) if total else 0.0,
        }
        for label, count in ordered[:MAX_CLASS_ITEMS]
    ]


def _label_counts(rows: list[AuditRow], mapping: AuditMapping) -> Counter[str]:
    return Counter(
        value.strip()
        for row in rows
        if not is_missing(value := row.values.get(mapping.label))
    )


def analyze_classes(
    rows: list[AuditRow], mapping: AuditMapping
) -> tuple[list[Finding], dict]:
    findings: list[Finding] = []
    counts = _label_counts(rows, mapping)
    labeled_count = sum(counts.values())
    overall = _slices(counts, labeled_count)
    grouped = split_of(rows, mapping)
    split_items = sorted(grouped.items(), key=lambda item: item[0])[:MAX_SPLITS_IN_STATISTICS]
    by_split = {}
    for split, split_rows in split_items:
        split_counts = _label_counts(split_rows, mapping)
        by_split[split] = _slices(split_counts, sum(split_counts.values()))

    min_label = min(counts, key=lambda label: (counts[label], label)) if counts else None
    max_label = max(counts, key=lambda label: (counts[label], label)) if counts else None
    min_count = counts[min_label] if min_label is not None else None
    max_count = counts[max_label] if max_label is not None else None
    imbalance_ratio = round(max_count / min_count, 6) if min_count else None

    train_counts = _label_counts(grouped.get("Train", []), mapping)
    test_counts = _label_counts(grouped.get("Test", []), mapping)
    train_total = sum(train_counts.values())
    test_total = sum(test_counts.values())
    train_test_by_label = []
    total_variation = 0.0
    max_percentage_point_difference = 0.0
    if train_total and test_total:
        labels = sorted(set(train_counts) | set(test_counts))
        for label in labels:
            train_fraction = train_counts[label] / train_total
            test_fraction = test_counts[label] / test_total
            difference = test_fraction - train_fraction
            total_variation += abs(difference)
            max_percentage_point_difference = max(
                max_percentage_point_difference, abs(difference) * 100
            )
            if len(train_test_by_label) < MAX_CLASS_ITEMS:
                train_test_by_label.append({
                    "label": label,
                    "train_count": train_counts[label],
                    "test_count": test_counts[label],
                    "train_percentage": round(train_fraction * 100, 6),
                    "test_percentage": round(test_fraction * 100, 6),
                    "percentage_point_difference": round(difference * 100, 6),
                })
        total_variation *= 0.5

    statistics = {
        "overall": overall,
        "counts": dict(sorted(counts.items())),
        "by_split": by_split,
        "total_rows": len(rows),
        "labeled_count": labeled_count,
        "missing_count": len(rows) - labeled_count,
        "category_count": len(counts),
        "min_label": min_label,
        "max_label": max_label,
        "min_count": min_count,
        "max_count": max_count,
        "imbalance_ratio": imbalance_ratio,
        "min_max_ratio": round(min_count / max_count, 6) if max_count else None,
        "train_test_difference": round(total_variation, 6),
        "train_test_total_variation": round(total_variation, 6),
        "train_test_max_percentage_point_difference": round(max_percentage_point_difference, 6),
        "train_test_by_label": train_test_by_label,
        "overall_truncated": len(counts) > MAX_CLASS_ITEMS,
    }

    if imbalance_ratio is not None and len(counts) > 1 and imbalance_ratio >= IMBALANCE_RATIO_THRESHOLD:
        findings.append(make_finding(
            rule_id="class_imbalance",
            severity="medium",
            title="类别分布存在潜在不平衡",
            description=f"最多类别与最少类别的样本数之比为 {imbalance_ratio:g}，这是统计上的潜在风险，并非已确认的建模失败。",
            rows=[],
            mapping=mapping,
            evidence={
                "fields": [mapping.label],
                "affected_count": len(counts),
                "min_label": min_label,
                "min_count": min_count,
                "max_label": max_label,
                "max_count": max_count,
                "imbalance_ratio": imbalance_ratio,
                "threshold": IMBALANCE_RATIO_THRESHOLD,
            },
            recommendation="按业务场景评估类别不平衡，考虑分层划分、合适指标或重采样，并保留原始分布记录。",
            status="potential_risk",
        ))

    if train_total and test_total and total_variation > DISTRIBUTION_DIFFERENCE_THRESHOLD:
        findings.append(make_finding(
            rule_id="class_distribution_shift",
            severity="medium",
            title="Train 与 Test 的类别分布存在差异",
            description=f"Train/Test 类别分布的总变差距离为 {total_variation:.6f}；该结果只表示统计差异，不能单独证明泄漏。",
            rows=[],
            mapping=mapping,
            evidence={
                "fields": [mapping.label, mapping.split],
                "affected_count": len(set(train_counts) | set(test_counts)),
                "train_test_difference": round(total_variation, 6),
                "threshold": DISTRIBUTION_DIFFERENCE_THRESHOLD,
                "by_label": train_test_by_label,
            },
            recommendation="核查划分是否分层以及各集合来源是否一致，并结合样本量和业务背景解释差异。",
            status="potential_risk",
        ))

    return findings, statistics
