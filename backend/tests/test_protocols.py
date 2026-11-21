"""Protocol Builder API tests."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from app.db import connect, init_db
from app.main import app

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REPROLAB_STORAGE_DIR", str(tmp_path / "storage"))
    monkeypatch.setenv("REPROLAB_MAX_UPLOAD_MB", "20")
    for name in (
        "LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL",
        "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)
    with TestClient(app) as test_client:
        yield test_client


def _sample_bytes() -> bytes:
    return (FIXTURES / "sample_paper.pdf").read_bytes()


def _upload_and_parse(client: TestClient, name: str = "sample_paper.pdf", content: bytes | None = None) -> str:
    upload = client.post(
        "/api/papers/upload",
        files={"file": (name, content if content is not None else _sample_bytes(), "application/pdf")},
    )
    assert upload.status_code == 201, upload.text
    paper_id = upload.json()["id"]
    parsed = client.post(f"/api/papers/{paper_id}/parse")
    assert parsed.status_code == 200, parsed.text
    return paper_id


def _protocol_with_paper_fact(client: TestClient) -> dict:
    """Structured protocol fixture with verbatim parameter evidence in a real PDF page."""
    quote = "batch size: 128;\nlearning rate: 0.001;\nepochs: 30"
    document = pymupdf.open()
    page = document.new_page()
    page.insert_textbox(
        pymupdf.Rect(72, 72, 540, 760),
        f"Structured Protocol Fixture\nHyperparameters:\n{quote}\nEvaluation: macro-F1.",
        fontsize=11,
    )
    content = document.tobytes()
    document.close()
    paper_id = _upload_and_parse(client, "parameter_fixture.pdf", content)
    with connect() as connection:
        connection.execute(
            "INSERT OR REPLACE INTO paper_fields (paper_id, field, value, status, source, confidence)"
            " VALUES (?, 'hyperparameters', ?, 'found', 'heuristic', 0.95)",
            (paper_id, quote),
        )
        connection.execute(
            "INSERT INTO paper_evidence (id, paper_id, field, page, quote)"
            " VALUES ('ev_phase7_hyperparameters', ?, 'hyperparameters', 1, ?)",
            (paper_id, quote),
        )
        connection.commit()
    response = client.post("/api/protocols/generate", json={"paper_id": paper_id})
    assert response.status_code == 201, response.text
    return response.json()


def test_generate_from_parsed_paper(client: TestClient) -> None:
    paper_id = _upload_and_parse(client)
    generate = client.post("/api/protocols/generate", json={"paper_id": paper_id})
    assert generate.status_code == 201, generate.text
    protocol = generate.json()

    assert protocol["paper_id"] == paper_id
    assert protocol["ai_status"] == "unconfigured"
    assert protocol["agent_method"] == "rule_template"
    assert protocol["status"] == "generated"
    assert protocol["version_no"] == 1
    assert len(protocol["steps"]) >= 5
    assert len(protocol["parameters"]) >= 3
    assert protocol["goal"], "goal should not be empty"

    # Heuristic draft must at least differentiate paper facts from suggestions
    info_types = {step["information_type"] for step in protocol["steps"]}
    assert "derived_suggestion" in info_types or "paper_fact" in info_types, protocol["steps"]

    # Ensure paper facts reference real paper evidence ids
    paper_evidence_ids = {item["id"] for item in client.get(f"/api/papers/{paper_id}/evidence").json()}
    for step in protocol["steps"]:
        if step["information_type"] == "paper_fact" and step["evidence_refs"]:
            assert any(ref in paper_evidence_ids for ref in step["evidence_refs"]), step

    # Unknown parameters must not pretend to be paper facts
    unknown_params = [param for param in protocol["parameters"] if param["source_type"] == "unknown"]
    assert unknown_params, protocol["parameters"]
    for param in unknown_params:
        assert param["value"] is None
        assert param["source_field"] is None
        assert param["evidence_id"] is None
        assert param["page_number"] is None

    # Unknown questions surfaced
    assert any(item["question"] for item in protocol["open_questions"])

    # GET detail
    detail = client.get(f"/api/protocols/{protocol['id']}")
    assert detail.status_code == 200
    assert detail.json()["id"] == protocol["id"]


def test_list_protocols(client: TestClient) -> None:
    paper_id = _upload_and_parse(client)
    client.post("/api/protocols/generate", json={"paper_id": paper_id, "name": "A"})
    client.post("/api/protocols/generate", json={"paper_id": paper_id, "name": "B"})
    listed = client.get("/api/protocols")
    assert listed.status_code == 200
    items = listed.json()["items"]
    assert len(items) == 2
    assert items[0]["parsed_paper"] is True


def test_generate_rejects_unparsed_paper(client: TestClient) -> None:
    # Upload without parsing
    upload = client.post(
        "/api/papers/upload",
        files={"file": ("sample_paper.pdf", _sample_bytes(), "application/pdf")},
    )
    assert upload.status_code == 201
    paper_id = upload.json()["id"]
    generate = client.post("/api/protocols/generate", json={"paper_id": paper_id})
    assert generate.status_code == 400
    assert generate.json()["detail"]["code"] == "paper_not_parsed"


def test_generate_rejects_missing_paper(client: TestClient) -> None:
    response = client.post("/api/protocols/generate", json={"paper_id": "paper_missing"})
    assert response.status_code == 404


def test_generate_without_any_facts_rejected(client: TestClient) -> None:
    # Blank PDF (extracts text but no structured facts)
    import pymupdf
    doc = pymupdf.open()
    doc.new_page()
    blob = doc.tobytes()
    doc.close()
    upload = client.post(
        "/api/papers/upload",
        files={"file": ("blank.pdf", blob, "application/pdf")},
    )
    assert upload.status_code == 201
    paper_id = upload.json()["id"]
    parsed = client.post(f"/api/papers/{paper_id}/parse")
    assert parsed.status_code == 200
    generate = client.post("/api/protocols/generate", json={"paper_id": paper_id})
    assert generate.status_code == 400
    assert generate.json()["detail"]["code"] == "paper_not_parsed" or generate.json()["detail"]["code"] == "no_extractable_facts"


def test_steps_have_real_evidence_or_unknown(client: TestClient) -> None:
    paper_id = _upload_and_parse(client)
    protocol = client.post("/api/protocols/generate", json={"paper_id": paper_id}).json()
    paper_evidence_ids = {item["id"] for item in client.get(f"/api/papers/{paper_id}/evidence").json()}
    for step in protocol["steps"]:
        if step["information_type"] == "paper_fact":
            assert step["evidence_refs"], step
            assert all(ref in paper_evidence_ids for ref in step["evidence_refs"]), step


def test_update_persists(client: TestClient) -> None:
    paper_id = _upload_and_parse(client)
    protocol = client.post("/api/protocols/generate", json={"paper_id": paper_id}).json()
    step_id = protocol["steps"][0]["id"]
    param_id = protocol["parameters"][0]["id"]
    update = client.put(
        f"/api/protocols/{protocol['id']}",
        json={
            "name": "updated name",
            "status": "saved",
            "steps": [
                {
                    "id": step_id,
                    "title": protocol["steps"][0]["title"],
                    "description": "updated description",
                    "order_no": 1,
                    "dependencies": [],
                    "required_inputs": [],
                    "expected_outputs": [],
                    "status": "done",
                    "information_type": "paper_fact",
                    "evidence_refs": protocol["steps"][0]["evidence_refs"],
                },
            ],
            "parameters": [
                {
                    "id": param_id,
                    "name": protocol["parameters"][0]["name"],
                    "value": "manually edited value",
                    "confirmed": True,
                    "source_type": "paper_fact",
                    "note": "checked",
                },
            ],
        },
    )
    assert update.status_code == 200, update.text
    detail = client.get(f"/api/protocols/{protocol['id']}").json()
    assert detail["name"] == "updated name"
    assert detail["status"] == "saved"
    assert detail["steps"][0]["status"] == "done"
    updated_param = next(item for item in detail["parameters"] if item["id"] == param_id)
    assert updated_param["confirmed"] is True
    assert updated_param["value"] == "manually edited value"
    assert updated_param["history"]
    assert any(item.get("action") == "edit" for item in updated_param["history"])


def test_save_version_and_versions_list(client: TestClient) -> None:
    paper_id = _upload_and_parse(client)
    protocol = client.post("/api/protocols/generate", json={"paper_id": paper_id}).json()
    v1 = client.post(f"/api/protocols/{protocol['id']}/versions", json={"message": "first"})
    assert v1.status_code == 201, v1.text
    assert v1.json()["version_no"] == 2
    v2 = client.post(f"/api/protocols/{protocol['id']}/versions", json={"message": "second"})
    assert v2.status_code == 201
    versions = client.get(f"/api/protocols/{protocol['id']}/versions").json()
    assert len(versions) == 3, versions  # initial + 2 saved
    assert versions[0]["version_no"] == 3


def test_export_markdown_and_json(client: TestClient) -> None:
    paper_id = _upload_and_parse(client)
    protocol = client.post("/api/protocols/generate", json={"paper_id": paper_id}).json()
    md = client.get(f"/api/protocols/{protocol['id']}/export")
    assert md.status_code == 200
    assert "# " in md.text
    assert "## 实验步骤" in md.text
    assert "## 参数表" in md.text
    assert md.headers["content-type"].startswith("text/markdown")

    js = client.get(f"/api/protocols/{protocol['id']}/export", params={"format": "json"})
    assert js.status_code == 200
    body = js.json()
    assert body["id"] == protocol["id"]
    assert body["steps"]
    assert js.headers["content-type"].startswith("application/json")


def test_protocol_delete(client: TestClient) -> None:
    paper_id = _upload_and_parse(client)
    protocol = client.post("/api/protocols/generate", json={"paper_id": paper_id}).json()
    assert client.delete(f"/api/protocols/{protocol['id']}").status_code == 204
    assert client.get(f"/api/protocols/{protocol['id']}").status_code == 404
    assert client.get("/api/protocols").json()["total"] == 0


def test_protocol_not_found(client: TestClient) -> None:
    paper_id = _upload_and_parse(client)
    assert client.get("/api/protocols/protocol_missing").status_code == 404
    assert client.put("/api/protocols/protocol_missing", json={}).status_code == 404
    assert client.delete("/api/protocols/protocol_missing").status_code == 404
    assert client.get("/api/protocols/protocol_missing/versions").status_code == 404
    assert client.get("/api/protocols/protocol_missing/export").status_code == 404


def test_ai_configured_flag(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    # Default is unconfigured
    paper_id = _upload_and_parse(client)
    protocol = client.post("/api/protocols/generate", json={"paper_id": paper_id}).json()
    assert protocol["ai_status"] == "unconfigured"


def test_persists_after_restart(client: TestClient) -> None:
    """New TestClient reuses the same tmp_path; protocol should still be there."""
    paper_id = _upload_and_parse(client)
    protocol_id = client.post("/api/protocols/generate", json={"paper_id": paper_id}).json()["id"]
    # Second connection to same DB dir should see it
    assert client.get(f"/api/protocols/{protocol_id}").status_code == 200
    assert client.get("/api/protocols").json()["total"] == 1


def test_cross_paper_evidence_is_rejected_without_partial_update(client: TestClient) -> None:
    protocol = _protocol_with_paper_fact(client)
    other_paper_id = _upload_and_parse(client, "other_paper.pdf")
    other_evidence = client.get(f"/api/papers/{other_paper_id}/evidence").json()
    assert other_evidence
    step = protocol["steps"][0]
    response = client.put(
        f"/api/protocols/{protocol['id']}",
        json={
            "name": "must-not-be-saved",
            "steps": [{
                "id": step["id"],
                "title": step["title"],
                "information_type": "paper_fact",
                "evidence_refs": [other_evidence[0]["id"]],
            }],
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_evidence"
    detail = client.get(f"/api/protocols/{protocol['id']}").json()
    assert detail["name"] == protocol["name"]
    assert detail["steps"][0]["evidence_refs"] == step["evidence_refs"]


def test_llm_unknown_and_invalid_paper_fact_are_sanitized(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mock only validates output guards; it is not a live-LLM acceptance result."""
    class FakeProvider:
        configured = True

        def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
            return {
                "steps": [{
                    "step_id": "invented_fact",
                    "title": "Unsupported fact",
                    "information_type": "paper_fact",
                    "evidence_refs": ["evidence_from_another_paper"],
                    "dependencies": [],
                }],
                "parameters": [
                    {
                        "name": "fabricated unknown",
                        "value": 999,
                        "source_type": "unknown",
                        "source_field": "invented",
                        "evidence_id": "invented",
                        "page_number": 99,
                    },
                    {
                        "name": "unsupported paper fact",
                        "value": 123,
                        "source_type": "paper_fact",
                        "evidence_id": "evidence_from_another_paper",
                    },
                ],
            }

    monkeypatch.setattr("app.services.protocol_agent.LLMProvider", FakeProvider)
    paper_id = _upload_and_parse(client)
    response = client.post("/api/protocols/generate", json={"paper_id": paper_id})
    assert response.status_code == 201, response.text
    protocol = response.json()
    unknown = next(item for item in protocol["parameters"] if item["name"] == "fabricated unknown")
    assert unknown["value"] is None
    assert unknown["source_field"] is None
    assert unknown["evidence_id"] is None
    assert unknown["page_number"] is None
    invalid_fact = next(item for item in protocol["parameters"] if item["name"] == "unsupported paper fact")
    assert invalid_fact["source_type"] == "derived_suggestion"
    assert invalid_fact["evidence_id"] is None
    invalid_step = next(item for item in protocol["steps"] if item["step_id"] == "invented_fact")
    assert invalid_step["information_type"] == "derived_suggestion"
    assert invalid_step["evidence_refs"] == []


