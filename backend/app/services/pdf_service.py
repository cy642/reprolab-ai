"""PDF validation and text extraction backed by PyMuPDF."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf


class PdfError(Exception):
    """Raised when an uploaded file is not a usable PDF."""

    def __init__(self, message: str, code: str = "invalid_pdf") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


@dataclass
class PdfContent:
    pages: list[str]
    page_count: int
    text_chars: int
    image_pages: list[int]

    @property
    def has_text(self) -> bool:
        return self.text_chars > 0

    @property
    def likely_scanned(self) -> bool:
        return not self.has_text and bool(self.image_pages)


def _clean_page_text(raw: str) -> str:
    text = raw.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    cleaned = "\n".join(lines)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def extract_pdf(path: Path) -> PdfContent:
    """Extract per-page text while keeping the real 1-based page numbers."""
    try:
        document = pymupdf.open(path, filetype="pdf")
    except Exception as exc:  # PyMuPDF raises several exception types
        raise PdfError("文件不是有效的 PDF 或已损坏，无法解析。") from exc

    try:
        if document.needs_pass:
            raise PdfError("PDF 已加密，请先移除密码后再上传。", code="encrypted_pdf")
        page_count = document.page_count
        if page_count <= 0:
            raise PdfError("PDF 没有可解析的页面。", code="empty_pdf")

        pages: list[str] = []
        image_pages: list[int] = []
        text_chars = 0
        for index in range(page_count):
            page = document.load_page(index)
            text = _clean_page_text(page.get_text("text") or "")
            pages.append(text)
            text_chars += len(text.replace("\n", "").replace(" ", ""))
            if text_chars == 0 or len(text.strip()) < 20:
                if page.get_images(full=False):
                    image_pages.append(index + 1)
        return PdfContent(
            pages=pages,
            page_count=page_count,
            text_chars=text_chars,
            image_pages=image_pages,
        )
    finally:
        document.close()


def looks_like_pdf(header: bytes) -> bool:
    return b"%PDF-" in header[:1024]
