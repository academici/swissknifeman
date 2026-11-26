import ctypes
import errno
import gc
import json
import os
import signal
import sys
import threading
import time
from collections import deque
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from typing import cast, override
from unittest.mock import Mock, call

import pytest

from skm.kernel.cancel import CancelSource
from skm.platform.process import ownership, runner
from skm.platform.process.environment import build_env
from skm.platform.process.identity import group_alive, identity_of, is_same_process
from skm.platform.process.ownership import ChildPipes, OwnedProcess
from skm.platform.process.streams import ProcessStreams


def _argv(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _no_delivery(owned: OwnedProcess, sig: int) -> bool:
    return True


def _always_alive(owned: OwnedProcess) -> bool:
    return True


def test_deferred_status_loss_after_empty_group_closes_owned_descriptor() -> None:
    # No real PIDs or signals: the group is already empty when another waiter takes the status.
    child = Mock(spec=runner._Child)
    child.owned = Mock(spec=OwnedProcess)
    child.owned.held_here.return_value = True
    child.owned.group_alive.return_value = False
    child.leader_exited.return_value = True
    child.guard = threading.RLock()
    error = runner._StatusLost("process_status_unknown")
    child._reap.side_effect = error
    assert runner._Child._reap_step(cast("runner._Child", child))
    child._cleanup_failed.assert_called_once_with(error)
    child.owned.close.assert_called_once_with()
    child._finish_pending.assert_called_once_with()
    assert child.mock_calls.index(call.owned.close()) < child.mock_calls.index(call._finish_pending())


def _run(tmp_path: Path, code: str, **kwargs: object) -> runner.ProcessResult:
    # A safety bound only: a loaded host can take seconds just to start the interpreter.
    return runner.run(_argv(code), cwd=tmp_path, env={}, timeout_seconds=30, **kwargs)  # type: ignore[arg-type]


@pytest.fixture
def reap_orphans() -> Generator[list[int]]:
    # Reap test grandchildren ourselves rather than depending on the host PID 1.
    pids: list[int] = []
    prior = ctypes.c_int()
    libc = ctypes.CDLL(None, use_errno=True)
    if sys.platform == "linux":
        assert libc.prctl(37, ctypes.byref(prior), 0, 0, 0) == 0  # PR_GET_CHILD_SUBREAPER
        assert libc.prctl(36, 1, 0, 0, 0) == 0  # PR_SET_CHILD_SUBREAPER
    try:
        yield pids
    finally:
        for pid in pids:
            with suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
            if sys.platform == "linux":
                os.waitpid(pid, 0)
        if sys.platform == "linux":
            assert libc.prctl(36, prior.value, 0, 0, 0) == 0


def test_explicit_env_cwd_literal_argv_and_stdin(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOST_SECRET", "not-for-child")
    args = _argv(
        "import json,os,sys; print(json.dumps([dict(os.environ),os.getcwd(),sys.argv[1:],sys.stdin.read()]))"
    )
    literal = "$(touch injected); 'a b'"
    result = runner.run(
        [*args, literal],
        cwd=tmp_path,
        env=build_env({"PATH": "/bin", "HOST_SECRET": "hidden"}),
        timeout_seconds=30,
        stdin=b"hello\n",
    )
    env, cwd, argv, stdin = json.loads(result.stdout)
    assert "HOST_SECRET" not in env
    assert env["PATH"] == "/bin"
    assert cwd == str(tmp_path)
    assert argv == [literal]
    assert stdin == "hello\n"
    assert not (tmp_path / "injected").exists()
    assert result.exit_code == 0
    assert result.argv == (*args, literal)
    assert not result.timed_out
    assert result.signal is None
    assert result.duration_seconds >= 0


def test_output_flood_and_large_input_do_not_deadlock(tmp_path: Path) -> None:
    result = _run(
        tmp_path,
        "import os,sys; sys.stdout.buffer.write(b'o'*2000000); sys.stdout.flush(); "
        "data=sys.stdin.buffer.read(); sys.stderr.buffer.write(b'e'*2000000); "
        "sys.stderr.flush(); sys.exit(0 if data == b'i'*2000000 else 9)",
        stdin=b"i" * 2_000_000,
        max_stdout_bytes=17,
        max_stderr_bytes=11,
    )
    assert result.exit_code == 0
    assert result.stdout == b"o" * 17
    assert result.stderr == b"e" * 11
    assert result.stdout_truncated
    assert result.stderr_truncated


@pytest.mark.parametrize("limit", [0, 3, 4])
def test_capture_exact_boundary_and_eof_stdin(tmp_path: Path, limit: int) -> None:
    result = _run(
        tmp_path, "import sys; assert sys.stdin.read()==''; print('abc',end='')", max_stdout_bytes=limit
    )
    assert result.stdout == b"abc"[:limit]
    assert result.stdout_truncated == (limit < 3)
    assert not result.stderr_truncated


@pytest.mark.parametrize("leader_exits", [False, True])
def test_timeout_and_normal_exit_kill_remaining_writers(
    tmp_path: Path, reap_orphans: list[int], leader_exits: bool
) -> None:
    code = """
import os,signal,time
from pathlib import Path
child=os.fork()
if child==0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    Path('descendant').write_text(str(os.getpid()))
    with open('writes', 'ab', buffering=0) as stream:
        while True:
            stream.write(b'x')
            time.sleep(.01)
else:
    while not Path('descendant').exists(): time.sleep(.001)
    if LEADER_EXITS: os._exit(0)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    while True: signal.pause()
""".replace("LEADER_EXITS", repr(leader_exits))
    try:
        # The leader that exits must never meet the deadline, however slowly it starts.
        timeout = 30 if leader_exits else 0.5
        result = runner.run(_argv(code), cwd=tmp_path, env={}, timeout_seconds=timeout, grace_seconds=0.03)
    finally:
        if (tmp_path / "descendant").exists():
            reap_orphans.append(int((tmp_path / "descendant").read_text()))
    assert reap_orphans
    child = identity_of(reap_orphans[0])
    assert child is None or not is_same_process(child)
    assert result.timed_out == (not leader_exits)
    assert result.exit_code == (0 if leader_exits else runner.TIMEOUT_EXIT)
    if not leader_exits:
        assert result.signal == signal.SIGKILL
    writes = (tmp_path / "writes").stat().st_size
    CancelSource().token.wait(0.05)
    assert (tmp_path / "writes").stat().st_size == writes


def test_escaped_descendant_holding_pipe_cannot_extend_deadline(
    tmp_path: Path, reap_orphans: list[int]
) -> None:
    code = """
import os,signal,time
from pathlib import Path
if os.fork()==0:
    os.setsid()
    Path('escaped').write_text(str(os.getpid()))
    while True: signal.pause()
while not Path('escaped').exists(): time.sleep(.001)
print('parent', flush=True)
"""
    try:
        result = _run(tmp_path, code)
    finally:
        if (tmp_path / "escaped").exists():
            reap_orphans.append(int((tmp_path / "escaped").read_text()))
    # Waiting for the escaped writer's EOF would run into the deadline and report a timeout.
    assert not result.timed_out
    assert result.exit_code == 0
    assert result.stdout == b"parent\n"
    # Explicitly demonstrate the documented process-group boundary, then fixture cleanup.
    escaped = identity_of(reap_orphans[0])
    assert escaped is not None
    assert is_same_process(escaped)


def test_spawn_lines_partial_tail_and_stdin(tmp_path: Path) -> None:
    out: list[bytes] = []
    err: list[bytes] = []
    handle = runner.spawn(
        _argv(
            "import sys; data=sys.stdin.buffer.read(); sys.stdout.buffer.write(data); "
            "sys.stderr.write('err\\nend')"
        ),
        cwd=tmp_path,
        env={},
        on_stdout=out.append,
        on_stderr=err.append,
    )
    try:
        assert handle.wait(0) is None
        handle.write_stdin(b"one\ntwo\npartial")
        handle.close_stdin()
        handle.close_stdin()
        assert handle.wait(3) == 0
        assert out == [b"one\n", b"two\n", b"partial"]
        assert err == [b"err\n", b"end"]
        assert handle.pgid == handle.pid == handle.identity.pid
        assert handle.started_at.utcoffset() is not None
        assert handle.wait(0) == 0
        assert handle.terminate(grace_seconds=0).exited
        handle.kill()
    finally:
        handle.kill()
        handle.wait(3)


@pytest.mark.parametrize("line_mode", [False, True])
def test_spawn_long_lines_have_bounded_buffers(tmp_path: Path, line_mode: bool) -> None:
    chunks: list[bytes] = []
    handle = runner.spawn(
        _argv("import sys; sys.stdout.buffer.write(b'x'*2000000)"),
        cwd=tmp_path,
        env={},
        on_stdout=chunks.append,
        on_stderr=lambda data: None,
        line_mode=line_mode,
    )
    try:
        assert handle.wait(3) == 0
        assert b"".join(chunks) == b"x" * 2_000_000
        assert max(map(len, chunks)) <= 65_536
    finally:
        handle.kill()
        handle.wait(3)


@pytest.fixture
def hanging_process(tmp_path: Path) -> Generator[tuple[runner.ProcessHandle, threading.Event]]:
    ready = threading.Event()
    handle = runner.spawn(
        _argv(
            "import signal; signal.signal(signal.SIGINT,signal.SIG_IGN); "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); signal.pause()"
        ),
        cwd=tmp_path,
        env={},
        on_stdout=lambda data: ready.set(),
        on_stderr=lambda data: None,
    )
    try:
        assert ready.wait(30)
        yield handle, ready
    finally:
        handle.kill()
        handle.wait(3)


@pytest.mark.parametrize(
    "ignore",
    [
        "",
        "signal.signal(signal.SIGINT, signal.SIG_IGN);",
        "signal.signal(signal.SIGINT, signal.SIG_IGN); signal.signal(signal.SIGTERM, signal.SIG_IGN);",
    ],
)
def test_termination_escalation_and_repetition(tmp_path: Path, ignore: str) -> None:
    ready = threading.Event()
    # Install an explicit INT handler so CPython does not print KeyboardInterrupt to stderr.
    handle = runner.spawn(
        _argv(
            "import signal,sys; signal.signal(signal.SIGINT, lambda *_: sys.exit(0)); "
            + ignore
            + "print('ready',flush=True);\nwhile True: signal.pause()"
        ),
        cwd=tmp_path,
        env={},
        on_stdout=lambda data: ready.set(),
        on_stderr=lambda data: None,
    )
    try:
        assert ready.wait(30)
        # Only an ignored signal waits out the grace; a handled one must have time to exit under load.
        result = handle.terminate(grace_seconds=0.5)
        expected = signal.SIGKILL if "SIGTERM" in ignore else signal.SIGTERM if ignore else signal.SIGINT
        assert result == runner.TerminationResult(expected, True, False, None)
        assert handle.terminate(grace_seconds=0) == result
        assert handle.wait(0) is not None
        assert not group_alive(handle.pgid)
    finally:
        handle.kill()
        handle.wait(3)


def test_signal_permission_failure_is_unconfirmed(
    hanging_process: tuple[runner.ProcessHandle, threading.Event], monkeypatch: pytest.MonkeyPatch
) -> None:
    handle, _ = hanging_process

    def denied(owned: OwnedProcess, sig: int) -> bool:
        raise PermissionError("denied")

    with monkeypatch.context() as patch:
        patch.setattr(OwnedProcess, "signal_group", denied)
        result = handle.terminate(grace_seconds=0)
    assert not result.exited
    assert not result.ignored
    assert result.reason == "signal_permission_denied"
    assert handle.wait(0) is None


def test_ignored_when_kill_does_not_confirm_group_stop(
    hanging_process: tuple[runner.ProcessHandle, threading.Event], monkeypatch: pytest.MonkeyPatch
) -> None:
    handle, _ = hanging_process
    with monkeypatch.context() as patch:
        patch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)
        patch.setattr(OwnedProcess, "group_alive", _always_alive)
        # No-op signals simulate a process that remains alive even after SIGKILL.
        patch.setattr(OwnedProcess, "signal_group", _no_delivery)
        result = handle.terminate(grace_seconds=0.01)
    assert result == runner.TerminationResult(signal.SIGKILL, False, True, "process_group_still_alive")


