"""Protocol Agent: convert paper analysis to a verifiable experiment protocol."""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from .llm_provider import LLMError, LLMProvider

INFORMATION_TYPES = ("paper_fact", "derived_suggestion", "unknown")

STEP_TEMPLATES = {
    "prerequisites": {
        "title": "环境与依赖核验",
        "description": "记录 Python、框架、CUDA、随机种子等运行环境版本，确保可复现。",
        "order_no": 1,
        "dependencies": [],
        "required_inputs": [],
        "expected_outputs": ["可复现的环境清单"],
    },
    "data_prepare": {
        "title": "数据集准备",
        "description": "下载或引用论文使用的公开数据集，记录版本与许可证。",
        "order_no": 2,
        "dependencies": ["prerequisites"],
        "required_inputs": ["dataset_identifier"],
        "expected_outputs": ["已下载数据目录"],
    },
    "data_preprocess": {
        "title": "数据预处理",
        "description": "完成清洗、划分、特征工程。优先使用论文报告的预处理流程。",
        "order_no": 3,
        "dependencies": ["data_prepare"],
        "required_inputs": ["raw_dataset"],
        "expected_outputs": ["train/val/test splits"],
    },
    "model_build": {
        "title": "模型构建",
        "description": "按论文描述搭建模型架构，记录层数、隐藏维度、激活函数。",
        "order_no": 4,
        "dependencies": ["data_preprocess"],
        "required_inputs": ["model_architecture_spec"],
        "expected_outputs": ["可实例化模型代码"],
    },
    "model_train": {
        "title": "模型训练",
        "description": "配置优化器、学习率、损失函数、最大轮数等训练参数。",
        "order_no": 5,
        "dependencies": ["model_build", "data_preprocess"],
        "required_inputs": ["model", "train_split"],
        "expected_outputs": ["训练日志、checkpoint"],
    },
    "model_validate": {
        "title": "模型验证与调参",
        "description": "用验证集监视指标变化，保存最优 checkpoint。",
        "order_no": 6,
        "dependencies": ["model_train"],
        "required_inputs": ["checkpoints", "val_split"],
        "expected_outputs": ["最优模型权重"],
    },
    "model_evaluate": {
        "title": "模型评估",
        "description": "在测试集上计算论文报告的评价指标，对比基线。",
        "order_no": 7,
        "dependencies": ["model_validate"],
        "required_inputs": ["best_model", "test_split"],
        "expected_outputs": ["完整评估指标表"],
    },
    "result_record": {
        "title": "结果记录",
        "description": "保存原始训练日志、指标曲线、checkpoint 路径、运行配置快照。",
        "order_no": 8,
        "dependencies": ["model_evaluate"],
        "required_inputs": ["评估结果"],
        "expected_outputs": ["可审计实验记录"],
    },
}


@dataclass
class StepDraft:
    step_id: str
    title: str
    description: str
    order_no: int
    dependencies: list[str]
    required_inputs: list[str]
    expected_outputs: list[str]
    status: str
    information_type: str
    evidence_refs: list[str]


@dataclass
class ParamDraft:
    name: str
    value: str | None
    param_type: str
    unit: str | None
    source_type: str
    page_number: int | None
    source_field: str | None
    evidence_id: str | None


@dataclass
class OpenQuestion:
    field: str
    question: str


@dataclass
class ProtocolDraft:
    goal: str
    summary: str
    steps: list[StepDraft]
    parameters: list[ParamDraft]
    open_questions: list[OpenQuestion]
    source_fields: list[str]
    agent_method: str
    ai_status: str
    ai_error: str | None


def _validate_step(step: dict[str, Any]) -> StepDraft | None:
    step_id = step.get("step_id")
    title = step.get("title")
    if not isinstance(step_id, str) or not isinstance(title, str):
        return None
    info_type = step.get("information_type", "derived_suggestion")
    if info_type not in INFORMATION_TYPES:
        info_type = "derived_suggestion"
    try:
        order_no = int(step.get("order") or step.get("order_no") or 0)
    except (TypeError, ValueError):
        order_no = 0
    return StepDraft(
        step_id=step_id,
        title=title,
        description=str(step.get("description") or "")[:4000],
        order_no=order_no,
        dependencies=_as_string_list(step.get("dependencies")),
        required_inputs=_as_string_list(step.get("required_inputs") or step.get("inputs")),
        expected_outputs=_as_string_list(step.get("expected_outputs") or step.get("outputs")),
        status="planned",
        information_type=info_type,
        evidence_refs=_as_string_list(step.get("evidence_refs") or step.get("evidence")),
    )


