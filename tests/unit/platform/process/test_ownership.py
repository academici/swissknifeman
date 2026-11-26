import ctypes
import errno
import gc
import json
import os
import signal
import socket
import stat
import sys
import threading
import time
from collections.abc import Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from pathlib import Path
from select import select
from typing import IO, override
from unittest.mock import Mock

import pytest

from skm.platform.process import ownership, runner
from skm.platform.process.identity import ProcessIdentity, identity_of, is_same_process
from skm.platform.process.ownership import OwnedProcess, OwnershipUnavailable


def _argv(code: str) -> list[str]:
    return [sys.executable, "-c", code]


def _ignore(data: bytes) -> None:
    pass


def _run(tmp_path: Path, code: str, **env: str) -> runner.ProcessResult:
    return runner.run(_argv(code), cwd=tmp_path, env=env, timeout_seconds=5)


@pytest.fixture
def no_spawn(monkeypatch: pytest.MonkeyPatch) -> Generator[list[object]]:
    calls: list[object] = []

    def refuse(*args: object, **kwargs: object) -> None:
        calls.append(args)
        raise AssertionError("a child was started")

    monkeypatch.setattr(ownership.subprocess, "_fork_exec", refuse)
    monkeypatch.setattr(ownership, "_fork_exec_signature", lambda: ownership._FORK_EXEC_PARAMETERS)
    yield calls
    assert not calls


def _cleanup_test_launch(pipes: ownership.ChildPipes, owned: OwnedProcess) -> None:
    with suppress(ChildProcessError):
        owned.signal_group(signal.SIGKILL)
        owned.reap(5)
    owned.close()
    for pipe in (pipes.stdin, pipes.stdout, pipes.stderr):
        pipe.close()


def _reap_adopted_child(pidfd: int) -> int:
    # The test holds its own pidfd for the fixture child. SKM does not acquire one by adoption.
    assert select([pidfd], [], [], 5)[0], "test child did not exit"
    status = os.waitid(os.P_PIDFD, pidfd, os.WEXITED | os.WNOHANG)
    assert status is not None
    assert status.si_code == os.CLD_EXITED
    return status.si_status


