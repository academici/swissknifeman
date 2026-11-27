"""Explicit argv/env execution with bounded pipes and pidfd-owned group supervision.

Every signal and wait goes through ``OwnedProcess``, so a reused number cannot be reached.
Group emptiness does not prove containment of descendants that escaped with setsid/double-fork.
"""

import math
import os
import signal
import threading
import time
from collections import deque
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Final

from skm.kernel.cancel import CancelSource
from skm.platform.process.argv_rules import check_argv
from skm.platform.process.environment import build_env
from skm.platform.process.identity import ProcessIdentity
from skm.platform.process.ownership import (
    ChildPipes,
    OwnedProcess,
    add_note,
    adopt_cleanup,
    describe_failure,
    discard,
    launch,
    start_cleanup_worker,
    supervised_note,
    unattended_note,
)
from skm.platform.process.streams import BoundedCapture, ProcessStreams
from skm.platform.system_clock import SystemClock

__all__ = ["TIMEOUT_EXIT", "ProcessHandle", "ProcessResult", "TerminationResult", "run", "spawn"]

TIMEOUT_EXIT: Final = 124
_POLL_SECONDS = 0.02
_DRAIN_SECONDS = 0.25
_KILL_WAIT_SECONDS = 5.0
_STATUS_UNKNOWN: Final = "process_status_unknown: child status consumed outside owner"
_pending_guard = threading.Lock()
_pending_children: set["_Child"] = set()
_cleanup_failures: deque[tuple[ProcessIdentity, str]] = deque(maxlen=128)
# Stays referenced in a forked child: releasing a child there would run destructors of its callbacks.
_inherited: list[set["_Child"]] = []


def _after_fork_in_child() -> None:
    global _pending_guard, _pending_children, _cleanup_failures
    guard = threading.Lock()
    children: set[_Child] = set()
    failures: deque[tuple[ProcessIdentity, str]] = deque(maxlen=128)
    _inherited.append(_pending_children)
    _pending_guard, _pending_children, _cleanup_failures = guard, children, failures


os.register_at_fork(after_in_child=_after_fork_in_child)


class _CleanupPending(Exception):
    """The bounded synchronous cleanup ended; ownership must outlive run(). None: status unknown."""

    def __init__(self, exit_code: int | None) -> None:
        self.exit_code = exit_code
        super().__init__(exit_code)


class _StatusLost(ProcessLookupError):
    """A foreign waiter consumed the status. The group stays addressable; the outcome stays unknown."""


@dataclass(frozen=True, slots=True)
class ProcessResult:
    argv: tuple[str, ...]
    exit_code: int
    stdout: bytes
    stderr: bytes
    timed_out: bool
    stdout_truncated: bool
    stderr_truncated: bool
    duration_seconds: float
    signal: int | None


@dataclass(frozen=True, slots=True)
class TerminationResult:
    signal_sent: int
    exited: bool
    ignored: bool
    reason: str | None


def _seconds(value: float, name: str) -> None:
    if isinstance(value, bool) or not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and non-negative")


