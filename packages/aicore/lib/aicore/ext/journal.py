"""The event journal file: append-only writes under a lock, reads of complete lines only.

This module is the only writer of the journal (see the architecture test). A journal lives in a
*journal directory* ``J``: ``<project>/.swissknifeman/state`` for a project (``projects/<code>/local/state`` of its
workspace when the project marker names one), else the machine state
folder ``events``. ``J`` holds the journal itself, ``ext/journal.lock`` and the delivery files.

Rules (the byte offset of a line is its stable address; nothing here rewrites or truncates):

* ``append`` writes one line with a single ``os.write`` on a ``O_APPEND`` descriptor while holding an
  exclusive ``flock`` on ``ext/journal.lock``, then ``fsync``. If the file does not end with a newline
  (a torn tail left by a crash) a newline is written first, so the torn line stays a broken line of
  its own and the new event starts on a fresh one.
* readers take the file size once and see only lines that are complete (end with a newline) within
  that snapshot; a trailing incomplete line belongs to a concurrent ``append``.
* a line longer than ``MAX_LINE`` bytes is reported as a problem and skipped, never buffered whole.

POSIX only (``fcntl.flock``); file systems without ``flock`` are not supported. stdlib only.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Iterator, Mapping, Optional, Tuple, Union

from ..state import ensure_dir, project_state_dir, state_dir
from ..util.lock import FileLock
from .errors import ExtError

JOURNAL_FILE = "events.jsonl"
LOCK_FILE = "journal.lock"
EXT_DIRNAME = "ext"
MAX_LINE = 262144
LOCK_TIMEOUT_S = 10.0
LOCK_POLL_S = 0.05
_BLOCK = 65536

PathLike = Union[str, "os.PathLike[str]"]

# A flock lives as long as any copy of its descriptor does, and a forked child inherits copies. A fork made by
# another thread while ``append`` runs would therefore keep the lock after the parent released it; the fork
# hooks make such a fork wait until the append is over.
_fork_lock = threading.RLock()

if hasattr(os, "register_at_fork"):
    os.register_at_fork(before=_fork_lock.acquire, after_in_parent=_fork_lock.release,
                        after_in_child=_fork_lock.release)


def journal_dir(project: Optional[PathLike] = None, *, env: Optional[Mapping[str, str]] = None,
                home: Optional[PathLike] = None) -> Path:
    """The journal directory of ``project`` (a project root), or the machine one when ``project`` is None."""
    if project is not None:
        return project_state_dir(project, env=env, home=home)
    return state_dir("events", env=env, home=home)


def journal_path(jdir: PathLike) -> Path:
    return Path(jdir) / JOURNAL_FILE


def lock_path(jdir: PathLike) -> Path:
    return Path(jdir) / EXT_DIRNAME / LOCK_FILE


def size(jdir: PathLike) -> int:
    """Size of the journal in bytes; 0 when there is none."""
    try:
        return os.stat(journal_path(jdir)).st_size
    except FileNotFoundError:
        return 0


def append(jdir: PathLike, line: bytes, *, lock_timeout_s: float = LOCK_TIMEOUT_S) -> int:
    """Append one line and return the byte offset where it starts.

    ``line`` is one JSON text without a newline inside; a trailing newline is added when missing. Raises
    ``ValueError`` for a line with an inner newline, ``ExtError("JOURNAL_LINE_TOO_LARGE")`` above
    ``MAX_LINE``, ``ExtError("JOURNAL_LOCKED")`` when the lock stays busy, and ``OSError`` for I/O failures.
    """
    if not isinstance(line, (bytes, bytearray)):
        raise TypeError("a journal line must be bytes")
    body = bytes(line)[:-1] if line.endswith(b"\n") else bytes(line)
    if b"\n" in body:
        raise ValueError("a journal line must not contain a newline")
    if len(body) + 1 > MAX_LINE:
        raise ExtError("JOURNAL_LINE_TOO_LARGE", f"a journal line is limited to {MAX_LINE} bytes")
    root = Path(jdir)
    ensure_dir(root)
    ensure_dir(root / EXT_DIRNAME)
    with _fork_lock:
        lock = FileLock(lock_path(root))
        if not lock.acquire(blocking=True, timeout=lock_timeout_s, poll=LOCK_POLL_S):
            raise ExtError("JOURNAL_LOCKED", f"the journal lock {lock_path(root)} is held by another process for "
                           f"more than {lock_timeout_s:g} s")
        try:
            fd = os.open(journal_path(root), os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
            try:
                current = os.fstat(fd).st_size
                torn = current > 0 and os.pread(fd, 1, current - 1) != b"\n"
                data = (b"\n" if torn else b"") + body + b"\n"
                offset = current + (1 if torn else 0)
                view = memoryview(data)
                while view:  # a regular file takes the whole buffer at once; the loop only covers short writes
                    written = os.write(fd, view)
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            lock.release()
    return offset


Entry = Tuple[int, Optional[bytes], Optional[str]]


def iter_lines(jdir: PathLike, start: int = 0) -> Iterator[Entry]:
    """Yield ``(offset, line, problem)`` for each complete line from byte ``start`` to the size seen now.

    ``line`` excludes the newline. ``problem`` is ``"too-long"`` (line is ``None``) or ``"empty"``.
    ``start`` must be the offset of a line start; an offset beyond the snapshot yields nothing.
    """
    path = journal_path(jdir)
    try:
        handle = open(path, "rb")
    except FileNotFoundError:
        return
    with handle:
        limit = os.fstat(handle.fileno()).st_size
        if start < 0:
            raise ValueError("start must not be negative")
        position = start
        line_start = start
        pending = bytearray()
        skipping = False
        handle.seek(start)
        while position < limit:
            block = handle.read(min(_BLOCK, limit - position))
            if not block:
                break
            cursor = 0
            while True:
                newline = block.find(b"\n", cursor)
                if newline == -1:
                    if not skipping:
                        pending += block[cursor:]
                        if len(pending) >= MAX_LINE:
                            skipping = True
                            pending = bytearray()
                    break
                if skipping:
                    yield line_start, None, "too-long"
                else:
                    pending += block[cursor:newline]
                    if len(pending) + 1 > MAX_LINE:
                        yield line_start, None, "too-long"
                    elif not pending:
                        yield line_start, None, "empty"
                    else:
                        yield line_start, bytes(pending), None
                pending = bytearray()
                skipping = False
                line_start = position + newline + 1
                cursor = newline + 1
            position += len(block)


def read_at(jdir: PathLike, offset: int) -> Optional[dict]:
    """The JSON object of the line that starts at ``offset``, or None (no such complete line, not an object)."""
    for _offset, line, problem in iter_lines(jdir, offset):
        if problem is not None or line is None:
            return None
        try:
            value = json.loads(line.decode("utf-8"))
        except ValueError:
            return None
        return value if isinstance(value, dict) else None
    return None