def test_callback_failure_preserved_when_cleanup_also_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = ValueError("callback failed")

    def callback(data: bytes) -> None:
        raise primary

    signal_group = OwnedProcess.signal_group

    def noisy_kill(owned: OwnedProcess, sig: int) -> bool:
        delivered = signal_group(owned, sig)
        if sig == 0:
            return delivered
        raise OSError(errno.EIO, "cleanup failed after delivery")

    monkeypatch.setattr(OwnedProcess, "signal_group", noisy_kill)
    handle = runner.spawn(
        _argv("import signal; print('ready',flush=True); signal.pause()"),
        cwd=tmp_path,
        env={},
        on_stdout=callback,
        on_stderr=lambda data: None,
    )
    with pytest.raises(ValueError, match="callback failed") as caught:
        handle.wait(3)
    assert caught.value is primary
    assert "cleanup failed" in " ".join(primary.__notes__)
    assert not group_alive(handle.pgid)


def test_cancel_interrupts_wait_without_sleep(
    hanging_process: tuple[runner.ProcessHandle, threading.Event],
) -> None:
    handle, _ = hanging_process
    source = CancelSource()

    def host_operation() -> runner.TerminationResult:
        assert source.token.wait(5)
        return handle.terminate(grace_seconds=0.01)

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(host_operation)
        source.cancel("lease_lost")
        assert result.result(timeout=3).exited


def test_stdin_writer_unblocks_when_child_is_terminated(
    hanging_process: tuple[runner.ProcessHandle, threading.Event],
) -> None:
    handle, _ = hanging_process
    with ThreadPoolExecutor(max_workers=1) as pool:
        writer = pool.submit(handle.write_stdin, b"x" * 2_000_000)
        assert handle.terminate(grace_seconds=0.01).exited
        with pytest.raises((ValueError, BrokenPipeError)):
            writer.result(timeout=3)


def test_signal_exit_and_missing_binary(tmp_path: Path) -> None:
    result = _run(tmp_path, "import os,signal; os.kill(os.getpid(),signal.SIGTERM)")
    assert result.exit_code == -signal.SIGTERM
    assert result.signal == signal.SIGTERM
    with pytest.raises(FileNotFoundError):
        runner.run([str(tmp_path / "absent")], cwd=tmp_path, env={}, timeout_seconds=1)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"timeout_seconds": -1},
        {"timeout_seconds": float("nan")},
        {"grace_seconds": float("inf")},
        {"max_stdout_bytes": -1},
        {"max_stderr_bytes": True},
    ],
)
def test_invalid_limits_fail_before_spawn(tmp_path: Path, kwargs: dict[str, float]) -> None:
    options = {"timeout_seconds": 1, **kwargs}
    with pytest.raises(ValueError, match=r"finite|integer"):
        runner.run([str(tmp_path / "absent")], cwd=tmp_path, env={}, **options)


def test_timeout_when_child_closes_all_pipes(tmp_path: Path) -> None:
    result = runner.run(
        _argv("import os,signal; os.close(0); os.close(1); os.close(2); signal.pause()"),
        cwd=tmp_path,
        env={},
        timeout_seconds=0.1,
        grace_seconds=0.01,
    )
    assert result.timed_out
    assert result.exit_code == runner.TIMEOUT_EXIT
    assert result.stdout == result.stderr == b""


@pytest.mark.parametrize("terminate", [False, True])
def test_spawn_cleans_writers_even_after_leader_exit(
    tmp_path: Path, reap_orphans: list[int], terminate: bool
) -> None:
    code = """
import os,signal,time
from pathlib import Path
if os.fork()==0:
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    Path('spawn-descendant').write_text(str(os.getpid()))
    while True: signal.pause()
while not Path('spawn-descendant').exists(): time.sleep(.001)
if TERMINATE:
    signal.signal(signal.SIGINT, lambda *_: os._exit(0))
print('ready',flush=True)
if TERMINATE:
    while True: signal.pause()
""".replace("TERMINATE", repr(terminate))
    ready = threading.Event()
    handle = runner.spawn(
        _argv(code), cwd=tmp_path, env={}, on_stdout=lambda data: ready.set(), on_stderr=lambda data: None
    )
    try:
        assert ready.wait(30)
        if terminate:
            assert handle.terminate(grace_seconds=0.1).exited
        assert handle.wait(3) == 0
        descendant = int((tmp_path / "spawn-descendant").read_text())
        current = identity_of(descendant)
        assert current is None or not is_same_process(current)
        assert not group_alive(handle.pgid)
    finally:
        handle.kill()
        handle.wait(3)
        if (tmp_path / "spawn-descendant").exists():
            reap_orphans.append(int((tmp_path / "spawn-descendant").read_text()))


@pytest.mark.parametrize(
    "error", [PermissionError("observation denied"), OSError(errno.EIO, "malformed process identity")]
)
def test_observation_permission_failure_is_unconfirmed(
    hanging_process: tuple[runner.ProcessHandle, threading.Event],
    monkeypatch: pytest.MonkeyPatch,
    error: OSError,
) -> None:
    handle, _ = hanging_process

    def denied(owned: OwnedProcess) -> bool:
        raise error

    with monkeypatch.context() as patch:
        patch.setattr(OwnedProcess, "group_alive", denied)
        result = handle.terminate(grace_seconds=0)
    assert not result.exited
    assert result.reason is not None


