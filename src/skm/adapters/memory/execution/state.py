"""In-memory state, cloning, and validators for ``skm_execution`` (adapters §2.2, execution §§6, 11)."""

from __future__ import annotations

import dataclasses
import functools
from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final, Self, cast
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    InternalError,
)
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain import stored_payloads as stored
from skm.modules.execution.domain.attempt import (
    Attempt,
)
from skm.modules.execution.domain.live_control import IncidentGate, ToolCallObservation
from skm.modules.execution.domain.step import AttemptStep
from skm.modules.execution.domain.step_note import StepNote
from skm.modules.execution.domain.stored_payloads import (
    invalid_ref,
)
from skm.modules.runtimes.domain.usage import usage_to_json as runtime_usage_to_json
from skm.modules.runtimes.public import UsageReport
from skm.platform.schema.registry import SchemaRegistry

if TYPE_CHECKING:
    from skm.kernel.ids import (
        AttemptId,
        EntityId,
        FileVersionId,
        HostId,
        PlanId,
        ProjectId,
        RepositoryId,
        RevisionId,
        RunId,
        TaskId,
        WorkspaceId,
    )
    from skm.modules.artifacts.public import BindingRole
    from skm.modules.execution.domain.acceptance import AcceptanceDecision
    from skm.modules.execution.domain.assignment import Assignment
    from skm.modules.execution.domain.autopilot import AutopilotState
    from skm.modules.execution.domain.budget import BudgetAccount, BudgetReservation
    from skm.modules.execution.domain.carry_forward import CarryForward
    from skm.modules.execution.domain.check_execution import CheckExecution
    from skm.modules.execution.domain.decision_record import DecisionRecord
    from skm.modules.execution.domain.decision_request import DecisionAnswer, DecisionRequest
    from skm.modules.execution.domain.deviation import DeviationAcceptance
    from skm.modules.execution.domain.environment import ExecutionEnvironment
    from skm.modules.execution.domain.execution_bundle import ExecutionBundle
    from skm.modules.execution.domain.external_effect import ExternalEffect
    from skm.modules.execution.domain.finding import Finding
    from skm.modules.execution.domain.finding_resolution import FindingResolution
    from skm.modules.execution.domain.fix_brief import FixBrief
    from skm.modules.execution.domain.ids import (
        AcceptanceDecisionId,
        AssignmentId,
        BudgetReservationId,
        CarryForwardId,
        CheckExecutionId,
        DecisionAnswerId,
        DecisionRecordId,
        DecisionRequestId,
        DeviationId,
        EnvironmentId,
        ExternalEffectId,
        FindingId,
        FindingResolutionId,
        FixBriefId,
        IntegrationSlotId,
        ManualVerdictId,
        OutputId,
        ReadinessReportId,
        RecoveryRecordId,
        ReviewId,
        ReviewRequestId,
        StageRecordId,
        StepId,
    )
    from skm.modules.execution.domain.integration import IntegrationSlot
    from skm.modules.execution.domain.lease import Lease
    from skm.modules.execution.domain.manual_verdict import ManualVerdict
    from skm.modules.execution.domain.output import Output
    from skm.modules.execution.domain.readiness import ReadinessReport, RevisionVisa
    from skm.modules.execution.domain.recovery import RecoveryRecord
    from skm.modules.execution.domain.review import Review
    from skm.modules.execution.domain.review_request import ReviewRequest
    from skm.modules.execution.domain.run import Run
    from skm.modules.execution.domain.stage_record import StageRecord
    from skm.modules.execution.domain.task import Task
    from skm.modules.execution.domain.task_graph import TaskEdge
    from skm.modules.execution.ports import ReconfigurationRecord

STATE_KEY: Final = "execution"

__all__ = ["STATE_KEY", "MemoryExecutionState", "execution_state"]


@functools.cache
def schema_registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def validate_step_payloads(step: AttemptStep, old_step: AttemptStep | None) -> None:
    stored.validate_step_payloads(step, old_step, require_valid=schema_registry().require_valid)


def validate_continuation_payload(attempt: Attempt, old_attempt: Attempt | None) -> None:
    stored.validate_continuation_payload(attempt, old_attempt, require_valid=schema_registry().require_valid)


