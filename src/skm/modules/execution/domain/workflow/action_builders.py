"""Action builders shared by the advance engine's rows (execution §5.1).

Each helper takes the decision context ``Ctx`` and the last stage entry and returns the ``ActionDecision``
of a recurring outcome: accepting, consulting the advisor, routing to triage or a question, rechecking after
integration or escalating an unexpected or invalid result.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, cast

from skm.modules.execution.domain.autonomy import Denied, PolicyDefault, Reused
from skm.modules.execution.domain.blocking_reason import BlockingCode
from skm.modules.execution.domain.check_execution import CheckState
from skm.modules.execution.domain.decision_request import Audience, DecisionKind
from skm.modules.execution.domain.output import OutputSource
from skm.modules.execution.domain.review import ReviewClearance
from skm.modules.execution.domain.risk import review_triggered
from skm.modules.execution.domain.step import RoleId
from skm.modules.execution.domain.workflow.actions import (
    DEFAULT_ADVISOR_MAX_ROUNDS,
    DEFAULT_FOLLOWUPS_MAX,
    DEFAULT_RESULT_RETRIES,
    DEFAULT_REVIEW_MAX_ROUNDS,
    DEFAULT_RISK_THRESHOLD,
    ESCALATION_OPTIONS,
    EXECUTE_ROLES,
    RERUN_SCOPE,
    Accept,
    ActionDecision,
    CreateFollowups,
    Ctx,
    Done,
    RunStage,
)
from skm.modules.execution.domain.workflow.definition import (
    OnOutcome,
    StageDefinition,
    StageParams,
    StageType,
    applies_to_kind,
)
from skm.modules.execution.domain.workflow.predicates import holds
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.domain.workflow.task_facts import (
    evaluate_question_route,
    failed_required,
    gate_reasons,
    kind_of,
    latest_task_review,
    open_major_findings,
    outcome_of,
)

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from uuid import UUID

    from skm.kernel.json_types import JsonValue
    from skm.modules.execution.domain.finding import Finding
    from skm.modules.execution.domain.ids import (
        DecisionRequestId,
    )
    from skm.modules.execution.domain.workflow.history import StageEntry

_WAITING_CODES: Final = frozenset({"MANUAL_PENDING", "DEVIATION_REQUIRED", "BUDGET_EXHAUSTED"})
_OWNER_ONLY: Final = frozenset(
    {"QUESTION_OWNER_ONLY", "QUESTION_GATED", "QUESTION_LIMIT", "QUESTION_CATEGORY_OWNER"}
)


def stage_type_of(value: str) -> StageType | None:
    try:
        return StageType(value)
    except ValueError:
        return None


def role_of(ctx: Ctx, record: object) -> RoleId | None:
    found = ctx.stage(getattr(record, "stage_id", ""))
    return None if found is None else found.role


def continue_with_answer(
    ctx: Ctx, last: StageEntry, extra: Mapping[str, JsonValue], request_ids: Sequence[DecisionRequestId]
) -> RunStage:
    feedback = FeedbackRefs(answer_request_ids=tuple(request_ids)) if request_ids else None
    return ctx.repeat(last, StageMode.CONTINUE_WITH_ANSWER, feedback=feedback, extra=extra)


def row_of(via: str | None, row: str, reasons: Sequence[str]) -> tuple[str, tuple[str, ...]]:
    return (row, tuple(reasons)) if via is None else (via, (f"VIA_{row.upper()}", *reasons))


def advisor_available(ctx: Ctx) -> bool:
    return (
        ctx.flag("advisor_enabled", True)
        and ctx.state.advisor_rounds_used < ctx.number("advisor_max_rounds", DEFAULT_ADVISOR_MAX_ROUNDS)
        and ctx.find("advisor_consult") is not None
    )


def consult(ctx: Ctx, last: StageEntry, rule: str, problem: str, reasons: Sequence[str]) -> ActionDecision:
    advisor = cast("StageDefinition", ctx.find("advisor_consult"))
    return ctx.decide(rule, ctx.run(advisor, extra={"problem_ref": problem}), reasons=reasons, entry=last)


def limit_reached(
    ctx: Ctx, last: StageEntry, rule: str, reasons: Sequence[str], refs: Sequence[tuple[str, UUID]] = ()
) -> ActionDecision:
    return ctx.escalate(
        rule,
        "REWORK_LIMIT_REACHED",
        options=("accept_deviation", "rework", "fail"),
        entry=last,
        extra={"check_fix_rounds": ctx.task.check_fix_rounds, "review_rounds": ctx.task.review_rounds},
        reasons=("REWORK_LIMIT_REACHED", *reasons),
        refs=refs,
    )


def recheck_unbound(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    """K5c: no exact commit per mount is proven; the recheck waits for the owner's ``recheck_commits``."""
    output = ctx.state.output
    mounts: list[JsonValue] = [] if output is None else [m.mount for m in output.manifest.mounts]
    return ctx.escalate(
        "K5c",
        "INTEGRATION_RECHECK_FAILED",
        options=("retry_stage", "fail"),
        entry=last,
        extra={"mounts": mounts, "recheck_commits_required": True},
        reasons=("INTEGRATION_RECHECK_FAILED", "RECHECK_COMMITS_UNKNOWN", *reasons),
    )