def test_reaped_handle_never_signals_reused_group(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    handle = runner.spawn(
        _argv("pass"), cwd=tmp_path, env={}, on_stdout=lambda data: None, on_stderr=lambda data: None
    )
    assert handle.wait(3) == 0
    calls: list[int] = []

    def record(owned: OwnedProcess, sig: int) -> bool:
        calls.append(sig)
        return True

    monkeypatch.setattr(OwnedProcess, "group_alive", _always_alive)
    monkeypatch.setattr(OwnedProcess, "signal_group", record)
    handle.kill()
    assert handle.terminate(grace_seconds=0).exited
    assert not calls


def test_identity_setup_failure_reaps_child(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    primary = OSError(errno.EIO, "selector setup failed")
    observed: list[int] = []

    def failed_identity(pid: int) -> None:
        observed.append(pid)
        raise primary

    monkeypatch.setattr(ownership, "identity_of", failed_identity)
    with pytest.raises(OSError, match="selector setup failed") as caught:
        _run(tmp_path, "import signal; signal.pause()")
    assert caught.value is primary
    assert identity_of(observed[0]) is None


def test_reader_close_failure_cannot_mask_callback_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = ValueError("callback primary")
    close = ProcessStreams.close

    def callback(data: bytes) -> None:
        raise primary

    def failed_close(streams: ProcessStreams) -> None:
        close(streams)
        raise OSError(errno.EIO, "pipe close secondary")

    monkeypatch.setattr(ProcessStreams, "close", failed_close)
    handle = runner.spawn(
        _argv("import signal; print('ready',flush=True); signal.pause()"),
        cwd=tmp_path,
        env={},
        on_stdout=callback,
        on_stderr=lambda data: None,
    )
    with pytest.raises(ValueError, match="callback primary") as caught:
        handle.wait(3)
    assert caught.value is primary
    assert "pipe close secondary" in " ".join(primary.__notes__)
    assert not group_alive(handle.pgid)


def test_run_never_raises_timeout_expired(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = runner._Child._drain
    children: list[runner._Child] = []
    with runner._pending_guard:
        baseline = runner._pending_children.copy()

    def drain(child: runner._Child, timeout: float | None, grace: float) -> None:
        original(child, timeout, grace)
        children.append(child)

    def status_pending(owned: OwnedProcess, timeout: float = 0) -> int | None:
        return None

    with monkeypatch.context() as patch:
        patch.setattr(runner._Child, "_drain", drain)
        patch.setattr(OwnedProcess, "reap", status_pending)
        started = time.monotonic()
        with pytest.raises(OSError, match="child_reap_unconfirmed"):
            _run(tmp_path, "pass")
        assert time.monotonic() - started < 1
        retained, worker = _new_retained_owner(baseline)
        assert retained is children[0]
        assert retained.held
        assert not retained.stopped
        assert retained.status is None
        assert retained.owned._pidfd is not None
    # An unconfirmed reap keeps the pidfd until the worker can finish the reap.
    assert retained.done.wait(3)
    worker.join(3)
    assert retained.stopped
    assert retained.status == 0
    assert retained.owned._pidfd is None
    with runner._pending_guard:
        assert retained not in runner._pending_children


class _FailedCleanup:
    """Signals other than the probe fail until released, then reach only the pidfd's group."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, error: OSError | None = None) -> None:
        self.released = threading.Event()
        self.denied = 0
        signal_group = OwnedProcess.signal_group

        def faulty(owned: OwnedProcess, sig: int) -> bool:
            if sig == 0 or self.released.is_set():
                return signal_group(owned, sig)
            self.denied += 1
            raise error or PermissionError(errno.EPERM, "signal delivery denied")

        monkeypatch.setattr(OwnedProcess, "signal_group", faulty)
        monkeypatch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)


def _assert_retained_until_release(
    child: runner._Child, worker: threading.Thread, fault: _FailedCleanup, primary: BaseException
) -> None:
    # Dropping every other reference must not close the pidfd of a live child.
    gc.collect()
    assert child.owned._pidfd is not None
    assert child.owned.signal_group(0)
    assert not child.stopped
    assert not child.done.is_set() or child.error is primary
    with runner._pending_guard:
        assert child in runner._pending_children
    fault.released.set()
    assert child.done.wait(3)
    worker.join(3)
    assert not worker.is_alive()
    assert child.stopped
    assert child.owned._pidfd is None
    # The failure the caller saw stays the outcome; a clean finish records no cleanup failure.
    assert child.error is primary
    with runner._pending_guard:
        assert child not in runner._pending_children
        assert not any(identity == child.identity for identity, _ in runner._cleanup_failures)


def test_callback_failure_with_failed_signal_and_reap_retains_live_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = ValueError("callback failed")

    def callback(data: bytes) -> None:
        raise primary

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    fault = _FailedCleanup(monkeypatch)
    handle = runner.spawn(
        _argv("import signal; print('ready',flush=True); signal.pause()"),
        cwd=tmp_path,
        env={},
        on_stdout=callback,
        on_stderr=lambda data: None,
    )
    try:
        with pytest.raises(ValueError, match="callback failed") as caught:
            handle.wait(3)
        assert caught.value is primary
        notes = " ".join(primary.__notes__)
        assert "signal delivery denied" in notes
        assert "child_reap_unconfirmed" in notes
        child, worker = _new_retained_owner(baseline)
        assert child is handle._child
        assert child.held
        assert child.owned.exit_code() is None
        assert fault.denied
        result = handle.terminate(grace_seconds=0)
        assert not result.exited
        assert result.reason == "process_group_cleanup_unconfirmed"
        _assert_retained_until_release(child, worker, fault, primary)
        assert child.status == -signal.SIGKILL
    finally:
        fault.released.set()


def test_pipe_failure_with_failed_signal_and_reap_retains_live_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = OSError(errno.EIO, "pipe read failed")
    step = ProcessStreams.step

    def failing_step(streams: ProcessStreams, timeout: float) -> None:
        step(streams, timeout)
        raise primary

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    fault = _FailedCleanup(monkeypatch)
    monkeypatch.setattr(ProcessStreams, "step", failing_step)
    try:
        with pytest.raises(OSError, match="pipe read failed") as caught:
            _run(tmp_path, "import signal; signal.pause()")
        assert caught.value is primary
        child, worker = _new_retained_owner(baseline)
        assert child.held
        for pipe in (child.proc.stdin, child.proc.stdout, child.proc.stderr):
            assert pipe.closed
        _assert_retained_until_release(child, worker, fault, primary)
        assert child.status == -signal.SIGKILL
    finally:
        fault.released.set()


def test_failure_after_leader_exit_retains_ownership_of_surviving_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reap_orphans: list[int]
) -> None:
    # The reap succeeds because the leader left by itself, while the failed signal spared a member.
    code = """
import os,signal,time
from pathlib import Path
if os.fork()==0:
    Path('member').write_text(str(os.getpid()))
    while True: signal.pause()
while not Path('member').exists() or not Path('member').stat().st_size: time.sleep(.001)
print('ready',flush=True)
"""
    primary = ValueError("callback failed")
    leader_gone = threading.Event()

    def callback(data: bytes) -> None:
        leader_gone.wait(3)
        raise primary

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    fault = _FailedCleanup(monkeypatch)
    handle = runner.spawn(_argv(code), cwd=tmp_path, env={}, on_stdout=callback, on_stderr=lambda data: None)
    deadline = time.monotonic() + 3
    while handle._child.owned.exit_code() is None:
        assert time.monotonic() < deadline
        CancelSource().token.wait(0.005)
    leader_gone.set()
    try:
        with pytest.raises(ValueError, match="callback failed"):
            handle.wait(3)
        child, worker = _new_retained_owner(baseline)
        assert child.status == 0
        assert not child.held
        member = identity_of(int((tmp_path / "member").read_text()))
        assert member is not None
        assert is_same_process(member)
        _assert_retained_until_release(child, worker, fault, primary)
        assert not is_same_process(member)
    finally:
        fault.released.set()
        if (tmp_path / "member").exists():
            reap_orphans.append(int((tmp_path / "member").read_text()))


def test_supervisor_thread_takes_over_when_the_worker_cannot_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = ValueError("callback failed")

    def callback(data: bytes) -> None:
        raise primary

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    start = threading.Thread.start

    def refused(thread: threading.Thread) -> None:
        if thread.name.startswith("skm-reap-"):
            raise RuntimeError("can't start new thread")
        start(thread)

    fault = _FailedCleanup(monkeypatch)
    monkeypatch.setattr(threading.Thread, "start", refused)
    handle = runner.spawn(
        _argv("import signal; print('ready',flush=True); signal.pause()"),
        cwd=tmp_path,
        env={},
        on_stdout=callback,
        on_stderr=lambda data: None,
    )
    child = handle._child
    try:
        with pytest.raises(ValueError, match="callback failed") as caught:
            handle.wait(3)
        assert caught.value is primary
        with runner._pending_guard:
            assert runner._pending_children - baseline == {child}
            assert (child.identity, "can't start new thread") in runner._cleanup_failures
        # The failure names the lost worker and who runs the cleanup instead: nothing claims a worker.
        notes = " ".join(primary.__notes__)
        assert "cleanup_worker_not_started" in notes
        assert "cleanup_worker_not_running" not in notes
        assert child.owned._pidfd is not None
        assert child.owned.exit_code() is None
    finally:
        fault.released.set()
    # Nobody starts or recovers anything here: the thread that was already running finishes it.
    handle._thread.join(3)
    assert not handle._thread.is_alive()
    assert child.stopped
    assert child.status == -signal.SIGKILL
    assert child.owned._pidfd is None
    assert child.error is primary
    assert ownership._unattended == {}
    with runner._pending_guard:
        assert child not in runner._pending_children


class _Unnoteable(ValueError):
    """A failure that refuses every note, with the error the test chooses."""

    refusal: type[BaseException] = RuntimeError

    @override
    def add_note(self, note: str, /) -> None:
        raise self.refusal("no room for a note")


class _UnnoteableOSError(OSError):
    @override
    def add_note(self, note: str, /) -> None:
        raise RuntimeError("no room for a note")


class _UnnoteableRuntimeError(RuntimeError):
    @override
    def add_note(self, note: str, /) -> None:
        raise RuntimeError("no room for a note")


class _UnprintableRuntimeError(RuntimeError):
    @override
    def __str__(self) -> str:
        raise RuntimeError("no text for this failure")


class _UnprintableOSError(PermissionError):
    @override
    def __str__(self) -> str:
        raise RuntimeError("no text for this failure")


def _assert_pipes_closed(child: runner._Child) -> None:
    for pipe in (child.proc.stdin, child.proc.stdout, child.proc.stderr):
        assert pipe.closed


@pytest.mark.parametrize("refusal", [RuntimeError, KeyboardInterrupt])
def test_refused_notes_cannot_skip_the_retention_of_a_spawned_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, refusal: type[BaseException]
) -> None:
    # Both cleanup failures want a note here. Before the fix the first refusal left collect at once.
    primary = _Unnoteable("callback failed")
    primary.refusal = refusal

    def callback(data: bytes) -> None:
        raise primary

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    fault = _FailedCleanup(monkeypatch)
    handle = runner.spawn(
        _argv("import signal; print('ready',flush=True); signal.pause()"),
        cwd=tmp_path,
        env={},
        on_stdout=callback,
        on_stderr=lambda data: None,
    )
    try:
        with pytest.raises(_Unnoteable) as caught:
            handle.wait(3)
        assert caught.value is primary
        child, worker = _new_retained_owner(baseline)
        assert child.owned.exit_code() is None
        _assert_pipes_closed(child)
        _assert_retained_until_release(child, worker, fault, primary)
        assert child.status == -signal.SIGKILL
    finally:
        fault.released.set()


def test_refused_notes_cannot_skip_the_retention_of_a_run_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = _UnnoteableOSError(errno.EIO, "pipe read failed")
    step = ProcessStreams.step

    def failing_step(streams: ProcessStreams, timeout: float) -> None:
        step(streams, timeout)
        raise primary

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    fault = _FailedCleanup(monkeypatch)
    monkeypatch.setattr(ProcessStreams, "step", failing_step)
    try:
        with pytest.raises(_UnnoteableOSError) as caught:
            _run(tmp_path, "import signal; signal.pause()")
        assert caught.value is primary
        child, worker = _new_retained_owner(baseline)
        _assert_pipes_closed(child)
        _assert_retained_until_release(child, worker, fault, primary)
        assert child.status == -signal.SIGKILL
    finally:
        fault.released.set()


def test_refused_note_cannot_skip_a_pipe_close_of_a_settled_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # stdin belongs to close_stdin alone here, which ran after the note that used to raise.
    primary = _Unnoteable("callback failed")
    close = ProcessStreams.close

    def callback(data: bytes) -> None:
        raise primary

    def failed_close(streams: ProcessStreams) -> None:
        close(streams)
        raise OSError(errno.EIO, "pipe close secondary")

    monkeypatch.setattr(ProcessStreams, "close", failed_close)
    handle = runner.spawn(
        _argv("import signal; print('ready',flush=True); signal.pause()"),
        cwd=tmp_path,
        env={},
        on_stdout=callback,
        on_stderr=lambda data: None,
    )
    with pytest.raises(_Unnoteable) as caught:
        handle.wait(3)
    assert caught.value is primary
    _assert_pipes_closed(handle._child)
    assert handle._child.stopped
    assert handle._child.owned._pidfd is None


def test_unprintable_cleanup_failure_keeps_primary_and_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = ValueError("callback failed")

    def callback(data: bytes) -> None:
        raise primary

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    fault = _FailedCleanup(monkeypatch, error=_UnprintableOSError(errno.EPERM, "denied"))
    handle = runner.spawn(
        _argv("import signal; print('ready',flush=True); signal.pause()"),
        cwd=tmp_path,
        env={},
        on_stdout=callback,
        on_stderr=lambda data: None,
    )
    try:
        with pytest.raises(ValueError, match="callback failed") as caught:
            handle.wait(3)
        assert caught.value is primary
        assert "<unprintable _UnprintableOSError>" in " ".join(primary.__notes__)
        child, worker = _new_retained_owner(baseline)
        _assert_retained_until_release(child, worker, fault, primary)
    finally:
        fault.released.set()


@pytest.mark.parametrize(
    ("failure", "evidence"),
    [
        (_UnnoteableRuntimeError("can't start new thread"), "can't start new thread"),
        (_UnprintableRuntimeError("hidden"), "<unprintable _UnprintableRuntimeError>"),
    ],
)
def test_deferred_worker_failure_with_broken_diagnostics_is_still_the_outcome(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: RuntimeError, evidence: str
) -> None:
    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    start = threading.Thread.start
    signal_group = OwnedProcess.signal_group
    released = threading.Event()

    def refused(thread: threading.Thread) -> None:
        if thread.name.startswith("skm-reap-"):
            raise failure
        start(thread)

    def held_back(owned: OwnedProcess, sig: int) -> bool:
        return signal_group(owned, sig) if sig == 0 or released.is_set() else True

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", refused)
        patch.setattr(OwnedProcess, "signal_group", held_back)
        patch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)
        with pytest.raises(RuntimeError) as caught:
            runner.run(
                _argv("import signal; signal.pause()"),
                cwd=tmp_path,
                env={},
                timeout_seconds=0.05,
                grace_seconds=0,
            )
        assert caught.value is failure
        with runner._pending_guard:
            retained = runner._pending_children - baseline
            assert len(retained) == 1
            child = retained.pop()
            assert (child.identity, evidence) in runner._cleanup_failures
        assert child.owned.exit_code() is None
        assert ownership.recover_cleanups() == (f"skm-reap-{child.proc.pid}",)
        released.set()
    assert ownership.recover_cleanups() == ()
    assert child.done.wait(3)
    assert child.stopped
    assert child.owned._pidfd is None


def test_lost_status_with_an_unprintable_signal_failure_stays_unknown(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fault = _FailedCleanup(monkeypatch)
    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    exit_code = OwnedProcess.exit_code
    lost: list[int] = []

    def lost_status(owned: OwnedProcess) -> int | None:
        if lost:
            raise ChildProcessError(errno.ECHILD, "status went elsewhere")
        return exit_code(owned)

    def timed_out_send(child: runner._Child, sig: int) -> bool:
        lost.append(sig)
        raise _UnprintableOSError(errno.EPERM, "denied")

    monkeypatch.setattr(OwnedProcess, "exit_code", lost_status)
    monkeypatch.setattr(runner._Child, "send", timed_out_send)
    try:
        with pytest.raises(ProcessLookupError, match="process_status_unknown") as caught:
            runner.run(
                _argv("import signal; signal.pause()"),
                cwd=tmp_path,
                env={},
                timeout_seconds=0.05,
                grace_seconds=0,
            )
        assert "<unprintable _UnprintableOSError>" in " ".join(caught.value.__notes__)
        child, worker = _new_retained_owner(baseline)
        assert child.owned._pidfd is not None
    finally:
        monkeypatch.undo()
        fault.released.set()
    assert child.owned.signal_group(signal.SIGKILL)
    assert child.done.wait(3)
    worker.join(3)
    assert not worker.is_alive()


def test_failed_status_probe_cannot_skip_the_deferred_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken_probe(child: runner._Child) -> bool:
        raise ValueError("status probe failed")

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    fault = _FailedCleanup(monkeypatch)
    monkeypatch.setattr(runner._Child, "_status_lost", broken_probe)
    try:
        result = runner.run(
            _argv("import signal; signal.pause()"),
            cwd=tmp_path,
            env={},
            timeout_seconds=0.05,
            grace_seconds=0,
        )
        assert result.timed_out
        assert result.exit_code == runner.TIMEOUT_EXIT
        child, worker = _new_retained_owner(baseline)
        _assert_pipes_closed(child)
        assert child.owned.exit_code() is None
    finally:
        fault.released.set()
    assert child.done.wait(3)
    worker.join(3)
    assert not worker.is_alive()
    assert child.stopped
    assert child.owned._pidfd is None


class _SupervisorRefused:
    """Refuses the handle's supervisor thread and records the child and the cleanup order."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, failure: BaseException) -> None:
        self.children: list[runner._Child] = []
        self.order: list[str] = []
        start = threading.Thread.start
        init = runner.ProcessHandle.__init__
        close = ProcessStreams.close
        discard = runner.discard

        def refused(thread: threading.Thread) -> None:
            if thread.name.startswith("skm-process-"):
                raise failure
            start(thread)

        def recording_init(handle: runner.ProcessHandle, child: runner._Child) -> None:
            self.children.append(child)
            init(handle, child)

        def recording_close(streams: ProcessStreams) -> None:
            self.order.append("streams")
            close(streams)

        def recording_discard(*args: object) -> None:
            self.order.append("discard")
            discard(*args)  # type: ignore[arg-type]

        monkeypatch.setattr(threading.Thread, "start", refused)
        monkeypatch.setattr(runner.ProcessHandle, "__init__", recording_init)
        monkeypatch.setattr(ProcessStreams, "close", recording_close)
        monkeypatch.setattr(runner, "discard", recording_discard)


def _spawn_blocked(tmp_path: Path) -> None:
    runner.spawn(
        _argv("import signal; signal.pause()"),
        cwd=tmp_path,
        env={},
        on_stdout=lambda data: None,
        on_stderr=lambda data: None,
    )


def test_failed_supervisor_start_closes_the_streams_before_the_discard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # In the old order the discard closed the files first, so the selector could not read their
    # numbers any more and a false "I/O operation on closed file" note reached the caller.
    primary = RuntimeError("can't start new thread")
    fault = _SupervisorRefused(monkeypatch, primary)
    with pytest.raises(RuntimeError, match="can't start new thread") as caught:
        _spawn_blocked(tmp_path)
    assert caught.value is primary
    assert fault.order == ["streams", "discard"]
    assert "pipe cleanup failed" not in " ".join(getattr(primary, "__notes__", ()))
    child = fault.children[0]
    assert child.streams.files == {}
    assert child.streams.selector.get_map() is None
    _assert_pipes_closed(child)
    assert child.owned._pidfd is None
    assert identity_of(child.proc.pid) is None


@pytest.mark.parametrize("primary_type", [RuntimeError, _UnnoteableRuntimeError])
def test_failed_stream_close_cannot_skip_the_discard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, primary_type: type[RuntimeError]
) -> None:
    primary = primary_type("can't start new thread")
    fault = _SupervisorRefused(monkeypatch, primary)

    def failed_close(streams: ProcessStreams) -> None:
        fault.order.append("streams")
        raise OSError(errno.EIO, "pipe close secondary")

    monkeypatch.setattr(ProcessStreams, "close", failed_close)
    with pytest.raises(RuntimeError, match="can't start new thread") as caught:
        _spawn_blocked(tmp_path)
    assert caught.value is primary
    if primary_type is RuntimeError:
        assert "pipe close secondary" in " ".join(primary.__notes__)
    assert fault.order == ["streams", "discard"]
    child = fault.children[0]
    _assert_pipes_closed(child)
    assert child.owned._pidfd is None
    assert identity_of(child.proc.pid) is None


def test_failed_supervisor_start_retains_a_child_the_discard_cannot_confirm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = _UnnoteableRuntimeError("can't start new thread")
    supervisor = _SupervisorRefused(monkeypatch, primary)
    fault = _FailedCleanup(monkeypatch)
    reap = OwnedProcess.reap

    def pending_reap(owned: OwnedProcess, timeout: float = 0) -> int | None:
        return reap(owned, timeout) if fault.released.is_set() else None

    monkeypatch.setattr(OwnedProcess, "reap", pending_reap)
    monkeypatch.setattr(ownership, "_ABORT_SECONDS", 0.05)
    try:
        with pytest.raises(RuntimeError, match="can't start new thread") as caught:
            _spawn_blocked(tmp_path)
        assert caught.value is primary
        child = supervisor.children[0]
        _assert_pipes_closed(child)
        gc.collect()
        with ownership._retained_guard:
            assert child.owned in ownership._retained
        assert child.owned.exit_code() is None
    finally:
        fault.released.set()
    worker = next(t for t in threading.enumerate() if t.name == f"skm-discard-{child.proc.pid}")
    worker.join(3)
    assert not worker.is_alive()
    assert child.owned._pidfd is None
    assert identity_of(child.proc.pid) is None


class _RefusingClose:
    """A pipe whose close closes it and then fails, with the failure the test chooses."""

    def __init__(self, failure: BaseException) -> None:
        self.failure = failure
        self.read_end, self.write_end = os.pipe()
        self.pipe = os.fdopen(self.read_end, "rb", 0)

    def fileno(self) -> int:
        return self.pipe.fileno()

    def close(self) -> None:
        self.pipe.close()
        os.close(self.write_end)
        raise self.failure


def _refusing_pipes(*failures: BaseException) -> ChildPipes:
    stdout, stderr = (_RefusingClose(failure) for failure in failures)
    return ChildPipes(0, stdout, stdout, stderr)  # type: ignore[arg-type]


def test_stream_close_with_a_refused_note_closes_every_descriptor() -> None:
    first = _UnnoteableOSError(errno.EIO, "first close failed")
    second = OSError(errno.EIO, "second close failed")
    pipes = _refusing_pipes(first, second)
    streams = ProcessStreams(
        pipes, lambda data: None, lambda data: None, line_mode=False, stdin=None, manage_stdin=False
    )
    with pytest.raises(_UnnoteableOSError) as caught:
        streams.close()
    assert caught.value is first
    assert streams.files == {}
    assert streams.selector.get_map() is None
    assert pipes.stdout.pipe.closed  # type: ignore[attr-defined]
    assert pipes.stderr.pipe.closed  # type: ignore[attr-defined]


def test_stream_setup_failure_stays_primary_when_its_note_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    primary = _UnnoteableOSError(errno.EIO, "setup failed")
    pipes = _refusing_pipes(OSError(errno.EIO, "close failed"), OSError(errno.EIO, "close failed"))

    def refused(fd: int, blocking: bool) -> None:
        raise primary

    with monkeypatch.context() as patch:
        patch.setattr(os, "set_blocking", refused)
        with pytest.raises(_UnnoteableOSError) as caught:
            ProcessStreams(
                pipes, lambda data: None, lambda data: None, line_mode=False, stdin=None, manage_stdin=False
            )
    assert caught.value is primary
    assert pipes.stdout.pipe.closed  # type: ignore[attr-defined]
    with suppress(OSError):
        pipes.stderr.close()


def test_deferred_cleanup_without_worker_raises_instead_of_a_plain_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A result would imply that cleanup goes on behind it, and no worker is running it.
    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    start = threading.Thread.start
    signal_group = OwnedProcess.signal_group
    released = threading.Event()

    def refused(thread: threading.Thread) -> None:
        if thread.name.startswith("skm-reap-"):
            raise RuntimeError("can't start new thread")
        start(thread)

    def held_back(owned: OwnedProcess, sig: int) -> bool:
        return signal_group(owned, sig) if sig == 0 or released.is_set() else True

    monkeypatch.setattr(threading.Thread, "start", refused)
    monkeypatch.setattr(OwnedProcess, "signal_group", held_back)
    monkeypatch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)
    with pytest.raises(RuntimeError, match="can't start new thread") as caught:
        runner.run(
            _argv("import signal; signal.pause()"),
            cwd=tmp_path,
            env={},
            timeout_seconds=0.05,
            grace_seconds=0,
        )
    notes = " ".join(caught.value.__notes__)
    assert "cleanup_worker_not_running" in notes
    assert f"exit code observed before cleanup: {runner.TIMEOUT_EXIT}" in notes
    with runner._pending_guard:
        retained = runner._pending_children - baseline
        assert len(retained) == 1
        child = retained.pop()
        assert (child.identity, "can't start new thread") in runner._cleanup_failures
    assert child.owned._pidfd is not None
    assert child.owned.exit_code() is None
    released.set()
    monkeypatch.setattr(threading.Thread, "start", start)
    # The next start takes the cleanup over without being asked to.
    assert runner.run(["/bin/true"], cwd=tmp_path, env={}, timeout_seconds=3).exit_code == 0
    assert child.done.wait(3)
    assert child.stopped
    assert child.status == -signal.SIGKILL
    assert child.owned._pidfd is None
    assert ownership._unattended == {}


def test_lost_status_without_worker_says_no_cleanup_is_running(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    start = threading.Thread.start
    fault = _FailedCleanup(monkeypatch)
    exit_code = OwnedProcess.exit_code
    lost: list[int] = []

    def lost_status(owned: OwnedProcess) -> int | None:
        if lost:
            raise ChildProcessError(errno.ECHILD, "status went elsewhere")
        return exit_code(owned)

    def timed_out_send(child: runner._Child, sig: int) -> bool:
        lost.append(sig)
        raise PermissionError(errno.EPERM, "signal delivery denied")

    def refused(thread: threading.Thread) -> None:
        if thread.name.startswith("skm-reap-"):
            raise RuntimeError("can't start new thread")
        start(thread)

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    with monkeypatch.context() as patch:
        patch.setattr(OwnedProcess, "exit_code", lost_status)
        patch.setattr(runner._Child, "send", timed_out_send)
        patch.setattr(threading.Thread, "start", refused)
        with pytest.raises(ProcessLookupError, match="process_status_unknown") as caught:
            runner.run(
                _argv("import signal; signal.pause()"),
                cwd=tmp_path,
                env={},
                timeout_seconds=0.05,
                grace_seconds=0,
            )
    assert "cleanup_worker_not_running" in " ".join(caught.value.__notes__)
    with runner._pending_guard:
        retained = runner._pending_children - baseline
    assert len(retained) == 1
    child = retained.pop()
    fault.released.set()
    # The status is unknown for this child, yet the pidfd finishes the group.
    assert ownership.recover_cleanups() == ()
    assert child.done.wait(3)
    assert not child.owned.group_alive()


@pytest.mark.parametrize("cached_exit", [False, True])
def test_timeout_cleanup_reports_status_already_known_lost(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reap_orphans: list[int], cached_exit: bool
) -> None:
    # The deadline passes first. The leader then exits, a foreign waiter consumes its status, and a
    # surviving member keeps the group alive past the kill wait: cleanup ends in _CleanupPending.
    code = """
import os,signal,time
from pathlib import Path
if os.fork()==0:
    Path('member').write_text(str(os.getpid()))
    while True: signal.pause()
while not (Path('member').exists() and Path('deadline').exists()): time.sleep(.001)
"""
    leader_exited = runner._Child.leader_exited
    signal_group = OwnedProcess.signal_group
    released = threading.Event()
    foreign: list[int] = []

    def foreign_reap(child: runner._Child) -> None:
        pid, status = os.waitpid(child.proc.pid, 0)
        assert pid == child.proc.pid
        foreign.append(os.waitstatus_to_exitcode(status))

    def probe(child: runner._Child) -> bool:
        if foreign:
            return leader_exited(child)
        if not cached_exit and os.waitid(os.P_PID, child.proc.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT):
            foreign_reap(child)
        exited = leader_exited(child)
        if exited and cached_exit:
            assert child.leader_code == 0
            foreign_reap(child)
        return exited

    def held_back(owned: OwnedProcess, sig: int) -> bool:
        if sig == signal.SIGTERM:
            # The leader exits only once the deadline has passed, however slowly it started.
            (tmp_path / "deadline").touch()
        return signal_group(owned, sig) if sig == 0 or released.is_set() else True

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    monkeypatch.setattr(runner._Child, "leader_exited", probe)
    monkeypatch.setattr(OwnedProcess, "signal_group", held_back)
    monkeypatch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)
    try:
        with pytest.raises(ProcessLookupError, match="process_status_unknown"):
            runner.run(_argv(code), cwd=tmp_path, env={}, timeout_seconds=0.1, grace_seconds=0.5)
        child, worker = _new_retained_owner(baseline)
        assert foreign == [0]
        assert child.timed_out
        assert child.status is None
        # Cleanup is retained, not skipped: the member stays owned until the group is empty.
        member = identity_of(int((tmp_path / "member").read_text()))
        assert member is not None
        assert is_same_process(member)
        assert child.owned._pidfd is not None
        released.set()
        _assert_lost_owner_finished(child, worker)
        assert not is_same_process(member)
    finally:
        released.set()
        if (tmp_path / "member").exists():
            reap_orphans.append(int((tmp_path / "member").read_text()))


def test_signal_failure_after_timeout_does_not_hide_a_lost_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fault = _FailedCleanup(monkeypatch)
    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    exit_code = OwnedProcess.exit_code
    lost: list[int] = []

    def lost_status(owned: OwnedProcess) -> int | None:
        if lost:
            raise ChildProcessError(errno.ECHILD, "status went elsewhere")
        return exit_code(owned)

    def timed_out_send(child: runner._Child, sig: int) -> bool:
        lost.append(sig)
        raise PermissionError(errno.EPERM, "signal delivery denied")

    monkeypatch.setattr(OwnedProcess, "exit_code", lost_status)
    monkeypatch.setattr(runner._Child, "send", timed_out_send)
    try:
        with pytest.raises(ProcessLookupError, match="process_status_unknown"):
            runner.run(
                _argv("import signal; signal.pause()"),
                cwd=tmp_path,
                env={},
                timeout_seconds=0.05,
                grace_seconds=0,
            )
        child, worker = _new_retained_owner(baseline)
        assert child.timed_out
        assert child.owned._pidfd is not None
    finally:
        monkeypatch.undo()
        fault.released.set()
    # The owner's pidfd still finishes the live group after the faults end.
    assert child.owned.signal_group(signal.SIGKILL)
    assert child.done.wait(3)
    worker.join(3)
    assert not worker.is_alive()


@pytest.mark.parametrize("signal_denied", [False, True])
def test_timeout_retains_ownership_until_deferred_reap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signal_denied: bool
) -> None:
    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    code = "import signal; print('ready',flush=True); signal.pause()"
    child: runner._Child | None = None
    worker: threading.Thread | None = None
    started = time.monotonic()

    def deliver(owned: OwnedProcess, sig: int) -> bool:
        if signal_denied and sig != 0:
            raise PermissionError("signal delivery denied")
        return True

    try:
        with monkeypatch.context() as patch:
            patch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)
            patch.setattr(OwnedProcess, "signal_group", deliver)
            patch.setattr(OwnedProcess, "group_alive", _always_alive)
            result = runner.run(_argv(code), cwd=tmp_path, env={}, timeout_seconds=0.05, grace_seconds=0)
            with runner._pending_guard:
                retained = runner._pending_children - baseline
            assert len(retained) == 1
            child = retained.pop()
            assert result.exit_code == runner.TIMEOUT_EXIT
            assert result.timed_out
            assert time.monotonic() - started < 1
            assert child.held
            assert not child.stopped
            assert not child.done.is_set()
            assert child.status is None
            assert identity_of(child.proc.pid) == child.identity
            for pipe in (child.proc.stdin, child.proc.stdout, child.proc.stderr):
                assert pipe.closed
            assert child.streams.selector.get_map() is None
            worker = next(t for t in threading.enumerate() if t.name == f"skm-reap-{child.proc.pid}")
    finally:
        # Restore real signal delivery even when assertions fail; the retained owner reaps.
        if child is None:
            with runner._pending_guard:
                retained = runner._pending_children - baseline
            child = next(iter(retained), None)
        if child is not None:
            child.owned.signal_group(signal.SIGKILL)
            assert child.done.wait(3)
        if worker is not None:
            worker.join(3)
            assert not worker.is_alive()
    assert child is not None
    assert child.stopped
    assert not child.held
    assert child.status is not None
    assert identity_of(child.proc.pid) is None
    with runner._pending_guard:
        assert child not in runner._pending_children


