"""Deterministic workflow orchestration engine.

Responsibilities:
- materialise a workflow and its nodes from the registry (idempotently)
- schedule runnable nodes in dependency order
- pause at human approval gates
- retry failed nodes with a bounded retry budget
- persist every state change and emit an append-only event log
- never re-run a node that already completed successfully
"""

from __future__ import annotations

import json
import time
import uuid
from typing import Any

from ..db import connect
from .llm_provider import capture_llm_requests
from .workflow_agents import HANDLERS, audit_requires_approval
from .workflow_events import record_event, utc_now
from .workflow_registry import template_map, templates_for
from .workflow_report import (
    build_workflow_report,
    build_workflow_report_markdown,
    capture_workflow_snapshot,
)
from .workflow_state import (
    NODE_SATISFIED_STATUSES,
    TERMINAL_WORKFLOW_STATUSES,
    WORKFLOW_TYPES,
    WorkflowInputError,
    WorkflowStateError,
)

MAX_EXECUTION_STEPS = 40
CONTEXT_REF_KEYS = ("paper_id", "protocol_id", "dataset_id", "audit_id", "comparison_id", "insight_id")


class WorkflowNotFound(LookupError):
    pass


def _loads(raw: Any) -> Any:
    if not raw:
        return {}
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}


def _dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


# --------------------------------------------------------------------------- #
# readers
# --------------------------------------------------------------------------- #
def _workflow_row(connection: Any, workflow_id: str) -> dict[str, Any] | None:
    row = connection.execute("SELECT * FROM research_workflows WHERE id = ?", (workflow_id,)).fetchone()
    return dict(row) if row else None


def _node_rows(connection: Any, workflow_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        "SELECT * FROM workflow_nodes WHERE workflow_id = ? ORDER BY order_no ASC", (workflow_id,)
    ).fetchall()
    return [dict(row) for row in rows]


def _node_out(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row["id"],
        "workflow_id": row["workflow_id"],
        "node_key": row["node_key"],
        "agent_name": row["agent_name"],
        "title": row["title"],
        "order_no": row["order_no"],
        "depends_on": _loads(row["depends_on"]),
        "requires_approval": bool(row["requires_approval"]),
        "optional": bool(row["optional"]),
        "status": row["status"],
        "input_ref": _loads(row["input_ref"]),
        "output_ref": _loads(row["output_ref"]),
        "error": row["error"],
        "retry_count": row["retry_count"],
        "max_retries": row["max_retries"],
        "started_at": row["started_at"],
        "completed_at": row["completed_at"],
        "duration": row["duration"],
    }


def _approval_out(item: Any) -> dict[str, Any]:
    return {
        "id": item["id"],
        "node_id": item["node_id"],
        "decision": item["decision"],
        "comment": item["comment"],
        "reviewer": item["reviewer"],
        "created_at": item["created_at"],
        "audit_id": item["audit_id"],
        "finding_ids": _loads(item["finding_ids"]) or [],
        "input_version": item["input_version"],
        "risk_acknowledged": bool(item["risk_acknowledged"]),
        "semantics": item["semantics"],
    }


