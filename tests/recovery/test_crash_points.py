"""Recovery at durable upload, result and worker handoff boundaries."""

from typing import cast

import pytest

from contracts.execution._worker_protocol_support import worker_claim
from fixtures.execution.blob_faults import application_with_blob_fault
from fixtures.execution.harness import clean_test_database, pg_session, recovery, test_database
from fixtures.execution.protocol import agent, client_with_uow, finalize, handoff
from skm.application_bus.client import SkmClient
from skm.application_bus.ports import EventReader
from skm.bootstrap.host_services import worker_command_factories, worker_concurrency
from skm.kernel.cancel import CancelSource
from skm.kernel.errors import InternalError
from skm.kernel.ports_uow import Surface
from skm.modules.execution import public as execution
from skm.modules.execution.application._worker_protocol import parse_worker_claim
from skm.modules.execution.domain.external_effect import EffectState
from skm.modules.execution.host.heartbeat import Heartbeat
from skm.modules.execution.host.stage_client import BoundStageClient
from skm.modules.execution.ports import (
    AcceptanceRepository,
    EvidenceBindingRepository,
    OutputRepository,
    StageRepository,
)
from support.fault_injection import FaultPlan, FaultPoint, FaultyClient, InjectedFault, faulty_uow_factory

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = pytest.mark.pg


@pytest.mark.parametrize(
    "point",
    [
        FaultPoint.BLOB_AFTER_STAGE,
        FaultPoint.BLOB_AFTER_PROMOTE,
        FaultPoint.UOW_AFTER_COMMIT,
        FaultPoint.CLIENT_AFTER_SERVER_COMMIT,
    ],
)
def test_evidence_and_result_commit_windows_recover_once(recovery, point):
    side = recovery
    case = agent(side)
    finalize(side, case)
    handoff(side, case)
    fault = FaultPlan({point: 1})
    content = b"Retained bytes of one failed stage.\n"
    stage_id = case.ready["stage_record_id"]
    key = f"crash-result:{case.attempt.id}"

    def snapshot():
        with side.uow(readonly=True) as uow:
            stage = uow.repo(StageRepository).get(stage_id)
            bindings = uow.repo(EvidenceBindingRepository).for_owner("attempt", case.attempt.id)
            event_ids = tuple(
                item.id
                for item in uow.repo(EventReader).after_workspace_seq(side.ws, 0, types=None, limit=200)
                if item.stream_id == case.run.id
            )
            assert not uow.repo(AcceptanceRepository).decisions_for_task(case.task.id)
            assert uow.repo(OutputRepository).latest(case.attempt.id) is None
            return stage, tuple(bindings), event_ids

    before = snapshot()
    assert before[0].finished_at is None
    assert before[1] == ()
    if point in {FaultPoint.BLOB_AFTER_STAGE, FaultPoint.BLOB_AFTER_PROMOTE}:
        with application_with_blob_fault(side, fault) as app:
            uploader = app.client(actor=side.worker1_client._actor, surface=Surface.WORKER)
            with pytest.raises(InjectedFault) as crash:
                uploader.upload_blob(side.ws, [content], size=len(content), media_type="text/plain")
            assert crash.value.point is point
        assert snapshot() == before

    staged = side.worker1_client.upload_blob(side.ws, [content], size=len(content), media_type="text/plain")
    command = execution.RecordStageResult(
        claim=worker_claim(side, case.claimed),
        stage_record_id=stage_id,
        outcome_kind="runtime_error",
        outcome={"error_code": "RUNTIME_TRANSPORT"},
        evidence=[
            {
                "owner": "attempt",
                "owner_id": str(case.attempt.id),
                "role": "evidence",
                "filename": "check.log",
                "media_type": "text/plain",
                "staged_blob": staged.to_json(),
            }
        ],
    )
    if point is FaultPoint.UOW_AFTER_COMMIT:
        client = client_with_uow(side, side.worker1_client, faulty_uow_factory(side.app.uow_factory, fault))
        with pytest.raises(InternalError) as after_commit:
            client.dispatch(command, idempotency_key=key)
        assert isinstance(after_commit.value.__cause__, InjectedFault)
        assert after_commit.value.__cause__.point is point
    elif point is FaultPoint.CLIENT_AFTER_SERVER_COMMIT:
        client = FaultyClient(side.worker1_client, fault, operations=("RecordStageResult",))
        with pytest.raises(InjectedFault) as after_response:
            client.dispatch(command, idempotency_key=key)
        assert after_response.value.point is point
    else:
        side.worker1_client.dispatch(command, idempotency_key=key)

    assert fault.hits[point] == 1
    committed = snapshot()
    assert committed[0].finished_at is not None
    assert len(committed[1]) == 1
    assert len(committed[2]) > len(before[2])
    replay = side.worker1_client.dispatch(command, idempotency_key=key)
    assert side.worker1_client.dispatch(command, idempotency_key=key) == replay
    assert snapshot() == committed