@pytest.mark.skipif(sys.platform != "linux", reason="Linux PR_SET_NAME raw comm")
@pytest.mark.parametrize("named_child", [False, True])
def test_raw_comm_on_foreign_and_owned_processes(tmp_path: Path, named_child: bool) -> None:
    raw_name = "import ctypes; assert ctypes.CDLL(None).prctl(15, b'\\xff\\xfe)\\n(name', 0, 0, 0)==0; "
    ready = threading.Event()
    foreign = runner.spawn(
        _argv(raw_name + "import signal; print('ready',flush=True); signal.pause()"),
        cwd=tmp_path,
        env={},
        on_stdout=lambda data: ready.set(),
        on_stderr=lambda data: None,
    )
    handle: runner.ProcessHandle | None = None
    try:
        assert ready.wait(30)
        assert is_same_process(foreign.identity)
        prefix = raw_name if named_child else ""
        assert _run(tmp_path, prefix + "print('ok')").exit_code == 0
        child_ready = threading.Event()
        handle = runner.spawn(
            _argv(prefix + "import signal; print('ready',flush=True); signal.pause()"),
            cwd=tmp_path,
            env={},
            on_stdout=lambda data: child_ready.set(),
            on_stderr=lambda data: None,
        )
        assert child_ready.wait(30)
        assert handle.terminate(grace_seconds=0.01).exited
        assert handle.wait(0) is not None
        assert not group_alive(handle.pgid)
        assert identity_of(handle.pid) is None
    finally:
        for process in (handle, foreign):
            if process is not None:
                process.kill()
                process.wait(3)


