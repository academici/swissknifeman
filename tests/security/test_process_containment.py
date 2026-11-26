"""Backend-independent ownership cases; real delegated-backend proof is reported separately."""

from __future__ import annotations

import ctypes
import dataclasses
import json
import os
import signal
import sys
import time
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path
from typing import Literal, override
from unittest.mock import patch

import pytest

from contracts.runtimes.conftest import Harness, build
from skm.adapters.runtimes._cli_session.cancel import terminate_group
from skm.adapters.runtimes._cli_session.identity import (
    GroupProcess,
    claim_marker,
    create_marker,
    is_same_process,
    reap_orphans,
    update_marker,
)
from skm.adapters.runtimes._cli_session.session import SessionLimits, TrustedProcessRunner
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.execution.host.isolation import WrappedCommand
from skm.modules.runtimes import public as rt
from skm.platform.process.identity import ProcessIdentity
from skm.platform.system_clock import SystemMonotonic


def test_marker_is_private_and_exists_before_backend_spawn(tmp_path: Path) -> None:
    harness = build(tmp_path)
    iterator = harness.session.run()
    next(iterator)  # native completion emits usage after final drain
    assert harness.runner.spawns == 1
    assert harness.session.result().outcome == "completed"
    assert not list(harness.session.identity_dir.glob("*.json"))
    assert not list(harness.session.identity_dir.glob("*.launch.lock"))


def test_prepared_marker_is_claimed_once_and_never_relaunched_after_uncertain_start(tmp_path: Path) -> None:
    harness = build(tmp_path)
    marker = create_marker(harness.session.identity_dir, harness.command.ownership)
    assert harness.session.result().outcome == "completed"
    assert not marker.exists()
    marker = claim_marker(harness.session.identity_dir, harness.command.ownership)
    assert json.loads(marker.read_bytes())["launching"] is True
    with pytest.raises(ValueError, match="already launched or uncertain"):
        claim_marker(harness.session.identity_dir, harness.command.ownership)
    assert marker.exists()


@pytest.mark.parametrize("state", ["unknown", "permission_denied"])
def test_uncertain_cleanup_never_erases_marker_or_reuses_environment(tmp_path: Path, state: str) -> None:
    harness = build(tmp_path, exit_code=None)
    harness.child.unknown = state == "unknown"
    harness.child.denied = state == "permission_denied"
    harness.cancel.set()
    result = harness.session.result()
    assert result.failure is not None
    assert result.failure.code == ErrorCode.RUNTIME_CRASHED
    assert result.failure.details == {"reason": "cleanup_unconfirmed"}
    assert len(list(harness.session.identity_dir.glob("*.json"))) == 1
    assert harness.command.cwd.is_dir()
    assert result.usage is not None
    assert result.observation is not None
    assert result.observation.capture.coverage == "partial"
    assert "capture_gap" in result.observation.capture.gaps
    assert result.observation.timing.duration_ms is None
    assert rt.validate_result_observation(result, request_id=harness.session.step_id) == ()
    assert rt.validate_event_stream(list(harness.session.run())) == ()


@pytest.mark.parametrize("escape", ["setsid", "double_fork", "dead_leader", "worker_sigkill"])
def test_owned_backend_survives_leader_loss_in_synthetic_port(tmp_path: Path, escape: str) -> None:
    harness = build(tmp_path)
    ownership = harness.command.ownership
    marker = claim_marker(harness.session.identity_dir, ownership)
    harness.child.owner = ownership
    harness.child.code = 0
    harness.child.escaped = True  # leader exited, backend still owns a daemon/descendant
    assert not harness.child.empty()
    assert marker.exists()
    outcome = terminate_group(
        None,
        ownership=ownership,
        backend=harness.child,
        mode="reap",
        clock=harness.clock,
        sleeper=harness.sleeper,
    )
    assert outcome.stopped
    assert harness.child.sent == [signal.SIGTERM]
    assert reap_orphans(harness.session.identity_dir, resolve=lambda _: harness.child)
    assert not marker.exists()
    assert not marker.with_suffix(".launch.lock").exists()
    harness.writer.close()