def _workflow_out(connection: Any, row: dict[str, Any]) -> dict[str, Any]:
    nodes = [_node_out(node) for node in _node_rows(connection, row["id"])]
    return {
        "id": row["id"],
        "name": row["name"],
        "workflow_type": row["workflow_type"],
        "status": row["status"],
        "config": _loads(row["config"]),
        "context": _loads(row["context"]),
        "idempotency_key": row["idempotency_key"],
        "error": row["error"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
        "completed_at": row["completed_at"],
        "input_version": (_loads(row["input_snapshot"]) or {}).get("input_version"),
        "cancel_requested": bool(row["cancel_requested"]),
        "report_finalized": bool(row["report_snapshot"]),
        "nodes": nodes,
        "progress": {
            "total": len(nodes),
            "completed": sum(1 for n in nodes if n["status"] == "completed"),
            "skipped": sum(1 for n in nodes if n["status"] == "skipped"),
            "failed": sum(1 for n in nodes if n["status"] == "failed"),
            "waiting": sum(1 for n in nodes if n["status"] == "waiting_approval"),
        },
    }


def get_workflow(workflow_id: str) -> dict[str, Any]:
    with connect() as connection:
        row = _workflow_row(connection, workflow_id)
        if row is None:
            raise WorkflowNotFound(workflow_id)
        workflow = _workflow_out(connection, row)
        approvals = [
            _approval_out(item)
            for item in connection.execute(
                "SELECT * FROM workflow_approvals WHERE workflow_id = ? ORDER BY created_at ASC, rowid ASC",
                (workflow_id,),
            ).fetchall()
        ]
    workflow["approvals"] = approvals
    return workflow


def list_workflows(status: str | None = None, limit: int = 100) -> dict[str, Any]:
    with connect() as connection:
        if status:
            rows = connection.execute(
                "SELECT * FROM research_workflows WHERE status = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
                (status, limit),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT * FROM research_workflows ORDER BY created_at DESC, rowid DESC LIMIT ?", (limit,)
            ).fetchall()
        items = []
        for row in rows:
            record = dict(row)
            items.append(
                {
                    "id": record["id"],
                    "name": record["name"],
                    "workflow_type": record["workflow_type"],
                    "status": record["status"],
                    "created_at": record["created_at"],
                    "updated_at": record["updated_at"],
                    "completed_at": record["completed_at"],
                    "error": record["error"],
                    "report_finalized": bool(record["report_snapshot"]),
                    "progress": {
                        "total": len(_node_rows(connection, record["id"])),
                        "completed": sum(
                            1 for n in _node_rows(connection, record["id"]) if n["status"] == "completed"
                        ),
                    },
                }
            )
        return {"items": items, "total": len(items)}


# --------------------------------------------------------------------------- #
# create
# --------------------------------------------------------------------------- #
def create_workflow(payload: dict[str, Any]) -> tuple[dict[str, Any], bool]:
    """Create a workflow with its nodes. Returns (workflow, created)."""
    workflow_type = payload.get("workflow_type") or "full_reproduction"
    if workflow_type not in WORKFLOW_TYPES:
        raise WorkflowStateError("invalid_workflow_type", f"未知工作流类型：{workflow_type}")

    idempotency_key = payload.get("idempotency_key")
    now = utc_now()
    workflow_id = f"wf_{uuid.uuid4().hex[:16]}"

    config = {
        "paper_id": payload.get("paper_id"),
        "dataset_id": payload.get("dataset_id"),
        "experiment_ids": payload.get("experiment_ids") or [],
        "comparison_id": payload.get("comparison_id"),
        "mapping": payload.get("mapping"),
        "protocol_name": payload.get("protocol_name"),
        "baseline_method": payload.get("baseline_method"),
        "primary_metric": payload.get("primary_metric") or "macro_f1",
        "use_llm": bool(payload.get("use_llm")),
        "reuse_audit": payload.get("reuse_audit", True),
    }
    context: dict[str, Any] = {}
    for key in CONTEXT_REF_KEYS:
        if config.get(key):
            context[key] = config[key]

    with connect() as connection:
        if idempotency_key:
            existing = connection.execute(
                "SELECT id FROM research_workflows WHERE idempotency_key = ?", (idempotency_key,)
            ).fetchone()
            if existing is not None:
                row = _workflow_row(connection, existing["id"])
                return _workflow_out(connection, row), False

        snapshot = capture_workflow_snapshot(
            connection, config=config, context=context, stage="initial"
        )
        connection.execute(
            "INSERT INTO research_workflows (id, name, workflow_type, status, config, context, idempotency_key,"
            " error, input_snapshot, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                workflow_id,
                payload.get("name") or "科研复现工作流",
                workflow_type,
                "pending",
                _dumps(config),
                _dumps(context),
                idempotency_key,
                None,
                _dumps(snapshot),
                now,
                now,
            ),
        )
        for template in templates_for(workflow_type):
            connection.execute(
                "INSERT INTO workflow_nodes (id, workflow_id, node_key, agent_name, title, order_no, depends_on,"
                " requires_approval, optional, status, input_ref, output_ref, error, retry_count, max_retries,"
                " started_at, completed_at, duration, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    f"wn_{uuid.uuid4().hex[:16]}",
                    workflow_id,
                    template.key,
                    template.agent_name,
                    template.title,
                    template.order_no,
                    _dumps(list(template.depends_on)),
                    1 if template.requires_approval else 0,
                    1 if template.optional else 0,
                    "pending",
                    _dumps({}),
                    _dumps({}),
                    None,
                    0,
                    2,
                    None,
                    None,
                    None,
                    now,
                    now,
                ),
            )
        connection.commit()
        record_event(
            workflow_id, "workflow_created", f"工作流已创建（{workflow_type}）", payload={"config": config}, connection=connection
        )
        connection.commit()
        row = _workflow_row(connection, workflow_id)
        return _workflow_out(connection, row), True


