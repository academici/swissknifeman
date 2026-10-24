"""The heartbeat of a run: ``<run>/heartbeat.json`` (records/v1 ``heartbeat``), the proof that the conductor that owns the run
still moves. The lease says who owns the run; the heartbeat says whether the owner makes progress.

It is written only from the thread of control of the conductor itself: every progress line, every look at a running role or
check (the threads that watch their own process), and before a blocking call with a known limit (``waiting``). There is no
timer thread: a stuck main loop must show as a stale heartbeat, never be masked by a clock that keeps writing. A write that
fails (``OSError``) never stops the run: the first failure is said once through ``on_failure``, the next writes try again.
"""
from __future__ import annotations

from contextlib import contextmanager, nullcontext
import os
from pathlib import Path
import socket
import threading
import time
from typing import Callable, Optional

from orch.conductor import process, records
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import clock

HEARTBEAT_FILE = "heartbeat.json"
HEARTBEAT_MIN_S = 5  # the least time between two writes, unless the kind of progress changed or the write is forced
# What counts as progress (last_progress_*); the growth of the CPU of the process tree is kept apart (last_cpu_at).
PROGRESS_KINDS = ("run_start", "stage_start", "stage_end", "tool_use", "tool_result", "check_evidence", "tree_change", "answer")
WAIT_KINDS = ("work_source", "provider", "git", "question", "budget", "lock", "subprocess")


class Heartbeat:
    """The writer of ``heartbeat.json`` of run ``run_id`` in ``run_dir``; the process that owns the run holds the one instance."""

    def __init__(self, run_dir: Path, run_id: str, *, monotonic: Optional[Callable[[], float]] = None,
                 on_failure: Optional[Callable[[OSError], None]] = None):
        self.run_dir, self.run_id = Path(run_dir), run_id
        self.path = self.run_dir / HEARTBEAT_FILE
        self.monotonic = monotonic or time.perf_counter  # monotonic, and not the clock the run's own timers use
        self.on_failure = on_failure
        self.seq = 0
        self.last_write_mono: Optional[float] = None
        self.failed = False  # a write failed: said once
        self.item = self.step = self.role = None
        self.last_progress_at = self.last_progress_kind = None
        self.stream_bytes: Optional[int] = None
        self.last_growth_at = None
        self.tree_cpu_s: Optional[float] = None
        self.last_cpu_at = None
        self.repeat: Optional[dict] = None
        self._waits: list = []
        self._lock = threading.RLock()
        self._identity = {"pid": os.getpid(), "start_ticks": process.start_ticks(os.getpid()), "boot_id": process.boot_id(),
                          "host": socket.gethostname()}

    # ------------------------------------------------------------------ writing

    def beat(self, *, item: Optional[str] = None, step: Optional[str] = None, role: Optional[str] = None,
             progress_kind: Optional[str] = None, stream_bytes: Optional[int] = None, tree_cpu_s: Optional[float] = None,
             repeat: Optional[dict] = None, force: bool = False) -> bool:
        """Note what the conductor does now and write the heartbeat when ``force`` is set, when at least ``HEARTBEAT_MIN_S``
        passed since the last write, or when the kind of progress changed. An argument left out leaves that field as it was.
        ``progress_kind`` ``cpu`` records the growth of the CPU of the process tree, any other kind a sign of progress.
        True when the file was written."""
        with self._lock:
            now = clock.utc_now()
            if item is not None:
                self.item = item
            if step is not None:
                self.step = step
            if role is not None:
                self.role = role
            changed = progress_kind not in (None, "cpu") and progress_kind != self.last_progress_kind
            if progress_kind == "cpu":
                self.last_cpu_at = now
            elif progress_kind is not None:
                self.last_progress_at, self.last_progress_kind = now, progress_kind
            if stream_bytes is not None:
                if stream_bytes != self.stream_bytes:
                    self.last_growth_at = now
                self.stream_bytes = stream_bytes
            if tree_cpu_s is not None:
                if self.tree_cpu_s is None:
                    self.last_cpu_at = self.last_cpu_at or now
                elif tree_cpu_s - self.tree_cpu_s >= process.CPU_PROGRESS_S:
                    self.last_cpu_at = now
                self.tree_cpu_s = tree_cpu_s
            if repeat is not None:
                self.repeat = repeat
            if not (force or changed or self.last_write_mono is None
                    or self.monotonic() - self.last_write_mono >= HEARTBEAT_MIN_S):
                return False
            return self._write(now)

    def leave_step(self) -> None:
        """A step ended: its role, stream, CPU and repeat counts no longer describe what the conductor does."""
        with self._lock:
            self.step = self.role = None
            self.stream_bytes = self.last_growth_at = self.tree_cpu_s = self.last_cpu_at = self.repeat = None

    def leave_item(self) -> None:
        with self._lock:
            self.item = None
            self.leave_step()

    def observe(self, line: dict) -> None:
        """The ``Progress`` observer: a progress line of the run. A step that starts or ends is progress; an ``info`` line is
        a sign of life (a write unless one was just made)."""
        event = line.get("event")
        if event in ("run.start", "run.resume"):
            self.leave_item()
            self.beat(progress_kind="run_start", force=True)
        elif event == "stage.start":
            self.leave_step()
            self.beat(item=line.get("item"), step=line.get("stage"), role=line.get("role"), progress_kind="stage_start",
                      force=True)
        elif event in ("stage.end", "stage.skip"):
            self.leave_step()
            self.beat(progress_kind="stage_end", force=True)
        elif event == "item.start":
            self.beat(item=line.get("item"))
        elif event == "item.end":
            self.leave_item()
            self.beat()
        else:
            self.beat()

    @contextmanager
    def waiting(self, kind: str, reason_code: str, deadline_s: Optional[float] = None):
        """Declare a blocking call with a known limit: until ``deadline_s`` seconds from now a silent heartbeat is a wait, not a
        hang. Written at once before and after the call. ``deadline_s`` is required for every kind but ``question``."""
        if kind not in WAIT_KINDS:
            raise ValueError(f"unknown wait kind {kind!r}")
        if deadline_s is None and kind != "question":
            raise ValueError(f"a {kind} wait needs a deadline")
        entry = {"kind": kind, "reason_code": reason_code, "since": clock.utc_now(),
                 "deadline": None if deadline_s is None else clock.utc_stamp(clock.wall() + float(deadline_s))}
        with self._lock:
            self._waits.append(entry)
        self.beat(force=True)
        try:
            yield entry
        finally:
            with self._lock:
                self._waits = [found for found in self._waits if found is not entry]
            self.beat(force=True)

    def document(self, at: str) -> dict:
        waiting = self._waits[-1] if self._waits else None
        return {"run_id": self.run_id, **self._identity, "seq": self.seq + 1, "at": at,
                "item": self.item, "step": self.step, "role": self.role,
                "last_progress_at": self.last_progress_at, "last_progress_kind": self.last_progress_kind,
                "stream_bytes": self.stream_bytes, "last_growth_at": self.last_growth_at,
                "tree_cpu_s": None if self.tree_cpu_s is None else round(self.tree_cpu_s, 2), "last_cpu_at": self.last_cpu_at,
                "repeat": self.repeat, "waiting": dict(waiting) if waiting else None}

    def _write(self, at: str) -> bool:
        try:
            records.write(self.path, self.document(at), "heartbeat")
        except OSError as error:  # the heartbeat is no condition of the run
            if not self.failed:
                self.failed = True
                if self.on_failure is not None:
                    self.on_failure(error)
            return False
        self.seq += 1
        self.last_write_mono = self.monotonic()
        return True


