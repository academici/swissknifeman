"""Every row of the advance decision table (execution §5.1).

Each row is a case of its own: a ``TaskState`` that fires exactly that row, the ``NextAction`` and the
``advance_rule`` the decision keeps as its cause. ``covers`` names the rows a test proves, and
``test_every_row_of_the_table_has_a_case`` compares them with the closed ``ADVANCE_RULES``.
"""

from __future__ import annotations

import ast
import dataclasses
import json
import re
import tomllib
from collections.abc import Callable
from datetime import timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from skm.kernel.json_types import JsonValue
from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.autonomy import ReusableDecision
from skm.modules.execution.domain.blocking_reason import BlockingCode, blocking_reason
from skm.modules.execution.domain.check_execution import CheckKind, CheckState
from skm.modules.execution.domain.decision_record import QuestionCategory
from skm.modules.execution.domain.decision_request import (
    Audience,
    DecisionKind,
    DecisionRequest,
    DecisionState,
    question_digest,
    question_key,
)
from skm.modules.execution.domain.finding import FindingState, Severity
from skm.modules.execution.domain.output import OutputMount, OutputSource, manifest_digest
from skm.modules.execution.domain.review import ReviewClearance, Verdict
from skm.modules.execution.domain.risk import RiskScore
from skm.modules.execution.domain.run import RunKind, RunStatus
from skm.modules.execution.domain.stage_record import StageOutcomeKind, StageRecord, StageState
from skm.modules.execution.domain.task import PathPattern, ReviewMode, TaskKind, TaskOrigin, TaskStatus
from skm.modules.execution.domain.workflow import actions as advance_context
from skm.modules.execution.domain.workflow import engine as engine_module
from skm.modules.execution.domain.workflow.actions import (
    ADVANCE_RULES,
    Accept,
    CreateFollowups,
    Done,
    Escalate,
    Fail,
    NewAttempt,
    Noop,
    RecordedInstruction,
    Rework,
    RunStage,
    WaitFor,
)
from skm.modules.execution.domain.workflow.definition import StageType, WorkflowDefinition, parse_workflow
from skm.modules.execution.domain.workflow.engine import (
    ActionDecision,
    DecisionFact,
    TaskState,
    advance,
    decide_advance,
)
from skm.modules.execution.domain.workflow.history import StageEntry, StageHistory
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from skm.modules.execution.domain.workflow.task_facts import RULE_ID_PATTERN
from unit.execution.domain.test_acceptance import (
    ATTEMPT,
    CHECK_CMD,
    CHECK_MANUAL,
    NOW,
    OUT,
    RUN,
    TASK,
    WS,
    changed,
    make_attempt,
    make_check,
    make_finding,
    make_output,
    make_review,
    make_task,
    verdict,
)
from unit.execution.domain.test_run_transitions import make_run
from unit.execution.domain.test_session import make_step, uid

ROOT = Path(__file__).resolve().parents[4]
WORKFLOWS = ROOT / "tests/fixtures/corpus/examples/execution/workflows"
DIGEST = "sha256:" + "1" * 64
COVERED: dict[str, set[str]] = {}


def workflow(name: str) -> WorkflowDefinition:
    document = tomllib.loads((WORKFLOWS / f"{name}.toml").read_text(encoding="utf-8"))
    definition, violations = parse_workflow(cast("JsonValue", document))
    assert violations == ()
    assert definition is not None
    return definition


REVIEWED = workflow("reviewed-development")
QUICK = workflow("quick-fix")
RESEARCH = workflow("research-only")
STAGE_TYPES = {
    **{s.id: s.type.value for s in REVIEWED.stages},
    **{s.id: s.type.value for s in QUICK.stages},
    **{s.id: s.type.value for s in RESEARCH.stages},
}
K = StageOutcomeKind


