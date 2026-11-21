"""Append-only execution log for workflows and their nodes."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any

from ..db import connect


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def record_event(
    workflow_id: str,
    event_type: str,
    message: str,
    *,
    node_id: str | None = None,
    payload: dict[str, Any] | None = None,
    connection: Any | None = None,
) -> str:
    """Persist one workflow event and return its id."""
    event_id = f"wfe_{uuid.uuid4().hex[:16]}"
    values = (
        event_id,
        workflow_id,
        node_id,
        event_type,
        message,
        json.dumps(payload or {}, ensure_ascii=False),
        utc_now(),
    )
    sql = (
        "INSERT INTO workflow_events (id, workflow_id, node_id, event_type, message, payload, created_at)"
        " VALUES (?,?,?,?,?,?,?)"
    )
    if connection is not None:
        connection.execute(sql, values)
        return event_id
    with connect() as own:
        own.execute(sql, values)
        own.commit()
    return event_id


def list_events(workflow_id: str, limit: int = 500) -> list[dict[str, Any]]:
    with connect() as connection:
        rows = connection.execute(
            "SELECT * FROM workflow_events WHERE workflow_id = ? ORDER BY created_at ASC, rowid ASC LIMIT ?",
            (workflow_id, limit),
        ).fetchall()
    return [
        {
            "id": row["id"],
            "workflow_id": row["workflow_id"],
            "node_id": row["node_id"],
            "event_type": row["event_type"],
            "message": row["message"],
            "payload": _loads(row["payload"]),
            "created_at": row["created_at"],
        }
        for row in rows
    ]


def _loads(raw: str | None) -> Any:
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {}
