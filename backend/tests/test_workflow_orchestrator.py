"""Phase 6: multi-agent research workflow orchestrator.

These tests drive the real orchestrator, which in turn calls the real Phase 1-5
business services (paper parsing, protocol generation, Data Guardian audit,
experiment comparison, insight generation). No business engine is mocked.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.db import connect, init_db
from app.main import app
from app.services import workflow_engine
from app.services.workflow_state import WorkflowStateError

FIXTURES = Path(__file__).resolve().parent / "fixtures"
LEAKY_CSV = FIXTURES / "simulated_six_class.csv"

PAPER_TEXT = """Title: Federated ECG Classification with Boundary-Sensitive Loss
Abstract: We study six-class ECG classification under federated learning.
Method: We propose FedAvg with Boundary-Sensitive Margin (BSM) loss.
Dataset: MIT-BIH Arrhythmia, six classes (N, SVEB, VEB, F, Q, B).
Parameters: batch size 128, learning rate 0.001, epochs 30, optimizer Adam.
Evaluation: macro-F1 and accuracy over three random seeds (42, 123, 2024).
"""


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REPROLAB_STORAGE_DIR", str(tmp_path / "storage"))
    for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with TestClient(app) as test_client:
        yield test_client


# --------------------------------------------------------------------------- #
# fixtures: create real business records through real services / DB rows
# --------------------------------------------------------------------------- #
def _seed_paper() -> str:
    now = "2026-01-01T00:00:00Z"
    paper_id = "paper_wf_test"
    with connect() as connection:
        connection.execute(
            "INSERT INTO papers (id, original_filename, stored_filename, sha256, file_size, page_count, title,"
            " status, parse_status, ai_status, extraction_method, text_chars, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (paper_id, "ecg.pdf", "ecg.pdf", "sha-wf-1", 1024, 1, "Federated ECG Classification",
             "processed", "pending", "not_used", "none", len(PAPER_TEXT), now, now),
        )
        connection.execute(
            "INSERT INTO paper_pages (paper_id, page, text) VALUES (?,?,?)", (paper_id, 1, PAPER_TEXT)
        )
        connection.commit()
    return paper_id


def _seed_leaky_dataset(client: TestClient) -> str:
    uploaded = client.post("/api/datasets/upload", files={"file": ("six.csv", LEAKY_CSV.read_bytes(), "text/csv")})
    assert uploaded.status_code == 201, uploaded.text
    dataset_id = uploaded.json()["id"]
    mapping = {
        "record_id": "record_id",
        "entity_id": "patient_id",
        "label": "label",
        "split": "split",
        "feature_columns": ["feature_age", "feature_biomarker", "feature_score", "constant_feature"],
        "split_mapping": {},
    }
    assert client.put(f"/api/datasets/{dataset_id}/mapping", json=mapping).status_code == 200
    return dataset_id


def _seed_clean_dataset(client: TestClient) -> str:
    """Upload the same CSV but leave mapping unconfirmed to force a real node failure."""
    uploaded = client.post("/api/datasets/upload", files={"file": ("six.csv", LEAKY_CSV.read_bytes(), "text/csv")})
    assert uploaded.status_code == 201, uploaded.text
    return uploaded.json()["id"]


def _seed_experiments(client: TestClient) -> list[str]:
    seeded = client.post("/api/experiments/demo/seed")
    assert seeded.status_code == 200, seeded.text
    return [item["id"] for item in client.get("/api/experiments").json()["items"]]


def _create(client: TestClient, **payload):
    response = client.post("/api/workflows", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _node(workflow: dict, key: str) -> dict:
    return next(node for node in workflow["nodes"] if node["node_key"] == key)


def _full_workflow(client: TestClient, **overrides) -> dict:
    paper_id = overrides.pop("paper_id", None) or _seed_paper()
    dataset_id = overrides.pop("dataset_id", None) or _seed_leaky_dataset(client)
    experiment_ids = overrides.pop("experiment_ids", None) or _seed_experiments(client)
    return _create(
        client,
        name="ECG 六分类复现",
        workflow_type="full_reproduction",
        paper_id=paper_id,
        dataset_id=dataset_id,
        experiment_ids=experiment_ids,
        **overrides,
    )


# 1 + 2. complete four-agent workflow and dependency ordering
def test_full_four_agent_workflow_runs_real_services(client: TestClient) -> None:
    workflow = _full_workflow(client)
    assert [node["node_key"] for node in workflow["nodes"]] == [
        "paper_parse", "protocol_generate", "protocol_approve", "data_audit",
        "audit_approve", "experiment_analyze", "report_publish",
    ]
    assert _node(workflow, "protocol_generate")["depends_on"] == ["paper_parse"]

    started = client.post(f"/api/workflows/{workflow['id']}/start").json()
    # Stops at the first human gate; Paper Agent and Protocol Agent already ran.
    assert started["status"] == "waiting_approval"
    assert _node(started, "paper_parse")["status"] == "completed"
    assert _node(started, "protocol_generate")["status"] == "completed"
    protocol_id = _node(started, "protocol_generate")["output_ref"]["protocol_id"]
    assert _node(started, "protocol_approve")["status"] == "waiting_approval"
    assert started["context"]["paper_id"] == workflow["config"]["paper_id"]
    assert started["context"]["protocol_id"] == protocol_id

    approved = client.post(
        f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "protocol_approve", "decision": "approve"}
    ).json()
    # High-risk leakage findings force a second human gate.
    assert _node(approved, "data_audit")["status"] == "completed"
    audit_id = _node(approved, "data_audit")["output_ref"]["audit_id"]
    assert approved["context"]["audit_id"] == audit_id
    assert approved["status"] == "waiting_approval"
    assert _node(approved, "audit_approve")["status"] == "waiting_approval"

    media = client.post(
        f"/api/workflows/{workflow['id']}/approvals",
        json={"node_key": "audit_approve", "decision": "approve", "comment": "已复核泄漏样本"},
    ).json()
    assert _node(media, "experiment_analyze")["status"] == "completed"
    assert media["context"]["insight_id"]
    assert _node(media, "report_publish")["status"] == "waiting_approval"

    final = client.post(
        f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "report_publish", "decision": "approve"}
    ).json()
    assert final["status"] == "completed"
    assert final["progress"]["completed"] == 7

    # Business records really exist and are linked.
    assert client.get(f"/api/protocols/{protocol_id}").status_code == 200
    assert client.get(f"/api/audits/{audit_id}").status_code == 200
    insight_id = final["context"]["insight_id"]
    insight = client.get(f"/api/insights/{insight_id}").json()
    assert insight["ai_status"] == "not_used"
    assert insight["content"]["experimental_summary"]["experiment_count"] == len(final["config"]["experiment_ids"])


# 3. node failure (real input problem) and single-node retry to success
def test_node_failure_and_retry_succeeds(client: TestClient) -> None:
    workflow = _full_workflow(client, dataset_id=_seed_clean_dataset(client))
    started = client.post(f"/api/workflows/{workflow['id']}/start").json()
    assert started["status"] == "waiting_approval"
    failed = client.post(
        f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "protocol_approve", "decision": "approve"}
    ).json()

    assert failed["status"] == "failed"
    audit_node = _node(failed, "data_audit")
    assert audit_node["status"] == "failed"
    assert "映射" in audit_node["error"]
    assert failed["error"]

    # Fix the real cause through the existing Data Guardian API, then retry same node.
    dataset_id = workflow["config"]["dataset_id"]
    mapping = {
        "record_id": "record_id",
        "entity_id": "patient_id",
        "label": "label",
        "split": "split",
        "feature_columns": ["feature_age", "feature_biomarker", "feature_score", "constant_feature"],
        "split_mapping": {},
    }
    assert client.put(f"/api/datasets/{dataset_id}/mapping", json=mapping).status_code == 200

    retried = client.post(f"/api/workflows/{workflow['id']}/nodes/data_audit/retry").json()
    audit_node = _node(retried, "data_audit")
    assert audit_node["status"] == "completed"
    assert audit_node["retry_count"] == 1
    assert audit_node["error"] is None
    assert retried["context"]["audit_id"]

    events = client.get(f"/api/workflows/{workflow['id']}/events").json()
    assert any(event["event_type"] == "node_failed" for event in events)
    assert any(event["event_type"] == "node_retried" for event in events)
    # Upstream successful nodes were not re-executed.
    assert sum(1 for e in events if e["event_type"] == "node_started" and e["payload"].get("node") == "paper_parse") == 0


# 4. retry budget is bounded
def test_retry_limit_enforced(client: TestClient) -> None:
    workflow = _full_workflow(client, dataset_id=_seed_clean_dataset(client))
    client.post(f"/api/workflows/{workflow['id']}/start")
    client.post(f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "protocol_approve", "decision": "approve"})

    first = client.post(f"/api/workflows/{workflow['id']}/nodes/data_audit/retry")
    assert first.status_code == 200
    assert _node(first.json(), "data_audit")["retry_count"] == 1

    second = client.post(f"/api/workflows/{workflow['id']}/nodes/data_audit/retry")
    assert second.status_code == 200
    assert _node(second.json(), "data_audit")["retry_count"] == 2

    third = client.post(f"/api/workflows/{workflow['id']}/nodes/data_audit/retry")
    assert third.status_code == 409
    assert third.json()["detail"]["code"] == "retry_limit_reached"


# 5. successfully completed nodes are never re-executed
def test_completed_node_not_rerun(client: TestClient) -> None:
    workflow = _full_workflow(client)
    client.post(f"/api/workflows/{workflow['id']}/start")

    retry = client.post(f"/api/workflows/{workflow['id']}/nodes/paper_parse/retry")
    assert retry.status_code == 409
    assert retry.json()["detail"]["code"] == "node_already_finished"

    with connect() as connection:
        evidence_count = connection.execute(
            "SELECT COUNT(*) FROM paper_evidence WHERE paper_id = ?", (workflow["config"]["paper_id"],)
        ).fetchone()[0]
        protocols = connection.execute(
            "SELECT COUNT(*) FROM protocols WHERE paper_id = ?", (workflow["config"]["paper_id"],)
        ).fetchone()[0]
    events = client.get(f"/api/workflows/{workflow['id']}/events").json()
    assert sum(1 for event in events if event["event_type"] == "node_started") == 2
    assert evidence_count >= 0
    assert protocols == 1


# 6. idempotent workflow creation
def test_idempotent_workflow_creation(client: TestClient) -> None:
    paper_id = _seed_paper()
    first = _create(client, name="复现任务", paper_id=paper_id, idempotency_key="idem-001")
    second = _create(client, name="复现任务", paper_id=paper_id, idempotency_key="idem-001")
    assert first["id"] == second["id"]
    with connect() as connection:
        count = connection.execute("SELECT COUNT(*) FROM research_workflows").fetchone()[0]
    assert count == 1


# 7. repeated start does not duplicate business resources
def test_repeated_start_is_idempotent(client: TestClient) -> None:
    workflow = _full_workflow(client)
    client.post(f"/api/workflows/{workflow['id']}/start")
    again = client.post(f"/api/workflows/{workflow['id']}/start")
    assert again.status_code == 200
    assert again.json()["status"] == "waiting_approval"
    paper_id = workflow["config"]["paper_id"]
    with connect() as connection:
        protocols = connection.execute("SELECT COUNT(*) FROM protocols WHERE paper_id = ?", (paper_id,)).fetchone()[0]
        audits = connection.execute(
            "SELECT COUNT(*) FROM audit_runs WHERE dataset_id = ?", (workflow["config"]["dataset_id"],)
        ).fetchone()[0]
    assert protocols == 1
    assert audits == 0  # audit node has not run yet (blocked by the first approval gate)


# 8. human approval is mandatory; rejection is recorded without touching data
def test_approval_rejection_preserves_business_data(client: TestClient) -> None:
    workflow = _full_workflow(client)
    started = client.post(f"/api/workflows/{workflow['id']}/start").json()
    protocol_id = _node(started, "protocol_generate")["output_ref"]["protocol_id"]
    before = client.get(f"/api/protocols/{protocol_id}").json()

    rejected = client.post(
        f"/api/workflows/{workflow['id']}/approvals",
        json={"node_key": "protocol_approve", "decision": "reject", "comment": "参数与论文不一致"},
    ).json()
    assert rejected["status"] == "failed"
    assert _node(rejected, "protocol_approve")["status"] == "failed"
    assert "参数与论文不一致" in _node(rejected, "protocol_approve")["error"]
    assert rejected["approvals"][-1]["decision"] == "reject"

    after = client.get(f"/api/protocols/{protocol_id}").json()
    assert after["name"] == before["name"]
    assert after["status"] == before["status"]
    assert after["goal"] == before["goal"]

    events = client.get(f"/api/workflows/{workflow['id']}/events").json()
    assert any(event["event_type"] == "approval_rejected" for event in events)


# 9. cancel a workflow
def test_cancel_workflow(client: TestClient) -> None:
    workflow = _full_workflow(client)
    client.post(f"/api/workflows/{workflow['id']}/start")
    cancelled = client.post(f"/api/workflows/{workflow['id']}/cancel").json()
    assert cancelled["status"] == "cancelled"
    assert all(
        node["status"] in {"completed", "skipped"} for node in cancelled["nodes"]
    )
    restart = client.post(f"/api/workflows/{workflow['id']}/start")
    assert restart.status_code == 409
    assert restart.json()["detail"]["code"] == "workflow_cancelled"


# 10. persistence and service restart recovery
def test_persistence_and_restart_recovery(client: TestClient) -> None:
    workflow = _full_workflow(client)
    client.post(f"/api/workflows/{workflow['id']}/start")

    with TestClient(app) as restarted:
        restored = restarted.get(f"/api/workflows/{workflow['id']}").json()
        assert restored["status"] == "waiting_approval"
        assert _node(restored, "paper_parse")["status"] == "completed"
        assert _node(restored, "protocol_approve")["status"] == "waiting_approval"
        events = restarted.get(f"/api/workflows/{workflow['id']}/events").json()
        assert any(event["event_type"] == "approval_requested" for event in events)
        listed = restarted.get("/api/workflows").json()
        assert listed["total"] == 1

        # Continue the workflow after restart using the persisted state.
        resumed = restarted.post(
            f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "protocol_approve", "decision": "approve"}
        ).json()
        assert _node(resumed, "data_audit")["status"] == "completed"


# 11. illegal states and unknown resources
def test_illegal_state_and_missing_resource(client: TestClient) -> None:
    workflow = _full_workflow(client)
    client.post(f"/api/workflows/{workflow['id']}/start")

    illegal = client.post(
        f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "paper_parse", "decision": "approve"}
    )
    assert illegal.status_code == 409
    assert illegal.json()["detail"]["code"] == "node_not_waiting_approval"

    unknown_node = client.post(f"/api/workflows/{workflow['id']}/nodes/not_a_node/retry")
    assert unknown_node.status_code == 409
    assert unknown_node.json()["detail"]["code"] == "node_not_found"

    missing = client.get("/api/workflows/wf_missing")
    assert missing.status_code == 404

    bad_decision = client.post(
        f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "protocol_approve", "decision": "maybe"}
    )
    assert bad_decision.status_code == 422


# 12. report traceability (all numbers trace to referenced business records)
def test_report_traceability(client: TestClient) -> None:
    workflow = _full_workflow(client)
    client.post(f"/api/workflows/{workflow['id']}/start")
    client.post(f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "protocol_approve", "decision": "approve"})
    client.post(f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "audit_approve", "decision": "approve"})
    final = client.post(
        f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "report_publish", "decision": "approve"}
    ).json()
    assert final["status"] == "completed"
    context = final["context"]

    report = client.get(f"/api/workflows/{workflow['id']}/report").json()
    refs = report["references"]
    assert refs["paper_id"] == context["paper_id"]
    assert refs["protocol_id"] == context["protocol_id"]
    assert refs["audit_id"] == context["audit_id"]
    assert refs["comparison_id"] == context["comparison_id"]
    assert refs["insight_id"] == context["insight_id"]
    assert refs["evidence_ids"]
    assert report["is_simulated"] is True
    assert report["ai_status"] == "not_used"
    titles = [section["title"] for section in report["sections"]]
    for required in ("论文与证据", "实验方案与参数", "数据质量审计", "实验结果与指标对比", "AI 科研洞察", "来源追溯与声明"):
        assert required in titles

    markdown = client.get(f"/api/workflows/{workflow['id']}/report/export", params={"format": "markdown"})
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    text = markdown.text
    assert "模拟数据" in text
    assert context["insight_id"] in text
    assert context["audit_id"] in text

    exported = client.get(f"/api/workflows/{workflow['id']}/report/export", params={"format": "json"})
    assert exported.status_code == 200
    assert exported.json()["references"]["comparison_id"] == context["comparison_id"]


# 13. analysis-only workflow may skip paper/protocol/audit, and says so
def test_analysis_only_skips_optional_steps_but_declares_gap(client: TestClient) -> None:
    experiment_ids = _seed_experiments(client)
    workflow = _create(
        client, name="仅分析", workflow_type="analysis_only", experiment_ids=experiment_ids
    )
    started = client.post(f"/api/workflows/{workflow['id']}/start").json()
    assert _node(started, "paper_parse")["status"] == "skipped"
    assert _node(started, "protocol_generate")["status"] == "skipped"
    assert _node(started, "protocol_approve")["status"] == "skipped"
    assert _node(started, "data_audit")["status"] == "skipped"
    assert _node(started, "audit_approve")["status"] == "skipped"
    assert _node(started, "experiment_analyze")["status"] == "completed"
    assert started["status"] == "waiting_approval"
    assert _node(started, "report_publish")["status"] == "waiting_approval"

    final = client.post(
        f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "report_publish", "decision": "approve"}
    ).json()
    assert final["status"] == "completed"

    report = client.get(f"/api/workflows/{workflow['id']}/report").json()
    assert report["data_validation_skipped"] is True
    limitations = next(section for section in report["sections"] if section["kind"] == "limitations")
    assert any("数据验证未执行" in line for line in limitations["lines"])
    audit_section = next(section for section in report["sections"] if section["kind"] == "audit")
    assert any("未执行数据质量审计" in line for line in audit_section["lines"])


# 14. a required analysis node cannot be skipped to fake completion
def test_missing_experiments_fails_instead_of_faking(client: TestClient) -> None:
    workflow = _create(client, name="缺实验", workflow_type="analysis_only")
    result = client.post(f"/api/workflows/{workflow['id']}/start").json()
    assert result["status"] == "failed"
    node = _node(result, "experiment_analyze")
    assert node["status"] == "failed"
    assert "experiment_ids" in node["error"]
    assert result["error"]


# 15. existing modules still work (no regression from the new router/schema)
def test_existing_modules_still_respond(client: TestClient) -> None:
    for path in ("/api/papers", "/api/protocols", "/api/datasets", "/api/experiments", "/api/health"):
        response = client.get(path)
        assert response.status_code == 200, path
    assert client.get("/api/health").json()["version"] == "0.5.0"


def test_high_risk_approval_and_final_report_snapshot(client: TestClient) -> None:
    workflow = _full_workflow(client)
    client.post(f"/api/workflows/{workflow['id']}/start")
    client.post(f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "protocol_approve", "decision": "approve"})
    client.post(f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "audit_approve", "decision": "approve"})
    final = client.post(
        f"/api/workflows/{workflow['id']}/approvals", json={"node_key": "report_publish", "decision": "approve"}
    ).json()
    report = client.get(f"/api/workflows/{workflow['id']}/report").json()

    assert final["report_finalized"] is True
    assert report["finalization_scope"] == "local_finalization"
    assert report["risk_summary"]["unresolved_high_risk_count"] > 0
    assert report["risk_summary"]["risk_acknowledged"] is True
    assert report["risk_summary"]["audit_passed"] is False
    approval = next(item for item in final["approvals"] if item["audit_id"])
    assert approval["input_version"]
    assert approval["finding_ids"]
    assert approval["semantics"] == "risk_acknowledged_continue_analysis"
    with connect() as connection:
        statuses = connection.execute(
            "SELECT DISTINCT status FROM audit_findings WHERE audit_id = ?", (report["references"]["audit_id"],)
        ).fetchall()
    assert all(row["status"] not in {"resolved", "fixed"} for row in statuses)

    protocol_id = report["references"]["protocol_id"]
    changed = client.put(f"/api/protocols/{protocol_id}", json={"goal": "定稿后的新目标"})
    assert changed.status_code == 200
    assert client.get(f"/api/workflows/{workflow['id']}/report").json() == report
    markdown = client.get(f"/api/workflows/{workflow['id']}/report/export").text
    assert "定稿后的新目标" not in markdown
    assert "批准继续不代表审计通过" in markdown
    assert "本地定稿" in markdown


@pytest.fixture()
def configured_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_BASE_URL", "https://example.invalid/v1")
    monkeypatch.setenv("LLM_API_KEY", "fixture-token")
    monkeypatch.setenv("LLM_MODEL", "fixture-model")


def test_workflow_llm_opt_out_never_calls_provider(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, configured_llm: None,
) -> None:
    def unexpected_request(*args, **kwargs):
        pytest.fail("A deterministic workflow attempted an external model request")

    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", unexpected_request)
    workflow = _full_workflow(client, use_llm=False)
    base = f"/api/workflows/{workflow['id']}"
    client.post(f"{base}/start").raise_for_status()
    for gate in ("protocol_approve", "audit_approve", "report_publish"):
        response = client.post(f"{base}/approvals", json={"node_key": gate, "decision": "approve"})
        response.raise_for_status()
    workflow = response.json()
    assert workflow["status"] == "completed"
    for key in ("paper_parse", "protocol_generate", "experiment_analyze"):
        output = _node(workflow, key)["output_ref"]
        assert output["execution_mode"] == "rule_compute"
        assert output["ai_status"] == "not_used"
        assert "llm_requests" not in output


def test_workflow_traces_http_retry_fallback_and_enrichment(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, configured_llm: None,
) -> None:
    paper_title = PAPER_TEXT.splitlines()[0].removeprefix("Title: ")
    paper_result = {"fields": {"title": {
        "value": paper_title, "status": "found", "evidence": [{"page": 1, "quote": paper_title}],
    }}}

    def completion(content: dict) -> httpx.Response:
        return httpx.Response(200, headers={"x-request-id": "req_fixture"}, json={
            "model": "fixture-model", "choices": [{"message": {"content": json.dumps(content)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        })

    responses = iter([
        httpx.Response(400, text="fixture-token"), completion(paper_result),
        httpx.Response(401, text="fixture-token"), completion({"narrative": "模拟数据存在数据审计风险。"}),
    ])
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", lambda *args, **kwargs: next(responses))
    workflow = _full_workflow(client, use_llm=True)
    base = f"/api/workflows/{workflow['id']}"
    client.post(f"{base}/start").raise_for_status()
    for gate in ("protocol_approve", "audit_approve", "report_publish"):
        response = client.post(f"{base}/approvals", json={"node_key": gate, "decision": "approve"})
        response.raise_for_status()
    workflow = response.json()
    assert workflow["status"] == "completed"
    paper = _node(workflow, "paper_parse")["output_ref"]
    protocol = _node(workflow, "protocol_generate")["output_ref"]
    insight = _node(workflow, "experiment_analyze")["output_ref"]
    assert paper["execution_mode"] == insight["execution_mode"] == "live_llm"
    assert protocol["execution_mode"] == "fallback"
    assert [(item["http_status"], item["compatibility_retry"], item["status"])
            for item in paper["llm_requests"]] == [(400, False, "http_error"), (200, True, "json_received")]
    assert insight["llm_requests"][0]["request_id"] == "req_fixture"
    assert insight["llm_requests"][0]["usage"]["total_tokens"] == 15
    assert protocol["llm_requests"][0]["http_status"] == 401
    protocol_response = client.get(f"/api/protocols/{protocol['protocol_id']}")
    assert "fixture-token" not in protocol_response.text
    report = client.get(f"{base}/report")
    assert "模型请求记录" in report.text
    assert "fixture-token" not in report.text


def test_audit_reuse_requires_matching_mapping(client: TestClient) -> None:
    first = _full_workflow(client)
    client.post(f"/api/workflows/{first['id']}/start")
    client.post(f"/api/workflows/{first['id']}/approvals", json={"node_key": "protocol_approve", "decision": "approve"})
    first_audit = _node(client.get(f"/api/workflows/{first['id']}").json(), "data_audit")["output_ref"]["audit_id"]

    second = _full_workflow(
        client, paper_id=first["config"]["paper_id"], dataset_id=first["config"]["dataset_id"],
        experiment_ids=first["config"]["experiment_ids"],
    )
    client.post(f"/api/workflows/{second['id']}/start")
    client.post(f"/api/workflows/{second['id']}/approvals", json={"node_key": "protocol_approve", "decision": "approve"})
    second_detail = client.get(f"/api/workflows/{second['id']}").json()
    assert _node(second_detail, "data_audit")["output_ref"]["audit_id"] == first_audit
    assert _node(second_detail, "data_audit")["output_ref"]["reuse_match_validated"] is True
    assert all(item["audit_id"] is None for item in second_detail["approvals"])
    assert _node(second_detail, "audit_approve")["status"] == "waiting_approval"

    mapping = {
        "record_id": "record_id", "entity_id": "patient_id", "label": "label", "split": "split",
        "feature_columns": ["feature_age", "feature_biomarker", "feature_score"], "split_mapping": {},
    }
    assert client.put(f"/api/datasets/{first['config']['dataset_id']}/mapping", json=mapping).status_code == 200
    third = _full_workflow(
        client, paper_id=first["config"]["paper_id"], dataset_id=first["config"]["dataset_id"],
        experiment_ids=first["config"]["experiment_ids"],
    )
    client.post(f"/api/workflows/{third['id']}/start")
    client.post(f"/api/workflows/{third['id']}/approvals", json={"node_key": "protocol_approve", "decision": "approve"})
    third_detail = client.get(f"/api/workflows/{third['id']}").json()
    assert _node(third_detail, "data_audit")["output_ref"]["audit_id"] != first_audit
    assert _node(third_detail, "data_audit")["output_ref"]["reused"] is False


def test_fault_injected_saved_audit_is_recovered_without_duplicate(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthetic crash injection only: this is not presented as a production outage."""
    from app.routers.datasets import create_audit

    workflow = _full_workflow(client)
    client.post(f"/api/workflows/{workflow['id']}/start")
    original = workflow_engine.HANDLERS["data_audit"]

    def save_then_crash(context, config):
        detail = create_audit(config["dataset_id"], operation_key=context["_operation_key"])
        context["injected_audit_id"] = detail.id
        raise KeyboardInterrupt("synthetic crash after business commit")

    monkeypatch.setitem(workflow_engine.HANDLERS, "data_audit", save_then_crash)
    with pytest.raises(KeyboardInterrupt):
        workflow_engine.submit_approval(
            workflow["id"], {"node_key": "protocol_approve", "decision": "approve"}
        )
    monkeypatch.setitem(workflow_engine.HANDLERS, "data_audit", original)

    init_db()
    interrupted = client.get(f"/api/workflows/{workflow['id']}").json()
    assert interrupted["status"] == "failed"
    assert _node(interrupted, "data_audit")["status"] == "failed"
    assert "进程中断" in _node(interrupted, "data_audit")["error"]
    audit_id = _node(interrupted, "data_audit")["input_ref"]["operation_key"]
    with connect() as connection:
        saved = connection.execute("SELECT id FROM audit_runs WHERE operation_key = ?", (audit_id,)).fetchone()
    assert saved is not None

    recovered = client.post(f"/api/workflows/{workflow['id']}/nodes/data_audit/retry").json()
    output = _node(recovered, "data_audit")["output_ref"]
    assert output["audit_id"] == saved["id"]
    assert output["recovered"] is True
    with connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM audit_runs WHERE dataset_id = ?", (workflow["config"]["dataset_id"],)
        ).fetchone()[0]
    assert count == 1