# --------------------------------------------------------------------------- #
# execution
# --------------------------------------------------------------------------- #
def _deps_satisfied(node: dict[str, Any], nodes_by_key: dict[str, dict[str, Any]]) -> bool:
    for dep in _loads(node["depends_on"]):
        dep_node = nodes_by_key.get(dep)
        if dep_node is None or dep_node["status"] not in NODE_SATISFIED_STATUSES:
            return False
    return True


def _dep_failed(node: dict[str, Any], nodes_by_key: dict[str, dict[str, Any]]) -> bool:
    for dep in _loads(node["depends_on"]):
        dep_node = nodes_by_key.get(dep)
        if dep_node is not None and dep_node["status"] == "failed":
            return True
    return False


def _set_node(
    connection: Any,
    node_id: str,
    *,
    status: str | None = None,
    input_ref: dict[str, Any] | None = None,
    output: dict[str, Any] | None = None,
    error: str | None = None,
    started_at: str | None = None,
    completed_at: str | None = None,
    duration: float | None = None,
    clear_error: bool = False,
) -> None:
    fields: list[str] = ["updated_at = ?"]
    values: list[Any] = [utc_now()]
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if input_ref is not None:
        fields.append("input_ref = ?")
        values.append(_dumps(input_ref))
    if output is not None:
        fields.append("output_ref = ?")
        values.append(_dumps(output))
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if clear_error:
        fields.append("error = NULL")
    if started_at is not None:
        fields.append("started_at = ?")
        values.append(started_at)
    if completed_at is not None:
        fields.append("completed_at = ?")
        values.append(completed_at)
    if duration is not None:
        fields.append("duration = ?")
        values.append(duration)
    values.append(node_id)
    connection.execute(f"UPDATE workflow_nodes SET {', '.join(fields)} WHERE id = ?", values)


def _set_workflow(
    connection: Any,
    workflow_id: str,
    *,
    status: str | None = None,
    context: dict[str, Any] | None = None,
    error: str | None = None,
    clear_error: bool = False,
    completed_at: str | None = None,
) -> None:
    fields: list[str] = ["updated_at = ?"]
    values: list[Any] = [utc_now()]
    if status is not None:
        fields.append("status = ?")
        values.append(status)
    if context is not None:
        fields.append("context = ?")
        values.append(_dumps(context))
    if error is not None:
        fields.append("error = ?")
        values.append(error)
    if clear_error:
        fields.append("error = NULL")
    if completed_at is not None:
        fields.append("completed_at = ?")
        values.append(completed_at)
    values.append(workflow_id)
    connection.execute(f"UPDATE research_workflows SET {', '.join(fields)} WHERE id = ?", values)


def _skip_node(connection: Any, node: dict[str, Any], reason: str) -> None:
    now = utc_now()
    _set_node(
        connection,
        node["id"],
        status="skipped",
        error=reason,
        started_at=node["started_at"] or now,
        completed_at=now,
        duration=0.0,
    )
    record_event(node["workflow_id"], "node_skipped", reason, node_id=node["id"], connection=connection)


def _update_snapshot(
    connection: Any,
    workflow_id: str,
    *,
    context: dict[str, Any],
    stage: str,
) -> dict[str, Any]:
    row = _workflow_row(connection, workflow_id)
    snapshot = capture_workflow_snapshot(
        connection,
        config=_loads(row["config"]),
        context=context,
        existing=_loads(row["input_snapshot"]),
        stage=stage,
    )
    connection.execute(
        "UPDATE research_workflows SET input_snapshot = ?, updated_at = ? WHERE id = ?",
        (_dumps(snapshot), utc_now(), workflow_id),
    )
    return snapshot


def _cancellation_requested(connection: Any, workflow_id: str) -> bool:
    row = connection.execute(
        "SELECT status, cancel_requested FROM research_workflows WHERE id = ?", (workflow_id,)
    ).fetchone()
    return bool(row and (row["cancel_requested"] or row["status"] == "cancelled"))