def _limit(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError("output limits must be non-negative integers")


def _start(
    argv: tuple[str, ...], cwd: Path, env: Mapping[str, str], *, merge_stderr: bool = False
) -> tuple[ChildPipes, OwnedProcess]:
    if not isinstance(env, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError("an explicit environment mapping is required")
    return launch(argv, cwd=cwd, env=build_env({}, extra=env), merge_stderr=merge_stderr)


class _Child:
    def __init__(
        self,
        proc: ChildPipes,
        owned: OwnedProcess,
        on_stdout: Callable[[bytes], None],
        on_stderr: Callable[[bytes], None],
        *,
        line_mode: bool,
        stdin: bytes | None,
        manage_stdin: bool,
    ) -> None:
        self.proc = proc
        self.owned = owned
        self.identity = owned.identity
        self.status: int | None = None
        self.guard = threading.RLock()
        self.input_lock = threading.Lock()
        self.held = True
        self.stopped = False
        self.supervised = False
        self._exited = False
        self._leader_code: int | None = None
        self.done = threading.Event()
        self.error: BaseException | None = None
        self.primary: BaseException | None = None
        self.cleanup_error: BaseException | None = None
        self.timed_out = False
        self.pause = CancelSource().token
        try:
            self.started_at = SystemClock().now()
            self.started = time.monotonic()
            self.streams = ProcessStreams(
                proc, on_stdout, on_stderr, line_mode=line_mode, stdin=stdin, manage_stdin=manage_stdin
            )
        except BaseException as primary:
            discard(proc, owned, primary)
            raise

    def send(self, sig: int) -> bool:
        self.owned.require_here()
        with self.guard:
            if self.stopped:
                return False
            return self.owned.signal_group(sig)

    def leader_exited(self) -> bool:
        self.owned.require_here()
        with self.guard:
            if self._exited or not self.held:
                return True
            try:
                code = self.owned.exit_code()
            except ChildProcessError:
                # Group cleanup is still exact; _reap reports the unknown status at the end.
                self.held = False
                return True
            self._exited = code is not None
            self._leader_code = code
            return self._exited

    def _close(self, primary: BaseException | None) -> None:
        for operation in (self.streams.close, self.close_stdin):
            try:
                operation()
            except BaseException as error:  # noqa: BLE001 - close all pipes before raising
                if primary is None:
                    primary = error
                else:
                    add_note(primary, f"pipe cleanup failed: {describe_failure(error)}")
        if primary is not None:
            raise primary

    def close_stdin(self) -> None:
        self.owned.require_here()
        with self.input_lock:
            self.proc.stdin.close()

    @property
    def leader_code(self) -> int | None:
        return self._leader_code

    def _status_lost(self) -> bool:
        # A fresh probe: a cached exit says nothing about who consumed the status since.
        with self.guard:
            if self.status is not None:
                return False
            if not self.held:
                return True
            try:
                self.owned.exit_code()
            except ChildProcessError:
                self.held = False
                return True
            except OSError:
                # Not proof of a loss; the retained worker keeps observing it.
                pass
            return False

    def _reap(self) -> int:
        # Consume our own wait status within the bound, or report it as unknown.
        if self.status is not None:
            return self.status
        if self.held:
            try:
                self.status = self.owned.reap(_KILL_WAIT_SECONDS)
            except ChildProcessError:
                self.held = False
            else:
                if self.status is None:
                    raise TimeoutError("child_reap_unconfirmed")
                self.held = False
                return self.status
        raise _StatusLost(_STATUS_UNKNOWN)

    def _settle(self, empty: bool) -> None:
        self.stopped = empty
        if empty:
            self.owned.close()

    def collect(self, timeout: float | None, grace: float) -> int:
        primary: BaseException | None = None
        empty = False
        try:
            self._drain(timeout, grace)
            empty = True
        except _CleanupPending as pending:
            # Keep the observed status distinct from timeout and unfinished cleanup.
            self.owned.require_here()
            return self._defer(None, pending.exit_code)
        except BaseException as error:  # noqa: BLE001 - retain callback/IO failure across cleanup
            # A callback forked and its child came back here: no cleanup below is the child's.
            self.owned.require_here()
            if self.timed_out and isinstance(error, OSError):
                return self._defer(error, TIMEOUT_EXIT)
            primary = error
            try:
                self.send(signal.SIGKILL)
            except BaseException as cleanup:  # noqa: BLE001 - retain the primary failure
                add_note(primary, f"process group cleanup failed: {describe_failure(cleanup)}")
        self.owned.require_here()
        try:
            with self.guard:
                code = self._reap()
                self._settle(empty)
        except BaseException as error:  # noqa: BLE001 - retain the primary failure
            code = TIMEOUT_EXIT
            if primary is None:
                primary = error
            else:
                add_note(primary, f"child reap failed: {describe_failure(error)}")
        if self.stopped:
            self._close(primary)
            return code
        # A failed signal or reap leaves a live child: the pidfd outlives the failure. The worker
        # starts after the pipes close, because its finish releases waiters.
        self.primary = self.error = primary
        try:
            self._close(primary)
        finally:
            self._retain()
        return code

    def _defer(self, primary: BaseException | None, exit_code: int | None) -> int:
        lost = False
        try:
            lost = self._status_lost()
        except BaseException as error:  # noqa: BLE001 - a failed probe cannot skip the retention
            self.error = error
        # Pipes are closed before returning, so capture callbacks cannot race the result.
        try:
            self._close(primary)
        except BaseException as error:  # noqa: BLE001 - preserve the primary public outcome
            self.error = error
        failure = self._retain()
        if exit_code is None or lost:
            # Cleanup goes on, but a known loss is never reported as an exit code or a timeout.
            unknown = _StatusLost(_STATUS_UNKNOWN)
            if primary is not None:
                add_note(unknown, f"process group cleanup failed: {describe_failure(primary)}")
            if failure is not None:
                add_note(unknown, unattended_note(failure))
            raise unknown from None
        if failure is not None:
            # A plain result would say cleanup goes on behind it, and nothing is running it.
            add_note(failure, unattended_note(failure))
            add_note(failure, f"exit code observed before cleanup: {exit_code}")
            if primary is not None:
                add_note(failure, f"process group cleanup failed: {describe_failure(primary)}")
            raise failure
        return exit_code

    def _retain(self) -> BaseException | None:
        """Hold ownership until empty-group proof + reap. The failure: no worker could start for it."""
        with _pending_guard:
            _pending_children.add(self)
        failure = start_cleanup_worker(self._reap_step, f"skm-reap-{self.proc.pid}")
        if failure is not None:
            self._cleanup_failed(failure)
            with _pending_guard:
                _cleanup_failures.append((self.identity, describe_failure(failure)))
            if self.primary is not None:
                note = supervised_note if self.supervised else unattended_note
                add_note(self.primary, note(failure))
        return failure

    def _cleanup_failed(self, error: BaseException) -> None:
        self.cleanup_error = error
        if self.primary is None:
            self.error = error

    def _reap_step(self) -> bool:
        if not self.owned.held_here():
            # Settled as far as this process goes: the cleanup stays with the owner.
            return True
        try:
            exited = self.leader_exited()
            self.send(signal.SIGKILL)
            if exited and not self.owned.group_alive():
                with self.guard:
                    self._reap()
                    self._settle(True)
                self._finish_pending()
                return True
        except _StatusLost as error:
            self._cleanup_failed(error)
            self.owned.close()
            self._finish_pending()
            return True
        except OSError as error:
            self._cleanup_failed(error)
        return False

    def _finish_pending(self) -> None:
        with _pending_guard:
            _pending_children.discard(self)
            if not self.stopped and self.cleanup_error is not None:
                _cleanup_failures.append((self.identity, describe_failure(self.cleanup_error)))
        self.done.set()

    def _drain(self, timeout: float | None, grace: float) -> None:
        deadline = None if timeout is None else self.started + timeout
        term_until: float | None = None
        kill_until: float | None = None
        drain_until: float | None = None
        cleanup_until: float | None = None
        while True:
            now = time.monotonic()
            exited = self.leader_exited()
            if exited and drain_until is None:
                self.send(signal.SIGKILL)
                if timeout is None and kill_until is None:
                    kill_until = now + _KILL_WAIT_SECONDS
                drain_until = now + _DRAIN_SECONDS
                cleanup_until = now + grace
                self.streams.drop("stdin")
            if not self.timed_out and deadline is not None and now >= deadline:
                self.timed_out = True
                self.send(signal.SIGTERM)
                term_until = now + grace
            if (
                exited
                and not self.owned.group_alive()
                and (not self.streams.has_output or (drain_until is not None and now >= drain_until))
            ):
                self.streams.finish()
                return
            if (
                exited
                and not self.timed_out
                and timeout is not None
                and cleanup_until is not None
                and now >= cleanup_until
            ):
                self.streams.step(0)
                self.streams.finish()
                raise _CleanupPending(self._leader_code)
            if term_until is not None and kill_until is None and now >= term_until:
                self.send(signal.SIGKILL)
                kill_until = now + _KILL_WAIT_SECONDS
            if kill_until is not None and now >= kill_until:
                if timeout is not None:
                    raise _CleanupPending(TIMEOUT_EXIT)
                # A streaming handle remains available to report ignored cancellation.
                self.send(signal.SIGKILL)
                kill_until = now + _KILL_WAIT_SECONDS
            horizons = [now + _POLL_SECONDS]
            horizons.extend(
                value
                for value in (deadline, term_until, kill_until, drain_until, cleanup_until)
                if value is not None and value > now
            )
            delay = max(0.0, min(horizons) - now)
            if self.streams.selector.get_map():
                self.streams.step(delay)
            else:
                self.pause.wait(delay)

    def background(self) -> None:
        self.supervised = True
        try:
            self.collect(None, 0)
        except BaseException as error:  # noqa: BLE001 - publish the failure to wait(), including interrupts
            self.error = error
        finally:
            # A forked copy of this thread has no one to release, and this event's lock is the parent's.
            if self.owned.held_here():
                self.done.set()
        # This thread already runs, so a worker that could not start costs no new one. After done,
        # because a cleanup that never settles must not hold wait() back.
        adopt_cleanup(self._reap_step)


class ProcessHandle:
    """A live child owned by this handle, with a single pipe supervisor thread."""

    pid: int
    pgid: int
    started_at: datetime
    identity: ProcessIdentity

    def __init__(self, child: _Child) -> None:
        self._child = child
        self.pid = self.pgid = child.proc.pid
        self.started_at = child.started_at
        self.identity = child.identity
        self._termination_lock = threading.Lock()
        self._termination: TerminationResult | None = None
        try:
            self._thread = threading.Thread(
                target=child.background, name=f"skm-process-{self.pid}", daemon=True
            )
            os.set_blocking(child.proc.stdin.fileno(), False)
            self._thread.start()
        except BaseException as primary:
            # The selector needs each file open to forget it, so the streams close first. The discard
            # runs whatever that raises and closes the rest; it finds closed files already closed.
            try:
                child.streams.close()
            except BaseException as cleanup:  # noqa: BLE001 - preserve thread startup failure
                add_note(primary, f"pipe cleanup failed: {describe_failure(cleanup)}")
            discard(child.proc, child.owned, primary)
            raise

    def write_stdin(self, data: bytes) -> None:
        self._child.owned.require_here()
        remaining = memoryview(data)
        while remaining:
            with self._child.input_lock:
                pipe = self._child.proc.stdin
                if pipe.closed:
                    raise ValueError("process stdin is closed")
                try:
                    written = os.write(pipe.fileno(), remaining[:65_536])
                except BlockingIOError:
                    written = 0
                remaining = remaining[written:]
            if not written:
                self._child.pause.wait(_POLL_SECONDS)

    def close_stdin(self) -> None:
        self._child.close_stdin()

    def wait(self, timeout_seconds: float | None = None) -> int | None:
        if timeout_seconds is not None:
            _seconds(timeout_seconds, "timeout_seconds")
        self._child.owned.require_here()
        if not self._child.done.wait(timeout_seconds):
            return None
        if self._child.error is not None:
            raise self._child.error
        return self._child.status

    def _stopped_within(self, seconds: float) -> bool:
        deadline = time.monotonic() + seconds
        while not self._child.stopped and self._child.owned.group_alive():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            self._child.pause.wait(min(_POLL_SECONDS, remaining))
        return True

    def terminate(self, *, grace_seconds: float = 10.0) -> TerminationResult:
        _seconds(grace_seconds, "grace_seconds")
        if not self._child.owned.held_here():
            return TerminationResult(0, False, False, "process_ownership_inherited")
        with self._termination_lock:
            if self._termination is not None and (
                self._termination.exited or (self._child.stopped and self._child.done.is_set())
            ):
                return self._termination
            result = self._terminate(grace_seconds)
            self._termination = result
            return result

    def _terminate(self, grace: float) -> TerminationResult:
        sent = 0
        try:
            if not self._child.stopped and not self._child.done.is_set() and self._child.owned.group_alive():
                for sig, seconds in (
                    (signal.SIGINT, grace),
                    (signal.SIGTERM, grace),
                    (signal.SIGKILL, _KILL_WAIT_SECONDS),
                ):
                    if self._child.send(sig):
                        sent = sig
                    if self._child.stopped or self._stopped_within(seconds):
                        break
                else:
                    return TerminationResult(sent, False, True, "process_group_still_alive")
            if not self._child.stopped and self._child.owned.group_alive():
                return TerminationResult(sent, False, False, "process_group_cleanup_unconfirmed")
            if not self._child.done.wait(_KILL_WAIT_SECONDS):
                return TerminationResult(sent, False, False, "process_reap_unconfirmed")
            if self._child.error is not None:
                return TerminationResult(sent, False, False, f"process_cleanup_failed: {self._child.error}")
        except PermissionError:
            return TerminationResult(sent, False, False, "signal_permission_denied")
        except OSError as error:
            return TerminationResult(sent, False, False, str(error))
        return TerminationResult(sent, True, False, None)

    def kill(self) -> None:
        self._child.send(signal.SIGKILL)


def run(  # noqa: PLR0913 - explicit subprocess settings
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    timeout_seconds: float,
    stdin: bytes | None = None,
    max_stdout_bytes: int = 1_048_576,
    max_stderr_bytes: int = 65_536,
    grace_seconds: float = 2.0,
    capture_combined_tail: bool = False,
) -> ProcessResult:
    """Run with bounded capture. A combined tail shares stdout's pipe and byte limit."""
    args = check_argv(argv)
    _seconds(timeout_seconds, "timeout_seconds")
    _seconds(grace_seconds, "grace_seconds")
    _limit(max_stdout_bytes)
    _limit(max_stderr_bytes)
    if stdin is not None and not isinstance(stdin, bytes):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise ValueError("stdin must be bytes or None")
    out = BoundedCapture(max_stdout_bytes, capture_tail=capture_combined_tail)
    err = BoundedCapture(max_stderr_bytes)
    started = _start(args, cwd, env, merge_stderr=True) if capture_combined_tail else _start(args, cwd, env)
    child = _Child(*started, out.feed, err.feed, line_mode=False, stdin=stdin, manage_stdin=True)
    code = child.collect(timeout_seconds, grace_seconds)
    actual_code = child.leader_code if child.leader_code is not None else code
    return ProcessResult(
        args,
        TIMEOUT_EXIT if child.timed_out else code,
        bytes(out.data),
        bytes(err.data),
        child.timed_out,
        out.truncated,
        err.truncated,
        time.monotonic() - child.started,
        -actual_code if actual_code < 0 else None,
    )


def spawn(
    argv: Sequence[str],
    *,
    cwd: Path,
    env: Mapping[str, str],
    on_stdout: Callable[[bytes], None],
    on_stderr: Callable[[bytes], None],
    line_mode: bool = True,
) -> ProcessHandle:
    args = check_argv(argv)
    child = _Child(
        *_start(args, cwd, env), on_stdout, on_stderr, line_mode=line_mode, stdin=None, manage_stdin=False
    )
    return ProcessHandle(child)