@pytest.mark.parametrize("backend_state", ["unknown", "wrong_owner", "permission_denied", "unknown_daemon"])
def test_orphan_reap_preserves_unconfirmed_owner(tmp_path: Path, backend_state: str) -> None:
    harness = build(tmp_path)
    ownership = harness.command.ownership
    marker = create_marker(harness.session.identity_dir, ownership)
    harness.child.owner = ownership if backend_state != "wrong_owner" else None
    harness.child.unknown = backend_state == "unknown"
    harness.child.denied = backend_state == "permission_denied"
    backend = None if backend_state == "unknown_daemon" else harness.child
    assert (
        reap_orphans(
            harness.session.identity_dir,
            resolve=lambda _: backend,
            clock=harness.clock,
            sleeper=harness.sleeper,
        )
        == ()
    )
    assert marker.exists()
    assert harness.command.cwd.is_dir()
    harness.writer.close()


def test_pid_reuse_does_not_signal_an_unrelated_process(tmp_path: Path) -> None:
    harness = build(tmp_path)
    marker = create_marker(harness.session.identity_dir, harness.command.ownership)
    identity = ProcessIdentity(42, 100, "boot-A")
    with patch("skm.platform.process.identity.identity_of", return_value=ProcessIdentity(42, 101, "boot-A")):
        assert not is_same_process(identity)
    assert not is_same_process(ProcessIdentity(42, None, None))
    assert reap_orphans(harness.session.identity_dir) == ()
    assert harness.child.sent == []
    assert marker.exists()
    harness.writer.close()


def test_container_name_reuse_cannot_substitute_for_daemon_identity(tmp_path: Path) -> None:
    harness = build(tmp_path)
    ownership = dataclasses.replace(
        harness.command.ownership, kind="container", ref="immutable-ID", daemon_identity="daemon-A"
    )
    marker = create_marker(harness.session.identity_dir, ownership)
    harness.child.owner = dataclasses.replace(ownership, daemon_identity="daemon-B")
    harness.child.code = 0
    assert reap_orphans(harness.session.identity_dir, resolve=lambda _: harness.child) == ()
    assert marker.exists()
    assert harness.child.sent == []
    harness.writer.close()


def test_permission_error_during_signal_is_not_stopped(tmp_path: Path) -> None:
    harness = build(tmp_path)
    harness.child.owner = harness.command.ownership
    harness.child.denied = True
    outcome = terminate_group(
        None,
        ownership=harness.command.ownership,
        backend=harness.child,
        mode="cancel",
        clock=harness.clock,
        sleeper=harness.sleeper,
    )
    assert not outcome.stopped
    assert outcome.reason == "signal_permission_denied"
    harness.writer.close()


@pytest.mark.parametrize("consent", [False, True])
@pytest.mark.parametrize("kind", ["cgroup", "container"])
def test_required_backend_unavailable_refuses_before_spawn(
    tmp_path: Path, consent: bool, kind: Literal["cgroup", "container"]
) -> None:
    harness = build(tmp_path)
    ownership = dataclasses.replace(
        harness.command.ownership,
        kind=kind,
        daemon_identity="synthetic-daemon" if kind == "container" else None,
    )
    harness.session.command = dataclasses.replace(harness.command, ownership=ownership)
    harness.session.ownership = ownership
    harness.session.runner = TrustedProcessRunner(allow_pgroup_best_effort=consent)
    with patch("skm.adapters.runtimes._cli_session.session.launch") as launch:
        with pytest.raises(CapabilityUnavailable) as error:
            harness.session.result()
        launch.assert_not_called()
    assert error.value.code == ErrorCode.SANDBOX_UNAVAILABLE
    assert harness.runner.spawns == 0
    assert not harness.session.identity_dir.exists()


