"""Shared deterministic audit contracts and helpers."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

MISSING_TOKENS = {"", "na", "n/a", "null", "none", "nan", "-", "?"}
SPLIT_ALIASES = {
    "train": "Train",
    "training": "Train",
    "tr": "Train",
    "validation": "Validation",
    "valid": "Validation",
    "val": "Validation",
    "dev": "Validation",
    "test": "Test",
    "testing": "Test",
    "te": "Test",
    "holdout": "Test",
}
CANONICAL_SPLITS = {"Train", "Validation", "Test"}
MAX_AFFECTED_ITEMS = 100
MAX_EVIDENCE_RECORDS = 25


def is_missing(value: str | None) -> bool:
    return value is None or value.strip().casefold() in MISSING_TOKENS


@dataclass(slots=True)
class AuditRow:
    """A CSV data row; row_number includes the header, so the first data row is 2."""

    row_number: int
    values: dict[str, str]


@dataclass(slots=True)
class AuditMapping:
    record_id: str
    entity_id: str | None
    label: str
    split: str
    feature_columns: list[str]
    split_mapping: dict[str, str] = field(default_factory=dict)

    def split_for(self, row: AuditRow) -> str:
        raw = row.values.get(self.split, "").strip()
        custom = self.split_mapping.get(raw)
        if custom is None:
            custom = next(
                (value for key, value in self.split_mapping.items() if key.casefold() == raw.casefold()),
                None,
            )
        if custom:
            return custom
        return SPLIT_ALIASES.get(raw.casefold(), raw)


@dataclass(slots=True)
class Finding:
    rule_id: str
    severity: str
    title: str
    description: str
    affected_rows: list[int]
    affected_record_ids: list[str]
    evidence: dict[str, Any]
    recommendation: str
    status: str
    finding_id: str = field(default_factory=lambda: f"finding_{uuid.uuid4().hex[:16]}")

    def as_dict(self) -> dict[str, Any]:
        return {
            "finding_id": self.finding_id,
            "rule_id": self.rule_id,
            "severity": self.severity,
            "title": self.title,
            "description": self.description,
            "affected_rows": self.affected_rows,
            "affected_record_ids": self.affected_record_ids,
            "evidence": self.evidence,
            "recommendation": self.recommendation,
            "status": self.status,
        }


@dataclass(slots=True)
class AuditResult:
    findings: list[Finding]
    statistics: dict[str, Any]


def make_finding(
    *,
    rule_id: str,
    severity: str,
    title: str,
    description: str,
    rows: Iterable[AuditRow],
    mapping: AuditMapping,
    evidence: dict[str, Any] | None = None,
    recommendation: str,
    status: str,
) -> Finding:
    affected = list(rows)
    details = dict(evidence or {})
    details.setdefault("affected_count", len(affected))
    details.setdefault(
        "records",
        [
            {
                "row_number": row.row_number,
                "record_id": row.values.get(mapping.record_id, ""),
                "entity_id": row.values.get(mapping.entity_id, "") if mapping.entity_id else None,
                "split": mapping.split_for(row),
                "values": row.values,
            }
            for row in affected[:MAX_EVIDENCE_RECORDS]
        ],
    )
    details["truncated"] = len(affected) > MAX_EVIDENCE_RECORDS
    return Finding(
        rule_id=rule_id,
        severity=severity,
        title=title,
        description=description,
        affected_rows=[row.row_number for row in affected[:MAX_AFFECTED_ITEMS]],
        affected_record_ids=list(dict.fromkeys(
            row.values.get(mapping.record_id, "") for row in affected
        ))[:MAX_AFFECTED_ITEMS],
        evidence=details,
        recommendation=recommendation,
        status=status,
    )


def split_of(rows: Iterable[AuditRow], mapping: AuditMapping) -> dict[str, list[AuditRow]]:
    grouped: dict[str, list[AuditRow]] = {}
    for row in rows:
        grouped.setdefault(mapping.split_for(row), []).append(row)
    return grouped
