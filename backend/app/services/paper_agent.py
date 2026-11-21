"""Paper Agent: structured extraction with strict, verifiable evidence."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .llm_provider import LLMError, LLMProvider

FIELD_DEFINITIONS: list[tuple[str, str, str]] = [
    ("title", "论文标题", "basics"),
    ("authors", "作者", "basics"),
    ("abstract", "摘要", "basics"),
    ("research_question", "研究问题", "research"),
    ("method", "研究方法", "research"),
    ("model_architecture", "模型架构", "research"),
    ("datasets", "数据集", "experiment"),
    ("experiment_setup", "实验设置", "experiment"),
    ("hyperparameters", "超参数", "experiment"),
    ("metrics", "评价指标", "experiment"),
    ("conclusions", "实验结论", "outcome"),
    ("limitations", "局限性", "outcome"),
]

FIELD_KEYS = [item[0] for item in FIELD_DEFINITIONS]

UNKNOWN_MESSAGE = "未在原文中找到可验证证据，标记为待确认。"


@dataclass
class EvidenceItem:
    page: int
    quote: str


@dataclass
class ExtractedField:
    value: str | None
    status: str  # found | pending | unknown
    source: str  # heuristic | llm | none
    confidence: float | None = None
    evidence: list[EvidenceItem] = field(default_factory=list)


@dataclass
class ExtractionResult:
    fields: dict[str, ExtractedField]
    method: str
    ai_status: str  # unconfigured | success | failed
    ai_error: str | None
    message: str


def _normalize_ws(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def locate_quote(page_text: str, quote: str) -> str | None:
    """Return the original span if the quote can be matched on that page."""
    normalized = _normalize_ws(quote)[:600]
    if len(normalized) < 6:
        return None
    tokens = [token for token in normalized.split(" ") if token]
    if not tokens:
        return None
    pattern = r"\s+".join(re.escape(token) for token in tokens)
    match = re.search(pattern, page_text or "", flags=re.IGNORECASE)
    if not match:
        return None
    return _normalize_ws(match.group(0))[:800]


def _first_page_lines(pages: list[str]) -> list[str]:
    if not pages:
        return []
    return [line.strip() for line in pages[0].split("\n") if line.strip()]


def _guess_title(pages: list[str]) -> tuple[str, str] | None:
    for line in _first_page_lines(pages)[:14]:
        if len(line) < 4 or len(line) > 240:
            continue
        if re.fullmatch(r"[\d\s./-]+", line):
            continue
        if re.search(r"(?i)arxiv|preprint|doi|copyright|proceedings", line):
            continue
        return line, line
    return None


def _looks_like_authors(line: str) -> bool:
    if len(line) < 4 or len(line) > 200:
        return False
    if "@" in line or re.search(r"\d{4}", line):
        return False
    if re.search(r"(?i)abstract|introduction|university|keywords|department", line):
        return False
    latin_names = re.findall(r"\b[A-Z][a-zA-Z.'-]{1,}", line)
    chinese_names = re.findall(r"[\u4e00-\u9fff]{2,4}", line)
    separated = "," in line or "，" in line or " and " in line or "、" in line
    return (len(latin_names) >= 2 and separated) or (len(chinese_names) >= 2 and separated)


def _guess_authors(pages: list[str], title: str) -> tuple[str, str] | None:
    lines = _first_page_lines(pages)[:20]
    try:
        title_index = lines.index(title)
    except ValueError:
        title_index = 0
    for line in lines[title_index + 1 : title_index + 4]:
        if _looks_like_authors(line):
            return line, line
    return None


def _guess_abstract(pages: list[str]) -> tuple[str, str] | None:
    if not pages:
        return None
    text = pages[0]
    match = re.search(r"(?im)^\s*abstract\b\s*[:.\-—]?\s*", text)
    if not match:
        return None
    remainder = text[match.end() :]
    stop = re.search(
        r"(?im)^\s*(?:1\.?\s*)?(?:introduction|keywords|index terms|background)\b",
        remainder,
    )
    body = (remainder[: stop.start()] if stop else remainder[:1600]).strip()
    if len(body) < 40:
        return None
    body = _normalize_ws(body)
    quote = body[:400]
    canonical = locate_quote(text, quote)
    if not canonical:
        return None
    return body[:1200], canonical


def heuristic_extract(pages: list[str]) -> dict[str, ExtractedField]:
    """Local, evidence-cited extraction. Never invents values for missing fields."""
    fields: dict[str, ExtractedField] = {
        key: ExtractedField(value=None, status="unknown", source="none")
        for key in FIELD_KEYS
    }

    title = _guess_title(pages)
    if title:
        fields["title"] = ExtractedField(
            value=title[0],
            status="found",
            source="heuristic",
            confidence=0.6,
            evidence=[EvidenceItem(page=1, quote=title[1])],
        )
    elif pages:
        first = _first_page_lines(pages)[:1]
        if first:
            fields["title"] = ExtractedField(
                value=first[0],
                status="pending",
                source="heuristic",
                confidence=0.3,
                evidence=[],
            )

    authors = _guess_authors(pages, title[0] if title else "")
    if authors:
        fields["authors"] = ExtractedField(
            value=authors[0],
            status="found",
            source="heuristic",
            confidence=0.5,
            evidence=[EvidenceItem(page=1, quote=authors[1])],
        )

    abstract = _guess_abstract(pages)
    if abstract:
        fields["abstract"] = ExtractedField(
            value=abstract[0],
            status="found",
            source="heuristic",
            confidence=0.7,
            evidence=[EvidenceItem(page=1, quote=abstract[1])],
        )

    return fields


SYSTEM_PROMPT = """You are a meticulous research-paper extraction agent.
Return only a JSON object with this exact shape:
{"fields": {"<field>": {"value": "<string or null>", "status": "found" | "unknown", "confidence": 0.0, "evidence": [{"page": <1-based page number>, "quote": "<verbatim text copied from that page>"}]}}}
Rules:
- Allowed field keys: title, authors, abstract, research_question, method, model_architecture, datasets, experiment_setup, hyperparameters, metrics, conclusions, limitations.
- Never fabricate. If the paper does not state something, use status "unknown" and value null.
- Every non-null value MUST include at least one evidence item with an exact verbatim quote from the supplied page text.
- Page numbers are the 1-based numbers shown in the [PAGE n] markers.
- Quotes must be in the original language of the paper and no longer than 400 characters.
- Keep values concise; use short paragraphs or comma-separated lists.
"""


def _build_user_prompt(pages: list[str], max_chars: int = 48_000) -> str:
    chunks: list[str] = []
    used = 0
    for index, text in enumerate(pages, start=1):
        block = f"[PAGE {index}]\n{text}\n"
        if used + len(block) > max_chars:
            remaining = max_chars - used
            if remaining > 1200:
                chunks.append(block[:remaining])
            chunks.append("[TRUNCATED] Later pages were omitted for length.")
            break
        chunks.append(block)
        used += len(block)
    return "Extract the fields from this paper:\n\n" + "\n".join(chunks)


def _merge_llm_fields(
    base: dict[str, ExtractedField],
    payload: dict,
    pages: list[str],
) -> dict[str, ExtractedField]:
    raw_fields = payload.get("fields")
    if not isinstance(raw_fields, dict):
        raise LLMError("模型响应缺少 fields 字段。")

    merged = {key: value for key, value in base.items()}
    for key in FIELD_KEYS:
        item = raw_fields.get(key)
        if not isinstance(item, dict):
            continue
        value = item.get("value")
        status = str(item.get("status") or "unknown")
        if not isinstance(value, str) or not value.strip() or status != "found":
            continue

        try:
            confidence = float(item.get("confidence"))
        except (TypeError, ValueError):
            confidence = None
        if confidence is not None:
            confidence = min(max(confidence, 0.0), 1.0)

        evidence: list[EvidenceItem] = []
        for entry in item.get("evidence") or []:
            if not isinstance(entry, dict):
                continue
            try:
                page = int(entry.get("page"))
            except (TypeError, ValueError):
                continue
            if page < 1 or page > len(pages):
                continue
            quote = entry.get("quote")
            if not isinstance(quote, str):
                continue
            canonical = locate_quote(pages[page - 1], quote)
            if canonical:
                evidence.append(EvidenceItem(page=page, quote=canonical))

        if evidence:
            merged[key] = ExtractedField(
                value=_normalize_ws(value)[:2000],
                status="found",
                source="llm",
                confidence=confidence,
                evidence=evidence,
            )
        else:
            # Value without verifiable source stays pending instead of being trusted.
            merged[key] = ExtractedField(
                value=_normalize_ws(value)[:2000],
                status="pending",
                source="llm",
                confidence=confidence,
                evidence=[],
            )
    return merged


def extract_paper(pages: list[str], *, use_llm: bool = True) -> ExtractionResult:
    """Run heuristic extraction, then the configured LLM on top of it."""
    base = heuristic_extract(pages)
    if not use_llm:
        return ExtractionResult(
            fields=base, method="heuristic", ai_status="not_used", ai_error=None,
            message="本次使用 PDF 文本提取与本地启发式字段识别。",
        )
    provider = LLMProvider()

    if not provider.configured:
        return ExtractionResult(
            fields=base,
            method="heuristic",
            ai_status="unconfigured",
            ai_error=None,
            message="AI 解析尚未配置，已完成 PDF 文本提取与本地启发式字段识别。",
        )

    try:
        payload = provider.complete_json(SYSTEM_PROMPT, _build_user_prompt(pages))
        merged = _merge_llm_fields(base, payload, pages)
        return ExtractionResult(
            fields=merged,
            method="hybrid",
            ai_status="success",
            ai_error=None,
            message="AI 结构化解析完成。请核对已定位的原文证据和待确认字段。",
        )
    except LLMError as exc:
        return ExtractionResult(
            fields=base,
            method="heuristic",
            ai_status="failed",
            ai_error=str(exc),
            message="模型调用失败，已保留 PDF 文本与本地启发式提取结果。",
        )
