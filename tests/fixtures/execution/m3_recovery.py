"""A real killed provider turn inside the three-task DAG, resumed after waitpid proof."""

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

from contracts.execution._worker_protocol_support import worker_claim
from fixtures.execution.harness import expire, system_dispatch
from fixtures.execution.m3 import KEYS
from fixtures.execution.processes import worker
from fixtures.execution.recovery_process import kill_runtime, proof, running_identity, subreaper
from skm.adapters.runtimes._cli_session.identity import remove_marker
from skm.modules.execution import public as execution
from skm.modules.execution.generated.queries import GetStep
from skm.modules.execution.ports import (
    AcceptanceRepository,
    AttemptRepository,
    EnvironmentRepository,
    RunRepository,
    TaskRepository,
)
from skm.modules.workspace.public import RecordWorkerHeartbeat
from skm.platform.process.identity import identity_of
from support.service_runner import Instance


def interrupt_first_executor(side, run_id, repository, script_path):
    identity = None
    with subreaper():
        try:
            with worker(side, repository, script_path) as process:

                def current():
                    with side.uow(readonly=True) as uow:
                        tasks = uow.repo(TaskRepository).list_for_run(run_id)
                        first = next(t for t in tasks if t.display_key == KEYS[0])
                        return (
                            uow.repo(AttemptRepository).get(first.current_attempt_id)
                            if first.current_attempt_id
                            else None
                        )

                attempt = Instance.wait_until(current, description="first M3 attempt")
                stage, identity = running_identity(side, SimpleNamespace(attempt=attempt), process)
                with side.uow(readonly=True) as uow:
                    environment = uow.repo(EnvironmentRepository).for_attempt(attempt.id)
                target = Path(environment.local_locator) / "repo/src/target.py"
                Instance.wait_until(lambda: target.read_text() == "answer = 41\n")
                # Alive but silent, without an expired deadline: observing it must not stop it.
                assert process.poll() is None
                Instance.kill(process)
            kill_runtime(identity)
            stopped = identity
            identity = None
            receipt = proof(stage, stopped)
            marker = side.root / "state/identities" / f"{receipt['unit_id']}.json"
            if marker.exists():
                remove_marker(marker)
            # PostgreSQL owns lease time. Keep released assignments claimable now,
            # rather than shifting their available_at 121 seconds into the future.
            with side.uow(readonly=True) as uow:
                side.clock.set(uow.repo(RunRepository).now())
            expire(side, seconds=0)

            def recovery_ready():
                # The service and the explicit sweep may contend for SKIP LOCKED ownership.
                system_dispatch(side, "expire_leases")
                with side.uow(readonly=True) as uow:
                    task = uow.repo(TaskRepository).get(attempt.task_id)
                    return task.blocking_reason and task.blocking_reason.code.value == "RECOVERING"

            Instance.wait_until(recovery_ready, description="committed lease recovery")
            side.worker1_client.dispatch(RecordWorkerHeartbeat(side.worker1, None))
            command = execution.ClaimAssignment(
                worker_id=str(side.worker1),
                host_id=str(side.host1),
                workspace_id=str(side.ws),
                offer={
                    "capabilities": ["fake"],
                    "labels": ["linux"],
                    "environment_kinds": ["git_worktree"],
                    "isolation_profiles": ["worktree", "landlock"],
                },
                reaped_steps=[receipt],
            )
            held = []
            for _ in range(3):
                admitted = side.worker1_client.dispatch(command, idempotency_key=f"m3-reap:{side.new_id()}")
                assert admitted.get("attempt_id"), admitted
                if admitted["attempt_id"] == str(attempt.id):
                    break
                held.append(admitted)
            assert admitted.get("attempt_id") == str(attempt.id), admitted
            assert admitted["instruction"]["mode"] == "resume_interrupted"
            assert target.read_text() == "answer = 41\n"
            step = side.client.ask(GetStep(UUID(receipt["unit_id"])))
            assert step.payload_visibility == "unavailable"
            assert step.state != "succeeded"
            with side.uow(readonly=True) as uow:
                assert uow.repo(AttemptRepository).get(attempt.id).environment_id == environment.id
                assert not uow.repo(AcceptanceRepository).decisions_for_task(stage.task_id)
            assert list((side.root / "state").rglob("stream.jsonl"))
            for other in held:
                side.worker1_client.dispatch(
                    execution.ReleaseAssignment(
                        claim=worker_claim(side, other), reason="paused", retain_environment=True
                    ),
                    idempotency_key=f"m3-held-release:{side.new_id()}",
                )
            side.worker1_client.dispatch(
                execution.ReleaseAssignment(
                    claim=worker_claim(side, admitted), reason="paused", retain_environment=True
                ),
                idempotency_key=f"m3-release:{side.new_id()}",
            )
        finally:
            if identity is not None:
                actual = identity_of(identity.pid)
                if actual is not None and actual.start_ticks == identity.start_ticks:
                    kill_runtime(identity)
