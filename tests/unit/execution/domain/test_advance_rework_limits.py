"""Bounded semantic loops of advance: check, review and rework limits (execution §5.1).

A loop driver feeds the engine its own decisions: every ``Rework`` becomes a new execute stage, a new
check or review round and a counter step on the task, exactly as ``apply_action`` would record them. The
counters are the only limit: a repeated finding key, an unchanged input digest or a different model changes
the diagnostics of the cause, never the number of rounds.
"""

from __future__ import annotations

import dataclasses
from typing import Any, cast

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from skm.modules.execution.domain.attempt import AttemptState
from skm.modules.execution.domain.blocking_reason import BlockingCode
from skm.modules.execution.domain.check_execution import CheckKind, CheckState
from skm.modules.execution.domain.finding import FindingState, Severity
from skm.modules.execution.domain.review import ReviewClearance, Verdict
from skm.modules.execution.domain.step import StepState
from skm.modules.execution.domain.task import TaskKind, TaskStatus
from skm.modules.execution.domain.workflow.actions import (
    Accept,
    CreateFollowups,
    Escalate,
    Fail,
    NewAttempt,
    Noop,
    Rework,
    RunStage,
    WaitFor,
)
from skm.modules.execution.domain.workflow.engine import ActionDecision, TaskState
from skm.modules.execution.domain.workflow.stage_inputs import FeedbackRefs, StageMode
from unit.execution.domain.test_acceptance import (
    CHECK_MANUAL,
    OUT,
    OUT_A,
    REVIEW_1,
    make_attempt,
    make_check,
    make_finding,
    make_output,
    make_review,
)
from unit.execution.domain.test_advance_table import (
    DIGEST,
    K,
    decide,
    e,
    expect,
    failed_check,
    make_state,
    passed_checks,
    reasons,
    ref_kinds,
)
from unit.execution.domain.test_session import make_step, uid

REVIEW_2 = uid(601)
MODELS = ("model-a", "model-b", "model-c")


def digest(n: int) -> str:
    return "sha256:" + f"{n:064x}"


def executor_step(n: int, model: str) -> Any:
    return make_step(id=uid(300 + n), seq=n + 1, model=model, state=StepState.SUCCEEDED)


# ------------------------------------------------------------------------------------ the check loop


def check_loop(
    policy: dict[str, Any],
    *,
    same_input: bool = True,
    rotate_models: bool = False,
    start_rounds: int = 0,
    gate: bool = False,
    limit: int = 30,
) -> list[ActionDecision]:
    """Feed every ``Rework`` back as a rework round whose checks fail the same way."""
    entries = [e("prepare"), e("execute", steps=(executor_step(0, MODELS[0]),))]
    entries.append(e("checks", K.CHECKS_FAILED, digest=DIGEST))
    rounds = start_rounds
    decisions: list[ActionDecision] = []
    for step in range(limit):
        state = make_state(
            *entries,
            status=TaskStatus.CHECKING,
            task={"check_fix_rounds": rounds},
            checks=(failed_check(),),
        )
        decision = decide(state, policy=policy)
        decisions.append(decision)
        if not isinstance(decision.action, Rework):
            return decisions
        rounds += 1
        model = MODELS[(step + 1) % len(MODELS)] if rotate_models else MODELS[0]
        marker = DIGEST if same_input else digest(step + 2)
        entries.append(
            e("execute", mode=StageMode.REWORK, round_no=rounds + 1, steps=(executor_step(step + 1, model),))
        )
        entries.append(e("checks", K.CHECKS_FAILED, round_no=rounds + 1, digest=marker))
    raise AssertionError("the check loop did not stop")


@pytest.mark.parametrize("limit", [0, 1, 2, 3])
def test_failed_checks_rework_exactly_the_declared_number_of_rounds(limit: int) -> None:
    decisions = check_loop({"rework_max_rounds": limit})
    rules = [d.cause["advance_rule"] for d in decisions]
    assert rules == ["D6"] * limit + ["D7"]
    assert [type(d.action) for d in decisions][:limit] == [Rework] * limit


