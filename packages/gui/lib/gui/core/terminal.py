"""Terminal sessions of the host (decisions D29, D30): a shell in a PTY, the credit gate of the output, the limits.

A session is one shell started through ``subprocess.Popen([python, '-I', '-c', LAUNCHER, shell])`` on the slave of
``os.openpty()``: the launcher makes the child a session leader with the slave as controlling terminal (job control
works) and ``exec``s the shell, so there is no ``preexec_fn`` and no ``fork`` in the threads of the backend. The
environment is ``clean_environment`` (no secrets, no ``GUI_*``) plus ``TERM``/``COLORTERM``/``LANG``.

The output is pulled, never pushed: :meth:`Session.take_output` reads the master only while the client has credit
(:class:`CreditGate`) and at most ``output_chunk_bytes`` at a time, so a fast shell is slowed down by the kernel buffer
and nothing piles up in memory or gets lost. The unpaid credit of a client is at most ``4 * credit_bytes``.

The content of a terminal (input and output) is never stored: it is not logged, audited or put in an event; only
metadata (project, shell, size, byte counts, reason) goes to the audit. A session ends once, in :meth:`Session.close`
(group ``SIGHUP``, a grace, group ``SIGKILL``, ``waitpid``), whatever asks: EOF, the client, the idle or the maximum
timer, or the stop of the backend. stdlib + aicore; the module imports on every platform, a manager on a platform
without a PTY refuses ``PERMISSION_DENIED``.
"""
from __future__ import annotations

import os
import select
import signal
import struct
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Set, Tuple

from aicore.ext.environment import clean_environment

from . import procinfo
from ..errors import GuiError

try:  # POSIX only; the import never fails on another platform
    import fcntl
    import termios
except ImportError:  # pragma: no cover - exercised only on a platform without a PTY
    fcntl = None  # type: ignore[assignment]
    termios = None  # type: ignore[assignment]

LAUNCHER = ("import os, sys, fcntl, termios\n"
            "os.setsid()\n"
            "fcntl.ioctl(0, termios.TIOCSCTTY, 1)\n"
            "os.execv(sys.argv[1], [sys.argv[1], '-i'])\n")
DEFAULT_SHELL = "/bin/sh"
COLS = (10, 500)
ROWS = (2, 200)
MAX_INPUT_BYTES = 64 * 1024
CREDIT_FACTOR = 4
CLOSE_GRACE_S = 2.0
WRITE_TIMEOUT_S = 5.0
KEEP_ENDED = 16
REASONS = ("exit", "closed", "idle", "max", "backend_stop", "error")
PLATFORM_TEXT = "the terminal needs a POSIX PTY (Linux or macOS); it is not available on this platform"


def supported() -> bool:
    return os.name == "posix" and fcntl is not None and termios is not None


def now_text() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def pick_shell(env: Mapping[str, str], shells_file: str = "/etc/shells") -> str:
    """``SHELL`` when it is an absolute, executable path listed in ``/etc/shells``, else ``/bin/sh``."""
    candidate = env.get("SHELL", "")
    if candidate and os.path.isabs(candidate) and os.access(candidate, os.X_OK) and not os.path.isdir(candidate):
        try:
            with open(shells_file, "r", encoding="utf-8", errors="replace") as handle:
                listed = {line.strip() for line in handle if line.strip() and not line.lstrip().startswith("#")}
        except OSError:
            listed = set()
        if candidate in listed:
            return candidate
    return DEFAULT_SHELL


def shell_environment(source: Mapping[str, str]) -> Dict[str, str]:
    """The environment of the shell: the allowlist of ``clean_environment`` and the terminal variables."""
    env, _secrets = clean_environment(dict(source), permissions=None, trusted=False)
    for name in [name for name in env if name.startswith(("SKM_EXT_", "GUI_"))]:
        del env[name]
    env["TERM"] = "xterm-256color"
    env["COLORTERM"] = "truecolor"
    if source.get("LANG"):
        env["LANG"] = source["LANG"]
    return env


