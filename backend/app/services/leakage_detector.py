"""Deterministic cross-split leakage checks with row-level evidence."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable

from .audit_types import AuditMapping, AuditRow, Finding, is_missing, make_finding

MAX_GROUPS_IN_EVIDENCE = 25
MAX_ITEMS_PER_GROUP = 10


def _cross_split_groups(rows: list[AuditRow], mapping: AuditMapping, key: Callable[[AuditRow], str | tuple[str, ...] | None]) -> list[list[AuditRow]]:
    grouped: dict[str | tuple[str, ...], list[AuditRow]] = defaultdict(list)
    for row in rows:
        value = key(row)
        if value is not None:
            grouped[value].append(row)
    return [
        group for group in grouped.values()
        if len({mapping.split_for(row) for row in group if not is_missing(row.values.get(mapping.split))}) > 1
    ]


def _group_evidence(groups: list[list[AuditRow]], mapping: AuditMapping, group_field: str) -> list[dict]:
    evidence = []
    for group in groups[:MAX_GROUPS_IN_EVIDENCE]:
        first = group[0]
        if group_field == "features":
            group_value: str | None = None
        else:
            group_value = first.values.get(group_field, "")
        evidence.append({
            "group_value": group_value,
            "row_count": len(group),
            "row_numbers": [row.row_number for row in group[:MAX_ITEMS_PER_GROUP]],
            "record_ids": list(dict.fromkeys(
                row.values.get(mapping.record_id, "") for row in group
            ))[:MAX_ITEMS_PER_GROUP],
            "entity_ids": list(dict.fromkeys(
                row.values.get(mapping.entity_id, "") for row in group
            ))[:MAX_ITEMS_PER_GROUP] if mapping.entity_id else [],
            "splits": sorted({mapping.split_for(row) for row in group})[:MAX_ITEMS_PER_GROUP],
        })
    return evidence


def _finding(
    *,
    rule_id: str,
    severity: str,
    title: str,
    description: str,
    groups: list[list[AuditRow]],
    mapping: AuditMapping,
    group_field: str,
    fields: list[str],
    recommendation: str,
) -> Finding | None:
    if not groups:
        return None
    affected = [row for group in groups for row in group]
    return make_finding(
        rule_id=rule_id,
        severity=severity,
        title=title,
        description=description,
        rows=affected,
        mapping=mapping,
        evidence={
            "fields": fields,
            "overlap_group_count": len(groups),
            "overlap_row_count": len(affected),
            "groups": _group_evidence(groups, mapping, group_field),
            "groups_truncated": len(groups) > MAX_GROUPS_IN_EVIDENCE,
        },
        recommendation=recommendation,
        status="confirmed_issue",
    )


def detect_leakage(rows: list[AuditRow], mapping: AuditMapping) -> list[Finding]:
    findings: list[Finding] = []

    if mapping.entity_id:
        def entity_key(row: AuditRow) -> str | None:
            value = row.values.get(mapping.entity_id or "")
            return None if is_missing(value) else value.strip()

        entity_groups = _cross_split_groups(rows, mapping, entity_key)
        entity_names = [
            group[0].values.get(mapping.entity_id, "").strip()
            for group in entity_groups[:MAX_ITEMS_PER_GROUP]
        ]
        finding = _finding(
            rule_id="leakage_entity_cross_split",
            severity="critical",
            title="同一实体出现在不同数据集合",
            description=(
                f"按明确映射的 entity_id 精确匹配后，确认同一实体跨越 Train/Test 或其他集合。涉及实体：{', '.join(entity_names)}。"
                "若研究设计要求实体独立评估，这违背划分要求并构成泄漏风险；未声明评估设计时保留重叠风险，不擅自推断研究设计。"
            ),
            groups=entity_groups,
            mapping=mapping,
            group_field=mapping.entity_id,
            fields=[mapping.entity_id, mapping.split],
            recommendation="以 entity_id 为最小分组单位重新划分数据，确保任一实体只属于一个集合。",
        )
        if finding:
            finding.evidence["fact_type"] = "entity_cross_split_observed"
            finding.evidence["design_interpretation"] = "conditional_on_entity_independence"
            findings.append(finding)

    def record_key(row: AuditRow) -> str | None:
        value = row.values.get(mapping.record_id)
        return None if is_missing(value) else value.strip()

    record_groups = _cross_split_groups(rows, mapping, record_key)
    finding = _finding(
        rule_id="leakage_record_id_cross_split",
        severity="critical",
        title="同一记录标识跨集合出现",
        description="相同 record_id 精确匹配到多个集合，相关原始行和集合信息已列入证据。",
        groups=record_groups,
        mapping=mapping,
        group_field=mapping.record_id,
        fields=[mapping.record_id, mapping.split],
        recommendation="核查记录复制和数据划分流程，确保同一 record_id 仅保留在一个集合中。",
    )
    if finding:
        findings.append(finding)

    def feature_key(row: AuditRow) -> tuple[str, ...] | None:
        if not mapping.feature_columns:
            return None
        values = tuple((row.values.get(column) or "").strip() for column in mapping.feature_columns)
        return None if all(is_missing(value) for value in values) else values

    feature_groups = _cross_split_groups(rows, mapping, feature_key)
    finding = _finding(
        rule_id="leakage_identical_features_cross_split",
        severity="high",
        title="完全相同的特征样本跨集合出现",
        description="不同集合中的记录具有完全相同的已映射特征向量，确认的是样本级重复风险；不同实体的相似特征不会被判定为患者级泄漏。",
        groups=feature_groups,
        mapping=mapping,
        group_field="features",
        fields=[*mapping.feature_columns, mapping.split],
        recommendation="回查这些行的原始样本来源并去重；若确属独立观测，应保留可验证的来源说明。",
    )
    if finding:
        findings.append(finding)

    return findings
