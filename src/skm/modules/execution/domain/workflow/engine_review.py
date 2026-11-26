"""Pure review, triage, integration and gate rows of decide_advance (execution §5.1)."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Final
from uuid import NAMESPACE_URL, uuid5

from skm.modules.execution.domain.blocking_reason import BlockingCode
from skm.modules.execution.domain.decision_request import DecisionKind
from skm.modules.execution.domain.finding import SEVERITY_RANK, Severity
from skm.modules.execution.domain.retry import RetryAction
from skm.modules.execution.domain.review import ReviewClearance
from skm.modules.execution.domain.role_contracts import ROLE_CONTRACTS, WriteAuthority
from skm.modules.execution.domain.run import RunKind
from skm.modules.execution.domain.session import RouteRef
from skm.modules.execution.domain.stage_record import StageOutcomeKind
from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.task import TaskKind
from skm.modules.execution.domain.workflow import action_builders as build
from skm.modules.execution.domain.workflow import actions as act
from skm.modules.execution.domain.workflow import task_facts as facts
from skm.modules.execution.domain.workflow.actions import ActionDecision, CreateFollowups, Ctx, Done, Rework
from skm.modules.execution.domain.workflow.definition import StageType
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode

if TYPE_CHECKING:
    from collections.abc import Sequence
    from uuid import UUID

    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.workflow.history import StageEntry


_INTEGRATION_TASK_NAMESPACE: Final = uuid5(NAMESPACE_URL, "urn:skm:execution:integration-task")


def role_writes(role: RoleId | None) -> bool:
    return role is not None and ROLE_CONTRACTS[role].write_authority is WriteAuthority.CODE_SCOPE


def runtime_failure(
    ctx: Ctx,
    last: StageEntry,
    *,
    retry_rule: str,
    stop_rule: str,
    reasons: Sequence[str],
    reconcile_rule: str | None = None,
    replan_rule: str | None = None,
    stop_code: str | None = None,
) -> ActionDecision:
    record = last.record
    found = ctx.stage(record.stage_id)
    step = max(last.steps, key=lambda s: s.seq, default=None)
    route = None if step is None else RouteRef(step.runtime_id, step.model, step.effort)
    role = build.role_of(ctx, record)
    decision, error_class = facts.retry_decision(
        ctx.state,
        ctx.policy,
        ctx.entries,
        last,
        role=role,
        role_writes=role_writes(role)
        or (step is not None and step.admission.get("reviewer_with_fix") is True),
        stage_retries_cap=None if found is None else found.params.retries,
        route=route,
        max_infra_retries=ctx.number("step_max_infra_retries", act.DEFAULT_INFRA_RETRIES),
        retry_budget=ctx.number("retry_budget_total_max", act.DEFAULT_RETRY_BUDGET),
        max_wait_s=ctx.number("retry_provider_wait_max_seconds", act.DEFAULT_PROVIDER_WAIT_MAX_S),
    )
    codes = (*reasons, *decision.reason_codes)
    if decision.action in facts.REPEATS:
        not_before = facts.retry_not_before(ctx.now, decision.wait_seconds)
        action = ctx.repeat(last, StageMode.RETRY, not_before=not_before, route_override=decision.route)
        return ctx.decide(retry_rule, action, trigger="retry", reasons=codes, entry=last)
    if decision.action is RetryAction.RECONCILE and reconcile_rule is not None:
        mode = (
            StageMode.RECONCILE
            if record.stage_type == StageType.INTEGRATE.value
            else StageMode.RESUME_INTERRUPTED
        )
        feedback = FeedbackRefs(interrupted_stage_record_id=record.id)
        return ctx.decide(
            reconcile_rule, ctx.repeat(last, mode, feedback=feedback), reasons=codes, entry=last
        )
    if decision.action is RetryAction.REPLAN and replan_rule is not None:
        return ctx.escalate(
            replan_rule,
            "CONTEXT_OVER_BUDGET",
            options=("split_task", "raise_budget", "retry_stage"),
            entry=last,
            reasons=codes,
        )
    code, blocking = facts.retry_stop_outcome(decision, error_class, last, stop_code)
    return ctx.escalate(
        stop_rule,
        code,
        blocking=blocking,
        options=act.ESCALATION_OPTIONS,
        entry=last,
        extra={"stage_id": record.stage_id, "error_class": error_class},
        reasons=codes,
    )


def after_review(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:  # noqa: PLR0911
    record = last.record
    kind = facts.kind_of(record)
    found = ctx.stage(record.stage_id)
    verdicts = {
        StageOutcomeKind.VERDICT_GREEN,
        StageOutcomeKind.VERDICT_ATTENTION,
        StageOutcomeKind.VERDICT_RED,
    }
    if kind in verdicts and ctx.state.run.kind is RunKind.REVIEW_REQUEST:
        return build.accept(ctx, last, "F7", ("REVIEW_REPORT", *reasons), ReviewClearance.REPORT)
    if kind in verdicts and facts.outcome_of(last).get("output_id") is not None:
        checks = ctx.find(StageType.RUN_CHECKS, scope="task")
        if checks is None:
            return ctx.escalate(
                "F8", "WORKFLOW_INCOMPLETE", entry=last, reasons=("NO_CHECKS_STAGE", *reasons)
            )
        return ctx.decide("F8", ctx.run(checks), entry=last, reasons=("REVIEW_FIX_SEALED", *reasons))
    if kind is StageOutcomeKind.VERDICT_GREEN:
        open_major = facts.open_major_findings(ctx.state)
        if open_major:
            return build.to_triage(ctx, last, "F4", ("GREEN_WITH_OPEN_FINDINGS", *reasons), open_major)
        if ctx.gate:
            return build.gate_stage(ctx, last, "F1", reasons)
        return build.accept(ctx, last, "F1", reasons, ReviewClearance.GREEN)
    if kind is StageOutcomeKind.VERDICT_ATTENTION:
        handler = None if found is None else found.on.verdict_attention
        if handler == "ask_owner" or ctx.policy.get("review_attention_policy") == "ask_owner":
            return ctx.escalate(
                "F3",
                "NOT_ACCEPTABLE",
                options=("accept_deviation", "rework", "fail"),
                entry=last,
                reasons=("ATTENTION_ASK_OWNER", *reasons),
            )
        return build.to_triage(ctx, last, "F2", reasons, ())
    if kind is StageOutcomeKind.VERDICT_RED:
        handler = None if found is None else found.on.verdict_red
        if handler == "escalate":
            return ctx.escalate(
                "F4",
                "NOT_ACCEPTABLE",
                options=("rework", "fail"),
                entry=last,
                reasons=("REVIEW_RED", *reasons),
            )
        return build.to_triage(ctx, last, "F4", reasons, ())
    if kind is StageOutcomeKind.RESULT_INVALID:
        return build.result_invalid(ctx, last, retry_rule="F5", escalate_rule="F6", reasons=reasons)
    if kind is StageOutcomeKind.RUNTIME_ERROR:
        return runtime_failure(
            ctx, last, retry_rule="F5", stop_rule="F6", stop_code="RESULT_INVALID", reasons=reasons
        )
    return build.unexpected(ctx, last, reasons)


def after_triage(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:  # noqa: PLR0911
    kind = facts.kind_of(last.record)
    if kind is StageOutcomeKind.RESULT_INVALID:
        return build.result_invalid(ctx, last, retry_rule="H0", escalate_rule="H0", reasons=reasons)
    if kind is StageOutcomeKind.RUNTIME_ERROR:
        return runtime_failure(
            ctx, last, retry_rule="H0", stop_rule="H0", stop_code="RESULT_INVALID", reasons=reasons
        )
    if kind is not StageOutcomeKind.SUCCESS:
        return build.unexpected(ctx, last, reasons)
    _, rejected, base, codes, blocking, refs = facts.triage_facts(ctx.state, last, ctx.gate, reasons)
    rounds_left = ctx.task.review_rounds < ctx.number("review_max_rounds", act.DEFAULT_REVIEW_MAX_ROUNDS)
    if blocking:
        if rounds_left and ctx.gate:
            cap = ctx.number("followups_max", act.DEFAULT_FOLLOWUPS_MAX)
            chosen = blocking[:cap]
            cut = ("FOLLOWUPS_TRUNCATED",) if len(blocking) > cap else ()
            action = CreateFollowups("review_findings", tuple(f.id for f in chosen), ())
            return ctx.decide(
                "H1g",
                action,
                trigger="review_findings",
                reasons=(*cut, *codes),
                refs=[*base, *(("finding", f.id) for f in chosen)],
                entry=last,
            )
        if rounds_left:
            return ctx.decide(
                "H1",
                Rework("review_findings", FeedbackRefs()),
                trigger="review_findings",
                reasons=codes,
                refs=refs,
                entry=last,
            )
        if any(f.severity is Severity.BLOCKER for f in blocking):
            return build.limit_reached(ctx, last, "H3", ("CONFIRMED_BLOCKER", *codes), refs)
        execute = ctx.find(StageType.AGENT_STEP, roles=act.EXECUTE_ROLES)
        if (
            not ctx.gate
            and execute is not None
            and ctx.flag("review_final_correction", True)
            and not _final_correction_used(ctx)
        ):
            stage = ctx.run(execute, StageMode.FINAL_CORRECTION)
            return ctx.decide("H2", stage, trigger="review_findings", reasons=codes, refs=refs, entry=last)
        return build.limit_reached(ctx, last, "H3", ("FINAL_CORRECTION_UNAVAILABLE", *codes), refs)
    if any(SEVERITY_RANK[f.severity] >= facts.MAJOR for f in rejected):
        refs = [*base, *(("finding", f.id) for f in rejected)]
        if build.advisor_available(ctx):
            return build.consult(ctx, last, "H4", f"findings:{last.record.round_no}", codes)
        return ctx.escalate(
            "H5",
            "NOT_ACCEPTABLE",
            options=("accept_rejection", "rework", "fail"),
            entry=last,
            reasons=("REJECTED_MAJOR", *codes),
            refs=refs,
        )
    if ctx.gate:
        return build.gate_stage(ctx, last, "H6", codes)
    return build.accept(ctx, last, "H6", codes, ReviewClearance.CLEARED_BY_TRIAGE, refs=base)


def _final_correction_used(ctx: Ctx) -> bool:
    return any(
        e.record.mode is StageMode.FINAL_CORRECTION and build.role_of(ctx, e.record) in act.EXECUTE_ROLES
        for e in ctx.entries
    )


def after_advice(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    kind = facts.kind_of(last.record)
    if ctx.task.kind is TaskKind.PLAN_AUDIT and kind in {StageOutcomeKind.SUCCESS, StageOutcomeKind.HELD}:
        return ctx.decide("I6", Done(), reasons=("READINESS_ADVICE", *reasons), entry=last)
    previous = facts.advice_origin(ctx.entries, last)
    prev_role = None if previous is None else build.role_of(ctx, previous.record)
    problem, step, refs, ids = facts.advice_facts(ctx.state, last, previous, prev_role)
    if kind is StageOutcomeKind.HELD:
        advice = facts.outcome_of(last).get("advice")
        question = problem == "question"
        return ctx.escalate(
            "I4",
            "ADVICE_HELD",
            kind=DecisionKind.QUESTION if question else DecisionKind.ESCALATION,
            blocking=BlockingCode.WAITING_ANSWER if question else BlockingCode.WAITING_OWNER,
            extra={
                "advice": advice,
                "held_reason": facts.outcome_of(last).get("held_reason"),
                "problem": problem,
            },
            entry=last,
            reasons=("ADVICE_HELD", *reasons),
            refs=refs,
        )
    if kind is StageOutcomeKind.SUCCESS:
        if problem == "question" and previous is not None:
            stage = build.continue_with_answer(ctx, previous, {"answered_by": "advisor"}, ids)
            return ctx.decide(
                "I1", stage, trigger="decision_answered", reasons=reasons, refs=refs, entry=last
            )
        if problem == "checks":
            execute = ctx.find(StageType.AGENT_STEP, roles=act.EXECUTE_ROLES)
            if execute is not None:
                feedback = FeedbackRefs(advice_step_id=step.id if step is not None else None)
                stage = ctx.run(execute, StageMode.REWORK, feedback=feedback)
                return ctx.decide(
                    "I2",
                    stage,
                    trigger="check_failed",
                    reasons=("ADVICE_EXTRA_ROUND", *reasons),
                    refs=refs,
                    entry=last,
                )
        if problem == "findings" and previous is not None:
            feedback = FeedbackRefs(advice_step_id=step.id if step is not None else None)
            stage = ctx.repeat(previous, StageMode.RETRIAGE_WITH_ADVICE, feedback=feedback)
            return ctx.decide("I3", stage, trigger="review_findings", reasons=reasons, refs=refs, entry=last)
        return ctx.escalate(
            "I5", "ADVANCE_UNHANDLED", entry=last, reasons=("ADVICE_UNUSABLE", *reasons), refs=refs
        )
    if kind in {StageOutcomeKind.RUNTIME_ERROR, StageOutcomeKind.RESULT_INVALID}:
        return _advisor_absent(ctx, last, problem, ("ADVISOR_FAILED", *reasons), refs)
    return build.unexpected(ctx, last, reasons)


def _advisor_absent(
    ctx: Ctx, last: StageEntry, problem: str, reasons: Sequence[str], refs: Sequence[tuple[str, UUID]]
) -> ActionDecision:
    if problem == "question":
        return ctx.escalate(
            "I5",
            "QUESTION_NO_ADVISOR",
            kind=DecisionKind.QUESTION,
            blocking=BlockingCode.WAITING_ANSWER,
            extra={"audience": "owner"},
            entry=last,
            reasons=("QUESTION_NO_ADVISOR", *reasons),
            refs=refs,
        )
    code = "NOT_ACCEPTABLE" if problem == "findings" else "REWORK_LIMIT_REACHED"
    first = "accept_rejection" if problem == "findings" else "accept_deviation"
    tag = "REJECTED_MAJOR" if problem == "findings" else "REWORK_LIMIT_REACHED"
    return ctx.escalate(
        "I5", code, options=(first, "rework", "fail"), entry=last, reasons=(tag, *reasons), refs=refs
    )


def after_integrate(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:  # noqa: PLR0911
    record = last.record
    kind = facts.kind_of(record)
    found = ctx.stage(record.stage_id)
    out = facts.outcome_of(last)
    if kind is StageOutcomeKind.SUCCESS:
        recheck = build.recheck_stage(ctx)
        if recheck is None:
            return ctx.decide("K5", Done(), reasons=reasons, entry=last)
        pinned = facts.integrated_commits(ctx.state, out)
        if not pinned:
            return build.recheck_unbound(ctx, last, reasons)
        extra: dict[str, JsonValue] = {"scope": act.RERUN_SCOPE, "recheck_commits": pinned}
        return ctx.decide("K5a", ctx.run(recheck, extra=extra), reasons=reasons, entry=last)
    if kind is StageOutcomeKind.CONFLICT:
        if found is not None and found.on.conflict == "escalate":
            return ctx.escalate(
                "K10", "INTEGRATION_CONFLICT", entry=last, reasons=("INTEGRATION_CONFLICT", *reasons)
            )
        task_id = uuid5(_INTEGRATION_TASK_NAMESPACE, f"{ctx.task.id}:{record.id}")
        wait = ctx.wait(
            BlockingCode.BLOCKED_BY_INTEGRATION,
            {"integration_task_id": str(task_id)},
            "an integration task resolves the conflict",
        )
        return ctx.decide(
            "K6", wait, trigger="integration", reasons=("INTEGRATION_TASK_REQUIRED", *reasons), entry=last
        )
    if kind is StageOutcomeKind.OUTCOME_UNKNOWN:
        feedback = FeedbackRefs(interrupted_stage_record_id=record.id)
        return ctx.decide(
            "K7",
            ctx.repeat(last, StageMode.RECONCILE, feedback=feedback),
            reasons=("OUTCOME_UNKNOWN", *reasons),
            entry=last,
        )
    if kind is StageOutcomeKind.APPROVAL_REQUIRED:
        return _approval(ctx, last, out, reasons)
    if kind is StageOutcomeKind.RUNTIME_ERROR:
        if record.error_code == "INTEGRATION_HOST_MISMATCH":
            return ctx.escalate(
                "K13",
                "INTEGRATION_HOST_MISMATCH",
                options=("new_attempt", "fail"),
                entry=last,
                reasons=("INTEGRATION_HOST_MISMATCH", *reasons),
            )
        stop = "INTEGRATION_CONFLICT" if record.error_code == "INTEGRATION_CONFLICT" else None
        return runtime_failure(
            ctx, last, retry_rule="K9", stop_rule="K10", reconcile_rule="K7", stop_code=stop, reasons=reasons
        )
    return build.unexpected(ctx, last, reasons)


def _approval(
    ctx: Ctx, last: StageEntry, out: Mapping[str, JsonValue], reasons: Sequence[str]
) -> ActionDecision:
    intent_id, effect_id = out.get("intent_id"), out.get("effect_id")
    if out.get("intent_state") == "approved" and isinstance(effect_id, str):
        integrate = ctx.stage(last.record.stage_id)
        if integrate is not None:
            stage = ctx.run(integrate, extra={"effect_id": effect_id})
            return ctx.decide("K8a", stage, reasons=("INTENT_APPROVED", *reasons), entry=last)
    return ctx.escalate(
        "K8",
        "APPROVAL_REQUIRED",
        kind=DecisionKind.APPROVAL,
        blocking=BlockingCode.WAITING_APPROVAL,
        extra={"refs": {"intent_id": intent_id, "effect_id": effect_id}, "intent_id": intent_id},
        entry=last,
        reasons=("APPROVAL_REQUIRED", *reasons),
    )


def after_gate(ctx: Ctx, last: StageEntry, stage_type: StageType, reasons: Sequence[str]) -> ActionDecision:
    """K12 coverage gaps create independent work while review rounds remain."""
    if (
        stage_type is StageType.PLAN_ACCEPTANCE
        and facts.kind_of(last.record) is StageOutcomeKind.NOT_ACCEPTABLE
    ):
        codes = tuple(str(r.get("code")) for r in facts.gate_reasons(last))
        coverage = {"CRITERION_UNVERIFIED", "REQUIREMENT_UNCOVERED"}
        if (
            codes
            and set(codes) <= coverage
            and ctx.task.review_rounds < ctx.number("review_max_rounds", act.DEFAULT_REVIEW_MAX_ROUNDS)
        ):
            return ctx.decide(
                "K12",
                CreateFollowups("checks_failed", (), ()),
                reasons=("COVERAGE_GAP", *codes, *reasons),
                entry=last,
            )
    return build.after_gate(ctx, last, stage_type, reasons)


def empty_gate(ctx: Ctx, rule: str, last: StageEntry | None = None) -> ActionDecision:
    """GATE_EMPTY is never a waiver of a required check or review (R13)."""
    required = bool((ctx.state.gate or {}).get("required_checks")) or any(
        c.required for c in ctx.state.checks
    )
    if required or ctx.task.review_mode == "required":
        return ctx.escalate(
            rule, "GATE_UNSUPPORTED_BY_WORKFLOW", entry=last, reasons=("GATE_UNSUPPORTED_BY_WORKFLOW",)
        )
    return ctx.decide(rule, Done(), reasons=("GATE_EMPTY",), entry=last)
