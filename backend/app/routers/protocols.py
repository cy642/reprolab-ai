"""Protocol Builder endpoints."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from starlette.responses import Response
from starlette.status import HTTP_201_CREATED, HTTP_204_NO_CONTENT

from ..config import get_settings, public_ai_info
from ..db import connect
from ..schemas import (
    OpenQuestionOut,
    ProtocolDetail,
    ProtocolGenerateRequest,
    ProtocolListResponse,
    ProtocolParamOut,
    ProtocolSaveVersionRequest,
    ProtocolStepOut,
    ProtocolSummary,
    ProtocolUpdateRequest,
    ProtocolVersionOut,
)
from ..services.protocol_agent import (
    INFORMATION_TYPES,
    ParamDraft,
    StepDraft,
    WorkflowValidationError,
    _extract_parameters_from_fields,
    build_heuristic_draft,
    build_protocol_draft,
    validate_workflow_steps,
)

router = APIRouter(prefix="/api/protocols", tags=["Protocols"])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _validate_paper( paper_id: str, require_parsed: bool = True) -> dict:
    with connect() as connection:
        row = connection.execute("SELECT * FROM papers WHERE id = ?", (paper_id,)).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "paper_not_found", "message": "论文不存在。"})
        if require_parsed and row["parse_status"] != "completed":
            raise HTTPException(
                status_code=400,
                detail={
                    "code": "paper_not_parsed",
                    "message": "论文尚未完成解析，无法生成正式协议。",
                },
            )
        fields = connection.execute("SELECT * FROM paper_fields WHERE paper_id = ?", (paper_id,)).fetchall()
        evidence = connection.execute(
            "SELECT id, field, page, quote FROM paper_evidence WHERE paper_id = ? ORDER BY page, rowid",
            (paper_id,),
        ).fetchall()
    return {
        "paper": dict(row),
        "fields": {item["field"]: dict(item) for item in fields},
        "evidence": [dict(item) for item in evidence],
    }


def _protocol_row(connection, protocol_id: str) -> dict:
    row = connection.execute("SELECT * FROM protocols WHERE id = ?", (protocol_id,)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail={"code": "protocol_not_found", "message": "实验方案不存在。"})
    return dict(row)


def _summary(connection: Any, row: dict) -> ProtocolSummary:
    paper_row = connection.execute(
        "SELECT title, parse_status FROM papers WHERE id = ?", (row["paper_id"],)
    ).fetchone()
    paper_title = paper_row["title"] if paper_row else ""
    parsed_paper = bool(paper_row and paper_row["parse_status"] == "completed")
    steps_count = connection.execute(
        "SELECT COUNT(*) FROM protocol_steps WHERE protocol_id = ?", (row["id"],)
    ).fetchone()[0]
    return ProtocolSummary(
        id=row["id"],
        paper_id=row["paper_id"],
        paper_title=paper_title,
        name=row["name"],
        goal=row["goal"],
        status=row["status"],
        version_no=row["version_no"],
        agent_method=row["agent_method"],
        ai_status=row["ai_status"],
        ai_error=row["ai_error"],
        steps_count=steps_count,
        parsed_paper=parsed_paper,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _detail(connection: Any, row: dict) -> ProtocolDetail:
    steps_rows = connection.execute(
        "SELECT * FROM protocol_steps WHERE protocol_id = ? ORDER BY order_no, rowid",
        (row["id"],),
    ).fetchall()
    param_rows = connection.execute(
        "SELECT * FROM protocol_parameters WHERE protocol_id = ? ORDER BY order_no, rowid, name",
        (row["id"],),
    ).fetchall()
    steps = [
        ProtocolStepOut(
            id=item["id"],
            step_id=item["step_id"],
            title=item["title"],
            description=item["description"],
            order_no=item["order_no"],
            dependencies=json.loads(item["dependencies"] or "[]"),
            required_inputs=json.loads(item["required_inputs"] or "[]"),
            expected_outputs=json.loads(item["expected_outputs"] or "[]"),
            status=item["status"],
            information_type=item["information_type"],
            evidence_refs=json.loads(item["evidence_refs"] or "[]"),
            created_at=item["created_at"],
            updated_at=item["updated_at"],
        )
        for item in steps_rows
    ]
    parameters = []
    for item in param_rows:
        value = item["value"]
        if isinstance(value, str) and value.startswith("{"):
            try:
                parsed = json.loads(value)
                value = parsed if not isinstance(parsed, (list, dict)) else str(parsed)
            except json.JSONDecodeError:
                pass
        history = json.loads(item["history"] or "[]")
        parameters.append(ProtocolParamOut(
            id=item["id"],
            name=item["name"],
            original_value=item["original_value"],
            value=value,
            param_type=item["param_type"],
            unit=item["unit"],
            source_type=item["source_type"],
            page_number=item["page_number"],
            source_field=item["source_field"],
            evidence_id=item["evidence_id"],
            confirmed=bool(item["confirmed"]),
            modified_value=item["modified_value"],
            modified_at=item["modified_at"],
            history=history,
            note=item["note"],
            created_at=item["created_at"],
            updated_at=item["updated_at"],
        ))
    open_questions = [
        OpenQuestionOut(**item)
        for item in json.loads(row["open_questions"] or "[]")
    ]
    return ProtocolDetail(
        **_summary(connection, row).model_dump(),
        steps=steps,
        parameters=parameters,
        open_questions=open_questions,
        summary=row.get("summary"),
        source_fields=json.loads(row.get("source_fields") or "[]"),
        ai_configured=get_settings().llm_configured,
    )


def _build_anyway(load: dict, allow_heuristic_fallback: bool = True) -> Any:
    """Try Protocol Agent; if missing required facts or LLM fails, fall back to rule template."""
    draft = build_protocol_draft(load["fields"], load["evidence"])
    # If we have ZERO paper facts at all, there's nothing to meaningfully generate from.
    if not allow_heuristic_fallback and not load["evidence"]:
        return None
    return draft


def _persist_protocol(
    connection: Any,
    paper_id: str,
    name: str,
    draft: Any,
    operation_key: str | None = None,
) -> str:
    protocol_id = f"protocol_{uuid.uuid4().hex[:16]}"
    now = _now()
    connection.execute(
        """
        INSERT INTO protocols (
            id, paper_id, name, goal, status, version_no, latest_version_id,
            agent_method, ai_status, ai_error, operation_key,
            summary, open_questions, source_fields,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'generated', 1, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            protocol_id,
            paper_id,
            name[:120],
            draft.goal[:400],
            draft.agent_method,
            draft.ai_status,
            draft.ai_error,
            operation_key,
            draft.summary[:2000],
            json.dumps(
                [item.__dict__ for item in draft.open_questions],
                ensure_ascii=False,
            ),
            json.dumps(draft.source_fields, ensure_ascii=False),
            now,
            now,
        ),
    )
    # Build snapshot and initial version BEFORE persisting children so they are consistent.
    initial_snapshot = _snapshot(connection, protocol_id, draft.steps, draft.parameters)
    version_id = f"pv_{uuid.uuid4().hex[:16]}"
    connection.execute(
        """
        INSERT INTO protocol_versions (id, protocol_id, version_no, snapshot, message, created_at)
        VALUES (?, ?, 1, ?, ?, ?)
        """,
        (version_id, protocol_id, json.dumps(initial_snapshot, ensure_ascii=False), "初始生成", now),
    )
    connection.execute(
        "UPDATE protocols SET latest_version_id = ? WHERE id = ?",
        (version_id, protocol_id),
    )
    # Steps
    for step in draft.steps:
        connection.execute(
            """
            INSERT INTO protocol_steps (
                id, protocol_id, step_id, title, description, order_no,
                dependencies, required_inputs, expected_outputs,
                status, information_type, evidence_refs,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"ps_{uuid.uuid4().hex[:16]}",
                protocol_id,
                step.step_id,
                step.title[:200],
                step.description,
                step.order_no,
                json.dumps(step.dependencies, ensure_ascii=False),
                json.dumps(step.required_inputs, ensure_ascii=False),
                json.dumps(step.expected_outputs, ensure_ascii=False),
                step.status,
                step.information_type,
                json.dumps(step.evidence_refs, ensure_ascii=False),
                now,
                now,
            ),
        )
    # Parameters
    for index, param in enumerate(draft.parameters):
        connection.execute(
            """
            INSERT INTO protocol_parameters (
                id, protocol_id, name, original_value, value, param_type, unit, source_type,
                page_number, source_field, evidence_id,
                confirmed, modified_value, modified_at, history,
                created_at, updated_at, order_no
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL, '[]', ?, ?, ?)
            """,
            (
                f"pp_{uuid.uuid4().hex[:16]}",
                protocol_id,
                param.name,
                param.value,
                param.value,
                param.param_type,
                param.unit,
                param.source_type,
                param.page_number,
                param.source_field,
                param.evidence_id,
                now,
                now,
                index,
            ),
        )
    return protocol_id


def _snapshot(
    connection: Any,
    protocol_id: str,
    steps: list[StepDraft] | None = None,
    parameters: list[ParamDraft] | None = None,
) -> dict:
    protocol = _protocol_row(connection, protocol_id)
    if steps is None:
        steps = []
        for item in connection.execute(
            "SELECT * FROM protocol_steps WHERE protocol_id = ? ORDER BY order_no, rowid",
            (protocol_id,),
        ).fetchall():
            steps.append(StepDraft(
                step_id=item["step_id"],
                title=item["title"],
                description=item["description"] or "",
                order_no=item["order_no"],
                dependencies=json.loads(item["dependencies"] or "[]"),
                required_inputs=json.loads(item["required_inputs"] or "[]"),
                expected_outputs=json.loads(item["expected_outputs"] or "[]"),
                status=item["status"],
                information_type=item["information_type"],
                evidence_refs=json.loads(item["evidence_refs"] or "[]"),
            ))
    if parameters is None:
        parameter_items = [dict(item) for item in connection.execute(
            "SELECT * FROM protocol_parameters WHERE protocol_id = ? ORDER BY order_no, rowid, name",
            (protocol_id,),
        ).fetchall()]
        for item in parameter_items:
            for key in ("history",):
                item[key] = json.loads(item[key] or "[]")
    else:
        parameter_items = [
            {
                **item.__dict__,
                "original_value": item.value,
                "modified_value": None,
                "modified_at": None,
                "history": [],
                "note": None,
            }
            for item in parameters
        ]
    return {
        "name": protocol["name"],
        "goal": protocol["goal"],
        "status": protocol["status"],
        "steps": [item.__dict__ for item in steps],
        "parameters": parameter_items,
    }


@router.get("", response_model=ProtocolListResponse)
def list_protocols() -> ProtocolListResponse:
    with connect() as connection:
        rows = connection.execute(
            """
            SELECT p.*, pa.title AS paper_title
            FROM protocols p JOIN papers pa ON pa.id = p.paper_id
            ORDER BY p.updated_at DESC
            """
        ).fetchall()
        items = [
            _summary(connection, dict(row))
            for row in rows
        ]
    return ProtocolListResponse(items=items, total=len(items))


@router.post("/generate", response_model=ProtocolDetail, status_code=HTTP_201_CREATED)
def generate_protocol(payload: ProtocolGenerateRequest, *, use_llm: bool = True) -> ProtocolDetail:
    """Generate an experiment protocol from a parsed paper."""
    if payload.operation_key:
        with connect() as connection:
            existing = connection.execute(
                "SELECT id FROM protocols WHERE operation_key = ?", (payload.operation_key,)
            ).fetchone()
            if existing:
                return _detail(connection, _protocol_row(connection, existing["id"]))
    load = _validate_paper(payload.paper_id, require_parsed=True)
    # If previous heuristic draft had zero paper facts, raise; otherwise build.
    if not load["evidence"] and not any(
        meta.get("status") == "found" for meta in load["fields"].values()
    ):
        raise HTTPException(
            status_code=400,
            detail={
                "code": "no_extractable_facts",
                "message": "论文解析结果中没有可提取的事实字段或证据，无法生成有依据的协议。",
            },
        )
    draft = build_protocol_draft(load["fields"], load["evidence"], use_llm=use_llm)
    default_name = load["paper"]["title"] or payload.paper_id
    name = (payload.name or f"{default_name} 实验方案")[:120]
    with connect() as connection:
        if payload.operation_key:
            existing = connection.execute(
                "SELECT id FROM protocols WHERE operation_key = ?", (payload.operation_key,)
            ).fetchone()
            if existing:
                return _detail(connection, _protocol_row(connection, existing["id"]))
        protocol_id = _persist_protocol(connection, payload.paper_id, name, draft, payload.operation_key)
        row = _protocol_row(connection, protocol_id)
        return _detail(connection, row)


@router.get("/{protocol_id}", response_model=ProtocolDetail)
def get_protocol(protocol_id: str) -> ProtocolDetail:
    with connect() as connection:
        row = _protocol_row(connection, protocol_id)
        return _detail(connection, row)


@router.put("/{protocol_id}", response_model=ProtocolDetail)
def update_protocol(protocol_id: str, payload: ProtocolUpdateRequest) -> ProtocolDetail:
    with connect() as connection:
        row = _protocol_row(connection, protocol_id)
        updated_at = _now()
        if payload.name is not None:
            row["name"] = payload.name[:120]
        if payload.goal is not None:
            row["goal"] = payload.goal[:400]
        if payload.status is not None:
            row["status"] = payload.status
        connection.execute(
            """
            UPDATE protocols SET name = ?, goal = ?, status = ?, updated_at = ? WHERE id = ?
            """,
            (row["name"], row["goal"], row["status"], updated_at, protocol_id),
        )
        if payload.steps is not None:
            evidence_by_id = {
                item["id"]: dict(item)
                for item in connection.execute(
                    "SELECT * FROM paper_evidence WHERE paper_id = ?", (row["paper_id"],)
                ).fetchall()
            }
            _apply_step_updates(connection, protocol_id, payload.steps, updated_at, evidence_by_id)
        if payload.parameters is not None:
            _apply_param_updates(connection, protocol_id, payload.parameters, updated_at)
        row = _protocol_row(connection, protocol_id)
        return _detail(connection, row)


def _apply_step_updates(
    connection: Any,
    protocol_id: str,
    steps: list[dict],
    now: str,
    evidence_by_id: dict[str, dict],
) -> None:
    """Validate the merged graph and evidence before applying any step changes."""
    entries: dict[str, dict] = {}
    for item in connection.execute(
        "SELECT * FROM protocol_steps WHERE protocol_id = ?", (protocol_id,)
    ).fetchall():
        entries[item["id"]] = {
            "id": item["id"],
            "step_id": item["step_id"],
            "title": item["title"],
            "description": item["description"],
            "order_no": item["order_no"],
            "dependencies": json.loads(item["dependencies"] or "[]"),
            "required_inputs": json.loads(item["required_inputs"] or "[]"),
            "expected_outputs": json.loads(item["expected_outputs"] or "[]"),
            "status": item["status"],
            "information_type": item["information_type"],
            "evidence_refs": json.loads(item["evidence_refs"] or "[]"),
            "submitted": False,
        }

    for step in steps:
        database_id = step.get("id")
        title = step.get("title")
        if not isinstance(database_id, str) or not isinstance(title, str):
            continue
        existing = entries.get(database_id, {})
        business_id = str(step.get("step_id") or existing.get("step_id") or "").strip()
        if not business_id:
            business_id = f"manual_{uuid.uuid4().hex[:8]}"
        information_type = step.get("information_type", existing.get("information_type"))
        if information_type not in INFORMATION_TYPES:
            information_type = "derived_suggestion"
        entries[database_id] = {
            "id": database_id,
            "step_id": business_id,
            "title": title[:200],
            "description": step.get("description", existing.get("description")) or None,
            "order_no": step.get("order_no", existing.get("order_no", len(entries) + 1)),
            "dependencies": _coerce_list(step.get("dependencies", existing.get("dependencies"))),
            "required_inputs": _coerce_list(step.get("required_inputs", existing.get("required_inputs"))),
            "expected_outputs": _coerce_list(step.get("expected_outputs", existing.get("expected_outputs"))),
            "status": str(step.get("status") or existing.get("status") or "planned"),
            "information_type": information_type,
            "evidence_refs": _coerce_list(step.get("evidence_refs", existing.get("evidence_refs"))),
            "submitted": True,
            "is_new": not existing,
        }

    try:
        validate_workflow_steps([
            {"step_id": entry["step_id"], "dependencies": entry["dependencies"]}
            for entry in entries.values()
        ])
    except WorkflowValidationError as exc:
        raise HTTPException(status_code=400, detail={"code": exc.code, "message": exc.message}) from exc

    for entry in entries.values():
        if any(ref not in evidence_by_id for ref in entry["evidence_refs"]):
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_evidence", "message": f"步骤 {entry['step_id']} 包含不存在或跨论文的证据。"},
            )
        if entry["information_type"] == "paper_fact" and not entry["evidence_refs"]:
            entry["information_type"] = "derived_suggestion"

    for entry in entries.values():
        if not entry["submitted"]:
            continue
        values = (
            entry["title"], entry["description"], entry["order_no"],
            json.dumps(entry["dependencies"], ensure_ascii=False),
            json.dumps(entry["required_inputs"], ensure_ascii=False),
            json.dumps(entry["expected_outputs"], ensure_ascii=False),
            entry["status"], entry["information_type"],
            json.dumps(entry["evidence_refs"], ensure_ascii=False), now,
        )
        if entry.get("is_new"):
            connection.execute(
                """
                INSERT INTO protocol_steps (
                    id, protocol_id, step_id, title, description, order_no,
                    dependencies, required_inputs, expected_outputs,
                    status, information_type, evidence_refs, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (entry["id"], protocol_id, entry["step_id"], *values[:-1], now, now),
            )
        else:
            connection.execute(
                """
                UPDATE protocol_steps SET step_id = ?, title = ?, description = ?, order_no = ?,
                    dependencies = ?, required_inputs = ?, expected_outputs = ?,
                    status = ?, information_type = ?, evidence_refs = ?, updated_at = ?
                WHERE id = ?
                """,
                (entry["step_id"], *values, entry["id"]),
            )


def _apply_param_updates(connection: Any, protocol_id: str, parameters: list[dict], now: str) -> None:
    for param in parameters:
        param_id = param.get("id")
        if not isinstance(param_id, str):
            continue
        existing = connection.execute(
            "SELECT * FROM protocol_parameters WHERE id = ? AND protocol_id = ?",
            (param_id, protocol_id),
        ).fetchone()
        if existing is None:
            continue

        original_value = existing["original_value"]
        current_value = existing["value"]
        if "value" in param and param.get("value") != current_value:
            raw_value = param.get("value")
        elif "modified_value" in param and param.get("modified_value") != existing["modified_value"]:
            raw_value = param.get("modified_value")
            if raw_value is None:
                raw_value = original_value
        elif "value" in param:
            raw_value = param.get("value")
        else:
            raw_value = current_value
        value = None if raw_value is None else str(raw_value)[:1000]
        confirmed = bool(param.get("confirmed", existing["confirmed"]))
        note = param.get("note", existing["note"])
        changed_value = value != current_value
        history = json.loads(existing["history"] or "[]")
        if changed_value:
            action = "restore" if value == original_value else "edit"
            history.append({
                "at": now,
                "action": action,
                "from": current_value,
                "to": value,
                "note": note[:400] if isinstance(note, str) else None,
            })
        modified_value = value if value != original_value else None
        modified_at = now if changed_value and modified_value is not None else (
            existing["modified_at"] if modified_value is not None else None
        )
        connection.execute(
            """
            UPDATE protocol_parameters SET
                value = ?, confirmed = ?, note = ?, modified_value = ?, modified_at = ?,
                history = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                value,
                1 if confirmed else 0,
                note[:400] if isinstance(note, str) else None,
                modified_value,
                modified_at,
                json.dumps(history, ensure_ascii=False),
                now,
                param_id,
            ),
        )


def _coerce_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item)[:200] for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


@router.post("/{protocol_id}/versions", response_model=ProtocolVersionOut, status_code=HTTP_201_CREATED)
def save_version(protocol_id: str, payload: ProtocolSaveVersionRequest) -> ProtocolVersionOut:
    with connect() as connection:
        row = _protocol_row(connection, protocol_id)
        snapshot = _snapshot(connection, protocol_id)
        version_no = int(row["version_no"]) + 1
        now = _now()
        version_id = f"pv_{uuid.uuid4().hex[:16]}"
        connection.execute(
            """
            INSERT INTO protocol_versions (id, protocol_id, version_no, snapshot, message, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (version_id, protocol_id, version_no, json.dumps(snapshot, ensure_ascii=False),
             (payload.message[:240] if payload.message else "用户保存"), now),
        )
        connection.execute(
            """
            UPDATE protocols SET version_no = ?, latest_version_id = ?, updated_at = ? WHERE id = ?
            """,
            (version_no, version_id, now, protocol_id),
        )
        return ProtocolVersionOut(id=version_id, version_no=version_no, message=payload.message, created_at=now)


@router.get("/{protocol_id}/versions", response_model=list[ProtocolVersionOut])
def list_versions(protocol_id: str) -> list[ProtocolVersionOut]:
    with connect() as connection:
        _protocol_row(connection, protocol_id)
        rows = connection.execute(
            "SELECT * FROM protocol_versions WHERE protocol_id = ? ORDER BY version_no DESC",
            (protocol_id,),
        ).fetchall()
    return [
        ProtocolVersionOut(id=item["id"], version_no=item["version_no"],
                           message=item["message"], created_at=item["created_at"])
        for item in rows
    ]


@router.get("/{protocol_id}/export")
def export_protocol(protocol_id: str, format: str = "markdown") -> Response:
    with connect() as connection:
        row = _protocol_row(connection, protocol_id)
        detail = _detail(connection, row)
    safe_name = (detail.name or detail.paper_title or "protocol").replace("/", "-")[:60]
    # Content-Disposition must be ASCII-safe under latin-1 header encoding.
    ascii_name = "".join(ch if ord(ch) < 128 else "_" for ch in safe_name) or "protocol"
    if format in {"json", "application/json"}:
        body = json.dumps(detail.model_dump(mode="json"), ensure_ascii=False, indent=2)
        return Response(
            body,
            media_type="application/json;charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{ascii_name}.json"'},
        )
    # Default: markdown
    lines: list[str] = [
        f"# {detail.name}",
        "",
        f"**来源论文**：{detail.paper_title}  ",
        f"**生成方法**：{detail.agent_method}（AI {detail.ai_status}）  ",
        f"**版本**：v{detail.version_no}  ",
        f"**状态**：{detail.status}  ",
        f"**更新**：{detail.updated_at}  ",
        "",
        "## 实验目标",
        detail.goal or detail.summary or "—",
        "",
        "## 研究摘要",
        detail.summary or "—",
        "",
        "## 实验步骤",
    ]
    for step in detail.steps:
        lines.append(f"### {step.order_no}. {step.title}")
        lines.append("")
        lines.append(f"- 信息类型：`{step.information_type}`  ")
        lines.append(f"- 执行状态：`{step.status}`  ")
        if step.dependencies:
            lines.append(f"- 依赖步骤：{', '.join(step.dependencies)}  ")
        if step.evidence_refs:
            lines.append(f"- 原文证据（{len(step.evidence_refs)} 条）  ")
        if step.description:
            lines.append(f"- 说明：{step.description}  ")
        if step.required_inputs:
            lines.append(f"- 输入：{', '.join(step.required_inputs)}  ")
        if step.expected_outputs:
            lines.append(f"- 输出：{', '.join(step.expected_outputs)}  ")
        lines.append("")
    lines.extend(["## 参数表", "", "| 参数 | 当前有效值 | 论文/生成原值 | 类型 | 单位 | 来源 | 页码 | 备注 |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"])
    for param in detail.parameters:
        value = param.value if param.value is not None else "`unknown`"
        original = param.original_value if param.original_value is not None else "`unknown`"
        note = param.note or ""
        if param.confirmed:
            note = "已确认 " + note
        if param.modified_value is not None:
            note = f"{note} 用户修改值：{param.modified_value}".strip()
        lines.append(
            f"| {param.name} | {value} | {original} | {param.param_type} | {param.unit or ''} | "
            f"*{param.source_type}* | {param.page_number or '-'} | {note} |"
        )
    if detail.open_questions:
        lines.extend(["", "## 待确认问题", ""])
        for q in detail.open_questions:
            lines.append(f"- **[{q.field}]** {q.question}")
    body = "\n".join(lines)
    return Response(
        body,
        media_type="text/markdown;charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{ascii_name}.md"'},
    )


@router.delete("/{protocol_id}", status_code=HTTP_204_NO_CONTENT)
def delete_protocol(protocol_id: str) -> None:
    with connect() as connection:
        _protocol_row(connection, protocol_id)
        connection.execute("DELETE FROM protocols WHERE id = ?", (protocol_id,))


__all__ = ["router"]
