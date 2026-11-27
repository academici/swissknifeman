"""Kernel-enforced ownership of one child: a pidfd the child opened for itself.

A numeric PID or PGID is reassigned once a foreign waiter consumes the status, so checking
one before using it never grants authority. Here the child runs a short bootstrap that calls
``pidfd_open(getpid())`` and passes the descriptor over a socket only it and the owner hold.
No window exists for the number to mean another process: the caller of ``pidfd_open`` is alive.
The target's argv and environment are sent only after the owner verified the descriptor, so an
unbound child never runs its target. The pidfd survives ``execve`` and names one ``struct pid``:

- ``PIDFD_SIGNAL_PROCESS_GROUP`` reaches exactly the group led by that object, including after
  a foreign reap, and returns ESRCH forever once it is empty. A later owner of the number has
  another object and cannot be reached.
- ``waitid(P_PIDFD)`` observes or consumes exactly this child, and ECHILD means its status went
  elsewhere: an unknown status, never a synthetic success.

Linux 6.9 or newer is required. Elsewhere ``launch`` refuses before anything starts. A crash of
the owner closes the pidfd and no later process can regain this authority; recovery has to treat
such a child as unknown. The owner is a child subreaper and adopts orphaned descendants, even
across ``setsid()``. Adoption grants no pidfd. Escaped descendants remain out of reach, and
adopted children without a pidfd can remain zombies until the owner exits.

``subprocess.Popen`` is not used: when its child fails before ``execve`` it calls ``waitpid`` on the
number, before any pidfd exists, and that can consume a foreign child holding a reused number. So
is ``posix_spawn``, whose libc waits the same way. ``launch`` calls Popen's own ``fork_exec`` and
waits for nothing. A bootstrap that never executed stays a zombie until the owner exits.

Ownership does not cross ``fork``. A forked child inherits this memory and the descriptors, but no
thread that held a lock, and a pidfd there would still reach the parent's group. So the child starts
with empty registries and new locks, and every object it inherited refuses before touching its lock:
it signals, waits, reaps and closes nothing. A copy of a pidfd stays open until ``execve`` or exit,
unused, because the child may already have given its number to another file.
"""

import atexit
import ctypes
import errno
import fcntl
import marshal
import os
import re
import signal
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Mapping
from contextlib import suppress
from dataclasses import dataclass
from functools import partial
from pathlib import Path
from typing import IO, Final

from skm.platform.logging.logger import get_logger
from skm.platform.process.identity import ProcessIdentity, group_alive, identity_of

__all__ = [
    "ChildPipes",
    "OwnedProcess",
    "OwnershipUnavailable",
    "add_note",
    "adopt_cleanup",
    "describe_failure",
    "discard",
    "launch",
    "recover_cleanups",
    "require_support",
    "start_cleanup_worker",
    "supervised_note",
    "unattended_note",
]

# <linux/pidfd.h>, Linux 6.9; Python does not expose this flag.
_PIDFD_SIGNAL_PROCESS_GROUP: Final = 1 << 2
_PR_SET_CHILD_SUBREAPER: Final = 36
_REQUIRED_API: Final = (
    (os, "pidfd_open"),
    (os, "waitid"),
    (os, "P_PIDFD"),
    (os, "WNOWAIT"),
    (signal, "pidfd_send_signal"),
    (subprocess, "_fork_exec"),
)
# fork_exec is private and positional: another parameter list refuses instead of misplacing a descriptor.
# Python 3.14 dropped the trailing allow_vfork parameter (CPython decides about vfork itself), so each
# interpreter line has exactly one accepted list and the arguments after preexec_fn that go with it.
_FORK_EXEC_COMMON: Final = (
    "$module, args, executable_list, close_fds, pass_fds, cwd, env, p2cread, p2cwrite, c2pread, "
    "c2pwrite, errread, errwrite, errpipe_read, errpipe_write, restore_signals, call_setsid, "
    "pgid_to_set, gid, extra_groups, uid, child_umask, preexec_fn"
)
if sys.version_info >= (3, 14):
    _FORK_EXEC_PARAMETERS: Final = f"{_FORK_EXEC_COMMON}, /"
    _FORK_EXEC_TAIL: Final[tuple[bool, ...]] = ()
