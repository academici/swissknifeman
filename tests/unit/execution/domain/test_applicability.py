"""Stage applicability and the closed predicate set in the advance engine (execution §5.3).

``for_kinds``, ``when`` and ``skip_when`` decide which stage follows another; the predicates are pure reads of
the given ``TaskState``. A stage that does not apply is skipped without a record, and gate stage types serve
only their own task kinds whatever ``for_kinds`` says.
"""

from __future__ import annotations

import dataclasses
from typing import Any, cast

import pytest

from skm.kernel.json_types import JsonValue
from skm.modules.execution.domain.check_execution import CheckKind, CheckState
from skm.modules.execution.domain.decision_request import Audience, DecisionKind, DecisionState
from skm.modules.execution.domain.review import ReviewClearance, Verdict
from skm.modules.execution.domain.risk import RiskScore
from skm.modules.execution.domain.run import RunKind
from skm.modules.execution.domain.task import ReviewMode, TaskKind, TaskStatus
from skm.modules.execution.domain.workflow.actions import Accept, Done, Escalate, Noop, RunStage
from skm.modules.execution.domain.workflow.definition import (
    WORKFLOW_SCHEMA,
    WorkflowDefinition,
    applies_to_kind,
    parse_workflow,
)
from skm.modules.execution.domain.workflow.engine import TaskState
from skm.modules.execution.domain.workflow.predicates import (
    AllPredicates,
    AnyPredicates,
    CheckOutcome,
    CheckOutcomeIs,
    HasOpenQuestions,
    ReviewModeIs,
    ReviewVerdictIs,
    RiskAtLeast,
    RoundsBelow,
    RoundsCounter,
    RouteFlag,
    RunKindIn,
    TaskKindIn,
    WorkKind,
    WorkKindIn,
    check_outcome,
    evaluate,
    holds,
    parse_condition,
)
from unit.execution.domain.test_acceptance import CHECK_MANUAL, make_check, make_review
from unit.execution.domain.test_advance_table import (
    QUICK,
    RESEARCH,
    REVIEWED,
    K,
    decide,
    e,
    expect,
    failed_check,
    make_state,
    passed_checks,
    reasons,
    request,
)
from unit.execution.domain.test_session import uid


def doc(*stages: dict[str, Any]) -> WorkflowDefinition:
    document: dict[str, Any] = {
        "schema": WORKFLOW_SCHEMA,
        "id": "probe",
        "version": "1.0.0",
        "applies_to": ["code"],
        "stage": [{"id": "prepare", "type": "prepare_environment"}, *stages],
    }
    definition, violations = parse_workflow(cast("JsonValue", document))
    assert violations == (), violations
    assert definition is not None
    return definition


EXECUTE = {"id": "execute", "type": "agent_step", "role": "executor"}
GATE_PREPARE = {
    "id": "gate_prepare",
    "type": "prepare_environment",
    "for_kinds": ["item_gate", "phase_gate", "group_review", "plan_acceptance"],
}
REVIEW = {"id": "review", "type": "agent_review", "role": "reviewer"}
ACCEPT = {"id": "accept", "type": "acceptance_gate"}


def next_stage(state: TaskState, wf: WorkflowDefinition) -> str | None:
    """The stage the engine runs right after a successful prepare (the first applicable one)."""
    decision = decide(dataclasses.replace(state, history=state.history), wf)
    action = decision.action
    return action.stage_id if isinstance(action, RunStage) else None


# ------------------------------------------------------------------------------- the predicate set


@pytest.mark.parametrize(
    ("predicate", "task", "expected"),
    [
        (ReviewModeIs(ReviewMode.REQUIRED), {"review_mode": ReviewMode.REQUIRED}, True),
        (ReviewModeIs(ReviewMode.REQUIRED), {"review_mode": ReviewMode.SELF}, False),
        (WorkKindIn(frozenset({WorkKind.CODE, WorkKind.DOCS})), {"work_kind": "docs"}, True),
        (WorkKindIn(frozenset({WorkKind.CODE})), {"work_kind": "research"}, False),
        (RoundsBelow(RoundsCounter.REVIEW_ROUNDS, 2), {"review_rounds": 1}, True),
        (RoundsBelow(RoundsCounter.REVIEW_ROUNDS, 2), {"review_rounds": 2}, False),
        (RoundsBelow(RoundsCounter.CHECK_FIX_ROUNDS, 1), {"check_fix_rounds": 0}, True),
        (RoundsBelow(RoundsCounter.CHECK_FIX_ROUNDS, 1), {"check_fix_rounds": 1}, False),
        (TaskKindIn(frozenset({TaskKind.ITEM, TaskKind.UNIT})), {}, True),
        (TaskKindIn(frozenset({TaskKind.FOLLOWUP})), {}, False),
    ],
)
def test_task_predicates(predicate: Any, task: dict[str, Any], expected: bool) -> None:
    assert evaluate(predicate, make_state(task=task)) is expected