def test_the_default_limit_is_two_rounds_then_an_advisor_then_the_owner() -> None:
    decisions = check_loop({})
    assert [d.cause["advance_rule"] for d in decisions] == ["D6", "D6", "D7"]
    last = check_loop({"advisor_enabled": False})[-1]
    action = expect(last, "D8", Escalate, code="REWORK_LIMIT_REACHED")
    assert action.payload["check_fix_rounds"] == 2
    assert action.blocking_code is BlockingCode.WAITING_OWNER


def test_a_different_model_in_each_round_never_resets_the_limit() -> None:
    same = [d.cause["advance_rule"] for d in check_loop({}, rotate_models=False)]
    rotated = [d.cause["advance_rule"] for d in check_loop({}, rotate_models=True)]
    assert rotated == same == ["D6", "D6", "D7"]


def test_a_repeated_input_digest_is_a_diagnostic_and_not_a_new_stop() -> None:
    plain = check_loop({}, same_input=False)
    repeated = check_loop({}, same_input=True)
    assert [d.cause["advance_rule"] for d in repeated] == [d.cause["advance_rule"] for d in plain]
    assert [type(d.action) for d in repeated] == [type(d.action) for d in plain]
    assert "INPUT_REPEATED" not in reasons(plain[-1])
    assert "INPUT_REPEATED" in reasons(repeated[-1])
    assert "INPUT_REPEATED" not in reasons(repeated[0])


def test_the_exhausted_check_loop_ends_with_one_escalation_that_names_its_cause() -> None:
    decisions = check_loop({"advisor_enabled": False}, same_input=True)
    final = decisions[-1]
    action = expect(final, "D8", Escalate, code="REWORK_LIMIT_REACHED")
    assert action.payload["options"] == ["accept_deviation", "rework", "fail"]
    assert {"REWORK_LIMIT_REACHED", "INPUT_REPEATED"} <= set(reasons(final))
    assert ref_kinds(final) >= {"check", "output", "stage"}
    assert len(decisions) == 3


def test_the_advisor_grants_no_more_rounds_than_the_policy_allows() -> None:
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks", K.CHECKS_FAILED, round_no=3),
        checks=(failed_check(),),
        task={"check_fix_rounds": 2},
        advisor_rounds_used=1,
    )
    expect(decide(state), "D7", RunStage, stage_id="advise")
    spent = dataclasses.replace(state, advisor_rounds_used=2)
    expect(decide(spent), "D8", Escalate, code="REWORK_LIMIT_REACHED")


def test_a_limit_lowered_below_the_reached_counter_escalates_at_the_next_advance() -> None:
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks", K.CHECKS_FAILED),
        checks=(failed_check(),),
        task={"check_fix_rounds": 1},
    )
    expect(decide(state, policy={"rework_max_rounds": 2}), "D6", Rework)
    lowered = decide(state, policy={"rework_max_rounds": 1, "advisor_enabled": False})
    expect(lowered, "D8", Escalate, code="REWORK_LIMIT_REACHED")
    # past counters are kept, not subtracted
    assert state.task.check_fix_rounds == 1


def test_a_gate_follows_up_failed_checks_until_its_review_rounds_are_spent() -> None:
    def gate_state(rounds: int) -> TaskState:
        return make_state(
            e("gate_prepare"),
            e("gate_checks", K.CHECKS_FAILED),
            kind=TaskKind.PHASE_GATE,
            checks=(failed_check(),),
            task={"review_rounds": rounds},
        )

    assert isinstance(decide(gate_state(1)).action, CreateFollowups)
    exhausted = decide(gate_state(2), policy={"advisor_enabled": False})
    expect(exhausted, "D8", Escalate, code="REWORK_LIMIT_REACHED")


def test_a_manual_check_waits_without_spending_a_rework_round() -> None:
    manual = make_check(CHECK_MANUAL, kind=CheckKind.MANUAL, state=CheckState.MANUAL_PENDING)
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks", K.MANUAL_PENDING),
        checks=(manual,),
        task={"check_fix_rounds": 2},
    )
    for _ in range(3):
        decision = decide(state)
        assert isinstance(decision.action, WaitFor)
        assert decision.cause["advance_rule"] == "D5"
    assert state.task.check_fix_rounds == 2


