"""Validate a per-run workflow against the closed stages of ADR 0013."""

from dataclasses import replace

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.task import TaskKind
from skm.modules.execution.domain.workflow.definition import (
    WORKFLOW_SCHEMA,
    StageType,
    WorkflowDefinition,
    applies_to_kind,
    parse_workflow,
)

__all__ = ["default_adhoc_workflow", "parse_adhoc_workflow"]

# These stages are reserved for the revision-backed plan engine.
_PLAN_STAGES = frozenset({StageType.PHASE_GATE, StageType.PLAN_ACCEPTANCE})


def default_adhoc_workflow() -> JsonObject:
    return {
        "schema": WORKFLOW_SCHEMA,
        "id": "adhoc-default",
        "version": "1.0.0",
        "applies_to": ["research"],
        "stage": [
            {"id": "prepare", "type": "prepare_environment"},
            {"id": "execute", "type": "agent_step", "role": "executor"},
            {"id": "accept", "type": "acceptance_gate"},
        ],
    }


def parse_adhoc_workflow(document: JsonValue, work_kind: str) -> WorkflowDefinition:
    workflow, violations = parse_workflow(document)
    if workflow is None:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "invalid ad hoc workflow",
            details={
                "violations": [
                    {"pointer": v.pointer, "code": v.reason, "message": v.message} for v in violations
                ]
            },
        )
    stages = tuple(stage for stage in workflow.stages if applies_to_kind(stage, TaskKind.ADHOC))
    if (
        work_kind not in workflow.applies_to
        or any(stage.type in _PLAN_STAGES for stage in workflow.stages)
        or not any(stage.type is StageType.AGENT_STEP and stage.role is RoleId.EXECUTOR for stage in stages)
    ):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "workflow must serve the requested work kind and include an ad hoc executor step",
        )
    return replace(workflow, stages=stages)
