"""API tests for PDF upload, extraction, evidence and persistence."""

from __future__ import annotations

import re
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.main import app

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REPROLAB_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("REPROLAB_MAX_UPLOAD_MB", "20")
    for name in (
        "LLM_BASE_URL",
        "LLM_API_KEY",
        "LLM_MODEL",
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    with TestClient(app) as test_client:
        yield test_client


def _sample_bytes() -> bytes:
    return (FIXTURES / "sample_paper.pdf").read_bytes()


def _upload(client: TestClient, name: str = "sample_paper.pdf", content: bytes | None = None):
    return client.post(
        "/api/papers/upload",
        files={"file": (name, content if content is not None else _sample_bytes(), "application/pdf")},
    )


def _make_pdf(pages: list[str]) -> bytes:
    document = pymupdf.open()
    for text in pages:
        page = document.new_page()
        if text:
            page.insert_textbox(pymupdf.Rect(56, 56, 539, 786), text, fontsize=11, fontname="helv")
    data = document.tobytes()
    document.close()
    return data


def _image_only_pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    pixmap = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 320, 320), 0)
    pixmap.set_rect(pixmap.irect, (180, 200, 220))
    page.insert_image(pymupdf.Rect(60, 60, 380, 380), pixmap=pixmap)
    data = document.tobytes()
    document.close()
    return data


def test_health(client: TestClient) -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["version"] == "0.5.0"


def test_upload_parse_and_evidence(client: TestClient) -> None:
    upload = _upload(client)
    assert upload.status_code == 201, upload.text
    paper = upload.json()
    assert paper["page_count"] == 3
    assert paper["status"] == "uploaded"
    assert paper["ai_status"] == "unconfigured"
    assert len(paper["pages"]) == 3
    paper_id = paper["id"]

    parsed = client.post(f"/api/papers/{paper_id}/parse")
    assert parsed.status_code == 200, parsed.text
    detail = parsed.json()
    assert detail["parse_status"] == "completed"
    assert detail["ai_status"] == "unconfigured"
    assert "尚未配置" in (detail["parse_message"] or "")

    fields = {item["field"]: item for item in detail["fields"]}
    assert fields["title"]["status"] == "found"
    assert fields["title"]["value"] == "Graph Neural Networks for Molecular Property Prediction"
    assert fields["authors"]["status"] == "found"
    assert "Alice Zhang" in fields["authors"]["value"]
    assert fields["abstract"]["status"] == "found"
    assert fields["datasets"]["status"] == "unknown"
    assert fields["datasets"]["value"] is None
    assert fields["hyperparameters"]["evidence"] == []

    for item in detail["evidence"]:
        assert item["page"] >= 1
        source = client.get(f"/api/papers/{paper_id}/text", params={"page": item["page"]}).json()["text"]
        normalized_source = re.sub(r"\s+", " ", source).lower()
        normalized_quote = re.sub(r"\s+", " ", item["quote"]).lower()
        assert normalized_quote in normalized_source

    page_two = client.get(f"/api/papers/{paper_id}/text", params={"page": 2})
    assert page_two.status_code == 200
    assert "Message-passing" in page_two.json()["text"] or "message-passing" in page_two.json()["text"]
    assert page_two.json()["page"] == 2

    listed = client.get("/api/papers").json()
    assert listed["total"] == 1
    assert listed["ai"]["configured"] is False
    assert listed["items"][0]["id"] == paper_id


def test_blank_pdf_requires_ocr(client: TestClient) -> None:
    response = _upload(client, "blank.pdf", _make_pdf([""]))
    assert response.status_code == 201, response.text
    paper = response.json()
    assert paper["status"] == "needs_ocr"
    assert "OCR" in (paper["parse_message"] or "")

    parsed = client.post(f"/api/papers/{paper['id']}/parse").json()
    assert parsed["status"] == "needs_ocr"
    assert all(field["status"] == "unknown" for field in parsed["fields"])
    assert parsed["evidence"] == []


def test_scanned_pdf_requires_ocr(client: TestClient) -> None:
    response = _upload(client, "scanned.pdf", _image_only_pdf())
    assert response.status_code == 201, response.text
    paper = response.json()
    assert paper["status"] == "needs_ocr"
    assert paper["text_chars"] == 0
    assert "扫描件" in (paper["parse_message"] or "")


def test_corrupt_pdf_rejected(client: TestClient) -> None:
    response = _upload(client, "broken.pdf", b"%PDF-1.7\nthis is not a real pdf")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] in {"invalid_pdf", "empty_pdf"}


def test_non_pdf_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/papers/upload",
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert response.status_code == 415


def test_oversized_file_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPROLAB_MAX_UPLOAD_MB", "1")
    payload = b"%PDF-1.7\n" + b"0" * (1024 * 1024 + 64)
    response = _upload(client, "huge.pdf", payload)
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"


def test_duplicate_upload_conflict(client: TestClient) -> None:
    first = _upload(client)
    assert first.status_code == 201
    second = _upload(client, "copy.pdf")
    assert second.status_code == 409
    detail = second.json()["detail"]
    assert detail["code"] == "duplicate_pdf"
    assert detail["paper_id"] == first.json()["id"]


def test_ai_failure_keeps_text_and_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    uploaded = _upload(client)
    paper_id = uploaded.json()["id"]
    monkeypatch.setenv("LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "2")

    parsed = client.post(f"/api/papers/{paper_id}/parse")
    assert parsed.status_code == 200, parsed.text
    detail = parsed.json()
    assert detail["ai_status"] == "failed"
    assert detail["ai_error"]
    assert detail["extraction_method"] == "heuristic"
    assert any(field["status"] == "found" for field in detail["fields"])

    page = client.get(f"/api/papers/{paper_id}/text", params={"page": 1})
    assert page.status_code == 200
    assert "Graph Neural Networks" in page.json()["text"]


def test_delete_and_persistence(client: TestClient) -> None:
    uploaded = _upload(client).json()
    paper_id = uploaded["id"]

    assert client.get(f"/api/papers/{paper_id}/evidence").status_code == 200
    delete = client.delete(f"/api/papers/{paper_id}")
    assert delete.status_code == 204
    assert client.get(f"/api/papers/{paper_id}").status_code == 404
    assert client.get("/api/papers").json()["total"] == 0

    # A deleted paper can be uploaded again.
    assert _upload(client).status_code == 201


def test_missing_paper_and_page_errors(client: TestClient) -> None:
    assert client.get("/api/papers/paper_missing").status_code == 404
    assert client.post("/api/papers/paper_missing/parse").status_code == 404
    assert client.get("/api/papers/paper_missing/evidence").status_code == 404
    assert client.delete("/api/papers/paper_missing").status_code == 404

    uploaded = _upload(client).json()
    assert client.get(f"/api/papers/{uploaded['id']}/text", params={"page": 99}).status_code == 404