# ----------------------------------------------------------------------------------- the review loop


def repeated(n: int, severity: Severity, state: FindingState, review_id: Any) -> Any:
    """The same logical finding seen again in a later review round."""
    found = make_finding(n, severity, state, review_id=review_id)
    return dataclasses.replace(found, id=uid(5000 + n), review_id=review_id, first_seen_review_id=REVIEW_1)


def review_loop(
    policy: dict[str, Any],
    *,
    severity: Severity = Severity.MAJOR,
    wide_correction: bool = False,
    limit: int = 20,
) -> list[ActionDecision]:
    """Red review -> triage confirms the same finding in every round -> rework -> review again."""
    entries = [
        e("prepare"),
        e("execute", steps=(executor_step(0, MODELS[0]),)),
        e("checks"),
        e("review", K.VERDICT_RED),
        e("triage"),
    ]
    rounds = 1
    review_ids = [REVIEW_1, REVIEW_2, uid(602), uid(603), uid(604)]
    decisions: list[ActionDecision] = []
    output = make_output()
    for step in range(limit):
        reviews = tuple(
            make_review(review_ids[i], round_no=i + 1, verdict_=Verdict.RED, output_id=output.id)
            for i in range(rounds)
        )
        found = repeated(1, severity, FindingState.CONFIRMED, review_ids[rounds - 1])
        state = make_state(
            *entries,
            status=TaskStatus.REVIEWING,
            task={"review_rounds": rounds},
            findings=(found,),
            reviews=reviews,
            output=output,
            checks=passed_checks(),
        )
        decision = decide(state, policy=policy)
        decisions.append(decision)
        action = decision.action
        if isinstance(action, Rework):
            entries += [
                e(
                    "execute",
                    mode=StageMode.REWORK,
                    round_no=rounds + 1,
                    steps=(executor_step(step + 1, MODELS[(step + 1) % 3]),),
                ),
                e("checks", round_no=rounds + 1),
            ]
        elif isinstance(action, RunStage) and action.mode is StageMode.FINAL_CORRECTION:
            entries += [
                e("execute", mode=StageMode.FINAL_CORRECTION, round_no=rounds + 1),
                e("checks", round_no=rounds + 1),
            ]
            output = make_output(outside=("src/app/other.py",) if wide_correction else ())
            output = dataclasses.replace(output, id=OUT_A)
            follow = make_state(
                *entries,
                status=TaskStatus.CHECKING,
                task={"review_rounds": rounds},
                findings=(found,),
                reviews=reviews,
                output=output,
                checks=passed_checks(),
            )
            decisions.append(decide(follow, policy=policy))
            nxt = decisions[-1].action
            if isinstance(nxt, RunStage) and nxt.stage_id == "review":
                entries += [e("review", K.VERDICT_RED, round_no=rounds + 1), e("triage", round_no=rounds + 1)]
                rounds += 1
                continue
            return decisions
        else:
            return decisions
        entries += [e("review", K.VERDICT_RED, round_no=rounds + 1), e("triage", round_no=rounds + 1)]
        rounds += 1
    raise AssertionError("the review loop did not stop")


def rules_of(decisions: list[ActionDecision]) -> list[str | None]:
    return [cast("str | None", d.cause["advance_rule"]) for d in decisions]


def test_repeated_findings_rework_up_to_the_round_limit_then_one_final_correction() -> None:
    decisions = review_loop({})
    assert rules_of(decisions) == ["H1", "H2", "H7"]
    assert isinstance(decisions[-1].action, Accept)
    assert decisions[-1].action.clearance is ReviewClearance.FINDINGS_ONLY
    assert "FINDING_REPEATED" not in reasons(decisions[0])  # first sight of the finding
    assert "FINDING_REPEATED" in reasons(decisions[1])  # the same key confirmed again in round 2


def test_a_repeated_finding_is_a_diagnostic_and_a_new_finding_follows_the_same_rules() -> None:
    plain = review_loop({})
    assert rules_of(plain) == ["H1", "H2", "H7"]
    fresh = make_state(
        e("prepare"),
        e("execute"),
        e("checks"),
        e("review", K.VERDICT_RED),
        e("triage"),
        status=TaskStatus.REVIEWING,
        task={"review_rounds": 1},
        findings=(make_finding(1, Severity.MAJOR, FindingState.CONFIRMED),),
        reviews=(make_review(verdict_=Verdict.RED),),
    )
    decision = decide(fresh)
    expect(decision, "H1", Rework)
    assert "FINDING_REPEATED" not in reasons(decision)