def _execute_node(workflow_id: str, context: dict[str, Any], node: dict[str, Any]) -> str:
    """Execute one node. Returns 'completed' | 'skipped' | 'waiting_approval' | 'failed' | 'cancelled'."""
    template = template_map()[node["node_key"]]
    operation_key = f"{workflow_id}:{node['node_key']}"
    handler_context = {
        **context,
        "workflow_id": workflow_id,
        "_operation_key": operation_key,
    }
    started = time.perf_counter()
    now = utc_now()

    # Approval gates ----------------------------------------------------- #
    if template.requires_approval:
        with connect() as connection:
            if _cancellation_requested(connection, workflow_id):
                return "cancelled"
            snapshot = _loads(_workflow_row(connection, workflow_id)["input_snapshot"])
            input_ref = {
                "input_version": snapshot.get("input_version"),
                "context_refs": {key: context.get(key) for key in CONTEXT_REF_KEYS if context.get(key)},
            }
            if node["node_key"] == "protocol_approve" and not context.get("protocol_id"):
                _skip_node(connection, node, "无实验方案，跳过方案确认。")
                connection.commit()
                return "skipped"
            if node["node_key"] == "audit_approve" and not context.get("audit_id"):
                _skip_node(connection, node, "未执行数据审计，跳过审计确认。")
                connection.commit()
                return "skipped"
            if node["node_key"] == "audit_approve":
                need, reason = audit_requires_approval(handler_context)
                if not need:
                    _set_node(
                        connection,
                        node["id"],
                        status="completed",
                        input_ref=input_ref,
                        output={
                            "auto_approved": True,
                            "reason": reason,
                            "audit_id": context.get("audit_id"),
                            "input_version": snapshot.get("input_version"),
                            "execution_mode": "automatic_validation",
                        },
                        started_at=now,
                        completed_at=utc_now(),
                        duration=round(time.perf_counter() - started, 4),
                    )
                    record_event(workflow_id, "approval_auto_passed", reason, node_id=node["id"], connection=connection)
                    connection.commit()
                    return "completed"
                _set_node(
                    connection,
                    node["id"],
                    status="waiting_approval",
                    input_ref=input_ref,
                    output={
                        "approval_reason": reason,
                        "audit_id": context.get("audit_id"),
                        "input_version": snapshot.get("input_version"),
                        "risk_semantics": "acknowledge_and_continue",
                    },
                    started_at=now,
                )
                record_event(
                    workflow_id, "approval_requested", reason, node_id=node["id"], payload={"stage": node["node_key"]}, connection=connection
                )
                _set_workflow(connection, workflow_id, status="waiting_approval")
                connection.commit()
                return "waiting_approval"
            # Unconditional human gate
            _set_node(
                connection, node["id"], status="waiting_approval", input_ref=input_ref, started_at=now
            )
            record_event(
                workflow_id,
                "approval_requested",
                f"等待人工确认：{node['title']}",
                node_id=node["id"],
                payload={"stage": node["node_key"]},
                connection=connection,
            )
            _set_workflow(connection, workflow_id, status="waiting_approval")
            connection.commit()
            return "waiting_approval"

    # Agent execution ---------------------------------------------------- #
    with connect() as connection:
        if _cancellation_requested(connection, workflow_id):
            return "cancelled"
        snapshot = _loads(_workflow_row(connection, workflow_id)["input_snapshot"])
        _set_node(
            connection,
            node["id"],
            status="running",
            input_ref={
                "input_version": snapshot.get("input_version"),
                "context_refs": {key: context.get(key) for key in CONTEXT_REF_KEYS if context.get(key)},
                "operation_key": operation_key,
            },
            started_at=now,
        )
        record_event(
            workflow_id,
            "node_started",
            f"{node['agent_name']} 开始执行：{node['title']}",
            node_id=node["id"],
            connection=connection,
        )
        connection.commit()

    try:
        with capture_llm_requests() as llm_requests:
            output = HANDLERS[node["node_key"]](handler_context, _merge_config(workflow_id))
        if llm_requests:
            output["llm_requests"] = llm_requests
        if output.get("execution_mode") == "live_llm" and not any(
            request["status"] == "json_received" for request in llm_requests
        ):
            output["execution_mode"] = "llm_unverified"
    except WorkflowInputError as exc:
        with connect() as connection:
            if _cancellation_requested(connection, workflow_id):
                record_event(
                    workflow_id, "node_late_result_ignored", f"取消后忽略 {node['title']} 的晚到失败结果。",
                    node_id=node["id"], payload={"llm_requests": llm_requests}, connection=connection,
                )
                connection.commit()
                return "cancelled"
            if template.optional and exc.code in {"missing_paper_id", "missing_dataset_id"}:
                _skip_node(connection, node, exc.message)
                connection.commit()
                return "skipped"
            _set_node(
                connection,
                node["id"],
                status="failed",
                error=exc.message,
                completed_at=utc_now(),
                duration=round(time.perf_counter() - started, 4),
            )
            record_event(
                workflow_id, "node_failed", f"{node['title']} 失败：{exc.message}", node_id=node["id"],
                payload={"code": exc.code, "llm_requests": llm_requests}, connection=connection,
            )
            _set_workflow(connection, workflow_id, status="failed", error=exc.message)
            connection.commit()
            return "failed"
    except Exception as exc:  # noqa: BLE001 - surface unexpected handler errors to the log
        message = f"{type(exc).__name__}: {exc}"
        with connect() as connection:
            if _cancellation_requested(connection, workflow_id):
                record_event(
                    workflow_id, "node_late_result_ignored", f"取消后忽略 {node['title']} 的晚到异常。",
                    node_id=node["id"], payload={"llm_requests": llm_requests}, connection=connection,
                )
                connection.commit()
                return "cancelled"
            _set_node(
                connection,
                node["id"],
                status="failed",
                error=message,
                completed_at=utc_now(),
                duration=round(time.perf_counter() - started, 4),
            )
            record_event(
                workflow_id, "node_failed", f"{node['title']} 异常：{message}", node_id=node["id"],
                payload={"llm_requests": llm_requests}, connection=connection,
            )
            _set_workflow(connection, workflow_id, status="failed", error=message)
            connection.commit()
            return "failed"

    duration = round(time.perf_counter() - started, 4)
    with connect() as connection:
        if _cancellation_requested(connection, workflow_id):
            record_event(
                workflow_id,
                "node_late_result_ignored",
                f"取消后忽略 {node['title']} 的晚到结果；已保存业务记录可通过操作标识追溯。",
                node_id=node["id"],
                payload={"operation_key": operation_key, "output_ref": output},
                connection=connection,
            )
            connection.commit()
            return "cancelled"
        merged_context = dict(context)
        for key in CONTEXT_REF_KEYS:
            if output.get(key):
                merged_context[key] = output[key]
        if node["node_key"] == "experiment_analyze":
            merged_context["is_simulated"] = bool(output.get("is_simulated"))
        snapshot = _update_snapshot(
            connection, workflow_id, context=merged_context, stage=node["node_key"]
        )
        _set_node(
            connection,
            node["id"],
            status="completed",
            input_ref={
                "input_version": snapshot.get("input_version"),
                "context_refs": {key: merged_context.get(key) for key in CONTEXT_REF_KEYS if merged_context.get(key)},
                "operation_key": operation_key,
            },
            output=output,
            completed_at=utc_now(),
            duration=duration,
            clear_error=True,
        )
        _set_workflow(connection, workflow_id, context=merged_context, clear_error=True)
        record_event(
            workflow_id,
            "node_completed",
            f"{node['agent_name']} 完成：{node['title']}",
            node_id=node["id"],
            payload={"output_ref": output, "duration": duration, "input_version": snapshot.get("input_version")},
            connection=connection,
        )
        connection.commit()
    return "completed"