def recheck_stage(ctx: Ctx) -> StageDefinition | None:
    """The explicit ``rerun_after_integration`` stage, else the implicit one when the policy asks for it."""

    for item in ctx.wf.stages:
        if item.type is not StageType.RUN_CHECKS or item.params.scope != RERUN_SCOPE:
            continue
        if not applies_to_kind(item, ctx.task.kind):
            continue
        if item.when is not None and not holds(item.when, ctx.state):
            continue
        if item.skip_when is not None and holds(item.skip_when, ctx.state):
            continue
        return item
    if ctx.flag("integration_rerun_checks", False) and ctx.state.rerun_checks_declared:
        return StageDefinition(
            id="recheck",
            type=StageType.RUN_CHECKS,
            for_kinds=frozenset({ctx.task.kind}),
            role=None,
            optional=False,
            params=StageParams(scope="rerun_after_integration"),
            when=None,
            skip_when=None,
            on=OnOutcome(),
        )
    return None


def recheck_after_answer(
    ctx: Ctx, last: StageEntry, commits: Mapping[str, JsonValue], refs: Sequence[tuple[str, UUID]]
) -> ActionDecision | None:
    """J2 on a committed integration whose recheck was never pinned: the owner's commits start the recheck."""
    recheck = recheck_stage(ctx)
    if recheck is None or not commits:
        return None
    extra: dict[str, JsonValue] = {"scope": RERUN_SCOPE, "recheck_commits": dict(commits)}
    return ctx.decide("J2", ctx.run(recheck, extra=extra), trigger="decision_answered", refs=refs, entry=last)


def accept(
    ctx: Ctx,
    last: StageEntry,
    rule: str,
    reasons: Sequence[str],
    clearance: ReviewClearance,
    *,
    trigger: str = "stage_outcome",
    refs: Sequence[tuple[str, UUID]] = (),
) -> ActionDecision:
    output = ctx.state.output
    if output is None:
        return ctx.escalate(
            rule, "NOT_ACCEPTABLE", entry=last, reasons=("OUTPUT_MISSING", *reasons), trigger=trigger
        )
    return ctx.decide(
        rule, Accept(output.id, clearance), trigger=trigger, reasons=reasons, refs=refs, entry=last
    )


def gate_stage(
    ctx: Ctx, last: StageEntry, rule: str, reasons: Sequence[str], *, trigger: str = "stage_outcome"
) -> ActionDecision:
    gate_type = "plan_acceptance" if ctx.task.kind == "plan_acceptance" else "phase_gate"
    stage = ctx.find(gate_type)
    if stage is None:
        return ctx.decide(rule, Done(), trigger=trigger, reasons=("GATE_EMPTY", *reasons), entry=last)
    return ctx.decide(rule, ctx.run(stage), trigger=trigger, reasons=reasons, entry=last)


