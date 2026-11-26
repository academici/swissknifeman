"""Two transport failures latch stop mode on a live, fenced PostgreSQL assignment."""

from typing import cast

import pytest

from contracts.execution._worker_protocol_support import make_case, worker_claim
from fixtures.execution.harness import (
    clean_test_database,
    pg_session,
    recovery,
    recovery_claim,
    test_database,
)
from skm.application_bus.client import SkmClient
from skm.bootstrap.host_services import worker_command_factories, worker_concurrency
from skm.kernel.cancel import CancelSource
from skm.modules.execution.application._worker_protocol import parse_worker_claim
from skm.modules.execution.host.heartbeat import Heartbeat
from skm.modules.execution.host.stage_client import BoundStageClient
from support.fault_injection import FaultPlan, FaultPoint, FaultyClient

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = pytest.mark.pg


def test_two_lost_heartbeats_stop_admission_and_suppress_late_results(recovery):
    side = recovery
    make_case(side)
    claimed = recovery_claim(side)
    source = CancelSource()
    plan = FaultPlan({})
    client = FaultyClient(side.worker1_client, plan, heartbeat_losses=2)
    worker = BoundStageClient(
        cast("SkmClient", client),
        parse_worker_claim(worker_claim(side, claimed)),
        worker_command_factories(),
        source.token,
        source.cancel,
        concurrency=worker_concurrency(),
    )
    heartbeat = Heartbeat(worker, source, every_seconds=1, concurrency=worker_concurrency())
    heartbeat.tick()
    assert not source.token.cancelled
    heartbeat.tick()
    assert source.token.reason == "lease_lost"
    assert plan.hits[FaultPoint.WORKER_HEARTBEAT_LOST] == 2
    before = len(client.calls)
    heartbeat.tick()
    assert len(client.calls) == before


def test_live_runtime_is_cancelled_and_its_late_result_is_not_uploaded(recovery):
    import json

    from fixtures.execution.processes import scenario, script, worker
    from fixtures.execution.recovery_process import process_case, restore_subreaper
    from skm.modules.execution.ports import AcceptanceRepository, OutputRepository
    from skm.platform.process.identity import identity_of

    side = recovery
    case = process_case(side)
    side.heartbeat_fault = True
    fixture = scenario(side.root / "heartbeat-hang.toml", "executor", hang=True)
    plan = script(side.root / "heartbeat-script.toml", [("executor", case.task.display_key, 1, fixture)])
    try:
        with worker(side, side.root / f"repository-{case.attempt.id}", plan) as process:
            process.wait(timeout=120)
            out = json.loads((side.root / "worker.stdout").read_text())
            assert out["slots"][0]["reason"] == "lease_lost"
        facts = list((side.root / "state/ownership-facts").glob("*.json"))
        assert facts
        for file in facts:
            recorded = json.loads(file.read_text())
            actual = identity_of(recorded["pid"])
            assert actual is None or actual.start_ticks != recorded["start_ticks"]
        # Cancellation can precede a final role result; the real provider stream remains local.
        assert any(path.stat().st_size > 0 for path in (side.root / "state/steps").rglob("stream.jsonl"))
        calls = json.loads((side.root / "state/fake" / f"{case.run.id}.json").read_text())
        assert calls[json.dumps(["executor", case.task.display_key])] == 1
        with side.uow(readonly=True) as uow:
            assert uow.repo(OutputRepository).latest(case.attempt.id) is None
            assert not uow.repo(AcceptanceRepository).decisions_for_task(case.task.id)
    finally:
        restore_subreaper(case)


def test_queued_heartbeat_does_not_renew_a_committed_finished_assignment(recovery):
    from skm.modules.execution import public as execution
    from skm.modules.execution.ports import AssignmentRepository

    side = recovery
    make_case(side)
    claimed = recovery_claim(side)
    bound = parse_worker_claim(worker_claim(side, claimed))
    source, concurrency = CancelSource(), worker_concurrency()
    client = FaultyClient(side.worker1_client, FaultPlan({}))
    worker = BoundStageClient(
        cast("SkmClient", client),
        bound,
        worker_command_factories(),
        source.token,
        source.cancel,
        concurrency=concurrency,
    )
    queued = concurrency.event()
    heartbeat = Heartbeat(worker, source, every_seconds=1, concurrency=concurrency, tick_hook=queued.set)
    pending = concurrency.thread(heartbeat.tick, "queued-final-heartbeat")
    try:
        # The renewal has passed Heartbeat's stop check and waits behind the result/release lock.
        with worker.guard:
            pending.start()
            assert queued.wait(timeout=5)
            side.worker1_client.dispatch(
                execution.ReleaseAssignment(
                    claim=worker_claim(side, claimed), reason="waiting", retain_environment=True
                ),
                idempotency_key=f"finished-assignment:{side.new_id()}",
            )
            worker.clear_progress(assignment_finished=True)
    finally:
        pending.join(timeout=5)
    assert not pending.is_alive()
    assert not source.token.cancelled
    assert not client.calls
    with side.uow(readonly=True) as uow:
        assert uow.repo(AssignmentRepository).get(bound.assignment_id).state.value == "completed"