def test_step_information_type_enforced(client: TestClient) -> None:
    """Update rejects unknown information_type values by normalizing them to derived_suggestion."""
    paper_id = _upload_and_parse(client)
    protocol = client.post("/api/protocols/generate", json={"paper_id": paper_id}).json()
    step_id = protocol["steps"][0]["id"]
    update = client.put(
        f"/api/protocols/{protocol['id']}",
        json={
            "steps": [{
                "id": step_id,
                "title": "x", "description": "y", "order_no": 1,
                "dependencies": [], "required_inputs": [], "expected_outputs": [],
                "status": "planned",
                "information_type": "invented_by_ai",
                "evidence_refs": [],
            }],
        },
    )
    assert update.status_code == 200, update.text
    detail = client.get(f"/api/protocols/{protocol['id']}").json()
    assert detail["steps"][0]["information_type"] == "derived_suggestion"


def test_original_value_survives_multiple_edits_and_restore(client: TestClient) -> None:
    protocol = _protocol_with_paper_fact(client)
    param = next(item for item in protocol["parameters"] if item["original_value"] is not None)
    original = param["original_value"]
    for value in ("first-edit", "second-edit"):
        response = client.put(
            f"/api/protocols/{protocol['id']}",
            json={"parameters": [{"id": param["id"], "value": value}]},
        )
        assert response.status_code == 200, response.text
    restored = client.put(
        f"/api/protocols/{protocol['id']}",
        json={"parameters": [{"id": param["id"], "modified_value": None}]},
    )
    assert restored.status_code == 200, restored.text
    updated = next(item for item in restored.json()["parameters"] if item["id"] == param["id"])
    assert updated["original_value"] == original
    assert updated["value"] == original
    assert updated["modified_value"] is None
    assert [item["action"] for item in updated["history"]] == ["edit", "edit", "restore"]


