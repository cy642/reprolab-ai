"""Safe CSV decoding, profiling and unconfirmed field suggestions."""

from __future__ import annotations

import csv
import io
import math
from dataclasses import dataclass
from pathlib import Path

from ..config import get_settings
from .audit_types import AuditRow, is_missing

MAX_CSV_COLUMNS = 100
MAX_CSV_CELLS = 1_000_000


class CsvError(ValueError):
    def __init__(self, code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


@dataclass(slots=True)
class ColumnProfile:
    name: str
    position: int
    inferred_type: str
    missing_count: int
    missing_rate: float
    unique_count: int
    sample_values: list[str]


@dataclass(slots=True)
class CsvData:
    encoding: str
    delimiter: str
    columns: list[ColumnProfile]
    rows: list[AuditRow]
    missing_cells: int
    duplicate_rows: int
    preview: list[dict]


def _decode(raw: bytes) -> tuple[str, str]:
    if not raw:
        raise CsvError("empty_file", "CSV 文件为空，请上传包含表头和数据行的文件。")
    if b"\x00" in raw[:8192]:
        raise CsvError("binary_file", "文件包含二进制内容，不是有效 CSV 文本。")
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise CsvError(
        "unsupported_encoding",
        "无法识别文件编码，请转换为 UTF-8 或 GB18030 后重试。",
    )


def _infer_type(values: list[str]) -> str:
    present = [value.strip() for value in values if not is_missing(value)]
    if not present:
        return "empty"
    if all(value.casefold() in {"true", "false", "yes", "no", "0", "1"} for value in present):
        return "boolean"
    if all(value.lstrip("+-").isdigit() for value in present):
        return "integer"
    try:
        if all(math.isfinite(float(value)) for value in present):
            return "number"
    except ValueError:
        pass
    return "text"


def read_csv(path: Path) -> CsvData:
    settings = get_settings()
    text, encoding = _decode(path.read_bytes())
    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        delimiter = ","

    try:
        reader = csv.reader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
        try:
            headers = next(reader)
        except StopIteration as exc:
            raise CsvError("empty_file", "CSV 文件为空。") from exc
        headers = [header.strip() for header in headers]
        if not headers or any(not header for header in headers):
            raise CsvError("invalid_header", "CSV 表头包含空列名。")
        if len(headers) > MAX_CSV_COLUMNS:
            raise CsvError(
                "too_many_columns",
                f"列数超过 {MAX_CSV_COLUMNS} 列上限。",
                413,
            )
        if len(set(headers)) != len(headers):
            raise CsvError("duplicate_columns", "CSV 表头存在重复列名，请先确保列名唯一。")

        rows: list[AuditRow] = []
        for row_number, values in enumerate(reader, start=2):
            if not values or all(not value.strip() for value in values):
                continue
            if len(values) != len(headers):
                raise CsvError(
                    "invalid_csv",
                    f"第 {row_number} 行包含 {len(values)} 列，与表头的 {len(headers)} 列不一致。",
                )
            if len(rows) >= settings.dataset_max_rows:
                raise CsvError(
                    "too_many_rows",
                    f"数据行超过 {settings.dataset_max_rows:,} 行上限，请拆分文件后审计。",
                    413,
                )
            if (len(rows) + 1) * len(headers) > MAX_CSV_CELLS:
                raise CsvError(
                    "too_many_cells",
                    "数据单元格总量超过安全上限，请减少行数或列数。",
                    413,
                )
            rows.append(AuditRow(row_number=row_number, values=dict(zip(headers, values))))
    except csv.Error as exc:
        raise CsvError("invalid_csv", f"CSV 结构解析失败：{exc}") from exc

    if not rows:
        raise CsvError("empty_dataset", "CSV 只有表头，没有可审计的数据行。")

    columns: list[ColumnProfile] = []
    missing_cells = 0
    for position, name in enumerate(headers):
        values = [row.values[name] for row in rows]
        missing_count = sum(is_missing(value) for value in values)
        present = [value.strip() for value in values if not is_missing(value)]
        missing_cells += missing_count
        columns.append(ColumnProfile(
            name=name,
            position=position,
            inferred_type=_infer_type(values),
            missing_count=missing_count,
            missing_rate=round(missing_count / len(rows), 6),
            unique_count=len(set(present)),
            sample_values=list(dict.fromkeys(present))[:5],
        ))

    fingerprints = [tuple(row.values[name] for name in headers) for row in rows]
    duplicate_rows = len(rows) - len(set(fingerprints))
    preview = [
        {"row_number": row.row_number, "values": row.values}
        for row in rows[:8]
    ]
    return CsvData(
        encoding=encoding,
        delimiter=delimiter,
        columns=columns,
        rows=rows,
        missing_cells=missing_cells,
        duplicate_rows=duplicate_rows,
        preview=preview,
    )


def suggest_mapping(columns: list[ColumnProfile]) -> dict:
    """Provide candidates only; callers must keep confirmed=False until the user saves."""
    by_name = {column.name.casefold(): column.name for column in columns}

    def candidate(names: tuple[str, ...]) -> str | None:
        return next((by_name[name] for name in names if name in by_name), None)

    record_id = candidate(("record_id", "sample_id", "record", "id"))
    entity_id = candidate(("patient_id", "entity_id", "subject_id", "patient", "entity"))
    label = candidate(("label", "class", "target", "diagnosis", "outcome"))
    split = candidate(("split", "dataset_split", "partition", "set"))
    reserved = {record_id, entity_id, label, split}
    return {
        "record_id": record_id,
        "entity_id": entity_id,
        "label": label,
        "split": split,
        "feature_columns": [column.name for column in columns if column.name not in reserved],
        "split_mapping": {},
        "confirmed": False,
    }