@pytest.mark.parametrize("close_fails", [False, True])
def test_termination_between_owned_reap_and_pipe_close(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    close_fails: bool,
    request: pytest.FixtureRequest,
) -> None:
    ready = threading.Event()
    handle = runner.spawn(
        _argv(
            "import signal; signal.signal(signal.SIGINT,signal.SIG_IGN); "
            "signal.signal(signal.SIGTERM,signal.SIG_IGN); print('ready',flush=True); signal.pause()"
        ),
        cwd=tmp_path,
        env={},
        on_stdout=lambda data: ready.set(),
        on_stderr=lambda data: None,
    )
    reaped, release = threading.Event(), threading.Event()
    close = runner._Child._close
    error = OSError(errno.EIO, "close failed after owned reap")

    def cleanup() -> None:
        release.set()
        handle.kill()
        if close_fails and handle._child.error is error:
            with pytest.raises(OSError, match="close failed after owned reap") as caught:
                handle.wait(3)
            assert caught.value is error
        else:
            handle.wait(3)

    request.addfinalizer(cleanup)
    assert ready.wait(30)

    def blocked_close(child: runner._Child, primary: BaseException | None) -> None:
        if child is handle._child:
            reaped.set()
            assert release.wait(3)
        close(child, primary)
        if close_fails:
            raise error

    def expired_grace(seconds: float) -> bool:
        handle._child.send(signal.SIGKILL)
        assert reaped.wait(3)
        return False

    with monkeypatch.context() as patch, ThreadPoolExecutor(max_workers=1) as pool:
        patch.setattr(runner._Child, "_close", blocked_close)
        patch.setattr(handle, "_stopped_within", expired_grace)
        future = pool.submit(handle.terminate, grace_seconds=0)
        try:
            assert reaped.wait(3)
            assert not handle._child.held
            assert not handle._child.done.is_set()
            assert not group_alive(handle.pgid)
            handle.kill()
        finally:
            release.set()
        result = future.result(timeout=3)
    if close_fails:
        assert not result.exited
        assert result.reason
        assert "close failed after owned reap" in result.reason
        assert handle._child.error is error
        with pytest.raises(OSError, match="close failed after owned reap"):
            handle.wait(0)
        assert handle.terminate(grace_seconds=0) == result
    else:
        assert result.exited
        assert not result.ignored
        assert handle.terminate(grace_seconds=0) == result
        assert handle.wait(0) == -signal.SIGKILL