def test_runtime_crash_and_missed_heartbeat_latch_worker_stop(recovery):
    from contracts.runtimes.conftest import build
    from skm.adapters.runtimes._cli_session.session import SessionLimits

    side = recovery
    case = agent(side)
    finalize(side, case)
    handoff(side, case)
    claimed = case.claimed
    source, concurrency = CancelSource(), worker_concurrency()
    plan = FaultPlan({FaultPoint.RUNTIME_DURING_STEP: 1})
    client = FaultyClient(side.worker1_client, plan, heartbeat_losses=2)
    worker = BoundStageClient(
        cast("SkmClient", client),
        parse_worker_claim(worker_claim(side, claimed)),
        worker_command_factories(),
        source.token,
        source.cancel,
        concurrency=concurrency,
    )
    heartbeat = Heartbeat(worker, source, every_seconds=1, concurrency=concurrency)
    runtime = build(
        side.root / "fault-runtime",
        exit_code=None,
        stdout=b'{"type":"text_delta","text":"partial"}\n',
        limits=SessionLimits(poll_interval_seconds=0.05, wall_timeout_seconds=2),
    )

    def crash_running_call(_delay: float) -> None:
        assert runtime.child.poll() is None
        assert runtime.runner.spawns == 1
        plan.maybe_fail(FaultPoint.RUNTIME_DURING_STEP)

    runtime.sleeper.on_sleep = crash_running_call
    with pytest.raises(InjectedFault) as crash:
        runtime.session.result()
    assert crash.value.point is FaultPoint.RUNTIME_DURING_STEP
    heartbeat.tick()
    assert not source.token.cancelled
    heartbeat.tick()
    assert source.token.reason == "lease_lost"
    runtime.sleeper.on_sleep = None
    runtime.cancel.set()
    assert runtime.session.result().outcome == "cancelled"
    assert runtime.child.empty() is True
    assert b"partial" in (runtime.writer.step_dir / "stream.jsonl").read_bytes()
    assert plan.hits == {FaultPoint.RUNTIME_DURING_STEP: 1, FaultPoint.WORKER_HEARTBEAT_LOST: 2}
    heartbeat.tick()
    assert len(client.calls) == 2
    with side.uow(readonly=True) as uow:
        assert uow.repo(OutputRepository).latest(case.attempt.id) is None
        assert not uow.repo(AcceptanceRepository).decisions_for_task(case.task.id)


def test_emergency_stops_live_runtime_and_preserves_executing_push(recovery, tmp_path, monkeypatch):
    from fixtures.execution.processes import scenario, script, worker
    from fixtures.execution.recovery_process import (
        kill_runtime,
        process_case,
        restore_subreaper,
        running_identity,
    )
    from recovery._recovery_helpers import (
        assert_emergency_admission_closed,
        assert_emergency_push_reconciled,
        executing_push,
        stage_tokens,
    )
    from skm.platform.process.identity import identity_of
    from support.service_runner import Instance
    from unit.execution.application.test_autopilot_commands import command, configure
    from unit.execution.application.test_external_effects import configure_effect_policy, saved_effect

    side = recovery
    configure(side)
    configure_effect_policy(side)
    command(side, execution.StartAutopilot)
    case = process_case(side)
    fixture = scenario(side.root / "emergency-runtime.toml", "executor", hang=True)
    plan = script(side.root / "emergency-script.toml", [("executor", case.task.display_key, 1, fixture)])
    identity = None

    try:
        with worker(side, side.root / f"repository-{case.attempt.id}", plan) as process:
            stage, runtime_identity = running_identity(side, case, process)
            identity = runtime_identity
            valid = {
                identifier
                for identifier, revoked in stage_tokens(side, case.assignment.id).items()
                if revoked is None
            }
            assert valid
            transcripts = list((side.root / "state/steps").rglob("stream.jsonl"))
            assert any(path.stat().st_size for path in transcripts)
            with executing_push(side, tmp_path / "push") as (effect, git, journal):
                recorded = journal.read_bytes()
                assert saved_effect(side, effect.effect.id).state is EffectState.EXECUTING
                assert git.tip() == git.after
                actual = identity_of(runtime_identity.pid)
                assert actual is not None
                assert actual.start_ticks == runtime_identity.start_ticks
                result = command(side, execution.StopAutopilot, emergency=True)
                assert result["emergency"] is True
                assert set(result["cancelled_run_ids"]) >= {str(case.run.id), str(effect.run.id)}
                assert journal.read_bytes() == recorded

            def stopped():
                actual = identity_of(runtime_identity.pid)
                return actual is None or actual.start_ticks != runtime_identity.start_ticks

            Instance.wait_until(stopped, timeout=30, description="emergency cleanup of the owned runtime")
            identity = None
            current_tokens = stage_tokens(side, case.assignment.id)
            assert all(current_tokens[token] is not None for token in valid)
            assert any(path.exists() and path.stat().st_size for path in transcripts)

        assert_emergency_admission_closed(side, effect)
        assert_emergency_push_reconciled(side, git, effect, journal, recorded, tmp_path / "push", monkeypatch)

        with side.uow(readonly=True) as uow:
            assert uow.repo(StageRepository).get(stage.id).finished_at is not None
            assert uow.repo(OutputRepository).latest(case.attempt.id) is None
            assert not uow.repo(AcceptanceRepository).decisions_for_task(case.task.id)
        history = side.client.ask(execution.GetRunHistory(run_id=case.run.id)).to_json()
        assert history["entries"]
    finally:
        if identity is not None:
            actual = identity_of(identity.pid)
            if actual is not None and actual.start_ticks == identity.start_ticks:
                kill_runtime(identity)
        restore_subreaper(case)