def test_route_flag_reads_the_route_and_the_scout_mode_of_the_policy() -> None:
    state = make_state(route_flags=frozenset({"research"}))
    assert evaluate(RouteFlag("research"), state)
    assert not evaluate(RouteFlag("scout"), state)
    always = dataclasses.replace(state, effective_policy={"scout_mode": "always"})
    assert evaluate(RouteFlag("scout"), always)
    assert not evaluate(RouteFlag("research"), make_state())
    # the scout mode never turns on another flag
    assert not evaluate(RouteFlag("phase_review"), always)


def test_risk_at_least_is_false_without_a_risk_score() -> None:
    assert not evaluate(RiskAtLeast(0), make_state())
    assert evaluate(RiskAtLeast(60), make_state(risk=RiskScore(60, (), ())))
    assert not evaluate(RiskAtLeast(61), make_state(risk=RiskScore(60, (), ())))


def test_run_kind_predicate() -> None:
    plan = make_state()
    request_run = make_state(run={"kind": RunKind.REVIEW_REQUEST, "review_request_id": uid(11)})
    only = RunKindIn(frozenset({RunKind.REVIEW_REQUEST}))
    assert not evaluate(only, plan)
    assert evaluate(only, request_run)


def test_review_verdict_reads_the_latest_review_of_the_current_output_only() -> None:
    red = make_review(verdict_=Verdict.RED, round_no=1)
    green = make_review(uid(602), round_no=2, verdict_=Verdict.GREEN)
    other = make_review(uid(603), round_no=3, verdict_=Verdict.RED, output_id=uid(999))
    state = make_state(reviews=(red, green, other))
    assert evaluate(ReviewVerdictIs(Verdict.GREEN), state)
    assert not evaluate(ReviewVerdictIs(Verdict.RED), state)
    assert not evaluate(ReviewVerdictIs(Verdict.GREEN), make_state())
    assert not evaluate(ReviewVerdictIs(Verdict.RED), make_state(output=None, reviews=(red,)))


def test_open_questions_count_only_open_question_requests() -> None:
    question = request(DecisionKind.QUESTION, n=70)
    answered = request(DecisionKind.QUESTION, n=71, state=DecisionState.ANSWERED)
    escalation = request(DecisionKind.ESCALATION, n=72)
    assert evaluate(HasOpenQuestions(True), make_state(open_requests=(question,)))
    assert not evaluate(HasOpenQuestions(True), make_state(open_requests=(answered, escalation)))
    assert evaluate(HasOpenQuestions(False), make_state(open_requests=(answered, escalation)))
    advisor = request(DecisionKind.QUESTION, audience=Audience.ADVISOR, n=73)
    assert evaluate(HasOpenQuestions(True), make_state(open_requests=(advisor,)))


@pytest.mark.parametrize(
    ("states", "outcome"),
    [
        ((CheckState.PASSED, CheckState.PASSED), CheckOutcome.PASSED),
        ((CheckState.PASSED, CheckState.FAILED), CheckOutcome.FAILED),
        ((CheckState.FAILED, CheckState.ERROR), CheckOutcome.ERROR),
        ((CheckState.UNKNOWN,), CheckOutcome.ERROR),
        ((CheckState.PASSED, CheckState.RUNNING), None),
        ((CheckState.PENDING,), None),
        ((), CheckOutcome.PASSED),
    ],
)
def test_check_outcome_of_the_latest_round(
    states: tuple[CheckState, ...], outcome: CheckOutcome | None
) -> None:
    checks = tuple(make_check(uid(500 + n), state=value) for n, value in enumerate(states))
    state = make_state(checks=checks)
    assert check_outcome(state) is outcome
    if outcome is not None:
        assert evaluate(CheckOutcomeIs(outcome), state)
        others = set(CheckOutcome) - {outcome}
        assert not any(evaluate(CheckOutcomeIs(other), state) for other in others)


