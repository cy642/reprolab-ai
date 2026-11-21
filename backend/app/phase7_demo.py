"""Initialize and verify the isolated Phase 7 acceptance demonstration.

Run from the backend directory, for example:
    python -m app.phase7_demo --storage-dir C:\\Temp\\reprolab-phase7-check

The command only writes below the selected isolated storage directory. Reusing that
directory replays assertions without repeating uploads, imports, or approvals.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
FIXTURE_DIR = BACKEND_DIR / "data" / "demo" / "phase7"
DAILY_STORAGE_DIR = (BACKEND_DIR / "storage").resolve()
DEFAULT_STORAGE_DIR = Path(tempfile.gettempdir()).resolve() / "reprolab-phase7-demo"
FULL_WORKFLOW_KEY = "phase7-demo-full-reproduction-v1"
FAILED_WORKFLOW_KEY = "phase7-demo-analysis-only-missing-experiments-v1"


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_fixtures() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = FIXTURE_DIR / "manifest.sha256.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    _require(manifest.get("algorithm") == "sha256", "Phase7 清单必须使用 SHA256。")
    files = manifest.get("files")
    _require(isinstance(files, dict) and files, "Phase7 清单缺少 files。")
    for name, expected in files.items():
        path = FIXTURE_DIR / name
        _require(path.is_file(), f"Phase7 夹具缺失：{name}")
        _require(path.stat().st_size == expected["bytes"], f"Phase7 夹具字节数不匹配：{name}")
        _require(_sha256(path) == expected["sha256"], f"Phase7 夹具 SHA256 不匹配：{name}")
    expected = json.loads((FIXTURE_DIR / "expected.json").read_text(encoding="utf-8"))
    _require(
        expected.get("schema_version") == "phase7-demo-expected-v1",
        "人工预期文件版本不受支持。",
    )
    return manifest, expected


def _isolated_storage(raw_path: str | None) -> Path:
    storage = Path(raw_path).expanduser().resolve() if raw_path else DEFAULT_STORAGE_DIR.resolve()
    _require(
        storage != DAILY_STORAGE_DIR and DAILY_STORAGE_DIR not in storage.parents,
        f"禁止使用日常存储 {DAILY_STORAGE_DIR}；请选择独立目录。",
    )
    storage.mkdir(parents=True, exist_ok=True)
    return storage


def _call(client: Any, method: str, path: str, expected_status: int = 200, **kwargs: Any) -> dict[str, Any]:
    response = client.request(method, path, **kwargs)
    if response.status_code != expected_status:
        raise RuntimeError(
            f"{method} {path} 返回 {response.status_code}，预期 {expected_status}：{response.text}"
        )
    payload = response.json()
    _require(isinstance(payload, dict), f"{method} {path} 未返回 JSON 对象。")
    return payload


def _ensure_paper(client: Any, connection: Any) -> str:
    fixture = FIXTURE_DIR / "synthetic_acceptance_fixture.pdf"
    digest = _sha256(fixture)
    rows = connection.execute("SELECT * FROM papers WHERE sha256 = ?", (digest,)).fetchall()
    if rows:
        _require(len(rows) == 1, "同一 Phase7 PDF 对应多条论文记录，拒绝继续。")
        row = rows[0]
        stored = connection.execute(
            "SELECT stored_filename FROM papers WHERE id = ?", (row["id"],)
        ).fetchone()["stored_filename"]
        _require(
            (Path(os.environ["REPROLAB_STORAGE_DIR"]) / "uploads" / stored).is_file(),
            "Phase7 论文记录存在但隔离存储中的 PDF 文件缺失。",
        )
        return row["id"]
    detail = _call(
        client,
        "POST",
        "/api/papers/upload",
        expected_status=201,
        files={"file": (fixture.name, fixture.read_bytes(), "application/pdf")},
    )
    return detail["id"]


def _ensure_dataset(client: Any, connection: Any, mapping: dict[str, Any]) -> str:
    fixture = FIXTURE_DIR / "patient_overlap.csv"
    digest = _sha256(fixture)
    rows = connection.execute("SELECT * FROM datasets WHERE sha256 = ? ORDER BY rowid", (digest,)).fetchall()
    if rows:
        _require(len(rows) == 1, "同一 Phase7 CSV 对应多条数据集记录，拒绝继续。")
        dataset_id = rows[0]["id"]
        _require(
            (Path(os.environ["REPROLAB_STORAGE_DIR"]) / "datasets" / rows[0]["stored_filename"]).is_file(),
            "Phase7 数据集记录存在但隔离存储中的 CSV 文件缺失。",
        )
        stored_mapping = connection.execute(
            "SELECT * FROM dataset_mappings WHERE dataset_id = ?", (dataset_id,)
        ).fetchone()
        if stored_mapping is not None:
            actual = {
                "record_id": stored_mapping["record_id"],
                "entity_id": stored_mapping["entity_id"],
                "label": stored_mapping["label"],
                "split": stored_mapping["split"],
                "feature_columns": json.loads(stored_mapping["feature_columns"] or "[]"),
                "split_mapping": json.loads(stored_mapping["split_mapping"] or "{}"),
            }
            _require(actual == mapping and bool(stored_mapping["confirmed"]), "Phase7 数据集映射与人工预期不一致。")
            return dataset_id
    else:
        detail = _call(
            client,
            "POST",
            "/api/datasets/upload",
            expected_status=201,
            files={"file": (fixture.name, fixture.read_bytes(), "text/csv")},
        )
        dataset_id = detail["id"]
    saved = _call(client, "PUT", f"/api/datasets/{dataset_id}/mapping", json=mapping)
    _require(saved["mapping"]["confirmed"], "Phase7 数据集映射未被确认。")
    return dataset_id


def _ensure_experiments(
    client: Any, connection: Any, dataset_id: str, expected: dict[str, Any]
) -> dict[str, str]:
    fixture_payload = json.loads((FIXTURE_DIR / "simulated_experiments.json").read_text(encoding="utf-8"))
    raw_records = fixture_payload["records"]
    external_ids = expected["experiments"]["external_experiment_ids"]
    _require(
        [record["experiment_id"] for record in raw_records] == external_ids,
        "模拟实验文件的外部 experiment_id 与人工预期不一致。",
    )
    rows = connection.execute(
        "SELECT * FROM experiment_records WHERE source_format = 'phase7_demo' ORDER BY rowid"
    ).fetchall()
    if not rows:
        imported = _call(
            client,
            "POST",
            "/api/experiments/import",
            json={
                "records": raw_records,
                "source_format": "phase7_demo",
                "metrics_scale": "fraction",
                "dataset_ref_id": dataset_id,
                "is_simulated": True,
                "data_source": "simulated",
            },
        )
        _require(imported["count"] == len(raw_records), "Phase7 模拟实验导入数量不正确。")
        rows = connection.execute(
            "SELECT * FROM experiment_records WHERE source_format = 'phase7_demo' ORDER BY rowid"
        ).fetchall()
    _require(len(rows) == len(external_ids), "Phase7 实验记录数量与人工预期不一致。")
    by_external_id = {row["experiment_id"]: row for row in rows}
    _require(set(by_external_id) == set(external_ids), "Phase7 实验外部标识与人工预期不一致。")
    for row in rows:
        _require(
            row["dataset_ref_id"] == dataset_id
            and bool(row["is_simulated"])
            and row["data_source"] == "simulated",
            f"Phase7 实验来源或数据集关联不正确：{row['experiment_id']}",
        )
    return {external_id: by_external_id[external_id]["id"] for external_id in external_ids}


def _workflow_by_key(connection: Any, key: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT id FROM research_workflows WHERE idempotency_key = ?", (key,)
    ).fetchone()
    return {"id": row["id"]} if row else None


def _validate_config(workflow: dict[str, Any], expected: dict[str, Any]) -> None:
    config = workflow["config"]
    for key, value in expected.items():
        actual = workflow["workflow_type"] if key == "workflow_type" else config.get(key)
        _require(actual == value, f"工作流 {workflow['id']} 的 {key} 已变化。")


def _node(workflow: dict[str, Any], key: str) -> dict[str, Any]:
    return next(item for item in workflow["nodes"] if item["node_key"] == key)


def _approve(client: Any, workflow: dict[str, Any], node_key: str, comment: str) -> dict[str, Any]:
    _require(workflow["status"] == "waiting_approval", f"审批 {node_key} 前工作流不在等待审批。")
    _require(_node(workflow, node_key)["status"] == "waiting_approval", f"节点 {node_key} 不在等待审批。")
    return _call(
        client,
        "POST",
        f"/api/workflows/{workflow['id']}/approvals",
        json={
            "node_key": node_key,
            "decision": "approve",
            "comment": comment,
            "reviewer": "phase7-demo-reviewer",
        },
    )


def _run_scenario_a(
    client: Any, connection: Any, paper_id: str, dataset_id: str,
    experiment_ids: dict[str, str], expected: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    internal_ids = list(experiment_ids.values())
    expected_config = {
        "workflow_type": "full_reproduction",
        "paper_id": paper_id,
        "dataset_id": dataset_id,
        "experiment_ids": internal_ids,
        "baseline_method": expected["experiments"]["baseline_method"],
        "primary_metric": "macro_f1",
        "use_llm": False,
    }
    existing = _workflow_by_key(connection, FULL_WORKFLOW_KEY)
    if existing:
        workflow = _call(client, "GET", f"/api/workflows/{existing['id']}")
    else:
        workflow = _call(
            client,
            "POST",
            "/api/workflows",
            expected_status=201,
            json={
                "name": "Phase7 A · 合成数据完整复现（保留泄漏风险）",
                "idempotency_key": FULL_WORKFLOW_KEY,
                "protocol_name": "Phase7 Synthetic Acceptance Protocol",
                "mapping": expected["mapping"],
                "auto_start": False,
                **expected_config,
            },
        )
        _validate_config(workflow, expected_config)
        workflow = _call(client, "POST", f"/api/workflows/{workflow['id']}/start")
        workflow = _approve(client, workflow, "protocol_approve", "确认这是合成验收方案，不代表真实研究设计。")
        workflow = _approve(
            client,
            workflow,
            "audit_approve",
            "已知悉 P002 的 Train/Test 患者重叠及 critical 风险；仅批准继续演示，不代表风险已修复。",
        )
        workflow = _approve(client, workflow, "report_publish", "确认本地定稿；报告必须保留未解决风险和模拟来源声明。")
        workflow = _call(client, "GET", f"/api/workflows/{workflow['id']}")
    _validate_config(workflow, expected_config)

    scenario = expected["scenario_a"]
    _require(workflow["status"] == scenario["status"], "场景 A 未完整完成。")
    _require(workflow["progress"]["completed"] == scenario["completed_node_count"], "场景 A 完成节点数不正确。")
    node_ids = {node["id"]: node["node_key"] for node in workflow["nodes"]}
    approved_nodes = [node_ids[item["node_id"]] for item in workflow["approvals"] if item["decision"] == "approve"]
    _require(approved_nodes == scenario["approval_node_keys"], "场景 A 审批节点或顺序不正确。")

    context = workflow["context"]
    for key in ("protocol_id", "audit_id", "comparison_id", "insight_id"):
        _require(bool(context.get(key)), f"场景 A 缺少 {key}。")
    audit = _call(client, "GET", f"/api/audits/{context['audit_id']}")
    high_risk = [item for item in audit["findings"] if item["severity"] in {"critical", "high"}]
    expected_rules = expected["dataset"]["required_critical_rules"]
    _require(len(high_risk) == expected["dataset"]["unresolved_high_risk_count"], "患者重叠高风险数量与人工预期不一致。")
    _require(
        {item["rule_id"]: item["severity"] for item in high_risk} == expected_rules,
        "患者重叠规则或严重度与人工预期不一致。",
    )
    overlap = expected["dataset"]["patient_overlap"][0]
    leakage = next(item for item in high_risk if item["rule_id"] == "leakage_entity_cross_split")
    _require(leakage["evidence"]["overlap_group_count"] == 1, "患者跨集合重叠组数应为 1。")
    groups = leakage["evidence"]["groups"]
    _require(len(groups) == 1, "患者跨集合证据应只有一个组。")
    _require(groups[0]["group_value"] == overlap["patient_id"], "跨集合患者不是人工预期的 P002。")
    _require(groups[0]["row_numbers"] == overlap["csv_row_numbers"], "患者重叠 CSV 行号与人工预期不一致。")
    expected_record_ids = overlap["train_record_ids"] + overlap["test_record_ids"]
    _require(set(groups[0]["record_ids"]) == set(expected_record_ids), "患者重叠 record_id 与人工预期不一致。")
    split_overlap = next(item for item in high_risk if item["rule_id"] == "split_entity_overlap")
    _require(split_overlap["evidence"]["overlap_entity_count"] == 1, "split_entity_overlap 的实体数应为 1。")

    comparison = _call(client, "GET", f"/api/experiments/comparisons/{context['comparison_id']}")
    result = comparison["result"]
    rows_by_method = {item["method"]: item for item in result["metric_comparison"]}
    experiment_expectation = expected["experiments"]
    baseline_name = experiment_expectation["baseline_method"]
    candidate_name = experiment_expectation["candidate_method"]
    _require(result["baseline"] == baseline_name, "场景 A baseline 方法不正确。")
    _require(
        math.isclose(rows_by_method[baseline_name]["macro_f1"]["mean"], experiment_expectation["baseline_macro_f1_mean"]),
        "Baseline Macro-F1 均值不符合人工算术预期。",
    )
    _require(
        math.isclose(rows_by_method[candidate_name]["macro_f1"]["mean"], experiment_expectation["candidate_macro_f1_mean"]),
        "Candidate Macro-F1 均值不符合人工算术预期。",
    )
    _require(
        math.isclose(
            rows_by_method[candidate_name]["macro_f1"]["delta_vs_baseline_pp"],
            experiment_expectation["candidate_delta_vs_baseline_pp"],
        ),
        "Candidate 相对 Baseline 的 Macro-F1 百分点差不符合人工算术预期。",
    )
    report = _call(client, "GET", f"/api/workflows/{workflow['id']}/report")
    risk = report["risk_summary"]
    _require(risk["unresolved_high_risk_count"] == expected["dataset"]["unresolved_high_risk_count"], "定稿报告丢失了未解决高风险数量。")
    _require(risk["risk_acknowledged"] is scenario["risk_acknowledged"], "定稿报告未记录已知悉风险。")
    _require(risk["audit_passed"] is scenario["audit_passed"], "患者重叠存在时报告不得宣称审计通过。")
    _require(report["data_validation_skipped"] is scenario["data_validation_skipped"], "场景 A 不应跳过数据审计。")
    _require(report["is_simulated"] is scenario["is_simulated"], "场景 A 必须保留模拟数据标识。")
    _require(report["data_source"] == scenario["data_source"], "场景 A 数据来源必须为 simulated。")
    _require(workflow["report_finalized"] and report["snapshot_version"], "场景 A 报告未固定输入快照。")
    return workflow, audit, comparison, report


def _run_scenario_b(client: Any, connection: Any, expected: dict[str, Any]) -> dict[str, Any]:
    expected_config = {
        "workflow_type": "analysis_only",
        "paper_id": None,
        "dataset_id": None,
        "experiment_ids": [],
        "comparison_id": None,
    }
    existing = _workflow_by_key(connection, FAILED_WORKFLOW_KEY)
    if existing:
        workflow = _call(client, "GET", f"/api/workflows/{existing['id']}")
    else:
        workflow = _call(
            client,
            "POST",
            "/api/workflows",
            expected_status=201,
            json={
                "name": "Phase7 B · 缺少实验记录的真实失败",
                "idempotency_key": FAILED_WORKFLOW_KEY,
                "auto_start": False,
                **expected_config,
            },
        )
        _validate_config(workflow, expected_config)
        workflow = _call(client, "POST", f"/api/workflows/{workflow['id']}/start")
        workflow = _call(client, "GET", f"/api/workflows/{workflow['id']}")
    _validate_config(workflow, expected_config)
    scenario = expected["scenario_b"]
    _require(workflow["status"] == scenario["status"], "场景 B 必须进入真实 failed 状态。")
    failed = _node(workflow, scenario["failed_node_key"])
    _require(failed["status"] == "failed", "场景 B 的 experiment_analyze 节点必须失败。")
    _require(failed["error"] == scenario["expected_error"], "场景 B 未明确指出缺少 experiment_ids 或 comparison_id。")
    _require(workflow["error"] == scenario["expected_error"], "场景 B 工作流错误摘要未保留缺失实验原因。")
    for key in scenario["skipped_node_keys"]:
        _require(_node(workflow, key)["status"] == "skipped", f"场景 B 的 {key} 应因缺少输入而跳过。")
    _require(not workflow["context"].get("insight_id"), "场景 B 不得伪造 Insight。")
    _require(_node(workflow, "report_publish")["status"] == "pending", "场景 B 失败后不得定稿报告。")
    return workflow


def _table_counts(connection: Any) -> dict[str, int]:
    names = [
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
    ]
    return {name: connection.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0] for name in names}


def initialize(storage: Path) -> dict[str, Any]:
    manifest, expected = _verify_fixtures()
    previous_path = storage / "phase7_demo_summary.json"
    previous = json.loads(previous_path.read_text(encoding="utf-8")) if previous_path.is_file() else None

    from fastapi.testclient import TestClient

    from .db import connect
    from .main import app

    with TestClient(app) as client:
        with connect() as connection:
            paper_id = _ensure_paper(client, connection)
        with connect() as connection:
            dataset_id = _ensure_dataset(client, connection, expected["mapping"])
        with connect() as connection:
            experiment_ids = _ensure_experiments(client, connection, dataset_id, expected)
        with connect() as connection:
            workflow_a, audit, comparison, report = _run_scenario_a(
                client, connection, paper_id, dataset_id, experiment_ids, expected
            )
        with connect() as connection:
            workflow_b = _run_scenario_b(client, connection, expected)
            insight_count = connection.execute("SELECT COUNT(*) FROM insight_reports").fetchone()[0]
            _require(insight_count == 1, "场景 B 失败后不得新增 Insight；隔离库应仅有场景 A 的一条。")
            counts = _table_counts(connection)

    resources = {
        "paper_id": paper_id,
        "dataset_id": dataset_id,
        "experiment_record_ids": experiment_ids,
        "scenario_a": {
            "workflow_id": workflow_a["id"],
            "protocol_id": workflow_a["context"]["protocol_id"],
            "audit_id": workflow_a["context"]["audit_id"],
            "comparison_id": workflow_a["context"]["comparison_id"],
            "insight_id": workflow_a["context"]["insight_id"],
        },
        "scenario_b": {"workflow_id": workflow_b["id"]},
    }
    replay_verified = None
    if previous is not None:
        _require(previous.get("resources") == resources, "重复运行后资源 ID 发生变化。")
        _require(previous.get("table_counts") == counts, "重复运行后数据库表计数发生变化。")
        replay_verified = True

    failed_node = _node(workflow_b, "experiment_analyze")
    summary = {
        "schema_version": "phase7-demo-summary-v1",
        "storage_dir": str(storage),
        "fixture_dir": str(FIXTURE_DIR),
        "fixture_manifest_sha256": _sha256(FIXTURE_DIR / "manifest.sha256.json"),
        "fixture_files_verified": sorted(manifest["files"]),
        "resources": resources,
        "scenario_a": {
            "status": workflow_a["status"],
            "audit_status": audit["status"],
            "audit_finding_count": audit["finding_count"],
            "comparison_status": comparison["status"],
            "risk_summary": report["risk_summary"],
            "data_source": report["data_source"],
            "is_simulated": report["is_simulated"],
            "snapshot_version": report["snapshot_version"],
            "finalization_scope": report["finalization_scope"],
        },
        "scenario_b": {
            "status": workflow_b["status"],
            "failed_node": "experiment_analyze",
            "error": failed_node["error"],
            "insight_created": False,
            "report_publish_status": _node(workflow_b, "report_publish")["status"],
        },
        "assertions": {
            "manifest_verified": True,
            "manual_patient_overlap_verified": True,
            "manual_metric_arithmetic_verified": True,
            "scenario_a_completed_with_risk_retained": True,
            "scenario_b_failed_without_fake_insight": True,
        },
        "table_counts": counts,
        "idempotency": {
            "previous_summary_found": previous is not None,
            "resource_ids_and_table_counts_unchanged": replay_verified,
            "repeat_upload_import_approval_skipped": previous is not None,
        },
    }
    previous_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化并验证 Phase7 隔离演示（幂等）。")
    parser.add_argument(
        "--storage-dir",
        help=f"独立存储目录；默认 {DEFAULT_STORAGE_DIR}。禁止 backend/storage。",
    )
    args = parser.parse_args()
    storage = _isolated_storage(args.storage_dir)
    os.environ["REPROLAB_STORAGE_DIR"] = str(storage)
    for key in ("LLM_BASE_URL", "OPENAI_BASE_URL", "LLM_API_KEY", "OPENAI_API_KEY", "LLM_MODEL", "OPENAI_MODEL"):
        os.environ[key] = ""
    summary = initialize(storage)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
