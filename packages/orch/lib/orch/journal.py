"""Run journal: the only module of this package that reads and writes the files of a run.

A run lives in ``<state>/orch/runs/<run_id>/``: ``events.jsonl`` (append-only run-events), ``events.lock``,
``run.json``, ``launch-plan.json`` and ``receipts/<n>.json``. An event is written under an exclusive ``flock``
on ``events.lock``; a reader sees only complete lines. POSIX only (``fcntl.flock``). Time is never read here.
"""
from __future__ import annotations

from collections.abc import Iterator, Mapping
import errno
import fcntl
import json
import os
from pathlib import Path
import re
import time

from aicore.state import ensure_dir, project_state_dir, state_dir

from orch import contracts
from orch.port import PortError

EVENTS_FILE = "events.jsonl"
LOCK_FILE = "events.lock"
LOCK_TIMEOUT_S = 10.0
LOCK_POLL_S = 0.05
MAX_LINE = 262144
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:@-]{0,159}$")
_DOC_NAME = re.compile(r"^(?:run\.json|launch-plan\.json|receipts/[A-Za-z0-9][A-Za-z0-9._-]{0,80}\.json)$")


def _canonical(doc: object) -> str:
    return json.dumps(doc, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def run_dir(run_id: str, *, project: str | os.PathLike | None = None,
            env: Mapping[str, str] | None = None) -> Path:
    """Directory of a run: under the project state, else under the machine state. Nothing is created."""
    if not isinstance(run_id, str) or not _RUN_ID.match(run_id) or ".." in run_id:
        raise PortError("INPUT_INVALID", f"run id {run_id!r} is not usable as a directory name")
    base = project_state_dir(project, "orch") if project is not None else state_dir("orch", env=env)
    return base / "runs" / run_id


def _acquire(fd: int, path: Path) -> None:
    deadline = time.monotonic() + LOCK_TIMEOUT_S
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            if exc.errno not in (errno.EAGAIN, errno.EACCES):
                raise
        if time.monotonic() >= deadline:
            raise TimeoutError(f"the journal lock {path} stayed busy for {LOCK_TIMEOUT_S:g} s")
        time.sleep(LOCK_POLL_S)


def _complete_lines(path: Path) -> Iterator[bytes]:
    """Complete lines of the file as it is now; a trailing line without a newline is not yet written."""
    try:
        with open(path, "rb") as handle:
            data = handle.read(os.fstat(handle.fileno()).st_size)
    except FileNotFoundError:
        return
    end = data.rfind(b"\n")
    if end < 0:
        return
    yield from data[:end].split(b"\n")


def _events(path: Path) -> Iterator[dict]:
    for line in _complete_lines(path):
        if not line.strip() or len(line) >= MAX_LINE:
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            continue  # a torn line left by a crash stays a broken line of its own
        if isinstance(doc, dict):
            yield doc


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:  # a regular file takes the whole buffer at once; the loop only covers short writes
        view = view[os.write(fd, view):]
    os.fsync(fd)


def append_event(directory: str | os.PathLike, event: dict) -> bool:
    """Append a run-event; ``False`` for an identical repeat, ``EVENT_CONFLICT``/``SEQ_ORDER`` for a clash."""
    directory = Path(directory)
    issues = [issue for issue in contracts.validate(event, "run-event") if issue.level == "error"]
    if issues:
        raise PortError("INPUT_INVALID", "run-event does not match exec/v1",
                        {"issues": [issue._asdict() for issue in issues]})
    if event["run_id"] != directory.name:
        raise PortError("RUN_UNKNOWN", f"event belongs to run {event['run_id']!r}, not {directory.name!r}")
    encoded = _canonical(event)
    body = encoded.encode("utf-8")
    if len(body) + 1 > MAX_LINE:
        raise PortError("INPUT_INVALID", f"a journal line is limited to {MAX_LINE} bytes")
    ensure_dir(directory)
    lock_fd = os.open(directory / LOCK_FILE, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        _acquire(lock_fd, directory / LOCK_FILE)
        path = directory / EVENTS_FILE
        fd = os.open(path, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            size = os.fstat(fd).st_size
            if size > 0 and os.pread(fd, 1, size - 1) != b"\n":
                # A crash left a tail without a newline. Finish the line first: a body that was complete
                # becomes the event it was and takes part in the duplicate check; a partial one stays a broken line.
                _write_all(fd, b"\n")
            for known in _events(path):
                if event.get("event_id") is not None and known.get("event_id") == event["event_id"]:
                    if _canonical(known) == encoded:
                        return False
                    raise PortError("EVENT_CONFLICT",
                                    f"event_id {event['event_id']!r} repeated with different content")
                if known.get("seq") == event["seq"]:
                    if _canonical(known) == encoded:
                        return False
                    raise PortError("SEQ_ORDER", f"seq {event['seq']} repeated with different content")
            _write_all(fd, body + b"\n")
        finally:
            os.close(fd)
    finally:
        os.close(lock_fd)  # closing the descriptor releases the flock
    return True


def read_events(directory: str | os.PathLike, after_seq: int | None = None) -> Iterator[dict]:
    """Events with ``seq > after_seq`` (all when ``None``) in file order; a repeated call gives the same sequence."""
    for doc in _events(Path(directory) / EVENTS_FILE):
        if after_seq is None or (isinstance(doc.get("seq"), int) and doc["seq"] > after_seq):
            yield doc


def _doc_path(directory: str | os.PathLike, name: str) -> Path:
    if not isinstance(name, str) or not _DOC_NAME.match(name):
        raise PortError("INPUT_INVALID", f"{name!r} is not a document of a run")
    return Path(directory) / name


def write_doc(directory: str | os.PathLike, name: str, doc: dict) -> Path:
    """Write ``run.json``, ``launch-plan.json`` or ``receipts/<n>.json`` atomically (temporary file, then replace)."""
    target = _doc_path(directory, name)
    ensure_dir(target.parent)
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(doc, sort_keys=True, ensure_ascii=False, indent=2) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target)
        directory_fd = os.open(target.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | os.O_CLOEXEC)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise
    return target


def read_doc(directory: str | os.PathLike, name: str) -> dict | None:
    """The document, or ``None`` when it was not written."""
    try:
        return json.loads(_doc_path(directory, name).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