def test_parallel_launches_keep_pidfds_and_start_ticks_paired(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first_binding = threading.Event()
    both_binding = threading.Barrier(2, timeout=10)
    original = ownership._bind

    def bind(channel: socket.socket, pid: int) -> OwnedProcess:
        first_binding.set()
        both_binding.wait()
        return original(channel, pid)

    def launch(code: int) -> tuple[ownership.ChildPipes, OwnedProcess]:
        argv = _argv(f"import sys; sys.stdin.buffer.read(); sys.exit({code})")
        return ownership.launch(tuple(argv), cwd=tmp_path, env={})

    monkeypatch.setattr(ownership, "_bind", bind)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(launch, 23)
        assert first_binding.wait(5)
        # Hold the first launch at bind while the second bootstrap starts in a different kernel tick.
        time.sleep(2 / os.sysconf("SC_CLK_TCK"))
        second = pool.submit(launch, 42)

    try:
        first_pipes, first_owned = first.result()
        second_pipes, second_owned = second.result()
        assert first_owned.pid != second_owned.pid
        assert first_owned._pidfd != second_owned._pidfd
        assert first_owned.identity.start_ticks != second_owned.identity.start_ticks
        for pipes, owned in ((first_pipes, first_owned), (second_pipes, second_owned)):
            assert owned._pidfd is not None
            assert ownership._pidfd_target(owned._pidfd) == pipes.pid == owned.identity.pid
            assert owned.identity.start_ticks is not None
            assert owned.identity == identity_of(pipes.pid)

        assert first_owned.signal_group(signal.SIGTERM)
        assert first_owned.reap(5) == -signal.SIGTERM
        assert second_owned.exit_code() is None
        second_pipes.stdin.close()
        assert second_owned.reap(5) == 42
    finally:
        for attempt in (first, second):
            if attempt.exception() is None:
                _cleanup_test_launch(*attempt.result())


def test_owner_crash_reparents_live_child_and_preserves_diagnostic_identity(tmp_path: Path) -> None:
    target = """
import os, time
from pathlib import Path
parent = os.getppid()
print(parent, flush=True)
deadline = time.monotonic() + 10
while os.getppid() == parent and time.monotonic() < deadline:
    time.sleep(0.005)
Path('adopted-by').write_text(str(os.getppid()))
raise SystemExit(42)
"""
    owner = """
import json, os, signal, sys
from pathlib import Path
from select import select
from skm.platform.process.ownership import launch
pipes, owned = launch((sys.executable, '-c', sys.argv[1]), cwd=Path.cwd(), env={})
assert select([pipes.stdout], [], [], 5)[0]
assert int(pipes.stdout.readline()) == os.getpid()
print(json.dumps([os.getpid(), owned.identity.pid, owned.identity.start_ticks]), flush=True)
signal.raise_signal(signal.SIGKILL)
"""
    source = Path(__file__).resolve().parents[4] / "src"
    result = runner.run(
        [*_argv(owner), target], cwd=tmp_path, env={"PYTHONPATH": str(source)}, timeout_seconds=15
    )
    assert result.signal == signal.SIGKILL, result.stderr
    owner_pid, child_pid, start_ticks = json.loads(result.stdout)
    child_fd = os.pidfd_open(child_pid)
    try:
        adopted = identity_of(child_pid)
        assert _reap_adopted_child(child_fd) == 42
    finally:
        os.close(child_fd)
    assert adopted is not None
    assert start_ticks is not None
    assert (adopted.pid, adopted.start_ticks) == (child_pid, start_ticks)
    assert owner_pid != os.getpid()
    assert int((tmp_path / "adopted-by").read_text()) == os.getpid()


@pytest.fixture
def subreaper_initially_disabled() -> Generator[None]:
    libc = ctypes.CDLL(None, use_errno=True)
    prior = ctypes.c_int()
    assert libc.prctl(37, ctypes.byref(prior), 0, 0, 0) == 0  # PR_GET_CHILD_SUBREAPER
    assert libc.prctl(36, 0, 0, 0, 0) == 0  # PR_SET_CHILD_SUBREAPER
    try:
        yield
    finally:
        assert libc.prctl(36, prior.value, 0, 0, 0) == 0


def test_setsid_descendant_is_adopted_and_survives_group_cleanup(
    tmp_path: Path, subreaper_initially_disabled: None
) -> None:
    code = """
import os, signal, sys
if os.fork():
    signal.pause()
    os._exit(0)
os.setsid()
print(os.getpid(), flush=True)
sys.stdin.buffer.read()
print(os.getppid(), os.getsid(0), flush=True)
os._exit(42)
"""
    pipes, owned = ownership.launch(tuple(_argv(code)), cwd=tmp_path, env={})
    escaped_fd = None
    escaped_exit = None
    try:
        assert select([pipes.stdout], [], [], 5)[0]
        escaped_pid = int(pipes.stdout.readline())
        escaped_fd = os.pidfd_open(escaped_pid)
        assert owned.signal_group(signal.SIGTERM)
        assert owned.reap(5) == -signal.SIGTERM
        assert not owned.group_alive()
        assert not select([escaped_fd], [], [], 0)[0], "group signal reached the escaped child"
        pipes.stdin.close()
        assert select([pipes.stdout], [], [], 5)[0]
        assert pipes.stdout.readline().split() == [str(os.getpid()).encode(), str(escaped_pid).encode()]
    finally:
        _cleanup_test_launch(pipes, owned)
        if escaped_fd is not None:
            try:
                with suppress(ChildProcessError):
                    escaped_exit = _reap_adopted_child(escaped_fd)
            finally:
                os.close(escaped_fd)
    assert escaped_exit == 42


def test_target_holds_only_stdio_and_keeps_pid_and_session(tmp_path: Path) -> None:
    code = (
        "import json,os; "
        "print(json.dumps([sorted(os.listdir('/proc/self/fd')),os.getpid(),os.getpgrp(),os.getsid(0)]))"
    )
    fds, pid, group, session = json.loads(_run(tmp_path, code).stdout)
    # The extra entry is the descriptor os.listdir itself opened; no pidfd or socket leaks.
    assert len(fds) == 4
    assert fds[:3] == ["0", "1", "2"]
    assert pid == group == session


def test_target_receives_literal_bytes(tmp_path: Path) -> None:
    code = (
        "import json,os,sys; print(json.dumps("
        "[os.fsencode(sys.argv[1]).hex(),sys.argv[2],os.fsencode(os.environ['ODD']).hex()]))"
    )
    odd = os.fsdecode(b"\xff\xfe")
    result = runner.run([*_argv(code), odd, ""], cwd=tmp_path, env={"ODD": odd}, timeout_seconds=5)
    assert result.exit_code == 0, result.stderr
    assert json.loads(result.stdout) == ["fffe", "", "fffe"]


def test_target_gets_default_signal_dispositions(tmp_path: Path) -> None:
    # A shell reads what the exec left in the kernel; Python would ignore SIGPIPE again by itself.
    probe = runner.run(
        ["/bin/sh", "-c", "grep -E '^SigIgn' /proc/self/status"], cwd=tmp_path, env={}, timeout_seconds=5
    )
    assert probe.exit_code == 0
    ignored = int(probe.stdout.split()[1], 16)
    assert not ignored & (1 << (signal.SIGPIPE - 1))
    assert not ignored & (1 << (signal.SIGXFSZ - 1))


def test_path_lookup_uses_the_explicit_environment(tmp_path: Path) -> None:
    tool = tmp_path / "skm-owned-tool"
    tool.write_text("#!/bin/sh\necho found\n")
    tool.chmod(stat.S_IRWXU)
    result = runner.run([tool.name], cwd=tmp_path, env={"PATH": str(tmp_path)}, timeout_seconds=5)
    assert result.stdout == b"found\n"
    with pytest.raises(FileNotFoundError):
        runner.run([tool.name], cwd=tmp_path, env={"PATH": str(tmp_path / "absent")}, timeout_seconds=5)


def test_failed_exec_reports_errno_and_reaps_exactly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    denied = tmp_path / "not-executable"
    denied.write_text("")
    observed: list[OwnedProcess] = []
    original = ownership._hold

    def hold(owned: OwnedProcess) -> None:
        observed.append(owned)
        original(owned)

    monkeypatch.setattr(ownership, "_hold", hold)
    with pytest.raises(PermissionError) as caught:
        runner.run([str(denied)], cwd=tmp_path, env={}, timeout_seconds=5)
    assert caught.value.errno == errno.EACCES
    assert caught.value.filename == str(denied)
    assert identity_of(observed[0].pid) is None
    assert not observed[0].signal_group(0)


@pytest.fixture
def no_numeric_wait(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    # A call is recorded rather than performed, so even a late one cannot consume anything here.
    calls: list[str] = []
    for name in ("waitpid", "wait", "wait3", "wait4"):

        def record(*args: object, _name: str = name) -> tuple[int, int]:
            calls.append(_name)
            raise ChildProcessError(errno.ECHILD, "numeric wait refused by the test")

        monkeypatch.setattr(os, name, record)
    return calls


@pytest.mark.parametrize(
    ("make_cwd", "error"),
    [
        (lambda path: path / "absent", FileNotFoundError),
        (lambda path: path / "file", NotADirectoryError),
    ],
)
def test_bad_cwd_fails_with_an_owned_child_and_no_numeric_wait(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_numeric_wait: list[str],
    make_cwd: Callable[[Path], Path],
    error: type[OSError],
) -> None:
    # The failure now comes from the bound bootstrap, so the pidfd reaps it and no zombie stays.
    (tmp_path / "file").write_text("")
    marker = tmp_path / "target-ran"
    observed: list[OwnedProcess] = []
    original = ownership._hold

    def hold(owned: OwnedProcess) -> None:
        observed.append(owned)
        original(owned)

    monkeypatch.setattr(ownership, "_hold", hold)
    cwd = make_cwd(tmp_path)
    with pytest.raises(error) as caught:
        runner.run(["/bin/touch", str(marker)], cwd=cwd, env={}, timeout_seconds=5)
    assert no_numeric_wait == []
    assert caught.value.filename == str(cwd)
    assert not marker.exists()
    assert identity_of(observed[0].pid) is None
    assert observed[0]._pidfd is None


def test_exec_failure_of_the_interpreter_never_waits_by_number(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Executable by mode but not by the kernel, so the preflight passes and execve fails with ENOEXEC.
    interpreter = tmp_path / "not-an-interpreter"
    interpreter.write_bytes(b"\0\0\0\0")
    interpreter.chmod(stat.S_IRWXU)
    marker = tmp_path / "target-ran"
    started: list[int] = []
    fork_exec = ownership._fork_exec()

    def recorded(*args: object) -> int:
        started.append(fork_exec(*args))
        return started[-1]

    with monkeypatch.context() as patch:
        patch.setattr(sys, "executable", str(interpreter))
        patch.setattr(ownership, "_fork_exec_signature", lambda: ownership._FORK_EXEC_PARAMETERS)
        patch.setattr(ownership.subprocess, "_fork_exec", recorded)
        calls: list[str] = []
        patch.setattr(os, "waitpid", lambda *args: calls.append("waitpid"))
        with pytest.raises(OwnershipUnavailable, match="child sent no pidfd") as caught:
            runner.run(["/bin/touch", str(marker)], cwd=tmp_path, env={}, timeout_seconds=5)
    assert calls == []
    assert f":{errno.ENOEXEC:x}:" in " ".join(caught.value.__notes__)
    assert not marker.exists()
    # The status is still there for its real parent: nothing in the owner consumed it.
    pid, status = os.waitpid(started[0], 0)
    assert pid == started[0]
    assert os.waitstatus_to_exitcode(status) == 255


def test_missing_interpreter_refuses_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_spawn: list[object]
) -> None:
    monkeypatch.setattr(sys, "executable", str(tmp_path / "gone"))
    with pytest.raises(OwnershipUnavailable, match="no interpreter"):
        runner.run(["/bin/true"], cwd=tmp_path, env={}, timeout_seconds=1)


def test_unknown_fork_exec_parameters_refuse_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_spawn: list[object]
) -> None:
    # Both shapes a changed Python can leave: reordered parameters and no signature at all.
    for signature in ("$module, args, pass_fds, close_fds, /", None):
        monkeypatch.setattr(ownership, "_fork_exec_signature", lambda value=signature: value)
        with pytest.raises(OwnershipUnavailable, match="unknown fork_exec parameters"):
            runner.run(["/bin/true"], cwd=tmp_path, env={}, timeout_seconds=1)


def test_fork_exec_parameters_match_this_interpreter(monkeypatch: pytest.MonkeyPatch) -> None:
    assert ownership._fork_exec_signature() == ownership._FORK_EXEC_PARAMETERS
    monkeypatch.setattr(ownership.subprocess, "_fork_exec", lambda *args: 0)
    assert ownership._fork_exec_signature() is None


def test_fork_exec_arguments_follow_the_accepted_parameters() -> None:
    # Python 3.14 removed allow_vfork: one argument too many raises TypeError there instead of starting.
    parameters = ownership._FORK_EXEC_PARAMETERS.removesuffix(", /").split(", ")[1:]
    assert parameters[-1 - len(ownership._FORK_EXEC_TAIL)] == "preexec_fn"
    assert ("allow_vfork" in parameters) == (ownership._FORK_EXEC_TAIL == (True,))


def test_nul_in_cwd_refuses_before_spawn(tmp_path: Path, no_spawn: list[object]) -> None:
    with pytest.raises(ValueError, match="embedded null byte"):
        runner.run(["/bin/true"], cwd=Path("bad\0cwd"), env={}, timeout_seconds=1)


def test_owner_with_closed_stdio_still_binds(tmp_path: Path) -> None:
    # Fresh descriptors land on 0-2 here; fork_exec must still receive them above stdio.
    code = """
import os,sys
from pathlib import Path
from skm.platform.process.runner import run
log=os.dup(1)
os.close(0); os.close(1); os.close(2)
result=run(['/bin/sh','-c','echo ran'],cwd=Path.cwd(),env={},timeout_seconds=5)
os.write(log,result.stdout)
"""
    src = Path(ownership.__file__).parents[3]
    result = _run(tmp_path, code, PYTHONPATH=str(src))
    assert result.exit_code == 0, result.stderr
    assert result.stdout == b"ran\n"


def test_silent_failed_start_report_does_not_block(tmp_path: Path) -> None:
    read_end, write_end = os.pipe()
    try:
        primary = ValueError("primary")
        ownership._note_failed_start(read_end, primary)
        assert not hasattr(primary, "__notes__")
    finally:
        os.close(read_end)
        os.close(write_end)


@pytest.mark.parametrize("owner_cwd", [False, True])
@pytest.mark.parametrize("name", ["socket", "os", "marshal", "signal"])
def test_planted_module_in_cwd_cannot_run_in_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, owner_cwd: bool
) -> None:
    # The bootstrap starts in the owner's directory and moves to the target's: both are hostile.
    marker = tmp_path / "planted"
    (tmp_path / f"{name}.py").write_text(f"open({str(marker)!r}, 'w').close()\nraise SystemExit(99)\n")
    if owner_cwd:
        monkeypatch.chdir(tmp_path)
    result = runner.run(["/bin/sh", "-c", "echo ran"], cwd=tmp_path, env={}, timeout_seconds=5)
    assert result.stdout == b"ran\n"
    assert not marker.exists()