def test_a_wide_final_correction_ends_in_an_owner_decision_with_the_review_debt() -> None:
    decisions = review_loop({}, wide_correction=True)
    assert rules_of(decisions) == ["H1", "H2", "H8"]
    assert isinstance(decisions[-1].action, Escalate)
    assert decisions[-1].action.payload["review_debt"]["count"] == 1  # type: ignore[index,union-attr]


def test_a_confirmed_blocker_stops_at_the_round_limit_without_a_final_correction() -> None:
    decisions = review_loop({}, severity=Severity.BLOCKER)
    assert rules_of(decisions) == ["H1", "H3"]
    expect(decisions[-1], "H3", Escalate, code="REWORK_LIMIT_REACHED")
    assert "CONFIRMED_BLOCKER" in reasons(decisions[-1])


def test_without_a_final_correction_the_loop_still_ends_at_the_round_limit() -> None:
    decisions = review_loop({"review_final_correction": False})
    assert rules_of(decisions) == ["H1", "H3"]
    assert "FINAL_CORRECTION_UNAVAILABLE" in reasons(decisions[-1])


def test_the_final_correction_is_used_once_even_when_it_is_reviewed_again() -> None:
    decisions = review_loop({"review_accept_findings_only": False})
    assert rules_of(decisions) == ["H1", "H2", "D1", "H3"]
    assert "FINDINGS_ONLY_DISABLED" in reasons(decisions[2])
    assert "FINAL_CORRECTION_UNAVAILABLE" in reasons(decisions[-1])
    assert len([d for d in decisions if d.cause["advance_rule"] == "H2"]) == 1


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_review_rework_stops_at_the_declared_review_limit(limit: int) -> None:
    decisions = review_loop({"review_max_rounds": limit})
    reworks = [d for d in decisions if isinstance(d.action, Rework)]
    assert len(reworks) == limit - 1
    assert len(decisions) <= limit + 3


def test_rework_carries_the_exact_verified_inputs_and_leaves_the_state_untouched() -> None:
    check = failed_check()
    state = make_state(
        e("prepare"),
        e("execute"),
        e("checks", K.CHECKS_FAILED),
        checks=(check,),
        task={"check_fix_rounds": 0},
        budget={
            "accounts": [{"scope": "run", "dimension": "tokens", "limit": 1000, "spent": 10, "reserved": 0}]
        },
    )
    before = (state.output, state.budget, state.task, state.checks)
    decision = decide(state)
    action = expect(decision, "D6", Rework, reason="checks_failed")
    assert action.feedback == FeedbackRefs()
    refs = {(r["kind"], r["id"]) for r in decision.cause["refs"]}  # type: ignore[index]
    assert ("output", str(OUT)) in refs
    assert ("check", str(check.id)) in refs
    assert ("stage", str(uid(7002))) in refs
    assert (state.output, state.budget, state.task, state.checks) == before


def test_the_model_of_the_next_round_is_not_an_input_of_the_decision() -> None:
    def state_with(model: str) -> TaskState:
        step = executor_step(0, model)
        return make_state(
            e("prepare"), e("execute", steps=(step,)), e("checks", K.CHECKS_FAILED), checks=(failed_check(),)
        )

    assert decide(state_with("model-a")) == decide(state_with("model-b"))


# ----------------------------------------------------------------------------- attempts and overlays


def lost_state(count: int) -> TaskState:
    return make_state(
        e("prepare"), attempt=make_attempt(AttemptState.OWNERSHIP_LOST), task={"attempt_count": count}
    )


def test_the_attempts_limit_of_the_call_decides_not_the_policy_copied_into_the_state() -> None:
    state = dataclasses.replace(lost_state(2), effective_policy={"attempts_max": 3})
    expect(decide(state, policy={"attempts_max": 3}), "G4", NewAttempt)
    expect(decide(state, policy={"attempts_max": 2}), "G5", Fail, code="LEASE_LOST")
    expect(decide(state, policy={"attempts_max": 1}), "G5", Fail)


