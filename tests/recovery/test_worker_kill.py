"""K12: real SIGKILL, actual orphan waitpid, and conservative containment recovery."""

import ctypes
import json
import os
import signal
import subprocess
import sys
from uuid import uuid4

import pytest

from fixtures.execution.harness import (
    clean_test_database,
    expire,
    pg_session,
    recovery,
    test_database,
)
from fixtures.execution.processes import worker
from fixtures.execution.recovery_process import (
    kill_runtime,
    proof,
    running_identity,
)
from skm.adapters.runtimes._cli_session.identity import create_marker, reap_orphans
from skm.modules.execution import public as execution
from skm.modules.execution.ports import (
    AttemptRepository,
    BudgetRepository,
    StageRepository,
    StepRepository,
    TaskRepository,
)
from skm.modules.runtimes.public import ProcessOwner, ProcessOwnership
from support.service_runner import Instance

__all__ = ["clean_test_database", "pg_session", "recovery", "test_database"]
pytestmark = pytest.mark.pg


@pytest.mark.parametrize("mode", ["unconfirmed", "same_host_reaped", "different_host"])
def test_sigkill_worker_recovers_unsealed_bytes_and_reaches_succeeded(recovery, mode):  # noqa: PLR0915 - complete OS/DB recovery trace
    from types import SimpleNamespace

    from fixtures.execution.harness import system_dispatch
    from fixtures.execution.recovery_process import subreaper
    from fixtures.execution.single_run import run_worker, single_run, successful_script
    from fixtures.execution.worker_registration import other_worker
    from skm.adapters.git.commit import git_vcs
    from skm.adapters.git.environments.worktree import WorktreeManager
    from skm.modules.execution.application._worker_inputs import previous_attempt
    from skm.modules.execution.ports import (
        AcceptanceRepository,
        EnvironmentRepository,
        OutputRepository,
        RunRepository,
    )
    from support.service_runner import ServiceRunner

    side = recovery
    confirmed, same_host = mode != "unconfirmed", mode != "different_host"
    case = single_run(side)
    plan = successful_script(side, case.task.display_key, interrupted=True)
    identity, alive = None, False
    with subreaper():
        try:
            with worker(side, case.repository, plan) as process:
                stage, identity = running_identity(side, case, process)
                alive = True
                with side.uow(readonly=True) as uow:
                    env = uow.repo(EnvironmentRepository).for_attempt(case.attempt.id)
                    assert uow.repo(OutputRepository).latest(case.attempt.id) is None
                manager = WorktreeManager(case.git, worktrees_root=side.root / "worktrees")
                prepared = manager.reopen(env.id, env.local_locator)
                old_root = prepared.mounts["repo"]
                assert (old_root / "src/target.py").read_text() == "answer = 41\n"
                vcs = git_vcs(case.git, state_dir=side.root / "recovery-inspection")
                crash_patch = vcs.diff(old_root, prepared.baseline[0].commit_sha)
                assert b"+answer = 41" in crash_patch
                Instance.kill(process)
                assert process.returncode == -signal.SIGKILL
            if confirmed:
                kill_runtime(identity)
                alive = False
            # PG is authoritative for leases. Age only the lease, without placing
            # the application's next assignment artificially 121 seconds in the future.
            with side.uow(readonly=True) as uow:
                side.clock.set(uow.repo(RunRepository).now())
            expire(side, seconds=0)
            claimant, host_id = side.worker1_client, side.host1
            worker_id = side.worker1
            if not same_host:
                worker_id, claimant = other_worker(side)
                host_id = side.host2
            raw = {
                "worker_id": str(worker_id),
                "host_id": str(host_id),
                "workspace_id": str(side.ws),
                "offer": {
                    "capabilities": ["fake"],
                    "labels": ["linux"],
                    "environment_kinds": ["git_worktree"],
                    "isolation_profiles": ["worktree", "landlock"],
                },
            }
            if confirmed:
                raw["reaped_steps"] = [proof(stage, identity)]
            admitted = claimant.dispatch(
                execution.ClaimAssignment(**raw), idempotency_key=f"reap:{side.new_id()}"
            )
            with side.uow(readonly=True) as uow:
                saved = uow.repo(StageRepository).get(stage.id)
                steps = uow.repo(StepRepository).for_stage(stage.id)
                assert saved.finished_at is not None
                assert all(s.state.value != "started" for s in steps)
                assert not uow.repo(BudgetRepository).open_for_steps(tuple(s.id for s in steps))
                assert uow.repo(OutputRepository).latest(case.attempt.id) is None
                assert uow.repo(StageRepository).reap_confirmed(stage.id) is (confirmed and same_host)
            if confirmed and same_host:
                assert admitted["attempt_id"] == str(case.attempt.id)
                assert admitted["instruction"]["mode"] == "resume_interrupted"
                claimant.dispatch(
                    execution.ReleaseAssignment(
                        claim={k: admitted[k] for k in ("assignment_id", "attempt_id", "fencing_token")}
                        | {"worker_id": str(worker_id)},
                        reason="waiting",
                        retain_environment=True,
                    ),
                    idempotency_key=f"release-recovery:{side.new_id()}",
                )
            else:
                assert admitted == {"outcome": "nothing_to_claim"}
                with side.uow() as uow:
                    task = uow.repo(TaskRepository).get(case.task.id)
                    assert task.blocking_reason.code.value == "RECOVERING"
                    uow.connection.execute(
                        "UPDATE skm_execution.run_tasks SET blocking_reason = "
                        "jsonb_set(blocking_reason, '{next_check_at}', "
                        "to_jsonb((clock_timestamp()-interval '1 second')::text)) WHERE id=%s",
                        (case.task.id,),
                    )
                    uow.commit()
                system_dispatch(side, "schedule_ready_tasks")
                with side.uow(readonly=True) as uow:
                    old = uow.repo(AttemptRepository).get(case.attempt.id)
                    task = uow.repo(TaskRepository).get(case.task.id)
                    current = uow.repo(AttemptRepository).get(task.current_attempt_id)
                    assert old.state.value == "ownership_lost"
                    assert task.attempt_count == 2
                    assert current.id != old.id
                    assert current.environment_id is None
                    previous = previous_attempt(uow, SimpleNamespace(task=task, attempt=current))
                    assert previous.outcome == "ownership_lost"
                    assert (
                        previous.patch_file_version_id is None
                    )  # unsealed bytes are never invented as an output
                if alive:
                    kill_runtime(identity)
                    alive = False
                assert vcs.diff(old_root, prepared.baseline[0].commit_sha) == crash_patch
            with ServiceRunner(side) as services:
                Instance.wait_until(services.healthy, description="replacement services")
                run_worker(side, case, plan)
            with side.uow(readonly=True) as uow:
                task = uow.repo(TaskRepository).get(case.task.id)
                current = uow.repo(AttemptRepository).get(task.current_attempt_id)
                fresh = uow.repo(EnvironmentRepository).for_attempt(current.id)
                assert uow.repo(RunRepository).get(case.run.id).status.value == "succeeded"
                assert task.status.value == "accepted"
                assert current.state.value == "completed"
                assert len(uow.repo(AcceptanceRepository).decisions_for_task(task.id)) == 1
                completed_steps = tuple(
                    step.id
                    for entry in uow.repo(StageRepository).history(current.id).entries
                    for step in entry.steps
                )
                assert not uow.repo(BudgetRepository).open_for_steps(completed_steps)
                if confirmed and same_host:
                    assert current.id == case.attempt.id
                    assert fresh.id == prepared.environment_id
                else:
                    assert fresh.id != prepared.environment_id
                    assert fresh.local_locator != env.local_locator
                    assert (old_root / "src/target.py").read_text() == "answer = 41\n"
                    assert uow.repo(OutputRepository).latest(case.attempt.id) is None
            assert any(p.stat().st_size for p in (side.root / "state/steps").rglob("stream.jsonl"))
            starts = [
                json.loads(line)
                for line in (side.root / "state/executor-starts.jsonl").read_text().splitlines()
            ]
            assert len(starts) == 2
            assert starts[0]["initial"] == "answer = 0\n"
            expected = "answer = 41\n" if confirmed and same_host else "answer = 0\n"
            resumed = next(start for start in starts if start["step_id"] != str(steps[0].id))
            assert resumed["initial"] == expected
        finally:
            if alive and identity is not None:
                from skm.platform.process.identity import identity_of

                actual = identity_of(identity.pid)
                if actual is not None and actual.start_ticks == identity.start_ticks:
                    kill_runtime(identity)