def test_external_reap_is_not_mistaken_for_owned_stop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ready = threading.Event()
    original = os.waitid

    def external_reap(idtype: int, ident: int, options: int) -> os.waitid_result | None:
        result = original(idtype, ident, options)
        if result is not None:
            os.waitpid(result.si_pid, 0)
            raise ChildProcessError
        return None

    with monkeypatch.context() as patch:
        patch.setattr(os, "waitid", external_reap)
        handle = runner.spawn(
            _argv("import sys; print('ready',flush=True); sys.stdin.read()"),
            cwd=tmp_path,
            env={},
            on_stdout=lambda data: ready.set(),
            on_stderr=lambda data: None,
        )
        assert ready.wait(30)
        handle.close_stdin()
        with pytest.raises(ProcessLookupError, match="process_status_unknown"):
            handle.wait(3)
        result = handle.terminate(grace_seconds=0)
        assert not result.exited
        assert result.reason is not None
        assert "process_status_unknown" in result.reason
    assert not handle._child.stopped
    assert handle._child.status is None
    assert identity_of(handle.pid) is None


def test_fork_handler_replaces_the_pending_state_and_keeps_the_old_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard = threading.Lock()
    guard.acquire()
    pending, failures = {object()}, deque([(object(), "foreign")], maxlen=128)
    with monkeypatch.context() as patch:
        patch.setattr(runner, "_pending_guard", guard)
        patch.setattr(runner, "_pending_children", pending)
        patch.setattr(runner, "_cleanup_failures", failures)
        patch.setattr(runner, "_inherited", [])
        runner._after_fork_in_child()
        assert not runner._pending_guard.locked()
        assert runner._pending_children == set()
        assert not runner._cleanup_failures
        assert runner._cleanup_failures.maxlen == 128
        # Dropped here they would run destructors of the callbacks these children hold.
        assert runner._inherited == [pending]


