"""Next actions of the advance engine, its shared decision context and action builders (execution §5.1).

A ``NextAction`` is a pure value: it performs no effect and holds no state. ``ADVANCE_RULES`` lists every
row id of the §5.1 table; ``make_cause`` builds the immutable history evidence the same evaluator keeps
beside the action (trigger kind, rule, accumulated reason codes and exact typed refs). ``TaskState`` and
``Ctx`` bind the task facts to the workflow definition, the policy and the clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Literal, cast

from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.decision_request import DecisionKind
from skm.modules.execution.domain.review import ReviewClearance
from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.workflow.definition import (
    StageDefinition,
    StageType,
    applies_to_kind,
)
from skm.modules.execution.domain.workflow.predicates import holds
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.domain.workflow.task_facts import (
    integrated_commits,
    kind_of,
    make_cause,
    outcome_of,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from datetime import datetime
    from uuid import UUID

    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.attempt import Attempt
    from skm.modules.execution.domain.autonomy import ReusableDecision
    from skm.modules.execution.domain.blocking_reason import BlockingReason
    from skm.modules.execution.domain.check_execution import CheckExecution
    from skm.modules.execution.domain.contracts import (
        BudgetView,
        DecisionPayload,
        ExecutionPolicy,
        GateView,
        HistoryCause,
    )
    from skm.modules.execution.domain.decision_request import DecisionRequest
    from skm.modules.execution.domain.finding import Finding
    from skm.modules.execution.domain.ids import (
        CheckExecutionId,
        DecisionRequestId,
        FindingId,
        OutputId,
        StageRecordId,
    )
    from skm.modules.execution.domain.manual_verdict import ManualVerdict
    from skm.modules.execution.domain.output import Output
    from skm.modules.execution.domain.review import Review
    from skm.modules.execution.domain.risk import RiskScore
    from skm.modules.execution.domain.run import Run
    from skm.modules.execution.domain.session import RouteRef
    from skm.modules.execution.domain.stage_record import StageRecord
    from skm.modules.execution.domain.task import Task
    from skm.modules.execution.domain.workflow.definition import (
        StageDefinition,
        StageType,
        WorkflowDefinition,
    )
    from skm.modules.execution.domain.workflow.history import StageEntry, StageHistory


@dataclass(frozen=True, slots=True)
class RecordedInstruction:
    """The recorded instruction of a stage record: the params and the feedback it was started with."""

    params: Mapping[str, JsonValue] = field(default_factory=lambda: cast("dict[str, JsonValue]", {}))
    feedback: FeedbackRefs | None = None


def _inherit(rec: FeedbackRefs | None, given: FeedbackRefs | None, verbatim: bool) -> FeedbackRefs | None:
    if rec is None:
        return given
    if verbatim:
        return rec if given is None else given
    if given is None:
        return rec if rec != FeedbackRefs() else None
    return FeedbackRefs(
        fix_brief_id=given.fix_brief_id or rec.fix_brief_id,
        schema_errors_step_id=given.schema_errors_step_id or rec.schema_errors_step_id,
        answer_request_ids=given.answer_request_ids or rec.answer_request_ids,
        advice_step_id=given.advice_step_id or rec.advice_step_id,
        interrupted_stage_record_id=given.interrupted_stage_record_id or rec.interrupted_stage_record_id,
    )


@dataclass(frozen=True, slots=True)
class RunStage:
    stage_id: str
    stage_type: StageType
    mode: StageMode
    round_no: int
    params: Mapping[str, JsonValue]
    not_before: datetime | None = None
    route_override: RouteRef | None = None
    feedback: FeedbackRefs | None = None


@dataclass(frozen=True, slots=True)
class WaitFor:
    blocking: BlockingReason
    release_assignment: bool


@dataclass(frozen=True, slots=True)
class Accept:
    output_id: OutputId
    clearance: ReviewClearance


@dataclass(frozen=True, slots=True)
class Rework:
    reason: Literal["checks_failed", "review_findings", "manual_failed"]
    feedback: FeedbackRefs


@dataclass(frozen=True, slots=True)
class CreateFollowups:
    reason: Literal["review_findings", "checks_failed"]
    finding_ids: tuple[FindingId, ...]
    check_execution_ids: tuple[CheckExecutionId, ...]


@dataclass(frozen=True, slots=True)
class NewAttempt:
    reason_code: str


@dataclass(frozen=True, slots=True)
class Escalate:
    kind: DecisionKind
    code: str
    payload: DecisionPayload
    blocking_code: BlockingCode


@dataclass(frozen=True, slots=True)
class Fail:
    code: str


@dataclass(frozen=True, slots=True)
class Integrate:
    output_id: OutputId


@dataclass(frozen=True, slots=True)
class Done:
    """Terminal action marker; no side effects. Instances are equal, so advance stays comparable."""


@dataclass(frozen=True, slots=True)
class Noop:
    """No-action marker; no side effects. Instances are equal, so advance stays comparable."""


type NextAction = (
    RunStage
    | WaitFor
    | Accept
    | Rework
    | CreateFollowups
    | NewAttempt
    | Escalate
    | Fail
    | Integrate
    | Done
    | Noop
)


# Every row id of the §5.1 table (guards G, rule L, A-K). The engine emits no other advance_rule.
ADVANCE_RULES: Final = frozenset({
    "G1", "G2", "G3", "G4", "G5", "G6", "G7", "L1", "L2", "L2b", "L2i", "A1", "A2", "A3", "A4", "A5", "A6",
    "B1", "B2", "B3", "C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "C9", "C10", "C10b", "C11", "C12",
    "C13", "C14", "D1", "D2", "D3", "D4", "D5", "D6", "D6g", "D7", "D8", "D9", "D10", "D11", "D12", "D13",
    "D14", "D15", "E1", "E2", "E3", "F1", "F2", "F3", "F4", "F5", "F6", "F7", "F8",
    "H0", "H1", "H1g", "H2", "H3",
    "H4", "H5", "H6", "H7", "H8", "I1", "I2", "I3", "I4", "I5", "I6", "J1", "J2", "J3", "J4", "J5", "J6",
    "J7", "K1", "K2", "K3", "K4", "K5", "K5a", "K5b", "K5c", "K5d", "K6", "K7", "K8", "K8a", "K9", "K10",
    "K11", "K12", "K13",
})  # fmt: skip

# Limits the policy may omit; the names are the ``ExecutionPolicy`` members of §5.
DEFAULT_REWORK_MAX_ROUNDS: Final = 2
DEFAULT_REVIEW_MAX_ROUNDS: Final = 2
DEFAULT_ATTEMPTS_MAX: Final = 3
DEFAULT_RESULT_RETRIES: Final = 1
DEFAULT_INFRA_RETRIES: Final = 1
DEFAULT_CHECKS_ERROR_RETRIES: Final = 1
DEFAULT_ADVISOR_MAX_ROUNDS: Final = 2
DEFAULT_FOLLOWUPS_MAX: Final = 3
DEFAULT_RISK_THRESHOLD: Final = 60
DEFAULT_RETRY_BUDGET: Final = 6
DEFAULT_PROVIDER_WAIT_MAX_S: Final = 21600
OWNER_ANSWERS: Final = frozenset({
    "answer", "retry_stage", "new_attempt", "accept_deviation",
    "accept_rejection", "skip", "fail", "raise_budget",
})  # fmt: skip
DECISION_ACTIONS: Final = OWNER_ANSWERS
RERUN_SCOPE: Final = "rerun_after_integration"
AGENT_STAGE_TYPES: Final = frozenset({"agent_step", "agent_review", "advisor_consult"})
CONTROL_TYPES: Final = frozenset({"acceptance_gate", "phase_gate", "plan_acceptance", "human_gate"})
EXECUTE_ROLES: Final = frozenset({RoleId.EXECUTOR, RoleId.RESEARCHER})
ESCALATION_OPTIONS: Final = ("retry_stage", "new_attempt", "fail")
_GATE_KINDS: Final = frozenset({"item_gate", "phase_gate", "group_review", "plan_acceptance"})


@dataclass(frozen=True, slots=True)
class ActionDecision:
    action: NextAction
    cause: HistoryCause


@dataclass(frozen=True, slots=True)
class DecisionFact:
    """An answered decision request not yet applied: the trusted input of the J rows."""

    request_id: DecisionRequestId
    action: str
    value: JsonValue = None
    code: str | None = None
    raise_limit: bool = False
    deviation_recorded: bool = False
    control_allowed: bool = True
    reconfigured: bool = False


@dataclass(frozen=True, slots=True)
class TaskState:
    """Everything one decision reads; the fields after ``gate`` are optional facts of the loader."""

    run: Run
    task: Task
    attempt: Attempt | None
    effective_policy: ExecutionPolicy
    history: StageHistory
    output: Output | None
    checks: tuple[CheckExecution, ...]
    manual: Mapping[CheckExecutionId, ManualVerdict]
    reviews: tuple[Review, ...]
    findings: tuple[Finding, ...]
    open_requests: tuple[DecisionRequest, ...]
    budget: BudgetView
    risk: RiskScore | None
    advisor_rounds_used: int
    gate: GateView | None
    route_flags: frozenset[str] = frozenset()
    decisions: tuple[DecisionFact, ...] = ()
    reusable: Mapping[str, ReusableDecision] = field(
        default_factory=lambda: cast("dict[str, ReusableDecision]", {})
    )
    policy_answered: frozenset[str] = frozenset()
    reap_confirmed: bool = False
    effects_unresolved: bool = False
    rerun_checks_declared: bool = False
    run_retries_used: int | None = None
    instructions: Mapping[StageRecordId, RecordedInstruction] = field(
        default_factory=lambda: cast("dict[StageRecordId, RecordedInstruction]", {})
    )
    recheck_commits: Mapping[str, str] | None = None
    integration_receipts_by_mount: Mapping[str, Mapping[str, JsonValue]] | None = None


@dataclass(slots=True)
class Ctx:
    state: TaskState
    wf: WorkflowDefinition
    policy: ExecutionPolicy
    now: datetime
    entries: tuple[StageEntry, ...] = field(init=False)

    def __post_init__(self) -> None:
        live = (e for e in self.state.history.entries if e.record.state != "skipped")
        self.entries = tuple(sorted(live, key=lambda e: e.record.seq))

    @property
    def task(self) -> Task:
        return self.state.task

    @property
    def gate(self) -> bool:
        return self.task.kind in _GATE_KINDS

    def number(self, key: str, default: int) -> int:
        value = self.policy.get(key)
        return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else default

    def flag(self, key: str, default: bool) -> bool:
        value = self.policy.get(key)
        return value if isinstance(value, bool) else default

    def decide(
        self,
        rule: str | None,
        action: NextAction,
        *,
        trigger: str = "stage_outcome",
        reasons: Sequence[str] = (),
        refs: Sequence[tuple[str, UUID]] = (),
        entry: StageEntry | None = None,
    ) -> ActionDecision:
        base: list[tuple[str, UUID]] = []
        if entry is not None:
            base.append(("stage", entry.record.id))
        if self.state.output is not None:
            base.append(("output", self.state.output.id))
        return ActionDecision(action, make_cause(trigger, rule, reasons, [*base, *refs]))

    def stage(self, stage_id: str) -> StageDefinition | None:
        return next((s for s in self.wf.stages if s.id == stage_id), None)

    def find(
        self, stage_type: StageType | str, *, roles: frozenset[RoleId] | None = None, scope: str | None = None
    ) -> StageDefinition | None:
        for item in self.wf.stages:
            if item.type != stage_type or not applies_to_kind(item, self.task.kind):
                continue
            if roles is not None and item.role not in roles:
                continue
            if scope is not None and (item.params.scope or "task") != scope:
                continue
            return item
        return None

    def next_applicable(self, after_id: str | None) -> StageDefinition | None:
        stages = self.wf.stages
        start = 0
        if after_id is not None:
            start = next((i + 1 for i, s in enumerate(stages) if s.id == after_id), 0)
        for item in stages[start:]:
            if not applies_to_kind(item, self.task.kind):
                continue
            if item.when is not None and not holds(item.when, self.state):
                continue
            if item.skip_when is not None and holds(item.skip_when, self.state):
                continue
            return item
        return None

    def next_round(self, stage_id: str) -> int:
        rounds = [e.record.round_no for e in self.entries if e.record.stage_id == stage_id]
        return max(rounds, default=0) + 1

    def run(
        self,
        item: StageDefinition,
        mode: StageMode = StageMode.NORMAL,
        *,
        round_no: int | None = None,
        extra: Mapping[str, JsonValue] | None = None,
        feedback: FeedbackRefs | None = None,
        not_before: datetime | None = None,
        route_override: RouteRef | None = None,
    ) -> RunStage:
        params: dict[str, JsonValue] = {**item.params.as_json(), **(extra or {})}
        return RunStage(
            stage_id=item.id,
            stage_type=item.type,
            mode=mode,
            round_no=round_no if round_no is not None else self.next_round(item.id),
            params=params,
            not_before=not_before,
            route_override=route_override,
            feedback=feedback,
        )

    def repeat(
        self,
        entry: StageEntry,
        mode: StageMode,
        *,
        feedback: FeedbackRefs | None = None,
        not_before: datetime | None = None,
        route_override: RouteRef | None = None,
        extra: Mapping[str, JsonValue] | None = None,
        verbatim: bool = False,
    ) -> RunStage:
        record = entry.record
        found = self.stage(record.stage_id)
        recorded = self.state.instructions.get(record.id)
        params: dict[str, JsonValue] = {} if found is None else dict(found.params.as_json())
        if recorded is not None:
            params.update(recorded.params)
        elif self._is_recheck(record, found):
            pinned = self._integrated_before(record)
            if pinned:
                params["recheck_commits"] = cast("JsonValue", pinned)
        params.update(extra or {})
        return RunStage(
            stage_id=record.stage_id,
            stage_type=StageType(record.stage_type),
            mode=mode,
            round_no=record.round_no,
            params=params,
            not_before=not_before,
            route_override=route_override,
            feedback=_inherit(None if recorded is None else recorded.feedback, feedback, verbatim),
        )

    @staticmethod
    def _is_recheck(record: StageRecord, found: StageDefinition | None) -> bool:
        if record.stage_type != "run_checks":
            return False
        return record.stage_id == "recheck" if found is None else found.params.scope == RERUN_SCOPE

    def is_recheck(self, record: StageRecord) -> bool:
        return self._is_recheck(record, self.stage(record.stage_id))

    def _integrated_before(self, record: StageRecord) -> dict[str, JsonValue]:
        for item in reversed(self.entries):
            if item.record.seq >= record.seq or item.record.stage_type != "integrate":
                continue
            if kind_of(item.record) == "success":
                return integrated_commits(self.state, outcome_of(item))
        return {}

    def wait(
        self,
        code: BlockingCode,
        refs: Mapping[str, JsonValue],
        message: str,
        *,
        release: bool = True,
        next_check_at: datetime | None = None,
    ) -> WaitFor:
        reason = blocking_reason(
            code,
            task_id=self.task.id,
            refs=refs,
            now=self.now,
            message=message,
            previous=self.task.blocking_reason,
            next_check_at=next_check_at,
        )
        return WaitFor(reason, release)

    def escalate(  # noqa: PLR0913
        self,
        rule: str,
        code: str,
        *,
        kind: DecisionKind = DecisionKind.ESCALATION,
        blocking: BlockingCode = BlockingCode.WAITING_OWNER,
        options: Sequence[str] = (),
        extra: Mapping[str, JsonValue] | None = None,
        entry: StageEntry | None = None,
        reasons: Sequence[str] = (),
        refs: Sequence[tuple[str, UUID]] = (),
        trigger: str = "stage_outcome",
    ) -> ActionDecision:
        payload: DecisionPayload = {"code": code, "options": list(options), **(extra or {})}
        action = Escalate(kind=kind, code=code, payload=payload, blocking_code=blocking)
        return self.decide(rule, action, trigger=trigger, reasons=reasons, refs=refs, entry=entry)
