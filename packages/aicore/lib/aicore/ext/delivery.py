"""Delivery of journaled events to subscribers: cursors, one deliverer per journal, dead letters, replay.

The journal is the source of truth; delivery only reads it. Files of a journal directory ``J``:
``ext/deliver.lock``, ``ext/cursors.json``, ``ext/dead-letter.jsonl`` and ``ext/deliveries.jsonl`` (one line
per attempt). The rules (numbered as in the extension design):

* I5 only stored events are delivered: a deliverer reads complete journal lines.
* I6 one deliverer per journal: ``flock(deliver.lock)``; the deliverer started after ``emit`` gives up at
  once when the lock is busy, ``deliver``/``replay`` from the command line wait up to 30 s.
* I7 no lost wake-up: after a pass the deliverer releases the lock and only then compares the journal size
  with what the pass covered; a grown journal is taken up again (``LOCK_NB``), a busy lock means the
  holder sees the growth itself.
* I8 per subscription events go in journal order; its cursor moves only after a success (``ok`` or
  ``skipped``) or after the event went to the dead-letter list. One attempt per event and pass; a failure
  stops the subscription until the next run of a deliverer.
* I9 ``cursors.json`` is replaced atomically and only while holding the lock: a crash between a delivery
  and the cursor write delivers that event again (at least once; subscribers are idempotent by ``id``).
* I10 after ``events.max_attempts`` failures in a row the event goes to the dead-letter list and the cursor
  moves on; ``replay`` delivers it again.
* I12 a new subscription starts at the event that triggered an automatic delivery, else at the end.
* I13 a cursor whose last event is no longer where it was (the journal was removed, replaced or cut by
  hand) moves to the end with a ``JOURNAL_RESET`` record instead of replaying everything.

Writers of the cursors and the dead-letter list take the :class:`DeliverLock` object, so they cannot run
without the lock. Locks are ``fcntl.flock`` (POSIX). stdlib and ``aicore`` only.
"""
from __future__ import annotations

import contextlib
import dataclasses
import fnmatch
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Set, Tuple, Union

from ..state import ensure_dir
from ..util.io import atomic_write_json
from ..util.lock import FileLock
from . import journal
from . import plugins as _plugins
from . import settings as _settings
from . import units as _units
from .environment import clean_environment
from .errors import ExtError, warn_once
from .events import Event, _now_text, parse_line
from .process import ProcessResult, run_json

LOCK_FILE = "deliver.lock"
CURSORS_FILE = "cursors.json"
DEAD_LETTER_FILE = "dead-letter.jsonl"
DELIVERIES_FILE = "deliveries.jsonl"
CURSORS_VERSION = 1
WAIT_S = 30.0
_POLL_S = 0.05
_SUCCESS = ("ok", "skipped")

PathLike = Union[str, "os.PathLike[str]"]
Problem = Dict[str, Any]


@dataclass(frozen=True)
class Subscription:
    """One subscription: from a module's ``unit.json`` (``<module>:<id>``) or from the configuration."""

    id: str
    on: Tuple[str, ...]
    run: Optional[Tuple[str, ...]]
    plugin: Optional[str]
    projects: Tuple[str, ...]
    timeout_seconds: int
    enabled: bool
    origin: str
    module: Optional[str]


@dataclass
class DeliveryReport:
    """What one ``deliver``/``replay`` call did. ``busy``: another deliverer held the lock."""

    delivered: int = 0
    failed: int = 0
    dead_lettered: int = 0
    resets: int = 0
    passes: int = 0
    busy: bool = False
    attempts: List[Dict[str, Any]] = field(default_factory=list)
    problems: List[Problem] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.failed == 0 and self.dead_lettered == 0

    def to_json(self) -> Dict[str, Any]:
        return {"delivered": self.delivered, "failed": self.failed, "dead_lettered": self.dead_lettered,
                "resets": self.resets, "passes": self.passes, "busy": self.busy, "attempts": self.attempts,
                "problems": self.problems}

    def problem(self, code: str, message: str, subscription: Optional[str] = None) -> None:
        entry = {"code": code, "subscription": subscription, "message": message}
        if entry not in self.problems:
            self.problems.append(entry)


def _ext_dir(jdir: PathLike) -> Path:
    return Path(jdir) / journal.EXT_DIRNAME