class CreditGate:
    """The credit a client granted for output bytes; the unpaid part is at most ``limit``."""

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self._available = 0
        self._lock = threading.Lock()

    @property
    def available(self) -> int:
        return self._available

    def grant(self, amount: Any) -> None:
        """Add ``amount`` bytes; ``ValueError`` for a non-positive or non-integer amount or one over the limit."""
        if isinstance(amount, bool) or not isinstance(amount, int) or amount < 1:
            raise ValueError("credit must be a positive integer")
        with self._lock:
            if self._available + amount > self.limit:
                raise ValueError(f"unpaid credit may not exceed {self.limit} bytes")
            self._available += amount

    def take(self, wanted: int) -> int:
        """Spend up to ``wanted`` bytes and return how many were spent."""
        with self._lock:
            used = min(wanted, self._available)
            self._available -= used
            return used

    def give_back(self, amount: int) -> None:
        with self._lock:
            self._available += amount


@dataclass(frozen=True)
class Limits:
    """The ``[gui.terminal]`` values the core needs (``settings.Terminal`` has the same field names)."""

    max_sessions: int = 2
    idle_timeout_s: int = 900
    max_session_s: int = 14400
    credit_bytes: int = 65536
    output_chunk_bytes: int = 16384


def session_members(sid: int) -> Set[int]:
    """Pids of the processes of session ``sid``: the shell, its jobs (each job has a group of its own) and the
    descendants that were detached from the shell. Linux reads ``/proc``; elsewhere ``ps`` finds the members by
    session and the descendants of ``sid``."""
    found: Set[int] = set()
    if sys.platform.startswith("linux"):
        try:
            names = os.listdir("/proc")
        except OSError:
            return found
        for name in names:
            if not name.isdigit():
                continue
            try:
                with open(f"/proc/{name}/stat", "rb") as handle:
                    raw = handle.read().decode("ascii", "replace")
            except OSError:
                continue
            fields = raw[raw.rfind(")") + 2:].split()
            if len(fields) > 3 and fields[3] == str(sid):
                found.add(int(name))
        return found
    return found.union(_ps_members(sid))