def test_process_group_mode_requires_explicit_trusted_consent(tmp_path: Path) -> None:
    harness = build(tmp_path)
    ownership = dataclasses.replace(harness.command.ownership, kind="pgroup_best_effort")
    command = dataclasses.replace(harness.command, ownership=ownership)
    with pytest.raises(CapabilityUnavailable):
        TrustedProcessRunner().validate(command)
    TrustedProcessRunner(allow_pgroup_best_effort=True).validate(command)
    marker = create_marker(harness.session.identity_dir, ownership)
    harness.child.owner, harness.child.code = ownership, 0
    # A process-group marker is intentionally not sufficient for restart orphan recovery.
    assert reap_orphans(harness.session.identity_dir, resolve=lambda _: harness.child) == ()
    assert marker.exists()
    harness.writer.close()


def test_insecure_marker_is_not_trusted(tmp_path: Path) -> None:
    harness = build(tmp_path)
    marker = create_marker(harness.session.identity_dir, harness.command.ownership)
    marker.chmod(0o644)
    harness.child.owner, harness.child.code = harness.command.ownership, 0
    assert reap_orphans(harness.session.identity_dir, resolve=lambda _: harness.child) == ()
    assert marker.exists()
    assert json.loads(marker.read_text())["ref"] == harness.command.ownership.ref
    harness.writer.close()


class OsSleeper:
    @staticmethod
    def sleep(seconds: float) -> None:
        time.sleep(seconds)


def real_command(harness: Harness, code: str) -> WrappedCommand:
    ownership = dataclasses.replace(harness.command.ownership, kind="pgroup_best_effort")
    return dataclasses.replace(harness.command, argv=(sys.executable, "-I", "-c", code), ownership=ownership)


def test_real_session_pumps_pipes_updates_marker_and_terminates_group(tmp_path: Path) -> None:
    harness = build(tmp_path)
    code = """
import json, signal, sys
def stop(sig, frame):
    print('received SIGINT', file=sys.stderr, flush=True)
    sys.exit(0)
signal.signal(signal.SIGINT, stop)
data = sys.stdin.buffer.read()
assert data == b'p' * 131073
print('stdin bytes ' + str(len(data)), file=sys.stderr, flush=True)
print(json.dumps({'type': 'session_started'}), flush=True)
while True: signal.pause()
"""

    class InspectRunner(TrustedProcessRunner):
        child: GroupProcess | None = None

        @override
        def spawn(self, command, *, marker, on_stdout, on_stderr):
            assert marker.stat().st_mode & 0o777 == 0o600
            record = json.loads(marker.read_bytes())
            assert record["launching"] is True
            assert "process" not in record
            child = super().spawn(command, marker=marker, on_stdout=on_stdout, on_stderr=on_stderr)
            assert isinstance(child, GroupProcess)
            self.child = child
            return child

    runner = InspectRunner(allow_pgroup_best_effort=True)
    session = harness.session
    session.command = real_command(harness, code)
    session.ownership = session.command.ownership
    session.stdin = b"p" * 131_073  # More than one bounded nonblocking stdin write.
    session.clock, session.sleeper, session.runner = SystemMonotonic(), OsSleeper(), runner
    session.limits = SessionLimits(wall_timeout_seconds=5, poll_interval_seconds=0.01)
    events: list[rt.SessionEvent] = []
    try:
        iterator = session.run()
        events.append(next(iterator))  # Child acknowledges EOF only after all stdin arrived.
        child = runner.child
        assert child is not None
        assert isinstance(events[0], rt.SessionStarted)
        assert child.stdin_written == len(session.stdin)
        assert is_same_process(child.identity)
        assert child.pgid == os.getpgid(child.pid)
        marker = session.identity_dir / f"{session.step_id}.json"
        assert marker.stat().st_mode & 0o777 == 0o600
        assert json.loads(marker.read_bytes())["process"] == {
            **dataclasses.asdict(child.identity),
            "pgid": child.pgid,
        }
        assert marker.with_suffix(".launch.lock").exists()
        harness.cancel.set()
        events.extend(iterator)
        result = session.result()
        assert result.failure is not None
        assert result.failure.code == ErrorCode.SESSION_CANCELLED
        assert rt.validate_event_stream(events) == ()
        assert child.empty() is True
        assert not marker.exists()
        assert not marker.with_suffix(".launch.lock").exists()
        assert b"session_started" in (harness.writer.step_dir / "stream.jsonl").read_bytes()
        stderr = (harness.writer.step_dir / "stream.stderr").read_text()
        assert "stdin bytes 131073" in stderr
        assert "received SIGINT" in stderr
        assert result.observation is not None
        assert result.observation.capture.coverage == "complete"
    finally:
        child = runner.child
        if child is not None and child.empty() is not True:
            child.signal(signal.SIGKILL)
            await_exit(child)
            child.close()
        harness.writer.close()