def _as_string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item)[:200] for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def normalize_information_type(value: object) -> str:
    return str(value) if value in INFORMATION_TYPES else "derived_suggestion"


class WorkflowValidationError(ValueError):
    """A stable domain error returned for invalid workflow graphs."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


def validate_workflow_steps(steps: list[dict]) -> None:
    """Validate business ids and dependencies with Kahn's topological algorithm."""
    graph: dict[str, list[str]] = {}
    for step in steps:
        step_id = str(step.get("step_id") or "").strip()
        if not step_id:
            raise WorkflowValidationError("missing_step_id", "步骤缺少稳定的 step_id。")
        if step_id in graph:
            raise WorkflowValidationError("duplicate_step", f"步骤标识重复：{step_id}")
        graph[step_id] = []

    for step in steps:
        step_id = str(step["step_id"]).strip()
        dependencies = step.get("dependencies") or []
        if not isinstance(dependencies, list):
            raise WorkflowValidationError("invalid_dependency", f"步骤 {step_id} 的依赖格式无效。")
        for dependency in dependencies:
            dependency_id = str(dependency).strip()
            if dependency_id == step_id:
                raise WorkflowValidationError("self_dependency", f"步骤 {step_id} 不能依赖自身。")
            if dependency_id not in graph:
                raise WorkflowValidationError(
                    "missing_dependency", f"步骤 {step_id} 依赖不存在的步骤 {dependency_id}。"
                )
            graph[step_id].append(dependency_id)

    indegree = {step_id: len(dependencies) for step_id, dependencies in graph.items()}
    dependents = {step_id: [] for step_id in graph}
    for step_id, dependencies in graph.items():
        for dependency in dependencies:
            dependents[dependency].append(step_id)
    queue = [step_id for step_id, degree in indegree.items() if degree == 0]
    visited = 0
    while queue:
        current = queue.pop(0)
        visited += 1
        for dependent in dependents[current]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                queue.append(dependent)
    if visited != len(graph):
        raise WorkflowValidationError("dependency_cycle", "实验步骤存在循环依赖，无法保存。")


def _validate_param(raw: dict[str, Any]) -> ParamDraft | None:
    name = raw.get("name")
    if not isinstance(name, str) or not name.strip():
        return None
    source_type = raw.get("source_type", "unknown")
    if source_type not in INFORMATION_TYPES:
        source_type = "unknown"
    try:
        page = int(raw["page_number"]) if raw.get("page_number") is not None else None
    except (TypeError, ValueError):
        page = None
    return ParamDraft(
        name=name.strip(),
        value=str(raw.get("value")) if raw.get("value") is not None else None,
        param_type=str(raw.get("param_type") or "string"),
        unit=str(raw.get("unit")) if raw.get("unit") else None,
        source_type=source_type,
        page_number=page,
        source_field=str(raw.get("source_field")) if raw.get("source_field") else None,
        evidence_id=str(raw.get("evidence_id")) if raw.get("evidence_id") else None,
    )


def _validate_open_questions(raw: Any) -> list[OpenQuestion]:
    if not isinstance(raw, list):
        return []
    questions: list[OpenQuestion] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        field = str(item.get("field") or "")
        question = str(item.get("question") or item.get("text") or "")
        if question:
            questions.append(OpenQuestion(field=field[:80], question=question[:800]))
    return questions


