"""Orchestrate the six deterministic Phase 4 audit modules."""

from __future__ import annotations

from .audit_types import AuditMapping, AuditResult, AuditRow
from .class_analyzer import analyze_classes
from .duplicate_detector import detect_duplicates
from .feature_inspector import inspect_features
from .leakage_detector import detect_leakage
from .missing_analyzer import analyze_missing
from .split_validator import validate_split


def run_audit(
    rows: list[AuditRow], columns: list[str], mapping: AuditMapping
) -> AuditResult:
    """Run every rule directly against the supplied rows; no model calls are used."""
    duplicate_findings = detect_duplicates(rows, columns, mapping)
    leakage_findings = detect_leakage(rows, mapping)
    class_findings, class_distribution = analyze_classes(rows, mapping)
    missing_findings, missing_by_column = analyze_missing(rows, columns, mapping)
    split_findings, split_distribution = validate_split(rows, mapping)
    feature_findings, feature_statistics = inspect_features(rows, mapping)

    findings = [
        *duplicate_findings,
        *leakage_findings,
        *class_findings,
        *missing_findings,
        *split_findings,
        *feature_findings,
    ]
    return AuditResult(
        findings=findings,
        statistics={
            "class_distribution": class_distribution,
            "missing_by_column": missing_by_column,
            "split_distribution": split_distribution,
            "feature_statistics": feature_statistics,
        },
    )