def clone_value[T](obj: T) -> T:
    """Deep-clone domain dataclasses, ``MappingProxyType``, and mutable containers safely."""
    if obj is None or isinstance(obj, bool | int | float | str | bytes | Decimal | datetime | UUID | Enum):
        return obj
    res: object = obj
    if isinstance(obj, MappingProxyType):
        mp = cast("Mapping[object, object]", obj)
        res = MappingProxyType({clone_value(k): clone_value(v) for k, v in mp.items()})
    elif isinstance(obj, dict):
        d = cast("dict[object, object]", obj)
        res = {clone_value(k): clone_value(v) for k, v in d.items()}
    elif isinstance(obj, list):
        res = [clone_value(x) for x in cast("list[object]", obj)]
    elif isinstance(obj, tuple):
        res = tuple(clone_value(x) for x in cast("tuple[object, ...]", obj))
    elif isinstance(obj, frozenset):
        res = frozenset(clone_value(x) for x in cast("frozenset[object]", obj))
    elif isinstance(obj, set):
        res = {clone_value(x) for x in cast("set[object]", obj)}
    elif dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        cls = type(obj)
        inst = object.__new__(cls)
        for f in dataclasses.fields(obj):
            object.__setattr__(inst, f.name, clone_value(getattr(obj, f.name)))
        res = inst
    return cast("T", res)


class MemoryExecutionState:
    def __init__(self) -> None:
        self.runs: dict[RunId, Run] = {}
        self.bundles: dict[RunId, ExecutionBundle] = {}
        self.reconfigurations: dict[UUID, ReconfigurationRecord] = {}
        self.revision_visas: dict[UUID, RevisionVisa] = {}
        self.readiness_reports: dict[ReadinessReportId, ReadinessReport] = {}
        self.tasks: dict[TaskId, Task] = {}
        self.task_edges: dict[tuple[RunId, TaskId, TaskId], TaskEdge] = {}
        self.attempts: dict[AttemptId, Attempt] = {}
        self.attempt_versions: dict[AttemptId, int] = {}
        self.stages: dict[StageRecordId, StageRecord] = {}
        self.steps: dict[StepId, AttemptStep] = {}
        self.step_notes: dict[UUID, StepNote] = {}
        self.step_tool_calls: dict[tuple[StepId, str], ToolCallObservation] = {}
        self.task_live_controls: dict[TaskId, JsonObject] = {}
        self.incident_gates: dict[UUID, IncidentGate] = {}
        self.assignments: dict[AssignmentId, Assignment] = {}
        self.leases: dict[AssignmentId, Lease] = {}
        self.environments: dict[EnvironmentId, ExecutionEnvironment] = {}
        self.outputs: dict[OutputId, Output] = {}
        self.checks: dict[CheckExecutionId, CheckExecution] = {}
        self.manual_verdicts: dict[ManualVerdictId, ManualVerdict] = {}
        self.reviews: dict[ReviewId, Review] = {}
        self.findings: dict[FindingId, Finding] = {}
        self.finding_tasks: dict[FindingId, TaskId] = {}
        self.resolutions: dict[FindingResolutionId, FindingResolution] = {}
        self.fix_briefs: dict[FixBriefId, FixBrief] = {}
        self.acceptance_decisions: dict[AcceptanceDecisionId, AcceptanceDecision] = {}
        self.deviations: dict[DeviationId, DeviationAcceptance] = {}
        self.carry_forwards: dict[CarryForwardId, CarryForward] = {}
        self.budget_accounts: dict[UUID, BudgetAccount] = {}
        self.budget_reservations: dict[BudgetReservationId, BudgetReservation] = {}
        self.decision_requests: dict[DecisionRequestId, DecisionRequest] = {}
        self.decision_answers: dict[DecisionAnswerId, tuple[int, DecisionAnswer]] = {}
        self.decision_records: dict[DecisionRecordId, DecisionRecord] = {}
        self.effects: dict[ExternalEffectId, ExternalEffect] = {}
        self.integration_slots: dict[IntegrationSlotId, IntegrationSlot] = {}
        self.run_integration_hosts: dict[tuple[RunId, RepositoryId], tuple[HostId, datetime]] = {}
        self.review_requests: dict[ReviewRequestId, ReviewRequest] = {}
        self.autopilot_states: dict[ProjectId, AutopilotState] = {}
        self.recoveries: dict[RecoveryRecordId, RecoveryRecord] = {}
        self.evidence_bindings: dict[tuple[str, UUID], list[tuple[FileVersionId, BindingRole]]] = {}

    def __deepcopy__(self, memo: dict[int, object]) -> Self:
        cls = type(self)
        copied = cls()
        memo[id(self)] = copied
        for name, val in self.__dict__.items():
            setattr(copied, name, clone_value(val))
        return copied