def build_heuristic_draft(paper_fields: dict[str, dict], paper_evidence: list[dict]) -> ProtocolDraft:
    """Rule-based protocol, always safe to run even without LLM."""
    title = paper_fields.get("title", {}).get("value") or "该论文"
    evidence_by_field: dict[str, list[dict]] = {}
    for item in paper_evidence:
        evidence_by_field.setdefault(item["field"], []).append(item)

    fields_with_facts = [
        key for key, meta in paper_fields.items()
        if meta.get("status") == "found" and meta.get("value") and evidence_by_field.get(key)
    ]
    field_values = {key: (meta.get("value") or "") for key, meta in paper_fields.items()}

    open_questions: list[OpenQuestion] = []
    for key in ("datasets", "hyperparameters", "experiment_setup"):
        meta = paper_fields.get(key, {})
        if meta.get("status") != "found" or not meta.get("value"):
            open_questions.append(OpenQuestion(field=key, question=f"论文未明确给出 {key}，需要实验前补充确认。"))

    # Steps: generate template steps, assigning information_type and evidence_refs from paper fields.
    step_fields = {
        "prerequisites": ["title"],
        "data_prepare": ["datasets"],
        "data_preprocess": ["datasets", "experiment_setup"],
        "model_build": ["model_architecture", "method"],
        "model_train": ["hyperparameters", "experiment_setup"],
        "model_validate": ["metrics", "experiment_setup"],
        "model_evaluate": ["metrics", "conclusions"],
        "result_record": [],
    }
    steps: list[StepDraft] = []
    for step_id, field_keys in step_fields.items():
        template = STEP_TEMPLATES[step_id]
        refs: list[str] = []
        info_type = "unknown"
        has_paper_fact = False
        for key in field_keys:
            if paper_fields.get(key, {}).get("status") == "found":
                has_paper_fact = True
                for ev in evidence_by_field.get(key, []):
                    refs.append(ev["id"])
        if has_paper_fact and refs:
            info_type = "paper_fact"
        elif field_keys:
            info_type = "derived_suggestion"
        else:
            info_type = "derived_suggestion"
        steps.append(StepDraft(
            step_id=step_id,
            title=template["title"],
            description=template["description"],
            order_no=template["order_no"],
            dependencies=template["dependencies"],
            required_inputs=template["required_inputs"],
            expected_outputs=template["expected_outputs"],
            status="planned",
            information_type=info_type,
            evidence_refs=sorted(set(refs)),
        ))

    parameters = _extract_parameters_from_fields(paper_fields, evidence_by_field)

    summary_parts = []
    for label, key in [("目标", "research_question"), ("方法", "method"), ("指标", "metrics")]:
        value = field_values.get(key)
        if value:
            summary_parts.append(f"{label}: {value[:160]}")
    goal = field_values.get("research_question") or f"复现《{title}》的核心实验。"

    return ProtocolDraft(
        goal=goal[:400],
        summary="；".join(summary_parts) or "该方案由规则驱动生成，请逐项校对参数与证据。",
        steps=steps,
        parameters=parameters,
        open_questions=open_questions,
        source_fields=fields_with_facts,
        agent_method="rule_template",
        ai_status="unconfigured",
        ai_error=None,
    )


def _extract_parameters_from_fields(
    paper_fields: dict[str, dict],
    evidence_by_field: dict[str, list[dict]],
) -> list[ParamDraft]:
    params: list[ParamDraft] = []
    hyper_value = paper_fields.get("hyperparameters", {}).get("value")
    setup_value = paper_fields.get("experiment_setup", {}).get("value")
    for chunk_name, chunk in (("hyperparameters", hyper_value), ("experiment_setup", setup_value)):
        if not chunk:
            continue
        evidence = evidence_by_field.get(chunk_name, [])
        for line in [segment.strip() for segment in chunk.replace(";", "\n").replace("，", "\n").splitlines() if segment.strip()]:
            if ":" in line:
                name, _, value = line.partition(":")
            elif "=" in line:
                name, _, value = line.partition("=")
            else:
                continue
            name = name.strip(" -•*·")
            value = value.strip(" .。,，")
            if not name or len(name) > 80:
                continue
            page = evidence[0]["page"] if evidence else None
            eid = evidence[0]["id"] if evidence else None
            params.append(ParamDraft(
                name=name,
                value=value or None,
                param_type=_guess_param_type(value),
                unit=None,
                source_type="paper_fact" if evidence and paper_fields.get(chunk_name, {}).get("status") == "found" else "derived_suggestion",
                page_number=page,
                source_field=chunk_name,
                evidence_id=eid,
            ))
    # Also inject unknown-but-important placeholders the paper likely omitted.
    for missing_name, question in [
        ("随机种子", "论文未声明随机种子，建议固定后复现。"),
        ("学习率", "论文未报告学习率，需在训练阶段补充。"),
        ("最大训练轮数", "论文未报告训练轮数，需确认 early stopping 或固定 epoch。"),
    ]:
        if any(param.name == missing_name for param in params):
            continue
        params.append(ParamDraft(
            name=missing_name,
            value=None,
            param_type="unknown",
            unit=None,
            source_type="unknown",
            page_number=None,
            source_field=None,
            evidence_id=None,
        ))
    return params


