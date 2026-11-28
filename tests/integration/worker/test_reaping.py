"""Durable backend binding, escaped descendants and uncertain ownership at worker restart."""

from __future__ import annotations

import contextlib
import errno
import os
import signal
import sys
from dataclasses import replace
from threading import Event
from typing import Literal
from uuid import uuid4

import pytest

from skm.adapters.runtimes._cli_session.identity import create_marker
from skm.bootstrap.host_services import WorkerReaper, build_host_storage
from skm.modules.execution.host.worker_loop import run
from skm.modules.runtimes.public import ProcessOwner, ProcessOwnership
from skm.platform.process.runner import spawn

from ._support import make_host


class Containment:
    def __init__(self, ownership, *, empty: bool | None = False, confirm=True, denied=False):
        self.ownership, self.is_empty, self.confirm, self.denied = ownership, empty, confirm, denied
        self.signals = []

    def confirmed(self, ownership):
        return self.confirm and ownership == self.ownership

    def empty(self):
        return self.is_empty

    def signal(self, sig):
        if self.denied:
            raise PermissionError("backend access denied")
        self.signals.append(sig)
        if sig in {signal.SIGINT, signal.SIGKILL}:
            self.is_empty = True


def ownership_at(state, *, kind: Literal["cgroup", "pgroup_best_effort"] = "cgroup"):
    return ProcessOwnership(
        ProcessOwner(
            uuid4(), uuid4(), uuid4(), uuid4(), "step", uuid4(), "n" * 32, str(state / "identities")
        ),
        kind,
        "owned-test-unit",
    )


@pytest.mark.parametrize("condition", ["pid_reuse", "EPERM", "daemon_unavailable", "unknown", "pgroup"])
def test_unknown_or_unowned_processes_keep_marker_and_block_claim(tmp_path, monkeypatch, condition):
    fixture = make_host(tmp_path, monkeypatch)
    owner = ownership_at(
        fixture.services.state_dir, kind="pgroup_best_effort" if condition == "pgroup" else "cgroup"
    )
    marker = create_marker(fixture.services.state_dir / "identities", owner)
    backend = Containment(
        owner,
        empty=None if condition == "unknown" else False,
        confirm=condition != "pid_reuse",
        denied=condition == "EPERM",
    )
    reaper = WorkerReaper(
        fixture.services.state_dir,
        fixture.services.storage,
        resolve=lambda _: None if condition == "daemon_unavailable" else backend,
    )
    # Unknown containment never becomes an empty proof just because its leader died.
    if condition == "unknown":
        monkeypatch.setattr(backend, "signal", lambda _: None)
        monkeypatch.setattr("skm.adapters.runtimes._cli_session.cancel._wait_empty", lambda *_: False)
    services = replace(
        fixture.services, reap=reaper.reap, reap_pending=reaper.pending, acknowledge_reap=reaper.acknowledge
    )
    fixture.entries[type(services)] = services
    assert run(fixture.ctx, fixture.request)["reason"] == "cleanup_unconfirmed"
    assert marker.exists()
    assert not fixture.client.calls


def test_confirmed_reap_has_durable_owner_proof_before_marker_removal(tmp_path):
    budget = build_host_storage(tmp_path)
    owner = ownership_at(tmp_path)
    marker = create_marker(tmp_path / "identities", owner)
    backend = Containment(owner)
    reaper = WorkerReaper(tmp_path, budget, resolve=lambda _: backend)
    (proof,) = reaper.reap()
    assert not marker.exists()
    assert not reaper.pending()
    assert proof["dead"] is True
    assert proof["unit_id"] == str(owner.owner.unit_id)
    assert proof["stage_record_id"] == str(owner.owner.stage_record_id)
    assert "env_patch" not in proof  # transcripts cannot be smuggled through the patch handoff
    assert WorkerReaper(tmp_path, budget, resolve=lambda _: backend).reap() == (proof,)
    reaper.acknowledge((proof,))
    assert reaper.reap() == ()


@pytest.mark.parametrize("error_number", [errno.EIO, errno.EPERM])
def test_reap_retries_proof_directory_sync_before_removing_marker(tmp_path, monkeypatch, error_number):
    owner = ownership_at(tmp_path)
    marker = create_marker(tmp_path / "identities", owner)
    budget = build_host_storage(tmp_path)
    backend = Containment(owner, empty=True)
    proofs = tmp_path / "recovery/reaped"
    target = proofs / f"{owner.owner.unit_id}.json"
    reaper = WorkerReaper(tmp_path, budget, resolve=lambda _: backend)
    real_sync = os.fsync
    failures = []

    def fail_published_directory(fd):
        if os.path.samefile(f"/proc/self/fd/{fd}", proofs) and target.exists():
            failures.append(fd)
            raise OSError(error_number, "proof directory sync failed")
        real_sync(fd)

    with monkeypatch.context() as patch:
        patch.setattr(os, "fsync", fail_published_directory)
        for _ in range(2):
            count = len(failures)
            assert reaper.reap() == ()
            assert len(failures) > count
            assert marker.exists()
    (proof,) = reaper.reap()
    assert proof["unit_id"] == str(owner.owner.unit_id)
    assert not marker.exists()


def test_kill9_leader_and_setsid_descendant_require_empty_backend_on_restart(tmp_path):
    from time import monotonic

    from skm.modules.runtimes.public import SessionHandle
    from skm.platform.process.identity import identity_of, is_same_process

    # A test-owned containment pins the real forked child's pidfd, even after setsid and leader death.
    # This tests the port against real OS processes; no delegated cgroup support is inferred for CI.
    ready = Event()
    children = []
    script = """import os, signal
pid = os.fork()
if pid == 0:
    os.setsid()
    print(os.getpid(), flush=True)
    signal.pause()
else:
    signal.pause()
"""

    def observed(line):
        children.append(int(line))
        ready.set()

    leader = spawn(
        (sys.executable, "-c", script), cwd=tmp_path, env={}, on_stdout=observed, on_stderr=lambda _: None
    )
    pidfd = None
    try:
        assert ready.wait(10)
        child = identity_of(children[0])
        assert child is not None
        pidfd = os.pidfd_open(child.pid)
        assert os.getsid(child.pid) == child.pid
        assert os.getsid(child.pid) != os.getsid(leader.pid)
        leader.kill()
        deadline = monotonic() + 5
        while is_same_process(leader.identity) and monotonic() < deadline:
            Event().wait(0.01)
        assert not is_same_process(leader.identity)
        assert is_same_process(child)
        budget = build_host_storage(tmp_path)
        owner = ownership_at(tmp_path)
        marker = create_marker(tmp_path / "identities", owner)
        backend = Containment(owner)
        backend.empty = lambda: not is_same_process(leader.identity) and not is_same_process(child)

        def terminate(sig):
            assert marker.exists()
            backend.signals.append(sig)
            signal.pidfd_send_signal(pidfd, sig)

        backend.signal = terminate
        reaper = WorkerReaper(tmp_path, budget, resolve=lambda _: backend)
        reaper.record(
            SessionHandle(
                "fake",
                str(owner.owner.unit_id),
                leader.pid,
                leader.identity.start_ticks,
                leader.started_at,
                owner,
            )
        )
        (proof,) = reaper.reap()
        assert proof["dead"] is True
        assert not marker.exists()
        assert not is_same_process(child)
        assert leader.wait(5) == -signal.SIGKILL
    finally:
        if pidfd is not None:
            with contextlib.suppress(ProcessLookupError):
                signal.pidfd_send_signal(pidfd, signal.SIGKILL)
            os.close(pidfd)
        leader.terminate(grace_seconds=0.01)