def cursors_path(jdir: PathLike) -> Path:
    return _ext_dir(jdir) / CURSORS_FILE


def dead_letter_path(jdir: PathLike) -> Path:
    return _ext_dir(jdir) / DEAD_LETTER_FILE


def deliveries_path(jdir: PathLike) -> Path:
    return _ext_dir(jdir) / DELIVERIES_FILE


# --- subscriptions -------------------------------------------------------------------------------------------

def match(subscription: Subscription, event_type: str) -> bool:
    """True when ``event_type`` matches one of the subscription's patterns (shell-style, case-sensitive)."""
    return any(fnmatch.fnmatchcase(event_type, pattern) for pattern in subscription.on)


def _same_path(left: str, right: str) -> bool:
    return os.path.realpath(left) == os.path.realpath(right)


def is_active(subscription: Subscription, project: Optional[PathLike]) -> bool:
    """True when the subscription applies to the journal of ``project`` (None: the machine journal)."""
    if not subscription.projects:
        return True
    if project is None:
        return False
    root = os.path.abspath(project)
    return any(os.path.isabs(item) and _same_path(item, root) for item in subscription.projects)


def _problem(code: str, message: str, subscription: Optional[str] = None) -> Problem:
    return {"code": code, "subscription": subscription, "message": message}


def resolve_subscriptions(settings: "_settings.ExtSettings", units: Mapping[str, "_units.UnitDoc"],
                          project: Optional[PathLike] = None) -> Tuple[List[Subscription], List[Problem]]:
    """Every subscription (enabled or not) ordered by id, and the problems of the configuration.

    Module subscriptions come from ``unit.json``; a configuration entry with the same id overlays one: it may
    change ``enabled``, ``timeout_seconds`` and ``projects``, never the command. Any other entry needs ``on``
    and exactly one of ``run`` and ``plugin`` (``SUBSCRIPTION_INVALID`` otherwise). An entry that only
    switches off a module subscription that is not installed is ignored. Whether a subscription applies to
    the journal of ``project`` is :func:`is_active`.
    """
    problems: List[Problem] = []
    found: Dict[str, Subscription] = {}
    for full, entry in _units.module_subscriptions(units).items():
        found[full] = Subscription(id=full, on=tuple(entry["on"]), run=tuple(entry["run"]), plugin=None,
                                   projects=(), timeout_seconds=entry["timeout_seconds"] or settings.timeout_seconds,
                                   enabled=True, origin="unit", module=entry["module"])
    for name in sorted(settings.subscriptions):
        body = settings.subscriptions[name]
        enabled = bool(body.get("enabled", True))
        projects = tuple(os.path.expanduser(item) for item in body.get("projects") or ())
        timeout = body.get("timeout_seconds")
        if name in found:
            base = found[name]
            refused = sorted(key for key in ("on", "run", "plugin") if key in body)
            if refused:
                problems.append(_problem("SUBSCRIPTION_INVALID", f"subscription {name} is declared by module "
                                         f"{base.module}; the configuration may change enabled, timeout_seconds "
                                         f"and projects only, not {', '.join(refused)}", name))
            found[name] = dataclasses.replace(base, enabled=enabled, projects=projects or base.projects,
                                              timeout_seconds=timeout or base.timeout_seconds)
            continue
        run, plugin, patterns = body.get("run"), body.get("plugin"), body.get("on")
        if run is None and plugin is None and not enabled and set(body) <= {"enabled", "projects"}:
            continue  # switches off a module subscription that is not installed on this machine
        if (run is None) == (plugin is None):
            problems.append(_problem("SUBSCRIPTION_INVALID", f"subscription {name} needs exactly one of run "
                                     "and plugin", name))
            continue
        if not patterns:
            problems.append(_problem("SUBSCRIPTION_INVALID", f"subscription {name} needs on: at least one "
                                     "event type pattern", name))
            continue
        found[name] = Subscription(id=name, on=tuple(patterns), run=tuple(run) if run is not None else None,
                                   plugin=plugin, projects=projects,
                                   timeout_seconds=timeout or settings.timeout_seconds, enabled=enabled,
                                   origin="config", module=None)
    for subscription in found.values():
        relative = [item for item in subscription.projects if not os.path.isabs(item)]
        if relative:
            problems.append(_problem("SUBSCRIPTION_INVALID", f"subscription {subscription.id}: project roots "
                                     "must be absolute paths; relative ones never match", subscription.id))
    return [found[name] for name in sorted(found)], problems


