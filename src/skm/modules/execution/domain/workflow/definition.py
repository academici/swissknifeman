"""Closed workflow declarations (execution §5.2-§5.3) and their pure parser.

A workflow is versioned data: stage types, parameters, outcome handlers, roles and predicates are closed sets
and nothing in a definition is evaluated as code. ``parse_workflow`` reads a ``urn:skm:execution:workflow:v1``
document (TOML -> JSON) on its own, so an unknown stage type, role or predicate is refused even without the
schema, and adds the cross-stage rules a JSON Schema cannot state: unique stage ids, roles pinned by
``requires_roles``, parameters and handlers that fit their stage type, handlers whose target stages serve
every task kind of the source stage and stages that apply to at least one task kind behind a
``prepare_environment``. An explicit null is a defect, never an absent field. Defects are reported, never
fixed.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final, Literal, cast

from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.task import GATE_KINDS, WORK_KINDS, TaskKind
from skm.modules.execution.domain.workflow.predicates import (
    Condition,
    ConditionDefect,
    WorkKind,
    parse_condition,
)

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.task import Task

__all__ = [
    "AGENT_STAGE_ROLES",
    "DEFAULT_FOR_KINDS",
    "STAGE_TYPE_KINDS",
    "WORKFLOW_SCHEMA",
    "OnOutcome",
    "StageDefinition",
    "StageParams",
    "StageType",
    "WorkflowDefinition",
    "WorkflowViolation",
    "applicable_kinds",
    "applies_to_kind",
    "parse_workflow",
]

WORKFLOW_SCHEMA: Final = "urn:skm:execution:workflow:v1"
_WORKFLOW_ID = re.compile(r"[a-z0-9][a-z0-9-]{1,62}")
_VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
_STAGE_ID = re.compile(r"[a-z][a-z0-9_]{0,31}")
_PROFILE = re.compile(r"[a-z][a-z0-9-]{1,60}")
_TITLE_MAX = 200
_DESCRIPTION_MAX = 2000
_RETRIES_MAX = 5


class StageType(StrEnum):
    PREPARE_ENVIRONMENT = "prepare_environment"
    AGENT_STEP = "agent_step"
    RUN_CHECKS = "run_checks"
    AGENT_REVIEW = "agent_review"
    ADVISOR_CONSULT = "advisor_consult"
    HUMAN_GATE = "human_gate"
    ACCEPTANCE_GATE = "acceptance_gate"
    PHASE_GATE = "phase_gate"
    PLAN_ACCEPTANCE = "plan_acceptance"
    INTEGRATE = "integrate"


# Roles a stage type may run; stage types outside this map run no role (execution §5.2).
AGENT_STAGE_ROLES: Final[Mapping[StageType, frozenset[RoleId]]] = {
    StageType.AGENT_STEP: frozenset(
        {RoleId.SCOUT, RoleId.EXECUTOR, RoleId.TRIAGER, RoleId.RESEARCHER, RoleId.REGISTRAR}
    ),
    StageType.AGENT_REVIEW: frozenset({RoleId.REVIEWER}),
    StageType.ADVISOR_CONSULT: frozenset({RoleId.ADVISOR}),
}
# The single role implied when the stage omits ``role``.
_IMPLIED_ROLE: Final = {StageType.AGENT_REVIEW: RoleId.REVIEWER, StageType.ADVISOR_CONSULT: RoleId.ADVISOR}

DEFAULT_FOR_KINDS: Final = WORK_KINDS
# Gate stage types apply to their own task kinds whatever ``for_kinds`` says (§5.3).
STAGE_TYPE_KINDS: Final[Mapping[StageType, frozenset[TaskKind]]] = {
    StageType.PHASE_GATE: frozenset({TaskKind.ITEM_GATE, TaskKind.PHASE_GATE, TaskKind.GROUP_REVIEW}),
    StageType.PLAN_ACCEPTANCE: frozenset({TaskKind.PLAN_ACCEPTANCE}),
}

type BaselineStrategy = Literal["integration_branch_head", "revision_pinned", "gate_range", "review_request"]
type ChecksScope = Literal["task", "gate", "rerun_after_integration"]
type AuditScope = Literal["corrected", "full", "range"]
type PushMode = Literal["none", "intent"]
type GateKind = Literal["manual_check", "approval"]
type Coverage = Literal["required", "advisory"]

_WORKER_STAGES: Final = frozenset(
    {
        StageType.PREPARE_ENVIRONMENT,
        StageType.AGENT_STEP,
        StageType.RUN_CHECKS,
        StageType.AGENT_REVIEW,
        StageType.ADVISOR_CONSULT,
        StageType.INTEGRATE,
    }
)
_AGENT_STAGES: Final = frozenset(AGENT_STAGE_ROLES)
# Parameter -> (allowed values or None for a typed value, stage types that read it).
_PARAMS: Final[Mapping[str, tuple[frozenset[str] | None, frozenset[StageType]]]] = {
    "baseline_strategy": (
        frozenset({"integration_branch_head", "revision_pinned", "gate_range", "review_request"}),
        frozenset({StageType.PREPARE_ENVIRONMENT}),
    ),
    "scope": (frozenset({"task", "gate", "rerun_after_integration"}), frozenset({StageType.RUN_CHECKS})),
    "audit_scope": (frozenset({"corrected", "full", "range"}), frozenset({StageType.AGENT_REVIEW})),
    "reviewer_with_fix": (None, frozenset({StageType.AGENT_REVIEW})),
    "profile": (None, _AGENT_STAGES),
    "push": (frozenset({"none", "intent"}), frozenset({StageType.INTEGRATE})),
    "gate_kind": (frozenset({"manual_check", "approval"}), frozenset({StageType.HUMAN_GATE})),
    "blocks_next_phase": (None, frozenset({StageType.PHASE_GATE})),
    "coverage": (frozenset({"required", "advisory"}), frozenset({StageType.PLAN_ACCEPTANCE})),
    "retries": (None, _WORKER_STAGES),
}
# Outcome handler -> (allowed values, stage types that produce the outcome).
_HANDLERS: Final[Mapping[str, tuple[frozenset[str], frozenset[StageType]]]] = {
    "checks_failed": (frozenset({"rework", "escalate", "fail"}), frozenset({StageType.RUN_CHECKS})),
    "checks_error": (
        frozenset({"retry_once_then_escalate", "escalate", "fail"}),
        frozenset({StageType.RUN_CHECKS}),
    ),
    "verdict_attention": (frozenset({"triage", "ask_owner"}), frozenset({StageType.AGENT_REVIEW})),
    "verdict_red": (frozenset({"triage", "escalate"}), frozenset({StageType.AGENT_REVIEW})),
    "result_invalid": (frozenset({"retry_then_escalate", "escalate", "skip_if_optional"}), _AGENT_STAGES),
    "conflict": (frozenset({"integration_task", "escalate"}), frozenset({StageType.INTEGRATE})),
}
# Handler value -> role of the agent_step stage that carries it out for the same task (§5.1).
_HANDLER_TARGETS: Final[Mapping[tuple[str, str], RoleId]] = {
    ("checks_failed", "rework"): RoleId.EXECUTOR,
    ("verdict_attention", "triage"): RoleId.TRIAGER,
    ("verdict_red", "triage"): RoleId.TRIAGER,
}
_WORKFLOW_FIELDS: Final = frozenset(
    {"schema", "id", "version", "title", "description", "applies_to", "requires_roles", "stage"}
)
_STAGE_FIELDS: Final = frozenset(
    {"id", "type", "role", "optional", "for_kinds", "when", "skip_when", "params", "on"}
)


@dataclass(frozen=True, slots=True)
class StageParams:
    """Declarative stage parameters; each applies to the stage types of §5.2 only."""

    baseline_strategy: BaselineStrategy | None = None
    scope: ChecksScope | None = None
    audit_scope: AuditScope | None = None
    reviewer_with_fix: bool | None = None
    profile: str | None = None
    push: PushMode | None = None
    gate_kind: GateKind | None = None
    blocks_next_phase: bool | None = None
    coverage: Coverage | None = None
    retries: int | None = None

    def as_json(self) -> dict[str, JsonValue]:
        """Declared parameters only, in declaration order (``RunStage.params`` base)."""
        values: dict[str, JsonValue] = {
            "baseline_strategy": self.baseline_strategy,
            "scope": self.scope,
            "audit_scope": self.audit_scope,
            "reviewer_with_fix": self.reviewer_with_fix,
            "profile": self.profile,
            "push": self.push,
            "gate_kind": self.gate_kind,
            "blocks_next_phase": self.blocks_next_phase,
            "coverage": self.coverage,
            "retries": self.retries,
        }
        return {name: value for name, value in values.items() if value is not None}


@dataclass(frozen=True, slots=True)
class OnOutcome:
    """Outcome handlers; an absent handler takes the engine default of §5.1."""

    checks_failed: Literal["rework", "escalate", "fail"] | None = None
    checks_error: Literal["retry_once_then_escalate", "escalate", "fail"] | None = None
    verdict_attention: Literal["triage", "ask_owner"] | None = None
    verdict_red: Literal["triage", "escalate"] | None = None
    result_invalid: Literal["retry_then_escalate", "escalate", "skip_if_optional"] | None = None
    conflict: Literal["integration_task", "escalate"] | None = None


@dataclass(frozen=True, slots=True)
class StageDefinition:
    id: str
    type: StageType
    for_kinds: frozenset[TaskKind]
    role: RoleId | None
    optional: bool
    params: StageParams
    when: Condition | None
    skip_when: Condition | None
    on: OnOutcome


@dataclass(frozen=True, slots=True)
class WorkflowDefinition:
    id: str
    version: str
    title: str
    description: str
    applies_to: tuple[WorkKind, ...]
    requires_roles: tuple[RoleId, ...]
    stages: tuple[StageDefinition, ...]


@dataclass(frozen=True, slots=True)
class WorkflowViolation:
    """One defect of a workflow document: JSON Pointer into it, stable reason code, message."""

    pointer: str
    reason: str
    message: str


def applicable_kinds(stage: StageDefinition) -> frozenset[TaskKind]:
    """Task kinds the stage applies to, before its ``when``/``skip_when`` (§5.3)."""
    own = STAGE_TYPE_KINDS.get(stage.type)
    if own is not None:
        return own
    if stage.type is StageType.ACCEPTANCE_GATE:
        return stage.for_kinds - GATE_KINDS
    return stage.for_kinds


def applies_to_kind(stage: StageDefinition, kind: TaskKind) -> bool:
    return kind in applicable_kinds(stage)


class _Defect(Exception):
    def __init__(self, pointer: str, reason: str, message: str) -> None:
        super().__init__(message)
        self.violation = WorkflowViolation(pointer, reason, message)


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _object(value: object, pointer: str, allowed: frozenset[str]) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise _Defect(pointer, "invalid_shape", "must be an object")
    fields = cast("Mapping[str, JsonValue]", value)
    unknown = sorted(set(fields) - allowed)
    if unknown:
        raise _Defect(f"{pointer}/{unknown[0]}", "unknown_field", f"unknown field {unknown[0]!r}")
    return fields


def _text(value: object, pointer: str, pattern: re.Pattern[str] | None = None, limit: int = 0) -> str:
    if not isinstance(value, str):
        raise _Defect(pointer, "invalid_shape", "must be a string")
    if pattern is not None and pattern.fullmatch(value) is None:
        raise _Defect(pointer, "invalid_value", f"{value!r} must match ^{pattern.pattern}$")
    if limit and len(value) > limit:
        raise _Defect(pointer, "invalid_value", f"must be at most {limit} characters")
    return value


def _member[E: StrEnum](kind: type[E], value: object, pointer: str, reason: str = "invalid_value") -> E:
    if isinstance(value, str):
        try:
            return kind(value)
        except ValueError:
            pass
    allowed = ", ".join(member.value for member in kind)
    raise _Defect(pointer, reason, f"{value!r} is not one of {allowed}")


def _unique[E: StrEnum](
    kind: type[E], value: object, pointer: str, reason: str = "invalid_value"
) -> tuple[E, ...]:
    if not isinstance(value, list) or not value:
        raise _Defect(pointer, "invalid_shape", "must be a non-empty array")
    values = cast("list[object]", value)
    items = tuple(_member(kind, item, f"{pointer}/{index}", reason) for index, item in enumerate(values))
    if len(set(items)) != len(items):
        raise _Defect(pointer, "invalid_value", "items must be unique")
    return items


def _condition(value: JsonValue, pointer: str) -> Condition:
    try:
        return parse_condition(value, pointer)
    except ConditionDefect as defect:
        raise _Defect(defect.pointer, defect.reason, defect.message) from None


def _choice(argument: JsonValue, allowed: frozenset[str], at: str) -> None:
    if not isinstance(argument, str) or argument not in allowed:
        raise _Defect(at, "invalid_value", f"{argument!r} is not one of {', '.join(sorted(allowed))}")


def _params(value: object, pointer: str, stage_type: StageType) -> StageParams:
    fields = _object(value, pointer, frozenset(_PARAMS))
    for name, argument in fields.items():
        at = f"{pointer}/{name}"
        allowed, stage_types = _PARAMS[name]
        if allowed is not None:
            _choice(argument, allowed, at)
        if name == "profile":
            _text(argument, at, _PROFILE)
        if name in {"blocks_next_phase", "reviewer_with_fix"} and not isinstance(argument, bool):
            raise _Defect(at, "invalid_shape", "must be a boolean")
        if name == "retries" and not (_is_int(argument) and 0 <= cast("int", argument) <= _RETRIES_MAX):
            raise _Defect(at, "invalid_value", f"must be an integer 0..{_RETRIES_MAX}")
        if stage_type not in stage_types:
            raise _Defect(at, "param_not_applicable", f"{name} is not a parameter of a {stage_type} stage")
    return StageParams(**cast("dict[str, Any]", dict(fields)))


def _on(value: object, pointer: str, stage_type: StageType) -> OnOutcome:
    fields = _object(value, pointer, frozenset(_HANDLERS))
    for name, argument in fields.items():
        at = f"{pointer}/{name}"
        allowed, stage_types = _HANDLERS[name]
        _choice(argument, allowed, at)
        if stage_type not in stage_types:
            raise _Defect(at, "handler_not_applicable", f"a {stage_type} stage has no {name} outcome")
    return OnOutcome(**cast("dict[str, Any]", dict(fields)))


def _role(stage_type: StageType, fields: Mapping[str, JsonValue], pointer: str) -> RoleId | None:
    allowed = AGENT_STAGE_ROLES.get(stage_type)
    if "role" not in fields:
        if stage_type is StageType.AGENT_STEP:
            raise _Defect(pointer, "role_mismatch", "an agent_step stage names its role")
        return _IMPLIED_ROLE.get(stage_type)
    role = _member(RoleId, fields["role"], f"{pointer}/role", "unknown_role")
    if allowed is None or role not in allowed:
        expected = ", ".join(sorted(allowed)) if allowed else "no role"
        raise _Defect(f"{pointer}/role", "role_mismatch", f"a {stage_type} stage runs {expected}, not {role}")
    return role


def _stage(value: object, pointer: str) -> StageDefinition:
    fields = _object(value, pointer, _STAGE_FIELDS)
    if "id" not in fields or "type" not in fields:
        raise _Defect(pointer, "invalid_shape", "a stage has id and type")
    stage_id = _text(fields["id"], f"{pointer}/id", _STAGE_ID)
    stage_type = _member(StageType, fields["type"], f"{pointer}/type", "unknown_stage_type")
    optional = fields.get("optional", False)
    if not isinstance(optional, bool):
        raise _Defect(f"{pointer}/optional", "invalid_shape", "must be a boolean")
    for_kinds = (
        frozenset(_unique(TaskKind, fields["for_kinds"], f"{pointer}/for_kinds"))
        if "for_kinds" in fields
        else DEFAULT_FOR_KINDS
    )
    # An absent condition is no restriction; an explicit null is a defect, not an absent key.
    when = _condition(fields["when"], f"{pointer}/when") if "when" in fields else None
    skip_when = _condition(fields["skip_when"], f"{pointer}/skip_when") if "skip_when" in fields else None
    stage = StageDefinition(
        id=stage_id,
        type=stage_type,
        for_kinds=for_kinds,
        role=_role(stage_type, fields, pointer),
        optional=optional,
        params=_params(fields.get("params", {}), f"{pointer}/params", stage_type),
        when=when,
        skip_when=skip_when,
        on=_on(fields.get("on", {}), f"{pointer}/on", stage_type),
    )
    if stage.on.result_invalid == "skip_if_optional" and not stage.optional:
        message = "result_invalid = skip_if_optional needs optional = true"
        raise _Defect(f"{pointer}/on/result_invalid", "handler_target_missing", message)
    return stage


def _header(fields: Mapping[str, JsonValue]) -> tuple[str, str, str, str]:
    for name in ("schema", "id", "version", "applies_to", "stage"):
        if name not in fields:
            raise _Defect("", "invalid_shape", f"{name} is required")
    if fields["schema"] != WORKFLOW_SCHEMA:
        raise _Defect("/schema", "invalid_value", f"schema must be {WORKFLOW_SCHEMA}")
    return (
        _text(fields["id"], "/id", _WORKFLOW_ID),
        _text(fields["version"], "/version", _VERSION),
        _text(fields.get("title", ""), "/title", limit=_TITLE_MAX),
        _text(fields.get("description", ""), "/description", limit=_DESCRIPTION_MAX),
    )


def _cross_stage(workflow: WorkflowDefinition) -> list[WorkflowViolation]:
    """Rules over several stages: each one makes a declared transition impossible at run time."""
    found: list[WorkflowViolation] = []
    seen: set[str] = set()
    # Task kinds an agent_step of each role serves; a handler target must serve every kind of its source.
    served_by: dict[RoleId, frozenset[TaskKind]] = {}
    for stage in workflow.stages:
        if stage.type is StageType.AGENT_STEP and stage.role is not None:
            served_by[stage.role] = served_by.get(stage.role, frozenset()) | applicable_kinds(stage)
    for index, stage in enumerate(workflow.stages):
        pointer = f"/stage/{index}"
        if stage.id in seen:
            found.append(
                WorkflowViolation(f"{pointer}/id", "duplicate_stage_id", f"stage id {stage.id!r} repeats")
            )
        seen.add(stage.id)
        if stage.role is not None and stage.role not in workflow.requires_roles:
            message = f"role {stage.role} is not listed in requires_roles, so no profile is pinned for it"
            found.append(WorkflowViolation(pointer, "role_not_required", message))
        if not applicable_kinds(stage):
            message = f"a {stage.type} stage with these for_kinds applies to no task kind"
            found.append(WorkflowViolation(f"{pointer}/for_kinds", "stage_never_applies", message))
        if (
            stage.type is StageType.AGENT_STEP
            and stage.role is RoleId.EXECUTOR
            and stage.for_kinds & GATE_KINDS
        ):
            message = "a writable executor cannot run on gate tasks"
            found.append(WorkflowViolation(f"{pointer}/for_kinds", "gate_executor_forbidden", message))
        for name in ("checks_failed", "verdict_attention", "verdict_red"):
            value = cast("str | None", getattr(stage.on, name))
            target = _HANDLER_TARGETS.get((name, value)) if value is not None else None
            if target is None:
                continue
            source_kinds = applicable_kinds(stage)
            if name == "checks_failed" and value == "rework":
                source_kinds = source_kinds - GATE_KINDS
            uncovered = source_kinds - served_by.get(target, frozenset())
            if uncovered:
                kinds = ", ".join(sorted(uncovered))
                message = f"{name} = {value} needs a {target} agent_step stage for task kind {kinds}"
                found.append(WorkflowViolation(f"{pointer}/on/{name}", "handler_target_missing", message))
    for kind in TaskKind:
        served = [
            (index, stage) for index, stage in enumerate(workflow.stages) if applies_to_kind(stage, kind)
        ]
        prepares = [index for index, stage in served if stage.type is StageType.PREPARE_ENVIRONMENT]
        if served and served[0][1].type is not StageType.PREPARE_ENVIRONMENT:
            message = f"the first stage for task kind {kind} must be prepare_environment"
            found.append(WorkflowViolation(f"/stage/{served[0][0]}", "prepare_not_first", message))
        for index in prepares[1:]:
            message = f"a second prepare_environment stage applies to task kind {kind}"
            found.append(WorkflowViolation(f"/stage/{index}", "duplicate_prepare", message))
    return found


def _requires_roles(fields: Mapping[str, JsonValue]) -> tuple[RoleId, ...] | None:
    """Declared roles; ``None`` when absent (then the stage roles are required)."""
    if "requires_roles" not in fields:
        return None
    value = fields["requires_roles"]
    if isinstance(value, list) and not value:
        return ()
    return _unique(RoleId, value, "/requires_roles", "unknown_role")


def parse_workflow(document: JsonValue) -> tuple[WorkflowDefinition | None, tuple[WorkflowViolation, ...]]:
    """Typed workflow and every defect found; the definition is ``None`` whenever a defect exists.

    Total over JSON values: a malformed document yields violations, never an exception.
    """
    found: list[WorkflowViolation] = []
    try:
        fields = _object(document, "", _WORKFLOW_FIELDS)
        workflow_id, version, title, description = _header(fields)
        applies_to = _unique(WorkKind, fields["applies_to"], "/applies_to")
        stages_value = fields["stage"]
    except _Defect as defect:
        return None, (defect.violation,)
    try:
        declared = _requires_roles(fields)
    except _Defect as defect:
        found.append(defect.violation)
        declared = ()
    if not isinstance(stages_value, list) or not stages_value:
        found.append(WorkflowViolation("/stage", "invalid_shape", "must be a non-empty array of stages"))
        return None, tuple(found)
    stages: list[StageDefinition] = []
    for index, item in enumerate(stages_value):
        try:
            stages.append(_stage(item, f"/stage/{index}"))
        except _Defect as defect:
            found.append(defect.violation)
    if found:
        return None, tuple(found)
    if declared is None:
        declared = tuple(dict.fromkeys(stage.role for stage in stages if stage.role is not None))
    workflow = WorkflowDefinition(
        id=workflow_id,
        version=version,
        title=title,
        description=description,
        applies_to=applies_to,
        requires_roles=declared,
        stages=tuple(stages),
    )
    found.extend(_cross_stage(workflow))
    return (None, tuple(found)) if found else (workflow, ())


def gate_workflow_violations(
    workflow: WorkflowDefinition,
    task: Task,
    *,
    required_checks: bool,
) -> tuple[WorkflowViolation, ...]:
    """R13 needs the compiled gate contract as well as the parsed workflow."""
    kind = task.kind
    if kind not in GATE_KINDS or kind is TaskKind.PLAN_AUDIT:
        return ()
    stages = [s for s in workflow.stages if applies_to_kind(s, kind)]
    review_required = task.review_mode == "required"
    terminal = StageType.PLAN_ACCEPTANCE if kind is TaskKind.PLAN_ACCEPTANCE else StageType.PHASE_GATE
    supported = any(s.type is terminal for s in stages)
    supported &= not required_checks or any(
        s.type is StageType.RUN_CHECKS and s.params.scope == "gate" for s in stages
    )
    # Gate dispatch pins audit_scope=range, including stages shared with work tasks (which may
    # declare corrected). R13 must reject a missing reviewer, not that shared declaration.
    supported &= not review_required or any(s.type is StageType.AGENT_REVIEW for s in stages)
    if (required_checks or review_required) and not supported:
        return (
            WorkflowViolation(
                "/stage", "GATE_UNSUPPORTED_BY_WORKFLOW", "R13: gate checks or review would be skipped"
            ),
        )
    return ()