def _merge_config(workflow_id: str) -> dict[str, Any]:
    with connect() as connection:
        row = _workflow_row(connection, workflow_id)
    return _loads(row["config"]) if row else {}


def _finalize_report(connection: Any, workflow_id: str) -> None:
    row = _workflow_row(connection, workflow_id)
    snapshot = _loads(row["input_snapshot"])
    workflow = _workflow_out(connection, row)
    workflow["report_finalized"] = True
    workflow["approvals"] = [
        _approval_out(item)
        for item in connection.execute(
            "SELECT * FROM workflow_approvals WHERE workflow_id = ? ORDER BY created_at ASC, rowid ASC",
            (workflow_id,),
        ).fetchall()
    ]
    report = build_workflow_report(
        workflow["context"], workflow=workflow, nodes=workflow["nodes"], snapshot=snapshot
    )
    connection.execute(
        "UPDATE research_workflows SET report_snapshot = ?, updated_at = ? WHERE id = ?",
        (_dumps(report), utc_now(), workflow_id),
    )


def advance(workflow_id: str) -> dict[str, Any]:
    """Atomically claim a runner and execute until a gate, failure, cancellation, or completion."""
    runner_token = uuid.uuid4().hex
    with connect() as connection:
        row = _workflow_row(connection, workflow_id)
        if row is None:
            raise WorkflowNotFound(workflow_id)
        if row["status"] in TERMINAL_WORKFLOW_STATUSES or row["status"] == "waiting_approval":
            return get_workflow(workflow_id)
        claimed = connection.execute(
            "UPDATE research_workflows SET runner_token = ?, runner_started_at = ?, status = 'running',"
            " error = NULL, updated_at = ? WHERE id = ? AND runner_token IS NULL"
            " AND status NOT IN ('completed', 'cancelled', 'waiting_approval')",
            (runner_token, utc_now(), utc_now(), workflow_id),
        )
        if claimed.rowcount != 1:
            return get_workflow(workflow_id)
        record_event(workflow_id, "workflow_started", "工作流开始执行", connection=connection)
        context = _loads(row["context"])
        connection.commit()

    try:
        for _ in range(MAX_EXECUTION_STEPS):
            with connect() as connection:
                if _cancellation_requested(connection, workflow_id):
                    break
                nodes = _node_rows(connection, workflow_id)
            nodes_by_key = {node["node_key"]: node for node in nodes}

            if any(node["status"] == "failed" for node in nodes):
                break

            blocking_failure = next(
                (
                    node for node in nodes
                    if node["status"] == "pending" and _dep_failed(node, nodes_by_key)
                ),
                None,
            )
            if blocking_failure is not None:
                with connect() as connection:
                    if not _cancellation_requested(connection, workflow_id):
                        _set_workflow(
                            connection,
                            workflow_id,
                            status="failed",
                            error=f"上游节点失败，{blocking_failure['title']} 无法执行。",
                        )
                        record_event(
                            workflow_id,
                            "workflow_failed",
                            f"上游节点失败：{blocking_failure['title']}",
                            node_id=blocking_failure["id"],
                            connection=connection,
                        )
                        connection.commit()
                break

            runnable = next(
                (
                    node for node in nodes
                    if node["status"] == "pending" and _deps_satisfied(node, nodes_by_key)
                ),
                None,
            )
            if runnable is None:
                break

            outcome = _execute_node(workflow_id, context, runnable)
            with connect() as connection:
                row = _workflow_row(connection, workflow_id)
            context = _loads(row["context"]) if row else context
            if outcome in {"waiting_approval", "failed", "cancelled"}:
                break

        with connect() as connection:
            nodes = _node_rows(connection, workflow_id)
            row = _workflow_row(connection, workflow_id)
            statuses = {node["status"] for node in nodes}
            if row["status"] not in TERMINAL_WORKFLOW_STATUSES and not row["cancel_requested"]:
                if "failed" in statuses:
                    _set_workflow(connection, workflow_id, status="failed")
                elif all(node["status"] in NODE_SATISFIED_STATUSES for node in nodes):
                    _set_workflow(
                        connection, workflow_id, status="completed", completed_at=utc_now(), clear_error=True
                    )
                    record_event(
                        workflow_id,
                        "workflow_completed",
                        "工作流全部节点执行结束；不代表科学有效或训练复现完成。",
                        connection=connection,
                    )
                    _finalize_report(connection, workflow_id)
                elif "waiting_approval" in statuses:
                    _set_workflow(connection, workflow_id, status="waiting_approval")
            connection.commit()
    finally:
        with connect() as connection:
            connection.execute(
                "UPDATE research_workflows SET runner_token = NULL, runner_started_at = NULL"
                " WHERE id = ? AND runner_token = ?",
                (workflow_id, runner_token),
            )
            connection.commit()
    return get_workflow(workflow_id)


