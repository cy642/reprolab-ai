"""Paper upload, parsing and evidence endpoints."""

from __future__ import annotations

import hashlib
import os
import sqlite3
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from starlette.responses import FileResponse
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from ..config import get_settings, public_ai_info
from ..db import connect
from ..schemas import (
    AIInfo,
    EvidenceOut,
    FieldOut,
    PageMeta,
    PageTextResponse,
    PaperDetail,
    PaperListResponse,
    PaperSummary,
)
from ..services.paper_agent import FIELD_DEFINITIONS, extract_paper
from ..services.pdf_service import PdfError, extract_pdf, looks_like_pdf

router = APIRouter(prefix="/api/papers", tags=["Papers"])

ALLOWED_SUFFIX = ".pdf"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _display_filename(raw: str | None) -> str:
    name = Path((raw or "paper.pdf").replace("\\", "/")).name.strip() or "paper.pdf"
    return name[:180]


def _safe_file_path(stored_filename: str) -> Path:
    uploads = get_settings().uploads_dir.resolve()
    path = (uploads / stored_filename).resolve()
    if uploads not in path.parents:
        raise HTTPException(status_code=400, detail={"code": "invalid_path", "message": "非法文件路径。"})
    return path


def _get_row(connection: sqlite3.Connection, paper_id: str) -> sqlite3.Row:
    row = connection.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "paper_not_found", "message": "论文不存在或已被删除。"})
    return row