def _new_retained_owner(baseline: set[runner._Child]) -> tuple[runner._Child, threading.Thread]:
    with runner._pending_guard:
        retained = runner._pending_children - baseline
    assert len(retained) == 1
    child = retained.pop()
    worker = next(t for t in threading.enumerate() if t.name == f"skm-reap-{child.proc.pid}")
    return child, worker


def _assert_lost_owner_finished(child: runner._Child, worker: threading.Thread) -> None:
    assert child.done.wait(2)
    worker.join(2)
    assert not worker.is_alive()
    assert not child.held
    assert not child.stopped
    assert child.status is None
    assert isinstance(child.error, ProcessLookupError)
    assert "process_status_unknown" in str(child.error)
    with runner._pending_guard:
        assert child not in runner._pending_children
        assert (child.identity, str(child.error)) in runner._cleanup_failures


@pytest.mark.parametrize("exit_code", [0, 7])
def test_completed_leader_with_zero_cleanup_grace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    child: runner._Child | None = None
    worker: threading.Thread | None = None
    try:
        with monkeypatch.context() as patch:
            patch.setattr(OwnedProcess, "signal_group", _no_delivery)
            patch.setattr(OwnedProcess, "group_alive", _always_alive)
            patch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)
            result = runner.run(
                _argv(f"import os; os.write(1,b'tail'); os._exit({exit_code})"),
                cwd=tmp_path,
                env={},
                timeout_seconds=3,
                grace_seconds=0,
            )
            child, worker = _new_retained_owner(baseline)
            assert not result.timed_out
            assert result.exit_code == exit_code
            assert result.stdout == b"tail"
            assert result.duration_seconds < 1
    finally:
        if child is None:
            with runner._pending_guard:
                retained = runner._pending_children - baseline
            child = next(iter(retained), None)
        if child is not None:
            assert child.done.wait(3)
        if worker is not None:
            worker.join(3)
            assert not worker.is_alive()


def _stamp_leader_exit(patch: pytest.MonkeyPatch) -> list[float]:
    """Record when the runner first observes the leader's exit."""
    observe = OwnedProcess.exit_code
    seen: list[float] = []

    def stamped(owned: OwnedProcess) -> int | None:
        code = observe(owned)
        if code is not None and not seen:
            seen.append(time.monotonic())
        return code

    patch.setattr(OwnedProcess, "exit_code", stamped)
    return seen


def _assert_kill_escalation(
    term: float, kills: list[float], returned: float, exit_seen: list[float], grace: float, kill_grace: float
) -> None:
    # The phase clock is sampled before each identity probe/signal callback.
    escalations = [stamp for stamp in kills if stamp - term >= grace - 0.005]
    assert escalations
    assert returned - escalations[0] >= kill_grace - 0.005
    # A slow leader may exit after the deadline: its group kill is immediate, never early.
    assert exit_seen
    assert all(stamp >= exit_seen[0] for stamp in kills if stamp < escalations[0])