def test_fault_recovery_rejects_audit_for_changed_mapping(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Synthetic crash injection must not bypass data/mapping/rule matching."""
    from app.routers.datasets import create_audit

    workflow = _full_workflow(client)
    client.post(f"/api/workflows/{workflow['id']}/start")

    def save_then_crash(context, config):
        create_audit(config["dataset_id"], operation_key=context["_operation_key"])
        raise KeyboardInterrupt("synthetic crash after business commit")

    original = workflow_engine.HANDLERS["data_audit"]
    monkeypatch.setitem(workflow_engine.HANDLERS, "data_audit", save_then_crash)
    with pytest.raises(KeyboardInterrupt):
        workflow_engine.submit_approval(
            workflow["id"], {"node_key": "protocol_approve", "decision": "approve"}
        )
    monkeypatch.setitem(workflow_engine.HANDLERS, "data_audit", original)
    init_db()

    changed_mapping = {
        "record_id": "record_id", "entity_id": "patient_id", "label": "label", "split": "split",
        "feature_columns": ["feature_age", "feature_biomarker", "feature_score"], "split_mapping": {},
    }
    dataset_id = workflow["config"]["dataset_id"]
    assert client.put(f"/api/datasets/{dataset_id}/mapping", json=changed_mapping).status_code == 200
    recovered = client.post(f"/api/workflows/{workflow['id']}/nodes/data_audit/retry")
    assert recovered.status_code == 200, recovered.text
    audit_node = _node(recovered.json(), "data_audit")
    assert audit_node["status"] == "failed"
    assert "不匹配" in audit_node["error"]
    with connect() as connection:
        count = connection.execute(
            "SELECT COUNT(*) FROM audit_runs WHERE dataset_id = ?", (dataset_id,)
        ).fetchone()[0]
    assert count == 1


def test_concurrent_start_has_single_runner(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    workflow = _full_workflow(client)
    original = workflow_engine.HANDLERS["paper_parse"]
    entered = threading.Event()
    release = threading.Event()

    def slow_parse(context, config):
        entered.set()
        assert release.wait(10)
        return original(context, config)

    monkeypatch.setitem(workflow_engine.HANDLERS, "paper_parse", slow_parse)
    results = []
    first = threading.Thread(target=lambda: results.append(workflow_engine.start_workflow(workflow["id"])))
    first.start()
    assert entered.wait(10)
    second = threading.Thread(target=lambda: results.append(workflow_engine.start_workflow(workflow["id"])))
    second.start()
    second.join(10)
    assert not second.is_alive()
    release.set()
    first.join(10)
    assert not first.is_alive()
    assert len(results) == 2
    with connect() as connection:
        protocol_count = connection.execute(
            "SELECT COUNT(*) FROM protocols WHERE paper_id = ?", (workflow["config"]["paper_id"],)
        ).fetchone()[0]
        starts = connection.execute(
            "SELECT COUNT(*) FROM workflow_events WHERE workflow_id = ? AND event_type = 'workflow_started'",
            (workflow["id"],),
        ).fetchone()[0]
    assert protocol_count == 1
    assert starts == 1


def test_concurrent_retry_has_single_attempt(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    workflow = _full_workflow(client, dataset_id=_seed_clean_dataset(client))
    client.post(f"/api/workflows/{workflow['id']}/start")
    failed = client.post(
        f"/api/workflows/{workflow['id']}/approvals",
        json={"node_key": "protocol_approve", "decision": "approve"},
    ).json()
    assert _node(failed, "data_audit")["status"] == "failed"
    mapping = {
        "record_id": "record_id", "entity_id": "patient_id", "label": "label", "split": "split",
        "feature_columns": ["feature_age", "feature_biomarker", "feature_score", "constant_feature"],
        "split_mapping": {},
    }
    assert client.put(f"/api/datasets/{workflow['config']['dataset_id']}/mapping", json=mapping).status_code == 200

    original_advance = workflow_engine.advance
    entered = threading.Event()
    release = threading.Event()

    def paused_advance(workflow_id: str):
        entered.set()
        assert release.wait(10)
        return original_advance(workflow_id)

    monkeypatch.setattr(workflow_engine, "advance", paused_advance)
    results = []
    first = threading.Thread(
        target=lambda: results.append(workflow_engine.retry_node(workflow["id"], "data_audit"))
    )
    first.start()
    assert entered.wait(10)
    with pytest.raises(WorkflowStateError) as conflict:
        workflow_engine.retry_node(workflow["id"], "data_audit")
    assert conflict.value.code == "node_not_failed"
    release.set()
    first.join(10)
    assert not first.is_alive()
    assert len(results) == 1
    assert _node(results[0], "data_audit")["retry_count"] == 1
    with connect() as connection:
        audit_count = connection.execute(
            "SELECT COUNT(*) FROM audit_runs WHERE dataset_id = ?", (workflow["config"]["dataset_id"],)
        ).fetchone()[0]
        retry_events = connection.execute(
            "SELECT COUNT(*) FROM workflow_events WHERE workflow_id = ? AND event_type = 'node_retried'",
            (workflow["id"],),
        ).fetchone()[0]
    assert audit_count == 1
    assert retry_events == 1


def test_cancel_ignores_late_result_and_stops_downstream(
    client: TestClient, monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow = _full_workflow(client)
    original = workflow_engine.HANDLERS["paper_parse"]
    entered = threading.Event()
    release = threading.Event()

    def slow_parse(context, config):
        entered.set()
        assert release.wait(10)
        return original(context, config)

    monkeypatch.setitem(workflow_engine.HANDLERS, "paper_parse", slow_parse)
    result = []
    runner = threading.Thread(target=lambda: result.append(workflow_engine.start_workflow(workflow["id"])))
    runner.start()
    assert entered.wait(10)
    cancelled = workflow_engine.cancel_workflow(workflow["id"])
    assert cancelled["status"] == "cancelled"
    assert cancelled["cancel_requested"] is True
    release.set()
    runner.join(10)
    assert not runner.is_alive()
    assert result[0]["status"] == "cancelled"
    assert _node(result[0], "paper_parse")["status"] == "skipped"
    assert _node(result[0], "protocol_generate")["status"] == "skipped"
    with connect() as connection:
        protocols = connection.execute(
            "SELECT COUNT(*) FROM protocols WHERE paper_id = ?", (workflow["config"]["paper_id"],)
        ).fetchone()[0]
    assert protocols == 0
    events = client.get(f"/api/workflows/{workflow['id']}/events").json()
    assert any(event["event_type"] == "node_late_result_ignored" for event in events)
