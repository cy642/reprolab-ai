"""Workflow and node state constants plus transition guards.

The orchestrator is deliberately explicit about legal transitions so that an
illegal request (e.g. retrying a completed node) fails loudly instead of
silently producing inconsistent state.
"""

from __future__ import annotations

WORKFLOW_STATUSES = ("pending", "running", "waiting_approval", "completed", "failed", "cancelled")
NODE_STATUSES = ("pending", "running", "waiting_approval", "completed", "failed", "skipped")

TERMINAL_WORKFLOW_STATUSES = ("completed", "failed", "cancelled")
NODE_SATISFIED_STATUSES = ("completed", "skipped")

WORKFLOW_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"running", "cancelled", "failed"},
    "running": {"waiting_approval", "completed", "failed", "cancelled"},
    "waiting_approval": {"running", "failed", "cancelled"},
    "completed": set(),
    "failed": {"running", "cancelled"},
    "cancelled": set(),
}

NODE_TRANSITIONS: dict[str, set[str]] = {
    "pending": {"running", "waiting_approval", "skipped", "failed"},
    "running": {"completed", "failed", "skipped"},
    "waiting_approval": {"completed", "failed", "skipped"},
    "completed": set(),
    "failed": {"pending", "skipped"},
    "skipped": set(),
}

WORKFLOW_TYPES = ("full_reproduction", "analysis_only")


class WorkflowStateError(ValueError):
    """Raised when a requested transition is not legal for the current state."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class WorkflowInputError(ValueError):
    """Raised by an agent handler when a required business input is missing."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def assert_workflow_status(current: str, target: str) -> None:
    if current == target:
        return
    if target not in WORKFLOW_TRANSITIONS.get(current, set()):
        raise WorkflowStateError(
            "illegal_workflow_transition",
            f"工作流不能从 {current} 变为 {target}。",
        )


def assert_node_status(current: str, target: str) -> None:
    if current == target:
        return
    if target not in NODE_TRANSITIONS.get(current, set()):
        raise WorkflowStateError(
            "illegal_node_transition",
            f"节点不能从 {current} 变为 {target}。",
        )