def _summary(row: sqlite3.Row) -> PaperSummary:
    return PaperSummary(
        id=row["id"],
        filename=row["original_filename"],
        title=row["title"],
        page_count=row["page_count"],
        file_size=row["file_size"],
        status=row["status"],
        parse_status=row["parse_status"],
        ai_status=row["ai_status"],
        ai_error=row["ai_error"],
        extraction_method=row["extraction_method"],
        text_chars=row["text_chars"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _detail(connection: sqlite3.Connection, row: sqlite3.Row, message: str | None = None) -> PaperDetail:
    paper_id = row["id"]
    evidence_rows = connection.execute(
        "SELECT * FROM paper_evidence WHERE paper_id = ? ORDER BY page, rowid",
        (paper_id,),
    ).fetchall()
    evidence = [
        EvidenceOut(id=item["id"], field=item["field"], page=item["page"], quote=item["quote"])
        for item in evidence_rows
    ]
    grouped: dict[str, list[EvidenceOut]] = {}
    for item in evidence:
        grouped.setdefault(item.field, []).append(item)

    stored_fields = {
        item["field"]: item
        for item in connection.execute(
            "SELECT * FROM paper_fields WHERE paper_id = ?", (paper_id,)
        ).fetchall()
    }
    fields: list[FieldOut] = []
    for key, label, category in FIELD_DEFINITIONS:
        stored = stored_fields.get(key)
        fields.append(
            FieldOut(
                field=key,
                label=label,
                category=category,
                value=stored["value"] if stored else None,
                status=stored["status"] if stored else "unknown",
                source=stored["source"] if stored else "none",
                confidence=stored["confidence"] if stored else None,
                evidence=grouped.get(key, []),
            )
        )

    pages = [
        PageMeta(page=item["page"], chars=len(item["text"]))
        for item in connection.execute(
            "SELECT page, text FROM paper_pages WHERE paper_id = ? ORDER BY page",
            (paper_id,),
        ).fetchall()
    ]
    settings = get_settings()
    return PaperDetail(
        **_summary(row).model_dump(),
        fields=fields,
        evidence=evidence,
        pages=pages,
        ai_configured=settings.llm_configured,
        parse_message=message,
    )


@router.get("", response_model=PaperListResponse)
def list_papers() -> PaperListResponse:
    """List uploaded papers with parse and AI status."""
    with connect() as connection:
        rows = connection.execute("SELECT * FROM papers ORDER BY created_at DESC").fetchall()
    return PaperListResponse(
        items=[_summary(row) for row in rows],
        total=len(rows),
        ai=AIInfo(**public_ai_info()),
    )


@router.post("/upload", response_model=PaperDetail, status_code=HTTP_201_CREATED)
def upload_paper(file: UploadFile = File(...)) -> PaperDetail:
    """Upload a PDF (≤20MB by default) and extract its real page text."""
    settings = get_settings()
    filename = _display_filename(file.filename)
    if not filename.lower().endswith(ALLOWED_SUFFIX):
        raise HTTPException(status_code=415, detail={"code": "invalid_type", "message": "仅支持上传 PDF 文件。"})
    if file.content_type not in (None, "", "application/pdf", "application/x-pdf", "application/octet-stream"):
        raise HTTPException(status_code=415, detail={"code": "invalid_type", "message": "文件类型必须是 application/pdf。"})

    settings.uploads_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    header = b""
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, dir=settings.uploads_dir, suffix=".pdf") as temp:
            temp_path = Path(temp.name)
            while chunk := file.file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail={
                            "code": "file_too_large",
                            "message": f"文件超过 {settings.max_upload_bytes // (1024 * 1024)}MB 上限。",
                        },
                    )
                if len(header) < 1024:
                    header += chunk[: 1024 - len(header)]
                digest.update(chunk)
                temp.write(chunk)

        if total == 0 or not looks_like_pdf(header):
            raise HTTPException(status_code=400, detail={"code": "invalid_pdf", "message": "文件不是有效的 PDF。"})

        sha256 = digest.hexdigest()
        with connect() as connection:
            duplicate = connection.execute(
                "SELECT id FROM papers WHERE sha256 = ?", (sha256,)
            ).fetchone()
        if duplicate:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "duplicate_pdf",
                    "message": "该论文已上传，无需重复导入。",
                    "paper_id": duplicate["id"],
                },
            )

        try:
            content = extract_pdf(temp_path)
        except PdfError as exc:
            raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc

        stored_filename = f"{uuid.uuid4().hex}.pdf"
        final_path = _safe_file_path(stored_filename)
        os.replace(temp_path, final_path)

        paper_id = f"paper_{uuid.uuid4().hex[:16]}"
        now = _now()
        needs_ocr = not content.has_text
        status = "needs_ocr" if needs_ocr else "uploaded"
        parse_status = "needs_ocr" if needs_ocr else "pending"
        ai_status = "pending" if settings.llm_configured else "unconfigured"
        with connect() as connection:
            connection.execute(
                """
                INSERT INTO papers (
                    id, original_filename, stored_filename, sha256, file_size, page_count,
                    title, status, parse_status, ai_status, ai_error, extraction_method,
                    text_chars, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, 'none', ?, ?, ?)
                """,
                (
                    paper_id,
                    filename,
                    stored_filename,
                    sha256,
                    total,
                    content.page_count,
                    Path(filename).stem[:180] or filename,
                    status,
                    parse_status,
                    ai_status,
                    content.text_chars,
                    now,
                    now,
                ),
            )
            connection.executemany(
                "INSERT INTO paper_pages (paper_id, page, text) VALUES (?, ?, ?)",
                [(paper_id, index, text) for index, text in enumerate(content.pages, start=1)],
            )
            row = _get_row(connection, paper_id)
        message = None
        if needs_ocr:
            kind = "扫描件" if content.likely_scanned else "空白或无可提取文本的 PDF"
            message = f"检测到{kind}。请先完成 OCR，再重新上传可检索文本的 PDF。"
        return _detail_for(row, message)
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                # A failed PyMuPDF open may briefly hold the handle on Windows.
                pass


def _detail_for(row: sqlite3.Row, message: str | None = None) -> PaperDetail:
    with connect() as connection:
        return _detail(connection, row, message)


@router.get("/{paper_id}/file", response_class=FileResponse)
def get_paper_file(paper_id: str) -> FileResponse:
    """Stream the stored PDF inline so the viewer can navigate to evidence pages."""
    with connect() as connection:
        row = _get_row(connection, paper_id)
        stored_filename = row["stored_filename"]
    path = _safe_file_path(stored_filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail={"code": "file_not_found", "message": "论文记录存在，但 PDF 文件已丢失。"})
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=path.name,
        content_disposition_type="inline",
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/{paper_id}", response_model=PaperDetail)
def get_paper(paper_id: str) -> PaperDetail:
    """Return metadata, structured fields, evidence and page index."""
    with connect() as connection:
        row = _get_row(connection, paper_id)
        return _detail(connection, row)