def covers(*rows: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def mark(function: Callable[..., Any]) -> Callable[..., Any]:
        COVERED.setdefault(function.__name__, set()).update(rows)
        return function

    return mark


def e(
    stage_id: str,
    outcome: StageOutcomeKind | None = K.SUCCESS,
    *,
    mode: StageMode = StageMode.NORMAL,
    round_no: int = 1,
    state: StageState | None = None,
    code: str | None = None,
    out: dict[str, Any] | None = None,
    steps: tuple[Any, ...] = (),
    started: bool = True,
    digest: str = DIGEST,
    stage_type: str | None = None,
) -> StageEntry:
    """A stage record in history; ``history`` numbers the sequence."""
    if state is None:
        failed = outcome in {K.RUNTIME_ERROR, K.RESULT_INVALID}
        state = StageState.FAILED if failed else StageState.COMPLETED
    if outcome is K.RUNTIME_ERROR and code is None:
        code = "RUNTIME_TRANSPORT"
    if outcome is K.RESULT_INVALID and code is None:
        code = "RESULT_INVALID"
    finished = state in {StageState.COMPLETED, StageState.FAILED, StageState.INTERRUPTED, StageState.SKIPPED}
    record = StageRecord(
        id=uid(7000),
        attempt_id=ATTEMPT,
        run_id=RUN,
        task_id=TASK,
        seq=1,
        stage_id=stage_id,
        stage_type=stage_type or STAGE_TYPES[stage_id],
        round_no=round_no,
        mode=mode,
        retry_of_id=None,
        state=state,
        input_digest=digest,
        outcome_kind=outcome,
        outcome=out,
        error_code=code if state in {StageState.FAILED, StageState.INTERRUPTED} else None,
        started_at=NOW,
        finished_at=NOW if finished else None,
        fencing_token=1,
        runtime_started_at=NOW if started else None,
        process_identities=(),
        reused_from_step_id=None,
    )
    return StageEntry(record, steps)


def history(*entries: StageEntry) -> StageHistory:
    numbered = [
        StageEntry(dataclasses.replace(item.record, seq=index + 1, id=uid(7000 + index)), item.steps)
        for index, item in enumerate(entries)
    ]
    return StageHistory(tuple(numbered))


def task_for(kind: TaskKind, status: TaskStatus, **changes: Any) -> Any:
    values: dict[str, Any] = {"kind": kind, "status": status}
    if status is TaskStatus.AWAITING_DECISION:
        values["blocking_reason"] = blocking_reason(
            BlockingCode.WAITING_OWNER,
            task_id=TASK,
            refs={"decision_request_id": str(uid(60)), "stop_code": "ITEM_BLOCKED"},
            now=NOW,
            message="waiting",
        )
    if status is TaskStatus.MANUAL_PENDING:
        values["blocking_reason"] = blocking_reason(
            BlockingCode.WAITING_MANUAL_CHECK,
            task_id=TASK,
            refs={"check_execution_id": str(CHECK_MANUAL), "check_key": "P1.1:M1"},
            now=NOW,
            message="waiting",
        )
    if status is TaskStatus.BLOCKED:
        values["blocking_reason"] = blocking_reason(
            BlockingCode.BLOCKED_BY_DEPENDENCY,
            task_id=TASK,
            refs={"prerequisite_task_ids": []},
            now=NOW,
            message="waiting",
        )
    if kind in {TaskKind.PLAN_ACCEPTANCE, TaskKind.PLAN_AUDIT}:
        values.update(spec_entity_id=None, declared_write_scope=())
    elif kind in {TaskKind.ITEM_GATE, TaskKind.PHASE_GATE}:
        values["declared_write_scope"] = ()
    elif kind in {TaskKind.INTEGRATION, TaskKind.FOLLOWUP, TaskKind.GROUP_REVIEW}:
        values.update(spec_entity_id=None, origin=TaskOrigin(None, (), "test"))
        if kind is TaskKind.GROUP_REVIEW:
            values["declared_write_scope"] = ()
    values.update(changes)
    return make_task(**values)


_MISSING: Any = object()


def make_state(
    *entries: StageEntry,
    status: TaskStatus = TaskStatus.EXECUTING,
    kind: TaskKind = TaskKind.ITEM,
    task: dict[str, Any] | None = None,
    run: dict[str, Any] | None = None,
    attempt: Any = _MISSING,
    output: Any = _MISSING,
    checks: tuple[Any, ...] = (),
    manual: dict[Any, Any] | None = None,
    reviews: tuple[Any, ...] = (),
    findings: tuple[Any, ...] = (),
    open_requests: tuple[Any, ...] = (),
    budget: dict[str, Any] | None = None,
    risk: RiskScore | None = None,
    advisor_rounds_used: int = 0,
    run_retries_used: int | None = 0,
    **extra: Any,
) -> TaskState:
    run_changes = dict(run or {})
    run_status = run_changes.pop("status", RunStatus.RUNNING)
    return TaskState(
        run=make_run(run_status, **run_changes),
        task=task_for(kind, status, **(task or {})),
        attempt=make_attempt() if attempt is _MISSING else attempt,
        effective_policy={},
        history=history(*entries),
        output=make_output() if output is _MISSING else output,
        checks=checks,
        manual=manual or {},
        reviews=reviews,
        findings=findings,
        open_requests=open_requests,
        budget=budget or {},
        risk=risk,
        advisor_rounds_used=advisor_rounds_used,
        gate=None,
        run_retries_used=run_retries_used,
        **extra,
    )


def decide(
    state: TaskState, wf: WorkflowDefinition = REVIEWED, policy: dict[str, Any] | None = None
) -> ActionDecision:
    return decide_advance(state, wf, cast("Any", policy or {}), NOW)


def expect(decision: ActionDecision, rule: str, action_type: type, **fields: Any) -> Any:
    assert decision.cause["advance_rule"] == rule, decision
    action = decision.action
    assert isinstance(action, action_type), action
    for name, value in fields.items():
        assert getattr(action, name) == value, (name, getattr(action, name), value)
    return action


def reasons(decision: ActionDecision) -> list[str]:
    return cast("list[str]", decision.cause["reason_codes"])


def ref_kinds(decision: ActionDecision) -> set[str]:
    return {ref["kind"] for ref in cast("list[dict[str, str]]", decision.cause["refs"])}


def failed_check(n: int = 500, **changes: Any) -> Any:
    return make_check(uid(n), state=CheckState.FAILED, **changes)


def request(
    kind: DecisionKind = DecisionKind.ESCALATION,
    *,
    audience: Audience = Audience.OWNER,
    n: int = 60,
    payload: dict[str, Any] | None = None,
    state: DecisionState = DecisionState.OPEN,
) -> DecisionRequest:
    return DecisionRequest(
        id=uid(n),
        workspace_id=WS,
        run_id=RUN,
        task_id=TASK,
        kind=kind,
        audience=audience,
        category=QuestionCategory.BOUNDED_AMBIGUITY if kind is DecisionKind.QUESTION else None,
        gate_categories=frozenset(),
        question_key="qk-1" if kind is DecisionKind.QUESTION else None,
        question_digest=None,
        revision=1,
        payload=payload or {},
        asked_by_step_id=None,
        binding={},
        state=state,
        stale_answer=None,
        deadline_at=None,
        created_at=NOW,
    )


LOCAL_FACTS = {
    "reversibility": "reversible",
    "scope_impact": "local",
    "contract_change": "none",
    "cost_class": "low",
    "needs_external_fact": False,
    "needs_authority": False,
}


def question(**changes: Any) -> dict[str, Any]:
    """A question as ``role-result-executor`` allows it: no ``category``, the six autonomy facts."""
    values: dict[str, Any] = {
        "id": "Q1",
        "revision": 1,
        "kind": "decision",
        "text": "which name?",
        "blocking": True,
        "default": "alpha",
        "facts": dict(LOCAL_FACTS),
    }
    values.update(changes)
    return values


def asked(**changes: Any) -> StageEntry:
    return e("execute", K.QUESTION, out={"questions": [question(**changes)]})


# ------------------------------------------------------------------------------------- guards G1-G7


@covers("G1")
def test_g1_run_not_running_is_a_noop_for_every_state_of_the_run() -> None:
    for status in (RunStatus.PAUSED, RunStatus.WAITING, RunStatus.CANCELLED, RunStatus.SUCCEEDED):
        state = make_state(e("prepare"), run={"status": status})
        expect(decide(state), "G1", Noop)


@covers("G2")
def test_g2_a_terminal_task_is_done() -> None:
    expect(decide(make_state(e("prepare"), status=TaskStatus.SKIPPED)), "G2", Done)


@covers("G3")
def test_g3_kill_switch_waits_by_policy_and_keeps_the_task_state() -> None:
    decision = decide(make_state(e("prepare")), policy={"kill_switch": True})
    action = expect(decision, "G3", WaitFor, release_assignment=True)
    assert action.blocking.code is BlockingCode.BLOCKED_BY_POLICY
    assert action.blocking.refs["reason"] == "kill_switch"


@covers("G4")
def test_g4_lost_ownership_with_attempts_left_starts_a_new_attempt() -> None:
    state = make_state(
        e("prepare"), attempt=make_attempt(AttemptState.OWNERSHIP_LOST), task={"attempt_count": 1}
    )
    expect(decide(state), "G4", NewAttempt, reason_code="LEASE_LOST")


@covers("G5")
def test_g5_lost_ownership_without_attempts_fails() -> None:
    state = make_state(
        e("prepare"), attempt=make_attempt(AttemptState.OWNERSHIP_LOST), task={"attempt_count": 3}
    )
    expect(decide(state), "G5", Fail, code="LEASE_LOST")
    assert decide(state, policy={"attempts_max": 4}).cause["advance_rule"] == "G4"


@covers("G6")
@pytest.mark.parametrize(
    ("kind", "code", "payload"),
    [
        (DecisionKind.QUESTION, BlockingCode.WAITING_ANSWER, {}),
        (DecisionKind.APPROVAL, BlockingCode.WAITING_APPROVAL, {"refs": {"intent_id": "i-1"}}),
        (DecisionKind.BUDGET, BlockingCode.BLOCKED_BY_BUDGET, {"dimension": "tokens", "limit": 5}),
        (DecisionKind.ESCALATION, BlockingCode.WAITING_OWNER, {"code": "ITEM_BLOCKED"}),
    ],
)
def test_g6_an_open_owner_request_blocks_by_its_kind(
    kind: DecisionKind, code: BlockingCode, payload: dict[str, Any]
) -> None:
    state = make_state(e("execute"), open_requests=(request(kind, payload=payload),))
    action = expect(decide(state), "G6", WaitFor, release_assignment=True)
    assert action.blocking.code is code
    assert ref_kinds(decide(state)) >= {"decision_request"}


def test_g6_ignores_advisor_requests_answered_requests_and_other_tasks() -> None:
    other = dataclasses.replace(request(n=61), task_id=uid(101))
    answered = request(n=62, state=DecisionState.ANSWERED)
    advisor = request(DecisionKind.QUESTION, audience=Audience.ADVISOR, n=63)
    state = make_state(e("prepare"), open_requests=(other, answered, advisor))
    assert decide(state).cause["advance_rule"] != "G6"


def test_g6_accumulates_every_open_request_in_the_cause() -> None:
    first, second = request(n=60), request(DecisionKind.QUESTION, n=61)
    decision = decide(make_state(e("execute"), open_requests=(second, first)))
    assert reasons(decision) == ["WAITING_OWNER", "WAITING_ANSWER"]
    requests = [ref for ref in decision.cause["refs"] if ref["kind"] == "decision_request"]  # type: ignore[index]
    assert len(requests) == 2


@covers("G7")
def test_g7_a_stage_that_does_not_fit_the_budget_becomes_a_budget_escalation() -> None:
    budget = {
        "accounts": [{"scope": "run", "dimension": "tokens", "limit": 100, "spent": 80, "reserved": 10}]
    }
    state = make_state(e("prepare"), budget={**budget, "estimate": {"tokens": 30}})
    action = expect(decide(state), "G7", Escalate, kind=DecisionKind.BUDGET, code="BUDGET_EXHAUSTED")
    assert action.blocking_code is BlockingCode.BLOCKED_BY_BUDGET
    assert (
        decide(make_state(e("prepare"), budget={**budget, "estimate": {"tokens": 10}})).cause["advance_rule"]
        == "A3"
    )


def test_g7_does_not_stop_a_decision_that_runs_no_stage() -> None:
    budget = {
        "accounts": [{"scope": "run", "dimension": "tokens", "limit": 100, "spent": 100, "reserved": 0}]
    }
    state = make_state(e("checks", K.SUCCESS), task={"review_mode": ReviewMode.WAIVED}, budget=budget)
    expect(decide(state), "D4", Accept)


def test_g7_unmetered_run_and_exhausted_wall_clock_block_the_next_stage() -> None:
    state = make_state(e("prepare"), run={"unmetered_at": NOW})
    assert "UNMETERED" in reasons(decide(state))
    wall = {"accounts": [{"scope": "task", "dimension": "wall_seconds", "limit": 60, "spent": 60}]}
    expect(decide(make_state(e("prepare"), budget=wall)), "G7", Escalate)


# ------------------------------------------------------------------------------------------- rule L


@covers("L2i")
def test_l2i_an_interrupted_integrate_reconciles_before_any_repeat() -> None:
    state = make_state(
        e("integrate", None, state=StageState.INTERRUPTED, started=False), status=TaskStatus.INTEGRATING
    )
    action = expect(decide(state), "L2i", RunStage, mode=StageMode.RECONCILE, stage_id="integrate")
    assert action.feedback == FeedbackRefs(interrupted_stage_record_id=uid(7000))


@covers("L1")
def test_l1_an_interrupted_stage_without_runtime_start_repeats_with_the_same_mode_and_round() -> None:
    state = make_state(
        e("execute", None, state=StageState.INTERRUPTED, started=False, mode=StageMode.REWORK, round_no=2)
    )
    expect(decide(state), "L1", RunStage, stage_id="execute", mode=StageMode.REWORK, round_no=2)


@covers("L2")
def test_l2_an_interrupted_writing_stage_resumes_after_a_confirmed_reap() -> None:
    state = make_state(e("execute", None, state=StageState.INTERRUPTED), reap_confirmed=True)
    action = expect(decide(state), "L2", RunStage, stage_id="execute", mode=StageMode.RESUME_INTERRUPTED)
    assert action.feedback == FeedbackRefs(interrupted_stage_record_id=uid(7000))


@covers("L2b")
@pytest.mark.parametrize("stage_id", ["scout", "checks", "review", "triage", "advise"])
def test_l2b_an_interrupted_read_only_stage_is_retried(stage_id: str) -> None:
    state = make_state(e(stage_id, None, state=StageState.INTERRUPTED), reap_confirmed=True)
    expect(decide(state), "L2b", RunStage, stage_id=stage_id, mode=StageMode.RETRY)


def test_l2_without_a_confirmed_reap_waits_and_does_not_start_anything() -> None:
    state = make_state(e("execute", None, state=StageState.INTERRUPTED))
    decision = decide(state)
    assert isinstance(decision.action, Noop)
    assert decision.cause["advance_rule"] is None
    assert "REAP_NOT_CONFIRMED" in reasons(decision)


def test_an_unresolved_effect_makes_l1_unsafe_even_without_a_runtime_start() -> None:
    state = make_state(
        e("execute", None, state=StageState.INTERRUPTED, started=False), effects_unresolved=True
    )
    assert isinstance(decide(state).action, Noop)
    expect(decide(dataclasses.replace(state, reap_confirmed=True)), "L2", RunStage)


# ------------------------------------------------------------------------------------------ A rows


@covers("A1")
@pytest.mark.parametrize("status", [TaskStatus.ASSIGNED, TaskStatus.EXECUTING])
def test_a1_a_new_attempt_selects_prepare_once_without_any_transition(status: TaskStatus) -> None:
    decision = decide(make_state(status=status))
    expect(decision, "A1", RunStage, stage_id="prepare", mode=StageMode.NORMAL, round_no=1)
    assert decision.cause["trigger_kind"] == "run_start"


def test_a1_selects_the_gate_range_prepare_for_a_gate_task() -> None:
    state = make_state(status=TaskStatus.ASSIGNED, kind=TaskKind.PHASE_GATE)
    expect(decide(state), "A1", RunStage, stage_id="gate_prepare")


def test_a1_is_not_selected_for_a_task_that_has_not_started() -> None:
    assert isinstance(decide(make_state(status=TaskStatus.READY)).action, Noop)


@covers("A2")
def test_a2_a_scout_follows_prepare_when_its_route_flag_is_set() -> None:
    state = make_state(e("prepare"), route_flags=frozenset({"scout"}))
    expect(decide(state), "A2", RunStage, stage_id="scout", mode=StageMode.NORMAL)


@covers("A3")
def test_a3_without_a_scout_the_next_applicable_stage_follows() -> None:
    expect(decide(make_state(e("prepare"))), "A3", RunStage, stage_id="execute")
    state = make_state(e("prepare"))
    expect(decide(state, QUICK), "A3", RunStage, stage_id="execute")
    expect(decide(state, RESEARCH), "A3", RunStage, stage_id="research")


def test_a3_scout_mode_always_makes_the_scout_applicable() -> None:
    state = dataclasses.replace(make_state(e("prepare")), effective_policy={"scout_mode": "always"})
    expect(decide(state), "A2", RunStage, stage_id="scout")


@covers("A4")
def test_a4_prepare_failure_with_retry_left_repeats_prepare() -> None:
    expect(
        decide(make_state(e("prepare", K.RUNTIME_ERROR))),
        "A4",
        RunStage,
        stage_id="prepare",
        mode=StageMode.RETRY,
    )


@covers("A5")
def test_a5_prepare_failure_that_stops_escalates_with_the_class_code() -> None:
    state = make_state(e("prepare", K.RUNTIME_ERROR, code="RUNTIME_AUTH_EXPIRED"))
    action = expect(decide(state), "A5", Escalate, code="RUNTIME_AUTH_EXPIRED")
    assert action.blocking_code is BlockingCode.WAITING_OWNER


@covers("A6")
def test_a6_a_gate_continues_with_its_next_applicable_stage() -> None:
    state = make_state(e("gate_prepare"), kind=TaskKind.PHASE_GATE, status=TaskStatus.EXECUTING)
    expect(decide(state), "A6", RunStage, stage_id="gate_checks")
    empty = make_state(e("prepare"), kind=TaskKind.ITEM_GATE, task={"review_mode": ReviewMode.WAIVED})
    assert decide(empty, QUICK).cause["advance_rule"] == "A6"
    assert isinstance(decide(empty, QUICK).action, Done)
    assert "GATE_EMPTY" in reasons(decide(empty, QUICK))


# ------------------------------------------------------------------------------------------ B rows


@covers("B1")
def test_b1_scout_success_goes_to_execute() -> None:
    expect(decide(make_state(e("prepare"), e("scout"))), "B1", RunStage, stage_id="execute", round_no=1)


@covers("B2")
@pytest.mark.parametrize("outcome", [K.RESULT_INVALID, K.RUNTIME_ERROR])
def test_b2_an_optional_scout_is_skipped_with_a_diagnostic(outcome: StageOutcomeKind) -> None:
    decision = decide(make_state(e("prepare"), e("scout", outcome)))
    expect(decision, "B2", RunStage, stage_id="execute")
    assert "SCOUT_SKIPPED" in reasons(decision)


@covers("B3")
def test_b3_a_required_scout_is_retried_after_infrastructure_failure() -> None:
    required = dataclasses.replace(
        REVIEWED,
        stages=tuple(
            dataclasses.replace(s, optional=False) if s.id == "scout" else s for s in REVIEWED.stages
        ),
    )
    state = make_state(e("prepare"), e("scout", K.RUNTIME_ERROR))
    expect(decide(state, required), "B3", RunStage, stage_id="scout", mode=StageMode.RETRY)


# ------------------------------------------------------------------------------------------ C rows


@covers("C1")
def test_c1_execute_success_goes_to_checks() -> None:
    state = make_state(e("prepare"), e("execute"))
    expect(decide(state), "C1", RunStage, stage_id="checks", round_no=1)


def test_c1_a_scope_violation_is_a_deviation_unless_the_policy_blocks() -> None:
    state = make_state(e("prepare"), e("execute", K.WRITE_SCOPE_VIOLATION))
    decision = decide(state)
    expect(decision, "C1", RunStage, stage_id="checks")
    assert "SCOPE_DEVIATION" in reasons(decision)


def test_c1_without_a_checks_stage_the_acceptance_path_follows() -> None:
    state = make_state(e("prepare"), e("research"), task={"review_mode": ReviewMode.WAIVED})
    decision = decide(state, RESEARCH)
    expect(decision, "D4", Accept, clearance=ReviewClearance.WAIVED)
    assert "NO_CHECKS_STAGE" in reasons(decision)


@covers("C2")
def test_c2_authority_questions_go_to_the_owner() -> None:
    state = make_state(e("prepare"), asked(kind="approval"))
    action = expect(decide(state), "C2", Escalate, kind=DecisionKind.QUESTION)
    assert action.blocking_code is BlockingCode.WAITING_ANSWER
    assert action.payload["audience"] == "owner"


def test_c2_a_question_without_facts_is_never_cheaper_than_the_owner() -> None:
    q = question()
    del q["facts"]
    state = make_state(e("prepare"), e("execute", K.QUESTION, out={"questions": [q]}))
    expect(decide(state), "C2", Escalate)


def test_c2_the_authority_fact_makes_a_question_owner_only() -> None:
    q = question(facts={**LOCAL_FACTS, "needs_authority": True})
    state = make_state(e("prepare"), e("execute", K.QUESTION, out={"questions": [q]}))
    expect(decide(state), "C2", Escalate)


def test_the_question_fixture_is_what_the_executor_schema_allows() -> None:
    path = ROOT / "src/skm/schemas/execution/role-result-executor.v1.json"
    schema = json.loads(path.read_text(encoding="utf-8"))["$defs"]["question"]
    assert set(question()) <= set(schema["properties"])
    assert set(schema["required"]) <= set(question())
    assert set(question()["facts"]) == set(schema["properties"]["facts"]["required"])
    assert "category" not in schema["properties"]


@covers("C3")
def test_c3_an_advisor_answers_a_bounded_question() -> None:
    state = make_state(e("prepare"), asked())
    action = expect(decide(state), "C3", RunStage, stage_id="advise", mode=StageMode.NORMAL)
    assert action.params["problem_ref"] == "question:Q1@1"


@covers("C4")
def test_c4_a_consilium_panel_is_consulted_when_the_policy_asks_for_it() -> None:
    policy = {"consilium": {"members": ["a", "b"], "trigger": "always"}}
    action = expect(
        decide(make_state(e("prepare"), asked()), policy=policy), "C4", RunStage, stage_id="advise"
    )
    assert action.params["panel"] is True


@covers("C5")
def test_c5_a_policy_default_answers_in_place() -> None:
    state = make_state(e("prepare"), asked())
    decision = decide(state, policy={"question_policy": "defaults"})
    expect(decision, "C5", RunStage, stage_id="execute", mode=StageMode.CONTINUE_WITH_ANSWER)
    assert decision.action.params["answered_by"] == "policy"  # type: ignore[union-attr]


def test_c5_a_default_already_used_goes_to_the_owner() -> None:
    q = question()
    key = question_key("P1.1", q)
    state = make_state(e("prepare"), asked(), policy_answered=frozenset({key}))
    decision = decide(state, policy={"question_policy": "defaults"})
    expect(decision, "C6", Escalate, kind=DecisionKind.QUESTION)


@covers("C6")
def test_c6_queue_policy_and_missing_advisor_go_to_the_owner_and_deny_is_refused() -> None:
    state = make_state(e("prepare"), asked())
    expect(decide(state, policy={"question_policy": "queue"}), "C6", Escalate, kind=DecisionKind.QUESTION)
    expect(decide(state, policy={"advisor_enabled": False}), "C6", Escalate, kind=DecisionKind.QUESTION)
    expect(decide(state, QUICK), "C6", Escalate, kind=DecisionKind.QUESTION)
    denied = expect(
        decide(state, policy={"question_policy": "deny"}),
        "C6",
        Escalate,
        kind=DecisionKind.ESCALATION,
        code="FORBIDDEN",
    )
    assert denied.payload["text"] == "QUESTION_DENIED: Q1"


@covers("C7")
def test_c7_a_reused_decision_answers_the_question() -> None:
    q = question()
    reusable = ReusableDecision(
        question_key=question_key("P1.1", q),
        question_digest=question_digest("P1.1", q),
        value="alpha",
        selected_option=None,
    )
    state = make_state(e("prepare"), asked(), reusable={reusable.question_key: reusable})
    decision = decide(state)
    expect(decision, "C7", RunStage, mode=StageMode.CONTINUE_WITH_ANSWER)
    assert "QUESTION_REUSED" in reasons(decision)


@covers("C8")
def test_c8_a_blocked_report_escalates_the_item() -> None:
    expect(decide(make_state(e("prepare"), e("execute", K.BLOCKED))), "C8", Escalate, code="ITEM_BLOCKED")


@covers("C9")
def test_c9_a_scope_violation_blocks_when_the_policy_says_block() -> None:
    state = make_state(e("prepare"), e("execute", K.WRITE_SCOPE_VIOLATION))
    expect(
        decide(state, policy={"scope_outside_policy": "block"}), "C9", Escalate, code="WRITE_SCOPE_VIOLATION"
    )


@covers("C10")
def test_c10_the_same_role_repeats_with_the_schema_errors_of_the_failed_step() -> None:
    step = make_step(
        id=uid(90), state=_failed(), error_code="RESULT_INVALID", schema_errors=({"pointer": "/x"},)
    )
    state = make_state(e("prepare"), e("execute", K.RESULT_INVALID, steps=(step,)))
    action = expect(decide(state), "C10", RunStage, stage_id="execute", mode=StageMode.RETRY)
    assert action.feedback == FeedbackRefs(schema_errors_step_id=uid(90))


def _failed() -> Any:
    from skm.modules.execution.domain.step import StepState

    return StepState.FAILED


@covers("C10b")
def test_c10b_repeats_exhausted_escalate_with_the_three_answers() -> None:
    first = e("execute", K.RESULT_INVALID)
    state = make_state(e("prepare"), first, e("execute", K.RESULT_INVALID, mode=StageMode.RETRY))
    action = expect(decide(state), "C10b", Escalate, code="RESULT_INVALID")
    assert action.payload["options"] == ["retry_stage", "new_attempt", "fail"]


def test_c10_a_valid_result_resets_the_count_of_invalid_results() -> None:
    state = make_state(
        e("prepare"), e("execute", K.RESULT_INVALID), e("execute", K.SUCCESS), e("execute", K.RESULT_INVALID)
    )
    expect(decide(state), "C10", RunStage, mode=StageMode.RETRY)


@covers("C11")
def test_c11_infrastructure_failure_retries_the_stage_and_may_wait() -> None:
    state = make_state(e("prepare"), e("execute", K.RUNTIME_ERROR))
    expect(decide(state), "C11", RunStage, stage_id="execute", mode=StageMode.RETRY, not_before=None)
    limited = make_state(
        e("prepare"), e("execute", K.RUNTIME_ERROR, code="RATE_LIMITED", out={"retry_after_seconds": 90})
    )
    action = expect(decide(limited), "C11", RunStage, mode=StageMode.RETRY)
    assert action.not_before == NOW + timedelta(seconds=90)


@covers("C12")
def test_c12_a_dirty_worktree_resumes_the_interrupted_executor() -> None:
    state = make_state(e("prepare"), e("execute", K.RUNTIME_ERROR, out={"worktree_dirty": True}))
    expect(decide(state), "C12", RunStage, stage_id="execute", mode=StageMode.RESUME_INTERRUPTED)


@covers("C13")
def test_c13_a_context_limit_asks_the_owner_to_replan() -> None:
    state = make_state(e("prepare"), e("execute", K.RUNTIME_ERROR, code="CONTEXT_OVERFLOW"))
    action = expect(decide(state), "C13", Escalate, code="CONTEXT_OVER_BUDGET")
    assert action.payload["options"] == ["split_task", "raise_budget", "retry_stage"]


@covers("C14")
def test_c14_a_stop_escalates_with_the_class_code_and_a_known_quota_reset_waits() -> None:
    state = make_state(e("prepare"), e("execute", K.RUNTIME_ERROR, code="RUNTIME_FORBIDDEN"))
    action = expect(decide(state), "C14", Escalate, code="RUNTIME_FORBIDDEN")
    assert action.blocking_code is BlockingCode.WAITING_OWNER
    quota = make_state(
        e("prepare"),
        e("execute", K.RUNTIME_ERROR, code="QUOTA_EXHAUSTED", out={"retry_after_seconds": 7200}),
    )
    policy = {"retry": {"on_error": {"quota": {"action": "stop"}}}}
    reset = expect(decide(quota, policy=policy), "C14", Escalate, code="QUOTA_EXHAUSTED")
    assert reset.blocking_code is BlockingCode.WAITING_BUDGET_RESET


def test_infrastructure_retries_are_bounded_by_the_policy() -> None:
    errors = [e("execute", K.RUNTIME_ERROR) for _ in range(2)]
    state = make_state(e("prepare"), *errors)
    expect(decide(state), "C14", Escalate, code="RUNTIME_TRANSPORT")
    expect(decide(state, policy={"step_max_infra_retries": 2}), "C11", RunStage)


# ------------------------------------------------------------------------------------------ D rows


def passed_checks() -> tuple[Any, ...]:
    return (make_check(CHECK_CMD, state=CheckState.PASSED),)


@covers("D1")
def test_d1_required_review_follows_green_checks_in_the_next_round() -> None:
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks"),
        task={"review_rounds": 0},
        checks=passed_checks(),
        status=TaskStatus.CHECKING,
    )
    expect(decide(state), "D1", RunStage, stage_id="review", round_no=1)
    again = dataclasses.replace(state, task=dataclasses.replace(state.task, review_rounds=1))
    expect(decide(again), "D1", RunStage, stage_id="review", round_no=2)


