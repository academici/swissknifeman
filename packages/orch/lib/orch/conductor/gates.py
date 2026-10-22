"""Capacity gate: a provider whose account quota is known to be exhausted is not started again before the reset.

The state is a machine file, ``<state>/orch/provider-gates.json`` (``provider-gates/v1``): a usage limit is a property
of the account, not of a project, so every conductor of the machine reads and writes the same file.

Invariant: an entry ``{until, class, code, set_by, set_at}`` of a provider with ``until`` in the future means "do not
start this provider before ``until``". An expired entry is ignored when read and dropped by the next write; of two
writes for one provider the later ``until`` wins. A write is a read-modify-write under an exclusive ``flock`` on the
sibling ``provider-gates.lock`` and replaces the file crash-safely (``records.write``: checked, fsync, ``os.replace``), so
a reader without the lock sees the old or the new file, never a torn one. Removing the file by hand (or
``orch conduct gates --clear``) resets the gates.

The file is the ``records/v1`` kind ``provider-gates`` (its published tag ``schema`` stays). A missing file, a symlink or
a file that is not regular is not the machine's gates: "no gates" when read and ``GATES_UNSAFE`` when a write would have
to go through it. A regular file that is not JSON (``STATE_CORRUPT``) or not ``provider-gates/v1`` (``RECORD_INVALID``,
with the JSON pointer) is a ``GateError``, a stop of the run that reads it, never read as no gates. ``until`` is stored
rounded up to the second: a gate never opens early. POSIX only (``fcntl.flock``); stdlib and aicore only.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import stat
from typing import Mapping, Optional

from aicore.state import locations
from aicore.util import timefmt
from aicore.util.lock import FileLock

from orch.conductor import records
from orch.conductor.domain.stop import Stop

SCHEMA = "provider-gates/v1"
KIND = "provider-gates"
HINT = "remove the file to reset the gates"
FILE = "provider-gates.json"
LOCK_FILE = "provider-gates.lock"
LOCK_TIMEOUT_S = 10.0
LOCK_POLL_S = 0.02
_PROVIDER_RE = re.compile(r"[a-z][a-z0-9-]*")
_ENTRY_KEYS = ("until", "class", "code", "set_by", "set_at")


class GateError(Stop):
    """A gate that cannot be read or written; a ``Stop`` when it reaches the engine. ``str()`` is the message alone."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message)
        self.args = (message,)


def path(*, env: Optional[Mapping[str, str]] = None, home=None) -> Path:
    """The gates file of the machine (nothing is created)."""
    return locations.state_dir("orch", env=env, home=home) / FILE


def _stamp(epoch: float) -> str:
    return timefmt.utc_stamp(epoch)


def _epoch(value: object) -> Optional[float]:
    return timefmt.epoch(value) if isinstance(value, str) else None


def _read(file: Path) -> dict:
    """Entries of the file as ``{provider: entry}`` (an entry whose ``until`` is not a time is left out); a missing or
    untrusted file is no gates, a damaged one a ``GateError`` (``STATE_CORRUPT``, ``RECORD_INVALID``).

    The file is opened without following a symlink and without blocking (a FIFO must not hang a reader) and must be a
    regular file.
    """
    try:
        fd = os.open(file, os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0))
    except OSError:
        return {}
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            return {}
        with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as handle:
            text = handle.read()
    except OSError:
        return {}
    except UnicodeDecodeError as error:
        raise GateError("STATE_CORRUPT", f"{file} is not JSON ({error}): {HINT}") from None
    finally:
        os.close(fd)
    try:
        doc = json.loads(text)
    except ValueError as error:
        raise GateError("STATE_CORRUPT", f"{file} is not JSON ({error}): {HINT}") from None
    try:
        doc = records.check(doc, KIND, file, hint=HINT)
    except Stop as stop:
        raise GateError(stop.code, stop.message) from None
    return {name: {key: entry[key] if isinstance(entry.get(key), str) else "unknown" for key in _ENTRY_KEYS}
            for name, entry in doc["gates"].items() if _epoch(entry.get("until")) is not None}


def active(now: float, *, file: Optional[Path] = None) -> dict:
    """The gates still in force at ``now`` (lock-free read)."""
    found = _read(file or path())
    return {name: entry for name, entry in found.items() if _epoch(entry["until"]) > now}


def blocked(provider: str, now: float, *, file: Optional[Path] = None) -> Optional[dict]:
    """The gate entry that forbids starting ``provider`` at ``now``, or ``None``."""
    return active(now, file=file).get(provider)


class _Locked:
    """Exclusive ``flock`` on the lock file beside the gates file, held for a read-modify-write.

    The lock is only good while its file is the one at the path (``aicore.util.lock.FileLock`` takes it again on the
    new file when the old one was replaced between ``open`` and ``flock``).
    """

    def __init__(self, file: Path):
        self.file = file
        self.lock: Optional[FileLock] = None

    @property
    def fd(self) -> Optional[int]:
        """The descriptor that holds the lock (``None`` when not held)."""
        return None if self.lock is None else self.lock.fd

    def __enter__(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        path = self.file.with_name(LOCK_FILE)
        lock = FileLock(path)
        if not lock.acquire(blocking=True, timeout=LOCK_TIMEOUT_S, poll=LOCK_POLL_S):
            raise GateError("GATES_LOCKED", f"{path} is held by another process for more than {LOCK_TIMEOUT_S:g} s")
        self.lock = lock
        return self

    def __exit__(self, *exc):
        self.lock.release()  # LOCK_UN first: a forked copy of the descriptor must not keep the lock


def _write(file: Path, gates: dict) -> None:
    """Replace the file under the lock the caller holds (a unique temporary file, never a planted name)."""
    try:
        records.write(file, {"schema": SCHEMA, "gates": gates}, KIND)
    except OSError as error:
        raise GateError("GATES_UNSAFE", f"cannot write {file}: {error}") from error
    except Stop as stop:
        raise GateError(stop.code, stop.message) from None


def set_gate(provider: str, *, until: float, code: str, run_id: str, now: float,
             error_class: str = "quota", file: Optional[Path] = None) -> Optional[dict]:
    """Forbid ``provider`` until ``until`` (unix seconds); returns the entry in force, ``None`` when ``until`` is past.

    An existing entry with a later ``until`` stays. Expired entries of every provider are dropped.
    """
    if not isinstance(provider, str) or not _PROVIDER_RE.fullmatch(provider):
        raise ValueError("provider must be a provider id")
    until = math.ceil(until)
    file = file or path()
    with _Locked(file):
        gates = {name: entry for name, entry in _read(file).items() if _epoch(entry["until"]) > now}
        if until > now:
            known = gates.get(provider)
            if known is None or _epoch(known["until"]) < until:
                gates[provider] = {"until": _stamp(until), "class": error_class, "code": code, "set_by": run_id,
                                   "set_at": _stamp(now)}
        _write(file, gates)
        return gates.get(provider)


def clear(provider: Optional[str] = None, *, file: Optional[Path] = None) -> list:
    """Remove the gate of ``provider`` (every gate when ``None``); returns the providers whose gate was removed."""
    file = file or path()
    with _Locked(file):
        gates = _read(file)
        removed = sorted(gates) if provider is None else ([provider] if provider in gates else [])
        if removed:
            for name in removed:
                del gates[name]
            _write(file, gates)
        return removed
