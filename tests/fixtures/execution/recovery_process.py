"""Real killed worker/runtime evidence, retained until a new fenced owner is admitted."""

import ctypes
import os
import signal
from contextlib import contextmanager
from dataclasses import asdict
from types import SimpleNamespace
from typing import cast

from contracts.execution._worker_protocol_support import make_case
from fixtures.execution.protocol import add_budget, real_environment
from skm.bootstrap.host_services import build_host_storage
from skm.modules.execution.host.context import EnvironmentBindings, WorkerServices
from skm.modules.execution.ports import StageRepository
from skm.platform.process.identity import identity_of
from support.service_runner import Instance


@contextmanager
def subreaper():
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0
    assert libc.prctl(36, 1, 0, 0, 0) == 0
    try:
        yield
    finally:
        assert libc.prctl(36, previous.value, 0, 0, 0) == 0


def process_case(side):
    # Linux adoption gives this test an actual waitpid acknowledgement for the orphaned runtime.
    libc = ctypes.CDLL(None, use_errno=True)
    previous = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(previous), 0, 0, 0) == 0  # PR_GET_CHILD_SUBREAPER
    assert libc.prctl(36, 1, 0, 0, 0) == 0  # PR_SET_CHILD_SUBREAPER
    run, task, attempt, assignment = make_case(
        side, stage_id="execute", stage_type="agent_step", params={"role": "executor"}
    )
    add_budget(side, run)
    prepared, git, manager = real_environment(side, attempt)
    services = SimpleNamespace(state_dir=side.root / "state", storage=build_host_storage(side.root / "state"))
    EnvironmentBindings(cast("WorkerServices", services), floor=0).remember(
        str(attempt.id), str(prepared.environment_id), prepared.locator
    )
    return SimpleNamespace(
        run=run,
        task=task,
        attempt=attempt,
        assignment=assignment,
        prepared=prepared,
        git=git,
        manager=manager,
        previous_subreaper=previous.value,
        libc=libc,
    )


def running_identity(side, case, process=None):
    def observed():
        if process is not None and process.poll() is not None:
            raise AssertionError(
                (side.root / "worker.stdout").read_text() + (side.root / "worker.stderr").read_text()
            )
        with side.uow(readonly=True) as uow:
            entries = uow.repo(StageRepository).history(case.attempt.id).entries
            for entry in reversed(entries):
                if entry.record.process_identities and any(s.usage_so_far is not None for s in entry.steps):
                    return entry.record, entry.record.process_identities[-1]
        return None

    return Instance.wait_until(observed, timeout=90, description="durable runtime process identity")


def kill_runtime(identity):
    actual = identity_of(identity.pid)
    assert actual is not None
    assert actual.start_ticks == identity.start_ticks
    os.kill(identity.pid, signal.SIGKILL)
    pid, status = os.waitpid(identity.pid, 0)
    assert pid == identity.pid
    assert os.WIFSIGNALED(status)
    assert os.WTERMSIG(status) == signal.SIGKILL


def proof(stage, identity):
    wire = {key: value for key, value in asdict(identity).items() if value is not None}
    wire["started_at"] = identity.started_at.isoformat()
    return {
        "stage_record_id": str(stage.id),
        "unit_kind": "step",
        "unit_id": str(identity.ownership["owner"]["unit_id"]),
        "dead": True,
        "identity": wire,
    }


def restore_subreaper(case):
    assert case.libc.prctl(36, case.previous_subreaper, 0, 0, 0) == 0
