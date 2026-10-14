"""Capacity gate: a provider whose account quota is known to be exhausted is not started again before the reset.

The state is a machine file, ``<state>/orch/provider-gates.json`` (``provider-gates/v1``): a usage limit is a property
of the account, not of a project, so every conductor of the machine reads and writes the same file.

Invariant: an entry ``{until, class, code, set_by, set_at}`` of a provider with ``until`` in the future means "do not
start this provider before ``until``". An expired entry is ignored when read and dropped by the next write; of two
writes for one provider the later ``until`` wins. A write is a read-modify-write under an exclusive ``flock`` on the
sibling ``provider-gates.lock`` and replaces the file atomically (``os.replace``), so a reader without the lock sees the
old or the new file, never a torn one. Removing the file by hand (or ``conduct.py gates --clear``) resets the gates.

A gate only spares a provider a doomed start, so a file that cannot be trusted (missing, damaged, a symlink, not a regular
file) means "no gates" when read and ``GATES_UNSAFE`` when a write would have to go through it. ``until`` is stored rounded
up to the second: a gate never opens early. POSIX only (``fcntl.flock``); stdlib and aicore only.
"""
from __future__ import annotations

import calendar
import errno
import fcntl
import json
import math
import os
from pathlib import Path
import re
import stat
import time
from typing import Mapping, Optional

from aicore.state import locations
from aicore.util import io

SCHEMA = "provider-gates/v1"
FILE = "provider-gates.json"
LOCK_FILE = "provider-gates.lock"
LOCK_TIMEOUT_S = 10.0
LOCK_POLL_S = 0.02
_PROVIDER_RE = re.compile(r"[a-z][a-z0-9-]*")
_TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_ENTRY_KEYS = ("until", "class", "code", "set_by", "set_at")


class GateError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def path(*, env: Optional[Mapping[str, str]] = None, home=None) -> Path:
    """The gates file of the machine (nothing is created)."""
    return locations.state_dir("orch", env=env, home=home) / FILE


def _stamp(epoch: float) -> str:
    return time.strftime(_TIME_FORMAT, time.gmtime(epoch))


def _epoch(value: object) -> Optional[float]:
    if not isinstance(value, str):
        return None
    try:
        return float(calendar.timegm(time.strptime(value, _TIME_FORMAT)))
    except ValueError:
        return None


def _read(file: Path) -> dict:
    """Valid entries of the file as ``{provider: entry}``; a missing, damaged or untrusted file is no gates.

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
            doc = json.loads(handle.read())
    except (OSError, ValueError):
        return {}
    finally:
        os.close(fd)
    gates = doc.get("gates") if isinstance(doc, dict) and doc.get("schema") == SCHEMA else None
    if not isinstance(gates, dict):
        return {}
    return {name: {key: entry[key] if isinstance(entry.get(key), str) else "unknown" for key in _ENTRY_KEYS}
            for name, entry in gates.items()
            if isinstance(name, str) and _PROVIDER_RE.fullmatch(name) and isinstance(entry, dict)
            and _epoch(entry.get("until")) is not None}


def active(now: float, *, file: Optional[Path] = None) -> dict:
    """The gates still in force at ``now`` (lock-free read)."""
    found = _read(file or path())
    return {name: entry for name, entry in found.items() if _epoch(entry["until"]) > now}


def blocked(provider: str, now: float, *, file: Optional[Path] = None) -> Optional[dict]:
    """The gate entry that forbids starting ``provider`` at ``now``, or ``None``."""
    return active(now, file=file).get(provider)


class _Locked:
    """Exclusive ``flock`` on the lock file beside the gates file, held for a read-modify-write.

    The lock is only good while its file is the one at the path: when the file was replaced between ``open`` and
    ``flock`` (someone removed it), the descriptor guards a dead inode, so the lock is taken again on the new file.
    """

    def __init__(self, file: Path):
        self.file = file
        self.fd = None

    def __enter__(self):
        self.file.parent.mkdir(parents=True, exist_ok=True)
        lock = self.file.with_name(LOCK_FILE)
        deadline = time.monotonic() + LOCK_TIMEOUT_S
        while True:
            fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                os.close(fd)
                if error.errno not in (errno.EAGAIN, errno.EACCES):  # anything but "held by another process"
                    raise
            else:
                try:
                    current = os.path.samestat(os.fstat(fd), os.stat(lock))
                except FileNotFoundError:
                    current = False
                if current:
                    self.fd = fd
                    return self
                os.close(fd)  # the lock file was replaced under us: lock the one that is there now
            if time.monotonic() >= deadline:
                raise GateError("GATES_LOCKED", f"{lock} is held by another process for more than {LOCK_TIMEOUT_S:g} s")
            time.sleep(LOCK_POLL_S)

    def __exit__(self, *exc):
        try:
            fcntl.flock(self.fd, fcntl.LOCK_UN)  # a forked copy of the descriptor must not keep the lock
        finally:
            os.close(self.fd)


def _write(file: Path, gates: dict) -> None:
    leftover = file.with_name(file.name + ".tmp")  # the temp name of the atomic writer; a planted symlink is dropped
    try:
        if leftover.is_symlink():
            leftover.unlink()
        io.atomic_write_json(file, {"schema": SCHEMA, "gates": gates}, indent=2)
    except OSError as error:
        raise GateError("GATES_UNSAFE", f"cannot write {file}: {error}") from error


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