# --------------------------------------------------------------------------- #
# approvals / retry / cancel
# --------------------------------------------------------------------------- #
def submit_approval(workflow_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    decision = (payload.get("decision") or "").lower()
    if decision not in {"approve", "reject"}:
        raise WorkflowStateError("invalid_decision", "审批决定必须是 approve 或 reject。")
    node_id = payload.get("node_id")
    node_key = payload.get("node_key")
    comment = payload.get("comment")
    reviewer = payload.get("reviewer") or "researcher"

    with connect() as connection:
        row = _workflow_row(connection, workflow_id)
        if row is None:
            raise WorkflowNotFound(workflow_id)
        nodes = _node_rows(connection, workflow_id)
        if node_id:
            node = next((item for item in nodes if item["id"] == node_id), None)
        elif node_key:
            node = next((item for item in nodes if item["node_key"] == node_key), None)
        else:
            node = next((item for item in nodes if item["status"] == "waiting_approval"), None)

        if node is None:
            raise WorkflowStateError("node_not_found", "未找到对应节点。")
        if node["status"] != "waiting_approval":
            raise WorkflowStateError(
                "node_not_waiting_approval",
                f"节点 {node['node_key']} 当前状态为 {node['status']}，不在等待审批。",
            )

        claimed = connection.execute(
            "UPDATE workflow_nodes SET status = 'running', updated_at = ?"
            " WHERE id = ? AND status = 'waiting_approval'",
            (utc_now(), node["id"]),
        )
        if claimed.rowcount != 1:
            raise WorkflowStateError("approval_already_submitted", "该审批已被其他请求处理。")

        snapshot = _loads(row["input_snapshot"])
        input_version = snapshot.get("input_version")
        node_input_version = _loads(node["input_ref"]).get("input_version")
        if node_input_version != input_version:
            raise WorkflowStateError(
                "approval_input_changed", "待审批输入版本已变化，请基于新内容重新运行，不能沿用旧审批。"
            )
        context = _loads(row["context"])
        audit_id = context.get("audit_id") if node["node_key"] == "audit_approve" else None
        finding_ids: list[str] = []
        if audit_id:
            finding_ids = [
                item["id"] for item in connection.execute(
                    "SELECT id FROM audit_findings WHERE audit_id = ? AND severity IN ('critical', 'high')"
                    " AND status NOT IN ('resolved', 'fixed') ORDER BY rowid",
                    (audit_id,),
                ).fetchall()
            ]
        risk_acknowledged = decision == "approve" and node["node_key"] == "audit_approve" and bool(finding_ids)
        if node["node_key"] == "audit_approve":
            semantics = "risk_acknowledged_continue_analysis" if risk_acknowledged else "audit_reviewed_continue"
        elif node["node_key"] == "report_publish":
            semantics = "local_report_finalization"
        else:
            semantics = "protocol_snapshot_approved"
        if decision == "reject":
            semantics = f"{semantics}_rejected"

        connection.execute(
            "INSERT INTO workflow_approvals (id, workflow_id, node_id, decision, comment, reviewer, created_at,"
            " audit_id, finding_ids, input_version, risk_acknowledged, semantics) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                f"wfa_{uuid.uuid4().hex[:16]}", workflow_id, node["id"], decision, comment, reviewer, utc_now(),
                audit_id, _dumps(finding_ids), input_version, 1 if risk_acknowledged else 0, semantics,
            ),
        )
        if decision == "approve":
            previous_output = _loads(node["output_ref"])
            output = {
                **previous_output,
                "approved": True,
                "reviewer": reviewer,
                "comment": comment,
                "input_version": input_version,
                "audit_id": audit_id,
                "finding_ids": finding_ids,
                "risk_acknowledged": risk_acknowledged,
                "semantics": semantics,
                "execution_mode": "human_review",
            }
            _set_node(
                connection,
                node["id"],
                status="completed",
                output=output,
                completed_at=utc_now(),
                duration=0.0,
                clear_error=True,
            )
            message = (
                "已知悉高风险发现并继续分析；finding 未修复，审计未因此通过。"
                if risk_acknowledged else f"人工确认：{node['title']}"
            )
            record_event(
                workflow_id,
                "approval_approved",
                message,
                node_id=node["id"],
                payload={
                    "reviewer": reviewer, "comment": comment, "input_version": input_version,
                    "audit_id": audit_id, "finding_ids": finding_ids, "semantics": semantics,
                },
                connection=connection,
            )
            _set_workflow(connection, workflow_id, status="running", clear_error=True)
        else:
            message = comment or "人工审核拒绝"
            _set_node(
                connection,
                node["id"],
                status="failed",
                error=f"审核被拒绝：{message}",
                completed_at=utc_now(),
                duration=0.0,
            )
            record_event(
                workflow_id,
                "approval_rejected",
                f"人工审核拒绝：{node['title']}",
                node_id=node["id"],
                payload={"reviewer": reviewer, "comment": comment},
                connection=connection,
            )
            _set_workflow(connection, workflow_id, status="failed", error=f"审核被拒绝：{message}")
        connection.commit()

    if decision == "approve":
        return advance(workflow_id)
    return get_workflow(workflow_id)


