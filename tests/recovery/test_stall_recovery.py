"""Containment mismatch and delayed notifications never forge a stop receipt."""

from typing import Any

# Real PostgreSQL persistence: no alternate store or fake transaction can satisfy this test.
from contracts.execution.harness import exec_side
from contracts.execution.seed_helpers import seed_attempt, seed_run, seed_stage, seed_task
from skm.modules.execution.domain.recovery import RecoveryRecord, RecoveryStep
from skm.modules.execution.ports import RecoveryRepository
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "exec_side", "pg_session", "test_database"]


from skm.kernel.json_types import JsonObject
from skm.modules.execution.host.recovery import RecoveryOperation


class Containment:
    def __init__(self, *, owned=True, stopped=False):
        self.owned, self.stopped = owned, stopped
        self.calls = []

    def verify(self, request):
        return self.owned

    def snapshot(self, request, *, stream_bytes, events) -> JsonObject:
        assert (stream_bytes, events) == (65536, 50)
        return {"snapshot": "diagnostic"}

    def cancel(self, request, *, grace_seconds):
        self.calls.append("cancel")
        return self.stopped

    def kill(self, request, *, grace_seconds):
        self.calls.append("kill")
        return self.stopped


def test_identity_mismatch_never_signals_and_late_cancel_cannot_claim_stopped():
    ctx: Any = None
    host = Containment(owned=False)
    op = RecoveryOperation(host)
    assert op(ctx, {"action": "kill_group", "intervention_authorized": True})["stopped"] is False
    assert host.calls == []
    host.owned = True
    assert op(ctx, {"action": "kill_group"})["stopped"] is False
    assert host.calls == []
    result = op(ctx, {"action": "kill_group", "intervention_authorized": True})
    assert result["stopped"] is False
    assert result["host_degraded"] is True
    assert host.calls == ["kill"]


def test_snapshot_limits_are_enforced_at_host_boundary():
    ctx: Any = None
    assert RecoveryOperation(Containment())(ctx, {}) == {"snapshot": "diagnostic"}


def test_recovery_progress_and_terminal_immutability(exec_side):
    from dataclasses import replace

    import pytest

    from skm.kernel.errors import SkmError

    side = exec_side
    with side.uow() as uow:
        run = seed_run(side, uow)
        task = seed_task(side, uow, run.id)
        attempt = seed_attempt(side, uow, run.id, task.id)
        stage = seed_stage(side, uow, attempt)
        recovery = RecoveryRecord(
            side.new_id(),
            run.id,
            task.id,
            attempt.id,
            stage.id,
            None,
            "hung",
            (RecoveryStep.VERIFY_LEGIT,),
            None,
            None,
            (),
            side.clock.now(),
        )
        uow.repo(RecoveryRepository).add(recovery)
        uow.commit()
    with side.uow() as uow:
        repo = uow.repo(RecoveryRepository)
        assert repo.open_for_stage(stage.id) == recovery
        finished = replace(recovery, steps_done=tuple(RecoveryStep)[:3], outcome="not_needed")
        repo.save(finished)
        uow.commit()
    with side.uow() as uow:
        assert uow.repo(RecoveryRepository).open_for_stage(stage.id) is None
        with pytest.raises(SkmError):
            uow.repo(RecoveryRepository).save(replace(finished, outcome="retried"))


def test_silent_runtime_observes_cancel_only_after_independent_authority(tmp_path):
    import signal

    from contracts.runtimes.conftest import build
    from skm.adapters.runtimes._cli_session.session import SessionLimits

    harness = build(
        tmp_path,
        stdout=b"",
        stderr=b"",
        exit_code=None,
        limits=SessionLimits(idle_timeout_seconds=0.1, wall_timeout_seconds=10, poll_interval_seconds=0.05),
    )
    saw_silence = []

    def observe(_: float) -> None:
        if harness.clock.monotonic() >= 0.25:
            assert harness.session.idle_suspected
            assert harness.child.poll() is None
            assert harness.child.sent == []
            saw_silence.append(harness.clock.monotonic())
            harness.cancel.set()

    harness.sleeper.on_sleep = observe
    result = harness.session.result()
    assert saw_silence
    assert result.outcome == "cancelled"
    assert harness.child.sent[0] == signal.SIGINT
    assert harness.child.empty() is True


def test_silent_check_can_finish_before_its_own_deadline(tmp_path):
    import sys
    from dataclasses import replace

    from integration.checks.test_check_stdin import check_harness

    runner, request, deps, _, _ = check_harness(tmp_path)
    command = [sys.executable, "-c", "import time; time.sleep(0.15)"]
    quiet = runner.run(replace(request, timeout_seconds=2, definition={"argv": command}), deps)
    assert quiet.exit_code == 0
    assert not quiet.timed_out
    assert not quiet.interrupted
    assert quiet.stdout_path.read_bytes() == b""
    assert quiet.stderr_path.read_bytes() == b""
