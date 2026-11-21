"""Validation of split values, proportions, entity isolation and class coverage."""

from __future__ import annotations

from collections import Counter, defaultdict

from .audit_types import (
    CANONICAL_SPLITS,
    AuditMapping,
    AuditRow,
    Finding,
    is_missing,
    make_finding,
    split_of,
)

REFERENCE_RATIOS = {"Train": 0.70, "Validation": 0.15, "Test": 0.15}
RATIO_TOLERANCE = 0.20
MAX_GROUPS_IN_EVIDENCE = 25
MAX_ITEMS = 100


def _split_sort_key(name: str) -> tuple[int, str]:
    order = {"Train": 0, "Validation": 1, "Test": 2}
    return order.get(name, 3), name


def validate_split(
    rows: list[AuditRow], mapping: AuditMapping
) -> tuple[list[Finding], list[dict]]:
    findings: list[Finding] = []
    grouped = split_of(rows, mapping)
    split_counts = Counter({name: len(group) for name, group in grouped.items()})
    distribution = [
        {
            "split": name,
            "count": count,
            "percentage": round(count / len(rows) * 100, 6) if rows else 0.0,
            "supported": name in CANONICAL_SPLITS,
        }
        for name, count in sorted(split_counts.items(), key=lambda item: _split_sort_key(item[0]))
    ][:MAX_ITEMS]

    missing_rows = [row for row in rows if is_missing(row.values.get(mapping.split))]
    if missing_rows:
        findings.append(make_finding(
            rule_id="split_missing_value",
            severity="high",
            title="存在缺失的数据集合标记",
            description="部分数据行没有有效的 split 值，无法确认其属于 Train、Validation 或 Test。",
            rows=missing_rows,
            mapping=mapping,
            evidence={"fields": [mapping.split]},
            recommendation="补齐每行的数据集合标记，或在明确划分规则后重新生成集合字段。",
            status="confirmed_issue",
        ))

    unsupported_rows = [
        row for row in rows
        if not is_missing(row.values.get(mapping.split)) and mapping.split_for(row) not in CANONICAL_SPLITS
    ]
    if unsupported_rows:
        values = sorted({mapping.split_for(row) for row in unsupported_rows})
        findings.append(make_finding(
            rule_id="split_unsupported_value",
            severity="high",
            title="存在不支持的数据集合值",
            description="部分 split 值未映射为 Train、Validation 或 Test，当前值及原始行见证据。",
            rows=unsupported_rows,
            mapping=mapping,
            evidence={"fields": [mapping.split, "split_mapping"], "unsupported_values": values[:MAX_ITEMS]},
            recommendation="修正集合值，或在 split_mapping 中明确映射到受支持的集合。",
            status="confirmed_issue",
        ))

    deviations = []
    for name, reference in REFERENCE_RATIOS.items():
        count = split_counts.get(name, 0)
        if not count or not rows:
            continue
        actual = count / len(rows)
        deviation = actual - reference
        if abs(deviation) > RATIO_TOLERANCE:
            deviations.append({
                "split": name,
                "actual_ratio": round(actual, 6),
                "actual_percentage": round(actual * 100, 6),
                "reference_ratio": reference,
                "ratio_deviation": round(deviation, 6),
            })
    if deviations:
        findings.append(make_finding(
            rule_id="split_ratio_deviation",
            severity="low",
            title="数据集合比例偏离参考值",
            description="当前集合比例与 70%/15%/15% 的通用参考比例差异较大；该规则仅提供调整建议，不表示数据必然有误。",
            rows=[],
            mapping=mapping,
            evidence={
                "fields": [mapping.split],
                "affected_count": len(deviations),
                "reference_ratios": REFERENCE_RATIOS,
                "tolerance": RATIO_TOLERANCE,
                "deviations": deviations,
                "observed_distribution": distribution,
            },
            recommendation="结合样本量、评估设计和业务要求决定是否调整划分比例，无需仅因偏离参考值而修改。",
            status="suggestion",
        ))

    if mapping.entity_id:
        entities: dict[str, list[AuditRow]] = defaultdict(list)
        for row in rows:
            value = row.values.get(mapping.entity_id)
            if not is_missing(value) and not is_missing(row.values.get(mapping.split)):
                entities[value.strip()].append(row)
        overlap_groups = [
            group for group in entities.values()
            if len({mapping.split_for(row) for row in group}) > 1
        ]
        if overlap_groups:
            affected = [row for group in overlap_groups for row in group]
            group_evidence = [{
                "entity_id": group[0].values.get(mapping.entity_id, ""),
                "splits": sorted({mapping.split_for(row) for row in group})[:20],
                "row_numbers": [row.row_number for row in group[:20]],
                "record_ids": list(dict.fromkeys(
                    row.values.get(mapping.record_id, "") for row in group
                ))[:20],
            } for group in overlap_groups[:MAX_GROUPS_IN_EVIDENCE]]
            findings.append(make_finding(
                rule_id="split_entity_overlap",
                severity="critical",
                title="数据集合之间存在实体重叠",
                description="相同 entity_id 出现在多个集合，现有划分不能保证实体级独立性。",
                rows=affected,
                mapping=mapping,
                evidence={
                    "fields": [mapping.entity_id, mapping.split],
                    "overlap_entity_count": len(overlap_groups),
                    "groups": group_evidence,
                    "groups_truncated": len(overlap_groups) > MAX_GROUPS_IN_EVIDENCE,
                },
                recommendation="按 entity_id 分组重新划分，保证每个实体的全部记录只进入一个集合。",
                status="confirmed_issue",
            ))

    global_labels = {
        value.strip() for row in rows
        if not is_missing(value := row.values.get(mapping.label))
    }
    coverage = []
    for split, split_rows in sorted(grouped.items(), key=lambda item: _split_sort_key(item[0])):
        if not split:
            continue
        labels = {
            value.strip() for row in split_rows
            if not is_missing(value := row.values.get(mapping.label))
        }
        missing_labels = sorted(global_labels - labels)
        if missing_labels:
            coverage.append({
                "split": split,
                "row_count": len(split_rows),
                "missing_labels": missing_labels[:MAX_ITEMS],
                "missing_class_count": len(missing_labels),
                "present_labels": sorted(labels)[:MAX_ITEMS],
            })
    if coverage:
        findings.append(make_finding(
            rule_id="split_missing_class",
            severity="medium",
            title="部分集合未覆盖全部类别",
            description="某些集合缺少数据集中出现过的类别，可能影响训练或类别级评估，需结合样本量判断。",
            rows=[],
            mapping=mapping,
            evidence={
                "fields": [mapping.split, mapping.label],
                "affected_count": len(coverage),
                "global_class_count": len(global_labels),
                "split_details": coverage[:MAX_GROUPS_IN_EVIDENCE],
            },
            recommendation="小样本类别优先保证评估可解释性；必要时采用分层或分组分层划分，避免为凑比例制造泄漏。",
            status="potential_risk",
        ))

    return findings, distribution