def retry_node(workflow_id: str, node_ref: str) -> dict[str, Any]:
    with connect() as connection:
        row = _workflow_row(connection, workflow_id)
        if row is None:
            raise WorkflowNotFound(workflow_id)
        nodes = _node_rows(connection, workflow_id)
        node = next((item for item in nodes if item["id"] == node_ref or item["node_key"] == node_ref), None)
        if node is None:
            raise WorkflowStateError("node_not_found", "未找到对应节点。")
        if node["status"] in {"completed", "skipped"}:
            raise WorkflowStateError(
                "node_already_finished",
                f"节点 {node['node_key']} 已 {node['status']}，不会重复执行。",
            )
        if node["status"] == "waiting_approval":
            raise WorkflowStateError("node_waiting_approval", "节点正在等待人工审批，请先提交审批决定。")
        if node["status"] == "running":
            raise WorkflowStateError("node_running", "节点正在执行中，无法重试。")
        if node["status"] != "failed":
            raise WorkflowStateError("node_not_failed", "只有失败节点可以重试；其他请求已领取该节点。")
        if node["retry_count"] >= node["max_retries"]:
            raise WorkflowStateError(
                "retry_limit_reached",
                f"节点 {node['node_key']} 已达到最大重试次数（{node['max_retries']}）。",
            )

        updated = connection.execute(
            "UPDATE workflow_nodes SET status = 'pending', error = NULL, retry_count = retry_count + 1,"
            " started_at = NULL, completed_at = NULL, duration = NULL, updated_at = ?"
            " WHERE id = ? AND status = ? AND retry_count = ?",
            (utc_now(), node["id"], node["status"], node["retry_count"]),
        )
        if updated.rowcount != 1:
            raise WorkflowStateError("retry_conflict", "节点状态已被其他重试请求改变，请刷新后重试。")
        record_event(
            workflow_id,
            "node_retried",
            f"节点重试：{node['title']}（第 {node['retry_count'] + 1} 次）",
            node_id=node["id"],
            payload={"previous_error": node["error"]},
            connection=connection,
        )
        _set_workflow(connection, workflow_id, status="running", clear_error=True, completed_at=None)
        connection.commit()
    return advance(workflow_id)