def read(run_dir: Path) -> tuple:
    """``(document, problem)`` of ``<run>/heartbeat.json`` for a reader: ``(doc, None)``; ``(None, "HEARTBEAT_MISSING")`` when
    there is none (a run from before it, or its first seconds); ``(None, "HEARTBEAT_INVALID: <why>")`` when it cannot be read or
    does not match its schema. Never raises."""
    try:
        doc = records.read(Path(run_dir) / HEARTBEAT_FILE, "heartbeat")
    except (OSError, Stop) as error:
        return None, f"HEARTBEAT_INVALID: {getattr(error, 'message', None) or error}"[:300]
    return (doc, None) if doc else (None, "HEARTBEAT_MISSING")


def declare(owner, kind: str, reason_code: str, deadline_s: Optional[float] = None):
    """``owner.heartbeat.waiting(...)`` for the run ``owner`` drives; a context that does nothing when it has no heartbeat (a
    conductor that is not opened, a test double)."""
    found = getattr(owner, "heartbeat", None)
    return found.waiting(kind, reason_code, deadline_s) if found is not None else nullcontext()


def observe_tick(owner, watch, elapsed: float, info, **where) -> list:
    """A look at a running role (``watch`` its :class:`StallWatch`, ``elapsed`` the seconds the role has run, ``info`` the :class:`TickInfo`): note it in the heartbeat of
    ``owner`` (``where``: item, step, role) and return the reasons the role is suspected to stall, for a beacon."""
    said = watch.feed(elapsed, info)
    found = getattr(owner, "heartbeat", None)
    if found is not None:
        found.beat(progress_kind=info.progress_kind, stream_bytes=info.stream_bytes, tree_cpu_s=info.tree_cpu_s,
                   repeat=watch.repeat, **where)
    return said


def ticker(owner) -> Optional[Callable[[], None]]:
    """A function that writes the heartbeat of the run ``owner`` drives at once (for a long pause that says it is alive), or
    ``None`` when it has none."""
    found = getattr(owner, "heartbeat", None)
    return (lambda: found.beat(force=True)) if found is not None else None