@covers("D2")
def test_d2_self_review_is_added_when_the_risk_reaches_the_threshold() -> None:
    mode = {"review_mode": ReviewMode.SELF}
    risk = RiskScore(score=70, features=(), critical=())
    state = make_state(e("prepare"), e("execute"), e("checks"), task=mode, checks=passed_checks(), risk=risk)
    decision = decide(state)
    expect(decision, "D2", RunStage, stage_id="review")
    assert "DYNAMIC_REVIEW_ADDED" in reasons(decision)
    critical = RiskScore(score=10, features=(), critical=("security",))
    expect(decide(dataclasses.replace(state, risk=critical)), "D2", RunStage)


@covers("D3")
def test_d3_self_review_below_the_threshold_or_per_task_accepts_with_self_clearance() -> None:
    mode = {"review_mode": ReviewMode.SELF}
    low = RiskScore(score=10, features=(), critical=())
    state = make_state(e("prepare"), e("execute"), e("checks"), task=mode, checks=passed_checks(), risk=low)
    expect(decide(state), "D3", Accept, clearance=ReviewClearance.SELF, output_id=OUT)
    high = dataclasses.replace(state, risk=RiskScore(score=90, features=(), critical=()))
    expect(decide(high, policy={"review_strategy": "per_task"}), "D3", Accept)


@covers("D4")
def test_d4_waived_review_accepts_with_waived_clearance() -> None:
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks"),
        task={"review_mode": ReviewMode.WAIVED},
        checks=passed_checks(),
    )
    expect(decide(state), "D4", Accept, clearance=ReviewClearance.WAIVED)


@covers("D5")
def test_d5_a_manual_check_without_a_verdict_waits() -> None:
    manual = make_check(CHECK_MANUAL, kind=CheckKind.MANUAL, state=CheckState.MANUAL_PENDING)
    state = make_state(e("prepare"), e("execute"), e("checks", K.MANUAL_PENDING), checks=(manual,))
    action = expect(decide(state), "D5", WaitFor, release_assignment=True)
    assert action.blocking.code is BlockingCode.WAITING_MANUAL_CHECK
    assert action.blocking.refs["check_execution_id"] == str(CHECK_MANUAL)


@covers("D6")
def test_d6_failed_checks_with_rounds_left_rework() -> None:
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks", K.CHECKS_FAILED),
        checks=(failed_check(),),
        task={"check_fix_rounds": 1},
    )
    decision = decide(state)
    expect(decision, "D6", Rework, reason="checks_failed")
    assert ref_kinds(decision) >= {"check", "output", "stage"}


@covers("D6g")
def test_d6g_a_gate_turns_failed_checks_into_followups() -> None:
    state = make_state(
        e("gate_prepare"),
        e("gate_checks", K.CHECKS_FAILED),
        kind=TaskKind.PHASE_GATE,
        checks=(failed_check(),),
        task={"review_rounds": 1},
    )
    action = expect(decide(state), "D6g", CreateFollowups, reason="checks_failed")
    assert action.check_execution_ids == (uid(500),)


@covers("D7")
def test_d7_exhausted_rework_asks_the_advisor_while_it_has_rounds() -> None:
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks", K.CHECKS_FAILED, round_no=3),
        checks=(failed_check(),),
        task={"check_fix_rounds": 2},
    )
    action = expect(decide(state), "D7", RunStage, stage_id="advise")
    assert action.params["problem_ref"] == "checks:3"


@covers("D8")
def test_d8_exhausted_rework_without_an_advisor_escalates() -> None:
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks", K.CHECKS_FAILED),
        checks=(failed_check(),),
        task={"check_fix_rounds": 2},
    )
    expect(decide(state, policy={"advisor_enabled": False}), "D8", Escalate, code="REWORK_LIMIT_REACHED")
    expect(decide(dataclasses.replace(state, advisor_rounds_used=2)), "D8", Escalate)
    expect(decide(state, QUICK), "D8", Escalate)


@covers("D9")
def test_d9_a_checks_error_is_retried_once() -> None:
    erred = make_check(uid(500), state=CheckState.ERROR, error_code="CHECK_TIMEOUT")
    state = make_state(e("prepare"), e("execute"), e("checks", K.CHECKS_ERROR), checks=(erred,))
    expect(decide(state), "D9", RunStage, stage_id="checks", mode=StageMode.RETRY)


@covers("D10")
def test_d10_repeated_checks_errors_escalate_with_the_check_error_code() -> None:
    erred = make_check(uid(500), state=CheckState.ERROR, error_code="CHECK_TIMEOUT")
    state = make_state(
        e("prepare"), e("execute"), e("checks", K.CHECKS_ERROR), e("checks", K.CHECKS_ERROR), checks=(erred,)
    )
    expect(decide(state), "D10", Escalate, code="CHECK_TIMEOUT")


@covers("D11")
def test_d11_unknown_checks_are_retried_without_spending_error_retries() -> None:
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks", K.CHECKS_UNKNOWN),
        e("checks", K.CHECKS_UNKNOWN),
        e("checks", K.CHECKS_ERROR),
        checks=(make_check(uid(500), state=CheckState.ERROR),),
    )
    expect(
        decide(dataclasses.replace(state, history=history(*state.history.entries[:4]))),
        "D11",
        RunStage,
        mode=StageMode.RETRY,
    )
    expect(decide(state), "D9", RunStage, mode=StageMode.RETRY)


@covers("D12", "D13")
def test_d12_d13_a_tree_changing_check_is_retried_once_then_escalates() -> None:
    first = make_state(e("prepare"), e("execute"), e("checks", K.TREE_CHANGED))
    decision = decide(first)
    expect(decision, "D12", RunStage, mode=StageMode.RETRY)
    assert "CHECK_CHANGED_TREE" in reasons(decision)
    second = make_state(e("prepare"), e("execute"), e("checks", K.TREE_CHANGED), e("checks", K.TREE_CHANGED))
    expect(decide(second), "D13", Escalate, code="CHECKS_MUTATED")


