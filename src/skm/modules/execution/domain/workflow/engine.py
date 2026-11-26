"""Deterministic advance engine (execution §5.1): the decision table as explicit rules.

``decide_advance`` is the only evaluator: it reads one ``TaskState`` and returns the ``NextAction`` with the
fired row (``advance_rule``), the reason codes it accumulated and the exact typed refs of its cause.
``advance`` is its compatibility projection. Both are pure: the clock is the ``now`` argument, nothing runs a
subprocess, a model or a database write, and one state always gives one answer.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final, cast

from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.blocking_reason import BlockingCode
from skm.modules.execution.domain.check_execution import CheckState
from skm.modules.execution.domain.decision_request import DecisionKind
from skm.modules.execution.domain.finding import FindingState
from skm.modules.execution.domain.review import ReviewClearance
from skm.modules.execution.domain.run import RunStatus
from skm.modules.execution.domain.stage_record import ACTIVE_STAGE_STATES, StageOutcomeKind, StageState
from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.task import TERMINAL_TASK_STATUSES, TaskStatus
from skm.modules.execution.domain.workflow import action_builders as build
from skm.modules.execution.domain.workflow import actions as act
from skm.modules.execution.domain.workflow import task_facts as facts
from skm.modules.execution.domain.workflow.actions import (
    DECISION_ACTIONS,
    Accept,
    ActionDecision,
    CreateFollowups,
    Ctx,
    DecisionFact,
    Done,
    Fail,
    NewAttempt,
    NextAction,
    Noop,
    Rework,
    RunStage,
    TaskState,
)
from skm.modules.execution.domain.workflow.definition import StageType
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.contracts import ExecutionPolicy
    from skm.modules.execution.domain.workflow.definition import WorkflowDefinition
    from skm.modules.execution.domain.workflow.history import StageEntry

from skm.modules.execution.domain.workflow.engine_review import (
    after_advice as after_advice,
)
from skm.modules.execution.domain.workflow.engine_review import (
    after_gate,
    empty_gate,
    role_writes,
)
from skm.modules.execution.domain.workflow.engine_review import (
    after_integrate as after_integrate,
)
from skm.modules.execution.domain.workflow.engine_review import (
    after_review as after_review,
)
from skm.modules.execution.domain.workflow.engine_review import (
    after_triage as after_triage,
)
from skm.modules.execution.domain.workflow.engine_review import (
    runtime_failure as runtime_failure,
)

__all__ = [
    "DECISION_ACTIONS",
    "ActionDecision",
    "DecisionFact",
    "TaskState",
    "advance",
    "decide_advance",
]

_REQUEST_BLOCKING: Final = {
    DecisionKind.QUESTION: BlockingCode.WAITING_ANSWER,
    DecisionKind.APPROVAL: BlockingCode.WAITING_APPROVAL,
    DecisionKind.BUDGET: BlockingCode.BLOCKED_BY_BUDGET,
    DecisionKind.ESCALATION: BlockingCode.WAITING_OWNER,
}
_GATE_STAGE_TYPES: Final = frozenset(
    {StageType.ACCEPTANCE_GATE, StageType.PHASE_GATE, StageType.PLAN_ACCEPTANCE}
)


def advance(state: TaskState, wf: WorkflowDefinition, policy: ExecutionPolicy, now: datetime) -> NextAction:
    return decide_advance(state, wf, policy, now).action


def decide_advance(
    state: TaskState, wf: WorkflowDefinition, policy: ExecutionPolicy, now: datetime
) -> ActionDecision:
    ctx = Ctx(state, wf, policy, now)
    for guard in (_g1, _g2, _g3, _g45, _g6):
        decided = guard(ctx)
        if decided is not None:
            return decided
    return _g7(ctx, _table(ctx))


def _g1(ctx: Ctx) -> ActionDecision | None:
    if ctx.state.run.status is RunStatus.RUNNING:
        return None
    return ctx.decide("G1", Noop(), reasons=("RUN_NOT_RUNNING",))


def _g2(ctx: Ctx) -> ActionDecision | None:
    if ctx.task.status in TERMINAL_TASK_STATUSES:
        return ctx.decide("G2", Done(), reasons=("TASK_TERMINAL",))
    return None


def _g3(ctx: Ctx) -> ActionDecision | None:
    if ctx.policy.get("kill_switch") is not True:
        return None
    wait = ctx.wait(BlockingCode.BLOCKED_BY_POLICY, {"reason": "kill_switch"}, "kill switch is on")
    return ctx.decide("G3", wait, trigger="policy_resolved", reasons=("KILL_SWITCH",))


def _g45(ctx: Ctx) -> ActionDecision | None:
    attempt = ctx.state.attempt
    if attempt is None or attempt.state is not AttemptState.OWNERSHIP_LOST:
        return None
    refs = [("attempt", attempt.id)]
    if ctx.task.attempt_count < ctx.number("attempts_max", act.DEFAULT_ATTEMPTS_MAX):
        return ctx.decide(
            "G4", NewAttempt("LEASE_LOST"), trigger="lease_recovery", reasons=("LEASE_LOST",), refs=refs
        )
    codes = ("LEASE_LOST", "ATTEMPTS_EXHAUSTED")
    return ctx.decide("G5", Fail("LEASE_LOST"), trigger="lease_recovery", reasons=codes, refs=refs)


def _g6(ctx: Ctx) -> ActionDecision | None:
    open_requests = facts.open_owner_requests(ctx.state, _REQUEST_BLOCKING)
    if not open_requests:
        return None
    first = open_requests[0]
    code = _REQUEST_BLOCKING[first.kind]
    wait = ctx.wait(
        code, facts.request_blocking_refs(first, code), f"waiting for {first.kind.value} {first.id}"
    )
    return ctx.decide(
        "G6",
        wait,
        trigger="wait_changed",
        reasons=[_REQUEST_BLOCKING[r.kind].value for r in open_requests],
        refs=[("decision_request", r.id) for r in open_requests],
    )


def _g7(ctx: Ctx, decided: ActionDecision) -> ActionDecision:
    action = decided.action
    if not isinstance(action, RunStage) or action.stage_type in act.CONTROL_TYPES:
        return decided
    blocked = facts.budget_block(
        ctx.state, action.stage_type.value, action.stage_type in act.AGENT_STAGE_TYPES
    )
    if blocked is None:
        return decided
    return ctx.escalate(
        "G7",
        "BUDGET_EXHAUSTED",
        kind=DecisionKind.BUDGET,
        blocking=BlockingCode.BLOCKED_BY_BUDGET,
        options=("raise_budget", "cancel_run"),
        extra={**blocked, "stage_id": action.stage_id},
        trigger="policy_resolved",
        reasons=("BUDGET_EXHAUSTED", *(("UNMETERED",) if blocked.get("reason") == "unmetered" else ())),
    )


def _table(ctx: Ctx) -> ActionDecision:
    active = next((e for e in ctx.state.history.entries if e.record.state in ACTIVE_STAGE_STATES), None)
    if active is not None:
        return ctx.decide(None, Noop(), reasons=("STAGE_ACTIVE",), entry=active)
    if not ctx.entries:
        return initial_selection(ctx)
    last = ctx.entries[-1]
    if last.record.state is StageState.INTERRUPTED:
        return _interrupted(ctx, last)
    if ctx.task.status is TaskStatus.AWAITING_DECISION:
        return _answered(ctx, last)
    return _dispatch(ctx, last)


def _dispatch(ctx: Ctx, last: StageEntry, *, reasons: Sequence[str] = ()) -> ActionDecision:  # noqa: PLR0911
    record = last.record
    stage_type = build.stage_type_of(record.stage_type)
    role = build.role_of(ctx, record)
    if stage_type is StageType.PREPARE_ENVIRONMENT:
        return after_prepare(ctx, last, reasons)
    if stage_type is StageType.AGENT_STEP and role is RoleId.SCOUT:
        return after_scout(ctx, last, reasons)
    if stage_type is StageType.AGENT_STEP and role in act.EXECUTE_ROLES:
        return after_execute(ctx, last, reasons)
    if stage_type is StageType.AGENT_STEP and role is RoleId.TRIAGER:
        return after_triage(ctx, last, reasons)
    if stage_type is StageType.RUN_CHECKS:
        return after_checks(ctx, last, reasons)
    if stage_type is StageType.AGENT_REVIEW:
        return after_review(ctx, last, reasons)
    if stage_type is StageType.ADVISOR_CONSULT:
        return after_advice(ctx, last, reasons)
    if stage_type is StageType.INTEGRATE:
        return after_integrate(ctx, last, reasons)
    if stage_type is not None and stage_type in _GATE_STAGE_TYPES:
        return after_gate(ctx, last, stage_type, reasons)
    return ctx.escalate(
        "K2",
        "ADVANCE_UNHANDLED",
        entry=last,
        extra={"stage_id": record.stage_id, "stage_type": record.stage_type},
        reasons=("ADVANCE_UNHANDLED", *reasons),
    )


def _interrupted(ctx: Ctx, last: StageEntry) -> ActionDecision:
    record = last.record
    feedback = FeedbackRefs(interrupted_stage_record_id=record.id)
    if record.stage_type == StageType.INTEGRATE.value:
        stage = ctx.repeat(last, StageMode.RECONCILE, feedback=feedback)
        return ctx.decide(
            "L2i", stage, trigger="lease_recovery", reasons=("INTEGRATE_INTERRUPTED",), entry=last
        )
    if record.runtime_started_at is None and not ctx.state.effects_unresolved:
        stage = ctx.repeat(last, record.mode, verbatim=True)
        return ctx.decide("L1", stage, trigger="lease_recovery", reasons=("RUNTIME_NOT_STARTED",), entry=last)
    if not ctx.state.reap_confirmed:
        return ctx.decide(None, Noop(), trigger="lease_recovery", reasons=("REAP_NOT_CONFIRMED",), entry=last)
    if record.stage_type in {"agent_step", "agent_review"} and (
        role_writes(build.role_of(ctx, record))
        or any(step.admission.get("reviewer_with_fix") is True for step in last.steps)
    ):
        stage = ctx.repeat(last, StageMode.RESUME_INTERRUPTED, feedback=feedback)
        return ctx.decide("L2", stage, trigger="lease_recovery", reasons=("RUNTIME_STARTED",), entry=last)
    stage = ctx.repeat(last, StageMode.RETRY)
    return ctx.decide("L2b", stage, trigger="lease_recovery", reasons=("RUNTIME_STARTED",), entry=last)


def _answered(ctx: Ctx, last: StageEntry) -> ActionDecision:  # noqa: PLR0911, PLR0912
    if not ctx.state.decisions:
        return ctx.decide(None, Noop(), trigger="decision_answered", reasons=("NO_ANSWER",), entry=last)
    fact = ctx.state.decisions[0]
    refs = [("decision_request", fact.request_id)]
    trigger = "decision_answered"
    if fact.action == "answer":
        asked = next(
            (e for e in reversed(ctx.entries) if build.role_of(ctx, e.record) in act.EXECUTE_ROLES), None
        )
        if asked is None:
            return ctx.escalate(
                "J1", "WORKFLOW_INCOMPLETE", entry=last, reasons=("NO_EXECUTE_STAGE",), refs=refs
            )
        stage = build.continue_with_answer(ctx, asked, {}, (fact.request_id,))
        return ctx.decide("J1", stage, trigger=trigger, refs=refs, entry=last)
    if fact.action == "retry_stage":
        extra: dict[str, JsonValue] = {}
        if isinstance(fact.value, Mapping) and isinstance(fact.value.get("recheck_commits"), dict):
            extra["recheck_commits"] = cast("JsonValue", fact.value["recheck_commits"])
        if (
            facts.kind_of(last.record) is StageOutcomeKind.SUCCESS
            and last.record.stage_type == StageType.INTEGRATE.value
        ):
            given = cast("Mapping[str, JsonValue]", extra.get("recheck_commits") or {})
            started = build.recheck_after_answer(ctx, last, given, refs)
            return started or build.recheck_unbound(ctx, last, ("NO_APPROVED_COMMITS",))
        stage = ctx.repeat(last, StageMode.RETRY, extra=extra)
        if ctx.is_recheck(last.record) and not stage.params.get("recheck_commits"):
            return build.recheck_unbound(ctx, last, ("NO_APPROVED_COMMITS",))
        return ctx.decide("J2", stage, trigger=trigger, refs=refs, entry=last)
    if fact.action == "new_attempt":
        if fact.raise_limit or ctx.task.attempt_count < ctx.number("attempts_max", act.DEFAULT_ATTEMPTS_MAX):
            return ctx.decide("J3", NewAttempt("OWNER_DECISION"), trigger=trigger, refs=refs, entry=last)
        return ctx.escalate(
            "J3",
            "ATTEMPTS_EXHAUSTED",
            options=("fail",),
            entry=last,
            reasons=("ATTEMPTS_EXHAUSTED",),
            refs=refs,
            trigger=trigger,
        )
    if fact.action in {"accept_deviation", "accept_rejection"}:
        if not fact.deviation_recorded:
            return ctx.decide(
                None, Noop(), trigger=trigger, reasons=("DEVIATION_NOT_RECORDED",), refs=refs, entry=last
            )
        return build.accept(ctx, last, "J4", (), ReviewClearance.DEVIATION, trigger=trigger, refs=refs)
    if fact.action == "skip":
        if not fact.control_allowed:
            return ctx.decide(
                None, Noop(), trigger=trigger, reasons=("SKIP_NOT_PERMITTED",), refs=refs, entry=last
            )
        return ctx.decide("J5", Done(), trigger=trigger, reasons=("TASK_SKIPPED",), refs=refs, entry=last)
    if fact.action == "fail":
        return ctx.decide("J6", Fail(fact.code or "OWNER_DECISION"), trigger=trigger, refs=refs, entry=last)
    if fact.action == "raise_budget":
        if not fact.reconfigured:
            return ctx.decide(
                None, Noop(), trigger=trigger, reasons=("BUDGET_NOT_RAISED",), refs=refs, entry=last
            )
        inner = _dispatch(ctx, last, reasons=("BUDGET_RAISED",))
        return ActionDecision(inner.action, facts.wrap_j7_cause(inner.cause, refs))
    return ctx.decide(None, Noop(), trigger=trigger, reasons=("UNKNOWN_ANSWER",), refs=refs, entry=last)


def initial_selection(ctx: Ctx) -> ActionDecision:
    if ctx.task.status not in {TaskStatus.ASSIGNED, TaskStatus.EXECUTING}:
        return ctx.decide(None, Noop(), reasons=("TASK_NOT_STARTED",))
    prepare = ctx.find(StageType.PREPARE_ENVIRONMENT)
    if prepare is None and ctx.gate:
        return empty_gate(ctx, "A1")
    if prepare is None:
        return ctx.escalate("A1", "WORKFLOW_INCOMPLETE", reasons=("NO_PREPARE_STAGE",), trigger="run_start")
    return ctx.decide("A1", ctx.run(prepare, round_no=1), trigger="run_start", reasons=("INITIAL_SELECTION",))


def after_prepare(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    kind = facts.kind_of(last.record)
    if kind is StageOutcomeKind.RUNTIME_ERROR:
        return runtime_failure(ctx, last, retry_rule="A4", stop_rule="A5", reasons=reasons)
    if kind is not StageOutcomeKind.SUCCESS:
        return build.unexpected(ctx, last, reasons)
    nxt = ctx.next_applicable(last.record.stage_id)
    if ctx.gate:
        if nxt is None:
            return empty_gate(ctx, "A6", last)
        return ctx.decide("A6", ctx.run(nxt), reasons=reasons, entry=last)
    if nxt is None:
        return ctx.escalate(
            "A3", "WORKFLOW_INCOMPLETE", entry=last, reasons=("NO_APPLICABLE_STAGE", *reasons)
        )
    is_scout = nxt.type is StageType.AGENT_STEP and nxt.role is RoleId.SCOUT
    return ctx.decide("A2" if is_scout else "A3", ctx.run(nxt), reasons=reasons, entry=last)


def after_scout(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    kind = facts.kind_of(last.record)
    found = ctx.stage(last.record.stage_id)
    optional = True if found is None else found.optional
    if kind is StageOutcomeKind.SUCCESS:
        return build.to_execute(ctx, last, "B1", reasons)
    if kind in {StageOutcomeKind.RESULT_INVALID, StageOutcomeKind.RUNTIME_ERROR} and optional:
        return build.to_execute(ctx, last, "B2", ("SCOUT_SKIPPED", *reasons))
    if kind is StageOutcomeKind.RUNTIME_ERROR:
        return runtime_failure(ctx, last, retry_rule="B3", stop_rule="C14", reasons=reasons)
    if kind is StageOutcomeKind.RESULT_INVALID:
        return build.result_invalid(ctx, last, retry_rule="C10", escalate_rule="C10b", reasons=reasons)
    return build.unexpected(ctx, last, reasons)


def after_execute(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    kind = facts.kind_of(last.record)
    if kind is StageOutcomeKind.SUCCESS:
        return _to_checks(ctx, last, reasons)
    if kind is StageOutcomeKind.WRITE_SCOPE_VIOLATION:
        if ctx.policy.get("scope_outside_policy", "deviation") == "block":
            return ctx.escalate(
                "C9", "WRITE_SCOPE_VIOLATION", options=act.ESCALATION_OPTIONS, entry=last, reasons=reasons
            )
        return _to_checks(ctx, last, ("SCOPE_DEVIATION", *reasons))
    if kind is StageOutcomeKind.QUESTION:
        return build.route_question(ctx, last, reasons)
    if kind is StageOutcomeKind.BLOCKED:
        return ctx.escalate("C8", "ITEM_BLOCKED", entry=last, reasons=reasons)
    if kind is StageOutcomeKind.RESULT_INVALID:
        return build.result_invalid(ctx, last, retry_rule="C10", escalate_rule="C10b", reasons=reasons)
    if kind is StageOutcomeKind.RUNTIME_ERROR:
        return runtime_failure(
            ctx,
            last,
            retry_rule="C11",
            stop_rule="C14",
            reconcile_rule="C12",
            replan_rule="C13",
            reasons=reasons,
        )
    return build.unexpected(ctx, last, reasons)


def _to_checks(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    nxt = ctx.next_applicable(last.record.stage_id)
    if nxt is not None and nxt.type is StageType.RUN_CHECKS:
        return ctx.decide("C1", ctx.run(nxt), reasons=reasons, entry=last)
    return build.accept_path(ctx, last, ("NO_CHECKS_STAGE", *reasons))


def after_checks(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:  # noqa: PLR0911
    record = last.record
    found = ctx.stage(record.stage_id)
    scope = None if found is None else found.params.scope
    if scope == act.RERUN_SCOPE or (found is None and record.stage_id == "recheck"):
        return _after_recheck(ctx, last, reasons)
    kind = facts.kind_of(record)
    if kind is StageOutcomeKind.SUCCESS:
        return _checks_success(ctx, last, reasons)
    if kind is StageOutcomeKind.MANUAL_PENDING:
        return _manual(ctx, last, reasons)
    if kind is StageOutcomeKind.CHECKS_FAILED:
        return _checks_failed(ctx, last, reasons)
    if kind is StageOutcomeKind.CHECKS_ERROR:
        return _checks_error(ctx, last, reasons, retry_rule="D9", stop_rule="D10")
    if kind is StageOutcomeKind.CHECKS_UNKNOWN:
        return ctx.decide(
            "D11", ctx.repeat(last, StageMode.RETRY), trigger="retry", reasons=reasons, entry=last
        )
    if kind is StageOutcomeKind.TREE_CHANGED:
        if facts.count_outcomes(ctx.state, last, StageOutcomeKind.TREE_CHANGED) <= 1:
            return ctx.decide(
                "D12",
                ctx.repeat(last, StageMode.RETRY),
                trigger="retry",
                reasons=("CHECK_CHANGED_TREE", *reasons),
                entry=last,
            )
        return ctx.escalate("D13", "CHECKS_MUTATED", entry=last, reasons=("CHECKS_MUTATED", *reasons))
    return build.unexpected(ctx, last, reasons)


def _checks_success(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    codes = list(reasons)
    if any(not c.required and c.state in {CheckState.FAILED, CheckState.ERROR} for c in ctx.state.checks):
        codes.append("ADVISORY_CHECK_FAILED")
    if _after_final_correction(ctx):
        return _debt_check(ctx, last, codes)
    return build.accept_path(ctx, last, codes)


def _after_final_correction(ctx: Ctx) -> bool:
    for item in reversed(ctx.entries[:-1]):
        if item.record.stage_type == StageType.RUN_CHECKS.value:
            continue
        executes = (
            item.record.stage_type == StageType.AGENT_STEP.value
            and build.role_of(ctx, item.record) in act.EXECUTE_ROLES
        )
        return executes and item.record.mode is StageMode.FINAL_CORRECTION
    return False


def _debt_check(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    if not ctx.flag("review_accept_findings_only", True):
        return build.accept_path(ctx, last, ("FINDINGS_ONLY_DISABLED", *reasons))
    confirmed = facts.triaged_findings(ctx.state, FindingState.CONFIRMED)
    wide = facts.changes_outside_findings(ctx.state, confirmed)
    output = ctx.state.output
    refs = [("finding", f.id) for f in confirmed]
    if wide or output is None:
        return ctx.escalate(
            "H8",
            "NOT_ACCEPTABLE",
            options=("accept_deviation", "rework", "fail"),
            entry=last,
            extra=facts.review_debt_extra(wide),
            reasons=("REVIEW_DEBT", *reasons),
            refs=refs,
        )
    accepted = Accept(output.id, ReviewClearance.FINDINGS_ONLY)
    return ctx.decide("H7", accepted, reasons=("REVIEW_DEBT", *reasons), refs=refs, entry=last)


def _checks_failed(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    found = ctx.stage(last.record.stage_id)
    handler = None if found is None else found.on.checks_failed
    failed = facts.failed_required(ctx.state)
    refs = [("check", c.id) for c in failed]
    codes = (*facts.loop_progress(ctx.state, last), *reasons)
    if handler == "fail":
        codes = ("CHECKS_FAILED", "HANDLER_FAIL", *codes)
        return ctx.decide("D8", Fail("CHECKS_FAILED"), reasons=codes, refs=refs, entry=last)
    if handler == "escalate":
        codes = ("CHECKS_FAILED", "HANDLER_ESCALATE", *codes)
        return ctx.escalate("D8", "CHECKS_FAILED", entry=last, reasons=codes, refs=refs)
    if ctx.gate:
        if ctx.task.review_rounds < ctx.number("review_max_rounds", act.DEFAULT_REVIEW_MAX_ROUNDS):
            action = CreateFollowups("checks_failed", (), tuple(c.id for c in failed))
            return ctx.decide("D6g", action, trigger="check_failed", reasons=codes, refs=refs, entry=last)
    elif ctx.task.check_fix_rounds < ctx.number("rework_max_rounds", act.DEFAULT_REWORK_MAX_ROUNDS):
        rework = Rework("checks_failed", FeedbackRefs())
        return ctx.decide("D6", rework, trigger="check_failed", reasons=codes, refs=refs, entry=last)
    if build.advisor_available(ctx):
        return build.consult(ctx, last, "D7", f"checks:{last.record.round_no}", codes)
    return build.limit_reached(ctx, last, "D8", codes, refs)


def _checks_error(
    ctx: Ctx, last: StageEntry, reasons: Sequence[str], *, retry_rule: str, stop_rule: str
) -> ActionDecision:
    found = ctx.stage(last.record.stage_id)
    handler = None if found is None else found.on.checks_error
    code, refs = facts.erred_checks_info(ctx.state)
    if handler == "fail":
        return ctx.decide(
            stop_rule, Fail(code), reasons=(code, "HANDLER_FAIL", *reasons), refs=refs, entry=last
        )
    retries = ctx.number("checks_error_retries", act.DEFAULT_CHECKS_ERROR_RETRIES)
    errors = facts.count_outcomes(ctx.state, last, StageOutcomeKind.CHECKS_ERROR)
    if handler != "escalate" and errors <= retries:
        stage = ctx.repeat(last, StageMode.RETRY)
        return ctx.decide(retry_rule, stage, trigger="retry", reasons=reasons, refs=refs, entry=last)
    return ctx.escalate(stop_rule, code, entry=last, reasons=(code, "RETRIES_EXHAUSTED", *reasons), refs=refs)


def _manual(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    pending, failed, has_err = facts.manual_check_status(ctx.state)
    if pending:
        first = pending[0]
        wait = ctx.wait(
            BlockingCode.WAITING_MANUAL_CHECK,
            {"check_execution_id": str(first.id), "check_key": first.check_key},
            f"manual check {first.check_key} waits for a verdict",
        )
        return ctx.decide(
            "D5",
            wait,
            trigger="wait_changed",
            reasons=("WAITING_MANUAL_CHECK", *reasons),
            refs=[("check", c.id) for c in pending],
            entry=last,
        )
    refs = [("check", c.id) for c in failed]
    if has_err:
        return ctx.escalate("D10", "CHECKS_ERROR", entry=last, reasons=("CHECKS_ERROR", *reasons))
    if failed:
        if ctx.gate:
            if ctx.task.review_rounds < ctx.number("review_max_rounds", act.DEFAULT_REVIEW_MAX_ROUNDS):
                action = CreateFollowups("checks_failed", (), tuple(c.id for c in failed))
                return ctx.decide(
                    "E2", action, trigger="manual_verdict", reasons=reasons, refs=refs, entry=last
                )
        elif ctx.task.check_fix_rounds < ctx.number("rework_max_rounds", act.DEFAULT_REWORK_MAX_ROUNDS):
            return ctx.decide(
                "E2",
                Rework("manual_failed", FeedbackRefs()),
                trigger="manual_verdict",
                reasons=(*facts.loop_progress(ctx.state, last), *reasons),
                refs=refs,
                entry=last,
            )
        return build.limit_reached(ctx, last, "E3", reasons, refs)
    return build.accept_path(ctx, last, reasons, via="E1", trigger="manual_verdict")


def _after_recheck(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    kind = facts.kind_of(last.record)
    retries = ctx.number("checks_error_retries", act.DEFAULT_CHECKS_ERROR_RETRIES)
    if kind is StageOutcomeKind.SUCCESS and all(
        c.state is CheckState.PASSED for c in ctx.state.checks if c.required
    ):
        return ctx.decide("K5b", Done(), reasons=reasons, entry=last)
    if kind is StageOutcomeKind.CHECKS_UNKNOWN or (
        kind is StageOutcomeKind.CHECKS_ERROR
        and facts.count_outcomes(ctx.state, last, StageOutcomeKind.CHECKS_ERROR) <= retries
    ):
        repeat = ctx.repeat(last, StageMode.RETRY)
        if not repeat.params.get("recheck_commits"):
            return build.recheck_unbound(ctx, last, reasons)
        return ctx.decide("K5d", repeat, trigger="retry", reasons=reasons, entry=last)
    output = ctx.state.output
    mounts: list[JsonValue] = [] if output is None else [mount.mount for mount in output.manifest.mounts]
    return ctx.escalate(
        "K5c",
        "INTEGRATION_RECHECK_FAILED",
        options=("retry_stage", "fail"),
        entry=last,
        extra={"mounts": mounts, "recheck_commits_required": True},
        refs=[("check", c.id) for c in ctx.state.checks if c.required and c.state is not CheckState.PASSED],
        reasons=("INTEGRATION_RECHECK_FAILED", *reasons),
    )