@pytest.fixture
def adopted_descendants(tmp_path: Path) -> Iterator[Path]:
    """Reap every test daemon locally, including intermediate double-fork children."""
    prior = ctypes.c_int()
    libc = ctypes.CDLL(None, use_errno=True)
    assert libc.prctl(37, ctypes.byref(prior), 0, 0, 0) == 0  # PR_GET_CHILD_SUBREAPER
    assert libc.prctl(36, 1, 0, 0, 0) == 0  # PR_SET_CHILD_SUBREAPER
    registry = tmp_path / "descendants"
    try:
        yield registry
    finally:
        try:
            for line in registry.read_text().splitlines() if registry.exists() else ():
                pid = int(line)
                with suppress(ProcessLookupError):
                    os.kill(pid, signal.SIGKILL)
                with suppress(ChildProcessError):
                    os.waitpid(pid, 0)
        finally:
            assert libc.prctl(36, prior.value, 0, 0, 0) == 0


def await_report(child: GroupProcess, output: bytearray) -> dict[str, int]:
    deadline = time.monotonic() + 5
    while b"\n" not in output:
        assert time.monotonic() < deadline, "child did not acknowledge startup"
        child.pump()
        time.sleep(0.01)
    return json.loads(output.split(b"\n", 1)[0])


def await_exit(child: GroupProcess) -> int:
    deadline = time.monotonic() + 5
    while (code := child.poll()) is None:
        assert time.monotonic() < deadline, "child did not exit after signal"
        child.pump()
        time.sleep(0.01)
    return code


@pytest.mark.parametrize("escape", ["setsid", "double_fork"])
def test_real_setsids_double_fork_and_worker_death_backend_proof(
    tmp_path: Path, adopted_descendants: Path, escape: str
) -> None:
    harness = build(tmp_path / "session")
    code = """
import json, os, signal, sys
def register():
    with open(REGISTRY, 'a') as target: target.write(str(os.getpid()) + '\\n')
if os.fork() == 0:
    register()
    os.setsid()
    if DOUBLE_FORK and os.fork(): os._exit(0)
    if DOUBLE_FORK: register()
    print(json.dumps({'pid': os.getpid(), 'pgid': os.getpgrp()}), flush=True)
    while True: signal.pause()
while True: signal.pause()
""".replace("REGISTRY", repr(str(adopted_descendants))).replace("DOUBLE_FORK", repr(escape == "double_fork"))
    command = real_command(harness, code)
    marker = claim_marker(harness.session.identity_dir, command.ownership)
    output = bytearray()
    child = None
    escaped_fd = None
    try:
        child = TrustedProcessRunner(allow_pgroup_best_effort=True).spawn(
            command, marker=marker, on_stdout=output.extend, on_stderr=lambda _: None
        )
        assert isinstance(child, GroupProcess)
        update_marker(marker, child.identity, pgid=child.pgid)
        report = await_report(child, output)
        escaped_fd = os.pidfd_open(report["pid"])
        assert report["pgid"] != child.pgid
        # The original group can be empty while an escaped daemon is demonstrably still alive.
        child.signal(signal.SIGTERM)
        assert await_exit(child) == -signal.SIGTERM
        assert child.empty() is True
        child.close()
        signal.pidfd_send_signal(escaped_fd, 0)
        with patch.object(child, "signal", side_effect=AssertionError("orphan pgroup authority")):
            assert reap_orphans(harness.session.identity_dir, resolve=lambda _: child) == ()
        assert marker.exists()
        assert marker.with_suffix(".launch.lock").exists()
    finally:
        if escaped_fd is not None:
            with suppress(ProcessLookupError):
                signal.pidfd_send_signal(escaped_fd, signal.SIGKILL)
            os.close(escaped_fd)
        if isinstance(child, GroupProcess) and child.owned.signal_group(0):
            child.signal(signal.SIGKILL)
            await_exit(child)
            child.close()
        harness.writer.close()