else:
    _FORK_EXEC_PARAMETERS: Final = f"{_FORK_EXEC_COMMON}, allow_vfork, /"
    _FORK_EXEC_TAIL: Final[tuple[bool, ...]] = (True,)  # allow_vfork
_HANDSHAKE_SECONDS = 30.0
_ABORT_SECONDS = 5.0
_POLL_SECONDS = 0.02
_INHERITED: Final = "process_ownership_inherited: this process forked after the owner took the child"
_log = get_logger("platform.process")
_retained_guard = threading.Lock()
_retained: set["OwnedProcess"] = set()
# Cleanups no worker is running, with the worker's name: nothing settles them until recover_cleanups.
_unattended: dict[Callable[[], bool], str] = {}
_recovery_lock = threading.Lock()
# Who may use what this module holds. A pid can return to a later descendant, and a fork that skips
# Python's handlers (ctypes, an extension) replaces no token, so a holder has to match both.
_owner: tuple[int, object] = (os.getpid(), object())
_first_owner: Final = _owner
# Stays referenced in a forked child: a destructor run by the release could wait on an orphaned lock.
_inherited: list[object] = []

# -I keeps the working directory and PYTHON* out of sys.path, so a planted socket.py cannot run
# here. Python ignores SIGPIPE and SIGXFSZ at startup; the target gets the defaults back, as
# Popen's restore_signals gives. The lookup order and the reported errno also follow Popen.
# The working directory changes here, after the bind, so a bad one fails with an owned child.
_BOOTSTRAP: Final = r"""
import errno, marshal, os, signal, socket, sys
channel = socket.socket(fileno=int(sys.argv[1]))
os.set_inheritable(channel.fileno(), False)
pidfd = os.pidfd_open(os.getpid())
socket.send_fds(channel, [b"\0"], [pidfd])
os.close(pidfd)
request = bytearray()
while chunk := channel.recv(65536):
    request += chunk
if not request:
    os._exit(125)
failure, first, stage = errno.EIO, 0, "exec"
try:
    workdir, paths, argv, env, merge_stderr = marshal.loads(request)
    if merge_stderr:
        os.dup2(1, 2)
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    signal.signal(signal.SIGXFSZ, signal.SIG_DFL)
    try:
        os.chdir(workdir)
    except OSError as error:
        failure, stage, paths = error.errno, "cwd", []
    for path in paths:
        try:
            os.execve(path, argv, env)
        except OSError as error:
            failure = error.errno
            if not first and failure not in (errno.ENOENT, errno.ENOTDIR):
                first = failure
except BaseException:
    pass
channel.sendall(f"{stage}:{first or failure}".encode("ascii"))
os._exit(127)
"""


class OwnershipUnavailable(OSError):
    """No kernel-enforced identity can be held for a child; nothing may be started or signalled."""


def _after_fork_in_child() -> None:
    global _retained_guard, _retained, _unattended, _recovery_lock, _owner  # noqa: PLW0603 - see below
    # Every other thread is gone, and any lock it held stays locked here. The owner changes last:
    # a failure before it leaves the parent's pid, which refuses like a fork no handler saw.
    guard, recovery = threading.Lock(), threading.Lock()
    retained: set[OwnedProcess] = set()
    unattended: dict[Callable[[], bool], str] = {}
    owner = (os.getpid(), object())
    _inherited.append((_retained, _unattended))
    _retained_guard, _recovery_lock, _retained, _unattended = guard, recovery, retained, unattended
    _owner = owner


os.register_at_fork(after_in_child=_after_fork_in_child)


def _fork_unseen() -> bool:
    """This process forked past the handler: its locks and lists are the parent's, as they were."""
    return _owner[0] != os.getpid()


@dataclass(slots=True)
class ChildPipes:
    """The owner's ends of a child's standard streams. ``pid`` is diagnostic and offers no wait."""

    pid: int
    stdin: IO[bytes]
    stdout: IO[bytes]
    stderr: IO[bytes]


def _fork_exec() -> Callable[..., int]:
    return vars(subprocess)["_fork_exec"]


