"""Per-column missing, placeholder, constant and non-finite checks."""

from __future__ import annotations

import math

from .audit_types import AuditMapping, AuditRow, Finding, is_missing, make_finding

PLACEHOLDER_TOKENS = {"na", "n/a", "null", "none", "-", "?"}
MAX_COLUMNS_IN_EVIDENCE = 50
MAX_VALUES_IN_EVIDENCE = 20


def _non_finite(value: str | None) -> bool:
    if value is None or not value.strip():
        return False
    try:
        return not math.isfinite(float(value.strip()))
    except ValueError:
        return False


def analyze_missing(
    rows: list[AuditRow], columns: list[str], mapping: AuditMapping
) -> tuple[list[Finding], list[dict]]:
    findings: list[Finding] = []
    statistics: list[dict] = []
    all_missing: list[str] = []
    partial_missing: list[str] = []
    constant_columns: list[str] = []
    placeholder_details: list[dict] = []
    non_finite_details: list[dict] = []
    missing_rows: list[AuditRow] = []
    all_missing_rows: list[AuditRow] = []
    constant_rows: list[AuditRow] = []
    placeholder_rows: list[AuditRow] = []
    non_finite_rows: list[AuditRow] = []

    for column in columns:
        raw_values = [row.values.get(column) for row in rows]
        present = [value.strip() for value in raw_values if not is_missing(value)]
        missing_count = len(rows) - len(present)
        unique_values = sorted(set(present))
        column_stats = {
            "column": column,
            "missing_count": missing_count,
            "missing_rate": round(missing_count / len(rows), 6) if rows else 0.0,
            "missing_percentage": round(missing_count / len(rows) * 100, 6) if rows else 0.0,
            "present_count": len(present),
            "unique_count": len(unique_values),
            "non_finite_count": sum(_non_finite(value) for value in raw_values),
        }
        statistics.append(column_stats)

        column_missing_rows = [row for row in rows if is_missing(row.values.get(column))]
        if rows and missing_count == len(rows):
            all_missing.append(column)
            all_missing_rows.extend(column_missing_rows)
        elif missing_count:
            partial_missing.append(column)
            missing_rows.extend(column_missing_rows)

        if present and len(unique_values) == 1:
            constant_columns.append(column)
            constant_rows.extend(row for row in rows if not is_missing(row.values.get(column)))

        placeholders = sorted({
            value.strip() for value in raw_values
            if value is not None and value.strip().casefold() in PLACEHOLDER_TOKENS
        })
        if placeholders:
            current = [
                row for row in rows
                if (row.values.get(column) or "").strip().casefold() in PLACEHOLDER_TOKENS
            ]
            placeholder_rows.extend(current)
            placeholder_details.append({
                "column": column,
                "count": len(current),
                "values": placeholders[:MAX_VALUES_IN_EVIDENCE],
                "row_numbers": [row.row_number for row in current[:MAX_VALUES_IN_EVIDENCE]],
            })

        non_finite_values = sorted({
            value.strip() for value in raw_values if _non_finite(value)
        })
        if non_finite_values:
            current = [row for row in rows if _non_finite(row.values.get(column))]
            non_finite_rows.extend(current)
            non_finite_details.append({
                "column": column,
                "count": len(current),
                "values": non_finite_values[:MAX_VALUES_IN_EVIDENCE],
                "row_numbers": [row.row_number for row in current[:MAX_VALUES_IN_EVIDENCE]],
            })

    def add(
        rule_id: str,
        severity: str,
        title: str,
        description: str,
        affected: list[AuditRow],
        fields: list[str],
        evidence: dict,
        recommendation: str,
    ) -> None:
        findings.append(make_finding(
            rule_id=rule_id,
            severity=severity,
            title=title,
            description=description,
            rows=list({row.row_number: row for row in affected}.values()),
            mapping=mapping,
            evidence={"fields": fields[:MAX_COLUMNS_IN_EVIDENCE], **evidence},
            recommendation=recommendation,
            status="confirmed_issue",
        ))

    if all_missing:
        add(
            "missing_all_values", "high", "存在整列缺失",
            "部分列的所有数据行均为缺失值，无法提供有效建模信息。",
            all_missing_rows, all_missing,
            {"columns": all_missing[:MAX_COLUMNS_IN_EVIDENCE]},
            "删除无有效信息的列，或回查数据导出和采集流程后补齐。",
        )
    if partial_missing:
        add(
            "missing_values", "medium", "检测到缺失值",
            "部分列存在空值或已定义的缺失占位符，具体数量和行号见统计与证据。",
            missing_rows, partial_missing,
            {"columns": [item for item in statistics if item["column"] in partial_missing][:MAX_COLUMNS_IN_EVIDENCE]},
            "结合字段含义选择删除、补全或显式保留缺失指示，避免无依据填充。",
        )
    if constant_columns:
        add(
            "missing_constant_column", "medium", "存在常量列",
            "排除缺失值后，部分列仅包含一个不同取值，无法提供区分度。",
            constant_rows, constant_columns,
            {"columns": [
                {"column": column, "value": next(
                    row.values.get(column, "").strip() for row in rows
                    if not is_missing(row.values.get(column))
                )}
                for column in constant_columns[:MAX_COLUMNS_IN_EVIDENCE]
            ]},
            "确认常量是否符合业务预期；对建模无信息的常量列应在特征处理阶段排除。",
        )
    if placeholder_details:
        add(
            "missing_placeholder_values", "low", "检测到缺失占位符",
            "部分单元格使用 NA、null、问号或短横线等占位符表示缺失，应统一缺失编码。",
            placeholder_rows, [item["column"] for item in placeholder_details],
            {"columns": placeholder_details[:MAX_COLUMNS_IN_EVIDENCE]},
            "将占位符统一转换为明确的缺失值，并核查其原始业务含义。",
        )
    if non_finite_details:
        add(
            "missing_non_finite_value", "high", "检测到非有限数值",
            "部分单元格可解析为 NaN 或正负无穷，不能作为普通有限数值参与统计和训练。",
            non_finite_rows, [item["column"] for item in non_finite_details],
            {"columns": non_finite_details[:MAX_COLUMNS_IN_EVIDENCE]},
            "回查计算溢出或无效输入，将非有限数值修正为合法值或明确标记为缺失。",
        )

    return findings, statistics