@pytest.mark.parametrize("exit_code", [0, 7, -signal.SIGTERM])
@pytest.mark.parametrize("deadline", [0.08, 30.0])
def test_leader_status_deadline_and_cleanup_are_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int, deadline: float
) -> None:
    grace, kill_grace = 0.2, 0.4
    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    child: runner._Child | None = None
    worker: threading.Thread | None = None
    signals: list[tuple[int, float]] = []
    finish = f"os._exit({exit_code})" if exit_code >= 0 else f"os.kill(os.getpid(), {-exit_code})"
    code = "import os; os.write(1,b'status\\n'); " + finish

    def record(owned: OwnedProcess, sig: int) -> bool:
        signals.append((sig, time.monotonic()))
        return True

    try:
        with monkeypatch.context() as patch:
            patch.setattr(runner, "_KILL_WAIT_SECONDS", kill_grace)
            patch.setattr(OwnedProcess, "signal_group", record)
            patch.setattr(OwnedProcess, "group_alive", _always_alive)
            exit_seen = _stamp_leader_exit(patch)
            result = runner.run(
                _argv(code), cwd=tmp_path, env={}, timeout_seconds=deadline, grace_seconds=grace
            )
            returned = time.monotonic()
            child, worker = _new_retained_owner(baseline)
            assert child.held
            assert not child.stopped
            assert child.status is None
            assert child._leader_code == exit_code
            assert result.stdout == b"status\n"
            assert result.signal == (-exit_code if exit_code < 0 else None)
            before_return = [(sig, stamp) for sig, stamp in signals if stamp <= returned]
            terms = [stamp for sig, stamp in before_return if sig == signal.SIGTERM]
            if deadline > grace + kill_grace:
                assert not result.timed_out
                assert result.exit_code == exit_code
                assert not terms
                assert result.duration_seconds >= grace
                assert result.duration_seconds < deadline
            else:
                assert result.timed_out
                assert result.exit_code == runner.TIMEOUT_EXIT
                assert len(terms) == 1
                assert terms[0] - child.started >= deadline
                kills = [stamp for sig, stamp in before_return if sig == signal.SIGKILL and stamp > terms[0]]
                _assert_kill_escalation(terms[0], kills, returned, exit_seen, grace, kill_grace)
                assert result.duration_seconds < 2
    finally:
        if child is None:
            with runner._pending_guard:
                retained = runner._pending_children - baseline
            child = next(iter(retained), None)
        if child is not None:
            assert child.done.wait(3)
        if worker is not None:
            worker.join(3)
            assert not worker.is_alive()
    assert child is not None
    assert child.stopped
    assert child.status == exit_code
    assert identity_of(child.proc.pid) is None
    with runner._pending_guard:
        assert child not in runner._pending_children


@pytest.mark.parametrize("cached_exit", [False, True])
def test_deferred_reaper_finishes_cleanup_after_external_reap(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    reap_orphans: list[int],
    cached_exit: bool,
) -> None:
    code = """
import os,signal,time
from pathlib import Path
if os.fork()==0:
    signal.signal(signal.SIGINT,signal.SIG_IGN)
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    Path('descendant').write_text(str(os.getpid()))
    with open('writes','ab',buffering=0) as stream:
        while True:
            stream.write(b'x')
            time.sleep(.005)
while not Path('descendant').exists() or not Path('descendant').stat().st_size: time.sleep(.001)
print('ready',flush=True)
while True: signal.pause()
"""
    original = runner._Child._reap_step
    release = threading.Event()
    child: runner._Child | None = None
    worker: threading.Thread | None = None
    signal_group = OwnedProcess.signal_group
    with runner._pending_guard:
        baseline = runner._pending_children.copy()

    def gated(child: runner._Child) -> bool:
        assert release.wait(3)
        return original(child)

    def undelivered_until_release(owned: OwnedProcess, sig: int) -> bool:
        return signal_group(owned, sig) if release.is_set() or sig == 0 else True

    try:
        with monkeypatch.context() as patch:
            patch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)
            patch.setattr(OwnedProcess, "signal_group", undelivered_until_release)
            patch.setattr(runner._Child, "_reap_step", gated)
            result = runner.run(_argv(code), cwd=tmp_path, env={}, timeout_seconds=0.4, grace_seconds=0.01)
            assert result.timed_out
            assert result.exit_code == runner.TIMEOUT_EXIT
            child, worker = _new_retained_owner(baseline)
            assert child.held
            assert not child._exited
            os.kill(child.proc.pid, signal.SIGKILL)
            if cached_exit:
                until = time.monotonic() + 2
                while not child.leader_exited():
                    assert time.monotonic() < until
                    CancelSource().token.wait(0.005)
                assert child._leader_code == -signal.SIGKILL
            pid, status = os.waitpid(child.proc.pid, 0)
            assert pid == child.proc.pid
            assert os.waitstatus_to_exitcode(status) == -signal.SIGKILL
            descendant = int((tmp_path / "descendant").read_text())
            assert group_alive(child.proc.pid)
            release.set()
            _assert_lost_owner_finished(child, worker)
        # The pidfd still names the group: the leftover writer is gone, the status stays unknown.
        current = identity_of(descendant)
        assert current is None or not is_same_process(current)
    finally:
        release.set()
        if child is None:
            with runner._pending_guard:
                retained = runner._pending_children - baseline
            child = next(iter(retained), None)
        if child is not None:
            assert child.done.wait(3)
        if worker is not None:
            worker.join(2)
        if (tmp_path / "descendant").exists():
            reap_orphans.append(int((tmp_path / "descendant").read_text()))


@pytest.mark.parametrize("exit_code", [0, 7])
@pytest.mark.parametrize("foreign", [False, True])
@pytest.mark.parametrize("api", ["run", "spawn"])
def test_foreign_reap_during_final_wait_is_never_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, api: str, foreign: bool, exit_code: int
) -> None:
    # A status consumed by a foreign waiter after exit observation stays unknown, never owned success.
    original = runner._Child._drain
    signal_group = OwnedProcess.signal_group
    signals: list[int] = []
    after_loss: list[int] = []

    def drain(child: runner._Child, timeout: float | None, grace: float) -> None:
        original(child, timeout, grace)
        assert child.leader_code == exit_code
        if foreign:
            pid, status = os.waitpid(child.proc.pid, 0)
            assert pid == child.proc.pid
            assert os.waitstatus_to_exitcode(status) == exit_code
        after_loss.append(len(signals))

    def record(owned: OwnedProcess, sig: int) -> bool:
        signals.append(sig)
        return signal_group(owned, sig)

    monkeypatch.setattr(runner._Child, "_drain", drain)
    monkeypatch.setattr(OwnedProcess, "signal_group", record)
    code = f"import os; os._exit({exit_code})"
    if api == "run":
        if not foreign:
            result = _run(tmp_path, code)
            assert result.exit_code == exit_code
            assert result.signal is None
            assert not result.timed_out
        else:
            with pytest.raises(ProcessLookupError, match="process_status_unknown"):
                _run(tmp_path, code)
    else:
        handle = runner.spawn(
            _argv(code), cwd=tmp_path, env={}, on_stdout=lambda data: None, on_stderr=lambda data: None
        )
        if not foreign:
            assert handle.wait(3) == exit_code
            assert handle._child.stopped
            assert handle.terminate(grace_seconds=0).exited
        else:
            with pytest.raises(ProcessLookupError, match="process_status_unknown"):
                handle.wait(3)
            assert not handle._child.stopped
            assert not handle._child.held
            assert handle._child.status is None
            assert not handle.terminate(grace_seconds=0).exited
    assert len(after_loss) == 1


@pytest.mark.parametrize("exit_code", [0, 7])
def test_deferred_reaper_foreign_reap_after_empty_group_is_not_stopped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exit_code: int
) -> None:
    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    original = runner._Child._reap_step
    release = threading.Event()
    foreign: list[int] = []
    child: runner._Child | None = None
    worker: threading.Thread | None = None

    def gated(child: runner._Child) -> bool:
        assert release.wait(3)
        return original(child)

    def group_probe(owned: OwnedProcess) -> bool:
        if not release.is_set():
            return True
        if not foreign:
            # A foreign waiter consumes the status between the empty-group proof and the reap.
            pid, status = os.waitpid(owned.pid, 0)
            assert pid == owned.pid
            foreign.append(os.waitstatus_to_exitcode(status))
        return False

    try:
        with monkeypatch.context() as patch:
            patch.setattr(OwnedProcess, "signal_group", _no_delivery)
            patch.setattr(OwnedProcess, "group_alive", group_probe)
            patch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)
            patch.setattr(runner._Child, "_reap_step", gated)
            result = runner.run(
                _argv(f"import os; os._exit({exit_code})"),
                cwd=tmp_path,
                env={},
                timeout_seconds=3,
                grace_seconds=0,
            )
            assert result.exit_code == exit_code
            assert not result.timed_out
            child, worker = _new_retained_owner(baseline)
            assert child.held
            release.set()
            _assert_lost_owner_finished(child, worker)
        assert foreign == [exit_code]
        assert child.owned._pidfd is None
    finally:
        release.set()
        if child is None:
            with runner._pending_guard:
                retained = runner._pending_children - baseline
            child = next(iter(retained), None)
        if child is not None:
            assert child.done.wait(3)
        if worker is not None:
            worker.join(2)