def execution_state(state: MemoryBackendState) -> MemoryExecutionState:
    found = state.modules.get(STATE_KEY)
    if found is None:
        found = MemoryExecutionState()
        state.modules[STATE_KEY] = found
    if not isinstance(found, MemoryExecutionState):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "execution memory state is malformed", details={"module": STATE_KEY}
        )
    return found


def usage_to_json(usage: UsageReport | None) -> JsonObject | None:
    return None if usage is None else runtime_usage_to_json(usage)


def plan_info(state: MemoryBackendState, plan_id: PlanId) -> tuple[str, str]:
    """Return ``(alias, purpose)`` from planning memory state when present."""
    pstate = state.modules.get("planning")
    if pstate is not None:
        plans = getattr(pstate, "plans", None)
        if isinstance(plans, dict):
            pmap = cast("dict[object, Any]", plans)
            if plan_id in pmap:
                p = pmap[plan_id]
                return str(p.alias), str(p.purpose.value)
    return str(plan_id)[:8], "standard"


def check_plan_revision_refs(
    state: MemoryBackendState,
    workspace_id: WorkspaceId,
    project_id: ProjectId,
    plan_id: PlanId,
    revision_id: RevisionId,
) -> None:
    """Enforce cross-module workspace/project/plan/revision FK consistency when prerequisite tables exist."""
    wstate = state.modules.get("workspace")
    if wstate is not None and isinstance(projs := getattr(wstate, "projects", None), dict) and projs:
        pmap = cast("dict[object, Any]", projs)
        proj = pmap.get(project_id)
        if proj is None or getattr(proj, "workspace_id", None) != workspace_id:
            raise invalid_ref("fk_runs__projects", project_id=str(project_id))
    pstate = state.modules.get("planning")
    if pstate is not None:
        plans = getattr(pstate, "plans", None)
        revs = getattr(pstate, "revisions", None)
        if isinstance(plans, dict) and plans:
            pl = cast("dict[object, Any]", plans).get(plan_id)
            if pl is None or pl.workspace_id != workspace_id or pl.project_id != project_id:
                raise invalid_ref("fk_runs__plans", plan_id=str(plan_id))
        if isinstance(revs, dict) and revs:
            rv = cast("dict[object, Any]", revs).get(revision_id)
            if rv is None or rv.meta.workspace_id != workspace_id or rv.meta.plan_id != plan_id:
                raise invalid_ref("fk_runs__plan_revisions", revision_id=str(revision_id))


def check_spec_entity_ref(
    state: MemoryBackendState,
    workspace_id: WorkspaceId,
    plan_id: PlanId,
    revision_id: RevisionId,
    entity_id: EntityId,
) -> None:
    pstate = state.modules.get("planning")
    if pstate is not None and isinstance(revs := getattr(pstate, "revisions", None), dict):
        rmap = cast("dict[object, Any]", revs)
        if revision_id in rmap:
            identities = getattr(pstate, "identities", None)
            if isinstance(identities, dict):
                imap = cast("dict[object, Any]", identities)
                if entity_id in imap:
                    if imap[entity_id].plan_id != plan_id:
                        raise invalid_ref("fk_run_tasks__revision_members", entity_id=str(entity_id))
                elif imap:
                    raise invalid_ref("fk_run_tasks__revision_members", entity_id=str(entity_id))
    del workspace_id
