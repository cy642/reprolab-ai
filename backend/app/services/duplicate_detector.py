"""Deterministic duplicate detection at row, record and feature level."""

from __future__ import annotations

from collections import defaultdict
from typing import Callable, Hashable

from .audit_types import AuditMapping, AuditRow, Finding, is_missing, make_finding

MAX_GROUPS_IN_EVIDENCE = 25
MAX_ITEMS_PER_GROUP = 10


def _groups(rows: list[AuditRow], key: Callable[[AuditRow], Hashable | None]) -> list[list[AuditRow]]:
    grouped: dict[Hashable, list[AuditRow]] = defaultdict(list)
    for row in rows:
        fingerprint = key(row)
        if fingerprint is not None:
            grouped[fingerprint].append(row)
    return [group for group in grouped.values() if len(group) > 1]


def _feature_key(row: AuditRow, mapping: AuditMapping) -> tuple[str, ...] | None:
    if not mapping.feature_columns:
        return None
    values = tuple((row.values.get(column) or "").strip() for column in mapping.feature_columns)
    if all(is_missing(value) for value in values):
        return None
    return values


def _group_evidence(groups: list[list[AuditRow]], mapping: AuditMapping) -> list[dict]:
    return [
        {
            "row_count": len(group),
            "row_numbers": [row.row_number for row in group[:MAX_ITEMS_PER_GROUP]],
            "record_ids": list(dict.fromkeys(
                row.values.get(mapping.record_id, "") for row in group
            ))[:MAX_ITEMS_PER_GROUP],
            "splits": sorted({mapping.split_for(row) for row in group})[:MAX_ITEMS_PER_GROUP],
        }
        for group in groups[:MAX_GROUPS_IN_EVIDENCE]
    ]


def _finding(
    *,
    rule_id: str,
    severity: str,
    title: str,
    description: str,
    groups: list[list[AuditRow]],
    mapping: AuditMapping,
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
            "duplicate_group_count": len(groups),
            "duplicate_row_count": len(affected),
            "groups": _group_evidence(groups, mapping),
            "groups_truncated": len(groups) > MAX_GROUPS_IN_EVIDENCE,
        },
        recommendation=recommendation,
        status="confirmed_issue",
    )


def detect_duplicates(
    rows: list[AuditRow], columns: list[str], mapping: AuditMapping
) -> list[Finding]:
    """Return findings whose evidence always points to the original CSV rows."""
    findings: list[Finding] = []

    exact_groups = _groups(rows, lambda row: tuple(row.values.get(column, "") for column in columns))
    finding = _finding(
        rule_id="duplicate_exact_row",
        severity="high",
        title="发现完全重复的数据行",
        description="多行在所提供全部列上的原始值完全一致，行号、记录标识和集合信息见证据。",
        groups=exact_groups,
        mapping=mapping,
        fields=columns,
        recommendation="核对重复行的采集来源，仅保留有明确业务含义的重复观测，避免训练样本被重复加权。",
    )
    if finding:
        findings.append(finding)

    def record_key(row: AuditRow) -> str | None:
        value = row.values.get(mapping.record_id)
        return None if is_missing(value) else value.strip()

    record_groups = _groups(rows, record_key)
    finding = _finding(
        rule_id="duplicate_record_id",
        severity="high",
        title="发现重复的记录标识",
        description="同一 record_id 对应多条记录；即使其他字段不同，也应核查标识唯一性。",
        groups=record_groups,
        mapping=mapping,
        fields=[mapping.record_id],
        recommendation="核查记录标识的生成和合并过程，修复重复标识或明确一对多关系后再建模。",
    )
    if finding:
        findings.append(finding)

    feature_groups = _groups(rows, lambda row: _feature_key(row, mapping))
    finding = _finding(
        rule_id="duplicate_feature_vector",
        severity="medium",
        title="发现重复的特征向量",
        description="多条记录的已映射特征值完全相同。本规则只说明特征重复，不据此推断实体或患者重复。",
        groups=feature_groups,
        mapping=mapping,
        fields=mapping.feature_columns,
        recommendation="结合 record_id、entity_id 和采集时间核查是否为重复样本；合理重复应保留业务依据。",
    )
    if finding:
        findings.append(finding)

    cross_split_groups = [
        group for group in feature_groups
        if len({mapping.split_for(row) for row in group}) > 1
    ]
    finding = _finding(
        rule_id="duplicate_features_cross_split",
        severity="high",
        title="相同特征向量出现在不同集合",
        description="完全相同的已映射特征向量跨越多个数据集合，可能造成训练与评估样本重复。",
        groups=cross_split_groups,
        mapping=mapping,
        fields=[*mapping.feature_columns, mapping.split],
        recommendation="按原始样本来源去重，并在去重后重新划分 Train、Validation 和 Test。",
    )
    if finding:
        findings.append(finding)

    return findings