def test_manual_unknown_supplement_preserves_paper_originals(client: TestClient) -> None:
    protocol = _protocol_with_paper_fact(client)
    unknown = next(item for item in protocol["parameters"] if item["source_type"] == "unknown")
    paper_fact = next(
        item for item in protocol["parameters"]
        if item["source_type"] == "paper_fact" and item["original_value"] is not None
    )
    response = client.put(
        f"/api/protocols/{protocol['id']}",
        json={"parameters": [{"id": unknown["id"], "value": "manually-supplied"}]},
    )
    assert response.status_code == 200, response.text
    parameters = {item["id"]: item for item in response.json()["parameters"]}
    supplemented = parameters[unknown["id"]]
    untouched_fact = parameters[paper_fact["id"]]
    assert supplemented["original_value"] is None
    assert supplemented["value"] == "manually-supplied"
    assert supplemented["modified_value"] == "manually-supplied"
    assert supplemented["source_type"] == "unknown"
    assert untouched_fact["original_value"] == paper_fact["original_value"]
    assert untouched_fact["value"] == paper_fact["value"]
    assert untouched_fact["evidence_id"] == paper_fact["evidence_id"]


def test_original_value_migration_backfills_from_initial_snapshot(client: TestClient) -> None:
    protocol = _protocol_with_paper_fact(client)
    param = next(item for item in protocol["parameters"] if item["original_value"] is not None)
    original = param["original_value"]
    edited = client.put(
        f"/api/protocols/{protocol['id']}",
        json={"parameters": [{"id": param["id"], "value": "current-after-edit"}]},
    )
    assert edited.status_code == 200

    # Isolated legacy-schema simulation only; the daily database is never altered by tests.
    with connect() as connection:
        connection.execute("ALTER TABLE protocol_parameters DROP COLUMN original_value")
        connection.commit()
    init_db()
    detail = client.get(f"/api/protocols/{protocol['id']}").json()
    migrated = next(item for item in detail["parameters"] if item["id"] == param["id"])
    assert migrated["original_value"] == original
    assert migrated["value"] == "current-after-edit"