def accept_path(
    ctx: Ctx,
    last: StageEntry,
    reasons: Sequence[str],
    *,
    via: str | None = None,
    trigger: str = "stage_outcome",
) -> ActionDecision:
    """D1-D4 and D15: where a task goes once its checks passed (review, acceptance or its gate stage)."""
    if ctx.state.output is not None and any(
        entry.record.stage_type == "agent_review"
        and outcome_of(entry).get("output_id") == str(ctx.state.output.id)
        for entry in ctx.entries
    ):
        return _review_round(
            ctx, last, "D1", ("REVIEW_FIX_CHECKED", *reasons), trigger=trigger, read_only=True
        )
    mode = ctx.task.review_mode
    if ctx.gate:
        if mode == "required":
            return _review_round(ctx, last, *row_of(via, "D15", ("D1", *reasons)), trigger=trigger)
        return gate_stage(ctx, last, *row_of(via, "D15", reasons), trigger=trigger)
    if mode == "required":
        return _review_round(ctx, last, *row_of(via, "D1", reasons), trigger=trigger)
    if mode == "self":
        risk = ctx.state.risk
        triggered = (
            ctx.policy.get("review_strategy", "risk_scored") == "risk_scored"
            and risk is not None
            and review_triggered(risk, ctx.number("risk_threshold", DEFAULT_RISK_THRESHOLD))
        )
        if triggered:
            rule, codes = row_of(via, "D2", ("DYNAMIC_REVIEW_ADDED", *reasons))
            return _review_round(ctx, last, rule, codes, trigger=trigger)
        return accept(ctx, last, *row_of(via, "D3", reasons), ReviewClearance.SELF, trigger=trigger)
    return accept(ctx, last, *row_of(via, "D4", reasons), ReviewClearance.WAIVED, trigger=trigger)


def _review_round(
    ctx: Ctx,
    last: StageEntry,
    rule: str,
    reasons: Sequence[str],
    *,
    trigger: str = "stage_outcome",
    read_only: bool = False,
) -> ActionDecision:
    review = ctx.find("agent_review")
    if review is None:
        return ctx.escalate(
            rule, "NOT_ACCEPTABLE", entry=last, reasons=("REVIEW_STAGE_MISSING", *reasons), trigger=trigger
        )
    rounds = ctx.task.review_rounds
    if read_only or (
        review.params.reviewer_with_fix is True
        and rounds + 1 >= ctx.number("review_max_rounds", DEFAULT_REVIEW_MAX_ROUNDS)
    ):
        stage = ctx.run(
            review,
            round_no=rounds + 1,
            extra={"reviewer_with_fix": False, "profile": ctx.task.review_profile or "reviewer"},
        )
    else:
        stage = ctx.run(review, round_no=rounds + 1)
    return ctx.decide(rule, stage, trigger=trigger, reasons=reasons, entry=last)


def to_execute(ctx: Ctx, last: StageEntry, rule: str, reasons: Sequence[str]) -> ActionDecision:
    execute = ctx.find("agent_step", roles=EXECUTE_ROLES)
    if execute is None:
        return ctx.escalate(rule, "WORKFLOW_INCOMPLETE", entry=last, reasons=("NO_EXECUTE_STAGE", *reasons))
    return ctx.decide(rule, ctx.run(execute), reasons=reasons, entry=last)


def to_triage(
    ctx: Ctx, last: StageEntry, rule: str, reasons: Sequence[str], findings: Sequence[Finding]
) -> ActionDecision:
    triage = ctx.find("agent_step", roles=frozenset({RoleId.TRIAGER}))
    if triage is None:
        return ctx.escalate(rule, "WORKFLOW_INCOMPLETE", entry=last, reasons=("NO_TRIAGE_STAGE", *reasons))
    review = latest_task_review(ctx.state)
    refs: list[tuple[str, UUID]] = [] if review is None else [("review", review.id)]
    refs.extend(("finding", f.id) for f in findings)
    return ctx.decide(rule, ctx.run(triage), reasons=reasons, refs=refs, entry=last)