@router.post("/{paper_id}/parse", response_model=PaperDetail)
def parse_paper(paper_id: str, *, use_llm: bool = True) -> PaperDetail:
    """Run structured extraction. Unconfigured AI never produces fake results."""
    with connect() as connection:
        row = _get_row(connection, paper_id)

    pages = _load_pages(paper_id)
    if not any(text.strip() for text in pages):
        with connect() as connection:
            connection.execute(
                "UPDATE papers SET status = 'needs_ocr', parse_status = 'needs_ocr', ai_error = NULL, updated_at = ? WHERE id = ?",
                (_now(), paper_id),
            )
            connection.execute("DELETE FROM paper_fields WHERE paper_id = ?", (paper_id,))
            connection.execute("DELETE FROM paper_evidence WHERE paper_id = ?", (paper_id,))
            row = _get_row(connection, paper_id)
            return _detail(
                connection,
                row,
                "该 PDF 没有可提取文本，可能为扫描件。需要先进行 OCR，系统不会生成虚假解析结果。",
            )

    with connect() as connection:
        connection.execute(
            "UPDATE papers SET status = 'extracting', parse_status = 'parsing', updated_at = ? WHERE id = ?",
            (_now(), paper_id),
        )

    result = extract_paper(pages, use_llm=use_llm)

    title_field = result.fields.get("title")
    title = title_field.value if title_field and title_field.value else row["title"]

    with connect() as connection:
        connection.execute("DELETE FROM paper_fields WHERE paper_id = ?", (paper_id,))
        connection.execute("DELETE FROM paper_evidence WHERE paper_id = ?", (paper_id,))
        for key, extracted in result.fields.items():
            connection.execute(
                "INSERT INTO paper_fields (paper_id, field, value, status, source, confidence) VALUES (?, ?, ?, ?, ?, ?)",
                (paper_id, key, extracted.value, extracted.status, extracted.source, extracted.confidence),
            )
            for item in extracted.evidence:
                connection.execute(
                    "INSERT INTO paper_evidence (id, paper_id, field, page, quote) VALUES (?, ?, ?, ?, ?)",
                    (f"ev_{uuid.uuid4().hex[:16]}", paper_id, key, item.page, item.quote),
                )
        connection.execute(
            """
            UPDATE papers SET
                title = ?, status = 'parsed', parse_status = 'completed',
                ai_status = ?, ai_error = ?, extraction_method = ?, updated_at = ?
            WHERE id = ?
            """,
            (title[:180], result.ai_status, result.ai_error, result.method, _now(), paper_id),
        )
        row = _get_row(connection, paper_id)
        return _detail(connection, row, result.message)


@router.get("/{paper_id}/evidence", response_model=list[EvidenceOut])
def get_evidence(paper_id: str, field: str | None = None) -> list[EvidenceOut]:
    """Return page-level evidence, optionally filtered by field name."""
    with connect() as connection:
        _get_row(connection, paper_id)
        if field:
            rows = connection.execute(
                "SELECT * FROM paper_evidence WHERE paper_id = ? AND field = ? ORDER BY page, rowid",
                (paper_id, field),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM paper_evidence WHERE paper_id = ? ORDER BY page, rowid",
                (paper_id,),
            ).fetchall()
    return [
        EvidenceOut(id=item["id"], field=item["field"], page=item["page"], quote=item["quote"])
        for item in rows
    ]


@router.get("/{paper_id}/text", response_model=PageTextResponse)
def get_page_text(paper_id: str, page: int = 1) -> PageTextResponse:
    """Return the extracted text of a single 1-based PDF page for preview."""
    with connect() as connection:
        row = _get_row(connection, paper_id)
        item = connection.execute(
            "SELECT text FROM paper_pages WHERE paper_id = ? AND page = ?",
            (paper_id, page),
        ).fetchone()
        if item is None:
            raise HTTPException(
                status_code=404,
                detail={"code": "page_not_found", "message": f"第 {page} 页不存在。"},
            )
        return PageTextResponse(
            paper_id=paper_id,
            page=page,
            page_count=row["page_count"],
            text=item["text"],
        )


@router.delete("/{paper_id}", status_code=HTTP_204_NO_CONTENT)
def delete_paper(paper_id: str) -> None:
    """Delete the database record, evidence and the stored PDF file."""
    with connect() as connection:
        row = _get_row(connection, paper_id)
        stored_filename = row["stored_filename"]
        connection.execute("DELETE FROM papers WHERE id = ?", (paper_id,))
    path = _safe_file_path(stored_filename)
    path.unlink(missing_ok=True)


def _load_pages(paper_id: str) -> list[str]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT text FROM paper_pages WHERE paper_id = ? ORDER BY page",
            (paper_id,),
        ).fetchall()
    return [row["text"] for row in rows]