@covers("D14")
def test_d14_failed_advisory_checks_do_not_stop_the_acceptance_path() -> None:
    advisory = make_check(uid(502), state=CheckState.FAILED, required=False)
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks"),
        task={"review_mode": ReviewMode.WAIVED},
        checks=(*passed_checks(), advisory),
    )
    decision = decide(state)
    expect(decision, "D4", Accept)
    assert "ADVISORY_CHECK_FAILED" in reasons(decision)


@covers("D15")
def test_d15_a_gate_goes_to_review_when_required_else_to_its_gate_stage() -> None:
    gate: dict[str, Any] = {"kind": TaskKind.PHASE_GATE}
    base = make_state(
        e("gate_prepare"), e("gate_checks"), checks=passed_checks(), task={"review_rounds": 0}, **gate
    )
    expect(decide(base), "D15", RunStage, stage_id="review", round_no=1)
    waived = make_state(
        e("gate_prepare"),
        e("gate_checks"),
        checks=passed_checks(),
        task={"review_mode": ReviewMode.WAIVED},
        **gate,
    )
    expect(decide(waived), "D15", RunStage, stage_id="phase_gate", stage_type=StageType.PHASE_GATE)
    plan = make_state(
        e("gate_prepare"),
        e("gate_checks"),
        checks=passed_checks(),
        kind=TaskKind.PLAN_ACCEPTANCE,
        task={"review_mode": ReviewMode.WAIVED},
    )
    expect(decide(plan), "D15", RunStage, stage_id="plan_acceptance")


# ------------------------------------------------------------------------------------------ E rows


def manual_state(check_state: CheckState, value: str, **changes: Any) -> TaskState:
    manual = make_check(CHECK_MANUAL, kind=CheckKind.MANUAL, state=check_state)
    extra: dict[str, Any] = {"manual": {CHECK_MANUAL: verdict(value)}, "status": TaskStatus.MANUAL_PENDING}
    extra.update(changes)
    return make_state(e("prepare"), e("execute"), e("checks", K.MANUAL_PENDING), checks=(manual,), **extra)


@covers("E1")
def test_e1_a_passing_manual_verdict_continues_like_d1_to_d4() -> None:
    state = manual_state(CheckState.PASSED, "pass", task={"review_mode": ReviewMode.WAIVED})
    decision = decide(state)
    expect(decision, "E1", Accept, clearance=ReviewClearance.WAIVED)
    assert "VIA_D4" in reasons(decision)
    assert decision.cause["trigger_kind"] == "manual_verdict"


def test_e1_a_verdict_not_yet_applied_to_the_check_row_still_counts() -> None:
    state = manual_state(CheckState.MANUAL_PENDING, "pass", task={"review_mode": ReviewMode.WAIVED})
    expect(decide(state), "E1", Accept)


@covers("E2")
def test_e2_a_failed_manual_check_reworks_a_work_task_and_follows_up_a_gate() -> None:
    expect(decide(manual_state(CheckState.FAILED, "fail")), "E2", Rework, reason="manual_failed")
    gate = make_state(
        e("gate_prepare"),
        e("gate_checks", K.MANUAL_PENDING),
        kind=TaskKind.PHASE_GATE,
        task={"review_rounds": 0},
        checks=(make_check(CHECK_MANUAL, kind=CheckKind.MANUAL, state=CheckState.FAILED),),
        manual={CHECK_MANUAL: verdict("fail")},
    )
    expect(decide(gate), "E2", CreateFollowups, reason="checks_failed")


@covers("E3")
def test_e3_a_failed_manual_check_without_rounds_escalates() -> None:
    state = manual_state(CheckState.FAILED, "fail", task={"check_fix_rounds": 2})
    expect(decide(state), "E3", Escalate, code="REWORK_LIMIT_REACHED")


# ------------------------------------------------------------------------------------------ F rows


def reviewed(outcome: StageOutcomeKind, verdict_: Verdict, **changes: Any) -> TaskState:
    review = make_review(verdict_=verdict_)
    base: dict[str, Any] = {"reviews": (review,), "status": TaskStatus.REVIEWING}
    base.update(changes)
    return make_state(e("prepare"), e("execute"), e("checks"), e("review", outcome), **base)


@covers("F1")
def test_f1_green_review_accepts_a_work_task_and_sends_a_gate_to_its_stage() -> None:
    expect(decide(reviewed(K.VERDICT_GREEN, Verdict.GREEN)), "F1", Accept, clearance=ReviewClearance.GREEN)
    gate = make_state(
        e("gate_prepare"),
        e("gate_checks"),
        e("review", K.VERDICT_GREEN),
        kind=TaskKind.PHASE_GATE,
        reviews=(make_review(verdict_=Verdict.GREEN),),
    )
    expect(decide(gate), "F1", RunStage, stage_id="phase_gate")


def test_f1_green_with_an_open_major_finding_is_triaged_not_accepted() -> None:
    major = make_finding(1, Severity.MAJOR, FindingState.OPEN)
    decision = decide(reviewed(K.VERDICT_GREEN, Verdict.GREEN, findings=(major,)))
    expect(decision, "F4", RunStage, stage_id="triage")
    assert "GREEN_WITH_OPEN_FINDINGS" in reasons(decision)


@covers("F2")
def test_f2_attention_goes_to_triage_by_default() -> None:
    expect(decide(reviewed(K.VERDICT_ATTENTION, Verdict.ATTENTION)), "F2", RunStage, stage_id="triage")


@covers("F3")
def test_f3_attention_asks_the_owner_when_the_policy_or_the_stage_says_so() -> None:
    state = reviewed(K.VERDICT_ATTENTION, Verdict.ATTENTION)
    action = expect(
        decide(state, policy={"review_attention_policy": "ask_owner"}), "F3", Escalate, code="NOT_ACCEPTABLE"
    )
    assert action.payload["options"] == ["accept_deviation", "rework", "fail"]
    owner = dataclasses.replace(
        REVIEWED,
        stages=tuple(
            dataclasses.replace(s, on=dataclasses.replace(s.on, verdict_attention="ask_owner"))
            if s.id == "review"
            else s
            for s in REVIEWED.stages
        ),
    )
    expect(decide(state, owner), "F3", Escalate)


@covers("F4")
def test_f4_a_red_review_goes_to_triage() -> None:
    expect(decide(reviewed(K.VERDICT_RED, Verdict.RED)), "F4", RunStage, stage_id="triage")


@covers("F5")
@pytest.mark.parametrize("outcome", [K.RESULT_INVALID, K.RUNTIME_ERROR])
def test_f5_a_failed_review_is_retried_once(outcome: StageOutcomeKind) -> None:
    expect(decide(reviewed(outcome, Verdict.GREEN)), "F5", RunStage, stage_id="review", mode=StageMode.RETRY)


@covers("F6")
@pytest.mark.parametrize("outcome", [K.RESULT_INVALID, K.RUNTIME_ERROR])
def test_f6_a_review_that_fails_again_escalates_with_result_invalid(outcome: StageOutcomeKind) -> None:
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks"),
        e("review", outcome),
        e("review", outcome, mode=StageMode.RETRY),
        reviews=(make_review(verdict_=Verdict.GREEN),),
    )
    expect(decide(state), "F6", Escalate, code="RESULT_INVALID")


@covers("F7")
def test_f7_a_review_request_accepts_the_report_whatever_the_verdict() -> None:
    for outcome, verdict_ in ((K.VERDICT_GREEN, Verdict.GREEN), (K.VERDICT_RED, Verdict.RED)):
        state = reviewed(
            outcome, verdict_, run={"kind": RunKind.REVIEW_REQUEST, "review_request_id": uid(11)}
        )
        expect(decide(state), "F7", Accept, clearance=ReviewClearance.REPORT)


@covers("F8")
@pytest.mark.parametrize("verdict", [K.VERDICT_GREEN, K.VERDICT_ATTENTION, K.VERDICT_RED])
def test_f8_reviewer_fix_has_to_pass_checks_and_fresh_review(verdict: StageOutcomeKind) -> None:
    fixed = e("review", verdict, out={"output_id": str(OUT)})
    state = make_state(e("prepare"), e("execute"), e("checks"), fixed)
    expect(decide(state), "F8", RunStage, stage_id="checks")
    state = make_state(e("prepare"), e("execute"), e("checks"), fixed, e("checks", round_no=2))
    review_stage = expect(decide(state), "D1", RunStage, stage_id="review")
    assert review_stage.params["reviewer_with_fix"] is False
    assert review_stage.params["profile"] == "reviewer"


# ------------------------------------------------------------------------------------------ H rows


def triaged(*findings: Any, rounds: int = 1, kind: TaskKind = TaskKind.ITEM, **changes: Any) -> TaskState:
    entries = (
        (e("prepare"), e("execute"), e("checks"), e("review", K.VERDICT_RED), e("triage"))
        if kind is TaskKind.ITEM
        else (e("gate_prepare"), e("gate_checks"), e("review", K.VERDICT_RED), e("triage"))
    )
    task = {"review_rounds": rounds, **changes.pop("task", {})}
    return make_state(
        *entries,
        kind=kind,
        status=TaskStatus.REVIEWING,
        task=task,
        findings=findings,
        reviews=(make_review(verdict_=Verdict.RED),),
        **changes,
    )


def finding(n: int, severity: Severity, state: FindingState) -> Any:
    return make_finding(n, severity, state)


@covers("H0")
def test_h0_a_failed_triage_is_retried_then_escalated() -> None:
    state = make_state(
        e("prepare"), e("execute"), e("checks"), e("review", K.VERDICT_RED), e("triage", K.RESULT_INVALID)
    )
    expect(decide(state), "H0", RunStage, stage_id="triage", mode=StageMode.RETRY)
    again = make_state(
        e("prepare"),
        e("execute"),
        e("checks"),
        e("review", K.VERDICT_RED),
        e("triage", K.RESULT_INVALID),
        e("triage", K.RESULT_INVALID, mode=StageMode.RETRY),
    )
    expect(decide(again), "H0", Escalate, code="RESULT_INVALID")
    infra = make_state(e("prepare"), e("review", K.VERDICT_RED), e("triage", K.RUNTIME_ERROR))
    expect(decide(infra), "H0", RunStage, mode=StageMode.RETRY)


@covers("H1")
def test_h1_confirmed_findings_with_rounds_left_rework() -> None:
    confirmed = finding(1, Severity.MAJOR, FindingState.CONFIRMED)
    decision = decide(triaged(confirmed))
    expect(decision, "H1", Rework, reason="review_findings")
    assert ref_kinds(decision) >= {"finding", "review", "output"}
    assert decision.cause["trigger_kind"] == "review_findings"


@covers("H1g")
def test_h1g_a_gate_creates_followups_for_confirmed_major_findings_up_to_the_cap() -> None:
    items = tuple(finding(n, Severity.MAJOR, FindingState.CONFIRMED) for n in range(1, 6))
    decision = decide(triaged(*items, kind=TaskKind.PHASE_GATE))
    action = expect(decision, "H1g", CreateFollowups, reason="review_findings")
    assert len(action.finding_ids) == 3
    assert "FOLLOWUPS_TRUNCATED" in reasons(decision)
    again = decide(triaged(*items, kind=TaskKind.PHASE_GATE), policy={"followups_max": 10})
    assert len(again.action.finding_ids) == 5  # type: ignore[union-attr]


@covers("H2")
def test_h2_exhausted_rounds_without_a_blocker_run_one_final_correction() -> None:
    confirmed = finding(1, Severity.MAJOR, FindingState.CONFIRMED)
    expect(
        decide(triaged(confirmed, rounds=2)),
        "H2",
        RunStage,
        stage_id="execute",
        mode=StageMode.FINAL_CORRECTION,
    )


def test_h2_is_used_once_then_the_owner_decides() -> None:
    confirmed = finding(1, Severity.MAJOR, FindingState.CONFIRMED)
    state = triaged(confirmed, rounds=2)
    used = dataclasses.replace(
        state, history=history(e("execute", mode=StageMode.FINAL_CORRECTION), *state.history.entries)
    )
    decision = decide(used)
    expect(decision, "H3", Escalate, code="REWORK_LIMIT_REACHED")
    assert "FINAL_CORRECTION_UNAVAILABLE" in reasons(decision)
    expect(decide(state, policy={"review_final_correction": False}), "H3", Escalate)


@covers("H3")
def test_h3_a_confirmed_blocker_with_exhausted_rounds_escalates() -> None:
    blocker = finding(1, Severity.BLOCKER, FindingState.CONFIRMED)
    decision = decide(triaged(blocker, rounds=2))
    expect(decision, "H3", Escalate, code="REWORK_LIMIT_REACHED")
    assert "CONFIRMED_BLOCKER" in reasons(decision)


@covers("H4")
def test_h4_rejected_major_findings_go_to_the_advisor() -> None:
    rejected = finding(1, Severity.MAJOR, FindingState.REJECTED)
    action = expect(decide(triaged(rejected)), "H4", RunStage, stage_id="advise")
    assert action.params["problem_ref"] == "findings:1"


@covers("H5")
def test_h5_rejected_major_findings_without_an_advisor_escalate() -> None:
    rejected = finding(1, Severity.MAJOR, FindingState.REJECTED)
    action = expect(
        decide(triaged(rejected), policy={"advisor_enabled": False}), "H5", Escalate, code="NOT_ACCEPTABLE"
    )
    assert action.payload["options"] == ["accept_rejection", "rework", "fail"]