def test_real_worker_sigkill_keeps_unowned_child_marker(tmp_path: Path, adopted_descendants: Path) -> None:
    harness = build(tmp_path / "worker")
    target = build(tmp_path / "runtime")
    target_command = real_command(target, "")
    marker = create_marker(target.session.identity_dir, target_command.ownership)
    code = """
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, SOURCE)
from skm.adapters.runtimes._cli_session.identity import claim_marker, load_marker, update_marker
from skm.adapters.runtimes._cli_session.session import TrustedProcessRunner
from skm.modules.execution.host.isolation import WrappedCommand
path = Path(MARKER)
ownership = load_marker(path)
claim_marker(path.parent, ownership)
command = WrappedCommand((sys.executable, '-I', '-c', 'import signal; signal.pause()'),
                         {}, Path(WORKDIR), ownership)
child = TrustedProcessRunner(allow_pgroup_best_effort=True).spawn(
    command, marker=path, on_stdout=lambda _: None, on_stderr=lambda _: None)
update_marker(path, child.identity, pgid=child.pgid)
with open(REGISTRY, 'a') as target: target.write(str(child.pid) + '\\n')
print(json.dumps({'pid': child.pid, 'pgid': child.pgid}), flush=True)
while True: time.sleep(1)
"""
    for key, value in {
        "SOURCE": str(Path(__file__).resolve().parents[2] / "src"),
        "MARKER": str(marker),
        "WORKDIR": str(target.command.cwd),
        "REGISTRY": str(adopted_descendants),
    }.items():
        code = code.replace(key, repr(value))
    command = real_command(harness, code)
    worker_marker = claim_marker(harness.session.identity_dir, command.ownership)
    worker, runtime_fd = None, None
    output = bytearray()
    try:
        worker = TrustedProcessRunner(allow_pgroup_best_effort=True).spawn(
            command, marker=worker_marker, on_stdout=output.extend, on_stderr=lambda _: None
        )
        assert isinstance(worker, GroupProcess)
        report = await_report(worker, output)
        runtime_fd = os.pidfd_open(report["pid"])
        assert report["pgid"] != worker.pgid
        assert json.loads(marker.read_bytes())["process"]["pid"] == report["pid"]
        worker.signal(signal.SIGKILL)
        assert await_exit(worker) == -signal.SIGKILL
        worker.close()
        signal.pidfd_send_signal(runtime_fd, 0)
        assert reap_orphans(target.session.identity_dir) == ()
        assert marker.exists()
        assert marker.with_suffix(".launch.lock").exists()
    finally:
        if runtime_fd is not None:
            with suppress(ProcessLookupError):
                signal.pidfd_send_signal(runtime_fd, signal.SIGKILL)
            os.close(runtime_fd)
        if isinstance(worker, GroupProcess) and worker.owned.signal_group(0):
            worker.signal(signal.SIGKILL)
            await_exit(worker)
            worker.close()
        harness.writer.close()
        target.writer.close()