@pytest.mark.parametrize(
    ("count", "limit", "rule"), [(0, 1, "G4"), (1, 1, "G5"), (2, 3, "G4"), (3, 3, "G5"), (5, 3, "G5")]
)
def test_attempt_limit_vectors(count: int, limit: int, rule: str) -> None:
    assert decide(lost_state(count), policy={"attempts_max": limit}).cause["advance_rule"] == rule


def test_a_new_attempt_answer_of_the_owner_needs_an_attempt_left_or_a_raised_limit() -> None:
    from unit.execution.domain.test_advance_table import answered

    last = (e("prepare"), e("execute", K.RESULT_INVALID))
    state = answered("new_attempt", last=last)
    full = dataclasses.replace(state, task=dataclasses.replace(state.task, attempt_count=2))
    expect(decide(full, policy={"attempts_max": 2}), "J3", Escalate, code="ATTEMPTS_EXHAUSTED")
    expect(decide(full, policy={"attempts_max": 3}), "J3", NewAttempt)


# ------------------------------------------------------------------------------------- properties


@settings(max_examples=60, deadline=None)
@given(
    limit=st.integers(0, 4),
    same_input=st.booleans(),
    rotate=st.booleans(),
    start=st.integers(0, 5),
)
def test_the_check_loop_always_stops_within_the_declared_limit(
    limit: int, same_input: bool, rotate: bool, start: int
) -> None:
    decisions = check_loop(
        {"rework_max_rounds": limit}, same_input=same_input, rotate_models=rotate, start_rounds=start
    )
    reworks = [d for d in decisions if isinstance(d.action, Rework)]
    assert len(reworks) == max(0, limit - start)
    assert not isinstance(decisions[-1].action, Rework)
    assert isinstance(decisions[-1].action, RunStage | Escalate)
    assert len(decisions) <= limit + 1


@settings(max_examples=40, deadline=None)
@given(limit=st.integers(1, 4), final=st.booleans(), only_findings=st.booleans(), blocker=st.booleans())
def test_the_review_loop_is_finite_and_ends_in_an_accept_or_an_owner_decision(
    limit: int, final: bool, only_findings: bool, blocker: bool
) -> None:
    policy = {
        "review_max_rounds": limit,
        "review_final_correction": final,
        "review_accept_findings_only": only_findings,
    }
    decisions = review_loop(policy, severity=Severity.BLOCKER if blocker else Severity.MAJOR)
    assert len(decisions) <= limit + 4
    assert isinstance(decisions[-1].action, Accept | Escalate)
    assert len([d for d in decisions if d.cause["advance_rule"] == "H2"]) <= 1
    assert not any(isinstance(d.action, Noop) for d in decisions)


def test_every_decision_of_both_loops_is_json_ready_evidence() -> None:
    import json

    for decision in [*check_loop({}), *review_loop({})]:
        json.dumps(decision.cause)
        assert decision.cause["trigger_kind"] in {"stage_outcome", "check_failed", "review_findings"}


def test_alternating_check_retry_outcomes_in_same_round_do_not_bypass_retry_limits() -> None:
    err_check = make_check(uid(500), state=CheckState.ERROR)
    mutated_then_error = make_state(
        e("prepare"),
        e("execute"),
        e("checks", K.TREE_CHANGED),
        e("checks", K.CHECKS_ERROR, mode=StageMode.RETRY),
        e("checks", K.TREE_CHANGED, mode=StageMode.RETRY),
        checks=(err_check,),
    )
    expect(decide(mutated_then_error), "D13", Escalate, code="CHECKS_MUTATED")
    error_then_mutated = make_state(
        e("prepare"),
        e("execute"),
        e("checks", K.CHECKS_ERROR),
        e("checks", K.TREE_CHANGED, mode=StageMode.RETRY),
        e("checks", K.CHECKS_ERROR, mode=StageMode.RETRY),
        checks=(err_check,),
    )
    expect(decide(error_then_mutated), "D10", Escalate, code="CHECKS_ERROR")
