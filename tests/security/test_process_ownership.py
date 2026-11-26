"""Authority over a child comes only from its pidfd.

Only children started by these tests are ever signalled. Real PID reuse needs a private PID
namespace, which unprivileged hosts may refuse, so these tests build the state a reuse leaves: the
number names a live decoy, while the descriptor names the original child.
"""

import ast
import errno
import os
import signal
import sys
import threading
import time
from collections.abc import Generator
from pathlib import Path

import pytest

import skm
from skm.platform.process import ownership, runner
from skm.platform.process.identity import group_alive, identity_of, is_same_process
from skm.platform.process.ownership import OwnedProcess

PACKAGE = Path(skm.__file__).parent
PROCESS = PACKAGE / "platform" / "process"
_NUMERIC_CALLS = frozenset({"kill", "killpg", "waitpid", "wait", "wait3", "wait4", "pidfd_open"})
_POPEN_NUMERIC = frozenset({"poll", "wait", "send_signal", "terminate", "communicate"})
_NUMERIC_STARTS = frozenset(
    {("subprocess", "Popen"), ("subprocess", "run"), ("os", "posix_spawn"), ("os", "posix_spawnp")}
)


def _ignore(data: bytes) -> None:
    pass


def _numeric_authority(source: str) -> list[str]:
    """Calls that act on a process by number, or on Popen's own numeric bookkeeping."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.ImportFrom) and any(alias.name == "kill_group" for alias in node.names):
            found.append("import kill_group")
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        owner, name = node.func.value, node.func.attr
        if isinstance(owner, ast.Name) and owner.id == "os" and name in _NUMERIC_CALLS:
            # The child opens its own pidfd: an argument of getpid() is the one safe number.
            argument = node.args[0] if node.args else None
            own = (
                isinstance(argument, ast.Call)
                and isinstance(argument.func, ast.Attribute)
                and argument.func.attr == "getpid"
            )
            if not (name == "pidfd_open" and own):
                found.append(f"os.{name}")
        if name in _POPEN_NUMERIC and isinstance(owner, ast.Attribute) and owner.attr == "proc":
            found.append(f"proc.{name}")
        # Popen and posix_spawn wait by number on a failed start, out of reach of any later check.
        if isinstance(owner, ast.Name) and (owner.id, name) in _NUMERIC_STARTS:
            found.append(f"{owner.id}.{name}")
    return found


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("import os\nos.kill(1, 9)", ["os.kill"]),
        ("import os\nos.killpg(1, 9)", ["os.killpg"]),
        ("import os\nos.waitpid(1, 0)", ["os.waitpid"]),
        ("import os\nos.pidfd_open(1)", ["os.pidfd_open"]),
        ("from skm.platform.process.identity import kill_group", ["import kill_group"]),
        ("self.proc.wait(timeout=1)", ["proc.wait"]),
        ("self.proc.poll()", ["proc.poll"]),
        ("import subprocess\nsubprocess.Popen(['x'])", ["subprocess.Popen"]),
        ("import os\nos.posix_spawn('x', ['x'], {})", ["os.posix_spawn"]),
        ("import os\nos.pidfd_open(os.getpid())", []),
    ],
)
def test_numeric_authority_rule_detects_each_form(source: str, expected: list[str]) -> None:
    assert _numeric_authority(source) == expected


@pytest.mark.parametrize("name", ["runner.py", "ownership.py"])
def test_owner_modules_never_act_on_a_number(name: str) -> None:
    assert _numeric_authority((PROCESS / name).read_text()) == []


def test_bootstrap_opens_only_its_own_pidfd() -> None:
    assert _numeric_authority(ownership._BOOTSTRAP) == []


def test_no_product_code_imports_the_numeric_group_kill() -> None:
    offenders = [
        str(path)
        for path in PACKAGE.rglob("*.py")
        if any(finding == "import kill_group" for finding in _numeric_authority(path.read_text()))
    ]
    assert offenders == []


@pytest.fixture
def decoy(tmp_path: Path) -> Generator[runner.ProcessHandle]:
    # A controlled stand-in for an unrelated process. It exits 0 only if nothing reached it.
    ready = threading.Event()
    handle = runner.spawn(
        [sys.executable, "-c", "import sys; print('ready',flush=True); sys.stdin.read()"],
        cwd=tmp_path,
        env={},
        on_stdout=lambda data: ready.set(),
        on_stderr=lambda data: None,
    )
    assert ready.wait(5)
    yield handle
    handle.close_stdin()
    assert handle.wait(5) == 0


def test_reused_number_is_out_of_reach_of_a_gone_child_capability(
    tmp_path: Path, decoy: runner.ProcessHandle
) -> None:
    probe = runner.spawn(
        [sys.executable, "-c", "pass"], cwd=tmp_path, env={}, on_stdout=_ignore, on_stderr=_ignore
    )
    # A second reference outlives the handle, which reaps the child and closes its own.
    with probe._child.owned._lock:
        owned = OwnedProcess(probe.pid, os.dup(probe._child.owned._pidfd or -1))
    assert probe.wait(5) == 0
    owned.pid = decoy.pid
    # Every numeric fact now says the number is alive and leads a group.
    assert group_alive(decoy.pid)
    assert is_same_process(decoy.identity)
    # The capability says the group is gone: nothing is delivered and nothing is reaped.
    assert not owned.signal_group(signal.SIGKILL)
    assert not owned.group_alive()
    with pytest.raises(ChildProcessError):
        owned.exit_code()
    with pytest.raises(ChildProcessError):
        owned.reap()
    owned.close()
    assert is_same_process(decoy.identity)


@pytest.mark.parametrize("api", ["kill", "terminate", "timeout"])
def test_every_signal_path_spares_the_holder_of_the_number(
    tmp_path: Path, decoy: runner.ProcessHandle, monkeypatch: pytest.MonkeyPatch, api: str
) -> None:
    # Only the membership scan reads the number, so it keeps the target's real one: the kernel
    # never reassigns a number while its group exists. Signals must follow the descriptor alone.
    original = runner._start
    scan = ownership.group_alive

    def renumbered(argv: tuple[str, ...], cwd: Path, env: dict[str, str]) -> object:
        proc, owned = original(argv, cwd, env)
        real = owned.pid
        monkeypatch.setattr(ownership, "group_alive", lambda pid: scan(real))
        owned.pid = decoy.pid
        return proc, owned

    monkeypatch.setattr(runner, "_start", renumbered)
    argv = [sys.executable, "-c", "import signal; signal.pause()"]
    if api == "timeout":
        result = runner.run(argv, cwd=tmp_path, env={}, timeout_seconds=0.2, grace_seconds=0.01)
        assert result.timed_out
        assert result.signal == signal.SIGTERM
    else:
        # SIGINT before the interpreter finished starting exits with 1, not by the signal.
        ready = threading.Event()
        argv[-1] = "import signal; print('ready', flush=True); signal.pause()"
        target = runner.spawn(argv, cwd=tmp_path, env={}, on_stdout=lambda _: ready.set(), on_stderr=_ignore)
        assert ready.wait(30)
        if api == "kill":
            target.kill()
            assert target.wait(5) == -signal.SIGKILL
        else:
            assert target.terminate(grace_seconds=0.5).exited
            assert target.wait(5) == -signal.SIGINT
    # The decoy fixture also asserts a clean exit 0 at teardown.
    assert is_same_process(decoy.identity)


def test_failed_start_cannot_consume_the_holder_of_a_reused_number(
    tmp_path: Path, decoy: runner.ProcessHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The state a reuse leaves: the failed fork is gone, and its number names another child of this
    # process. Popen would waitpid here and consume the decoy; the fixture's exit 0 proves otherwise.
    fork_exec = ownership._fork_exec()
    decoy_group = decoy._child.owned.group_alive
    interpreter = tmp_path / "not-an-interpreter"
    interpreter.write_bytes(b"\0\0\0\0")
    interpreter.chmod(0o700)

    def reused(*args: object) -> int:
        real = fork_exec(*args)
        assert os.waitpid(real, 0)[0] == real
        return decoy.pid

    with monkeypatch.context() as patch:
        patch.setattr(sys, "executable", str(interpreter))
        patch.setattr(ownership, "_fork_exec_signature", lambda: ownership._FORK_EXEC_PARAMETERS)
        patch.setattr(ownership.subprocess, "_fork_exec", reused)
        with pytest.raises(ownership.OwnershipUnavailable, match="process_ownership_unbound"):
            runner.run(["/bin/true"], cwd=tmp_path, env={}, timeout_seconds=1)
    assert decoy_group()
    assert is_same_process(decoy.identity)
    assert decoy.wait(0) is None


def test_failed_cleanup_retains_the_child_and_spares_every_other_process(
    tmp_path: Path, decoy: runner.ProcessHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Numeric facts name the decoy while the cleanup fails and later succeeds: signals follow the pidfd.
    numeric: list[str] = []
    monkeypatch.setattr(os, "kill", lambda *args: numeric.append("kill"))
    monkeypatch.setattr(os, "killpg", lambda *args: numeric.append("killpg"))
    original = runner._start
    scan = ownership.group_alive
    signal_group = OwnedProcess.signal_group
    released = threading.Event()

    def renumbered(argv: tuple[str, ...], cwd: Path, env: dict[str, str]) -> object:
        proc, owned = original(argv, cwd, env)
        real = owned.pid
        monkeypatch.setattr(ownership, "group_alive", lambda pid: scan(real))
        owned.pid = decoy.pid
        return proc, owned

    def denied_until_release(owned: OwnedProcess, sig: int) -> bool:
        if sig == 0 or released.is_set():
            return signal_group(owned, sig)
        raise PermissionError(errno.EPERM, "signal delivery denied")

    primary = ValueError("callback failed")

    def callback(data: bytes) -> None:
        raise primary

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    monkeypatch.setattr(runner, "_start", renumbered)
    monkeypatch.setattr(OwnedProcess, "signal_group", denied_until_release)
    monkeypatch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)
    target = runner.spawn(
        [sys.executable, "-c", "import signal; print('ready',flush=True); signal.pause()"],
        cwd=tmp_path,
        env={},
        on_stdout=callback,
        on_stderr=_ignore,
    )
    try:
        with pytest.raises(ValueError, match="callback failed"):
            target.wait(5)
        with runner._pending_guard:
            assert runner._pending_children - baseline == {target._child}
        assert target._child.owned.exit_code() is None
    finally:
        released.set()
    deadline = time.monotonic() + 5
    while target._child.status is None or not target._child.stopped:
        assert time.monotonic() < deadline
        threading.Event().wait(0.01)
    assert target._child.status == -signal.SIGKILL
    assert numeric == []
    assert is_same_process(decoy.identity)


class _NoWorkerFault:
    """The cleanup worker cannot start and the number names the decoy: only the descriptor is left."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, decoy: runner.ProcessHandle) -> None:
        self.numeric: list[str] = []
        self.released = threading.Event()
        monkeypatch.setattr(os, "kill", lambda *args: self.numeric.append("kill"))
        monkeypatch.setattr(os, "killpg", lambda *args: self.numeric.append("killpg"))
        monkeypatch.setattr(os, "waitpid", lambda *args: self.numeric.append("waitpid"))
        original = runner._start
        scan = ownership.group_alive
        signal_group = OwnedProcess.signal_group
        start = threading.Thread.start

        def renumbered(argv: tuple[str, ...], cwd: Path, env: dict[str, str]) -> object:
            proc, owned = original(argv, cwd, env)
            real = owned.pid
            monkeypatch.setattr(ownership, "group_alive", lambda pid: scan(real))
            owned.pid = decoy.pid
            return proc, owned

        def denied_until_release(owned: OwnedProcess, sig: int) -> bool:
            if sig == 0 or self.released.is_set():
                return signal_group(owned, sig)
            raise PermissionError(errno.EPERM, "signal delivery denied")

        def refused(thread: threading.Thread) -> None:
            if thread.name.startswith("skm-reap-"):
                raise RuntimeError("can't start new thread")
            start(thread)

        monkeypatch.setattr(runner, "_start", renumbered)
        monkeypatch.setattr(OwnedProcess, "signal_group", denied_until_release)
        monkeypatch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)
        monkeypatch.setattr(threading.Thread, "start", refused)