def _fork_exec_signature() -> str | None:
    text = getattr(_fork_exec(), "__text_signature__", None)
    return None if text is None else re.sub(r"\s+", " ", text).strip("()")


def require_support() -> None:
    if _fork_unseen():
        raise OwnershipUnavailable("process_ownership_unavailable: forked past the fork handlers")
    if sys.platform != "linux":
        raise OwnershipUnavailable(f"process_ownership_unavailable: no pidfd on {sys.platform}")
    for module, name in _REQUIRED_API:
        if not hasattr(module, name):
            raise OwnershipUnavailable(f"process_ownership_unavailable: Python lacks {name}")
    # A missing interpreter fails here, with nothing started and no zombie left behind.
    if not sys.executable or not os.access(sys.executable, os.X_OK):
        raise OwnershipUnavailable("process_ownership_unavailable: no interpreter for the bootstrap")
    if _fork_exec_signature() != _FORK_EXEC_PARAMETERS:
        raise OwnershipUnavailable("process_ownership_unavailable: unknown fork_exec parameters")
    try:
        probe = os.pidfd_open(os.getpid())
    except OSError as error:
        raise OwnershipUnavailable(f"process_ownership_unavailable: pidfd_open: {error}") from error
    try:
        # Signal 0 delivers nothing. ESRCH only says this process leads no group: the flag was accepted.
        signal.pidfd_send_signal(probe, 0, None, _PIDFD_SIGNAL_PROCESS_GROUP)
    except ProcessLookupError:
        pass
    except OSError as error:
        raise OwnershipUnavailable(
            f"process_ownership_unavailable: no pidfd process-group signal (Linux 6.9): {error}"
        ) from error
    finally:
        os.close(probe)


def _enable_subreaper() -> None:
    # The flag belongs to the process. Setting it again is safe across concurrent launches
    # and picks up a reset by the host. Closing a single child's pidfd leaves it enabled.
    operation = "process_ownership_unavailable: PR_SET_CHILD_SUBREAPER"
    try:
        prctl = ctypes.CDLL(None, use_errno=True).prctl
        prctl.argtypes = (ctypes.c_int,)
    except (AttributeError, OSError) as error:
        raise OwnershipUnavailable(f"{operation}: {error}") from error
    zero = ctypes.c_ulong(0)
    if prctl(_PR_SET_CHILD_SUBREAPER, ctypes.c_ulong(1), zero, zero, zero) != 0:
        code = ctypes.get_errno()
        raise OwnershipUnavailable(code, f"{operation}: {os.strerror(code)}")


class OwnedProcess:
    """The pidfd of one child and its group. ``pid`` is diagnostic only and grants nothing."""

    def __init__(self, pid: int, pidfd: int) -> None:
        self.pid = pid
        self.identity = ProcessIdentity(pid, None, None)
        self._pidfd: int | None = pidfd
        # A closed number may name another descriptor, so every use holds this lock.
        self._lock = threading.Lock()
        self._owner = _owner

    def held_here(self) -> bool:
        """False in a forked child, whose copy of this object, lock included, belongs to the parent."""
        return self._owner is _owner and self._owner[0] == os.getpid()

    def require_here(self) -> None:
        if not self.held_here():
            raise OwnershipUnavailable(_INHERITED)

    def signal_group(self, sig: int) -> bool:
        """Signal exactly this group. False: it is empty, for good."""
        self.require_here()
        with self._lock:
            if self._pidfd is None:
                return False
            try:
                signal.pidfd_send_signal(self._pidfd, sig, None, _PIDFD_SIGNAL_PROCESS_GROUP)
            except ProcessLookupError:
                return False
            return True

    def group_alive(self) -> bool:
        """Whether this group has a member that is not a zombie.

        An emptied ``struct pid`` never refills and its number stays assigned until then, so a
        group that still exists after the scan is the group the scan read.
        """
        return self.signal_group(0) and group_alive(self.pid) and self.signal_group(0)

    def _wait(self, options: int) -> int | None:
        self.require_here()
        with self._lock:
            if self._pidfd is None:
                raise ChildProcessError(errno.ECHILD, "process ownership closed")
            result = os.waitid(os.P_PIDFD, self._pidfd, os.WEXITED | os.WNOHANG | options)
        if result is None:
            return None
        return result.si_status if result.si_code == os.CLD_EXITED else -result.si_status

    def exit_code(self) -> int | None:
        """Observe the exit without consuming it. ChildProcessError: the status went elsewhere."""
        return self._wait(os.WNOWAIT)

    def reap(self, timeout: float = 0) -> int | None:
        """Consume the status within the bound. None: not exited. ChildProcessError: went elsewhere."""
        deadline = time.monotonic() + timeout
        pause = threading.Event()
        while True:
            code = self._wait(0)
            remaining = deadline - time.monotonic()
            if code is not None or remaining <= 0:
                return code
            pause.wait(min(_POLL_SECONDS, remaining))

    def close(self) -> None:
        if not self.held_here():
            return
        with self._lock:
            pidfd, self._pidfd = self._pidfd, None
        if pidfd is not None:
            os.close(pidfd)

    def __del__(self) -> None:
        self.close()