def cancel_workflow(workflow_id: str) -> dict[str, Any]:
    with connect() as connection:
        row = _workflow_row(connection, workflow_id)
        if row is None:
            raise WorkflowNotFound(workflow_id)
        if row["status"] in TERMINAL_WORKFLOW_STATUSES:
            raise WorkflowStateError("workflow_finished", f"工作流已处于 {row['status']} 状态，无法取消。")
        for node in _node_rows(connection, workflow_id):
            if node["status"] in {"pending", "running", "waiting_approval"}:
                reason = (
                    "已请求取消；当前业务调用无法立即中断，晚到结果将被忽略。"
                    if node["status"] == "running" else "工作流已取消，不再调度该节点。"
                )
                _set_node(
                    connection,
                    node["id"],
                    status="skipped",
                    error=reason,
                    completed_at=utc_now(),
                    duration=0.0,
                )
        connection.execute(
            "UPDATE research_workflows SET cancel_requested = 1 WHERE id = ?", (workflow_id,)
        )
        _set_workflow(connection, workflow_id, status="cancelled", error="工作流被用户取消", completed_at=utc_now())
        record_event(
            workflow_id, "workflow_cancelled", "已取消调度；执行中的调用若无法中断，其晚到结果不会覆盖取消状态。",
            connection=connection,
        )
        connection.commit()
    return get_workflow(workflow_id)


def start_workflow(workflow_id: str) -> dict[str, Any]:
    with connect() as connection:
        row = _workflow_row(connection, workflow_id)
        if row is None:
            raise WorkflowNotFound(workflow_id)
        if row["status"] == "cancelled":
            raise WorkflowStateError("workflow_cancelled", "已取消的工作流不能重新启动。")
    return advance(workflow_id)


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def _report_payload(workflow_id: str) -> dict[str, Any]:
    with connect() as connection:
        row = _workflow_row(connection, workflow_id)
        if row is None:
            raise WorkflowNotFound(workflow_id)
        if row["report_snapshot"]:
            return _loads(row["report_snapshot"])
        snapshot = _loads(row["input_snapshot"])
    workflow = get_workflow(workflow_id)
    return build_workflow_report(
        workflow["context"], workflow=workflow, nodes=workflow["nodes"], snapshot=snapshot or None
    )


def get_workflow_report(workflow_id: str) -> dict[str, Any]:
    workflow = get_workflow(workflow_id)
    if not workflow["context"].get("insight_id") and workflow["status"] != "completed":
        raise WorkflowStateError("report_not_ready", "实验洞察尚未生成，报告暂不可用。")
    return _report_payload(workflow_id)


def get_workflow_report_markdown(workflow_id: str) -> str:
    return build_workflow_report_markdown(_report_payload(workflow_id))
