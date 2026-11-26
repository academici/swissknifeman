"""Stage records (execution §4.7-§4.8)."""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.modules.execution.domain.lease import ProcessIdentity
from skm.modules.execution.domain.stage_record import (
    ACTIVE_STAGE_STATES,
    STAGE_TRANSITIONS,
    StageOutcomeKind,
    StageRecord,
    StageState,
    active_stage,
    begin_stage_record,
    complete_stage,
    control_plane_record,
    fail_stage,
    interrupt_stage,
    mark_runtime_started,
    os_stop_proven,
    record_process_identity,
    skipped_record,
)
from skm.modules.execution.domain.step import AttemptStep, RoleId, StepPurpose, StepState, finish_step
from skm.modules.execution.domain.workflow.stage_inputs import StageMode

NOW = datetime(2026, 10, 25, 12, 0, tzinfo=UTC)
DIGEST = "sha256:" + "1" * 64
OTHER_DIGEST = "sha256:" + "2" * 64


def uid(n: int) -> Any:
    return UUID(int=n)


def begin(
    existing: tuple[StageRecord, ...] = (), stage_type: str = "agent_step", **changes: Any
) -> StageRecord:
    values: dict[str, Any] = {
        "record_id": uid(900 + len(existing)),
        "attempt_id": uid(200),
        "run_id": uid(1),
        "task_id": uid(100),
        "stage_id": "execute",
        "stage_type": stage_type,
        "round_no": 1,
        "mode": StageMode.NORMAL,
        "input_digest": DIGEST,
        "fencing_token": 3,
        "now": NOW,
    }
    values.update(changes)
    return begin_stage_record(existing, **values)


def identity(kind: str, unit: str, pid: int = 10) -> ProcessIdentity:
    return ProcessIdentity(pid, pid, NOW, {"owner": {"unit_kind": kind, "unit_id": unit, "nonce": "n"}})


# --- transitions


def test_the_transition_table_of_section_4_7() -> None:
    assert (StageState.CONTEXT_DRAFT, StageState.RUNNING) in STAGE_TRANSITIONS
    assert (StageState.STARTED, StageState.RUNNING) in STAGE_TRANSITIONS
    assert (None, StageState.COMPLETED) in STAGE_TRANSITIONS
    assert (None, StageState.SKIPPED) in STAGE_TRANSITIONS
    for target in (StageState.COMPLETED, StageState.FAILED, StageState.INTERRUPTED):
        for source in ACTIVE_STAGE_STATES:
            assert (source, target) in STAGE_TRANSITIONS
    assert (StageState.RUNNING, StageState.STARTED) not in STAGE_TRANSITIONS


@pytest.mark.parametrize(("stage_type", "state"), [
    ("agent_step", StageState.CONTEXT_DRAFT),
    ("agent_review", StageState.CONTEXT_DRAFT),
    ("advisor_consult", StageState.CONTEXT_DRAFT),
    ("prepare_environment", StageState.STARTED),
    ("run_checks", StageState.STARTED),
    ("integrate", StageState.STARTED),
])  # fmt: skip
def test_begin_records_the_stage_before_it_runs(stage_type: str, state: StageState) -> None:
    record = begin(stage_type=stage_type)
    assert (record.state, record.seq, record.fencing_token, record.runtime_started_at) == (state, 1, 3, None)
    running = mark_runtime_started(record, now=NOW + timedelta(seconds=5))
    assert running.state is StageState.RUNNING
    assert running.runtime_started_at == NOW + timedelta(seconds=5)
    assert mark_runtime_started(running, now=NOW + timedelta(minutes=1)) is running


def test_plugin_stage_types_state_whether_they_run_an_agent() -> None:
    with pytest.raises(SkmError, match="plugin stage type"):
        begin(stage_type="lint_bot")
    assert begin(stage_type="lint_bot", agent=False).state is StageState.STARTED
    assert begin(stage_type="lint_bot", agent=True).state is StageState.CONTEXT_DRAFT