def add_note(primary: BaseException, text: str) -> None:
    # A note is evidence: it never takes the place of the primary failure or of the cleanup after it.
    with suppress(BaseException):
        primary.add_note(text)


def describe_failure(error: BaseException) -> str:
    """The text of a failure for a note. Reading it never raises, so it cannot interrupt a cleanup."""
    try:
        return str(error)
    except BaseException:  # noqa: BLE001 - the text is evidence, the cleanup comes first
        return f"<unprintable {type(error).__name__}>"


def _close_all(*closers: Callable[[], None]) -> list[BaseException]:
    """Run each close once and return the failures. A failed close is not retried: the number is gone."""
    failures: list[BaseException] = []
    for close in closers:
        try:
            close()
        except BaseException as error:  # noqa: BLE001 - close the rest, the caller decides
            failures.append(error)
    return failures


def _report_unattended() -> None:
    # Outlives a note on an exception nobody reads, and never stops the cleanup it reports.
    # A forked child stays silent: the log's locks may be held by a thread that did not cross the fork.
    if _owner is _first_owner:
        with suppress(BaseException):
            _log.error("platform.process.cleanup_worker_not_running")


def _report_recovered() -> None:
    if _owner is _first_owner:
        with suppress(BaseException):
            _log.info("platform.process.cleanup_worker_recovered")


def _attend(step: Callable[[], bool], name: str) -> None:
    pause = threading.Event()
    try:
        while not step():
            # A running worker needs no new thread to give the listed cleanups another step.
            if _unattended and _recovery_lock.acquire(blocking=False):
                try:
                    _recover_pass()
                finally:
                    _recovery_lock.release()
            pause.wait(_POLL_SECONDS)
    except BaseException:
        # This worker ends here, so the cleanup goes back to having none.
        with _retained_guard:
            _unattended[step] = name
        _report_unattended()
        raise


def _start_worker(step: Callable[[], bool], name: str) -> BaseException | None:
    try:
        threading.Thread(target=_attend, args=(step, name), name=name, daemon=True).start()
    except BaseException as error:  # noqa: BLE001 - the registry still holds the pidfd
        return error
    return None


def start_cleanup_worker(step: Callable[[], bool], name: str) -> BaseException | None:
    """Repeat ``step`` on a daemon thread until it returns True.

    A worker that cannot start is returned as a failure and its cleanup is listed. Whatever still
    runs retries it: ``adopt_cleanup``, a live worker, ``launch`` and the exit of the owner. If none
    of them runs, no cleanup does either, and callers must say so.
    """
    if _fork_unseen():
        return OwnershipUnavailable(_INHERITED)
    failure = _start_worker(step, name)
    if failure is not None:
        with _retained_guard:
            _unattended[step] = name
        _report_unattended()
    return failure


def adopt_cleanup(step: Callable[[], bool]) -> None:
    """Run a listed cleanup on the calling thread until it settles. Not listed: nothing to do.

    This is for a thread that has nothing else to do, so it replaces the worker that could not start.
    """
    if _fork_unseen():
        return
    with _retained_guard:
        name = _unattended.pop(step, None)
    if name is not None:
        _report_recovered()
        _attend(step, name)