@covers("H6")
def test_h6_nothing_confirmed_accepts_by_triage_and_a_gate_goes_to_its_stage() -> None:
    minor = finding(1, Severity.MINOR, FindingState.REJECTED)
    expect(decide(triaged(minor)), "H6", Accept, clearance=ReviewClearance.CLEARED_BY_TRIAGE)
    expect(decide(triaged(kind=TaskKind.PHASE_GATE)), "H6", RunStage, stage_id="phase_gate")
    only_minor = finding(2, Severity.MINOR, FindingState.CONFIRMED)
    expect(decide(triaged(only_minor, kind=TaskKind.PHASE_GATE)), "H6", RunStage, stage_id="phase_gate")


def final_checks(changed_ok: bool, *, findings_only: bool = True) -> tuple[TaskState, dict[str, Any]]:
    confirmed = finding(1, Severity.MAJOR, FindingState.CONFIRMED)
    output = make_output(outside=() if changed_ok else ("src/app/other.py",))
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks"),
        e("review", K.VERDICT_RED),
        e("triage"),
        e("execute", mode=StageMode.FINAL_CORRECTION, round_no=2),
        e("checks", round_no=2),
        status=TaskStatus.CHECKING,
        task={"review_rounds": 2},
        findings=(confirmed,),
        output=output,
        reviews=(make_review(verdict_=Verdict.RED),),
        checks=passed_checks(),
    )
    return state, {"review_accept_findings_only": findings_only}


@covers("H7")
def test_h7_a_final_correction_inside_the_findings_is_accepted_with_review_debt() -> None:
    state, policy = final_checks(True)
    decision = decide(state, policy=policy)
    expect(decision, "H7", Accept, clearance=ReviewClearance.FINDINGS_ONLY)
    assert "REVIEW_DEBT" in reasons(decision)


@covers("H8")
def test_h8_a_wider_final_correction_escalates_with_the_review_debt() -> None:
    state, policy = final_checks(False)
    action = expect(decide(state, policy=policy), "H8", Escalate, code="NOT_ACCEPTABLE")
    assert action.payload["review_debt"]["paths_outside_findings"] == ["src/app/other.py"]


def test_h7_tests_and_docs_inside_the_write_scope_do_not_widen_the_debt() -> None:
    state, policy = final_checks(True)
    output = make_output(outside=("tests/unit/test_x.py", "docs/guide.md"))
    scope = (PathPattern("app", "tests/**"), PathPattern("app", "docs/**"), PathPattern("app", "src/**"))
    with_scope = dataclasses.replace(
        state, output=output, task=dataclasses.replace(state.task, declared_write_scope=scope)
    )
    expect(decide(with_scope, policy=policy), "H7", Accept)
    unscoped = dataclasses.replace(state, output=output)
    expect(decide(unscoped, policy=policy), "H8", Escalate)


def test_without_accept_findings_only_a_final_correction_is_reviewed_again() -> None:
    state, policy = final_checks(True, findings_only=False)
    decision = decide(state, policy=policy)
    expect(decision, "D1", RunStage, stage_id="review")
    assert "FINDINGS_ONLY_DISABLED" in reasons(decision)


# ------------------------------------------------------------------------------------------ I rows


def advised(
    problem_entries: tuple[StageEntry, ...], outcome: StageOutcomeKind = K.SUCCESS, **changes: Any
) -> TaskState:
    step = make_step(id=uid(91))
    return make_state(e("prepare"), *problem_entries, e("advise", outcome, steps=(step,)), **changes)


@covers("I1")
def test_i1_an_advised_question_continues_the_executor_with_the_answer() -> None:
    open_question = request(DecisionKind.QUESTION, audience=Audience.ADVISOR, n=64)
    state = advised((asked(),), open_requests=(open_question,))
    action = expect(decide(state), "I1", RunStage, stage_id="execute", mode=StageMode.CONTINUE_WITH_ANSWER)
    assert action.feedback == FeedbackRefs(answer_request_ids=(uid(64),))


@covers("I2")
def test_i2_advice_on_failed_checks_grants_exactly_one_extra_rework_round() -> None:
    state = advised(
        (e("execute"), e("checks", K.CHECKS_FAILED)), checks=(failed_check(),), task={"check_fix_rounds": 2}
    )
    action = expect(decide(state), "I2", RunStage, stage_id="execute", mode=StageMode.REWORK)
    assert action.feedback == FeedbackRefs(advice_step_id=uid(91))


@covers("I3")
def test_i3_advice_on_rejected_findings_retriages_with_the_advice() -> None:
    state = advised((e("review", K.VERDICT_RED), e("triage")))
    action = expect(decide(state), "I3", RunStage, stage_id="triage", mode=StageMode.RETRIAGE_WITH_ADVICE)
    assert action.feedback == FeedbackRefs(advice_step_id=uid(91))


@covers("I4")
def test_i4_held_advice_goes_to_the_owner_with_the_advice() -> None:
    held = advised((asked(),), K.HELD)
    held = dataclasses.replace(
        held,
        history=history(
            *held.history.entries[:-1],
            e("advise", K.HELD, out={"advice": {"recommendation": "a"}, "held_reason": "needs_owner"}),
        ),
    )
    action = expect(decide(held), "I4", Escalate, kind=DecisionKind.QUESTION)
    assert action.blocking_code is BlockingCode.WAITING_ANSWER
    assert action.payload["advice"] == {"recommendation": "a"}
    assert "ADVICE_HELD" in reasons(decide(held))
    other = advised((e("execute"), e("checks", K.CHECKS_FAILED)), K.HELD)
    expect(decide(other), "I4", Escalate, kind=DecisionKind.ESCALATION)


@covers("I5")
@pytest.mark.parametrize("outcome", [K.RUNTIME_ERROR, K.RESULT_INVALID])
def test_i5_a_failed_advisor_is_treated_as_no_advisor(outcome: StageOutcomeKind) -> None:
    question_case = decide(advised((asked(),), outcome))
    expect(question_case, "I5", Escalate, kind=DecisionKind.QUESTION, code="QUESTION_NO_ADVISOR")
    assert "ADVISOR_FAILED" in reasons(question_case)
    checks_case = decide(
        advised((e("execute"), e("checks", K.CHECKS_FAILED)), outcome, checks=(failed_check(),))
    )
    expect(checks_case, "I5", Escalate, code="REWORK_LIMIT_REACHED")
    findings_case = decide(advised((e("review", K.VERDICT_RED), e("triage")), outcome))
    expect(findings_case, "I5", Escalate, code="NOT_ACCEPTABLE")


@covers("I6")
@pytest.mark.parametrize("outcome", [K.SUCCESS, K.HELD])
def test_i6_a_plan_audit_is_done_when_the_advice_is_recorded(outcome: StageOutcomeKind) -> None:
    state = make_state(e("prepare"), e("advise", outcome), kind=TaskKind.PLAN_AUDIT)
    audit = workflow("plan-audit") if (WORKFLOWS / "plan-audit.toml").exists() else REVIEWED
    expect(decide(state, audit), "I6", Done)


# ------------------------------------------------------------------------------------------ J rows


def answered(action: str, *, last: tuple[StageEntry, ...] | None = None, **fact: Any) -> TaskState:
    entries = last if last is not None else (e("prepare"), asked())
    return make_state(
        *entries, status=TaskStatus.AWAITING_DECISION, decisions=(DecisionFact(uid(60), action, **fact),)
    )


@covers("J1")
def test_j1_an_answer_continues_the_executor_with_the_answer_request() -> None:
    action = expect(
        decide(answered("answer")), "J1", RunStage, stage_id="execute", mode=StageMode.CONTINUE_WITH_ANSWER
    )
    assert action.feedback == FeedbackRefs(answer_request_ids=(uid(60),))
    assert decide(answered("answer")).cause["trigger_kind"] == "decision_answered"


@covers("J2")
def test_j2_retry_stage_repeats_the_last_stage() -> None:
    state = answered("retry_stage", last=(e("prepare"), e("execute", K.RESULT_INVALID, round_no=2)))
    expect(decide(state), "J2", RunStage, stage_id="execute", mode=StageMode.RETRY, round_no=2)


@covers("J3")
def test_j3_new_attempt_needs_an_attempt_left_or_a_raised_limit() -> None:
    last = (e("prepare"), e("execute", K.RESULT_INVALID))
    expect(decide(answered("new_attempt", last=last)), "J3", NewAttempt, reason_code="OWNER_DECISION")
    spent = answered("new_attempt", last=last)
    spent = dataclasses.replace(spent, task=dataclasses.replace(spent.task, attempt_count=3))
    expect(decide(spent), "J3", Escalate, code="ATTEMPTS_EXHAUSTED")
    raised = dataclasses.replace(spent, decisions=(DecisionFact(uid(60), "new_attempt", raise_limit=True),))
    expect(decide(raised), "J3", NewAttempt)


@covers("J4")
@pytest.mark.parametrize("action", ["accept_deviation", "accept_rejection"])
def test_j4_an_accepted_deviation_accepts_the_output_once_it_is_recorded(action: str) -> None:
    last = (e("prepare"), e("review", K.VERDICT_ATTENTION))
    expect(
        decide(answered(action, last=last, deviation_recorded=True)),
        "J4",
        Accept,
        clearance=ReviewClearance.DEVIATION,
    )
    pending = decide(answered(action, last=last))
    assert isinstance(pending.action, Noop)
    assert "DEVIATION_NOT_RECORDED" in reasons(pending)


@covers("J5")
def test_j5_skip_needs_the_right_to_control_the_run() -> None:
    expect(decide(answered("skip")), "J5", Done)
    denied = decide(answered("skip", control_allowed=False))
    assert isinstance(denied.action, Noop)
    assert "SKIP_NOT_PERMITTED" in reasons(denied)


@covers("J6")
def test_j6_fail_keeps_the_code_of_the_escalation() -> None:
    expect(decide(answered("fail", code="ITEM_BLOCKED")), "J6", Fail, code="ITEM_BLOCKED")
    expect(decide(answered("fail")), "J6", Fail, code="OWNER_DECISION")


@covers("J7")
def test_j7_raise_budget_repeats_the_row_that_the_budget_had_stopped() -> None:
    last = (e("prepare"), e("execute"), e("checks"))
    state = answered("raise_budget", last=last, reconfigured=True)
    state = dataclasses.replace(
        state, task=dataclasses.replace(state.task, review_rounds=0), checks=passed_checks()
    )
    decision = decide(state)
    expect(decision, "J7", RunStage, stage_id="review")
    assert "VIA_D1" in reasons(decision)
    waiting = decide(answered("raise_budget", last=last))
    assert isinstance(waiting.action, Noop)


def test_an_awaiting_task_without_an_answer_does_nothing() -> None:
    state = make_state(e("prepare"), asked(), status=TaskStatus.AWAITING_DECISION)
    assert isinstance(decide(state).action, Noop)


# ------------------------------------------------------------------------------------------ K rows


def gate_record(stage_id: str, outcome: StageOutcomeKind, **out: Any) -> StageEntry:
    return e(stage_id, outcome, out=out or None, started=False)


def integrating(*entries: StageEntry, **changes: Any) -> TaskState:
    changes.setdefault("status", TaskStatus.INTEGRATING)
    return make_state(e("prepare"), e("execute"), e("checks"), *entries, **changes)


@covers("K1")
def test_k1_waiting_reasons_wait_for_the_manual_verdict_or_decision() -> None:
    manual = make_check(CHECK_MANUAL, kind=CheckKind.MANUAL, state=CheckState.MANUAL_PENDING)
    waiting = gate_record("accept", K.NOT_ACCEPTABLE, reasons=[{"code": "MANUAL_PENDING", "refs": {}}])
    action = expect(decide(integrating(waiting, checks=(manual,))), "K1", WaitFor)
    assert action.blocking.code is BlockingCode.WAITING_MANUAL_CHECK
    deviation = gate_record("accept", K.NOT_ACCEPTABLE, reasons=[{"code": "DEVIATION_REQUIRED", "refs": {}}])
    expect(decide(integrating(deviation)), "K1", Escalate, code="DEVIATION_REQUIRED")
    budget = gate_record("accept", K.NOT_ACCEPTABLE, reasons=[{"code": "BUDGET_EXHAUSTED", "refs": {}}])
    expect(decide(integrating(budget)), "K1", Escalate, kind=DecisionKind.BUDGET)


@covers("K2")
def test_k2_a_violation_escalates_with_every_reason() -> None:
    reasons_ = [{"code": "MANUAL_PENDING", "refs": {}}, {"code": "REVIEW_STALE", "refs": {}}]
    action = expect(
        decide(integrating(gate_record("accept", K.NOT_ACCEPTABLE, reasons=reasons_))), "K2", Escalate
    )
    assert action.payload["reasons"] == reasons_
    assert isinstance(decide(integrating(gate_record("accept", K.NOT_ACCEPTABLE))).action, Escalate)


@covers("K3")
def test_k3_an_accepted_executor_output_is_integrated() -> None:
    expect(decide(integrating(gate_record("accept", K.ACCEPTED))), "K3", RunStage, stage_id="integrate")


@covers("K4")
def test_k4_a_workflow_without_integrate_or_a_range_output_is_done() -> None:
    expect(decide(integrating(gate_record("accept", K.ACCEPTED)), RESEARCH), "K4", Done)
    range_output = dataclasses.replace(make_output(), source=OutputSource.RANGE, produced_by_step_id=None)
    expect(decide(integrating(gate_record("accept", K.ACCEPTED), output=range_output)), "K4", Done)