def test_supervisor_takeover_acts_through_the_pidfd_alone(
    tmp_path: Path, decoy: runner.ProcessHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    fault = _NoWorkerFault(monkeypatch, decoy)
    primary = ValueError("callback failed")

    def callback(data: bytes) -> None:
        raise primary

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    target = runner.spawn(
        [sys.executable, "-c", "import signal; print('ready',flush=True); signal.pause()"],
        cwd=tmp_path,
        env={},
        on_stdout=callback,
        on_stderr=_ignore,
    )
    with pytest.raises(ValueError, match="callback failed"):
        target.wait(5)
    with runner._pending_guard:
        assert runner._pending_children - baseline == {target._child}
    assert "cleanup_worker_not_started" in " ".join(primary.__notes__)
    assert target._child.owned.exit_code() is None
    fault.released.set()
    target._thread.join(5)
    assert not target._thread.is_alive()
    assert target._child.status == -signal.SIGKILL
    assert fault.numeric == []
    assert is_same_process(decoy.identity)


def test_cleanup_without_a_worker_recovers_through_the_pidfd_alone(
    tmp_path: Path, decoy: runner.ProcessHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    # run() has no thread to lend, so the cleanup waits for a recovery pass and says so.
    fault = _NoWorkerFault(monkeypatch, decoy)
    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    with pytest.raises(RuntimeError, match="can't start new thread") as caught:
        runner.run(
            [sys.executable, "-c", "import signal; signal.pause()"],
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
    assert child.owned.exit_code() is None
    fault.released.set()
    deadline = time.monotonic() + 5
    while ownership.recover_cleanups():
        assert time.monotonic() < deadline
        threading.Event().wait(0.01)
    while not child.stopped:
        assert time.monotonic() < deadline
        ownership.recover_cleanups()
        threading.Event().wait(0.01)
    assert child.status == -signal.SIGKILL
    assert fault.numeric == []
    assert is_same_process(decoy.identity)


@pytest.mark.parametrize(("leave", "survives"), [("sys.exit(0)", False), ("os._exit(0)", True)])
def test_owner_exit_gives_a_listed_cleanup_its_last_step_and_a_crash_does_not(
    tmp_path: Path, leave: str, survives: bool
) -> None:
    # The limitation stays visible: only an orderly exit reaches the group. A surviving target
    # reports the reparenting and exits on its own, so no process here needs to kill it.
    target = (
        "import os,time; from pathlib import Path; parent=os.getppid(); "
        "Path('target').write_text(str(os.getpid())); deadline=time.monotonic()+10\n"
        "while os.getppid()==parent and time.monotonic()<deadline: time.sleep(.005)\n"
        "Path('orphaned').write_text(str(os.getppid()!=parent))"
    )
    owner = f"""
import atexit,errno,os,sys,threading
from pathlib import Path
from skm.platform.process import ownership,runner
from skm.platform.process.ownership import OwnedProcess
signal_group=OwnedProcess.signal_group
start=threading.Thread.start
released=[]
def denied(owned,sig):
    if sig==0 or released: return signal_group(owned,sig)
    raise PermissionError(errno.EPERM,"signal delivery denied")
def refused(thread):
    if thread.name.startswith("skm-reap-"): raise RuntimeError("can't start new thread")
    start(thread)
OwnedProcess.signal_group=denied
threading.Thread.start=refused
atexit.register(released.append,True)
try:
    runner.run([sys.executable,"-c",{target!r}],cwd=Path.cwd(),env={{}},timeout_seconds=1,grace_seconds=0)
except RuntimeError:
    pass
assert len(ownership.recover_cleanups())==1
{leave}
"""
    result = runner.run(
        [sys.executable, "-c", owner],
        cwd=tmp_path,
        env={"PYTHONPATH": str(PACKAGE.parent)},
        timeout_seconds=20,
    )
    assert result.exit_code == 0, result.stderr
    pid = int((tmp_path / "target").read_text())
    orphaned = tmp_path / "orphaned"
    deadline = time.monotonic() + 15
    if survives:
        while not orphaned.exists() or not orphaned.stat().st_size:
            assert time.monotonic() < deadline
            threading.Event().wait(0.01)
        assert orphaned.read_text() == "True"
    else:
        while group_alive(pid):
            assert time.monotonic() < deadline
            threading.Event().wait(0.01)
        assert not orphaned.exists()


# Each script is an owner of its own: only the target it started is ever signalled, through the
# pidfd, and it waits only for the child it forked. A child that hangs ends by its own alarm.
_FORK_OWNER = """
import ctypes,os,signal,sys,threading,time
from functools import partial
from pathlib import Path
from skm.platform.process import ownership,runner
from skm.platform.process.ownership import OwnedProcess,OwnershipUnavailable
SLEEPER=[sys.executable,"-c","import time; time.sleep(60)"]
def child_exit(pid):
    return os.waitstatus_to_exitcode(os.waitpid(pid,0)[1])
def refuses(call,*args,code="process_ownership_inherited"):
    try:
        call(*args)
    except OwnershipUnavailable as error:
        assert code in str(error),error
    else:
        raise AssertionError(call)
def holding(locks):
    ready,release=threading.Event(),threading.Event()
    def hold():
        for lock in locks: lock.acquire()
        ready.set()
        release.wait()
        for lock in reversed(locks): lock.release()
    holder=threading.Thread(target=hold)
    holder.start()
    ready.wait()
    def done():
        release.set()
        holder.join()
    return done
def retain(owned):
    step=partial(ownership._settle_retained,owned)
    ownership._retained.add(owned)
    ownership._unattended[step]="skm-discard-test"
    return step
def settle(owned):
    assert ownership.recover_cleanups()==()
    deadline=time.monotonic()+5
    while owned._pidfd is not None:
        assert time.monotonic()<deadline
        time.sleep(.01)
"""


def _run_owner(tmp_path: Path, body: str) -> None:
    result = runner.run(
        [sys.executable, "-c", _FORK_OWNER + body],
        cwd=tmp_path,
        env={"PYTHONPATH": str(PACKAGE.parent)},
        timeout_seconds=40,
    )
    assert result.exit_code == 0, result.stderr


@pytest.mark.parametrize("held", [False, True], ids=["free_locks", "held_locks"])
def test_exit_of_forked_child_leaves_the_owner_group_alone(tmp_path: Path, held: bool) -> None:
    # Free locks show the kill a child's atexit would send, held ones the deadlock it would meet.
    _run_owner(
        tmp_path,
        f"""
pipes,owned=ownership.launch(tuple(SLEEPER),cwd=Path.cwd(),env={{}})
retain(owned)
locks=[ownership._retained_guard,ownership._recovery_lock,owned._lock] if {held} else []
done=holding(locks)
pid=os.fork()
if pid==0:
    signal.alarm(10)
    sys.exit(0)
done()
assert child_exit(pid)==0
assert owned.exit_code() is None
assert owned.signal_group(0)
assert owned in ownership._retained
settle(owned)
""",
    )


def test_exit_of_forked_child_leaves_a_retained_run_to_its_owner(tmp_path: Path) -> None:
    _run_owner(
        tmp_path,
        """
signal_group=OwnedProcess.signal_group
start=threading.Thread.start
released=[]
def denied(owned,sig):
    if sig==0 or released: return signal_group(owned,sig)
    raise PermissionError(1,"signal delivery denied")
def refused(thread):
    if thread.name.startswith("skm-reap-"): raise RuntimeError("can't start new thread")
    start(thread)
OwnedProcess.signal_group=denied
threading.Thread.start=refused
runner._KILL_WAIT_SECONDS=.05
try:
    runner.run(SLEEPER,cwd=Path.cwd(),env={},timeout_seconds=.2,grace_seconds=0)
except RuntimeError:
    pass
assert len(ownership.recover_cleanups())==1
retained=next(iter(runner._pending_children))
done=holding([runner._pending_guard,ownership._retained_guard,ownership._recovery_lock,retained.guard])
pid=os.fork()
if pid==0:
    signal.alarm(10)
    # Nothing stands in the way of a real kill here: only the empty lists do.
    released.append(True)
    sys.exit(0)
done()
assert child_exit(pid)==0
assert retained.owned.exit_code() is None
assert retained.owned.signal_group(0)
assert retained in runner._pending_children
released.append(True)
threading.Thread.start=start
assert ownership.recover_cleanups()==()
assert retained.done.wait(10)
assert retained.status==-signal.SIGKILL
""",
    )


def test_forked_child_gets_refusals_for_everything_it_inherited(tmp_path: Path) -> None:
    _run_owner(
        tmp_path,
        """
handle=runner.spawn(SLEEPER,cwd=Path.cwd(),env={},on_stdout=len,on_stderr=len)
child=handle._child
owned=child.owned
step=retain(owned)
done=holding([
    ownership._retained_guard,ownership._recovery_lock,runner._pending_guard,child.guard,owned._lock,
    child.input_lock,handle._termination_lock,child.done._cond,
])
pid=os.fork()
if pid==0:
    signal.alarm(20)
    refuses(owned.signal_group,signal.SIGKILL)
    refuses(owned.group_alive)
    refuses(owned.exit_code)
    refuses(owned.reap)
    owned.close()
    refuses(handle.kill)
    refuses(handle.wait)
    refuses(handle.write_stdin,b"x")
    refuses(handle.close_stdin)
    result=handle.terminate(grace_seconds=0)
    assert result==runner.TerminationResult(0,False,False,"process_ownership_inherited")
    assert ownership.recover_cleanups()==()
    ownership.adopt_cleanup(step)
    assert step()
    assert child._reap_step()
    assert not ownership._retained and not ownership._unattended and not runner._pending_children
    # The child is an owner in its own right, through locks and lists of its own.
    mine=runner.run(
        [sys.executable,"-c","print('mine')"],cwd=Path.cwd(),env={},timeout_seconds=10
    )
    assert (mine.exit_code,mine.stdout)==(0,b"mine\\n")
    sys.exit(0)
done()
assert child_exit(pid)==0
assert owned.exit_code() is None
assert owned.signal_group(0)
handle.write_stdin(b"x")
handle.kill()
assert handle.wait(10)==-signal.SIGKILL
ownership.recover_cleanups()
""",
    )


def test_fork_past_the_python_handlers_fails_closed(tmp_path: Path) -> None:
    _run_owner(
        tmp_path,
        """
pipes,owned=ownership.launch(tuple(SLEEPER),cwd=Path.cwd(),env={})
step=retain(owned)
locks=[ownership._retained_guard,ownership._recovery_lock,owned._lock]
for lock in locks: lock.acquire()
pid=ctypes.CDLL(None).fork()
assert pid>=0
if pid==0:
    signal.alarm(10)
    assert ownership.recover_cleanups()==()
    refuses(owned.signal_group,signal.SIGKILL)
    ownership.adopt_cleanup(step)
    assert isinstance(ownership.start_cleanup_worker(step,"skm-discard-test"),OwnershipUnavailable)
    refuses(
        partial(ownership.launch,tuple(SLEEPER),cwd=Path.cwd(),env={}),
        code="forked past the fork handlers",
    )
    sys.exit(0)
for lock in locks: lock.release()
assert child_exit(pid)==0
assert owned.exit_code() is None
assert owned.signal_group(0)
settle(owned)
""",
    )


def test_child_forked_inside_a_callback_cannot_run_the_supervisor(tmp_path: Path) -> None:
    # The child comes back into a copy of the supervisor loop, whose next step would kill the group.
    _run_owner(
        tmp_path,
        """
seen=threading.Event()
forked=[]
def callback(data):
    pid=os.fork()
    if pid==0:
        signal.alarm(10)
        return
    forked.append(pid)
    seen.set()
argv=[sys.executable,"-c","import time; print('up',flush=True); time.sleep(60)"]
handle=runner.spawn(argv,cwd=Path.cwd(),env={},on_stdout=callback,on_stderr=len)
assert seen.wait(20)
assert child_exit(forked[0])==0
assert handle._child.owned.exit_code() is None
assert handle._child.owned.signal_group(0)
assert handle.wait(0) is None
handle.kill()
assert handle.wait(10)==-signal.SIGKILL
""",
    )


def test_foreign_waiter_leaves_status_unknown_and_group_exact(
    tmp_path: Path, decoy: runner.ProcessHandle, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = runner._Child._drain

    def foreign_reap_then_reuse(child: runner._Child, timeout: float | None, grace: float) -> None:
        original(child, timeout, grace)
        assert os.waitpid(child.proc.pid, 0)[0] == child.proc.pid
        child.owned.pid = decoy.pid
        child.proc.pid = decoy.pid

    monkeypatch.setattr(runner._Child, "_drain", foreign_reap_then_reuse)
    target = runner.spawn(
        [sys.executable, "-c", "pass"], cwd=tmp_path, env={}, on_stdout=_ignore, on_stderr=_ignore
    )
    with pytest.raises(ProcessLookupError, match="process_status_unknown"):
        target.wait(5)
    assert target._child.status is None
    assert not target._child.stopped
    target.kill()
    result = target.terminate(grace_seconds=0)
    assert not result.exited
    assert result.signal_sent == 0
    assert is_same_process(decoy.identity)


def test_ignored_sigchld_is_unknown_outcome_never_synthetic_success(tmp_path: Path) -> None:
    # The kernel reaps by itself under SIG_IGN, a real foreign consumption of the status.
    previous = signal.signal(signal.SIGCHLD, signal.SIG_IGN)
    try:
        with pytest.raises(ProcessLookupError, match="process_status_unknown"):
            runner.run([sys.executable, "-c", "pass"], cwd=tmp_path, env={}, timeout_seconds=5)
    finally:
        signal.signal(signal.SIGCHLD, previous)


def test_deferred_cleanup_records_unknown_as_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # A descendant outlives the grace, then the status is consumed elsewhere before the final reap.
    code = """
import os,signal,time
from pathlib import Path
if os.fork()==0:
    signal.signal(signal.SIGTERM,signal.SIG_IGN)
    Path('member').write_text(str(os.getpid()))
    while True: signal.pause()
while not Path('member').exists() or not Path('member').stat().st_size: time.sleep(.001)
os._exit(0)
"""
    signal_group = OwnedProcess.signal_group
    released = threading.Event()

    def held_back(owned: OwnedProcess, sig: int) -> bool:
        return signal_group(owned, sig) if released.is_set() or sig == 0 else True

    with runner._pending_guard:
        baseline = runner._pending_children.copy()
    monkeypatch.setattr(OwnedProcess, "signal_group", held_back)
    monkeypatch.setattr(runner, "_KILL_WAIT_SECONDS", 0.05)
    result = runner.run(
        [sys.executable, "-c", code], cwd=tmp_path, env={}, timeout_seconds=5, grace_seconds=0.05
    )
    assert result.exit_code == 0
    with runner._pending_guard:
        retained = runner._pending_children - baseline
    assert len(retained) == 1
    child = retained.pop()
    assert os.waitpid(child.proc.pid, 0)[0] == child.proc.pid
    released.set()
    assert child.done.wait(5)
    member = identity_of(int((tmp_path / "member").read_text()))
    assert member is None or not is_same_process(member)
    assert not child.stopped
    assert child.status is None
    assert (child.identity, str(child.error)) in runner._cleanup_failures
    assert "process_status_unknown" in str(child.error)


def test_owner_crash_gives_no_one_authority_and_sends_nothing(tmp_path: Path) -> None:
    # The owner is killed mid-run. The target proves it was not signalled by reporting the
    # reparenting itself and exiting on its own, so no process here needs to kill it.
    target = (
        "import os,time; from pathlib import Path; parent=os.getppid(); "
        "Path('target').write_text(str(os.getpid())); deadline=time.monotonic()+10\n"
        "while os.getppid()==parent and time.monotonic()<deadline: time.sleep(.005)\n"
        "Path('orphaned').write_text(str(os.getppid()!=parent))"
    )
    owner = f"""
import os,signal,sys,time
from pathlib import Path
from skm.platform.process.runner import spawn
spawn([sys.executable,"-c",{target!r}],cwd=Path.cwd(),env={{}},on_stdout=len,on_stderr=len)
while not Path("target").exists() or not Path("target").stat().st_size: time.sleep(.001)
os.kill(os.getpid(),signal.SIGKILL)
"""
    result = runner.run(
        [sys.executable, "-c", owner],
        cwd=tmp_path,
        env={"PYTHONPATH": str(PACKAGE.parent)},
        timeout_seconds=20,
    )
    assert result.signal == signal.SIGKILL, result.stderr
    # The killed owner's pidfd closed with it; the target lives in its own session and ran on.
    orphaned = tmp_path / "orphaned"
    deadline = time.monotonic() + 15
    while not orphaned.exists() or not orphaned.stat().st_size:
        assert time.monotonic() < deadline
        threading.Event().wait(0.01)
    assert orphaned.read_text() == "True"