class _DiscardFault:
    """A real live target whose setup fails afterwards, with cleanup faults until released."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, *, signal_denied: bool, reap_pending: bool) -> None:
        self.released = threading.Event()
        self.started: list[OwnedProcess] = []
        self.primary = OSError(errno.EIO, "streams setup failed")
        signal_group, reap, hold = OwnedProcess.signal_group, OwnedProcess.reap, ownership._hold

        def faulty_signal(owned: OwnedProcess, sig: int) -> bool:
            if sig == 0 or self.released.is_set():
                return signal_group(owned, sig)
            if signal_denied:
                raise PermissionError(errno.EPERM, "signal delivery denied")
            return True

        def faulty_reap(owned: OwnedProcess, timeout: float = 0) -> int | None:
            return reap(owned, timeout) if self.released.is_set() else None

        def recording_hold(owned: OwnedProcess) -> None:
            self.started.append(owned)
            hold(owned)

        def failed_streams(*args: object, **kwargs: object) -> None:
            raise self.primary

        monkeypatch.setattr(OwnedProcess, "signal_group", faulty_signal)
        if reap_pending:
            monkeypatch.setattr(OwnedProcess, "reap", faulty_reap)
        monkeypatch.setattr(ownership, "_hold", recording_hold)
        monkeypatch.setattr(ownership, "_ABORT_SECONDS", 0.05)
        monkeypatch.setattr(runner, "ProcessStreams", failed_streams)


@pytest.mark.parametrize(
    ("signal_denied", "reap_pending", "reason"),
    [
        (True, False, "signal delivery denied"),
        (False, True, "child_reap_unconfirmed"),
        (True, True, "signal delivery denied"),
    ],
)
def test_discard_retains_live_child_until_cleanup_is_safe(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, signal_denied: bool, reap_pending: bool, reason: str
) -> None:
    fault = _DiscardFault(monkeypatch, signal_denied=signal_denied, reap_pending=reap_pending)
    try:
        with pytest.raises(OSError, match="streams setup failed") as caught:
            runner.spawn(
                _argv("import signal; signal.pause()"),
                cwd=tmp_path,
                env={},
                on_stdout=_ignore,
                on_stderr=_ignore,
            )
        assert caught.value is fault.primary
        assert reason in " ".join(fault.primary.__notes__)
        owned = fault.started[0]
        del caught
        gc.collect()
        # The failed start has no handle left, yet the pidfd of the live child stays open.
        with ownership._retained_guard:
            assert owned in ownership._retained
        assert owned._pidfd is not None
        assert owned.signal_group(0)
        assert identity_of(owned.pid) is not None
    finally:
        fault.released.set()
    worker = next(t for t in threading.enumerate() if t.name == f"skm-discard-{owned.pid}")
    worker.join(3)
    assert not worker.is_alive()
    assert owned._pidfd is None
    assert identity_of(owned.pid) is None
    with ownership._retained_guard:
        assert owned not in ownership._retained


def test_discard_keeps_ownership_when_the_worker_cannot_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fault = _DiscardFault(monkeypatch, signal_denied=True, reap_pending=True)
    start = threading.Thread.start

    def refused(thread: threading.Thread) -> None:
        if thread.name.startswith("skm-discard-"):
            raise RuntimeError("can't start new thread")
        start(thread)

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", refused)
        with pytest.raises(OSError, match="streams setup failed"):
            runner.spawn(
                _argv("import signal; signal.pause()"),
                cwd=tmp_path,
                env={},
                on_stdout=_ignore,
                on_stderr=_ignore,
            )
    notes = " ".join(fault.primary.__notes__)
    assert "can't start new thread" in notes
    # The failure says that nothing is cleaning up, and the cleanup stays listed.
    assert "cleanup_worker_not_running" in notes
    owned = fault.started[0]
    assert list(ownership._unattended.values()) == [f"skm-discard-{owned.pid}"]
    with ownership._retained_guard:
        assert owned in ownership._retained
    assert owned._pidfd is not None
    assert owned.exit_code() is None
    fault.released.set()
    # A recovery pass needs no thread: it kills the child now, and the new worker finishes the reap.
    assert ownership.recover_cleanups() == ()
    deadline = time.monotonic() + 30
    while owned._pidfd is not None:
        assert time.monotonic() < deadline
        threading.Event().wait(0.01)
    assert identity_of(owned.pid) is None
    with ownership._retained_guard:
        assert owned not in ownership._retained


def test_recovery_keeps_the_cleanup_listed_while_workers_stay_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fault = _DiscardFault(monkeypatch, signal_denied=True, reap_pending=True)
    start = threading.Thread.start

    def refused(thread: threading.Thread) -> None:
        if thread.name.startswith("skm-discard-"):
            raise RuntimeError("can't start new thread")
        start(thread)

    monkeypatch.setattr(threading.Thread, "start", refused)
    with pytest.raises(OSError, match="streams setup failed"):
        runner.spawn(
            _argv("import signal; signal.pause()"), cwd=tmp_path, env={}, on_stdout=_ignore, on_stderr=_ignore
        )
    owned = fault.started[0]
    name = f"skm-discard-{owned.pid}"
    assert ownership.recover_cleanups() == (name,)
    assert owned.exit_code() is None
    assert owned._pidfd is not None
    fault.released.set()
    # Threads stay refused, so the synchronous steps have to finish this on their own.
    deadline = time.monotonic() + 30
    while ownership.recover_cleanups():
        assert time.monotonic() < deadline
        threading.Event().wait(0.01)
    assert owned._pidfd is None
    assert identity_of(owned.pid) is None
    with ownership._retained_guard:
        assert owned not in ownership._retained


def test_worker_that_dies_returns_its_cleanup_to_the_list(monkeypatch: pytest.MonkeyPatch) -> None:
    finished: list[bool] = []
    reported: list[type[BaseException] | None] = []

    def step() -> bool:
        if not finished:
            finished.append(True)
            raise ValueError("cleanup step failed")
        return True

    monkeypatch.setattr(threading, "excepthook", lambda args: reported.append(args.exc_type))
    assert ownership.start_cleanup_worker(step, "skm-test-worker") is None
    deadline = time.monotonic() + 30
    while not reported:
        assert time.monotonic() < deadline
        threading.Event().wait(0.01)
    assert reported == [ValueError]
    assert ownership._unattended == {step: "skm-test-worker"}
    assert ownership.recover_cleanups() == ()
    assert ownership._unattended == {}


def test_recovery_survives_a_failing_step() -> None:
    attempts: list[int] = []

    def step() -> bool:
        attempts.append(1)
        if len(attempts) == 1:
            raise ValueError("cleanup step failed")
        return True

    with ownership._retained_guard:
        ownership._unattended[step] = "skm-test-step"
    assert ownership.recover_cleanups() == ("skm-test-step",)
    assert ownership.recover_cleanups() == ()
    assert len(attempts) == 2


def test_live_worker_gives_a_listed_cleanup_its_step(monkeypatch: pytest.MonkeyPatch) -> None:
    # Nobody calls recover_cleanups here: a worker that already runs needs no new thread for this.
    released = threading.Event()
    attempts: list[int] = []

    def waiting() -> bool:
        attempts.append(1)
        return True

    with ownership._retained_guard:
        ownership._unattended[waiting] = "skm-test-waiting"
    assert ownership.start_cleanup_worker(released.is_set, "skm-test-live") is None
    worker = next(t for t in threading.enumerate() if t.name == "skm-test-live")
    deadline = time.monotonic() + 30
    while ownership._unattended:
        assert time.monotonic() < deadline
        threading.Event().wait(0.01)
    released.set()
    worker.join(3)
    assert not worker.is_alive()
    assert attempts == [1]


def test_recovery_leaves_a_cleanup_adopted_during_its_step_alone() -> None:
    # The old code deleted the entry unconditionally, which raised KeyError out of launch.
    def step() -> bool:
        with ownership._retained_guard:
            del ownership._unattended[step]
        return False

    with ownership._retained_guard:
        ownership._unattended[step] = "skm-test-adopted"
    assert ownership.recover_cleanups() == ()
    assert not any(t.name == "skm-test-adopted" for t in threading.enumerate())


def test_adopt_cleanup_runs_a_listed_step_on_the_calling_thread() -> None:
    threads: list[threading.Thread] = []

    def step() -> bool:
        threads.append(threading.current_thread())
        return len(threads) == 2

    with ownership._retained_guard:
        ownership._unattended[step] = "skm-test-adopted"
    ownership.adopt_cleanup(step)
    assert threads == [threading.current_thread()] * 2
    assert ownership._unattended == {}
    # It is no longer listed, so a second adoption does nothing.
    ownership.adopt_cleanup(step)
    assert len(threads) == 2


def test_adopted_cleanup_that_fails_goes_back_on_the_list() -> None:
    def step() -> bool:
        raise ValueError("cleanup step failed")

    with ownership._retained_guard:
        ownership._unattended[step] = "skm-test-adopted"
    with pytest.raises(ValueError, match="cleanup step failed"):
        ownership.adopt_cleanup(step)
    assert ownership._unattended == {step: "skm-test-adopted"}
    with ownership._retained_guard:
        del ownership._unattended[step]


class _RecordedLog:
    def __init__(self, failure: BaseException | None = None) -> None:
        self.failure = failure
        self.events: list[tuple[str, str]] = []

    def _record(self, level: str, event: str) -> None:
        self.events.append((level, event))
        if self.failure is not None:
            raise self.failure

    def error(self, event: str, /) -> None:
        self._record("error", event)

    def info(self, event: str, /) -> None:
        self._record("info", event)


def test_lost_worker_is_logged_once_across_retries_and_once_when_recovered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    log = _RecordedLog()
    monkeypatch.setattr(ownership, "_log", log)
    start = threading.Thread.start
    released = threading.Event()

    def refused(thread: threading.Thread) -> None:
        if thread.name == "skm-test-refused":
            raise RuntimeError("can't start new thread")
        start(thread)

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", refused)
        assert ownership.start_cleanup_worker(released.is_set, "skm-test-refused") is not None
        for _ in range(3):
            assert ownership.recover_cleanups() == ("skm-test-refused",)
    assert log.events == [("error", "platform.process.cleanup_worker_not_running")]
    assert ownership.recover_cleanups() == ()
    assert log.events[1:] == [("info", "platform.process.cleanup_worker_recovered")]
    released.set()


@pytest.mark.parametrize("failure", [RuntimeError("log sink failed"), KeyboardInterrupt()])
def test_raising_log_cannot_stop_the_cleanup_it_reports(
    monkeypatch: pytest.MonkeyPatch, failure: BaseException
) -> None:
    monkeypatch.setattr(ownership, "_log", _RecordedLog(failure))
    start = threading.Thread.start
    worker_failure = RuntimeError("can't start new thread")
    attempts: list[int] = []

    def step() -> bool:
        attempts.append(1)
        return True

    def refused(thread: threading.Thread) -> None:
        if thread.name == "skm-test-refused":
            raise worker_failure
        start(thread)

    with monkeypatch.context() as patch:
        patch.setattr(threading.Thread, "start", refused)
        assert ownership.start_cleanup_worker(step, "skm-test-refused") is worker_failure
    assert ownership._unattended == {step: "skm-test-refused"}
    assert ownership.recover_cleanups() == ()
    assert attempts == [1]


class _NoteInterrupted(Exception):
    @override
    def add_note(self, note: str, /) -> None:
        raise KeyboardInterrupt


class _Unprintable(OSError):
    @override
    def __str__(self) -> str:
        raise KeyboardInterrupt


def test_note_helpers_never_raise() -> None:
    ownership.add_note(_NoteInterrupted(), "evidence")
    assert ownership.describe_failure(_Unprintable()) == "<unprintable _Unprintable>"
    assert ownership.describe_failure(ValueError("readable")) == "readable"
    assert "<unprintable _Unprintable>" in ownership.unattended_note(_Unprintable())
    assert "<unprintable _Unprintable>" in ownership.supervised_note(_Unprintable())


def test_unprintable_close_failure_cannot_skip_the_discard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The note about the second close read its text inside the handler that leads to the discard.
    primary = OSError(errno.EIO, "first close failed")
    failed = _FailedRelease(monkeypatch, primary)
    fork_bootstrap = ownership._fork_bootstrap

    def failed_closes(channel: int, failures: list[BaseException]) -> tuple[ownership.ChildPipes, int]:
        started = fork_bootstrap(channel, failures)
        failures.extend((primary, _Unprintable(errno.EIO, "second close failed")))
        return started

    monkeypatch.setattr(ownership, "_fork_bootstrap", failed_closes)
    with pytest.raises(OSError, match="first close failed") as caught:
        ownership.launch(("/bin/true",), cwd=tmp_path, env={})
    assert caught.value is primary
    assert "<unprintable _Unprintable>" in " ".join(primary.__notes__)
    owned = failed.started[0]
    assert owned._pidfd is None
    assert identity_of(owned.pid) is None


def test_unprintable_discard_failure_keeps_primary_and_retention(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = OSError(errno.EIO, "release failed")
    failed = _FailedRelease(monkeypatch, primary)
    released = threading.Event()
    signal_group = OwnedProcess.signal_group

    def denied(owned: OwnedProcess, sig: int) -> bool:
        if sig == 0 or released.is_set():
            return signal_group(owned, sig)
        raise _Unprintable(errno.EPERM, "signal delivery denied")

    monkeypatch.setattr(OwnedProcess, "signal_group", denied)
    try:
        with pytest.raises(OSError, match="release failed") as caught:
            ownership.launch(("/bin/true",), cwd=tmp_path, env={})
        assert caught.value is primary
        assert "<unprintable _Unprintable>" in " ".join(primary.__notes__)
        owned = failed.started[0]
        with ownership._retained_guard:
            assert owned in ownership._retained
        assert owned._pidfd is not None
    finally:
        released.set()
    worker = next(t for t in threading.enumerate() if t.name == f"skm-discard-{owned.pid}")
    worker.join(3)
    assert not worker.is_alive()
    assert owned._pidfd is None
    assert identity_of(owned.pid) is None


def _open_fds() -> set[int]:
    gc.collect()
    listed = {int(name) for name in os.listdir("/proc/self/fd")}
    # The listing's own descriptor is closed by now, so only real ones pass.
    return {fd for fd in listed if _is_open(fd)}


def _is_open(fd: int) -> bool:
    try:
        os.fstat(fd)
    except OSError:
        return False
    return True


class _FailedRelease:
    """Records the bound child, then fails the start before its target can run."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, primary: BaseException) -> None:
        self.started: list[OwnedProcess] = []
        hold = ownership._hold

        def recording_hold(owned: OwnedProcess) -> None:
            self.started.append(owned)
            hold(owned)

        def failed_release(*args: object) -> None:
            raise primary

        monkeypatch.setattr(ownership, "_hold", recording_hold)
        monkeypatch.setattr(ownership, "_release", failed_release)