@covers("K5")
def test_k5_a_committed_integration_without_recheck_is_done() -> None:
    expect(decide(integrating(e("integrate")), QUICK), "K5", Done)
    implicit_off = dataclasses.replace(integrating(e("integrate")), rerun_checks_declared=True)
    expect(decide(implicit_off, QUICK), "K5", Done)


def receipt(after: str, *commits: str) -> dict[str, Any]:
    """A ``GitCommitReceipt`` as the integrate outcome schema carries it: per target, no mount."""
    return {
        "ref": "1" * 40,
        "before_sha": "0" * 40,
        "after_sha": after * 40,
        "tree_sha": "2" * 40,
        "commit_shas": [c * 40 for c in commits],
        "target_branch": "main",
        "output_ids": [str(OUT)],
        "request_digest": "sha256:" + "3" * 64,
        "writer_epoch_sha": "4" * 40,
        "receipt_ref": "refs/skm/effects/" + "5" * 8,
        "receipt_commit_sha": "6" * 40,
        "at": "2026-01-01T00:00:00Z",
    }


def two_mounts(*changed_in_other: str) -> Any:
    """The default output with a second mount ``other`` that changed the given paths."""
    base = make_output()
    manifest = dataclasses.replace(
        base.manifest,
        mounts=(*base.manifest.mounts, OutputMount("other", uid(8), "sha1", "a" * 40, "b" * 40, "c" * 40)),
        changed_paths=(
            *base.manifest.changed_paths,
            *(dataclasses.replace(c, mount="other") for c in map(changed, changed_in_other)),
        ),
    )
    return dataclasses.replace(base, manifest=manifest, manifest_digest=manifest_digest(manifest))


def test_the_receipt_fixture_has_the_fields_of_the_schema() -> None:
    schema = json.loads((ROOT / "src/skm/schemas/execution/defs.v1.json").read_text(encoding="utf-8"))
    definition = schema["$defs"]["git-commit-receipt"]
    assert set(receipt("b", "b")) == set(definition["required"])
    assert "mount" not in definition["properties"]
    assert "commit_sha" not in definition["properties"]


@covers("K5a")
def test_k5a_the_recheck_runs_on_the_exact_integrated_commit() -> None:
    outcome = {"integration_receipts": [receipt("b", "a", "b")]}
    action = expect(decide(integrating(e("integrate", out=outcome))), "K5a", RunStage, stage_id="recheck")
    assert action.params["recheck_commits"] == {"app": "b" * 40}
    assert action.params["scope"] == "rerun_after_integration"
    only_shas = integrating(e("integrate", out={"commit_shas": ["c" * 40, "d" * 40]}))
    implicit = dataclasses.replace(only_shas, rerun_checks_declared=True)
    again = decide(implicit, QUICK, {"integration_rerun_checks": True})
    assert again.action.params["recheck_commits"] == {"app": "d" * 40}  # type: ignore[union-attr]
    expect(again, "K5a", RunStage, stage_id="recheck")


def test_k5a_a_receipt_without_commits_pins_its_after_sha() -> None:
    outcome = {"integration_receipts": [receipt("e")]}
    action = decide(integrating(e("integrate", out=outcome))).action
    assert action.params["recheck_commits"] == {"app": "e" * 40}  # type: ignore[union-attr]


def unbound(decision: ActionDecision) -> Escalate:
    """K5c without a recheck: the commit of no mount is proven, the owner is asked for ``recheck_commits``."""
    action = expect(decision, "K5c", Escalate, code="INTEGRATION_RECHECK_FAILED")
    assert action.payload["options"] == ["retry_stage", "fail"]
    assert action.payload["recheck_commits_required"] is True
    assert "RECHECK_COMMITS_UNKNOWN" in reasons(decision)
    return action


def test_k5a_several_mounts_are_not_paired_with_receipts_by_position() -> None:
    """Receipts carry no mount: equal counts in manifest order prove nothing, so no mount is pinned."""
    outcome = {"integration_receipts": [receipt("a", "a"), receipt("b", "c", "b")]}
    state = integrating(e("integrate", out=outcome), output=two_mounts("src/other.py"))
    action = unbound(decide(state))
    assert action.payload["mounts"] == ["app", "other"]
    swapped = {"integration_receipts": [receipt("b", "c", "b"), receipt("a", "a")]}
    unbound(decide(integrating(e("integrate", out=swapped), output=two_mounts("src/other.py"))))


@pytest.mark.parametrize(
    "outcome",
    [
        {"integration_receipts": [receipt("a", "a")], "commit_shas": ["f" * 40]},
        {"commit_shas": ["f" * 40]},
        {"integration_receipts": [receipt("a", "a"), receipt("b", "b"), receipt("c", "c")]},
    ],
    ids=["fewer-receipts-than-mounts", "bare-shas-of-several-mounts", "more-receipts-than-mounts"],
)
def test_k5a_mismatched_counts_of_receipts_and_mounts_ask_the_owner(outcome: dict[str, Any]) -> None:
    state = integrating(e("integrate", out=outcome), output=two_mounts("src/other.py"))
    unbound(decide(state))


@pytest.mark.parametrize(
    "outcome",
    [
        {"integration_receipts": [receipt("a", "a"), receipt("b", "b")]},
        {"integration_receipts": [{**receipt("a", "a"), "output_ids": [str(uid(999))]}]},
        {"integration_receipts": [{**receipt("a", "a"), "output_ids": []}]},
        {"integration_receipts": [{**receipt("a", "a"), "commit_shas": [], "after_sha": None}]},
        {"integration_receipts": ["not a receipt"], "commit_shas": ["f" * 40]},
        {"integration_receipts": "garbage", "commit_shas": ["f" * 40]},
        {},
    ],
    ids=["two-receipts", "other-output", "no-output", "no-tip", "garbage-receipt", "garbage-list", "nothing"],
)
def test_k5a_a_single_mount_is_pinned_only_by_one_receipt_that_names_its_output(
    outcome: dict[str, Any],
) -> None:
    unbound(decide(integrating(e("integrate", out=outcome))))


def test_k5d_a_retried_recheck_without_an_approved_or_provable_commit_is_not_run() -> None:
    unbound(
        decide(integrating(e("integrate", out={"integration_receipts": []}), e("recheck", K.CHECKS_UNKNOWN)))
    )
    several = integrating(
        e("integrate", out={"integration_receipts": [receipt("a", "a"), receipt("b", "b")]}),
        e("recheck", K.CHECKS_UNKNOWN),
        output=two_mounts("src/other.py"),
    )
    unbound(decide(several))
    approved = {"app": "9" * 40, "other": "8" * 40}
    record = several.history.entries[-1].record
    recorded = dataclasses.replace(
        several,
        instructions={record.id: RecordedInstruction({"recheck_commits": cast("JsonValue", approved)})},
    )
    action = expect(decide(recorded), "K5d", RunStage, stage_id="recheck", mode=StageMode.RETRY)
    assert action.params["recheck_commits"] == approved


def test_j2_the_owner_commits_start_the_recheck_that_k5a_could_not_pin() -> None:
    approved = {"app": "9" * 40, "other": "8" * 40}
    last = (e("integrate", out={"integration_receipts": [receipt("a", "a"), receipt("b", "b")]}),)
    state = dataclasses.replace(
        answered("retry_stage", last=last, value={"recheck_commits": approved}),
        output=two_mounts("src/other.py"),
        rerun_checks_declared=True,
    )
    action = expect(
        decide(state, QUICK, {"integration_rerun_checks": True}), "J2", RunStage, stage_id="recheck"
    )
    assert action.mode is StageMode.NORMAL
    assert action.params["recheck_commits"] == approved
    assert action.params["scope"] == "rerun_after_integration"
    without = dataclasses.replace(state, decisions=(DecisionFact(uid(60), "retry_stage"),))
    unbound(decide(without, QUICK, {"integration_rerun_checks": True}))


def test_j2_a_red_recheck_retried_without_commits_does_not_run_unbound() -> None:
    plain = make_state(e("integrate"), e("recheck", K.CHECKS_FAILED), status=TaskStatus.AWAITING_DECISION)
    state = dataclasses.replace(plain, decisions=(DecisionFact(uid(60), "retry_stage"),))
    unbound(decide(state))
    approved = {"app": "9" * 40}
    value = cast("JsonValue", {"recheck_commits": approved})
    given = dataclasses.replace(plain, decisions=(DecisionFact(uid(60), "retry_stage", value=value),))
    action = expect(decide(given), "J2", RunStage, stage_id="recheck", mode=StageMode.RETRY)
    assert action.params["recheck_commits"] == approved


@covers("K5b")
def test_k5b_a_green_recheck_is_done() -> None:
    state = integrating(e("integrate"), e("recheck"), checks=passed_checks())
    expect(decide(state), "K5b", Done)


@covers("K5c")
def test_k5c_a_red_recheck_escalates_and_never_reverts() -> None:
    state = integrating(e("integrate"), e("recheck", K.CHECKS_FAILED), checks=(failed_check(),))
    action = expect(decide(state), "K5c", Escalate, code="INTEGRATION_RECHECK_FAILED")
    assert action.payload["options"] == ["retry_stage", "fail"]
    erred = integrating(
        e("integrate"),
        e("recheck", K.CHECKS_ERROR),
        e("recheck", K.CHECKS_ERROR),
        checks=(make_check(uid(500), state=CheckState.ERROR),),
    )
    expect(decide(erred), "K5c", Escalate)


@covers("K5d")
def test_k5d_an_unknown_or_first_errored_recheck_is_retried() -> None:
    pinned = e("integrate", out={"integration_receipts": [receipt("b", "b")]})
    expect(
        decide(integrating(pinned, e("recheck", K.CHECKS_UNKNOWN))),
        "K5d",
        RunStage,
        stage_id="recheck",
        mode=StageMode.RETRY,
    )
    erred = integrating(
        pinned, e("recheck", K.CHECKS_ERROR), checks=(make_check(uid(500), state=CheckState.ERROR),)
    )
    expect(decide(erred), "K5d", RunStage, mode=StageMode.RETRY)


@covers("K6")
def test_k6_a_conflict_waits_for_an_integration_task_with_a_stable_id() -> None:
    state = integrating(e("integrate", K.CONFLICT))
    first = decide(state)
    action = expect(first, "K6", WaitFor, release_assignment=True)
    assert action.blocking.code is BlockingCode.BLOCKED_BY_INTEGRATION
    assert "INTEGRATION_TASK_REQUIRED" in reasons(first)
    assert decide(state) == first


@covers("K7")
def test_k7_an_unknown_integration_outcome_reconciles() -> None:
    expect(
        decide(integrating(e("integrate", K.OUTCOME_UNKNOWN))),
        "K7",
        RunStage,
        stage_id="integrate",
        mode=StageMode.RECONCILE,
    )


@covers("K8")
def test_k8_a_proposed_intent_asks_for_approval() -> None:
    out = {"intent_id": "intent-1", "effect_id": "effect-1", "intent_state": "proposed"}
    action = expect(
        decide(integrating(e("integrate", K.APPROVAL_REQUIRED, out=out))),
        "K8",
        Escalate,
        kind=DecisionKind.APPROVAL,
    )
    assert action.blocking_code is BlockingCode.WAITING_APPROVAL
    assert action.payload["refs"] == {"intent_id": "intent-1", "effect_id": "effect-1"}


@covers("K8a")
def test_k8a_an_approved_intent_executes_the_effect_on_the_same_stage() -> None:
    out = {"intent_id": "intent-1", "effect_id": "effect-1", "intent_state": "approved"}
    action = expect(
        decide(integrating(e("integrate", K.APPROVAL_REQUIRED, out=out))),
        "K8a",
        RunStage,
        stage_id="integrate",
    )
    assert action.params["effect_id"] == "effect-1"


@covers("K9")
def test_k9_an_integration_infrastructure_failure_is_retried() -> None:
    expect(
        decide(integrating(e("integrate", K.RUNTIME_ERROR))),
        "K9",
        RunStage,
        stage_id="integrate",
        mode=StageMode.RETRY,
    )


@covers("K10")
def test_k10_a_stopped_integration_escalates() -> None:
    stop = e("integrate", K.RUNTIME_ERROR, code="RUNTIME_FORBIDDEN")
    expect(decide(integrating(stop)), "K10", Escalate, code="RUNTIME_FORBIDDEN")
    conflict = e("integrate", K.RUNTIME_ERROR, code="INTEGRATION_CONFLICT")
    expect(decide(integrating(conflict)), "K10", Escalate, code="INTEGRATION_CONFLICT")
    handler = dataclasses.replace(
        REVIEWED,
        stages=tuple(
            dataclasses.replace(s, on=dataclasses.replace(s.on, conflict="escalate"))
            if s.id == "integrate"
            else s
            for s in REVIEWED.stages
        ),
    )
    expect(
        decide(integrating(e("integrate", K.CONFLICT)), handler), "K10", Escalate, code="INTEGRATION_CONFLICT"
    )


@covers("K13")
def test_k13_a_host_mismatch_offers_a_new_attempt_or_failure() -> None:
    mismatch = e("integrate", K.RUNTIME_ERROR, code="INTEGRATION_HOST_MISMATCH")
    action = expect(decide(integrating(mismatch)), "K13", Escalate, code="INTEGRATION_HOST_MISMATCH")
    assert action.payload["options"] == ["new_attempt", "fail"]


