"""Node templates for the four-agent research workflow.

Each template declares its agent, dependency edges, whether it is optional for a
given workflow type, and whether it is a human approval gate. The registry is the
single source of truth used both to materialise a workflow's nodes and to render
the dependency graph in the UI.
"""

from __future__ import annotations

from dataclasses import dataclass

from .workflow_state import WORKFLOW_TYPES


@dataclass(frozen=True)
class NodeTemplate:
    key: str
    agent_name: str
    title: str
    order_no: int
    depends_on: tuple[str, ...]
    requires_approval: bool = False
    optional: bool = False
    description: str = ""


NODE_TEMPLATES: tuple[NodeTemplate, ...] = (
    NodeTemplate(
        key="paper_parse",
        agent_name="Paper Agent",
        title="论文解析与证据抽取",
        order_no=1,
        depends_on=(),
        optional=True,
        description="复用 Paper Agent 抽取结构化字段与页码级证据；已解析论文直接复用结果。",
    ),
    NodeTemplate(
        key="protocol_generate",
        agent_name="Protocol Agent",
        title="生成实验方案",
        order_no=2,
        depends_on=("paper_parse",),
        optional=True,
        description="复用 Protocol Agent 从论文证据生成实验方案；不修改论文原始数据。",
    ),
    NodeTemplate(
        key="protocol_approve",
        agent_name="Human Review",
        title="实验方案人工确认",
        order_no=3,
        depends_on=("protocol_generate",),
        requires_approval=True,
        description="实验方案正式采用前必须由研究者确认；拒绝会记录审核事件并保留原方案。",
    ),
    NodeTemplate(
        key="data_audit",
        agent_name="Data Guardian",
        title="实验数据确定性审计",
        order_no=4,
        depends_on=("protocol_approve",),
        optional=True,
        description="复用 Data Guardian 六大确定性规则审计；复用已有审计结果避免重复创建。",
    ),
    NodeTemplate(
        key="audit_approve",
        agent_name="Human Review",
        title="高风险审计结果确认",
        order_no=5,
        depends_on=("data_audit",),
        requires_approval=True,
        optional=True,
        description="仅在存在 critical/high 风险时要求人工处置；无高风险自动通过并记录原因。",
    ),
    NodeTemplate(
        key="experiment_analyze",
        agent_name="Insight Agent",
        title="实验指标分析与科研洞察",
        order_no=6,
        depends_on=("audit_approve",),
        optional=False,
        description="复用 Experiment Insight 对比与洞察引擎；所有指标由 Python 确定性计算。",
    ),
    NodeTemplate(
        key="report_publish",
        agent_name="Human Review",
        title="统一科研报告本地定稿",
        order_no=7,
        depends_on=("experiment_analyze",),
        requires_approval=True,
        description="汇总论文证据、协议、审计、指标与洞察；本地定稿前必须人工确认，不上传外部服务。",
    ),
)


def templates_for(workflow_type: str = "full_reproduction") -> list[NodeTemplate]:
    """Return node templates valid for the requested workflow type."""
    if workflow_type not in WORKFLOW_TYPES:
        raise ValueError(f"未知工作流类型：{workflow_type}")
    if workflow_type == "analysis_only":
        # Analysis-only still cannot skip the actual metric analysis or the final report.
        return [
            NodeTemplate(
                **{
                    **template.__dict__,
                    "optional": template.key in {"paper_parse", "protocol_generate", "protocol_approve", "data_audit", "audit_approve"},
                }
            )
            for template in NODE_TEMPLATES
        ]
    return list(NODE_TEMPLATES)


def template_map() -> dict[str, NodeTemplate]:
    return {template.key: template for template in NODE_TEMPLATES}