class _Unnoteable(OSError):
    @override
    def add_note(self, note: str, /) -> None:
        raise RuntimeError("no room for a note")


@pytest.mark.parametrize("failing", ["set_blocking", "read"])
def test_failed_start_diagnostic_cannot_replace_primary_or_skip_discard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failing: str
) -> None:
    # Before the fix the OSError below replaced the primary failure and the child was abandoned.
    primary = ValueError("release failed")
    fault = _FailedRelease(monkeypatch, primary)
    before = _open_fds()

    def refused(*args: object) -> None:
        raise OSError(errno.EIO, "diagnostic refused")

    monkeypatch.setattr(os, failing, refused)
    with pytest.raises(ValueError, match="release failed") as caught:
        ownership.launch(("/bin/true",), cwd=tmp_path, env={})
    assert caught.value is primary
    assert "bootstrap report unavailable" in " ".join(primary.__notes__)
    owned = fault.started[0]
    assert owned._pidfd is None
    assert identity_of(owned.pid) is None
    del caught
    assert _open_fds() <= before


def test_diagnostic_failure_with_failed_cleanup_retains_ownership(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fault = _DiscardFault(monkeypatch, signal_denied=True, reap_pending=True)
    primary = OSError(errno.EIO, "release failed")
    failed = _FailedRelease(monkeypatch, primary)
    before = _open_fds()

    def refused(fd: int, blocking: bool) -> None:
        raise OSError(errno.EIO, "diagnostic refused")

    with monkeypatch.context() as patch:
        patch.setattr(os, "set_blocking", refused)
        with pytest.raises(OSError, match="release failed") as caught:
            ownership.launch(("/bin/true",), cwd=tmp_path, env={})
    assert caught.value is primary
    owned = failed.started[0]
    try:
        with ownership._retained_guard:
            assert owned in ownership._retained
        assert owned._pidfd is not None
        assert owned.exit_code() is None
        assert "ownership retained" in " ".join(primary.__notes__)
    finally:
        fault.released.set()
    worker = next(t for t in threading.enumerate() if t.name == f"skm-discard-{owned.pid}")
    worker.join(3)
    assert not worker.is_alive()
    assert owned._pidfd is None
    assert identity_of(owned.pid) is None
    del caught
    assert _open_fds() <= before


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_primary_that_refuses_notes_still_gets_full_cleanup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cleanup_fails: bool
) -> None:
    primary = _Unnoteable(errno.EIO, "release failed")
    fault = _DiscardFault(monkeypatch, signal_denied=cleanup_fails, reap_pending=cleanup_fails)
    if not cleanup_fails:
        fault.released.set()
    failed = _FailedRelease(monkeypatch, primary)
    before = _open_fds()

    def refused(fd: int, blocking: bool) -> None:
        raise OSError(errno.EIO, "diagnostic refused")

    with monkeypatch.context() as patch:
        patch.setattr(os, "set_blocking", refused)
        with pytest.raises(_Unnoteable) as caught:
            ownership.launch(("/bin/true",), cwd=tmp_path, env={})
    assert caught.value is primary
    owned = failed.started[0]
    if cleanup_fails:
        with ownership._retained_guard:
            assert owned in ownership._retained
        assert owned._pidfd is not None
        fault.released.set()
        worker = next(t for t in threading.enumerate() if t.name == f"skm-discard-{owned.pid}")
        worker.join(3)
        assert not worker.is_alive()
    fault.released.set()
    assert owned._pidfd is None
    assert identity_of(owned.pid) is None
    del caught
    assert _open_fds() <= before