def test_check_outcome_ignores_advisory_checks_and_open_manual_ones_make_it_undecided() -> None:
    advisory = make_check(uid(502), state=CheckState.FAILED, required=False)
    assert check_outcome(make_state(checks=(*passed_checks(), advisory))) is CheckOutcome.PASSED
    manual = make_check(CHECK_MANUAL, kind=CheckKind.MANUAL, state=CheckState.MANUAL_PENDING)
    assert check_outcome(make_state(checks=(*passed_checks(), manual))) is None


def test_all_and_any_conditions() -> None:
    state = make_state(task={"review_mode": ReviewMode.REQUIRED, "review_rounds": 1})
    yes, no = ReviewModeIs(ReviewMode.REQUIRED), ReviewModeIs(ReviewMode.WAIVED)
    assert holds(yes, state)
    assert holds(AllPredicates((yes, RoundsBelow(RoundsCounter.REVIEW_ROUNDS, 2))), state)
    assert not holds(AllPredicates((yes, no)), state)
    assert holds(AnyPredicates((no, yes)), state)
    assert not holds(AnyPredicates((no, no)), state)


def test_parsed_conditions_evaluate_like_the_typed_ones() -> None:
    condition = parse_condition({"any": [{"review_mode": "required"}, {"risk_at_least": 60}]})
    assert holds(condition, make_state(task={"review_mode": ReviewMode.REQUIRED}))
    assert not holds(condition, make_state(task={"review_mode": ReviewMode.SELF}))
    assert holds(condition, make_state(task={"review_mode": ReviewMode.SELF}, risk=RiskScore(80, (), ())))


# -------------------------------------------------------------------------------- applicability


def test_the_first_applicable_stage_wins_in_workflow_order() -> None:
    wf = doc(EXECUTE, REVIEW, ACCEPT)
    assert next_stage(make_state(e("prepare")), wf) == "execute"


def test_when_false_skips_the_stage_without_a_record() -> None:
    scout = {"id": "scout", "type": "agent_step", "role": "scout", "when": {"route_flag": "scout"}}
    wf = doc(scout, EXECUTE)
    plain = make_state(e("prepare"))
    assert next_stage(plain, wf) == "execute"
    flagged = make_state(e("prepare"), route_flags=frozenset({"scout"}))
    assert next_stage(flagged, wf) == "scout"
    assert plain.history.of_stage("scout") == ()


def test_skip_when_true_skips_the_stage() -> None:
    after = {**EXECUTE, "id": "later", "skip_when": {"review_mode": "waived"}}
    wf = doc(after, {**EXECUTE, "id": "second"})
    waived = make_state(e("prepare"), task={"review_mode": ReviewMode.WAIVED})
    required = make_state(e("prepare"), task={"review_mode": ReviewMode.REQUIRED})
    assert next_stage(waived, wf) == "second"
    assert next_stage(required, wf) == "later"


def test_when_and_skip_when_together_both_have_to_allow_the_stage() -> None:
    stage = {
        **EXECUTE,
        "id": "both",
        "when": {"work_kind": ["code"]},
        "skip_when": {"review_mode": "waived"},
    }
    wf = doc(stage, {**EXECUTE, "id": "fallback"})
    code = {"work_kind": "code"}
    assert next_stage(make_state(e("prepare"), task=code), wf) == "both"
    assert (
        next_stage(make_state(e("prepare"), task={**code, "review_mode": ReviewMode.WAIVED}), wf)
        == "fallback"
    )
    assert next_stage(make_state(e("prepare"), task={"work_kind": "docs"}), wf) == "fallback"


def test_for_kinds_limits_a_stage_to_its_task_kinds() -> None:
    only_followups = {**EXECUTE, "id": "special", "for_kinds": ["followup"]}
    wf = doc(only_followups, {**EXECUTE, "id": "general"})
    assert next_stage(make_state(e("prepare"), kind=TaskKind.FOLLOWUP), wf) == "special"
    assert next_stage(make_state(e("prepare"), kind=TaskKind.ITEM), wf) == "general"
    stage = wf.stages[1]
    assert applies_to_kind(stage, TaskKind.FOLLOWUP)
    assert not applies_to_kind(stage, TaskKind.ITEM)