# --- the lock and the files it guards ------------------------------------------------------------------------

class DeliverLock:
    """Proof that the caller holds ``ext/deliver.lock`` of one journal directory (only while it is held)."""

    def __init__(self, jdir: Path, fd: int):
        self.jdir = jdir
        self._fd: Optional[int] = fd

    @property
    def held(self) -> bool:
        return self._fd is not None

    def _release(self) -> None:
        self._fd = None


def _require(lock: object, jdir: PathLike) -> None:
    if not isinstance(lock, DeliverLock) or not lock.held or lock.jdir != Path(jdir):
        raise RuntimeError("delivery state is written only while holding the deliver lock of its journal")


@contextlib.contextmanager
def _deliver_lock(jdir: PathLike, *, wait: Union[bool, float]) -> Iterator[Optional[DeliverLock]]:
    """Hold ``ext/deliver.lock``; yields None when it is busy and ``wait`` is false.

    ``wait=True`` waits up to :data:`WAIT_S` seconds, a number waits that long; a lock still busy then is
    ``ExtError("DELIVERY_LOCKED")``.
    """
    root = Path(jdir)
    ensure_dir(root)
    ensure_dir(_ext_dir(root))
    path = _ext_dir(root) / LOCK_FILE
    guard = FileLock(path)
    limit = WAIT_S if wait is True else float(wait or 0)
    if not guard.acquire(blocking=bool(wait), timeout=limit, poll=_POLL_S):
        if not wait:
            yield None
            return
        raise ExtError("DELIVERY_LOCKED", f"another deliverer holds {path} for more than {limit:g} s")
    lock = DeliverLock(root, guard.fd)
    try:
        yield lock
    finally:
        lock._release()
        guard.release()