@pytest.mark.parametrize("step", [0, 1, 2])
@pytest.mark.parametrize("behaviour", ["refused", "closed", "closed_and_reused"])
def test_each_wrapping_failure_leaves_no_child_and_no_descriptor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_spawn: list[object], step: int, behaviour: str
) -> None:
    # The wrapping runs before the fork, so a refusal leaves nothing to own; no_spawn proves it.
    primary = OSError(errno.EMFILE, "wrapping failed")
    fdopen = os.fdopen
    wrapped: list[int] = []
    foreign: list[int] = []
    before = _open_fds()

    def failing(fd: int, mode: str, buffering: int = -1) -> IO[bytes]:
        if len(wrapped) < step:
            wrapped.append(fd)
            return fdopen(fd, mode, buffering)
        if behaviour != "refused":
            os.close(fd)
        if behaviour == "closed_and_reused":
            # Another thread opened a file, and the lowest free number was this one.
            reused = os.open(os.devnull, os.O_RDONLY)
            if reused != fd:
                os.dup2(reused, fd)
                os.close(reused)
            foreign.append(fd)
        raise primary

    monkeypatch.setattr(os, "fdopen", failing)
    with pytest.raises(OSError, match="wrapping failed") as caught:
        ownership.launch(("/bin/true",), cwd=tmp_path, env={})
    assert caught.value is primary
    del caught
    if foreign:
        # The stranger's file survives: closing that number blindly would have closed it.
        assert os.path.samestat(os.fstat(foreign[0]), os.stat(os.devnull))
        os.close(foreign[0])
    assert _open_fds() <= before
    assert len(wrapped) == step