@pytest.mark.parametrize("agent", [True, False])
def test_plugin_stages_reach_running_from_their_pre_runtime_state(agent: bool) -> None:
    record = begin(stage_type="lint_bot", agent=agent)
    started_at = NOW + timedelta(seconds=5)
    running = mark_runtime_started(record, now=started_at)
    assert (running.state, running.runtime_started_at) == (StageState.RUNNING, started_at)
    assert mark_runtime_started(running, now=NOW + timedelta(minutes=1)) is running
    done = complete_stage(running, outcome_kind=StageOutcomeKind.SUCCESS, outcome={}, now=started_at)
    with pytest.raises(SkmError) as caught:
        mark_runtime_started(done, now=started_at)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION


def test_control_plane_stages_are_completed_at_once() -> None:
    record = control_plane_record(
        (),
        record_id=uid(900),
        attempt_id=uid(200),
        run_id=uid(1),
        task_id=uid(100),
        stage_id="accept",
        stage_type="acceptance_gate",
        round_no=1,
        input_digest=DIGEST,
        outcome_kind=StageOutcomeKind.ACCEPTED,
        outcome=None,
        now=NOW,
    )
    assert (record.state, record.fencing_token, record.finished_at) == (StageState.COMPLETED, 0, NOW)
    with pytest.raises(SkmError, match="control_plane_record"):
        begin(stage_type="acceptance_gate")
    with pytest.raises(SkmError, match="control-plane"):
        control_plane_record(
            (), record_id=uid(1), attempt_id=uid(200), run_id=uid(1), task_id=uid(100), stage_id="execute",
            stage_type="agent_step", round_no=1, input_digest=DIGEST, outcome_kind=StageOutcomeKind.SUCCESS,
            outcome=None, now=NOW,
        )  # fmt: skip


def test_skipped_stages_are_history() -> None:
    record = skipped_record(
        (), record_id=uid(900), attempt_id=uid(200), run_id=uid(1), task_id=uid(100), stage_id="scout",
        stage_type="agent_step", round_no=1, input_digest=DIGEST, now=NOW,
    )  # fmt: skip
    assert (record.state, record.finished_at) == (StageState.SKIPPED, NOW)
    with pytest.raises(SkmError) as caught:
        mark_runtime_started(record, now=NOW)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION


@pytest.mark.parametrize("close", ["complete", "fail", "interrupt"])
def test_finished_records_never_change(close: str) -> None:
    record = begin()
    later = NOW + timedelta(minutes=1)
    finished = {
        "complete": lambda: complete_stage(
            record, outcome_kind=StageOutcomeKind.SUCCESS, outcome={}, now=later
        ),
        "fail": lambda: fail_stage(
            record, error_code="RESULT_INVALID", now=later, outcome_kind=StageOutcomeKind.RESULT_INVALID
        ),
        "interrupt": lambda: interrupt_stage(record, now=later),
    }[close]()
    assert finished.finished_at == later
    for again in (
        lambda: complete_stage(finished, outcome_kind=StageOutcomeKind.SUCCESS, outcome=None, now=later),
        lambda: fail_stage(finished, error_code="RUNTIME_ERROR", now=later),
        lambda: interrupt_stage(finished, now=later),
        lambda: mark_runtime_started(finished, now=later),
    ):
        with pytest.raises(SkmError) as caught:
            again()
        assert caught.value.code is ErrorCode.INVALID_TRANSITION


def test_runtime_start_follows_the_stage_kind() -> None:
    # a non-agent stage never passes through context_draft, an agent stage never through started
    checks_in_draft = dataclasses.replace(begin(), stage_type="run_checks")
    agent_started = dataclasses.replace(begin(stage_type="run_checks"), stage_type="agent_step")
    for record in (checks_in_draft, agent_started):
        with pytest.raises(SkmError) as caught:
            mark_runtime_started(record, now=NOW)
        assert caught.value.code is ErrorCode.INVALID_TRANSITION


# --- one unfinished stage per attempt