def unexpected(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    record = last.record
    return ctx.escalate(
        "K2",
        "ADVANCE_UNHANDLED",
        entry=last,
        extra={"stage_id": record.stage_id, "outcome": getattr(kind_of(record), "value", None)},
        reasons=("ADVANCE_UNHANDLED", *reasons),
    )


def result_invalid(
    ctx: Ctx, last: StageEntry, *, retry_rule: str, escalate_rule: str, reasons: Sequence[str]
) -> ActionDecision:
    """C10/C10b, F5/F6, H0: the same role repeats with its schema errors until ``step_max_result_retries``."""
    record = last.record
    found = ctx.stage(record.stage_id)
    handler = None if found is None else found.on.result_invalid
    used = ctx.state.history.result_retries_used(record.stage_id)
    limit = ctx.number("step_max_result_retries", DEFAULT_RESULT_RETRIES)
    if handler != "escalate" and used <= limit:
        step = max(last.steps, key=lambda s: s.seq, default=None)
        feedback = (
            FeedbackRefs(schema_errors_step_id=step.id) if step is not None and step.schema_errors else None
        )
        refs = [] if step is None else [("step", step.id)]
        return ctx.decide(
            retry_rule,
            ctx.repeat(last, StageMode.RETRY, feedback=feedback),
            trigger="retry",
            reasons=("RESULT_INVALID", *reasons),
            refs=refs,
            entry=last,
        )
    return ctx.escalate(
        escalate_rule,
        "RESULT_INVALID",
        options=ESCALATION_OPTIONS,
        entry=last,
        extra={"stage_id": record.stage_id},
        reasons=("RESULT_INVALID", "RETRIES_EXHAUSTED", *reasons),
    )


def route_question(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    route, info, gates, digest, refs, revision = evaluate_question_route(
        ctx.state, ctx.policy, ctx.entries, last
    )
    q_id = str(info["question_id"])
    if isinstance(route, Reused):
        again = continue_with_answer(ctx, last, {**info, "answered_by": "reuse"}, ())
        return ctx.decide("C7", again, reasons=("QUESTION_REUSED", *reasons), entry=last, refs=refs)
    if isinstance(route, PolicyDefault):
        again = continue_with_answer(ctx, last, {**info, "answered_by": "policy"}, ())
        return ctx.decide("C5", again, reasons=("ANSWERED_BY_POLICY", *reasons), entry=last, refs=refs)
    if isinstance(route, Denied):
        return ctx.escalate(
            "C6",
            "FORBIDDEN",
            entry=last,
            extra={"text": f"QUESTION_DENIED: {q_id}", **info},
            reasons=(route.code, *reasons),
            refs=refs,
        )
    categories: JsonValue = cast("list[JsonValue]", sorted(gates))
    if route.audience is Audience.OWNER:
        rule = "C2" if route.code in _OWNER_ONLY else "C6"
        return ctx.escalate(
            rule,
            route.code or "QUESTION_ASKED",
            kind=DecisionKind.QUESTION,
            blocking=BlockingCode.WAITING_ANSWER,
            options=(),
            extra={**info, "audience": "owner", "gate_categories": categories, "digest": digest},
            entry=last,
            reasons=(route.code or "QUESTION_ASKED", *reasons),
            refs=refs,
        )
    advisor = ctx.find("advisor_consult")
    if advisor is None:
        return ctx.escalate(
            "C6",
            "QUESTION_NO_ADVISOR",
            kind=DecisionKind.QUESTION,
            blocking=BlockingCode.WAITING_ANSWER,
            extra={**info, "audience": "owner", "gate_categories": categories},
            entry=last,
            reasons=("QUESTION_NO_ADVISOR", *reasons),
            refs=refs,
        )
    panel = route.audience is Audience.CONSILIUM
    extra: dict[str, JsonValue] = {"problem_ref": f"question:{q_id}@{revision}"}
    if panel:
        extra["panel"] = True
    return ctx.decide(
        "C4" if panel else "C3", ctx.run(advisor, extra=extra), reasons=reasons, entry=last, refs=refs
    )


def after_gate(ctx: Ctx, last: StageEntry, stage_type: StageType, reasons: Sequence[str]) -> ActionDecision:
    kind = kind_of(last.record)
    if kind == "accepted":
        if stage_type == "acceptance_gate":
            integrate = ctx.find("integrate")
            output = ctx.state.output
            if integrate is not None and output is not None and output.source is OutputSource.EXECUTOR:
                return ctx.decide("K3", ctx.run(integrate), reasons=reasons, entry=last)
            return ctx.decide("K4", Done(), reasons=reasons, entry=last)
        return ctx.decide("K11" if stage_type == "phase_gate" else "K12", Done(), reasons=reasons, entry=last)
    if kind != "not_acceptable":
        return unexpected(ctx, last, reasons)
    if stage_type == "plan_acceptance":
        return _plan_not_acceptable(ctx, last, reasons)
    return _not_acceptable(ctx, last, reasons)


def _not_acceptable(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    given = gate_reasons(last)
    codes = [str(r.get("code")) for r in given]
    if given and all(code in _WAITING_CODES for code in codes):
        pending = next(
            (c for c in ctx.state.checks if c.required and c.state is CheckState.MANUAL_PENDING), None
        )
        if "MANUAL_PENDING" in codes and pending is not None:
            wait = ctx.wait(
                BlockingCode.WAITING_MANUAL_CHECK,
                {"check_execution_id": str(pending.id), "check_key": pending.check_key},
                f"manual check {pending.check_key} waits for a verdict",
            )
            return ctx.decide(
                "K1",
                wait,
                trigger="wait_changed",
                reasons=(*codes, *reasons),
                refs=[("check", pending.id)],
                entry=last,
            )
        if "BUDGET_EXHAUSTED" in codes and "DEVIATION_REQUIRED" not in codes:
            return ctx.escalate(
                "K1",
                "BUDGET_EXHAUSTED",
                kind=DecisionKind.BUDGET,
                blocking=BlockingCode.BLOCKED_BY_BUDGET,
                options=("raise_budget", "cancel_run"),
                entry=last,
                reasons=(*codes, *reasons),
            )
        return ctx.escalate(
            "K1",
            "DEVIATION_REQUIRED",
            options=("accept_deviation", "rework", "fail"),
            entry=last,
            extra={"reasons": cast("list[JsonValue]", given)},
            reasons=(*codes, *reasons),
        )
    return ctx.escalate(
        "K2",
        "NOT_ACCEPTABLE",
        options=("accept_deviation", "rework", "fail"),
        entry=last,
        extra={"reasons": cast("list[JsonValue]", given)},
        reasons=("NOT_ACCEPTABLE", *codes, *reasons),
    )


def _plan_not_acceptable(ctx: Ctx, last: StageEntry, reasons: Sequence[str]) -> ActionDecision:
    failed = failed_required(ctx.state)
    open_major = open_major_findings(ctx.state)
    rounds_left = ctx.task.review_rounds < ctx.number("review_max_rounds", DEFAULT_REVIEW_MAX_ROUNDS)
    if rounds_left and (failed or open_major):
        cap = ctx.number("followups_max", DEFAULT_FOLLOWUPS_MAX)
        if failed:
            action = CreateFollowups("checks_failed", (), tuple(c.id for c in failed))
            refs = [("check", c.id) for c in failed]
        else:
            action = CreateFollowups("review_findings", tuple(f.id for f in open_major[:cap]), ())
            refs = [("finding", f.id) for f in open_major[:cap]]
        return ctx.decide("K12", action, reasons=("COVERAGE_GAP", *reasons), refs=refs, entry=last)
    return ctx.escalate(
        "K12",
        "NOT_ACCEPTABLE",
        options=("accept_deviation", "rework", "fail"),
        entry=last,
        extra={"coverage": outcome_of(last).get("coverage")},
        reasons=("NOT_ACCEPTABLE", "COVERAGE_GAP", *reasons),
    )