def test_wrapping_failure_with_an_unreadable_descriptor_closes_nothing_blindly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_spawn: list[object]
) -> None:
    primary = OSError(errno.EMFILE, "wrapping failed")
    fstat = os.fstat
    fds: list[int] = []

    def refused(fd: int, *args: object, **kwargs: object) -> None:
        fds.append(fd)
        monkeypatch.setattr(os, "fstat", unreadable)
        raise primary

    def unreadable(fd: int) -> None:
        raise OSError(errno.EIO, "fstat refused")

    monkeypatch.setattr(os, "fdopen", refused)
    with pytest.raises(OSError, match="wrapping failed") as caught:
        ownership.launch(("/bin/true",), cwd=tmp_path, env={})
    monkeypatch.setattr(os, "fstat", fstat)
    assert "fstat refused" in " ".join(caught.value.__notes__)
    # It stays open, and a leak is the safer side: the number could name anything by now.
    assert _is_open(fds[0])
    os.close(fds[0])


def test_failed_fork_closes_every_descriptor_despite_a_failing_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    primary = OSError(errno.EAGAIN, "fork refused")
    close = os.close
    forked: list[bool] = []
    closes: list[int] = []
    before = _open_fds()

    def refused(*args: object) -> int:
        forked.append(True)
        raise primary

    def failing_close(fd: int) -> None:
        close(fd)
        if forked:
            closes.append(fd)
            if len(closes) == 1:
                raise OSError(errno.EIO, "close reported an error")

    monkeypatch.setattr(ownership, "_fork_exec_signature", lambda: ownership._FORK_EXEC_PARAMETERS)
    monkeypatch.setattr(ownership.subprocess, "_fork_exec", refused)
    monkeypatch.setattr(os, "close", failing_close)
    with pytest.raises(OSError, match="fork refused") as caught:
        ownership.launch(("/bin/true",), cwd=tmp_path, env={})
    monkeypatch.setattr(os, "close", close)
    assert caught.value is primary
    assert "close reported an error" in " ".join(primary.__notes__)
    assert len(closes) == len(set(closes))
    del caught
    assert _open_fds() <= before


def _close_fails_once(monkeypatch: pytest.MonkeyPatch, armed: list[bool]) -> None:
    close = os.close

    def failing(fd: int) -> None:
        close(fd)
        if armed:
            armed.clear()
            raise OSError(errno.EIO, "close reported an error")

    monkeypatch.setattr(os, "close", failing)


def _socket_close_fails_once(monkeypatch: pytest.MonkeyPatch, armed: list[bool]) -> None:
    close = ownership.socket.socket.close

    def failing(channel: socket.socket) -> None:
        close(channel)
        if armed:
            armed.clear()
            raise OSError(errno.EIO, "close reported an error")

    monkeypatch.setattr(ownership.socket.socket, "close", failing)


@pytest.mark.parametrize("arm_close", [_close_fails_once, _socket_close_fails_once])
def test_close_failure_after_the_fork_binds_and_settles_before_any_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arm_close: Callable[..., None]
) -> None:
    marker = tmp_path / "target-ran"
    armed: list[bool] = []
    held: list[OwnedProcess] = []
    hold = ownership._hold
    fork_exec = ownership._fork_exec()

    def recording_hold(owned: OwnedProcess) -> None:
        held.append(owned)
        hold(owned)

    def arming_fork(*args: object) -> int:
        pid = fork_exec(*args)
        armed.append(True)
        return pid

    monkeypatch.setattr(ownership, "_hold", recording_hold)
    monkeypatch.setattr(ownership, "_fork_exec_signature", lambda: ownership._FORK_EXEC_PARAMETERS)
    monkeypatch.setattr(ownership.subprocess, "_fork_exec", arming_fork)
    before = _open_fds()
    arm_close(monkeypatch, armed)
    with pytest.raises(OSError, match="close reported an error") as caught:
        ownership.launch(("/bin/touch", str(marker)), cwd=tmp_path, env={})
    assert not armed
    assert not marker.exists()
    assert held[0]._pidfd is None
    assert identity_of(held[0].pid) is None
    del caught
    assert _open_fds() <= before


@pytest.mark.parametrize("arm_close", [_close_fails_once, _socket_close_fails_once])
def test_close_failure_after_release_settles_the_running_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, arm_close: Callable[..., None]
) -> None:
    # A raise hands the caller nothing, so the released target must not be left without an owner.
    armed: list[bool] = []
    held: list[OwnedProcess] = []
    hold, release = ownership._hold, ownership._release

    def recording_hold(owned: OwnedProcess) -> None:
        held.append(owned)
        hold(owned)

    def arming_release(channel: socket.socket, request: bytes, executable: str, cwd: Path) -> None:
        release(channel, request, executable, cwd)
        armed.append(True)

    monkeypatch.setattr(ownership, "_hold", recording_hold)
    monkeypatch.setattr(ownership, "_release", arming_release)
    before = _open_fds()
    arm_close(monkeypatch, armed)
    with pytest.raises(OSError, match="close reported an error") as caught:
        ownership.launch((sys.executable, "-c", "import signal; signal.pause()"), cwd=tmp_path, env={})
    assert not armed
    assert held[0]._pidfd is None
    assert identity_of(held[0].pid) is None
    del caught
    assert _open_fds() <= before