@covers("K11")
def test_k11_a_phase_gate_decision_ends_the_gate_or_waits_like_k1_k2() -> None:
    gate: dict[str, Any] = {"kind": TaskKind.PHASE_GATE, "status": TaskStatus.INTEGRATING}
    entries = (e("gate_prepare"), e("gate_checks"))
    accepted = make_state(*entries, gate_record("phase_gate", K.ACCEPTED), **gate)
    expect(decide(accepted), "K11", Done)
    rejected = gate_record("phase_gate", K.NOT_ACCEPTABLE, reasons=[{"code": "REVIEW_STALE", "refs": {}}])
    expect(decide(make_state(*entries, rejected, **gate)), "K2", Escalate)


@covers("K12")
def test_k12_plan_acceptance_ends_follows_up_or_escalates_with_the_coverage() -> None:
    gate: dict[str, Any] = {"kind": TaskKind.PLAN_ACCEPTANCE, "status": TaskStatus.INTEGRATING}
    entries = (e("gate_prepare"), e("gate_checks"))
    expect(decide(make_state(*entries, gate_record("plan_acceptance", K.ACCEPTED), **gate)), "K12", Done)
    rejected = gate_record("plan_acceptance", K.NOT_ACCEPTABLE, coverage={"uncovered": ["AC-1"]})
    followups = make_state(*entries, rejected, checks=(failed_check(),), task={"review_rounds": 1}, **gate)
    expect(decide(followups), "K12", CreateFollowups, reason="checks_failed")
    exhausted = make_state(*entries, rejected, checks=(failed_check(),), task={"review_rounds": 2}, **gate)
    action = expect(decide(exhausted), "K12", Escalate, code="NOT_ACCEPTABLE")
    assert action.payload["coverage"] == {"uncovered": ["AC-1"]}


# ---------------------------------------------------------------------------- engine-wide properties


def test_every_row_of_the_table_has_a_case() -> None:
    proven = {row for name, rows in COVERED.items() for row in rows}
    assert proven == set(ADVANCE_RULES), sorted(set(ADVANCE_RULES) ^ proven)
    # the registry lists exactly the rows of the owner table
    table = (ROOT / "tests/fixtures/corpus/examples/execution/advance-decision-table.md").read_text(
        encoding="utf-8"
    )
    listed = set(re.findall(r"^\| ([A-Z][A-Za-z0-9]*) \|", table, flags=re.MULTILINE)) - {"#"}
    assert listed == set(ADVANCE_RULES)


def test_rule_ids_match_the_history_pattern() -> None:
    assert all(RULE_ID_PATTERN.fullmatch(rule) for rule in ADVANCE_RULES)
    assert {"K5b", "L2i", "SE8r"} - set(ADVANCE_RULES) == {
        "SE8r"
    }  # SE8r is a session row, not an advance row
    assert RULE_ID_PATTERN.fullmatch("SE8r")


def test_the_evaluator_emits_only_registered_rules_and_valid_causes() -> None:
    states = [make_state(e("prepare")), make_state(), integrating(e("integrate")), triaged()]
    for state in states:
        cause = decide(state).cause
        assert cause["advance_rule"] in ADVANCE_RULES | {None}
        assert set(cause) == {"trigger_kind", "advance_rule", "reason_codes", "refs"}
        json.dumps(cause)


def test_advance_is_the_action_of_decide_advance() -> None:
    state = make_state(e("prepare"))
    assert advance(state, REVIEWED, cast("Any", {}), NOW) == decide(state).action


def test_repeating_advance_on_the_same_state_gives_the_same_decision() -> None:
    states = [
        make_state(e("prepare"), e("execute"), e("checks", K.CHECKS_FAILED), checks=(failed_check(),)),
        make_state(e("prepare"), asked()),
        reviewed(K.VERDICT_RED, Verdict.RED),
        integrating(e("integrate", K.CONFLICT)),
    ]
    for state in states:
        first = decide(state)
        assert decide(state) == first
        assert decide(dataclasses.replace(state)) == first


def test_the_evaluator_does_not_read_the_clock_or_the_state_of_the_policy_argument() -> None:
    state = make_state(
        e("prepare"), e("execute", K.RUNTIME_ERROR, code="RATE_LIMITED", out={"retry_after_seconds": 30})
    )
    early = decide_advance(state, REVIEWED, cast("Any", {}), NOW)
    later = decide_advance(state, REVIEWED, cast("Any", {}), NOW + timedelta(hours=1))
    assert early.action.not_before == NOW + timedelta(seconds=30)  # type: ignore[union-attr]
    assert later.action.not_before == NOW + timedelta(hours=1, seconds=30)  # type: ignore[union-attr]
    # the policy of the call decides, not the frozen copy inside the state
    stale = dataclasses.replace(state, effective_policy={"kill_switch": True})
    assert decide(stale).cause["advance_rule"] == "C11"


@pytest.mark.parametrize(
    "status", [TaskStatus.CHECKING, TaskStatus.REWORK_REQUIRED, TaskStatus.EXECUTING, TaskStatus.REVIEWING]
)
def test_a_decision_follows_the_history_not_the_status_a_transition_already_changed(
    status: TaskStatus,
) -> None:
    """The same history gives the same row whatever status an applied transition left (C1/D6 replay)."""
    state = make_state(
        e("prepare"), e("execute"), e("checks", K.CHECKS_FAILED), checks=(failed_check(),), status=status
    )
    expect(decide(state), "D6", Rework, reason="checks_failed")
    after_execute = make_state(e("prepare"), e("execute"), status=status)
    expect(decide(after_execute), "C1", RunStage, stage_id="checks")


def test_a_stage_that_is_still_running_is_left_alone() -> None:
    state = make_state(e("prepare"), e("execute", None, state=StageState.RUNNING, started=True))
    decision = decide(state)
    assert isinstance(decision.action, Noop)
    assert decision.cause["advance_rule"] is None


def test_skipped_records_do_not_decide_the_next_action() -> None:
    skipped = e("scout", None, state=StageState.SKIPPED, started=False)
    state = make_state(e("prepare"), skipped)
    expect(decide(state), "A3", RunStage, stage_id="execute")


STATE_SHAPES = st.sampled_from(
    [
        make_state,
        lambda: make_state(e("prepare")),
        lambda: make_state(e("prepare"), e("execute")),
        lambda: make_state(
            e("prepare"), e("execute"), e("checks", K.CHECKS_FAILED), checks=(failed_check(),)
        ),
        lambda: reviewed(K.VERDICT_ATTENTION, Verdict.ATTENTION),
        lambda: integrating(e("integrate")),
    ]
)


@settings(max_examples=40, deadline=None)
@given(shape=STATE_SHAPES, review_mode=st.sampled_from(list(ReviewMode)), rounds=st.integers(0, 4))
def test_decisions_are_deterministic_for_equal_states(
    shape: Callable[[], TaskState], review_mode: ReviewMode, rounds: int
) -> None:
    state = shape()
    state = dataclasses.replace(
        state,
        task=dataclasses.replace(state.task, review_mode=review_mode, check_fix_rounds=rounds),
    )
    assert decide(state) == decide(dataclasses.replace(state))


ADVANCE_LAYERS = (
    "actions",
    "engine",
)


def test_advance_modules_import_only_earlier_layers() -> None:
    """The row modules are a chain under the engine facade: nothing reaches back, so no import cycle."""
    package = Path(cast("str", engine_module.__file__)).parent
    prefix = "skm.modules.execution.domain.workflow."
    for index, name in enumerate(ADVANCE_LAYERS):
        tree = ast.parse((package / f"{name}.py").read_text(encoding="utf-8"))
        imported = {
            node.module.removeprefix(prefix)
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith(prefix)
        }
        assert imported & set(ADVANCE_LAYERS) <= set(ADVANCE_LAYERS[:index]), name


def test_engine_facade_keeps_its_public_names() -> None:
    assert sorted(engine_module.__all__) == [
        "ActionDecision",
        "DECISION_ACTIONS",
        "DecisionFact",
        "TaskState",
        "advance",
        "decide_advance",
    ]
    assert engine_module.TaskState is advance_context.TaskState
    assert engine_module.ActionDecision is advance_context.ActionDecision
    assert engine_module.DecisionFact is advance_context.DecisionFact
    assert engine_module.DECISION_ACTIONS is advance_context.DECISION_ACTIONS


# ------------------------------------------------------------------------- corrections of the review


def test_k5d_a_retried_recheck_keeps_the_commits_k5a_pinned() -> None:
    outcome = {"integration_receipts": [receipt("b", "b")]}
    for kind in (K.CHECKS_UNKNOWN, K.CHECKS_ERROR):
        state = integrating(
            e("integrate", out=outcome),
            e("recheck", kind),
            checks=(make_check(uid(500), state=CheckState.ERROR),),
        )
        action = expect(decide(state), "K5d", RunStage, stage_id="recheck", mode=StageMode.RETRY)
        assert action.params["recheck_commits"] == {"app": "b" * 40}
        assert action.params["scope"] == "rerun_after_integration"


def test_a_retry_reuses_the_recorded_instruction_of_the_stage_record() -> None:
    approved = {"app": "9" * 40}
    state = integrating(e("integrate"), e("recheck", K.CHECKS_UNKNOWN, mode=StageMode.RETRY))
    record = state.history.entries[-1].record
    recorded = dataclasses.replace(
        state, instructions={record.id: RecordedInstruction({"recheck_commits": cast("JsonValue", approved)})}
    )
    action = expect(decide(recorded), "K5d", RunStage, stage_id="recheck", mode=StageMode.RETRY)
    assert action.params["recheck_commits"] == approved


def test_a_retry_keeps_the_fix_brief_and_a_repeat_after_an_interruption_keeps_all_feedback() -> None:
    brief = FeedbackRefs(fix_brief_id=uid(95), answer_request_ids=(uid(64),))
    failed = make_state(
        e("prepare"),
        e("execute", K.RUNTIME_ERROR, mode=StageMode.REWORK, round_no=2),
        task={"check_fix_rounds": 1},
    )
    record = failed.history.entries[-1].record
    with_brief = dataclasses.replace(failed, instructions={record.id: RecordedInstruction(feedback=brief)})
    retried = expect(decide(with_brief), "C11", RunStage, mode=StageMode.RETRY)
    assert retried.feedback == brief
    cut = make_state(
        e("execute", None, state=StageState.INTERRUPTED, started=False, mode=StageMode.REWORK, round_no=2)
    )
    keep = dataclasses.replace(
        cut, instructions={cut.history.entries[-1].record.id: RecordedInstruction(feedback=brief)}
    )
    assert expect(decide(keep), "L1", RunStage, mode=StageMode.REWORK).feedback == brief


def test_h8_the_same_path_in_another_mount_is_not_covered_by_the_finding() -> None:
    state, policy = final_checks(True)
    other = dataclasses.replace(state, output=two_mounts("src/app/x.py"))
    action = expect(decide(other, policy=policy), "H8", Escalate, code="NOT_ACCEPTABLE")
    debt = action.payload["review_debt"]
    assert debt["changes_outside_findings"] == [{"mount": "other", "path": "src/app/x.py"}]
    assert debt["paths_outside_findings"] == ["src/app/x.py"]


def test_h7_the_tests_and_docs_exception_is_per_mount() -> None:
    state, policy = final_checks(True)
    scope = (PathPattern("app", "tests/**"), PathPattern("app", "src/**"))
    scoped = dataclasses.replace(
        state,
        task=dataclasses.replace(state.task, declared_write_scope=scope),
        output=two_mounts("tests/t.py"),
    )
    expect(decide(scoped, policy=policy), "H8", Escalate)
    inside = dataclasses.replace(
        scoped,
        task=dataclasses.replace(
            scoped.task, declared_write_scope=(*scope, PathPattern("other", "tests/**"))
        ),
    )
    expect(decide(inside, policy=policy), "H7", Accept)


def test_h6_a_confirmed_finding_of_an_earlier_review_that_the_next_review_omitted_stays_open() -> None:
    carried = finding(1, Severity.MAJOR, FindingState.CONFIRMED)
    second = make_review(uid(601), round_no=2, verdict_=Verdict.RED)
    state = dataclasses.replace(
        triaged(carried, rounds=1), reviews=(make_review(verdict_=Verdict.RED), second)
    )
    decision = decide(state)
    expect(decision, "H1", Rework, reason="review_findings")
    assert ("finding", str(carried.id)) in {(r["kind"], r["id"]) for r in decision.cause["refs"]}  # type: ignore[union-attr]
    exhausted = dataclasses.replace(state, task=dataclasses.replace(state.task, review_rounds=2))
    expect(decide(exhausted), "H2", RunStage, mode=StageMode.FINAL_CORRECTION)


def test_h6_a_finding_resolved_by_the_correction_no_longer_blocks() -> None:
    resolved = finding(1, Severity.MAJOR, FindingState.RESOLVED)
    second = make_review(uid(601), round_no=2, verdict_=Verdict.RED)
    state = dataclasses.replace(
        triaged(resolved, rounds=1), reviews=(make_review(verdict_=Verdict.RED), second)
    )
    expect(decide(state), "H6", Accept, clearance=ReviewClearance.CLEARED_BY_TRIAGE)