def _guess_param_type(value: str | None) -> str:
    if value is None or value == "":
        return "unknown"
    if value.replace(".", "", 1).replace("-", "", 1).isdigit():
        return "number"
    if value.lower() in {"true", "false"}:
        return "boolean"
    if "," in value or "、" in value:
        return "list"
    return "string"


SYSTEM_PROMPT = """你是一个严格的实验协议生成 Agent。输入是 ReproLab AI 已经提取好的论文结构化字段和页码级证据，输出是一个 JSON 对象，结构如下：
{
  "goal": "一句话目标",
  "summary": "两三句摘要",
  "steps": [
    {
      "step_id": "step_a_unique_id",
      "title": "...",
      "description": "...",
      "order": 1,
      "dependencies": ["step_id_1", "step_id_2"],
      "required_inputs": ["..."],
      "expected_outputs": ["..."],
      "information_type": "paper_fact | derived_suggestion | unknown",
      "evidence_refs": ["evidence_id_from_input"]
    }
  ],
  "parameters": [
    {
      "name": "参数名",
      "value": "值或 null",
      "param_type": "number | string | boolean | list | unknown",
      "unit": "可选",
      "source_type": "paper_fact | derived_suggestion | unknown",
      "page_number": 1,
      "source_field": "hyperparameters",
      "evidence_id": "evidence_id_from_input"
    }
  ],
  "open_questions": [{"field": "hyperparameters", "question": "..."}]
}
绝对规则：
- evidence_refs 中的每个 id 必须来自输入的 evidence_ids 字段；不存在的 id 一律禁止使用。
- information_type 只能是三个枚举。从输入 evidence 可追溯的才能标 paper_fact；AI 建议或规则推断标 derived_suggestion；论文完全没讲清楚的标 unknown。
- 不得编造随机种子、学习率、epoch 等数值；找不到就把 value 设为 null 并把 source_type 标成 unknown。
- 输出 JSON 即可，不要多余文字。"""


def _build_user_prompt(paper_fields: dict[str, dict], paper_evidence: list[dict]) -> str:
    fields_text = "\n".join(
        f"- {key} [{meta.get('status')}] {meta.get('value') or ''}".strip()
        for key, meta in paper_fields.items()
    )
    evidence_text = "\n".join(
        f"- id={item['id']} field={item['field']} page={item['page']} quote={item['quote'][:200]}"
        for item in paper_evidence
    )
    evidence_ids = [item["id"] for item in paper_evidence]
    return (
        "基于这篇已解析的论文生成实验方案。严格只使用下列 evidence_ids：\n"
        f"evidence_ids: {json.dumps(evidence_ids, ensure_ascii=False)}\n\n"
        f"论文字段：\n{fields_text}\n\n"
        f"页码证据：\n{evidence_text or '（无）'}"
    )


def _resolve_evidence_ids(
    refs: list[str],
    allowed_ids: set[str],
    paper_evidence: list[dict],
) -> list[str]:
    """Drop refs that do not actually belong to this paper's evidence set."""
    valid = [ref for ref in refs if ref in allowed_ids]
    if valid:
        return valid
    # Fall back to page-matching if evidence_id was not faithfully echoed.
    pages = [item["page"] for item in paper_evidence if item["id"] in allowed_ids]
    return []