def test_discard_retains_group_with_a_survivor_after_a_confirmed_reap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The signal reports delivery but reaches nobody, so the member outlives the confirmed reap.
    fault = _DiscardFault(monkeypatch, signal_denied=False, reap_pending=False)
    code = """
import os,signal,time
from pathlib import Path
if os.fork()==0:
    Path('member').write_text(str(os.getpid()))
    while True: signal.pause()
while not Path('member').exists() or not Path('member').stat().st_size: time.sleep(.001)
"""

    streams = runner.ProcessStreams

    # Setup fails only once the leader has left by itself, so the reap inside discard succeeds.
    def after_leader_exit(
        proc: ownership.ChildPipes,
        on_stdout: Callable[[bytes], None],
        on_stderr: Callable[[bytes], None],
        *,
        line_mode: bool,
        stdin: bytes | None,
        manage_stdin: bool,
    ) -> None:
        owned = fault.started[0]
        deadline = time.monotonic() + 5
        while owned.exit_code() is None:
            assert time.monotonic() < deadline
            threading.Event().wait(0.005)
        streams(proc, on_stdout, on_stderr, line_mode=line_mode, stdin=stdin, manage_stdin=manage_stdin)

    monkeypatch.setattr(runner, "ProcessStreams", after_leader_exit)
    monkeypatch.setattr(ownership, "_ABORT_SECONDS", 3.0)
    member: ProcessIdentity | None = None
    try:
        with pytest.raises(OSError, match="streams setup failed"):
            runner.spawn(_argv(code), cwd=tmp_path, env={}, on_stdout=_ignore, on_stderr=_ignore)
        assert "process_group_cleanup_unconfirmed" in " ".join(fault.primary.__notes__)
        owned = fault.started[0]
        assert owned._pidfd is not None
        with ownership._retained_guard:
            assert owned in ownership._retained
        member = identity_of(int((tmp_path / "member").read_text()))
        assert member is not None
        assert is_same_process(member)
    finally:
        fault.released.set()
    worker = next((t for t in threading.enumerate() if t.name == f"skm-discard-{owned.pid}"), None)
    if worker is not None:
        worker.join(3)
    assert owned._pidfd is None
    assert not is_same_process(member)


@pytest.mark.parametrize(
    ("patch_target", "reason"),
    [
        ((sys, "platform", "darwin"), "no pidfd on darwin"),
        ((sys, "executable", ""), "no interpreter"),
    ],
)
def test_platform_without_authority_refuses_before_spawn(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    no_spawn: list[object],
    patch_target: tuple[object, str, str],
    reason: str,
) -> None:
    monkeypatch.setattr(*patch_target)
    with pytest.raises(OwnershipUnavailable, match=reason):
        runner.run(["/bin/true"], cwd=tmp_path, env={}, timeout_seconds=1)
    with pytest.raises(OwnershipUnavailable, match=reason):
        runner.spawn(["/bin/true"], cwd=tmp_path, env={}, on_stdout=_ignore, on_stderr=_ignore)


@pytest.mark.parametrize(
    ("module", "name"),
    [
        (os, "pidfd_open"),
        (os, "waitid"),
        (os, "P_PIDFD"),
        (os, "WNOWAIT"),
        (signal, "pidfd_send_signal"),
        (ownership.subprocess, "_fork_exec"),
    ],
)
def test_missing_python_api_refuses_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_spawn: list[object], module: object, name: str
) -> None:
    monkeypatch.delattr(module, name)
    with pytest.raises(OwnershipUnavailable, match=name):
        runner.run(["/bin/true"], cwd=tmp_path, env={}, timeout_seconds=1)


@pytest.mark.parametrize(
    ("failure", "reason"),
    [(errno.EINVAL, "Linux 6.9"), (errno.ENOSYS, "Linux 6.9"), (errno.EPERM, "Linux 6.9")],
)
def test_kernel_without_group_scope_refuses_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_spawn: list[object], failure: int, reason: str
) -> None:
    def rejected(*args: object) -> None:
        raise OSError(failure, os.strerror(failure))

    monkeypatch.setattr(signal, "pidfd_send_signal", rejected)
    with pytest.raises(OwnershipUnavailable, match=reason):
        runner.run(["/bin/true"], cwd=tmp_path, env={}, timeout_seconds=1)


def test_seccomp_refused_pidfd_open_refuses_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_spawn: list[object]
) -> None:
    def rejected(pid: int) -> int:
        raise PermissionError(errno.EPERM, "denied")

    monkeypatch.setattr(os, "pidfd_open", rejected)
    with pytest.raises(OwnershipUnavailable, match="pidfd_open"):
        runner.run(["/bin/true"], cwd=tmp_path, env={}, timeout_seconds=1)


def test_subreaper_refusal_prevents_fork(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, no_spawn: list[object]
) -> None:
    def refuse(*args: object) -> int:
        ctypes.set_errno(errno.EPERM)
        return -1

    libc = Mock(prctl=Mock(side_effect=refuse))
    monkeypatch.setattr(ctypes, "CDLL", lambda *args, **kwargs: libc)
    with pytest.raises(OwnershipUnavailable, match="PR_SET_CHILD_SUBREAPER") as caught:
        ownership.launch(("/bin/true",), cwd=tmp_path, env={})
    assert caught.value.errno == errno.EPERM


def test_missing_start_ticks_blocks_release_and_reaps_bootstrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bound: list[int] = []

    def missing_ticks(pid: int) -> ProcessIdentity:
        bound.append(pid)
        return ProcessIdentity(pid, None, "boot")

    monkeypatch.setattr(ownership, "identity_of", missing_ticks)
    marker = tmp_path / "target-ran"
    with pytest.raises(OwnershipUnavailable, match="child start ticks unavailable"):
        ownership.launch(("/bin/touch", str(marker)), cwd=tmp_path, env={})
    assert not marker.exists()
    assert len(bound) == 1
    assert identity_of(bound[0]) is None


def test_probe_accepts_an_owner_that_leads_no_group(monkeypatch: pytest.MonkeyPatch) -> None:
    def no_group(*args: object) -> None:
        raise ProcessLookupError

    monkeypatch.setattr(signal, "pidfd_send_signal", no_group)
    ownership.require_support()


@pytest.mark.parametrize(
    ("bootstrap", "reason"),
    [
        ("pass", "sent no pidfd"),
        ("raise SystemExit(3)", "sent no pidfd"),
        # The owner's own pidfd is a live foreign process from the child's point of view.
        (
            "import os,socket,sys; c=socket.socket(fileno=int(sys.argv[1])); "
            "socket.send_fds(c,[b'x'],[os.pidfd_open(os.getppid())]); c.recv(1)",
            "names another process",
        ),
        # A descriptor that is no pidfd at all.
        (
            "import os,socket,sys; c=socket.socket(fileno=int(sys.argv[1])); "
            "socket.send_fds(c,[b'x'],[1]); c.recv(1)",
            "names another process",
        ),
        ("import socket,sys; socket.socket(fileno=int(sys.argv[1])).send(b'x')", "sent no pidfd"),
    ],
)
def test_unbound_child_never_runs_target_and_is_never_signalled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, bootstrap: str, reason: str
) -> None:
    marker = tmp_path / "target-ran"
    calls: list[int] = []

    def record(owned: OwnedProcess, sig: int) -> bool:
        calls.append(sig)
        return False

    monkeypatch.setattr(ownership, "_BOOTSTRAP", bootstrap)
    monkeypatch.setattr(OwnedProcess, "signal_group", record)
    with pytest.raises(OwnershipUnavailable, match=reason):
        runner.run(["/bin/touch", str(marker)], cwd=tmp_path, env={}, timeout_seconds=1)
    assert not marker.exists()
    assert not calls