def test_begin_is_idempotent_for_the_same_input_and_refuses_another_stage() -> None:
    first = begin()
    assert begin((first,), record_id=uid(999)) is first
    with pytest.raises(SkmError, match="unfinished"):
        begin((first,), input_digest=OTHER_DIGEST)
    with pytest.raises(SkmError, match="unfinished"):
        begin((first,), stage_id="review", stage_type="agent_review")
    done = complete_stage(first, outcome_kind=StageOutcomeKind.SUCCESS, outcome={}, now=NOW)
    second = begin((done,), stage_id="checks", stage_type="run_checks")
    assert (second.seq, active_stage((done, second))) == (2, second)


def test_two_unfinished_records_break_the_invariant() -> None:
    first = begin()
    second = begin((), record_id=uid(950), stage_id="checks", stage_type="run_checks")
    with pytest.raises(SkmError, match="at most one unfinished"):
        active_stage((first, second))
    assert active_stage(()) is None


@pytest.mark.parametrize(
    "changes",
    [
        {"input_digest": "sha256:short"},
        {"seq": 0},
        {"retry_of_id": uid(5)},
        {"state": StageState.COMPLETED, "finished_at": NOW},
        {"finished_at": NOW},
        {"error_code": "bad"},
        {"reused_from_step_id": uid(6)},
    ],
)
def test_record_invariants(changes: dict[str, Any]) -> None:
    base = {field: getattr(begin(), field) for field in StageRecord.__dataclass_fields__}
    with pytest.raises(SkmError) as caught:
        StageRecord(**{**base, **changes})
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_a_reused_scout_result_has_no_token_or_runtime() -> None:
    base = {field: getattr(begin(), field) for field in StageRecord.__dataclass_fields__}
    reused = StageRecord(**{
        **base, "state": StageState.COMPLETED, "finished_at": NOW, "outcome_kind": StageOutcomeKind.SUCCESS,
        "fencing_token": 0, "reused_from_step_id": uid(6),
    })  # fmt: skip
    assert reused.reused_from_step_id == uid(6)


# --- durable process identities and OS stop proof


def test_process_identities_of_every_unit_kind_are_kept_by_unit() -> None:
    record = mark_runtime_started(begin(), now=NOW)
    for kind, unit in (("step", "s1"), ("check", "c1"), ("git_effect", "e1")):
        record = record_process_identity(record, identity(kind, unit))
    assert [found.unit_key for found in record.process_identities] == [
        ("step", "s1"), ("check", "c1"), ("git_effect", "e1"),
    ]  # fmt: skip
    assert record_process_identity(record, identity("step", "s1")) is record
    with pytest.raises(SkmError, match="another process identity"):
        record_process_identity(record, identity("step", "s1", pid=11))
    with pytest.raises(SkmError, match=r"owner\.unit_kind"):
        record_process_identity(
            record, ProcessIdentity(1, 1, NOW, {"owner": {"unit_kind": "shell", "unit_id": "x"}})
        )
    interrupted = interrupt_stage(record, now=NOW)
    late = record_process_identity(interrupted, identity("check", "c2"))
    assert len(late.process_identities) == 4  # still durable after the lease is gone


def test_terminal_history_is_not_an_os_stop_proof() -> None:
    running = record_process_identity(mark_runtime_started(begin(), now=NOW), identity("step", "s1"))
    interrupted = interrupt_stage(running, now=NOW + timedelta(minutes=1))
    assert interrupted.state is StageState.INTERRUPTED
    assert interrupted.runtime_started_at is not None  # the runtime may have run: L2, not L1
    assert not os_stop_proven(interrupted, confirmed_units=frozenset(), host_markers_confirmed=False)
    assert not os_stop_proven(interrupted, confirmed_units=frozenset(), host_markers_confirmed=True)
    assert not os_stop_proven(
        interrupted, confirmed_units=frozenset({("step", "s1")}), host_markers_confirmed=False
    )
    assert os_stop_proven(
        interrupted, confirmed_units=frozenset({("step", "s1")}), host_markers_confirmed=True
    )
    completed = complete_stage(
        record_process_identity(mark_runtime_started(begin(), now=NOW), identity("check", "c1")),
        outcome_kind=StageOutcomeKind.SUCCESS, outcome={}, now=NOW,
    )  # fmt: skip
    assert not os_stop_proven(completed, confirmed_units=frozenset(), host_markers_confirmed=True)