def unattended_note(error: BaseException) -> str:
    return f"cleanup_worker_not_running: {describe_failure(error)}; ownership retained until recover_cleanups"


def supervised_note(error: BaseException) -> str:
    return f"cleanup_worker_not_started: {describe_failure(error)}; the process supervisor thread attends it"


def _recover_pass() -> None:
    with _retained_guard:
        waiting = tuple(_unattended.items())
    for step, name in waiting:
        try:
            settled = step()
        except Exception:  # noqa: BLE001, S112 - stays listed for the next pass
            continue
        with _retained_guard:
            if _unattended.pop(step, None) is None:
                # Another thread adopted it during the step.
                continue
        failure = None if settled else _start_worker(step, name)
        if failure is None:
            _report_recovered()
        else:
            with _retained_guard:
                _unattended[step] = name


def recover_cleanups() -> tuple[str, ...]:
    """Take over the cleanups that have no worker. Returns the names of those still without one.

    Each gets one bounded step here, which needs no thread, then a new worker. A step or a worker
    that fails again keeps its cleanup listed. ``launch`` calls this, so every later start retries,
    and so does the exit of the owner, whose step still reaches the group through the pidfd.

    A forked child inherits this function and its ``atexit`` entry, not the list: it recovers only
    what it started itself.
    """
    if _fork_unseen():
        return ()
    with _recovery_lock:
        _recover_pass()
        with _retained_guard:
            return tuple(_unattended.values())


atexit.register(recover_cleanups)


def _settle_retained(owned: OwnedProcess) -> bool:
    if not owned.held_here():
        # Settled as far as this process goes: the cleanup stays with the owner.
        return True
    try:
        owned.signal_group(signal.SIGKILL)
        if owned.group_alive():
            return False
        try:
            if owned.reap() is None:
                return False
        except ChildProcessError:
            # Reaped by discard or consumed elsewhere; the group is empty either way.
            pass
        owned.close()
    except OSError:
        # The start already failed and reported it; only the pidfd can still finish this.
        return False
    with _retained_guard:
        _retained.discard(owned)
    return True


def _retain(owned: OwnedProcess, primary: BaseException) -> None:
    # The registry alone keeps the pidfd open, so a worker that cannot start loses no authority.
    with _retained_guard:
        _retained.add(owned)
    failure = start_cleanup_worker(partial(_settle_retained, owned), f"skm-discard-{owned.pid}")
    if failure is not None:
        add_note(primary, unattended_note(failure))


def discard(pipes: ChildPipes, owned: OwnedProcess | None, primary: BaseException) -> None:
    """Undo a failed start. Only a verified pidfd can kill or reap; failures annotate ``primary``.

    The pidfd closes only after a confirmed reap and an empty group. Until then it is retained.
    """
    try:
        if owned is not None and not owned.held_here():
            add_note(primary, f"process setup cleanup skipped: {_INHERITED}")
        elif owned is not None:
            try:
                owned.signal_group(signal.SIGKILL)
                if owned.reap(_ABORT_SECONDS) is None:
                    raise TimeoutError("child_reap_unconfirmed")
                if owned.group_alive():
                    raise TimeoutError("process_group_cleanup_unconfirmed")
                owned.close()
            except BaseException as error:  # noqa: BLE001 - cleanup is secondary to setup failure
                _retain(owned, primary)
                text = describe_failure(error)
                add_note(primary, f"process setup cleanup failed: {text}; ownership retained")
    finally:
        for failure in _close_all(pipes.stdin.close, pipes.stdout.close, pipes.stderr.close):
            add_note(primary, f"process setup pipe cleanup failed: {describe_failure(failure)}")


def _pidfd_target(pidfd: int) -> int | None:
    for line in (Path("/proc/self/fdinfo") / str(pidfd)).read_text().splitlines():
        if line.startswith("Pid:"):
            return int(line.split()[1])
    return None


