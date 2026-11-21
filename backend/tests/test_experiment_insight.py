"""Phase 5 Experiment Insight: import, comparison, stability, ablation, insight, export.

All assertions are grounded in deterministic Python computation; tests never
accept fabricated metrics or static demo numbers.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app

FIXTURES = Path(__file__).resolve().parent / "fixtures"
SIMULATED_SIX = FIXTURES / "simulated_six_class.csv"

VALID_CSV = """experiment_id,method,model_name,dataset,seed,accuracy,precision,recall,f1,macro_f1,weighted_f1,runtime
A_s1,MethodA,NetX,DS1,1,0.830,0.820,0.810,0.815,0.780,0.825,120
A_s2,MethodA,NetX,DS1,2,0.835,0.825,0.815,0.820,0.785,0.830,121
B_s1,MethodB,NetX,DS1,1,0.850,0.840,0.835,0.838,0.810,0.845,130
B_s2,MethodB,NetX,DS1,2,0.852,0.842,0.837,0.840,0.813,0.847,131
"""

PERCENT_CSV = """experiment_id,method,dataset,seed,accuracy,macro_f1
P_s1,MethodP,DS1,1,83.0,78.0
P_s2,MethodP,DS1,2,83.5,78.5
P_s3,MethodQ,DS1,1,85.0,81.0
P_s4,MethodQ,DS1,2,85.2,81.3
"""

INVALID_RANGE_CSV = """experiment_id,method,dataset,seed,accuracy,macro_f1
X_s1,MethodX,DS1,1,150.0,80.0
"""

DUPLICATE_CSV = """experiment_id,method,dataset,seed,accuracy,macro_f1
D_s1,MethodD,DS1,1,0.80,0.70
D_s1,MethodD,DS1,1,0.80,0.70
"""

VALID_JSON = [
    {
        "experiment_id": "C_s1", "method": "MethodC", "model_name": "NetY", "dataset": "DS2",
        "seed": 1, "accuracy": 0.86, "precision": 0.85, "recall": 0.84, "f1": 0.845,
        "macro_f1": 0.81, "weighted_f1": 0.855, "runtime": 110,
        "training_config": {"optimizer": "adam", "lr": 0.001, "loss": "CE", "federated": False},
        "confusion_matrix": [[5, 1, 0], [1, 6, 1], [0, 1, 7]],
        "per_class_metrics": {
            "A": {"precision": 0.83, "recall": 0.83, "f1": 0.83},
            "B": {"precision": 0.75, "recall": 0.75, "f1": 0.75},
            "C": {"precision": 0.88, "recall": 0.88, "f1": 0.88},
        },
    },
    {
        "experiment_id": "C_s2", "method": "MethodC", "model_name": "NetY", "dataset": "DS2",
        "seed": 2, "accuracy": 0.87, "precision": 0.86, "recall": 0.85, "f1": 0.855,
        "macro_f1": 0.82, "weighted_f1": 0.865, "runtime": 111,
        "training_config": {"optimizer": "adam", "lr": 0.001, "loss": "CE", "federated": False},
        "confusion_matrix": [[6, 0, 0], [0, 7, 1], [0, 1, 7]],
        "per_class_metrics": {
            "A": {"precision": 0.86, "recall": 0.86, "f1": 0.86},
            "B": {"precision": 0.78, "recall": 0.78, "f1": 0.78},
            "C": {"precision": 0.90, "recall": 0.90, "f1": 0.90},
        },
    },
    {
        "experiment_id": "D_s1", "method": "MethodD", "model_name": "NetY", "dataset": "DS2",
        "seed": 1, "accuracy": 0.89, "precision": 0.88, "recall": 0.87, "f1": 0.875,
        "macro_f1": 0.84, "weighted_f1": 0.885, "runtime": 125,
        "training_config": {"optimizer": "adam", "lr": 0.001, "loss": "BSM", "federated": True, "use_bsm": True},
        "confusion_matrix": [[7, 0, 0], [0, 8, 0], [0, 0, 8]],
        "per_class_metrics": {
            "A": {"precision": 0.88, "recall": 0.88, "f1": 0.88},
            "B": {"precision": 0.82, "recall": 0.82, "f1": 0.82},
            "C": {"precision": 0.92, "recall": 0.92, "f1": 0.92},
        },
    },
]


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REPROLAB_STORAGE_DIR", str(tmp_path / "storage"))
    for name in ("LLM_BASE_URL", "LLM_API_KEY", "LLM_MODEL", "OPENAI_BASE_URL", "OPENAI_API_KEY", "OPENAI_MODEL"):
        monkeypatch.delenv(name, raising=False)
    with TestClient(app) as test_client:
        yield test_client


def _preview_csv(client: TestClient, content: str, filename: str = "exp.csv") -> dict:
    response = client.post("/api/experiments/import/preview", files={"file": (filename, content.encode("utf-8"), "text/csv")})
    assert response.status_code == 200, response.text
    return response.json()


def _import_records(client: TestClient, records: list[dict], **kwargs) -> list[str]:
    payload = {"records": records, "source_format": "json", **kwargs}
    response = client.post("/api/experiments/import", json=payload)
    assert response.status_code == 200, response.text
    return response.json()["ids"]


def _analyze(client: TestClient, ids: list[str], **kwargs) -> dict:
    response = client.post("/api/experiments/analyze", json={"experiment_ids": ids, "use_llm": False, **kwargs})
    assert response.status_code == 200, response.text
    return response.json()


def _seed_audit(client: TestClient) -> tuple[str, str]:
    """Reuse the Phase 4 deterministic audit pipeline to produce a real leakage finding."""
    uploaded = client.post("/api/datasets/upload", files={"file": ("six.csv", SIMULATED_SIX.read_bytes(), "text/csv")})
    assert uploaded.status_code == 201, uploaded.text
    dataset_id = uploaded.json()["id"]
    mapping = {
        "record_id": "record_id", "entity_id": "patient_id", "label": "label", "split": "split",
        "feature_columns": ["feature_age", "feature_biomarker", "feature_score", "constant_feature"],
        "split_mapping": {},
    }
    assert client.put(f"/api/datasets/{dataset_id}/mapping", json=mapping).status_code == 200
    audited = client.post(f"/api/datasets/{dataset_id}/audit")
    assert audited.status_code == 201, audited.text
    return dataset_id, audited.json()["id"]


def _seed_protocol(client: TestClient) -> str:
    from app.db import connect

    now = "2026-01-01T00:00:00Z"
    with connect() as connection:
        connection.execute(
            "INSERT INTO papers (id, original_filename, stored_filename, sha256, file_size, page_count, title, status, parse_status, ai_status, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            ("paper_test", "p.pdf", "p.pdf", "sha-test", 1, 1, "Test Paper", "processed", "done", "not_used", now, now),
        )
        connection.execute(
            "INSERT INTO protocols (id, paper_id, name, goal, status, agent_method, ai_status, created_at, updated_at, open_questions, source_fields)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            ("proto_test", "paper_test", "ECG 复现协议", "复现 ECG 六分类 SOTA", "draft", "extraction", "not_used", now, now, "[]", "[]"),
        )
        connection.execute(
            "INSERT INTO protocol_steps (id, protocol_id, step_id, title, order_no, status, information_type, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            ("step_1", "proto_test", "train", "训练模型", 1, "pending", "method", now, now),
        )
        connection.execute(
            "INSERT INTO protocol_parameters (id, protocol_id, name, value, param_type, source_type, order_no, created_at, updated_at)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            ("param_1", "proto_test", "lr", "0.001", "float", "paper", 1, now, now),
        )
        connection.commit()
    return "proto_test"


# 1. CSV 导入 + 预览校验 + 持久化 + 详情恢复
def test_csv_import_preview_persist_and_detail(client: TestClient) -> None:
    preview = _preview_csv(client, VALID_CSV)
    assert preview["ok"] is True
    assert preview["row_count"] == 4
    assert preview["source_format"] == "csv"
    assert preview["deterministic"] is True
    assert all(row["method"] in {"MethodA", "MethodB"} for row in preview["preview"])

    ids = _import_records(client, preview["records"])
    assert len(ids) == 4

    listed = client.get("/api/experiments").json()
    assert listed["total"] == 4
    assert listed["deterministic_engine"] is True
    assert listed["ai_configured"] is False
    detail = client.get(f"/api/experiments/{ids[0]}").json()
    assert detail["experiment_id"].startswith(("A_", "B_"))
    assert detail["metrics_scale"] == "fraction"
    assert detail["source_format"] == "json"


# 2. JSON 导入含混淆矩阵与每类指标
def test_json_import_with_confusion_and_per_class(client: TestClient) -> None:
    ids = _import_records(client, VALID_JSON)
    assert len(ids) == 3
    comparison = client.post("/api/experiments/compare", json={"experiment_ids": ids}).json()
    result = comparison["result"]
    assert result["per_class"]["classes"] == ["A", "B", "C"]
    assert "MethodD" in result["confusion"]["matrices"]
    assert len(result["confusion"]["matrices"]["MethodD"]) == 3
    assert result["per_class"]["by_method"]["MethodC"]["A"]["f1"] is not None


# 3. 非法指标范围被拒绝
def test_invalid_metric_range_rejected(client: TestClient) -> None:
    # accuracy=150 被自动识别为百分数 → 1.5，越界 [0,1]
    response = client.post("/api/experiments/import", json={"records": [
        {"experiment_id": "X", "method": "MethodX", "dataset": "DS1", "seed": 1, "accuracy": 150.0, "macro_f1": 80.0}
    ], "source_format": "json"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "validation_failed"
    assert any(err["code"] == "out_of_range" for err in response.json()["detail"]["errors"])
    preview = _preview_csv(client, INVALID_RANGE_CSV)
    assert preview["ok"] is False
    assert any(err["code"] == "out_of_range" for err in preview["errors"])


# 4. 重复记录检测（预览阶段剔除重复行，仅保留唯一记录）
def test_duplicate_record_detected(client: TestClient) -> None:
    preview = _preview_csv(client, DUPLICATE_CSV)
    assert preview["ok"] is False
    assert any(err["code"] == "duplicate_record" for err in preview["errors"])
    # 重复行已在归一化时剔除，仅幸存 1 条唯一记录可被导入
    assert preview["row_count"] == 1
    confirm = client.post("/api/experiments/import", json={"records": preview["records"], "source_format": "csv"})
    assert confirm.status_code == 200
    assert confirm.json()["count"] == 1


# 5. Macro-F1 计算与对比 + 排名 + delta 百分点
def test_macro_f1_comparison_and_ranking(client: TestClient) -> None:
    ids = _import_records(client, VALID_JSON)
    result = client.post("/api/experiments/compare", json={"experiment_ids": ids, "baseline_method": "MethodD"}).json()["result"]
    rows = {row["method"]: row for row in result["metric_comparison"]}
    # MethodC mean macro_f1 = (0.81+0.82)/2 = 0.815
    assert rows["MethodC"]["macro_f1"]["mean"] == pytest.approx(0.815, rel=1e-3)
    # MethodD 作为指定 baseline，MethodC delta = (0.815 - 0.84)*100 = -2.5 pp
    assert rows["MethodC"]["macro_f1"]["delta_vs_baseline_pp"] == pytest.approx(-2.5, abs=0.05)
    top = result["rankings"][0]
    assert top["method"] == "MethodD"
    assert top["value"] == pytest.approx(0.84, rel=1e-3)


# 6. Accuracy 计算与对比
def test_accuracy_comparison(client: TestClient) -> None:
    ids = _import_records(client, VALID_JSON)
    result = client.post("/api/experiments/compare", json={"experiment_ids": ids, "baseline_method": "MethodD"}).json()["result"]
    rows = {row["method"]: row for row in result["metric_comparison"]}
    assert rows["MethodC"]["accuracy"]["mean"] == pytest.approx(0.865, rel=1e-3)
    assert rows["MethodD"]["accuracy"]["mean"] == pytest.approx(0.89, rel=1e-3)
    assert rows["MethodC"]["accuracy"]["delta_vs_baseline_pp"] == pytest.approx(-2.5, abs=0.05)


# 7. 百分数自动转换（>1 → ÷100，记录口径）
def test_percent_auto_conversion(client: TestClient) -> None:
    preview = _preview_csv(client, PERCENT_CSV)
    assert preview["ok"] is True
    record = next(r for r in preview["records"] if r["experiment_id"] == "P_s1")
    assert record["accuracy"] == pytest.approx(0.830, rel=1e-6)
    assert record["macro_f1"] == pytest.approx(0.780, rel=1e-6)
    assert record["metrics_scale"] == "converted_from_percent"
    assert 0.0 <= record["accuracy"] <= 1.0


# 8. 显式 metrics_scale：percent 与 fraction 互不混淆
def test_explicit_percent_and_fraction_scale(client: TestClient) -> None:
    ids = _import_records(
        client,
        [{"experiment_id": "E1", "method": "MethodE", "dataset": "DS1", "seed": 1, "accuracy": 83.0, "macro_f1": 78.0}],
        metrics_scale="percent",
    )
    stored = client.get(f"/api/experiments/{ids[0]}").json()
    assert stored["accuracy"] == pytest.approx(0.83, rel=1e-6)
    assert stored["metrics_scale"] == "percent"

    bad = client.post("/api/experiments/import", json={
        "records": [{"experiment_id": "E2", "method": "MethodE", "dataset": "DS1", "seed": 2, "accuracy": 1.5, "macro_f1": 0.8}],
        "source_format": "json", "metrics_scale": "fraction",
    })
    assert bad.status_code == 422
    assert any(err["code"] == "out_of_range" for err in bad.json()["detail"]["errors"])


# 9. 多随机种子均值与标准差
def test_multi_seed_mean_and_std(client: TestClient) -> None:
    records = [
        {"experiment_id": f"S_{i}", "method": "MethodS", "dataset": "DS1", "seed": i, "macro_f1": value, "accuracy": value}
        for i, value in enumerate([0.80, 0.82, 0.84], start=1)
    ]
    ids = _import_records(client, records)
    insight = _analyze(client, ids)
    group = insight["content"]["stability_analysis"]["groups"][0]
    stats = group["metrics"]["macro_f1"]
    assert stats["count"] == 3
    assert stats["mean"] == pytest.approx(0.82, rel=1e-6)
    assert stats["std"] == pytest.approx(0.02, rel=1e-6)
    assert stats["min"] == pytest.approx(0.80, rel=1e-6)
    assert stats["max"] == pytest.approx(0.84, rel=1e-6)
    assert group["can_assess_stability"] is True


# 10. 单随机种子限制提示（不夸大稳定性）
def test_single_seed_stability_limitation(client: TestClient) -> None:
    ids = _import_records(client, [
        {"experiment_id": "single", "method": "MethodSolo", "dataset": "DS1", "seed": 1, "macro_f1": 0.80, "accuracy": 0.83}
    ])
    insight = _analyze(client, ids)
    group = insight["content"]["stability_analysis"]["groups"][0]
    assert group["can_assess_stability"] is False
    assert group["seed_count"] == 1
    assert "无法评估" in group["note"]
    # 没有该方法的统计发现结论（避免把单次结果写成稳定结论）
    assert not any(
        c["claim_type"] == "statistical_finding" and "MethodSolo" in c["claim"]
        for c in insight["content"]["key_observations"]
    )


# 11. 置信区间计算（方法说明、适用条件、充分样本标记）
def test_confidence_interval_calculation(client: TestClient) -> None:
    from app.services.stats_helpers import confidence_interval

    ci = confidence_interval([0.80, 0.82, 0.84])
    assert ci is not None
    assert ci["count"] == 3
    assert ci["mean"] == pytest.approx(0.82, rel=1e-6)
    assert ci["lower"] < ci["mean"] < ci["upper"]
    assert ci["margin_of_error"] > 0
    assert ci["t_critical"] > 1.0
    assert ci["confidence"] == 0.95
    assert ci["sufficient_sample"] is False  # n<30
    assert "t-interval" in ci["method"]
    assert "不得据此声称统计显著" in ci["note"]

    # n<2 不返回区间
    assert confidence_interval([0.80]) is None
    two_seeds = confidence_interval([0.61, 0.63])
    assert two_seeds["t_critical"] == pytest.approx(12.7062, abs=0.0001)
    assert two_seeds["lower"] == pytest.approx(0.492938, abs=0.000001)
    assert two_seeds["upper"] == pytest.approx(0.747062, abs=0.000001)
    assert two_seeds["sufficient_sample"] is False


# 12. 消融实验分析（无组件开关不推断因果，标注相关性≠因果）
def test_ablation_analysis_no_causal_claim(client: TestClient) -> None:
    ids = _import_records(client, VALID_JSON)
    insight = _analyze(client, ids)
    ablation = insight["content"]["ablation_analysis"]
    assert ablation["has_component_flags"] is True  # use_bsm / federated 命中组件开关 token
    assert ablation["comparisons"]
    non_baseline = ablation["comparisons"][0]
    assert "macro_f1" in non_baseline["deltas"]
    limitations = insight["content"]["limitations"]
    assert any("不推断" in text or "独立贡献" in text for text in limitations)
    assert any("相关性不等于因果" in text for text in limitations)
    # 假设类结论必须标记为 hypothesis，不得伪装为事实
    hypothesis_claims = [c for c in insight["content"]["key_observations"] if c["claim_type"] == "hypothesis"]
    for claim in hypothesis_claims:
        assert "假设" in claim["claim"]


# 13. Data Guardian 审计结果联动（带 audit_id 与 finding_id）
def test_data_guardian_audit_linkage(client: TestClient) -> None:
    dataset_id, audit_id = _seed_audit(client)
    ids = _import_records(
        client,
        [{"experiment_id": "L1", "method": "MethodL", "dataset": "DS1", "seed": 1, "macro_f1": 0.80, "accuracy": 0.83}],
        dataset_ref_id=dataset_id,
    )
    insight = _analyze(client, ids, dataset_ref_id=dataset_id)
    warnings = insight["content"]["data_quality_warnings"]
    assert warnings, "预期联动到 Data Guardian 的高风险审计发现"
    assert insight["audit_id"] == audit_id
    for finding in warnings:
        assert finding["audit_id"] == audit_id
        assert finding["finding_id"]
        assert finding["rule_id"]
        assert finding["severity"] in {"critical", "high", "medium", "low", "info"}
    leakage = [w for w in warnings if "leakage" in w["rule_id"] or "cross_split" in w["rule_id"]]
    assert leakage, "预期存在患者级泄漏或跨集合重复相关发现"
    # 即使指标高，数据质量风险仍出现在结论中
    claim_texts = " ".join(c["claim"] for c in insight["content"]["key_observations"])
    assert "数据质量" in claim_texts


# 14. Protocol 方案联动（未完成步骤 / 参数偏离 / 缺失指标阈值，只读不改）
def test_protocol_linkage_readonly(client: TestClient) -> None:
    protocol_id = _seed_protocol(client)
    ids = _import_records(
        client,
        [{"experiment_id": "PR1", "method": "MethodPR", "dataset": "DS1", "seed": 1, "macro_f1": 0.80, "accuracy": 0.83,
          "training_config": {"lr": 0.01}}],
        protocol_id=protocol_id,
    )
    insight = _analyze(client, ids, protocol_id=protocol_id)
    alignment = insight["content"]["protocol_alignment"]
    assert alignment is not None
    assert alignment["protocol_id"] == protocol_id
    messages = " ".join(check["message"] for check in alignment["checks"])
    assert "未标记完成" in messages  # pending 步骤
    assert "lr" in messages and "偏离" in messages  # 协议 0.001 vs 实验 0.01
    assert "未明确量化评价指标阈值" in messages
    # 只读：协议原始值未被修改
    from app.db import connect
    with connect() as connection:
        row = connection.execute("SELECT value FROM protocol_parameters WHERE protocol_id = ? AND name = 'lr'", (protocol_id,)).fetchone()
        assert row["value"] == "0.001"


# 15. Insight Agent 结构化输出（每条结论含五要素，claim_type 合法）
def test_insight_structured_output(client: TestClient) -> None:
    ids = _import_records(client, VALID_JSON)
    insight = _analyze(client, ids)
    content = insight["content"]
    for field in ("experimental_summary", "key_observations", "metric_comparisons",
                  "stability_analysis", "ablation_analysis", "data_quality_warnings",
                  "protocol_alignment", "limitations", "recommendations"):
        assert field in content
    assert content["key_observations"], "预期至少一条结构化结论"
    allowed = {"observed_fact", "statistical_finding", "hypothesis", "recommendation"}
    for claim in content["key_observations"]:
        assert claim["claim_type"] in allowed
        for sub in ("claim", "evidence", "calculation", "confidence_level", "limitation"):
            assert sub in claim and claim[sub]
    assert content["experimental_summary"]["experiment_count"] == 3
    assert content["metric_comparisons"]["methods"] == ["MethodC", "MethodD"]


# 16. LLM 未配置时确定性分析仍然可用（use_llm=True 也不编造）
def test_no_llm_deterministic_analysis(client: TestClient) -> None:
    ids = _import_records(client, VALID_JSON)
    response = client.post("/api/experiments/analyze", json={"experiment_ids": ids, "use_llm": True})
    assert response.status_code == 200
    insight = response.json()
    assert insight["ai_status"] == "not_used"
    content = insight["content"]
    assert content["key_observations"]
    assert content["is_simulated"] is False
    # 没有任何 LLM 编造的数值字段：metric 仍来自 comparison
    assert content["metric_comparisons"]["primary_metric"] == "macro_f1"


# 17. 报告导出 Markdown 与 JSON，全部数值来自计算且标注模拟数据
def test_report_export_markdown_and_json(client: TestClient) -> None:
    seeded = client.post("/api/experiments/demo/seed")
    assert seeded.status_code == 200
    ids = client.get("/api/experiments").json()["items"]
    insight = _analyze(client, [r["id"] for r in ids])
    assert insight["content"]["is_simulated"] is True

    md = client.get(f"/api/insights/{insight['id']}/export", params={"format": "markdown"})
    assert md.status_code == 200
    assert md.headers["content-type"].startswith("text/markdown")
    assert "模拟" in md.text
    assert "Macro-F1" in md.text or "macro_f1" in md.text

    exported = client.get(f"/api/insights/{insight['id']}/export", params={"format": "json"})
    assert exported.status_code == 200
    body = exported.json()
    assert body["experimental_summary"]["is_simulated"] is True
    assert body["stability_analysis"]["summary"]["ci_method"]


# 18. 数据持久化与历史记录恢复
def test_persistence_and_history_recovery(client: TestClient) -> None:
    ids = _import_records(client, VALID_JSON)
    insight = _analyze(client, ids)
    comparison = client.post("/api/experiments/compare", json={"experiment_ids": ids}).json()

    with TestClient(app) as restarted:
        listed = restarted.get("/api/experiments").json()
        assert listed["total"] == 3
        assert {r["id"] for r in listed["items"]} == set(ids)
        restored_insight = restarted.get(f"/api/insights/{insight['id']}").json()
        assert restored_insight["id"] == insight["id"]
        assert restored_insight["ai_status"] == "not_used"
        assert restored_insight["content"]["experimental_summary"]["experiment_count"] == 3
        restored_cmp = restarted.get(f"/api/experiments/comparisons/{comparison['id']}").json()
        assert restored_cmp["result"]["methods"] == ["MethodC", "MethodD"]


# 19. 演示数据幂等种子（重复载入不产生重复记录，标记模拟）
def test_demo_seed_is_idempotent(client: TestClient) -> None:
    first = client.post("/api/experiments/demo/seed").json()
    assert first["count"] == 12
    second = client.post("/api/experiments/demo/seed").json()
    assert second["count"] == 12
    listed = client.get("/api/experiments").json()
    assert listed["total"] == 12
    assert all(r["is_simulated"] for r in listed["items"])
    methods = {r["method"] for r in listed["items"]}
    assert methods == {"Central-CE", "FedAvg-CE", "Central-BSM", "FedAvg-BSM"}


# 20. 数据库迁移幂等（init_db 多次不丢数据，新表存在）
def test_schema_migration_idempotent(client: TestClient) -> None:
    from app.db import connect, init_db

    _import_records(client, VALID_JSON)
    init_db()
    init_db()
    with connect() as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for required in ("experiment_records", "experiment_groups", "experiment_comparisons", "insight_reports"):
            assert required in tables
        assert connection.execute("SELECT COUNT(*) FROM experiment_records").fetchone()[0] == 3


# Phase 7A：值 1 必须确认单位，preview → confirm 不得二次换算，原始值随记录恢复。
def test_ambiguous_unit_confirmation_and_raw_metric_persistence(client: TestClient) -> None:
    raw = [{"experiment_id": "unit_1", "method": "MethodUnit", "dataset": "DS1", "seed": 1, "accuracy": 1.0, "macro_f1": 1.0}]
    preview = client.post("/api/experiments/import/preview", json=raw)
    assert preview.status_code == 200
    body = preview.json()
    assert body["ok"] is False
    assert any(item["code"] == "metrics_scale_confirmation_required" for item in body["errors"])

    unresolved = client.post("/api/experiments/import", json={"records": body["records"], "source_format": "json"})
    assert unresolved.status_code == 422
    confirmed = client.post("/api/experiments/import", json={
        "records": body["records"], "source_format": "json", "metrics_scale": "percent",
    })
    assert confirmed.status_code == 200, confirmed.text
    stored = client.get(f"/api/experiments/{confirmed.json()['ids'][0]}").json()
    assert stored["accuracy"] == pytest.approx(0.01)
    assert stored["macro_f1"] == pytest.approx(0.01)
    assert stored["raw_metrics"]["accuracy"] == pytest.approx(1.0)
    assert stored["original_metrics_scale"] == "percent"
    assert stored["metric_source"] == "imported_summary"


# Phase 7A：标签顺序变化必须同时重排矩阵行和列；两种 Macro-F1 口径分开命名。
def test_confusion_label_reorder_and_macro_f1_definitions(client: TestClient) -> None:
    matrix = [[8, 1, 0], [2, 5, 1], [0, 3, 4]]
    reordered = [[4, 0, 3], [0, 8, 1], [1, 2, 5]]
    ids = _import_records(client, [
        {
            "experiment_id": "cm_1", "method": "MethodCM", "dataset": "DS-CM", "seed": 1,
            "macro_f1": 0.70, "confusion_labels": ["z", "a", "m"], "confusion_matrix": matrix,
        },
        {
            "experiment_id": "cm_2", "method": "MethodCM", "dataset": "DS-CM", "seed": 2,
            "macro_f1": 0.80, "confusion_labels": ["m", "z", "a"], "confusion_matrix": reordered,
        },
    ])
    result = client.post("/api/experiments/compare", json={"experiment_ids": ids}).json()["result"]
    confusion = result["confusion"]
    assert confusion["labels"]["MethodCM"] == ["z", "a", "m"]
    assert confusion["matrices"]["MethodCM"] == matrix
    assert confusion["per_class"]["MethodCM"]["z"]["precision"] == pytest.approx(0.8)
    assert confusion["per_class"]["MethodCM"]["z"]["recall"] == pytest.approx(8 / 9)
    assert confusion["per_class"]["MethodCM"]["a"]["f1"] == pytest.approx(0.588235)
    assert confusion["macro_f1_from_confusion"]["MethodCM"] == pytest.approx(0.699002)
    assert result["method_stats"]["MethodCM"]["macro_f1_mean_of_runs"] == pytest.approx(0.75)
    assert "不互相替代" in result["macro_f1_definitions"]["note"]


# Phase 7A：关联不足只标未核实；明确不同数据集则禁止混合排名。
def test_comparability_guardrails(client: TestClient) -> None:
    same_name_ids = _import_records(client, [
        {"experiment_id": "cmp_a", "method": "A", "dataset": "same-display-name", "seed": 1, "macro_f1": 0.7},
        {"experiment_id": "cmp_b", "method": "B", "dataset": "same-display-name", "seed": 1, "macro_f1": 0.8},
    ])
    unverified = client.post("/api/experiments/compare", json={"experiment_ids": same_name_ids}).json()["result"]
    assert unverified["comparability"]["status"] == "unverified"
    assert unverified["rankings"]

    different_ids = _import_records(client, [
        {"experiment_id": "cmp_c", "method": "C", "dataset": "DS-C", "seed": 1, "macro_f1": 0.7},
        {"experiment_id": "cmp_d", "method": "D", "dataset": "DS-D", "seed": 1, "macro_f1": 0.8},
    ])
    incompatible = client.post("/api/experiments/compare", json={"experiment_ids": different_ids}).json()["result"]
    assert incompatible["comparability"]["status"] == "incompatible"
    assert incompatible["comparability"]["ranking_suppressed"] is True
    assert incompatible["rankings"] == []


# Phase 7A：重复 seed 不能扩大独立样本数；n=1 不产生稳定性区间。
def test_duplicate_seed_excluded_from_stability_interval(client: TestClient) -> None:
    ids = _import_records(client, [
        {"experiment_id": "seed_a", "method": "MethodSeed", "dataset": "DS1", "seed": 1, "macro_f1": 0.70},
        {"experiment_id": "seed_a_repeat", "method": "MethodSeed", "dataset": "DS1", "seed": 1, "macro_f1": 0.90},
        {"experiment_id": "seed_b", "method": "MethodSeed", "dataset": "DS1", "seed": 2, "macro_f1": 0.80},
    ])
    content = _analyze(client, ids)["content"]
    group = content["stability_analysis"]["groups"][0]
    assert group["run_count"] == 3
    assert group["independent_run_count"] == 1
    assert group["duplicate_seeds"] == ["1"]
    assert group["metrics"]["macro_f1"]["count"] == 1
    assert group["metrics"]["macro_f1"]["confidence_interval"] is None
    assert group["can_assess_stability"] is False
    assert len(group["excluded_record_ids"]) == 2


# Phase 7A：科研/演示筛选、混合来源说明与不存在关联的真实失败。
def test_data_source_isolation_and_linkage_validation(client: TestClient) -> None:
    unknown_id = _import_records(client, [
        {"experiment_id": "source_unknown", "method": "Unknown", "dataset": "DS1", "seed": 1, "macro_f1": 0.7},
    ])[0]
    test_id = _import_records(client, [
        {"experiment_id": "source_test", "method": "Test", "dataset": "DS1", "seed": 1, "macro_f1": 0.8},
    ], data_source="test")[0]
    simulated_id = _import_records(client, [
        {"experiment_id": "source_sim", "method": "Sim", "dataset": "DS1", "seed": 1, "macro_f1": 0.9},
    ], is_simulated=True, data_source="simulated")[0]

    research = client.get("/api/experiments", params={"source_scope": "research"}).json()["items"]
    demo = client.get("/api/experiments", params={"source_scope": "demo"}).json()["items"]
    assert {row["id"] for row in research} == {unknown_id}
    assert research[0]["data_source"] == "unknown"
    assert {row["id"] for row in demo} == {test_id, simulated_id}

    mixed = _analyze(client, [unknown_id, simulated_id])["content"]["experimental_summary"]
    assert mixed["data_sources"] == ["simulated", "unknown"]
    assert mixed["has_demo_data"] is True
    assert "混合来源" in mixed["data_label"]

    missing_dataset = client.post("/api/experiments/import", json={
        "records": [{"experiment_id": "bad_link", "method": "Bad", "dataset": "DS1", "macro_f1": 0.7}],
        "source_format": "json", "dataset_ref_id": "missing_dataset",
    })
    assert missing_dataset.status_code == 404
    assert missing_dataset.json()["detail"]["code"] == "dataset_not_found"
    missing_audit = client.post("/api/experiments/analyze", json={
        "experiment_ids": [unknown_id], "audit_id": "missing_audit", "use_llm": False,
    })
    assert missing_audit.status_code == 404
    assert missing_audit.json()["detail"]["code"] == "audit_not_found"