@pytest.mark.parametrize("backend", ["pgroup", "eperm", "unavailable"])
def test_dead_leader_and_escaped_descendant_never_produce_false_reaped(tmp_path, backend):
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    root = tmp_path / "identities"
    root.mkdir(mode=0o700)
    ready = tmp_path / "descendant.pid"
    code = "import os,signal,sys; child=os.fork(); " + (
        "\nif child == 0:\n os.setsid(); open(sys.argv[1], 'w').write(str(os.getpid())); signal.pause()"
        "\nelse:\n os._exit(0)\n"
    )
    leader = subprocess.Popen(  # noqa: TID251 - actual orphan/setsid regression
        [sys.executable, "-c", code, str(ready)], start_new_session=True
    )
    descendant = None
    try:
        leader.wait(timeout=5)
        descendant = int(Instance.wait_until(lambda: ready.read_text() if ready.exists() else None))
        owner = ProcessOwner(uuid4(), uuid4(), uuid4(), uuid4(), "step", uuid4(), "n" * 32, str(root))
        ownership = ProcessOwnership(
            owner,
            "pgroup_best_effort" if backend == "pgroup" else "container",
            "synthetic-unit",
            None if backend == "pgroup" else "synthetic-daemon-identity",
        )
        marker = create_marker(root, ownership)
        expected = ownership

        class Denied:
            def confirmed(self, ownership: ProcessOwnership) -> bool:
                assert ownership == expected
                return True

            def empty(self) -> bool:
                return False

            def signal(self, sig: int) -> None:
                raise PermissionError(f"injected OS EPERM for signal {sig}")

        assert reap_orphans(root, resolve=lambda _owner: None if backend == "unavailable" else Denied()) == ()
        assert marker.exists()
        os.kill(descendant, 0)  # still alive outside the dead leader's session
    finally:
        if descendant is not None:
            os.kill(descendant, signal.SIGKILL)
            os.waitpid(descendant, 0)
        Instance.stop(leader)
        assert libc.prctl(36, previous.value, 0, 0, 0) == 0