def test_gate_stage_types_serve_only_their_own_task_kinds() -> None:
    phase = {"id": "phase_gate", "type": "phase_gate"}
    plan = {"id": "plan_acceptance", "type": "plan_acceptance"}
    wf = doc(GATE_PREPARE, phase, plan, EXECUTE)
    assert next_stage(make_state(e("prepare"), kind=TaskKind.ITEM), wf) == "execute"
    assert next_stage(make_state(e("gate_prepare"), kind=TaskKind.PHASE_GATE), wf) == "phase_gate"
    assert next_stage(make_state(e("gate_prepare"), kind=TaskKind.GROUP_REVIEW), wf) == "phase_gate"
    assert next_stage(make_state(e("gate_prepare"), kind=TaskKind.PLAN_ACCEPTANCE), wf) == "plan_acceptance"


def test_acceptance_gate_never_applies_to_a_gate_task() -> None:
    wf = doc(GATE_PREPARE, ACCEPT, {"id": "phase_gate", "type": "phase_gate"})
    assert next_stage(make_state(e("gate_prepare"), kind=TaskKind.ITEM_GATE), wf) == "phase_gate"
    assert next_stage(make_state(e("prepare"), kind=TaskKind.ITEM), wf) == "accept"


def test_a_gate_without_an_applicable_stage_is_accepted_at_once_as_empty() -> None:
    wf = doc(EXECUTE)
    decision = decide(
        make_state(e("gate_prepare"), kind=TaskKind.ITEM_GATE, task={"review_mode": ReviewMode.WAIVED}), wf
    )
    expect(decision, "A6", Done)
    assert "GATE_EMPTY" in reasons(decision)


@pytest.mark.parametrize("required", ["review", "check"])
def test_an_empty_gate_never_waives_required_review_or_checks(required: str) -> None:
    state = dataclasses.replace(
        make_state(
            e("gate_prepare"),
            kind=TaskKind.ITEM_GATE,
            task={"review_mode": ReviewMode.REQUIRED if required == "review" else ReviewMode.WAIVED},
        ),
        gate={"required_checks": ["required"] if required == "check" else []},
    )
    decision = decide(state, doc(EXECUTE))
    expect(decision, "A6", Escalate, code="GATE_UNSUPPORTED_BY_WORKFLOW")
    assert "GATE_EMPTY" not in reasons(decision)


def test_gate_rework_needs_no_gate_executor_because_it_creates_followups() -> None:
    workflow = doc(
        GATE_PREPARE,
        {**EXECUTE, "for_kinds": ["unit"]},
        {
            "id": "checks",
            "type": "run_checks",
            "for_kinds": ["unit", "phase_gate"],
            "on": {"checks_failed": "rework"},
        },
    )
    executor = next(s for s in workflow.stages if s.id == "execute")
    assert not applies_to_kind(executor, TaskKind.PHASE_GATE)
    checks = next(s for s in workflow.stages if s.id == "checks")
    assert applies_to_kind(checks, TaskKind.PHASE_GATE)
    assert checks.on.checks_failed == "rework"


def test_a_work_workflow_without_an_applicable_stage_escalates_instead_of_stalling() -> None:
    wf = doc({**EXECUTE, "for_kinds": ["followup"]})
    decision = decide(make_state(e("prepare"), kind=TaskKind.ITEM), wf)
    assert decision.cause["advance_rule"] == "A3"
    assert "NO_APPLICABLE_STAGE" in reasons(decision)


# ----------------------------------------------------------------- the shipped workflows by kind


