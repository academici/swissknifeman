"""The ordered stop table, campaign authority and paused-run classification."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.errors import SkmError
from skm.modules.execution.domain.autopilot import (
    OWNER_CODES,
    STOP_CODES,
    TRANSIENT_CODES,
    AutopilotFacts,
    AutopilotPolicy,
    AutopilotState,
    AutopilotStateKind,
    classify_outcome,
    effective_policy,
    evaluate_conditions,
    narrow_limits,
    start_session,
    stop_conditions,
)

NOW = datetime(2026, 11, 17, tzinfo=UTC)
POLICY = AutopilotPolicy(allowed=True, enabled=True)


@pytest.fixture
def state() -> Any:
    uid: Any = UUID(int=1)
    return AutopilotState(
        uid, uid, AutopilotStateKind.RUNNING, False, None, NOW, {}, {}, None, None, uid, NOW, 1
    )


@pytest.mark.parametrize(
    ("number", "change", "facts", "policy"),
    [
        (1, {}, {"has_work": False}, {}),
        (2, {"state": AutopilotStateKind.DRAINING}, {}, {}),
        (3, {}, {"stopped_by_command": True}, {}),
        (4, {"counters": {"runs_started": 20}}, {}, {}),
        (5, {"session_started_at": NOW - timedelta(seconds=43200)}, {}, {}),
        (6, {}, {}, {"allowed": False}),
        (7, {}, {}, {"enabled": False}),
        (8, {}, {"busy": True}, {}),
        (9, {}, {"not_ready": True}, {}),
        (10, {}, {"owner_needed": True}, {}),
        (11, {}, {"budget_exhausted": True}, {}),
        (12, {}, {"quota_exhausted": True}, {}),
        (13, {}, {"repeated_blocker": True}, {}),
        (14, {}, {"state_invalid": True}, {}),
        (15, {}, {"checkout_lost": True}, {}),
        (16, {}, {"no_improvement_rounds": 2}, {}),
        (17, {"counters": {"no_progress_runs": 2}}, {}, {}),
        (18, {"counters": {"auto_decisions": 10}}, {}, {}),
        (19, {}, {"recovery_open": True}, {}),
        (20, {}, {"run_stopped": True}, {}),
    ],
)
def test_every_stop_condition_and_owner_boundary(
    state: Any, number: int, change: Any, facts: Any, policy: Any
):
    rows = evaluate_conditions(
        replace(state, **change), replace(POLICY, **policy), NOW, AutopilotFacts(**facts)
    )
    assert [row.id for row in rows] == [f"AP{i}" for i in range(1, 21)]
    matched = [row for row in rows if row.met]
    assert matched[0].code == STOP_CODES[number - 1]
    assert matched[0].owner_required == (number == 6 or number >= 9)


def test_competing_conditions_keep_normative_order(state: Any):
    state = replace(
        state, counters={"runs_started": 99, "auto_decisions": 99}, session_started_at=NOW - timedelta(days=2)
    )
    assert stop_conditions(
        state,
        replace(POLICY, allowed=False, enabled=False),
        NOW,
        AutopilotFacts(owner_needed=True, state_invalid=True),
    ) == (
        "AUTOPILOT_MAX_RUNS",
        "AUTOPILOT_MAX_WALL",
        "AUTOPILOT_NOT_ALLOWED",
        "AUTOPILOT_DISABLED",
        "AUTOPILOT_OWNER_NEEDED",
        "AUTOPILOT_STATE_INVALID",
        "AUTOPILOT_DECISIONS_EXCEEDED",
    )


@pytest.mark.parametrize("kind", [AutopilotStateKind.PAUSED, AutopilotStateKind.STOPPED])
def test_continue_preserves_spent_session_and_only_narrows(state: Any, kind: Any):
    counters = {"runs_started": 4, "auto_decisions": 3, "last_blocker": {"task_key": "P1/U1", "code": "X"}}
    previous = replace(
        state,
        state=kind,
        counters=counters,
        session_started_at=NOW - timedelta(hours=3),
        session_limits={"max_runs": 5, "max_wall_seconds": 3600},
        stop_code="AUTOPILOT_MAX_WALL",
        stop_detail="deadline",
    )
    resumed, reset = start_session(previous, POLICY, NOW, limits={"max_runs": 100})
    assert not reset
    assert resumed.counters == counters
    assert resumed.session_started_at == previous.session_started_at
    assert resumed.stop_code is None
    assert resumed.stop_detail is None
    assert resumed.session_limits["max_runs"] == 5
    assert resumed.session_limits["max_wall_seconds"] == 3600
    assert stop_conditions(resumed, POLICY, NOW)[0] == "AUTOPILOT_MAX_WALL"
    fresh, reset = start_session(previous, POLICY, NOW, new_session=True, reason="New campaign")
    assert reset
    assert fresh.session_started_at == NOW
    assert fresh.counters["runs_started"] == 0
    assert fresh.counters["last_blocker"] is None


def test_new_session_and_emergency_guards(state: Any):
    state = replace(state, state=AutopilotStateKind.STOPPED, emergency=True, stop_code="AUTOPILOT_STOPPED")
    for changes, code in [
        ({}, "EMERGENCY_STOPPED"),
        ({"clear_emergency": True, "new_session": True}, "SCHEMA_INVALID"),
    ]:
        with pytest.raises(SkmError) as caught:
            start_session(state, POLICY, NOW, **changes)
        assert caught.value.code.value == code
    cleared, _ = start_session(state, POLICY, NOW, clear_emergency=True)
    assert not cleared.emergency
    with pytest.raises(SkmError, match="disabled"):
        start_session(state, replace(POLICY, allowed=False), NOW)


def test_config_and_invocation_limits_form_a_monotone_minimum():
    limits = narrow_limits({}, {"max_runs": 1000, "max_wall_seconds": 60}, POLICY)
    assert limits == {"max_runs": 20, "max_wall_seconds": 60, "max_auto_decisions": 10}
    limits = narrow_limits(limits, {"max_runs": 2}, POLICY)
    limits = narrow_limits(limits, {}, replace(POLICY, max_runs=1000))
    assert limits["max_runs"] == 2
    assert effective_policy(replace(POLICY, max_runs=1), limits).max_runs == 1


@pytest.mark.parametrize("code", sorted(TRANSIENT_CODES))
@pytest.mark.parametrize(("pause_source", "expected"), [("system", "resume"), ("owner", "waiting")])
def test_resume_is_bound_to_paused_system_transients(code: str, pause_source: str, expected: str):
    run: Any = SimpleNamespace(
        status=SimpleNamespace(value="paused"), pause_source=pause_source, stop_code=code
    )
    assert classify_outcome(run, POLICY) == expected
    run.status.value = "waiting"
    assert classify_outcome(run, POLICY) == "waiting"


def test_invalid_results_and_quota_are_not_generic_transients(state: Any):
    run: Any = SimpleNamespace(
        status=SimpleNamespace(value="paused"), pause_source="system", stop_code="RESULT_INVALID"
    )
    assert classify_outcome(run, POLICY) == "stop(AUTOPILOT_OWNER_NEEDED)"
    run.stop_code = "QUOTA_EXHAUSTED"
    assert classify_outcome(run, POLICY, now=NOW) == "stop(AUTOPILOT_QUOTA)"
    reset = NOW + timedelta(seconds=POLICY.quota_wait_max_seconds)
    assert classify_outcome(run, POLICY, now=NOW, quota_reset_at=reset) == "wait_quota"
    assert classify_outcome(run, POLICY, now=reset, quota_reset_at=reset) == "resume"
    assert (
        stop_conditions(state, POLICY, NOW, AutopilotFacts(quota_exhausted=True, quota_reset_at=reset)) == ()
    )
    assert stop_conditions(state, POLICY, NOW, AutopilotFacts(waiting_runs=3)) == ("AUTOPILOT_OWNER_NEEDED",)
    assert len(OWNER_CODES) == 13


@pytest.mark.parametrize("offset", [0, -1, -3600])
@pytest.mark.parametrize("source", ["system", "owner"])
def test_elapsed_quota_reset_resumes_only_system_paused_runs(offset: int, source: str):
    run: Any = SimpleNamespace(
        status=SimpleNamespace(value="paused"), pause_source=source, stop_code="QUOTA_EXHAUSTED"
    )
    reset = NOW + timedelta(seconds=offset)
    assert classify_outcome(run, POLICY, now=NOW, quota_reset_at=reset) == (
        "resume" if source == "system" else "waiting"
    )
    run.status.value = "waiting"
    assert classify_outcome(run, POLICY, now=NOW, quota_reset_at=reset) == "waiting"
