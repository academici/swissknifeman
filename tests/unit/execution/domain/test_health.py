"""Health priority and truthful missing/stale observation coverage, without clocks or IO."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from skm.kernel.ids import AttemptId, HostId, RunId, TaskId, WorkerId
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.assignment import WorkerOffer
from skm.modules.execution.domain.health import HealthClass, classify_run_health, reap_proven
from skm.modules.execution.domain.ids import StageRecordId
from skm.modules.execution.domain.lease import ProcessIdentity
from skm.modules.execution.domain.stage_record import (
    begin_stage_record,
    interrupt_stage,
    mark_runtime_started,
    record_process_identity,
)
from skm.modules.execution.domain.workflow.stage_inputs import StageMode

NOW = datetime(2026, 11, 16, tzinfo=UTC)


def classify(**facts):
    return classify_run_health({"status": "running", "active_units": 1, **facts}, NOW)


@pytest.mark.parametrize(
    ("facts", "expected"),
    [
        ({"status": "succeeded", "recovery_open": True}, "finished"),
        ({"status": "cancelled", "open_blocking_request": True}, "finished"),
        (
            {
                "status": "paused",
                "stop_code": "QUOTA_EXHAUSTED",
                "budget_reset_at": (NOW + timedelta(hours=1)).isoformat(),
            },
            "waiting_budget_reset",
        ),
        ({"status": "paused", "open_blocking_request": True, "active_units": 0}, "waiting_owner"),
        ({"status": "paused", "recovery_open": True}, "stopped"),
        ({"status": "failed"}, "stopped"),
        ({"recovery_open": True, "lease_expired": True}, "recovering"),
        ({"unfinished_stage": True, "lease_expired": True}, "orphaned"),
        ({"active_units": 0}, "unknown"),
        ({"active_units": 0, "ready_tasks": 1}, "running"),
        ({"not_before": (NOW + timedelta(seconds=10)).isoformat()}, "waiting_provider"),
        ({"waiting_tool": True, "deadline_at": (NOW + timedelta(seconds=10)).isoformat()}, "waiting_tool"),
        (
            {"waiting_tool": True, "deadline_at": (NOW - timedelta(seconds=100)).isoformat()},
            "suspected_stall",
        ),
        ({"waiting_tool": True, "deadline_at": (NOW - timedelta(seconds=400)).isoformat()}, "hung"),
        ({"last_heartbeat_at": (NOW - timedelta(seconds=301)).isoformat()}, "hung"),
        (
            {"last_progress_at": (NOW - timedelta(seconds=6000)).isoformat(), "cpu_active": False},
            "suspected_stall",
        ),
        (
            {"last_progress_at": (NOW - timedelta(seconds=6000)).isoformat(), "repeated_command_count": 5},
            "suspected_stall",
        ),
        ({"last_progress_at": (NOW - timedelta(seconds=6000)).isoformat()}, "running"),
        ({"last_progress_at": (NOW - timedelta(seconds=6000)).isoformat(), "cpu_active": True}, "running"),
    ],
)
def test_first_matching_health_rule(facts, expected):
    assert classify(**facts).health == expected


@pytest.mark.parametrize("cpu", [None, True])
def test_missing_cpu_is_never_negative_progress_or_death(cpu):
    health = classify(
        process_alive=True, cpu_active=cpu, last_progress_at=(NOW - timedelta(hours=6)).isoformat()
    )
    assert health.health is HealthClass.RUNNING
    assert health.observation_state == "alive_but_no_progress"
    assert health.signal_coverage == ()


def test_monitor_liveness_does_not_refresh_a_stale_subject_watermark():
    result = classify(
        process_alive=True,
        input_stale=True,
        monitor_alive=True,
        input_watermark=42,
        cpu_active=False,
        cpu_available=True,
        heartbeat_available=True,
        last_heartbeat_at=(NOW - timedelta(hours=1)).isoformat(),
        last_progress_at=(NOW - timedelta(hours=1)).isoformat(),
    )
    assert result.health is HealthClass.RUNNING
    assert result.observation_state == "unknown"
    assert result.input_watermark == 42
    assert result.signal_coverage == ()


def test_observation_coverage_has_explicit_provenance():
    result = classify(
        progress_observed=True,
        progress_available=True,
        runtime_available=True,
        last_observed_at=NOW.isoformat(),
        input_watermark="snapshot-1",
    )
    assert result.last_observed_at == NOW
    assert result.signal_coverage == ("runtime", "progress")
    assert result.observation_state == "progress_observed"


def test_zero_idle_and_repeat_thresholds_disable_suspicion():
    result = classify(
        thresholds={"idle_seconds": 0, "stall_repeat_n": 0},
        cpu_active=False,
        repeated_command_count=100,
        last_progress_at=(NOW - timedelta(hours=1)).isoformat(),
    )
    assert result.health is HealthClass.RUNNING


def test_server_stage_seconds_sum_parallel_work_and_exclude_pause_and_human_wait():
    from skm.modules.execution.domain.health import active_stage_seconds

    intervals = ((NOW, NOW + timedelta(seconds=10)), (NOW, NOW + timedelta(seconds=20)))
    events = (("run-paused", NOW + timedelta(seconds=2)), ("run-resumed", NOW + timedelta(seconds=7)))
    assert active_stage_seconds(intervals, events, NOW + timedelta(days=1)) == 20
    assert active_stage_seconds(intervals, (), NOW + timedelta(days=1)) == 30


def test_active_pause_does_not_age_an_unfinished_stage():
    from skm.modules.execution.domain.health import active_stage_seconds

    assert (
        active_stage_seconds(
            ((NOW, None),), (("run-paused", NOW + timedelta(seconds=5)),), NOW + timedelta(days=1)
        )
        == 5
    )


@pytest.mark.parametrize(
    "key", ["last_heartbeat_at", "last_progress_at", "deadline_at", "not_before", "budget_reset_at"]
)
def test_a_timestamp_without_offset_is_missing_not_a_crash(key: str) -> None:
    naive = (NOW - timedelta(seconds=6000)).replace(tzinfo=None)
    facts = {key: naive.isoformat(), "waiting_tool": True, "status": "running"}
    assert classify(**facts).health == classify(**{**facts, key: None}).health
    assert classify(**{key: naive}).health == classify(**{key: None}).health


def test_reap_needs_every_proof_to_confirm_the_host_markers() -> None:
    host = HostId(UUID(int=7))
    stage = mark_runtime_started(
        begin_stage_record(
            (),
            record_id=StageRecordId(UUID(int=900)),
            attempt_id=AttemptId(UUID(int=200)),
            run_id=RunId(UUID(int=1)),
            task_id=TaskId(UUID(int=100)),
            stage_id="execute",
            stage_type="agent_step",
            round_no=1,
            mode=StageMode.NORMAL,
            input_digest="sha256:" + "1" * 64,
            fencing_token=3,
            now=NOW,
        ),
        now=NOW,
    )
    proofs: list[JsonObject] = []
    for kind, unit in (("step", "s1"), ("check", "c1")):
        owner: JsonObject = {
            "host_id": str(host),
            "attempt_id": str(stage.attempt_id),
            "stage_record_id": str(stage.id),
            "unit_kind": kind,
            "unit_id": unit,
        }
        stage = record_process_identity(stage, ProcessIdentity(10, 10, NOW, {"owner": owner}))
        identity: JsonObject = {
            "ownership": {"owner": owner},
            "pid": 10,
            "pgid": 10,
            "started_at": NOW.isoformat(),
        }
        proofs.append(
            {
                "stage_record_id": str(stage.id),
                "dead": True,
                "unit_kind": kind,
                "unit_id": unit,
                "identity": identity,
            }
        )
    stage = interrupt_stage(stage, now=NOW)

    def offer(*reaped: JsonObject) -> WorkerOffer:
        return WorkerOffer(
            worker_id=WorkerId(UUID(int=40)),
            host_id=host,
            capabilities=frozenset(),
            labels=frozenset(),
            environment_kinds=frozenset(),
            isolation_profiles=frozenset(),
            reaped_steps=reaped,
        )

    assert reap_proven(stage, offer(*proofs))
    unconfirmed = {**proofs[0], "host_markers_confirmed": False}
    assert not reap_proven(stage, offer(unconfirmed, proofs[1]))  # the later proof must not override it
    assert not reap_proven(stage, offer(proofs[1], unconfirmed))