def make_step(**changes: Any) -> AttemptStep:
    values: dict[str, Any] = {
        "id": uid(80), "attempt_id": uid(200), "stage_record_id": uid(900), "parent_step_id": None, "seq": 1,
        "role": RoleId.EXECUTOR, "purpose": StepPurpose.PRIMARY, "runtime_id": "claude_code", "model": "m1",
        "effort": "high", "operation": "new_implementation", "admission": {}, "route_source": "plan_route",
        "route_reason": "ROUTE_DEFAULT", "context_manifest_id": uid(81), "session_mode": "new",
        "session_ref": None, "session_fingerprint": None, "session_fingerprint_digest": DIGEST,
        "fresh_reason": None,
        "state": StepState.STARTED, "result": None, "raw_result_file_version_id": None, "repairs": (),
        "schema_errors": (), "usage": None, "usage_so_far": None, "process_identity": identity("step", "s1"),
        "activity": None, "route_snapshot": {"resolved": {"runtime_id": "claude_code", "model": "m1"}},
        "runtime_observation": None, "reuse_key": None, "transcript_file_version_id": None,
        "last_progress_at": None, "error_code": None, "started_at": NOW, "finished_at": None,
    }  # fmt: skip
    values.update(changes)
    return AttemptStep(**values)


def test_a_cancelled_step_proves_no_stop_and_keeps_its_route_snapshot() -> None:
    step = make_step()
    cancelled = finish_step(step, state=StepState.CANCELLED, now=NOW + timedelta(minutes=1))
    assert cancelled.state is StepState.CANCELLED
    assert cancelled.route_snapshot == step.route_snapshot
    record = record_process_identity(mark_runtime_started(begin(), now=NOW), step.process_identity)  # type: ignore[arg-type]
    assert not os_stop_proven(
        interrupt_stage(record, now=NOW), confirmed_units=frozenset(), host_markers_confirmed=True
    )
    with pytest.raises(SkmError):
        finish_step(cancelled, state=StepState.SUCCEEDED, now=NOW)


def test_the_route_snapshot_is_deeply_immutable() -> None:
    snapshot: dict[str, Any] = {
        "requested": {"class": "implementation"},
        "resolved": {"runtime_id": "claude_code", "model": "m1"},
        "installation": {"evidence": [{"digest": DIGEST}]},
    }
    step = make_step(route_snapshot=snapshot)
    snapshot["resolved"]["model"] = "m2"
    snapshot["installation"]["evidence"].append({"digest": OTHER_DIGEST})
    route = step.route_snapshot
    assert route is not None
    resolved, installation = route["resolved"], route["installation"]
    assert resolved == {"runtime_id": "claude_code", "model": "m1"}
    with pytest.raises(TypeError):
        resolved["model"] = "m2"  # type: ignore[index]
    with pytest.raises(TypeError):
        installation["evidence"][0]["digest"] = OTHER_DIGEST  # type: ignore[index,call-overload]
    with pytest.raises(AttributeError):
        installation["evidence"].append({})  # type: ignore[index,call-overload,union-attr]
    done = finish_step(step, state=StepState.CANCELLED, now=NOW + timedelta(minutes=1))
    assert done.route_snapshot == route
    assert done.route_snapshot["resolved"]["model"] == done.model == "m1"  # type: ignore[index,call-overload]
    assert len(done.route_snapshot["installation"]["evidence"]) == 1  # type: ignore[index,call-overload,arg-type]


def test_step_invariants() -> None:
    with pytest.raises(SkmError, match="only a succeeded step"):
        make_step(result={"x": 1})
    with pytest.raises(SkmError, match="reuse key"):
        make_step(reuse_key=DIGEST)
    with pytest.raises(SkmError, match="finished step"):
        make_step(state=StepState.FAILED)
    with pytest.raises(SkmError, match="fresh_reason"):
        make_step(session_mode="resume", fresh_reason="ROUTE_CHANGED")