def test_invalid_dag_update_rolls_back_all_changes(client: TestClient) -> None:
    paper_id = _upload_and_parse(client)
    protocol = client.post("/api/protocols/generate", json={"paper_id": paper_id}).json()
    before = client.get(f"/api/protocols/{protocol['id']}").json()
    first, second = before["steps"][:2]
    response = client.put(
        f"/api/protocols/{protocol['id']}",
        json={
            "name": "must-roll-back",
            "steps": [
                {"id": first["id"], "title": first["title"], "dependencies": [second["step_id"]]},
                {"id": second["id"], "title": second["title"], "dependencies": [first["step_id"]]},
            ],
        },
    )
    assert response.status_code == 400, response.text
    after = client.get(f"/api/protocols/{protocol['id']}").json()
    assert after["name"] == before["name"]
    assert [(item["id"], item["dependencies"]) for item in after["steps"]] == [
        (item["id"], item["dependencies"]) for item in before["steps"]
    ]


def test_version_snapshot_contains_goal_and_parameter_provenance(client: TestClient) -> None:
    protocol = _protocol_with_paper_fact(client)
    param = next(
        item for item in protocol["parameters"]
        if item["source_type"] == "paper_fact" and item["evidence_id"]
    )
    updated = client.put(
        f"/api/protocols/{protocol['id']}", json={"goal": "snapshot goal with traceable sources"}
    )
    assert updated.status_code == 200
    saved = client.post(f"/api/protocols/{protocol['id']}/versions", json={"message": "phase7 provenance"})
    assert saved.status_code == 201
    with connect() as connection:
        row = connection.execute(
            "SELECT snapshot FROM protocol_versions WHERE id = ?", (saved.json()["id"],)
        ).fetchone()
    snapshot = json.loads(row["snapshot"])
    snapshot_param = next(item for item in snapshot["parameters"] if item["id"] == param["id"])
    assert snapshot["goal"] == "snapshot goal with traceable sources"
    assert snapshot_param["source_type"] == param["source_type"]
    assert snapshot_param["source_field"] == param["source_field"]
    assert snapshot_param["evidence_id"] == param["evidence_id"]
    assert snapshot_param["original_value"] == param["original_value"]