def _bind(channel: socket.socket, pid: int) -> OwnedProcess:
    channel.settimeout(_HANDSHAKE_SECONDS)
    try:
        received = socket.recv_fds(channel, 1, 1, socket.MSG_CMSG_CLOEXEC)[1]
        if not received:
            raise OwnershipUnavailable("process_ownership_unbound: child sent no pidfd")
        target = None
        try:
            target = _pidfd_target(received[0])
        finally:
            if target != pid:
                os.close(received[0])
        if target != pid:
            raise OwnershipUnavailable("process_ownership_unbound: received descriptor names another process")
    except OwnershipUnavailable:
        raise
    except (OSError, ValueError, IndexError) as error:
        raise OwnershipUnavailable(f"process_ownership_unbound: {describe_failure(error)}") from error
    return OwnedProcess(pid, received[0])


def _hold(owned: OwnedProcess) -> None:
    # The bootstrap waits for its request. Check its pidfd after reading /proc so a child that
    # died during the read cannot bind a reused number's start ticks.
    identity = identity_of(owned.pid)
    if identity is None or owned.exit_code() is not None or not owned.signal_group(0):
        raise OwnershipUnavailable("process_ownership_unbound: child left before release")
    if identity.start_ticks is None:
        raise OwnershipUnavailable("process_ownership_unbound: child start ticks unavailable")
    owned.identity = identity


def _release(channel: socket.socket, request: bytes, executable: str, cwd: Path) -> None:
    channel.sendall(request)
    channel.shutdown(socket.SHUT_WR)
    reply = bytearray()
    # The child's end closes on a successful execve, like Popen's error pipe.
    while chunk := channel.recv(64):
        reply += chunk
    if reply:
        stage, _, number = reply.decode("ascii").partition(":")
        code = int(number)
        raise OSError(code, os.strerror(code), os.fspath(cwd) if stage == "cwd" else executable)


def _exec_paths(executable: str, env: Mapping[str, str]) -> list[bytes]:
    if os.path.dirname(executable):
        return [os.fsencode(executable)]
    name = os.fsencode(executable)
    return [os.path.join(os.fsencode(entry), name) for entry in os.get_exec_path(env)]


def _own_pipe(fds: list[int], fd: int, mode: str) -> IO[bytes]:
    """Move ``fd`` from ``fds`` into a stream. It is closed at most once whatever happens."""
    pipe = os.fstat(fd)
    fds.remove(fd)
    try:
        return os.fdopen(fd, mode, 0)
    except BaseException as primary:
        # fdopen leaves a refused descriptor open but closes it on a later failure, and by then
        # the number may name another file. Only the same pipe is still ours to close.
        try:
            if os.path.samestat(os.fstat(fd), pipe):
                os.close(fd)
        except OSError as error:
            if error.errno != errno.EBADF:
                add_note(primary, f"process setup pipe cleanup failed: {describe_failure(error)}")
        raise