def _valid_cursor(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False

    def integer(value: object, allow_none: bool) -> bool:
        return (value is None and allow_none) or (isinstance(value, int) and not isinstance(value, bool)
                                                  and value >= 0)

    pending = entry.get("pending")
    pending_ok = pending is None or (isinstance(pending, dict) and isinstance(pending.get("event_id"), str)
                                     and integer(pending.get("attempts"), False) and pending["attempts"] >= 1
                                     and (pending.get("last_error") is None
                                          or isinstance(pending.get("last_error"), str)))
    return (integer(entry.get("offset"), False) and integer(entry.get("last_offset"), True)
            and (entry.get("last_id") is None or isinstance(entry.get("last_id"), str)) and pending_ok)


def load_cursors(jdir: PathLike) -> Dict[str, Dict[str, Any]]:
    """The cursors by subscription id; a damaged file or entry is dropped with a warning (it starts anew)."""
    path = cursors_path(jdir)
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        warn_once("DELIVERY_CURSORS_INVALID", f"{path} was ignored ({exc.__class__.__name__}); its "
                  "subscriptions start again from new events", key=str(path))
        return {}
    entries = doc.get("subscriptions") if isinstance(doc, dict) and doc.get("version") == CURSORS_VERSION else None
    if not isinstance(entries, dict):
        warn_once("DELIVERY_CURSORS_INVALID", f"{path} was ignored (unknown layout); its subscriptions start "
                  "again from new events", key=str(path))
        return {}
    cursors = {}
    for name, entry in entries.items():
        if _valid_cursor(entry):
            cursors[name] = dict(entry)
        else:
            warn_once("DELIVERY_CURSORS_INVALID", f"the cursor of {name} in {path} was ignored; it starts "
                      "again from new events", key=f"{path}:{name}")
    return cursors


def save_cursors(lock: DeliverLock, cursors: Mapping[str, Mapping[str, Any]]) -> None:
    """Replace ``cursors.json`` atomically (I9); only with the held lock of the journal."""
    _require(lock, lock.jdir if isinstance(lock, DeliverLock) else "")
    atomic_write_json(cursors_path(lock.jdir), {"version": CURSORS_VERSION,
                                                "subscriptions": {name: dict(cursors[name])
                                                                  for name in sorted(cursors)}}, mode=0o600)


def _append_line(path: Path, record: Mapping[str, Any], *, sync: bool) -> None:
    data = json.dumps(record, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
    ensure_dir(path.parent)
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        view = memoryview(data)
        while view:
            view = view[os.write(fd, view):]
        if sync:
            os.fsync(fd)
    finally:
        os.close(fd)


def append_dead_letter(lock: DeliverLock, record: Mapping[str, Any]) -> None:
    """Append one entry to ``dead-letter.jsonl`` (I10); only with the held lock of the journal."""
    _require(lock, lock.jdir if isinstance(lock, DeliverLock) else "")
    _append_line(dead_letter_path(lock.jdir), record, sync=True)


def _log(jdir: PathLike, record: Mapping[str, Any]) -> None:
    """Append to the delivery log; a failure is a warning (the log is diagnostics, not state)."""
    try:
        _append_line(deliveries_path(jdir), record, sync=False)
    except OSError as exc:
        warn_once("DELIVERY_IO", f"the delivery log cannot be written: {exc.strerror or exc}", key=str(jdir))


def record_config_error(jdir: PathLike, error: ExtError, *, now: Any = None) -> None:
    """Note in the delivery log that delivery was skipped because the configuration is invalid."""
    _log(jdir, {"time": _now_text(now), "outcome": "skipped-config", "code": error.code, "message": error.message})


def _read_records(path: Path) -> List[Dict[str, Any]]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return []
    records = []
    for line in text.splitlines():
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records


# --- reading the journal -------------------------------------------------------------------------------------

def _is_line_start(jdir: PathLike, offset: int) -> bool:
    if offset == 0:
        return True
    try:
        with open(journal.journal_path(jdir), "rb") as handle:
            handle.seek(offset - 1)
            return handle.read(1) == b"\n"
    except OSError:
        return False


def _line_end(jdir: PathLike, offset: int) -> int:
    """Offset after the newline of the line starting at ``offset`` (for lines too long to be returned)."""
    with open(journal.journal_path(jdir), "rb") as handle:
        handle.seek(offset)
        position = offset
        while True:
            block = handle.read(65536)
            if not block:
                return position
            found = block.find(b"\n")
            if found != -1:
                return position + found + 1
            position += len(block)


Entry = Tuple[int, int, Optional[Event], Optional[Problem]]


def _entries(jdir: Path, start: int, snapshot: int, cache: Dict[int, Entry]) -> Iterator[Entry]:
    """``(offset, end, event, problem)`` of the complete lines that start in ``[start, snapshot)``."""
    for offset, line, problem in journal.iter_lines(jdir, start):
        if offset >= snapshot:
            return
        cached = cache.get(offset)
        if cached is None:
            if line is not None:
                end = offset + len(line) + 1
            elif problem == "empty":
                end = offset + 1
            else:
                end = _line_end(jdir, offset)
            event, found = parse_line(offset, line, problem)
            cached = cache[offset] = (offset, end, event, found)
        yield cached


def _find_event(jdir: Path, event_id: str) -> Tuple[int, int, Event]:
    for offset, end, event, _problem_found in _entries(jdir, 0, journal.size(jdir), {}):
        if event is not None and event.id == event_id:
            return offset, end, event
    raise ExtError("EVENT_NOT_FOUND", f"no event with id {event_id} in the journal")


# --- one delivery run ----------------------------------------------------------------------------------------

@dataclass
class _Run:
    jdir: Path
    project: Optional[str]
    env: Optional[Mapping[str, str]]
    home: Optional[PathLike]
    config_file: Optional[PathLike]
    trigger_offset: Optional[int]
    now: Any
    report: DeliveryReport = field(default_factory=DeliveryReport)
    stalled: Set[str] = field(default_factory=set)
    loaded: Optional["_settings.ExtSettings"] = None
    units: Optional[Mapping[str, "_units.UnitDoc"]] = None
    _registrations: Optional[List["_plugins.Registration"]] = None

    def time(self) -> str:
        return _now_text(self.now)

    def source_env(self) -> Mapping[str, str]:
        return os.environ if self.env is None else self.env

    def subscriptions(self) -> Tuple[List[Subscription], int]:
        """The subscriptions of this pass (the configuration is read once per pass) and ``max_attempts``."""
        try:
            loaded = _settings.load(self.project, env=self.env, home=self.home, config_file=self.config_file)
        except ExtError as exc:
            record_config_error(self.jdir, exc, now=self.now)
            raise
        self.loaded, self.units, self._registrations = loaded, _units.discover_units(self.env), None
        subscriptions, problems = resolve_subscriptions(loaded, self.units, self.project)
        for problem in problems:
            self.report.problem(problem["code"], problem["message"], problem["subscription"])
        return subscriptions, loaded.max_attempts

    def plugin_registrations(self) -> List["_plugins.Registration"]:
        """The plugins of this pass (read once per pass, after :meth:`subscriptions`)."""
        if self._registrations is None:
            assert self.loaded is not None
            self._registrations, _problems = _plugins.registered_plugins(self.loaded, units=self.units, env=self.env)
        return self._registrations

    def plugin_problem(self, subscription: "Subscription") -> Optional[Tuple[str, str]]:
        assert subscription.plugin is not None
        return _plugins.subscriber_problem(self.plugin_registrations(), subscription.plugin, subscription.on)


def _attempt(run: _Run, subscription: Subscription, event: Event, attempt: int) -> Tuple[str, Optional[str],
                                                                                           ProcessResult]:
    """One run of the subscriber command or plugin: ``(outcome, code, result)``, outcome ok, skipped or failed."""
    if subscription.plugin is not None:
        registration = {item.id: item for item in run.plugin_registrations()}[subscription.plugin]
        return _plugins.deliver_event(registration, event.to_json(), attempt=attempt,
                                      deadline_s=subscription.timeout_seconds, env=run.env, project=run.project)
    assert subscription.run is not None
    extra = {"SKM_EVENT_JOURNAL": str(run.jdir), "SKM_EVENT_SUBSCRIPTION": subscription.id,
             "SKM_EVENT_ATTEMPT": str(attempt)}
    if run.project is not None:
        extra["SKM_PROJECT_ROOT"] = run.project
    child_env, secrets = clean_environment(run.source_env(), trusted=True, extra=extra)
    result = run_json(list(subscription.run), event.to_json(), deadline_s=subscription.timeout_seconds,
                      env=child_env, cwd=run.project or str(run.jdir), secrets_to_redact=secrets)
    if not result.ok:
        return "failed", result.code or "PROCESS_EXIT", result
    if result.document is None:
        return "ok", None, result
    status = result.document.get("status")
    if status in _SUCCESS:
        return status, None, result
    return "failed", "PROTOCOL_STDOUT", result


def _record(run: _Run, subscription: Subscription, event: Event, attempt: int, outcome: str,
            code: Optional[str], result: ProcessResult, *, replay: bool = False) -> None:
    record = {"time": run.time(), "subscription": subscription.id, "event_id": event.id, "offset": event.offset,
              "attempt": attempt, "outcome": outcome, "duration_ms": result.duration_ms, "exit": result.exit,
              "code": code, "stderr_tail": result.stderr_tail}
    if replay:
        record["replay"] = True
    run.report.attempts.append(record)
    _log(run.jdir, record)


def _new_cursor(run: _Run, snapshot: int) -> Dict[str, Any]:
    """I12: the triggering event of an automatic delivery, otherwise the end of the journal."""
    offset = snapshot
    trigger = run.trigger_offset
    if trigger is not None and 0 <= trigger < snapshot and _is_line_start(run.jdir, trigger):
        offset = trigger
    return {"offset": offset, "last_offset": None, "last_id": None, "pending": None}


def _reconcile(lock: DeliverLock, run: _Run, subscription: Subscription, cursor: Dict[str, Any],
               cursors: Dict[str, Dict[str, Any]], snapshot: int) -> Dict[str, Any]:
    """I13: a cursor that no longer fits the journal starts again like a new one (the triggering event, else
    the end), with a ``JOURNAL_RESET`` record."""
    fits = cursor["offset"] <= snapshot and (cursor["offset"] == snapshot or _is_line_start(run.jdir, cursor["offset"]))
    if fits and cursor["last_offset"] is not None:
        doc = journal.read_at(run.jdir, cursor["last_offset"])
        fits = (isinstance(doc, dict) and doc.get("id") == cursor["last_id"]
                and cursor["last_offset"] < cursor["offset"])
    if fits:
        return cursor
    fresh = _new_cursor(run, snapshot)
    cursors[subscription.id] = fresh
    save_cursors(lock, cursors)
    run.report.resets += 1
    _log(run.jdir, {"time": run.time(), "subscription": subscription.id, "outcome": "reset",
                    "code": "JOURNAL_RESET", "offset": cursor["offset"], "new_offset": fresh["offset"]})
    warn_once("JOURNAL_RESET", f"the journal in {run.jdir} no longer holds the last event of {subscription.id}; "
              "its cursor starts again from new events", key=f"{run.jdir}:{subscription.id}:{cursor['offset']}")
    return fresh


def _deliver_subscription(lock: DeliverLock, run: _Run, subscription: Subscription,
                          cursors: Dict[str, Dict[str, Any]], snapshot: int, max_attempts: int,
                          cache: Dict[int, Entry]) -> int:
    """I8 and I10 for one subscription; returns the offset up to which the journal was read."""
    cursor = cursors.get(subscription.id)
    if cursor is None:
        cursor = cursors[subscription.id] = _new_cursor(run, snapshot)
        save_cursors(lock, cursors)
    else:
        cursor = _reconcile(lock, run, subscription, cursor, cursors, snapshot)
    covered = snapshot
    dirty = False
    for offset, end, event, problem in _entries(run.jdir, cursor["offset"], snapshot, cache):
        covered = max(covered, end)
        if event is None:
            assert problem is not None
            warn_once(problem["code"], f"the journal line at offset {offset} in {run.jdir} was skipped: "
                      f"{problem['message']}", key=f"{run.jdir}:{offset}")
            cursor["offset"] = end
            dirty = True
            continue
        if not match(subscription, event.type):
            cursor.update(offset=end, last_offset=offset, last_id=event.id)
            dirty = True
            continue
        pending = cursor.get("pending")
        attempt = pending["attempts"] + 1 if pending and pending["event_id"] == event.id else 1
        outcome, code, result = _attempt(run, subscription, event, attempt)
        if outcome in _SUCCESS:
            _record(run, subscription, event, attempt, outcome, code, result)
            cursor.update(offset=end, last_offset=offset, last_id=event.id, pending=None)
            save_cursors(lock, cursors)
            dirty = False
            run.report.delivered += 1
            continue
        if attempt >= max_attempts:
            _record(run, subscription, event, attempt, "dead-letter", code, result)
            append_dead_letter(lock, {"subscription": subscription.id, "event_id": event.id, "offset": offset,
                                      "attempts": attempt, "last_error": code, "time": run.time()})
            cursor.update(offset=end, last_offset=offset, last_id=event.id, pending=None)
            save_cursors(lock, cursors)
            dirty = False
            run.report.dead_lettered += 1
            continue
        _record(run, subscription, event, attempt, "failed", code, result)
        cursor["pending"] = {"event_id": event.id, "attempts": attempt, "last_error": code}
        save_cursors(lock, cursors)
        run.report.failed += 1
        run.stalled.add(subscription.id)  # order: nothing after this event until the next run (I8)
        return covered
    if dirty:
        save_cursors(lock, cursors)
    return covered


def _pass(lock: DeliverLock, run: _Run) -> int:
    """One pass over every active subscription; returns the journal offset the pass covered."""
    subscriptions, max_attempts = run.subscriptions()
    snapshot = journal.size(run.jdir)
    cursors = load_cursors(run.jdir)
    cache: Dict[int, Entry] = {}  # offsets are stable within a pass (I2), parsed lines are shared
    covered = snapshot
    for subscription in subscriptions:
        if not subscription.enabled or not is_active(subscription, run.project) or subscription.id in run.stalled:
            continue
        if subscription.plugin is not None:
            refusal = run.plugin_problem(subscription)
            if refusal is not None:
                run.report.problem(refusal[0], refusal[1], subscription.id)
                continue
        covered = max(covered, _deliver_subscription(lock, run, subscription, cursors, snapshot, max_attempts,
                                                     cache))
    run.report.passes += 1
    return covered


def _drive(run: _Run, *, wait: Union[bool, float],
           prepare: Optional[Callable[[DeliverLock], None]] = None) -> DeliveryReport:
    """Passes under the lock until the journal stops growing (I6, I7)."""
    first = True
    while True:
        with _deliver_lock(run.jdir, wait=wait if first else False) as lock:
            if lock is None:
                run.report.busy = first
                return run.report
            if first and prepare is not None:
                prepare(lock)
            first = False
            covered = _pass(lock, run)
        if journal.size(run.jdir) <= covered:  # checked after releasing the lock: no lost wake-up (I7)
            return run.report


def _root(project: Optional[PathLike]) -> Optional[str]:
    return os.path.abspath(project) if project is not None else None


def deliver(jdir: PathLike, *, trigger_offset: Optional[int] = None, project: Optional[PathLike] = None,
            env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None,
            config_file: Optional[PathLike] = None, wait: Union[bool, float] = False,
            now: Any = None) -> DeliveryReport:
    """Deliver the pending events of the journal in ``jdir`` to the active subscriptions of ``project``.

    ``trigger_offset`` is the event that started an automatic delivery (new subscriptions start there).
    ``wait`` false returns at once with ``busy`` when another deliverer runs; true waits up to 30 s.
    Raises ``ExtError`` for an invalid configuration (``CONFIG_INVALID``) or a lock that stays busy
    (``DELIVERY_LOCKED``), ``OSError`` when the delivery state cannot be written.
    """
    root = Path(jdir)
    run = _Run(root, _root(project), env, home, config_file, trigger_offset, now)
    if not journal.journal_path(root).exists():
        return run.report
    return _drive(run, wait=wait)


def replay(jdir: PathLike, subscription_id: str, *, from_event: Optional[str] = None, from_start: bool = False,
           event_id: Optional[str] = None, project: Optional[PathLike] = None,
           env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None,
           config_file: Optional[PathLike] = None, wait: Union[bool, float] = True,
           now: Any = None) -> DeliveryReport:
    """Deliver again: rewind the cursor (``from_start``, ``from_event``) or send one event (``event_id``,
    for example from the dead-letter list) outside the cursor; then deliver as usual.

    Exactly one of the three is given (``ValueError`` otherwise). ``SUBSCRIPTION_UNKNOWN`` for an id that is
    not configured, ``SUBSCRIPTION_INACTIVE`` for one that is off for this journal, ``EVENT_NOT_FOUND`` for
    an event that is not in the journal.
    """
    if [from_start, from_event is not None, event_id is not None].count(True) != 1:
        raise ValueError("choose exactly one of from_start, from_event and event_id")
    root = Path(jdir)
    run = _Run(root, _root(project), env, home, config_file, None, now)

    def prepare(lock: DeliverLock) -> None:
        subscriptions, _max_attempts = run.subscriptions()
        subscription = {item.id: item for item in subscriptions}.get(subscription_id)
        if subscription is None:
            raise ExtError("SUBSCRIPTION_UNKNOWN", f"no subscription {subscription_id}")
        if not subscription.enabled or not is_active(subscription, run.project):
            raise ExtError("SUBSCRIPTION_INACTIVE", f"subscription {subscription_id} is switched off for this "
                           "journal")
        if subscription.plugin is not None:
            refusal = run.plugin_problem(subscription)
            if refusal is not None:
                raise ExtError(refusal[0], refusal[1])
        if event_id is not None:
            _offset, _end, event = _find_event(root, event_id)
            outcome, code, result = _attempt(run, subscription, event, 1)
            _record(run, subscription, event, 1, outcome, code, result, replay=True)
            if outcome in _SUCCESS:
                run.report.delivered += 1
            else:
                run.report.failed += 1
            return
        offset = 0 if from_start else _find_event(root, str(from_event))[0]
        cursors = load_cursors(root)
        cursors[subscription.id] = {"offset": offset, "last_offset": None, "last_id": None, "pending": None}
        save_cursors(lock, cursors)
        _log(root, {"time": run.time(), "subscription": subscription.id, "outcome": "rewind", "code": None,
                    "offset": offset})

    return _drive(run, wait=wait, prepare=prepare)


# --- status --------------------------------------------------------------------------------------------------

def delivery_status(jdir: PathLike, *, project: Optional[PathLike] = None,
                    env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None,
                    config_file: Optional[PathLike] = None) -> Dict[str, Any]:
    """Read-only state: ``{"subscriptions": [...], "malformed": n, "resets": n, "problems": [...]}``.

    Each subscription has ``id, origin, enabled, active, plugin, on, offset, lag`` (matching events after the
    cursor), ``pending`` and ``dead_letters`` (entries not yet delivered by a replay). A plugin subscription
    whose plugin cannot receive it is reported in ``problems``.
    """
    root = Path(jdir)
    project_root = _root(project)
    problems: List[Problem] = []
    registrations: List[_plugins.Registration] = []
    try:
        loaded = _settings.load(project_root, env=env, home=home, config_file=config_file)
    except ExtError as exc:
        subscriptions: List[Subscription] = []
        problems.append(_problem(exc.code, exc.message))
    else:
        units = _units.discover_units(env)
        subscriptions, problems = resolve_subscriptions(loaded, units, project_root)
        registrations, _plugin_problems = _plugins.registered_plugins(loaded, units=units, env=env)
    index: List[Tuple[int, str]] = []
    malformed = 0
    for offset, _end, event, _found in _entries(root, 0, journal.size(root), {}):
        if event is None:
            malformed += 1
        else:
            index.append((offset, event.type))
    cursors = load_cursors(root)
    records = _read_records(deliveries_path(root))
    replayed = {(item.get("subscription"), item.get("event_id")) for item in records
                if item.get("replay") and item.get("outcome") in _SUCCESS}
    dead: Dict[str, int] = {}
    for item in _read_records(dead_letter_path(root)):
        if (item.get("subscription"), item.get("event_id")) not in replayed:
            name = str(item.get("subscription"))
            dead[name] = dead.get(name, 0) + 1
    rows = []
    for subscription in subscriptions:
        cursor = cursors.get(subscription.id)
        offset = cursor["offset"] if cursor else None
        lag = 0 if offset is None else sum(1 for at, kind in index if at >= offset and match(subscription, kind))
        active = is_active(subscription, project_root)
        if subscription.plugin is not None and subscription.enabled and active:
            refusal = _plugins.subscriber_problem(registrations, subscription.plugin, subscription.on)
            if refusal is not None:
                problems.append(_problem(refusal[0], refusal[1], subscription.id))
        rows.append({"id": subscription.id, "origin": subscription.origin, "enabled": subscription.enabled,
                     "active": active, "plugin": subscription.plugin, "on": list(subscription.on),
                     "offset": offset, "lag": lag,
                     "pending": cursor.get("pending") if cursor else None,
                     "dead_letters": dead.get(subscription.id, 0)})
    resets = sum(1 for item in records if item.get("code") == "JOURNAL_RESET")
    return {"subscriptions": rows, "malformed": malformed, "resets": resets, "problems": problems}


# --- the background deliverer --------------------------------------------------------------------------------

_SPAWNED: List["subprocess.Popen[bytes]"] = []


def spawn_background(jdir: PathLike, *, trigger_offset: int, project: Optional[PathLike] = None,
                     env: Optional[Mapping[str, str]] = None, config_file: Optional[PathLike] = None,
                     strict: bool = False) -> Optional["subprocess.Popen[bytes]"]:
    """Start ``aicore events deliver`` for the journal in a detached session and return without waiting.

    The child gets ``env`` (default: this process's environment) with this foundation first on
    ``PYTHONPATH``. A failure to start is a warning and None (``strict``: ``ExtError("DELIVERY_SPAWN")``).
    """
    _SPAWNED[:] = [proc for proc in _SPAWNED if proc.poll() is None]  # reap deliverers that are done
    child_env = dict(os.environ if env is None else env)
    lib = str(Path(__file__).resolve().parents[2])
    child_env["PYTHONPATH"] = lib + (os.pathsep + child_env["PYTHONPATH"] if child_env.get("PYTHONPATH") else "")
    argv = [sys.executable, "-m", "aicore", "events", "deliver", "--journal", str(jdir),
            "--trigger-offset", str(int(trigger_offset))]
    if project is not None:
        argv += ["--project", os.path.abspath(project)]
    if config_file is not None:
        argv += ["--config-file", os.path.abspath(config_file)]
    try:
        proc = subprocess.Popen(argv, start_new_session=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, env=child_env, cwd=str(jdir), close_fds=True)
    except OSError as exc:
        message = f"the background deliverer could not start: {exc.strerror or exc.__class__.__name__}"
        if strict:
            raise ExtError("DELIVERY_SPAWN", message) from None
        warn_once("DELIVERY_SPAWN", message, key=str(jdir))
        return None
    _SPAWNED.append(proc)
    return proc
