"""API surface for the multi-agent research workflow orchestrator."""

from __future__ import annotations

import json

from fastapi import APIRouter, HTTPException, Response, status

from ..schemas import (
    WorkflowApprovalRequest,
    WorkflowCreateRequest,
    WorkflowEventOut,
    WorkflowListResponse,
    WorkflowOut,
    WorkflowReportOut,
)
from ..services import workflow_engine
from ..services.workflow_engine import WorkflowNotFound
from ..services.workflow_events import list_events
from ..services.workflow_state import WorkflowStateError

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _state_error(exc: WorkflowStateError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": exc.code, "message": exc.message})


@router.post("", response_model=WorkflowOut, status_code=status.HTTP_201_CREATED)
def create_workflow(payload: WorkflowCreateRequest) -> WorkflowOut:
    try:
        workflow, created = workflow_engine.create_workflow(payload.model_dump())
    except WorkflowStateError as exc:
        raise _state_error(exc) from exc
    if payload.auto_start:
        try:
            workflow = workflow_engine.start_workflow(workflow["id"])
        except WorkflowStateError as exc:
            raise _state_error(exc) from exc
    return WorkflowOut(**workflow)


@router.get("", response_model=WorkflowListResponse)
def list_workflows(status_filter: str | None = None, limit: int = 100) -> WorkflowListResponse:
    return WorkflowListResponse(**workflow_engine.list_workflows(status=status_filter, limit=limit))


@router.get("/{workflow_id}", response_model=WorkflowOut)
def get_workflow(workflow_id: str) -> WorkflowOut:
    try:
        return WorkflowOut(**workflow_engine.get_workflow(workflow_id))
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "工作流不存在。"}) from exc


@router.post("/{workflow_id}/start", response_model=WorkflowOut)
def start_workflow(workflow_id: str) -> WorkflowOut:
    try:
        return WorkflowOut(**workflow_engine.start_workflow(workflow_id))
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "工作流不存在。"}) from exc
    except WorkflowStateError as exc:
        raise _state_error(exc) from exc


@router.post("/{workflow_id}/nodes/{node_ref}/retry", response_model=WorkflowOut)
def retry_node(workflow_id: str, node_ref: str) -> WorkflowOut:
    try:
        return WorkflowOut(**workflow_engine.retry_node(workflow_id, node_ref))
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "工作流不存在。"}) from exc
    except WorkflowStateError as exc:
        raise _state_error(exc) from exc


@router.post("/{workflow_id}/approvals", response_model=WorkflowOut)
def submit_approval(workflow_id: str, payload: WorkflowApprovalRequest) -> WorkflowOut:
    try:
        return WorkflowOut(**workflow_engine.submit_approval(workflow_id, payload.model_dump()))
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "工作流不存在。"}) from exc
    except WorkflowStateError as exc:
        raise _state_error(exc) from exc


@router.post("/{workflow_id}/cancel", response_model=WorkflowOut)
def cancel_workflow(workflow_id: str) -> WorkflowOut:
    try:
        return WorkflowOut(**workflow_engine.cancel_workflow(workflow_id))
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "工作流不存在。"}) from exc
    except WorkflowStateError as exc:
        raise _state_error(exc) from exc


@router.get("/{workflow_id}/events", response_model=list[WorkflowEventOut])
def get_events(workflow_id: str, limit: int = 500) -> list[WorkflowEventOut]:
    try:
        workflow_engine.get_workflow(workflow_id)
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "工作流不存在。"}) from exc
    return [WorkflowEventOut(**item) for item in list_events(workflow_id, limit=limit)]


@router.get("/{workflow_id}/report", response_model=WorkflowReportOut)
def get_report(workflow_id: str) -> WorkflowReportOut:
    try:
        return WorkflowReportOut(**workflow_engine.get_workflow_report(workflow_id))
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "工作流不存在。"}) from exc
    except WorkflowStateError as exc:
        raise _state_error(exc) from exc


@router.get("/{workflow_id}/report/export")
def export_report(workflow_id: str, format: str = "markdown") -> Response:
    try:
        report = workflow_engine.get_workflow_report(workflow_id)
    except WorkflowNotFound as exc:
        raise HTTPException(status_code=404, detail={"code": "not_found", "message": "工作流不存在。"}) from exc
    except WorkflowStateError as exc:
        raise _state_error(exc) from exc

    if format == "json":
        body = json.dumps(report, ensure_ascii=False, indent=2)
        media_type = "application/json"
        filename = f"research-workflow-{workflow_id}.json"
    else:
        body = workflow_engine.get_workflow_report_markdown(workflow_id)
        media_type = "text/markdown; charset=utf-8"
        filename = f"research-workflow-{workflow_id}.md"
    return Response(
        content=body,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