def test_a_repeated_confirmed_finding_counts_once_with_its_latest_row() -> None:
    first = finding(1, Severity.MAJOR, FindingState.CONFIRMED)
    again = make_finding(1, Severity.MAJOR, FindingState.REJECTED, review_id=uid(601))
    assert again.finding_key == first.finding_key
    second = make_review(uid(601), round_no=2, verdict_=Verdict.RED)
    state = dataclasses.replace(
        triaged(first, again, rounds=1), reviews=(make_review(verdict_=Verdict.RED), second)
    )
    assert expect(decide(state), "H4", RunStage, stage_id="advise")


def test_c14_the_retry_budget_of_the_run_is_shared_by_its_tasks() -> None:
    state = make_state(e("prepare"), e("execute", K.RUNTIME_ERROR))
    policy = {"retry_budget_total_max": 1}
    expect(decide(state, policy=policy), "C11", RunStage, mode=StageMode.RETRY)
    spent = dataclasses.replace(state, run_retries_used=1)
    expect(decide(spent, policy=policy), "C14", Escalate, code="RUNTIME_TRANSPORT")


def test_c14_the_default_retry_budget_of_the_run_is_six() -> None:
    assert advance_context.DEFAULT_RETRY_BUDGET == 6
    retries = [e("execute", K.RUNTIME_ERROR, mode=StageMode.RETRY) for _ in range(6)]
    state = make_state(e("prepare"), e("execute", K.RUNTIME_ERROR), *retries)
    policy = {"step_max_infra_retries": 99}
    expect(decide(state, policy=policy), "C14", Escalate, code="RUNTIME_TRANSPORT")
    fewer = make_state(e("prepare"), e("execute", K.RUNTIME_ERROR), *retries[:5])
    expect(decide(fewer, policy=policy), "C11", RunStage, mode=StageMode.RETRY)


def test_c14_an_unknown_run_wide_retry_count_is_not_zero_and_stops_the_repeat() -> None:
    state = make_state(e("prepare"), e("execute", K.RUNTIME_ERROR), run_retries_used=None)
    decision = decide(state)
    expect(decision, "C14", Escalate, code="RUNTIME_TRANSPORT")
    assert "RUN_RETRIES_UNKNOWN" in reasons(decision)
    for known in (0, 1, 5):
        expect(
            decide(dataclasses.replace(state, run_retries_used=known)), "C11", RunStage, mode=StageMode.RETRY
        )
    assert TaskState.__dataclass_fields__["run_retries_used"].default is None


def test_c14_an_explicit_zero_run_count_keeps_the_retry_and_a_larger_one_stops_it() -> None:
    state = make_state(e("prepare"), e("execute", K.RUNTIME_ERROR), run_retries_used=0)
    policy = {"retry_budget_total_max": 1}
    assert "RUN_RETRIES_UNKNOWN" not in reasons(decide(state, policy=policy))
    expect(decide(state, policy=policy), "C11", RunStage, mode=StageMode.RETRY)
    expect(decide(dataclasses.replace(state, run_retries_used=6)), "C14", Escalate)


def test_c14_an_unknown_run_count_does_not_hide_the_retries_of_the_task_itself() -> None:
    retries = [e("execute", K.RUNTIME_ERROR, mode=StageMode.RETRY) for _ in range(6)]
    state = make_state(e("prepare"), e("execute", K.RUNTIME_ERROR), *retries, run_retries_used=None)
    policy = {"step_max_infra_retries": 99}
    decision = decide(state, policy=policy)
    expect(decision, "C14", Escalate, code="RUNTIME_TRANSPORT")
    assert "BUDGET_EXHAUSTED" in reasons(decision)


def test_c14_an_unknown_run_count_changes_no_decision_that_is_not_a_repeat() -> None:
    state = make_state(e("prepare"), e("execute", K.RUNTIME_ERROR, code="RUNTIME_FORBIDDEN"))
    unknown = dataclasses.replace(state, run_retries_used=None)
    assert reasons(decide(unknown)) == reasons(decide(state))
    assert "RUN_RETRIES_UNKNOWN" not in reasons(decide(unknown))


def test_an_unknown_run_count_stops_a_quota_wait_without_promising_a_budget_reset() -> None:
    state = make_state(
        e("prepare"),
        e("execute", K.RUNTIME_ERROR, code="QUOTA_EXHAUSTED", out={"retry_after_seconds": 60}),
        run_retries_used=None,
    )
    action = expect(decide(state), "C14", Escalate)
    assert action.blocking_code is BlockingCode.WAITING_OWNER
    known = dataclasses.replace(state, run_retries_used=0)
    assert isinstance(decide(known).action, RunStage)


def review_account(spent: int, reserved: int = 0, limit: int = 1) -> dict[str, Any]:
    return {
        "accounts": [
            {
                "scope": "run",
                "dimension": "review_rounds",
                "limit": limit,
                "spent": spent,
                "reserved": reserved,
            }
        ]
    }


def test_g7_an_exhausted_review_round_account_stops_the_required_review() -> None:
    state = make_state(
        e("prepare"), e("execute"), e("checks"), task={"review_rounds": 0}, checks=passed_checks()
    )
    expect(decide(state), "D1", RunStage, stage_id="review")
    stopped = dataclasses.replace(state, budget=review_account(spent=1))
    action = expect(decide(stopped), "G7", Escalate, code="BUDGET_EXHAUSTED")
    assert action.payload["dimension"] == "review_rounds"
    reserved = dataclasses.replace(state, budget=review_account(spent=0, reserved=1))
    expect(decide(reserved), "G7", Escalate)
    room = dataclasses.replace(state, budget=review_account(spent=0, limit=2))
    expect(decide(room), "D1", RunStage, stage_id="review")


def test_g7_review_rounds_do_not_stop_a_stage_that_is_not_a_review() -> None:
    state = make_state(e("prepare"), budget=review_account(spent=1))
    expect(decide(state), "A3", RunStage, stage_id="execute")


@pytest.mark.parametrize("origin", ["question", "checks", "findings"])
def test_i_advice_after_a_failed_advisor_and_an_owner_retry_keeps_its_origin(origin: str) -> None:
    problem: dict[str, tuple[StageEntry, ...]] = {
        "question": (asked(),),
        "checks": (e("execute"), e("checks", K.CHECKS_FAILED)),
        "findings": (e("review", K.VERDICT_RED), e("triage")),
    }
    extra: dict[str, Any] = {"checks": (failed_check(),)} if origin == "checks" else {}
    extra["task"] = {"check_fix_rounds": 2} if origin == "checks" else {}
    state = make_state(
        e("prepare"),
        *problem[origin],
        e("advise", K.RUNTIME_ERROR),
        e("advise", mode=StageMode.RETRY, out={"advice": {}, "held": False}),
        **extra,
    )
    rule = {"question": "I1", "checks": "I2", "findings": "I3"}[origin]
    decision = decide(state)
    assert decision.cause["advance_rule"] == rule, decision
    assert "ADVICE_UNUSABLE" not in reasons(decision)


def test_k5a_multi_mount_recheck_runs_when_authoritative_mount_bindings_exist() -> None:
    r_app = receipt("b", "a", "b")
    r_other = receipt("e")  # no-op integration preserves after_sha
    outcome = {"integration_receipts": [r_app, r_other]}
    bound = integrating(
        e("integrate", out=outcome),
        output=two_mounts("src/other.py"),
        integration_receipts_by_mount={"app": r_app, "other": r_other},
    )
    action = expect(decide(bound), "K5a", RunStage, stage_id="recheck")
    assert action.params["recheck_commits"] == {"app": "b" * 40, "other": "e" * 40}
    assert action.params["scope"] == "rerun_after_integration"
    retried = integrating(
        e("integrate", out=outcome),
        e("recheck", K.CHECKS_UNKNOWN),
        output=two_mounts("src/other.py"),
        integration_receipts_by_mount={"app": r_app, "other": r_other},
        checks=(make_check(uid(500), state=CheckState.ERROR),),
    )
    retry_action = expect(decide(retried), "K5d", RunStage, stage_id="recheck", mode=StageMode.RETRY)
    assert retry_action.params["recheck_commits"] == {"app": "b" * 40, "other": "e" * 40}
    by_shas = integrating(
        e("integrate", out=outcome),
        output=two_mounts("src/other.py"),
        recheck_commits={"app": "b" * 40, "other": "e" * 40},
    )
    sha_action = expect(decide(by_shas), "K5a", RunStage, stage_id="recheck")
    assert sha_action.params["recheck_commits"] == {"app": "b" * 40, "other": "e" * 40}


def test_k5c_multi_mount_recheck_fails_closed_when_mount_bindings_are_missing_or_invalid() -> None:
    r_app = receipt("a", "a")
    r_other = receipt("b", "b")
    outcome = {"integration_receipts": [r_app, r_other]}
    # Missing binding for changed mount "other"
    missing_mount = integrating(
        e("integrate", out=outcome),
        output=two_mounts("src/other.py"),
        integration_receipts_by_mount={"app": r_app},
    )
    unbound(decide(missing_mount))
    # Receipt bound to wrong output_id
    wrong_out = {**r_other, "output_ids": [str(uid(999))]}
    mismatch_output = integrating(
        e("integrate", out={"integration_receipts": [r_app, wrong_out]}),
        output=two_mounts("src/other.py"),
        integration_receipts_by_mount={"app": r_app, "other": wrong_out},
    )
    unbound(decide(mismatch_output))
    # Unverified worker-supplied mount labels on outcome receipts are never trusted without TaskState binding
    unverified_labels = {"integration_receipts": [{**r_app, "mount": "app"}, {**r_other, "mount": "other"}]}
    unbound(decide(integrating(e("integrate", out=unverified_labels), output=two_mounts("src/other.py"))))
    # TaskState recheck_commits conflicting with stage outcome receipts fails closed
    conflicting_shas = integrating(
        e("integrate", out=outcome),
        output=two_mounts("src/other.py"),
        recheck_commits={"app": "a" * 40, "other": "c" * 40},
    )
    unbound(decide(conflicting_shas))


def test_h1g_confirmed_major_findings_on_group_review_create_followups() -> None:
    found = finding(1, Severity.MAJOR, FindingState.CONFIRMED)
    state = make_state(
        e("prepare"),
        e("review", K.VERDICT_RED),
        e("triage"),
        kind=TaskKind.GROUP_REVIEW,
        status=TaskStatus.REVIEWING,
        task={"review_rounds": 1},
        findings=(found,),
        reviews=(make_review(verdict_=Verdict.RED),),
    )
    action = expect(decide(state), "H1g", CreateFollowups)
    assert action.finding_ids == (found.id,)


def test_c2_question_on_task_touching_or_declaring_security_paths_never_bypasses_owner() -> None:
    sec_output = make_output(outside=("src/auth/login.py",))
    by_output = make_state(
        e("prepare"),
        asked(),
        output=sec_output,
        task={"declared_write_scope": (PathPattern("app", "src/**"),)},
    )
    act_out = expect(
        decide(by_output, policy={"question_policy": "defaults"}),
        "C2",
        Escalate,
        kind=DecisionKind.QUESTION,
        code="QUESTION_GATED",
    )
    assert "security" in act_out.payload["gate_categories"]
    by_scope = make_state(
        e("prepare"),
        asked(),
        output=None,
        task={"declared_write_scope": (PathPattern("app", "src/security/**"),)},
    )
    act_scope = expect(
        decide(by_scope, policy={"question_policy": "defaults"}),
        "C2",
        Escalate,
        kind=DecisionKind.QUESTION,
        code="QUESTION_GATED",
    )
    assert "security" in act_scope.payload["gate_categories"]


def test_retrying_continue_with_answer_preserves_answer_request_ids_and_all_feedback() -> None:
    feedback = FeedbackRefs(
        fix_brief_id=uid(95),
        answer_request_ids=(uid(60), uid(61)),
        advice_step_id=uid(91),
    )
    failed = make_state(
        e("prepare"),
        e("execute", K.RUNTIME_ERROR, mode=StageMode.CONTINUE_WITH_ANSWER),
    )
    rec = failed.history.entries[-1].record
    state = dataclasses.replace(failed, instructions={rec.id: RecordedInstruction(feedback=feedback)})
    c11 = expect(decide(state), "C11", RunStage, mode=StageMode.RETRY)
    assert c11.feedback == feedback
    invalid_step = make_step(id=uid(88), schema_errors=("missing field",))
    invalid = make_state(
        e("prepare"),
        e("execute", K.RESULT_INVALID, mode=StageMode.CONTINUE_WITH_ANSWER, steps=(invalid_step,)),
    )
    inv_rec = invalid.history.entries[-1].record
    inv_state = dataclasses.replace(
        invalid, instructions={inv_rec.id: RecordedInstruction(feedback=feedback)}
    )
    c10 = expect(decide(inv_state), "C10", RunStage, mode=StageMode.RETRY)
    assert c10.feedback == dataclasses.replace(feedback, schema_errors_step_id=uid(88))
    owner_retry = answered(
        "retry_stage",
        last=(e("prepare"), e("execute", K.RESULT_INVALID, mode=StageMode.CONTINUE_WITH_ANSWER)),
    )
    own_rec = owner_retry.history.entries[-1].record
    own_state = dataclasses.replace(
        owner_retry, instructions={own_rec.id: RecordedInstruction(feedback=feedback)}
    )
    j2 = expect(decide(own_state), "J2", RunStage, mode=StageMode.RETRY)
    assert j2.feedback == feedback