def _fork_bootstrap(channel: int, failures: list[BaseException]) -> tuple[ChildPipes, int]:
    """Start the bootstrap in a new session. Returns its pipes and the read end of its error report.

    Only ``fork_exec`` runs here, with the arguments ``Popen`` gives it, and nothing waits afterwards.
    Whatever can refuse runs before the fork, so a raised failure leaves no child. A close that fails
    after the fork lands in ``failures``, because only the caller can bind that child and discard it.
    """
    fds: list[int] = []
    files: list[IO[bytes]] = []
    try:
        for _ in range(4):
            fds.extend(os.pipe())
        stdin_read, stdin_write, stdout_read, stdout_write = fds[:4]
        stderr_read, stderr_write, report_read, report = fds[4:]
        # fork_exec keeps only descriptors above stdio, where its own dup2 calls cannot overwrite them.
        kept_channel = fcntl.fcntl(channel, fcntl.F_DUPFD_CLOEXEC, 3)
        fds.append(kept_channel)
        report_write = fcntl.fcntl(report, fcntl.F_DUPFD_CLOEXEC, 3)
        fds.append(report_write)
        for fd, mode in ((stdin_write, "wb"), (stdout_read, "rb"), (stderr_read, "rb")):
            files.append(_own_pipe(fds, fd, mode))
        # The number arrives with the fork; nothing reads it before that.
        pipes = ChildPipes(0, files[0], files[1], files[2])
        args = [sys.executable, "-I", "-S", "-B", "-c", _BOOTSTRAP, str(kept_channel)]
        sys.audit("subprocess.Popen", sys.executable, args, None, {})
        pipes.pid = _fork_exec()(
            args,
            (os.fsencode(sys.executable),),
            True,  # close_fds
            tuple(sorted((kept_channel, report_write))),
            None,  # cwd: changed by the bootstrap after the bind
            [],  # env
            stdin_read,
            stdin_write,
            stdout_read,
            stdout_write,
            stderr_read,
            stderr_write,
            report_read,
            report_write,
            True,  # restore_signals
            True,  # call_setsid
            -1,  # pgid_to_set
            None,  # gid
            None,  # extra_groups
            None,  # uid
            -1,  # child_umask
            None,  # preexec_fn
            *_FORK_EXEC_TAIL,
        )
    except BaseException as primary:
        closers = [file.close for file in files] + [partial(os.close, fd) for fd in fds]
        for failure in _close_all(*closers):
            add_note(primary, f"process setup pipe cleanup failed: {describe_failure(failure)}")
        raise
    failures.extend(
        _close_all(
            *(
                partial(os.close, fd)
                for fd in (stdin_read, stdout_write, stderr_write, report, kept_channel, report_write)
            )
        )
    )
    return pipes, report_read


def _note_failed_start(report: int, primary: BaseException) -> None:
    # Never blocks: a bootstrap that is merely silent still holds the write end open.
    # Never raises: this report is a diagnostic, and the discard after it holds the child's cleanup.
    try:
        os.set_blocking(report, False)
        data = os.read(report, 4096)
    except BlockingIOError:
        return
    except BaseException as error:  # noqa: BLE001 - diagnostics cannot bypass the discard
        add_note(primary, f"bootstrap report unavailable: {describe_failure(error)}")
        return
    if data:
        add_note(primary, f"bootstrap did not start: {data.decode('ascii', 'replace')}")


def launch(
    argv: tuple[str, ...], *, cwd: Path, env: Mapping[str, str], merge_stderr: bool = False
) -> tuple[ChildPipes, OwnedProcess]:
    """Start ``argv`` in a new session and return its pipes and the verified owner."""
    require_support()
    recover_cleanups()
    workdir = os.fsencode(cwd)
    if b"\0" in workdir:
        raise ValueError("embedded null byte in cwd")
    request = marshal.dumps(
        (
            workdir,
            _exec_paths(argv[0], env),
            [os.fsencode(item) for item in argv],
            {os.fsencode(name): os.fsencode(value) for name, value in env.items()},
            merge_stderr,
        )
    )
    _enable_subreaper()
    ours, theirs = socket.socketpair()
    failures: list[BaseException] = []
    try:
        pipes, report = _fork_bootstrap(theirs.fileno(), failures)
    except BaseException as primary:
        for failure in _close_all(theirs.close, ours.close):
            add_note(primary, f"process setup close failed: {describe_failure(failure)}")
        raise
    # A child exists from here on: a failed close must reach the discard, with the pidfd if it can.
    failures.extend(_close_all(theirs.close))
    owned: OwnedProcess | None = None
    try:
        owned = _bind(ours, pipes.pid)
        _hold(owned)
        if failures:
            raise failures[0]
        _release(ours, request, argv[0], cwd)
    except BaseException as primary:
        for failure in failures:
            if failure is not primary:
                add_note(primary, f"process setup close failed: {describe_failure(failure)}")
        _note_failed_start(report, primary)
        discard(pipes, owned, primary)
        for failure in _close_all(partial(os.close, report), ours.close):
            add_note(primary, f"process setup close failed: {describe_failure(failure)}")
        raise
    failures = _close_all(partial(os.close, report), ours.close)
    if failures:
        # The caller gets no handle from a raise, so nothing else could own the released target.
        for failure in failures[1:]:
            add_note(failures[0], f"process setup close failed: {describe_failure(failure)}")
        discard(pipes, owned, failures[0])
        raise failures[0]
    return pipes, owned