def build_protocol_draft(
    paper_fields: dict[str, dict],
    paper_evidence: list[dict],
    *,
    use_llm: bool = True,
) -> ProtocolDraft:
    heuristic = build_heuristic_draft(paper_fields, paper_evidence)
    if not use_llm:
        heuristic.ai_status = "not_used"
        return heuristic
    provider = LLMProvider()
    if not provider.configured:
        return heuristic

    try:
        payload = provider.complete_json(
            SYSTEM_PROMPT,
            _build_user_prompt(paper_fields, paper_evidence),
        )
        if not isinstance(payload.get("steps"), list) or not isinstance(payload.get("parameters"), list):
            raise LLMError("LLM 输出缺少有效的 steps/parameters 数组。")

        allowed_ids = {item["id"] for item in paper_evidence}
        evidence_by_id = {item["id"]: item for item in paper_evidence}
        llm_steps: dict[str, StepDraft] = {}
        for raw in payload["steps"]:
            if not isinstance(raw, dict):
                raise LLMError("LLM 输出包含非对象步骤。")
            step = _validate_step(raw)
            if step is None:
                raise LLMError("LLM 输出步骤缺少 step_id 或 title。")
            step.information_type = normalize_information_type(step.information_type)
            step.evidence_refs = _resolve_evidence_ids(step.evidence_refs, allowed_ids, paper_evidence)
            if step.information_type == "paper_fact" and not step.evidence_refs:
                step.information_type = "derived_suggestion"
            llm_steps[step.step_id] = step

        merged_steps: list[StepDraft] = []
        for template in heuristic.steps:
            llm_step = llm_steps.pop(template.step_id, None)
            if llm_step is None:
                merged_steps.append(template)
                continue
            if not llm_step.evidence_refs:
                llm_step.evidence_refs = template.evidence_refs
            if llm_step.information_type == "paper_fact" and not llm_step.evidence_refs:
                llm_step.information_type = "derived_suggestion"
            if not llm_step.description:
                llm_step.description = template.description
            merged_steps.append(llm_step)
        merged_steps.extend(llm_steps.values())
        merged_steps.sort(key=lambda step: step.order_no)
        validate_workflow_steps([
            {"step_id": step.step_id, "dependencies": step.dependencies}
            for step in merged_steps
        ])

        parameters: list[ParamDraft] = []
        seen_names: set[str] = set()
        for raw in payload["parameters"]:
            if not isinstance(raw, dict):
                raise LLMError("LLM 输出包含非对象参数。")
            param = _validate_param(raw)
            if not param or param.name in seen_names:
                continue
            if param.source_type == "unknown":
                param.value = None
                param.evidence_id = None
                param.page_number = None
                param.source_field = None
                param.param_type = "unknown"
            else:
                if param.evidence_id not in allowed_ids:
                    param.evidence_id = None
                if param.source_type == "paper_fact" and param.evidence_id is None:
                    param.source_type = "derived_suggestion"
                evidence = evidence_by_id.get(param.evidence_id or "")
                param.page_number = evidence["page"] if evidence else None
                param.source_field = evidence["field"] if evidence else param.source_field
            parameters.append(param)
            seen_names.add(param.name)
        for param in heuristic.parameters:
            if param.name not in seen_names:
                parameters.append(param)

        open_questions = _validate_open_questions(payload.get("open_questions")) or heuristic.open_questions
        return ProtocolDraft(
            goal=str(payload.get("goal"))[:400] if payload.get("goal") else heuristic.goal,
            summary=str(payload.get("summary"))[:800] if payload.get("summary") else heuristic.summary,
            steps=merged_steps,
            parameters=parameters,
            open_questions=open_questions,
            source_fields=heuristic.source_fields,
            agent_method="hybrid",
            ai_status="success",
            ai_error=None,
        )
    except (LLMError, TypeError, ValueError, AttributeError) as exc:
        heuristic.ai_status = "failed"
        heuristic.ai_error = str(exc)
        heuristic.agent_method = "hybrid_fallback"
        return heuristic


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"
