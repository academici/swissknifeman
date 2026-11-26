"""Resume or fresh session: every row SE0-SE10 of execution §5.16."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import pytest
from hypothesis import given
from hypothesis import strategies as st

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.session import (
    SESSION_FRESH_REASONS,
    Fresh,
    Resume,
    RouteRef,
    SessionFacts,
    SessionFingerprint,
    decide_session,
    session_lost,
)
from skm.modules.execution.domain.step import AttemptStep, RoleId, StepPurpose, StepState
from skm.modules.execution.domain.workflow.stage_inputs import StageMode
from skm.modules.runtimes.public import ResumeAllowance

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
DIGEST = "sha256:" + "1" * 64
OUT_1, OUT_2, OUT_3 = (UUID(int=900 + n) for n in range(3))
ROUTE = RouteRef("claude_code", "m1", "high")
ALLOWED = ResumeAllowance(allowed=True, required=False, session_ref="sess-1", reason="allowed")
REQUIRED = ResumeAllowance(allowed=True, required=True, session_ref="sess-1", reason="allowed")
DENIED = ResumeAllowance(allowed=False, required=False, session_ref=None, reason="resume_disabled")
DENIED_REQUIRED = ResumeAllowance(allowed=False, required=True, session_ref=None, reason="resume_disabled")


def uid(n: int) -> Any:
    return UUID(int=n)


def fingerprint(**changes: Any) -> SessionFingerprint:
    values: dict[str, Any] = {
        "runtime_id": "claude_code",
        "project_id": uid(3),
        "environment_id": uid(6),
        "role": RoleId.EXECUTOR,
        "attempt_id": uid(200),
        "instruction_digest": DIGEST,
        "authority_digest": "sha256:" + "a" * 64,
        "route": ROUTE,
        "last_validated_output_id": OUT_1,
    }
    values.update(changes)
    return SessionFingerprint(**values)


def make_step(**changes: Any) -> AttemptStep:
    state = changes.get("state", StepState.SUCCEEDED)
    values: dict[str, Any] = {
        "id": uid(80), "attempt_id": uid(200), "stage_record_id": uid(900), "parent_step_id": None, "seq": 1,
        "role": RoleId.EXECUTOR, "purpose": StepPurpose.PRIMARY, "runtime_id": "claude_code", "model": "m1",
        "effort": "high", "operation": "new_implementation", "admission": {}, "route_source": "plan_route",
        "route_reason": "ROUTE_DEFAULT", "context_manifest_id": uid(81), "session_mode": "new",
        "session_ref": "sess-1", "session_fingerprint": fingerprint(), "session_fingerprint_digest": DIGEST,
        "fresh_reason": None,
        "state": state, "result": {} if state is StepState.SUCCEEDED else None,
        "raw_result_file_version_id": None, "repairs": (),
        "schema_errors": (), "usage": None, "usage_so_far": None, "process_identity": None,
        "activity": None, "route_snapshot": None,
        "runtime_observation": None, "reuse_key": None, "transcript_file_version_id": None,
        "last_progress_at": None, "error_code": None, "started_at": NOW,
        "finished_at": None if state is StepState.STARTED else NOW,
    }  # fmt: skip
    values.update(changes)
    return AttemptStep(**values)


def facts(**changes: Any) -> SessionFacts:
    values: dict[str, Any] = {
        "previous": make_step(),
        "runtime_supports_resume": True,
        "previous_context_tokens": 1000,
        "max_resume_context_tokens": 120000,
        "stage_mode": StageMode.REWORK,
        "admission_allows_resume": ALLOWED,
        "retry_of_previous_stage": False,
        "previous_error_code": None,
    }
    values.update(changes)
    return SessionFacts(**values)


def reason(result: Resume | Fresh) -> str | None:
    assert isinstance(result, Fresh)
    return result.reason


# --- one test per row of the table -----------------------------------------------------------------


def test_se0_admission_forbids_resume_gives_fresh_with_handoff_of_a_previous_step() -> None:
    result = decide_session(fingerprint(), facts(admission_allows_resume=DENIED))
    assert result == Fresh("ADMISSION_NO_RESUME", handoff=True)


def test_se0_without_a_previous_step_has_nothing_to_hand_off() -> None:
    result = decide_session(fingerprint(), facts(previous=None, admission_allows_resume=DENIED))
    assert result == Fresh("ADMISSION_NO_RESUME", handoff=False)


def test_se0_comes_before_every_other_row_even_a_changed_authority() -> None:
    other = fingerprint(authority_digest="sha256:" + "b" * 64)
    assert reason(decide_session(other, facts(admission_allows_resume=DENIED))) == "ADMISSION_NO_RESUME"


def test_se0_with_a_required_resume_refuses_the_step() -> None:
    with pytest.raises(SkmError) as raised:
        decide_session(fingerprint(), facts(admission_allows_resume=DENIED_REQUIRED))
    assert raised.value.code is ErrorCode.ADMISSION_REFUSED
    assert raised.value.details["reason"] == "resume_required_unavailable"


def test_se1_no_previous_step() -> None:
    assert decide_session(fingerprint(), facts(previous=None)) == Fresh("NO_PREVIOUS_SESSION", handoff=False)


def test_se1_previous_step_without_a_session_ref() -> None:
    result = decide_session(fingerprint(), facts(previous=make_step(session_ref=None)))
    assert result == Fresh("NO_PREVIOUS_SESSION", handoff=False)


def test_se2_authority_change_is_fresh_even_when_everything_else_matches() -> None:
    other = fingerprint(authority_digest="sha256:" + "b" * 64)
    assert decide_session(other, facts()) == Fresh("AUTHORITY_CHANGED", handoff=True)


@pytest.mark.parametrize(
    "change",
    [
        {"environment_id": uid(7)},
        {"project_id": uid(4)},
        {"attempt_id": uid(201)},
        {"role": RoleId.REVIEWER},
    ],
)
def test_se3_environment_project_attempt_or_role_change(change: dict[str, Any]) -> None:
    assert decide_session(fingerprint(**change), facts()) == Fresh("ENVIRONMENT_CHANGED", handoff=True)


@pytest.mark.parametrize(
    "change",
    [
        {"runtime_id": "codex"},
        {"route": RouteRef("claude_code", "m2", "high")},
        {"route": RouteRef("claude_code", "m1", "low")},
    ],
)
def test_se4_runtime_or_route_change(change: dict[str, Any]) -> None:
    assert decide_session(fingerprint(**change), facts()) == Fresh("ROUTE_CHANGED", handoff=True)


def test_se5_runtime_cannot_resume() -> None:
    result = decide_session(fingerprint(), facts(runtime_supports_resume=False))
    assert result == Fresh("RESUME_UNSUPPORTED", handoff=True)


def test_se6_instruction_digest_change_is_a_scope_change() -> None:
    other = fingerprint(instruction_digest="sha256:" + "2" * 64)
    assert decide_session(other, facts()) == Fresh("SCOPE_CHANGED", handoff=True)


@pytest.mark.parametrize("code", ["RUNTIME_TRANSPORT", "REPAIR_SEMANTIC_DRIFT", None])
def test_se7_a_failed_step_contaminates_the_session(code: str | None) -> None:
    previous = make_step(state=StepState.FAILED, error_code=code)
    result = decide_session(fingerprint(), facts(previous=previous, previous_error_code=code))
    assert result == Fresh("SESSION_CONTAMINATED", handoff=True)


def test_se7_a_step_cancelled_by_recovery_contaminates_the_session() -> None:
    previous = make_step(state=StepState.CANCELLED)
    assert reason(decide_session(fingerprint(), facts(previous=previous))) == "SESSION_CONTAMINATED"


def test_se8_a_bloated_context() -> None:
    result = decide_session(fingerprint(), facts(previous_context_tokens=120001))
    assert result == Fresh("CONTEXT_BLOATED", handoff=True)


def test_se8_the_limit_itself_still_resumes() -> None:
    assert decide_session(fingerprint(), facts(previous_context_tokens=120000)) == Resume("sess-1")


def test_se8r_a_result_retry_resumes_the_same_session() -> None:
    previous = make_step(state=StepState.FAILED, error_code="RESULT_INVALID")
    result = decide_session(
        fingerprint(last_validated_output_id=None),
        facts(
            previous=previous,
            stage_mode=StageMode.RETRY,
            retry_of_previous_stage=True,
            previous_error_code="RESULT_INVALID",
        ),
    )
    assert result == Resume("sess-1")


def test_se8r_needs_the_retry_of_that_very_stage() -> None:
    previous = make_step(state=StepState.FAILED, error_code="RESULT_INVALID")
    result = decide_session(
        fingerprint(last_validated_output_id=None),
        facts(
            previous=previous,
            stage_mode=StageMode.RETRY,
            retry_of_previous_stage=False,
            previous_error_code="RESULT_INVALID",
        ),
    )
    assert reason(result) == "NOT_A_CONTINUATION"


def test_se8r_never_overrides_a_denied_allowance() -> None:
    previous = make_step(state=StepState.FAILED, error_code="RESULT_INVALID")
    result = decide_session(
        fingerprint(),
        facts(
            previous=previous,
            stage_mode=StageMode.RETRY,
            retry_of_previous_stage=True,
            previous_error_code="RESULT_INVALID",
            admission_allows_resume=DENIED,
        ),
    )
    assert reason(result) == "ADMISSION_NO_RESUME"


@pytest.mark.parametrize(
    "mode",
    [
        StageMode.REWORK,
        StageMode.FINAL_CORRECTION,
        StageMode.CONTINUE_WITH_ANSWER,
        StageMode.RETRY,
        StageMode.RESUME_INTERRUPTED,
    ],
)
def test_se9_a_continuation_of_the_current_output_resumes(mode: StageMode) -> None:
    assert decide_session(fingerprint(), facts(stage_mode=mode)) == Resume("sess-1")


def test_se9_a_step_that_validated_an_earlier_output_resumes() -> None:
    result = decide_session(
        fingerprint(last_validated_output_id=OUT_2), facts(earlier_output_ids=frozenset({OUT_1}))
    )
    assert result == Resume("sess-1")


def test_se9_an_unrelated_output_is_not_a_continuation() -> None:
    result = decide_session(fingerprint(last_validated_output_id=OUT_3), facts())
    assert result == Fresh("NOT_A_CONTINUATION", handoff=True)


def test_se9_two_absent_validated_outputs_are_no_relationship() -> None:
    previous = make_step(session_fingerprint=fingerprint(last_validated_output_id=None))
    result = decide_session(
        fingerprint(last_validated_output_id=None),
        facts(previous=previous, stage_mode=StageMode.CONTINUE_WITH_ANSWER),
    )
    assert result == Fresh("NOT_A_CONTINUATION", handoff=True)


def test_se8r_needs_a_retry_of_the_stage_even_when_both_validated_outputs_are_absent() -> None:
    previous = make_step(
        state=StepState.FAILED,
        error_code="RESULT_INVALID",
        session_fingerprint=fingerprint(last_validated_output_id=None),
    )
    result = decide_session(
        fingerprint(last_validated_output_id=None),
        facts(
            previous=previous,
            stage_mode=StageMode.RETRY,
            retry_of_previous_stage=False,
            previous_error_code="RESULT_INVALID",
        ),
    )
    assert reason(result) == "NOT_A_CONTINUATION"


@pytest.mark.parametrize("mode", [StageMode.NORMAL, StageMode.RECONCILE, StageMode.RETRIAGE_WITH_ADVICE])
def test_se10_other_modes_are_not_a_continuation(mode: StageMode) -> None:
    assert decide_session(fingerprint(), facts(stage_mode=mode)) == Fresh("NOT_A_CONTINUATION", handoff=True)


# --- cross-row properties ------------------------------------------------------------------------------


def test_a_required_resume_makes_every_fresh_result_a_refusal() -> None:
    cases = [
        (fingerprint(), facts(previous=None, admission_allows_resume=REQUIRED)),
        (fingerprint(authority_digest="sha256:" + "b" * 64), facts(admission_allows_resume=REQUIRED)),
        (fingerprint(), facts(admission_allows_resume=REQUIRED, runtime_supports_resume=False)),
        (fingerprint(), facts(admission_allows_resume=REQUIRED, stage_mode=StageMode.NORMAL)),
    ]
    for nxt, case in cases:
        with pytest.raises(SkmError) as raised:
            decide_session(nxt, case)
        assert raised.value.code is ErrorCode.ADMISSION_REFUSED


def test_a_required_resume_that_continues_still_resumes() -> None:
    assert decide_session(fingerprint(), facts(admission_allows_resume=REQUIRED)) == Resume("sess-1")


def test_session_lost_is_a_fresh_start_with_a_handoff_while_the_authority_is_unchanged() -> None:
    assert session_lost(fingerprint(), make_step()) == Fresh("SESSION_LOST", handoff=True)


def test_session_lost_never_hides_an_authority_change() -> None:
    other = fingerprint(authority_digest="sha256:" + "b" * 64)
    assert session_lost(other, make_step()) == Fresh("AUTHORITY_CHANGED", handoff=True)


def test_live_control_starts_fresh_and_respects_a_required_resume() -> None:
    assert decide_session(fingerprint(), facts(), force_fresh=True) == Fresh(
        "OPERATOR_LIVE_CONTROL", handoff=True
    )
    with pytest.raises(SkmError) as raised:
        decide_session(fingerprint(), facts(admission_allows_resume=REQUIRED), force_fresh=True)
    assert raised.value.code is ErrorCode.ADMISSION_REFUSED


def test_every_fresh_reason_is_a_value_of_the_sql_check() -> None:
    reasons = {
        "ADMISSION_NO_RESUME",
        "NO_PREVIOUS_SESSION",
        "AUTHORITY_CHANGED",
        "OPERATOR_LIVE_CONTROL",
        "ENVIRONMENT_CHANGED",
        "ROUTE_CHANGED",
        "RESUME_UNSUPPORTED",
        "SCOPE_CHANGED",
        "SESSION_CONTAMINATED",
        "CONTEXT_BLOATED",
        "NOT_A_CONTINUATION",
        "SESSION_LOST",
    }
    assert reasons == SESSION_FRESH_REASONS


@given(
    mode=st.sampled_from(list(StageMode)),
    tokens=st.one_of(st.none(), st.integers(0, 200000)),
    supports=st.booleans(),
    authority_same=st.booleans(),
    retry_of=st.booleans(),
    error=st.sampled_from([None, "RESULT_INVALID", "RUNTIME_TRANSPORT"]),
    state=st.sampled_from([StepState.SUCCEEDED, StepState.FAILED, StepState.CANCELLED]),
)
def test_a_changed_authority_never_resumes_and_the_decision_is_deterministic(
    mode: StageMode,
    tokens: int | None,
    supports: bool,
    authority_same: bool,
    retry_of: bool,
    error: str | None,
    state: StepState,
) -> None:
    nxt = fingerprint(authority_digest="sha256:" + ("a" if authority_same else "c") * 64)
    previous = make_step(state=state, error_code=error if state is StepState.FAILED else None)
    given = facts(
        previous=previous,
        stage_mode=mode,
        previous_context_tokens=tokens,
        runtime_supports_resume=supports,
        retry_of_previous_stage=retry_of,
        previous_error_code=error,
    )
    first, second = decide_session(nxt, given), decide_session(nxt, dataclasses.replace(given))
    assert first == second
    if not authority_same:
        assert isinstance(first, Fresh)
        assert first.reason == "AUTHORITY_CHANGED"
