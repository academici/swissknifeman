"""Supervisor authority is independent of silence and monitor liveness."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from skm.modules.execution.domain.recovery import RecoveryRecord, RecoveryStep, breaker_open, plan_recovery

NOW = datetime(2026, 11, 17, tzinfo=UTC)


def record(**changes: Any) -> RecoveryRecord:
    ident: Any = UUID(int=1)
    return replace(
        RecoveryRecord(ident, ident, ident, ident, ident, None, "hung", (), None, "retried", (), NOW),
        **changes,
    )


@pytest.mark.parametrize(("mode", "length"), [("notify", 3), ("stop_only", 6), ("resume", 7)])
def test_ordered_recovery_modes(mode, length):
    assert (
        plan_recovery({"deadline_expired": True, "identity_verified": True}, {"recover": mode})
        == tuple(RecoveryStep)[:length]
    )


@pytest.mark.parametrize(
    "facts",
    [
        {},
        {"cpu_active": False},
        {"repeated_command_count": 500},
        {"monitor_alive": True},
        {"input_stale": True},
        {"lease_expired": True},
    ],
)
def test_suspicion_does_not_authorize_cancel(facts):
    assert len(plan_recovery(facts, {"recover": "resume"})) == 3


def test_unknown_identity_can_reconcile_but_cannot_signal():
    steps = plan_recovery({"deadline_expired": True}, {"recover": "resume"})
    assert RecoveryStep.RECONCILE in steps
    assert RecoveryStep.KILL_GROUP not in steps
    assert RecoveryStep.COOPERATIVE_CANCEL not in steps


def test_legitimate_wait_finishes_before_snapshot():
    assert plan_recovery({"legitimate_wait": True}, {}) == (RecoveryStep.VERIFY_LEGIT,)


def test_breaker_strict_lower_window_boundary_and_outcomes():
    old = record(at=NOW - timedelta(seconds=3600))
    assert not breaker_open([old, record(outcome="not_needed"), record(outcome="escalated")], {}, NOW)
    assert not breaker_open([record()], {}, NOW)
    assert breaker_open([record(), record(outcome="new_attempt")], {}, NOW)
    assert not breaker_open([record(at=NOW + timedelta(seconds=1))], {"max_recoveries": 1}, NOW)
    assert breaker_open([], {"max_recoveries": 0}, NOW)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("authority_digest", "sha256:" + "b" * 64),
        ("environment_id", UUID(int=999)),
        ("attempt_id", UUID(int=999)),
        ("runtime_id", "other"),
        ("instruction_digest", "sha256:" + "b" * 64),
    ],
)
def test_advisor_resume_rechecks_binding(field, value):
    from skm.modules.execution.domain.session import Fresh, decide_session
    from unit.execution.domain.test_session import facts, fingerprint

    assert isinstance(decide_session(fingerprint(**{field: value}), facts()), Fresh)


def test_session_lost_requires_proven_pre_turn_and_single_fallback():
    from skm.modules.execution.domain.recovery import safe_session_lost
    from skm.modules.execution.domain.session import Fresh
    from unit.execution.domain.test_session import facts, fingerprint

    arguments = {"before_turn": True, "fallback_used": False, "external_effect_unknown": False}
    assert safe_session_lost(fingerprint(), facts(), **arguments) == Fresh("SESSION_LOST", True)
    for field, value in (("before_turn", False), ("fallback_used", True), ("external_effect_unknown", True)):
        assert safe_session_lost(fingerprint(), facts(), **{**arguments, field: value}) is None
    assert safe_session_lost(fingerprint(authority_digest="sha256:" + "b" * 64), facts(), **arguments) is None


@pytest.mark.parametrize(
    "row", ["SE0", "SE1", "SE2", "SE3", "SE4", "SE5", "SE6", "SE7", "SE8", "SE8r", "SE9", "SE10"]
)
def test_advisor_uses_complete_safe_resume_table(row):
    from skm.modules.execution.domain.session import Fresh, Resume, RouteRef, decide_session
    from skm.modules.execution.domain.step import RoleId, StepState
    from skm.modules.execution.domain.workflow.stage_inputs import StageMode
    from unit.execution.domain.test_session import DENIED, facts, fingerprint, make_step

    nxt = fingerprint(role=RoleId.ADVISOR)
    previous = make_step(role=RoleId.ADVISOR, session_fingerprint=nxt)
    inputs = facts(previous=previous)
    if row == "SE0":
        inputs = replace(inputs, admission_allows_resume=DENIED)
    elif row == "SE1":
        inputs = replace(inputs, previous=None)
    elif row == "SE2":
        nxt = replace(nxt, authority_digest="sha256:" + "b" * 64)
    elif row == "SE3":
        nxt = replace(nxt, environment_id=UUID(int=999))
    elif row == "SE4":
        nxt = replace(nxt, route=RouteRef("other", "m2", None))
    elif row == "SE5":
        inputs = replace(inputs, runtime_supports_resume=False)
    elif row == "SE6":
        nxt = replace(nxt, instruction_digest="sha256:" + "c" * 64)
    elif row == "SE7":
        inputs = replace(
            inputs,
            previous=replace(previous, state=StepState.FAILED, result=None, error_code="RUNTIME_ERROR"),
        )
    elif row == "SE8":
        inputs = replace(inputs, previous_context_tokens=120001)
    elif row == "SE8r":
        inputs = replace(
            inputs,
            stage_mode=StageMode.RETRY,
            retry_of_previous_stage=True,
            previous=replace(previous, state=StepState.FAILED, result=None, error_code="RESULT_INVALID"),
        )
    elif row == "SE10":
        inputs = replace(inputs, stage_mode=StageMode.NORMAL)
    decision = decide_session(nxt, inputs)
    assert isinstance(decision, Resume if row in {"SE8r", "SE9"} else Fresh)


def test_required_resume_refuses_session_lost():
    from skm.kernel.errors import SkmError
    from skm.modules.execution.domain.recovery import safe_session_lost
    from unit.execution.domain.test_session import REQUIRED, facts, fingerprint

    with pytest.raises(SkmError) as caught:
        safe_session_lost(
            fingerprint(),
            facts(admission_allows_resume=REQUIRED),
            before_turn=True,
            fallback_used=False,
            external_effect_unknown=False,
        )
    assert caught.value.code.value == "ADMISSION_REFUSED"
