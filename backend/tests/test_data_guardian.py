"""Phase 4 Data Guardian API and deterministic audit tests."""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

FIXTURES = Path(__file__).resolve().parent / "fixtures"
DEMO = FIXTURES / "simulated_six_class.csv"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REPROLAB_STORAGE_DIR", str(tmp_path / "storage"))
    for name in (
        "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
        "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    with TestClient(app) as test_client:
        yield test_client


def _upload(client: TestClient, content: bytes | None = None, filename: str = "research.csv"):
    return client.post(
        "/api/datasets/upload",
        files={"file": (filename, content if content is not None else DEMO.read_bytes(), "text/csv")},
    )


def _mapping(feature_columns: list[str] | None = None) -> dict:
    return {
        "record_id": "record_id",
        "entity_id": "patient_id",
        "label": "label",
        "split": "split",
        "feature_columns": feature_columns or [
            "feature_age", "feature_biomarker", "feature_score", "constant_feature",
        ],
        "split_mapping": {},
    }


def _audit_demo(client: TestClient) -> tuple[dict, dict]:
    uploaded = _upload(client)
    assert uploaded.status_code == 201, uploaded.text
    dataset = uploaded.json()
    mapped = client.put(f"/api/datasets/{dataset['id']}/mapping", json=_mapping())
    assert mapped.status_code == 200, mapped.text
    audited = client.post(f"/api/datasets/{dataset['id']}/audit")
    assert audited.status_code == 201, audited.text
    return dataset, audited.json()


def _custom_audit(client: TestClient, content: str, mapping: dict) -> dict:
    uploaded = _upload(client, content.encode("utf-8"))
    assert uploaded.status_code == 201, uploaded.text
    dataset_id = uploaded.json()["id"]
    mapped = client.put(f"/api/datasets/{dataset_id}/mapping", json=mapping)
    assert mapped.status_code == 200, mapped.text
    response = client.post(f"/api/datasets/{dataset_id}/audit")
    assert response.status_code == 201, response.text
    return response.json()


def test_normal_csv_upload_profiles_and_persists(client: TestClient) -> None:
    response = _upload(client)
    assert response.status_code == 201, response.text
    detail = response.json()
    assert detail["row_count"] == 25
    assert detail["column_count"] == 9
    assert detail["duplicate_rows"] == 1
    assert detail["missing_cells"] == 3
    assert detail["encoding"] == "utf-8-sig"
    assert len(detail["columns"]) == 9
    assert detail["preview"]
    assert detail["mapping"]["confirmed"] is False
    assert detail["suggested_mapping"]["entity_id"] == "patient_id"

    listed = client.get("/api/datasets")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["deterministic_engine"] is True
    refreshed = client.get(f"/api/datasets/{detail['id']}")
    assert refreshed.status_code == 200
    assert refreshed.json()["filename"] == "research.csv"


def test_invalid_csv_and_extension_rejected(client: TestClient) -> None:
    wrong_type = _upload(client, b"record_id,label\nR1,A\n", "notes.txt")
    assert wrong_type.status_code == 415
    malformed = _upload(client, b'record_id,label,split,f1\nR1,A,Train,"unterminated\n')
    assert malformed.status_code == 400
    assert malformed.json()["detail"]["code"] == "invalid_csv"
    inconsistent = _upload(client, b"record_id,label\nR1,A,extra\n")
    assert inconsistent.status_code == 400


def test_empty_and_header_only_csv_rejected(client: TestClient) -> None:
    empty = _upload(client, b"")
    assert empty.status_code == 400
    assert empty.json()["detail"]["code"] == "empty_file"
    header_only = _upload(client, b"record_id,label,split\n")
    assert header_only.status_code == 400
    assert header_only.json()["detail"]["code"] == "empty_dataset"


def test_oversized_csv_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPROLAB_DATASET_MAX_BYTES", "64")
    response = _upload(client, DEMO.read_bytes())
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "file_too_large"


def test_row_limit_rejected(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REPROLAB_DATASET_MAX_ROWS", "3")
    response = _upload(client)
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "too_many_rows"


def test_gb18030_encoding_detected(client: TestClient) -> None:
    content = "record_id,label,split,f1\nR1,类别甲,Train,1\nR2,类别乙,Test,2\n".encode("gb18030")
    response = _upload(client, content)
    assert response.status_code == 201, response.text
    assert response.json()["encoding"] == "gb18030"
    assert "类别甲" in response.json()["preview"][0]["values"]["label"]


def test_exact_duplicate_and_record_id_duplicate_detected(client: TestClient) -> None:
    _, audit = _audit_demo(client)
    findings = audit["findings"]
    exact = next(item for item in findings if "duplicate" in item["rule_id"] and "exact" in item["rule_id"])
    assert "R010" in exact["affected_record_ids"]
    assert exact["evidence"]["affected_count"] >= 2
    record = next(item for item in findings if item["rule_id"].startswith("duplicate") and "record_id" in item["rule_id"])
    assert "R010" in record["affected_record_ids"]
    assert record["affected_rows"]


def test_patient_cross_split_leakage_has_real_records(client: TestClient) -> None:
    _, audit = _audit_demo(client)
    entity = next(item for item in audit["findings"] if item["rule_id"].startswith("leakage") and "entity" in item["rule_id"])
    evidence = json.dumps(entity["evidence"], ensure_ascii=False)
    assert "P003" in evidence
    assert "R003" in evidence and "R015" in evidence
    assert "Train" in evidence and "Test" in evidence
    assert entity["severity"] == "critical"
    assert entity["status"] == "confirmed_issue"


def test_different_patients_with_same_features_not_patient_leakage(client: TestClient) -> None:
    content = """record_id,patient_id,label,split,f1,f2
R1,P1,A,Train,10,1
R2,P2,A,Test,10,1
R3,P3,B,Train,11,2
R4,P4,B,Test,12,3
"""
    mapping = {"record_id": "record_id", "entity_id": "patient_id", "label": "label", "split": "split", "feature_columns": ["f1", "f2"], "split_mapping": {}}
    audit = _custom_audit(client, content, mapping)
    assert not any(item["rule_id"].startswith("leakage") and "entity" in item["rule_id"] for item in audit["findings"])
    assert any("duplicate" in item["rule_id"] or "cross_split" in item["rule_id"] for item in audit["findings"])


def test_class_distribution_computed_from_real_rows(client: TestClient) -> None:
    _, audit = _audit_demo(client)
    distribution = audit["summary"]["class_distribution"]
    overall = distribution["overall"]
    with DEMO.open(encoding="utf-8") as handle:
        expected = Counter(row["label"] for row in csv.DictReader(handle))
    actual = {item["label"]: item["count"] for item in overall}
    assert actual == dict(expected)
    assert len(overall) == 6
    assert sum(item["percentage"] for item in overall) == pytest.approx(100.0)
    assert distribution["min_label"] in {"E", "F"}
    assert distribution["max_label"] == "A"
    assert any(item["rule_id"].startswith("class") for item in audit["findings"])


def test_missing_and_constant_features_detected(client: TestClient) -> None:
    _, audit = _audit_demo(client)
    missing = {item["column"]: item for item in audit["summary"]["missing_by_column"]}
    assert missing["feature_biomarker"]["missing_count"] == 3
    assert missing["feature_biomarker"]["missing_rate"] == pytest.approx(3 / 25, rel=1e-4)
    constant = [item for item in audit["findings"] if "constant" in item["rule_id"]]
    assert constant
    assert any("constant_feature" in json.dumps(item["evidence"]) for item in constant)


def test_invalid_mapping_rejected(client: TestClient) -> None:
    dataset = _upload(client).json()
    invalid = {**_mapping(), "record_id": "not_a_column"}
    response = client.put(f"/api/datasets/{dataset['id']}/mapping", json=invalid)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_mapping"
    leaky_features = _mapping(["feature_age", "label"])
    response = client.put(f"/api/datasets/{dataset['id']}/mapping", json=leaky_features)
    assert response.status_code == 400
    assert client.post(f"/api/datasets/{dataset['id']}/audit").status_code == 400


def test_unsupported_split_value_and_custom_mapping(client: TestClient) -> None:
    content = """record_id,patient_id,label,split,f1
R1,P1,A,Train,1
R2,P2,A,unexpected,2
R3,P3,B,Train,3
R4,P4,B,unexpected,4
"""
    mapping = {"record_id": "record_id", "entity_id": "patient_id", "label": "label", "split": "split", "feature_columns": ["f1"], "split_mapping": {}}
    audit = _custom_audit(client, content, mapping)
    assert any("split" in item["rule_id"] and "unsupported" in item["rule_id"] for item in audit["findings"])

    custom = _custom_audit(client, content, {**mapping, "split_mapping": {"unexpected": "Test"}})
    assert not any("split" in item["rule_id"] and "unsupported" in item["rule_id"] for item in custom["findings"])


def test_normal_dataset_has_no_deterministic_leakage_or_duplicates(client: TestClient) -> None:
    content = """record_id,patient_id,label,split,f1,f2
R1,P1,A,Train,1,10
R2,P2,B,Train,2,20
R3,P3,A,Train,3,30
R4,P4,B,Train,4,40
R5,P5,A,Test,5,50
R6,P6,B,Test,6,60
R7,P7,A,Validation,7,70
R8,P8,B,Validation,8,80
"""
    mapping = {"record_id": "record_id", "entity_id": "patient_id", "label": "label", "split": "split", "feature_columns": ["f1", "f2"], "split_mapping": {}}
    audit = _custom_audit(client, content, mapping)
    assert not any(item["rule_id"].startswith("leakage") for item in audit["findings"])
    assert not any(item["rule_id"].startswith("duplicate") for item in audit["findings"])
    assert audit["status"] == "completed"


def test_audit_requires_user_confirmed_mapping(client: TestClient) -> None:
    dataset = _upload(client).json()
    response = client.post(f"/api/datasets/{dataset['id']}/audit")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "mapping_not_confirmed"


def test_audit_results_and_history_survive_restart(client: TestClient) -> None:
    dataset, audit = _audit_demo(client)
    history = client.get(f"/api/datasets/{dataset['id']}/audits")
    assert history.status_code == 200
    assert history.json()["total"] == 1
    assert history.json()["items"][0]["finding_count"] == len(audit["findings"])
    with TestClient(app) as restarted:
        detail = restarted.get(f"/api/audits/{audit['id']}")
        assert detail.status_code == 200
        assert len(detail.json()["findings"]) == len(audit["findings"])
        findings = restarted.get(f"/api/audits/{audit['id']}/findings")
        assert findings.status_code == 200
        assert findings.json()[0]["finding_id"]
        assert restarted.get(f"/api/datasets/{dataset['id']}").json()["latest_audit_id"] == audit["id"]


def test_export_markdown_and_json_reports(client: TestClient) -> None:
    _, audit = _audit_demo(client)
    markdown = client.get(f"/api/audits/{audit['id']}/export")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "Data Guardian 审计报告" in markdown.text
    assert "P003" in markdown.text
    exported = client.get(f"/api/audits/{audit['id']}/export", params={"format": "json"})
    assert exported.status_code == 200
    body = exported.json()
    assert body["id"] == audit["id"]
    assert body["summary"]["deterministic"] is True
    assert body["findings"]


def test_rules_run_without_llm_and_do_not_fake_ai(client: TestClient) -> None:
    _, audit = _audit_demo(client)
    assert audit["ai_status"] == "not_used"
    assert audit["summary"]["deterministic"] is True
    assert "未调用 LLM" in audit["summary"]["ai_note"]
    assert audit["findings"]
    listed = client.get("/api/datasets").json()
    assert listed["ai_configured"] is False


def test_feature_distribution_difference_is_not_labelled_leakage(client: TestClient) -> None:
    _, audit = _audit_demo(client)
    distribution_findings = [
        item for item in audit["findings"]
        if "distribution" in item["rule_id"] or "shift" in item["rule_id"]
    ]
    assert distribution_findings
    assert all("leakage" not in item["rule_id"] for item in distribution_findings)
    assert all(item["status"] != "confirmed_issue" for item in distribution_findings)


def test_phase4_schema_initialization_is_idempotent(client: TestClient) -> None:
    from app.db import connect, init_db

    dataset = _upload(client).json()
    init_db()
    init_db()
    with connect() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert {"datasets", "dataset_columns", "dataset_mappings", "audit_runs", "audit_findings"} <= tables
        assert connection.execute("SELECT COUNT(*) FROM datasets").fetchone()[0] == 1
        assert connection.execute("SELECT original_filename FROM datasets WHERE id = ?", (dataset["id"],)).fetchone()[0] == "research.csv"


def test_missing_source_file_is_reported(client: TestClient) -> None:
    from app.config import get_settings

    dataset = _upload(client).json()
    assert client.put(f"/api/datasets/{dataset['id']}/mapping", json=_mapping()).status_code == 200
    stored = get_settings().datasets_dir / next(get_settings().datasets_dir.glob("*.csv")).name
    stored.unlink()
    response = client.post(f"/api/datasets/{dataset['id']}/audit")
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "dataset_file_missing"