def _ps_members(sid: int) -> Set[int]:
    """Members of session ``sid`` where there is no ``/proc``: every process in the same session as the leader or as
    a process of its group (``ps`` ``sess``), so jobs stay found after the shell exited, plus the descendants of ``sid``."""
    found: Set[int] = set()
    try:
        result = subprocess.run(["ps", "-axo", "pid=,ppid=,pgid=,sess="], capture_output=True, text=True, timeout=5,
                                env={"LC_ALL": "C", "PATH": os.environ.get("PATH", "/bin:/usr/bin")})
    except (OSError, subprocess.SubprocessError):
        return found
    rows: List[Tuple[int, int, int, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0].isdigit() and parts[1].isdigit() and parts[2].isdigit():
            rows.append((int(parts[0]), int(parts[1]), int(parts[2]), parts[3]))
    sessions = {sess for pid, _ppid, pgid, sess in rows if (pid == sid or pgid == sid) and sess not in ("0", "-")}
    children: Dict[int, List[int]] = {}
    for pid, ppid, _pgid, sess in rows:
        children.setdefault(ppid, []).append(pid)
        if sess in sessions:
            found.add(pid)
    todo = [sid]
    seen: Set[int] = set()
    while todo:
        pid = todo.pop()
        if pid not in seen:
            seen.add(pid)
            todo.extend(children.get(pid, ()))
    found.update(seen)
    return found


def _winsize(master: int, cols: int, rows: int) -> None:
    fcntl.ioctl(master, termios.TIOCSWINSZ, struct.pack("HHHH", rows, cols, 0, 0))


def check_size(cols: Any, rows: Any) -> Tuple[int, int]:
    for name, value, (low, high) in (("cols", cols, COLS), ("rows", rows, ROWS)):
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            raise GuiError("INPUT_INVALID", f"{name} must be an integer from {low} to {high}",
                           issues=[{"pointer": f"/{name}", "code": "range", "message": f"{low}..{high}"}])
    return cols, rows


class Session:
    """One shell on a PTY. Safe to use from the event loop and from worker threads."""

    def __init__(self, session_id: str, project_id: str, shell: str, proc: subprocess.Popen, master: int,
                 cols: int, rows: int, limits: Limits, clock: Callable[[], float], grace_s: float = CLOSE_GRACE_S):
        self.id = session_id
        self.project_id = project_id
        self.shell = shell
        self.proc = proc
        self.pgid = proc.pid  # the launcher called setsid(): the shell leads its own group
        self.cols, self.rows = cols, rows
        self.started_at = now_text()
        self.ended_at: Optional[str] = None
        self.limits = limits
        self.gate = CreditGate(CREDIT_FACTOR * limits.credit_bytes)
        self._clock = clock
        self.started = clock()
        self.last_activity = self.started
        self._master = master
        self._lock = threading.RLock()
        self._grace_s = grace_s
        self._seq = 0
        self._attached = False
        self._eof = False
        self.closed = False
        self.reason: Optional[str] = None
        self.bytes_in = 0
        self.bytes_out = 0
        self._done = threading.Event()
        os.set_blocking(master, False)

    # --- documents ------------------------------------------------------------------------------------------

    def entry(self) -> Dict[str, Any]:
        return {"session_id": self.id, "project_id": self.project_id, "shell": self.shell, "cols": self.cols,
                "rows": self.rows, "started_at": self.started_at}

    def document(self) -> Dict[str, Any]:
        document = {"$schema": "urn:swissknifeman:gui:terminal:v1", "kind": "session", **self.entry()}
        if self.ended_at is not None:
            document["ended_at"] = self.ended_at
        return document

    # --- ownership of the socket ----------------------------------------------------------------------------

    def attach(self) -> bool:
        """Claim the session for one client; ``False`` when another client holds it or it has ended."""
        with self._lock:
            if self._attached or self.closed:
                return False
            self._attached = True
            return True

    def detach(self) -> None:
        with self._lock:
            self._attached = False

    # --- output -----------------------------------------------------------------------------------------------

    def take_output(self) -> Optional[Tuple[int, bytes]]:
        """``(seq, bytes)`` of the next output chunk, or ``None``: no credit, nothing to read, EOF or closed.

        Reads at most ``output_chunk_bytes`` and never more than the credit; the master is not touched at zero credit.
        """
        with self._lock:
            if self.closed or self._eof or self._master < 0:
                return None
            allowed = self.gate.take(self.limits.output_chunk_bytes)
            if allowed <= 0:
                return None
            try:
                data = os.read(self._master, allowed)
            except BlockingIOError:
                self.gate.give_back(allowed)
                return None
            except OSError:  # EIO: every holder of the slave is gone
                self.gate.give_back(allowed)
                self._eof = True
                return None
            if not data:
                self.gate.give_back(allowed)
                self._eof = True
                return None
            self.gate.give_back(allowed - len(data))
            self.bytes_out += len(data)
            self.last_activity = self._clock()
            seq = self._seq
            self._seq += 1
            return seq, data

    def wait_readable(self, timeout: float) -> bool:
        """Block up to ``timeout`` seconds until the master has data or hung up (call it from a worker thread)."""
        master = self._master
        if master < 0:
            return False
        try:
            ready, _, _ = select.select([master], [], [], timeout)
        except (OSError, ValueError):
            return False
        return bool(ready)

    def readable_now(self) -> bool:
        return self.wait_readable(0)

    def exited(self) -> bool:
        return self.proc.poll() is not None

    def finished(self) -> bool:
        """The shell is gone and everything it wrote was read, or the PTY reported EOF."""
        with self._lock:
            if self.closed:
                return True
            if self._eof:
                return True
        return self.exited() and not self.readable_now()

    # --- input and size -------------------------------------------------------------------------------------

    def write(self, data: bytes) -> None:
        """Write to the shell (blocks up to ``WRITE_TIMEOUT_S`` when its input is full); ``OSError`` when closed."""
        deadline = time.monotonic() + WRITE_TIMEOUT_S
        view = memoryview(data)
        while view:
            with self._lock:
                if self.closed or self._master < 0:
                    raise OSError("the session is closed")
                try:
                    sent = os.write(self._master, view)
                except BlockingIOError:
                    sent = 0
                if sent:
                    self.bytes_in += sent
                    self.last_activity = self._clock()
            view = view[sent:]
            if view:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError("the shell does not read its input")
                time.sleep(min(0.02, left))

    def resize(self, cols: int, rows: int) -> None:
        check_size(cols, rows)
        with self._lock:
            if self.closed or self._master < 0:
                return
            _winsize(self._master, cols, rows)
            self.cols, self.rows = cols, rows

    # --- the end ----------------------------------------------------------------------------------------------

    def close(self, reason: str) -> bool:
        """End the session once: ``SIGHUP`` to the group, a grace, ``SIGKILL`` to the group and to the rest of the
        session, ``waitpid``, close the master.

        Returns ``True`` for the call that ended it. Any other call (also a concurrent one) waits until the end is done
        and returns ``False``, so after ``close`` returns the shell and its descendants of the group are gone.
        """
        if reason not in REASONS:
            raise ValueError(f"unknown reason {reason!r}")
        with self._lock:
            first = not self.closed
            if first:
                self.closed = True
                self.reason = reason
        if not first:
            self._done.wait(self._grace_s * 3 + 5)
            return False
        try:
            known = self._snapshot({})
            self._signal_group(signal.SIGHUP)
            deadline = time.monotonic() + self._grace_s
            while self.proc.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            known = self._snapshot(known)
            self._signal_group(signal.SIGKILL)  # also what ignored the hangup
            for pid, started in known.items():  # jobs have groups of their own; detached ones keep the session
                if pid != self.proc.pid and procinfo.same_process(pid, started):
                    try:
                        os.kill(pid, signal.SIGKILL)
                    except (ProcessLookupError, PermissionError):
                        pass
            try:
                self.proc.wait(timeout=max(5.0, self._grace_s))
            except subprocess.TimeoutExpired:  # pragma: no cover - a killed process always ends
                pass
        finally:
            with self._lock:
                if self._master >= 0:
                    try:
                        os.close(self._master)
                    except OSError:
                        pass
                    self._master = -1
                self.ended_at = now_text()
            self._done.set()
        return True

    def _snapshot(self, known: Dict[int, Optional[str]]) -> Dict[int, Optional[str]]:
        """``known`` plus the members of the session now, each with its start time (a reused pid is not killed)."""
        merged = dict(known)
        for pid in session_members(self.pgid):
            if pid not in merged:
                merged[pid] = procinfo.start_time(pid)
        return merged

    def _signal_group(self, number: int) -> None:
        try:
            os.killpg(self.pgid, number)
        except (ProcessLookupError, PermissionError):
            pass

    def exit_info(self) -> Dict[str, Any]:
        """``code``, optional ``signal`` and ``reason`` of the ``exit`` frame."""
        status = self.proc.returncode
        info: Dict[str, Any] = {"code": status if isinstance(status, int) and status >= 0 else -1}
        if isinstance(status, int) and status < 0:
            info["signal"] = -status
        info["reason"] = self.reason or "closed"
        return info

    def output_state(self) -> Tuple[int, int]:
        """``(unpaid credit, bytes sent)`` as one consistent pair: the output pump spends credit and counts the bytes
        under the session lock, so a reader that takes the lock never sees the credit spent but the bytes not counted."""
        with self._lock:
            return self.gate.available, self.bytes_out

    def metadata(self) -> Dict[str, Any]:
        """The audit details of the end; no content."""
        info = self.exit_info()
        details: Dict[str, Any] = {"project_id": self.project_id, "reason": info["reason"], "exit_code": info["code"],
                                   "bytes_in": self.bytes_in, "bytes_out": self.output_state()[1],
                                   "duration_s": max(0, int(self._clock() - self.started))}
        if "signal" in info:
            details["signal"] = info["signal"]
        return details


class TerminalManager:
    """The sessions of one backend: the limits, the timers (an injectable clock), the audit of start and end."""

    def __init__(self, limits: Limits, *, env: Mapping[str, str], audit: Optional[Callable[..., None]] = None,
                 clock: Callable[[], float] = time.monotonic, grace_s: float = CLOSE_GRACE_S,
                 shells_file: str = "/etc/shells") -> None:
        self.limits = limits
        self.env = dict(env)
        self.audit = audit
        self.clock = clock
        self.grace_s = grace_s
        self.shells_file = shells_file
        self._sessions: "OrderedDict[str, Session]" = OrderedDict()
        self._ended: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()
        self._lock = threading.RLock()
        self._stopped = False

    def shell(self) -> str:
        return pick_shell(self.env, self.shells_file)

    def count(self) -> int:
        with self._lock:
            return len(self._sessions)

    def list(self) -> List[Session]:
        with self._lock:
            return list(self._sessions.values())

    def get(self, session_id: str) -> Optional[Session]:
        with self._lock:
            return self._sessions.get(session_id)

    def ended_document(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._ended.get(session_id)

    def _audit(self, action: str, target: str, decision: str, details: Mapping[str, Any]) -> None:
        if self.audit is not None:
            self.audit(action, target, decision, details)

    def start(self, project_id: str, root: str, cols: int, rows: int) -> Session:
        """Start a shell in ``root``; ``PERMISSION_DENIED`` without a PTY, ``TERMINAL_LIMIT`` beyond ``max_sessions``."""
        if not supported():
            raise GuiError("PERMISSION_DENIED", PLATFORM_TEXT, details={"reason": "terminal_unsupported"})
        check_size(cols, rows)
        with self._lock:
            if self._stopped:
                raise GuiError("PERMISSION_DENIED", "the backend is stopping", details={"reason": "backend_stop"})
            if len(self._sessions) >= self.limits.max_sessions:
                raise GuiError("TERMINAL_LIMIT", f"at most {self.limits.max_sessions} terminal sessions at the same time")
            shell = self.shell()
            master, slave = os.openpty()
            try:
                _winsize(master, cols, rows)
                proc = subprocess.Popen([sys.executable, "-I", "-c", LAUNCHER, shell], stdin=slave, stdout=slave,
                                        stderr=slave, close_fds=True, cwd=root, env=shell_environment(self.env))
            except OSError as error:
                os.close(master)
                raise GuiError("INTERNAL", f"the shell did not start ({error.__class__.__name__})") from None
            finally:
                os.close(slave)
            session = Session(f"term-{uuid.uuid4().hex}", project_id, shell, proc, master, cols, rows, self.limits,
                              self.clock, self.grace_s)
            self._sessions[session.id] = session
        self._audit("terminal.start", session.id, "allowed",
                    {"project_id": project_id, "shell": shell, "cols": cols, "rows": rows})
        return session

    def close(self, session_id: str, reason: str) -> Optional[Dict[str, Any]]:
        """End a session (blocking up to the grace); the ``session`` document, ``None`` for an unknown id."""
        with self._lock:
            session = self._sessions.get(session_id)
        if session is None:
            return self.ended_document(session_id)
        first = session.close(reason)
        with self._lock:
            self._sessions.pop(session_id, None)
            self._ended[session_id] = session.document()
            while len(self._ended) > KEEP_ENDED:
                self._ended.popitem(last=False)
        if first:
            self._audit("terminal.end", session_id, "allowed", session.metadata())
        return session.document()

    def reap(self) -> List[str]:
        """Close the sessions that are idle or over the maximum (the injected clock decides); the ids."""
        now = self.clock()
        reaped = []
        for session in self.list():
            if now - session.started >= self.limits.max_session_s:
                reason = "max"
            elif now - session.last_activity >= self.limits.idle_timeout_s:
                reason = "idle"
            else:
                continue
            self.close(session.id, reason)
            reaped.append(session.id)
        return reaped

    def close_all(self, reason: str = "backend_stop") -> int:
        """Refuse new sessions and end every running one (the stop of the backend)."""
        with self._lock:
            self._stopped = True
            ids = list(self._sessions)
        threads = [threading.Thread(target=self.close, args=(session_id, reason), daemon=True) for session_id in ids]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(self.grace_s * 3 + 10)
        return len(ids)