def test_silent_child_is_bounded_and_ends_on_channel_close(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    done = tmp_path / "bootstrap-ended"
    bootstrap = (
        "import socket,sys; c=socket.socket(fileno=int(sys.argv[1])); c.recv(1); "
        f"open({str(done)!r},'w').close()"
    )
    monkeypatch.setattr(ownership, "_BOOTSTRAP", bootstrap)
    monkeypatch.setattr(ownership, "_HANDSHAKE_SECONDS", 0.2)
    with pytest.raises(OwnershipUnavailable, match="process_ownership_unbound"):
        runner.run(["/bin/true"], cwd=tmp_path, env={}, timeout_seconds=1)
    # No authority was held, so the owner only closed its end; the child ended by itself.
    deadline = time.monotonic() + 30
    while not done.exists():
        assert time.monotonic() < deadline
        threading.Event().wait(0.01)


def test_child_that_dies_before_release_does_not_bind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = ownership._hold
    held: list[OwnedProcess] = []

    def killed_first(owned: OwnedProcess) -> None:
        held.append(owned)
        assert owned.signal_group(signal.SIGKILL)
        deadline = time.monotonic() + 5
        while owned.exit_code() is None:
            assert time.monotonic() < deadline
            threading.Event().wait(0.01)
        original(owned)

    monkeypatch.setattr(ownership, "_hold", killed_first)
    marker = tmp_path / "target-ran"
    with pytest.raises(OwnershipUnavailable, match="child left before release"):
        runner.run(["/bin/touch", str(marker)], cwd=tmp_path, env={}, timeout_seconds=1)
    assert not marker.exists()
    assert not held[0].signal_group(0)


def test_closed_ownership_grants_nothing(tmp_path: Path) -> None:
    handle = runner.spawn(_argv("pass"), cwd=tmp_path, env={}, on_stdout=_ignore, on_stderr=_ignore)
    assert handle.wait(5) == 0
    owned = handle._child.owned
    assert owned._pidfd is None
    assert not owned.signal_group(signal.SIGKILL)
    assert not owned.group_alive()
    with pytest.raises(ChildProcessError):
        owned.exit_code()
    with pytest.raises(ChildProcessError):
        owned.reap()
    owned.close()


class _OrphanedLock:
    """A lock whose holder did not cross the fork: entering it would never return."""

    def __enter__(self) -> None:
        raise AssertionError("an inherited lock was taken")

    def __exit__(self, *args: object) -> None:
        raise AssertionError("an inherited lock was released")


def _sleeper(tmp_path: Path) -> tuple[ownership.ChildPipes, OwnedProcess]:
    return ownership.launch(tuple(_argv("import signal; signal.pause()")), cwd=tmp_path, env={})


def _finish(pipes: ownership.ChildPipes, owned: OwnedProcess) -> None:
    assert owned.signal_group(signal.SIGKILL)
    assert owned.reap(5) == -signal.SIGKILL
    owned.close()
    for pipe in (pipes.stdin, pipes.stdout, pipes.stderr):
        pipe.close()


def test_inherited_ownership_refuses_before_its_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pipes, owned = _sleeper(tmp_path)
    pidfd = owned._pidfd
    with monkeypatch.context() as patch:
        patch.setattr(ownership, "_owner", (os.getpid(), object()))
        patch.setattr(owned, "_lock", _OrphanedLock())
        assert not owned.held_here()
        for call in (
            lambda: owned.signal_group(signal.SIGKILL),
            owned.group_alive,
            owned.exit_code,
            owned.reap,
        ):
            with pytest.raises(OwnershipUnavailable, match="process_ownership_inherited"):
                call()
        # Silent, because a destructor calls it, and it closes no number the child may have reused.
        owned.close()
        owned.__del__()
        assert owned._pidfd == pidfd
        assert ownership._settle_retained(owned)
    assert owned.held_here()
    assert owned.exit_code() is None
    _finish(pipes, owned)


def test_fork_past_the_handlers_refuses_and_keeps_the_lists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A libc fork from ctypes or an extension runs no handler, so only the pid tells.
    pipes, owned = _sleeper(tmp_path)
    real = os.getpid()

    def step() -> bool:
        raise AssertionError("a step of the parent ran")

    with monkeypatch.context() as patch:
        patch.setattr(os, "getpid", lambda: real + 1)
        patch.setattr(ownership, "_retained_guard", _OrphanedLock())
        patch.setattr(ownership, "_recovery_lock", _OrphanedLock())
        patch.setattr(ownership, "_unattended", {step: "skm-reap-1"})
        patch.setattr(owned, "_lock", _OrphanedLock())
        assert ownership.recover_cleanups() == ()
        ownership.adopt_cleanup(step)
        assert isinstance(ownership.start_cleanup_worker(step, "skm-reap-1"), OwnershipUnavailable)
        assert ownership._unattended == {step: "skm-reap-1"}
        with pytest.raises(OwnershipUnavailable, match="forked past the fork handlers"):
            ownership.require_support()
        with pytest.raises(OwnershipUnavailable, match="forked past the fork handlers"):
            ownership.launch(("/bin/true",), cwd=tmp_path, env={})
        with pytest.raises(OwnershipUnavailable, match="process_ownership_inherited"):
            owned.signal_group(signal.SIGKILL)
    assert owned.exit_code() is None
    _finish(pipes, owned)


def test_fork_handler_replaces_locks_and_lists_and_keeps_the_old_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    guard, recovery = threading.Lock(), threading.Lock()
    guard.acquire()
    recovery.acquire()

    def step() -> bool:
        raise AssertionError("a step of the parent ran")

    retained, unattended = {object()}, {step: "skm-reap-1"}
    with monkeypatch.context() as patch:
        patch.setattr(ownership, "_retained_guard", guard)
        patch.setattr(ownership, "_recovery_lock", recovery)
        patch.setattr(ownership, "_retained", retained)
        patch.setattr(ownership, "_unattended", unattended)
        patch.setattr(ownership, "_inherited", [])
        patch.setattr(ownership, "_owner", ownership._owner)
        before = ownership._owner
        ownership._after_fork_in_child()
        assert ownership._owner is not before
        assert ownership._owner[0] == os.getpid()
        assert not ownership._retained_guard.locked()
        assert not ownership._recovery_lock.locked()
        assert ownership._retained == set()
        assert ownership._unattended == {}
        # Dropped here they would run destructors, which may wait on locks nobody can release.
        assert ownership._inherited == [(retained, unattended)]
        assert ownership.recover_cleanups() == ()


def test_discard_of_inherited_child_only_closes_this_process_copies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pipes, owned = _sleeper(tmp_path)
    primary = RuntimeError("start failed")
    with monkeypatch.context() as patch:
        patch.setattr(ownership, "_owner", (os.getpid(), object()))
        patch.setattr(ownership, "_retained_guard", _OrphanedLock())
        patch.setattr(owned, "_lock", _OrphanedLock())
        ownership.discard(pipes, owned, primary)
    assert all(pipe.closed for pipe in (pipes.stdin, pipes.stdout, pipes.stderr))
    assert "process_ownership_inherited" in " ".join(primary.__notes__)
    assert owned not in ownership._retained
    assert owned.exit_code() is None
    assert owned.signal_group(signal.SIGKILL)
    assert owned.reap(5) == -signal.SIGKILL
    owned.close()


def test_forked_child_does_not_touch_the_inherited_log(monkeypatch: pytest.MonkeyPatch) -> None:
    class Log:
        def error(self, event: str) -> None:
            raise AssertionError(event)

        def info(self, event: str) -> None:
            raise AssertionError(event)

    with monkeypatch.context() as patch:
        patch.setattr(ownership, "_log", Log())
        patch.setattr(ownership, "_owner", (os.getpid(), object()))
        ownership._report_unattended()
        ownership._report_recovered()