@pytest.mark.parametrize(
    ("wf", "kind", "flags", "expected"),
    [
        (REVIEWED, TaskKind.ITEM, frozenset[str](), "execute"),
        (REVIEWED, TaskKind.ITEM, frozenset({"scout"}), "scout"),
        (REVIEWED, TaskKind.FOLLOWUP, frozenset[str](), "execute"),
        (REVIEWED, TaskKind.INTEGRATION, frozenset[str](), "execute"),
        (QUICK, TaskKind.UNIT, frozenset[str](), "execute"),
        (RESEARCH, TaskKind.ITEM, frozenset[str](), "research"),
    ],
)
def test_the_stage_after_prepare_of_the_shipped_workflows(
    wf: WorkflowDefinition, kind: TaskKind, flags: frozenset[str], expected: str
) -> None:
    assert next_stage(make_state(e("prepare"), kind=kind, route_flags=flags), wf) == expected


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (TaskKind.ITEM_GATE, "gate_checks"),
        (TaskKind.PHASE_GATE, "gate_checks"),
        (TaskKind.PLAN_ACCEPTANCE, "gate_checks"),
        (TaskKind.GROUP_REVIEW, "review"),  # a group review has no gate checks of its own
    ],
)
def test_a_gate_of_the_reviewed_workflow_runs_its_gate_checks_first(kind: TaskKind, expected: str) -> None:
    assert next_stage(make_state(e("gate_prepare"), kind=kind), REVIEWED) == expected


def test_quick_fix_reviews_only_when_the_plan_requires_it_or_the_risk_is_high() -> None:
    def after_checks(mode: ReviewMode, score: int | None) -> Any:
        risk = None if score is None else RiskScore(score, (), ())
        state = make_state(
            e("prepare"),
            e("execute"),
            e("checks"),
            task={"review_mode": mode, "review_rounds": 0},
            checks=passed_checks(),
            risk=risk,
        )
        return decide(state, QUICK).action

    assert isinstance(after_checks(ReviewMode.REQUIRED, None), RunStage)
    assert isinstance(after_checks(ReviewMode.SELF, 80), RunStage)  # D2
    assert isinstance(after_checks(ReviewMode.SELF, 10), Accept)  # D3
    waived = after_checks(ReviewMode.WAIVED, 99)
    assert isinstance(waived, Accept)
    assert waived.clearance is ReviewClearance.WAIVED


def test_review_only_a_waived_gate_skips_its_review_stage() -> None:
    gates = ["item_gate", "phase_gate", "group_review"]
    wf = doc(
        {"id": "gate_prepare", "type": "prepare_environment", "for_kinds": gates},
        {"id": "gate_checks", "type": "run_checks", "for_kinds": ["phase_gate"], "params": {"scope": "gate"}},
        {**REVIEW, "for_kinds": ["phase_gate"], "skip_when": {"review_mode": "waived"}},
        {"id": "phase_gate", "type": "phase_gate"},
    )
    waived = make_state(
        e("gate_prepare", stage_type="prepare_environment"),
        kind=TaskKind.PHASE_GATE,
        task={"review_mode": ReviewMode.WAIVED},
    )
    assert next_stage(waived, wf) == "gate_checks"
    after = make_state(
        e("gate_prepare", stage_type="prepare_environment"),
        e("gate_checks", stage_type="run_checks"),
        kind=TaskKind.PHASE_GATE,
        task={"review_mode": ReviewMode.WAIVED},
        checks=passed_checks(),
    )
    expect(decide(after, wf), "D15", RunStage, stage_id="phase_gate")


# --------------------------------------------------------------------------------- guards by status


def test_the_initial_selection_applies_only_to_a_started_attempt_and_changes_no_status() -> None:
    for status in (TaskStatus.ASSIGNED, TaskStatus.EXECUTING):
        state = make_state(status=status)
        decision = decide(state)
        expect(decision, "A1", RunStage, stage_id="prepare")
        assert state.task.status is status
    for status in (TaskStatus.READY, TaskStatus.BLOCKED):
        assert isinstance(decide(make_state(status=status)).action, Noop)


def test_the_initial_selection_is_not_repeated_once_a_record_exists() -> None:
    decision = decide(make_state(e("prepare", K.SUCCESS), status=TaskStatus.ASSIGNED))
    assert decision.cause["advance_rule"] != "A1"


def test_a_failed_required_check_is_not_an_advisory_one() -> None:
    advisory = make_check(uid(502), state=CheckState.FAILED, required=False)
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks", K.CHECKS_FAILED),
        checks=(advisory,),
        task={"check_fix_rounds": 0},
    )
    # nothing required failed: the rework brief has no check to name, the engine still follows its row
    assert decide(state).cause["advance_rule"] == "D6"
    assert failed_check().required
