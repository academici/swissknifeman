"""Notes about closed plans: the path, the text and a write that never duplicates or overwrites.

``handle`` is the whole of ``brain note``. The write is the only place where this module changes the vault
and it keeps these invariants (the numbers are used in the comments and in ``tests/test_notes.py``):

* I1  the path of a note is a pure function of the settings, the project folder and the event;
* I2  at most one note per event id in a vault: the ledger and the file at the path are both consulted;
* I3  "check the ledger, check the file, write, append to the ledger" runs under one ``flock``;
* I4  a note appears whole: it is written to a temporary file in the same folder and hard-linked to its name,
      which fails when the name exists, so a reader never sees half a note and nothing is replaced;
* I5  an existing vault file is never overwritten or removed; a file with the same name and another event id
      sends the note to ``name (2).md``, ``name (3).md``, ...;
* I6  the ledger is only appended to, one line per ``write``, under the lock;
* I7  ``ok`` is returned only after the ledger line is written, so a delivery repeated by the event cursor
      answers ``DUPLICATE_EVENT``.

The ledger ``<state>/brain/notes.jsonl`` remembers which event produced which note, so a note that a person
moved or renamed in the vault is not created again. A person who moves a note *and* deletes the ledger gets a
second note: that is the one way around the model and it is documented in the README.
"""
from __future__ import annotations

import datetime
import errno
import fcntl
import json
import os
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Tuple, Union

from aicore.ext import emit as _emit
from aicore.ext.errors import ExtError
from aicore.ext.events import check_data, contracts_strict
from aicore.state import ensure_dir, state_dir

from . import catalog, errors, events, frontmatter, settings as _settings, vault as _vault
from .errors import BrainError

LOCK_DEADLINE_S = 10.0
LOCK_POLL_S = 0.05
MAX_SUFFIX = 1000
CREATED_EVENT = "brain.note.created"
CREATED_SCHEMA = "urn:swissknifeman:brain:event-data:brain-note-created:v1"
DATA_DIR = Path(__file__).resolve().parents[2] / "schemas" / "event-data" / "v1"
LOCK_FILE = "notes.lock"
LEDGER_FILE = "notes.jsonl"
_NO_LINKS = (errno.EPERM, errno.ENOTSUP, errno.ENOSYS, errno.EMLINK)
_COUNT_LABELS = {"items": "items", "done": "done", "done_with_deviations": "done with deviations",
                 "skipped": "skipped", "blocked": "blocked"}

PathLike = Union[str, "os.PathLike[str]"]


@dataclass
class NoteResult:
    """The answer of the subscriber: ``ok`` (a note was written) or ``skipped`` with a ``reason``."""

    status: str
    reason: Optional[str] = None
    note: Optional[str] = None
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        doc: Dict[str, Any] = {"status": self.status}
        if self.reason is not None:
            doc["reason"] = self.reason
        if self.note is not None:
            doc["note"] = self.note
        return doc


# --- the pure part: names and text -------------------------------------------------------------------------

def _clean_plan_id(plan_id: str) -> str:
    text = "".join("-" if ch in "/\\" or ord(ch) < 32 or ord(ch) == 127 else ch for ch in plan_id)
    return text.strip().lstrip(".").strip()[:100].rstrip() or "plan"


def note_name(plan: events.PlanClosed) -> str:
    """``<YYYY-MM-DD> <plan_id> closed <id8>.md``: the date is the UTC date of the closing time."""
    day = plan.closed_utc().strftime("%Y-%m-%d")
    return f"{day} {_clean_plan_id(plan.plan_id)} closed {plan.event_id.replace('-', '')[:8]}.md"


def note_path(config: _settings.BrainSettings, vault: PathLike, project: Optional[catalog.VaultProject],
              plan: events.PlanClosed) -> Path:
    """Where the note of ``plan`` goes (I1): inside the project folder of the vault, else in the fallback folder.

    Touches no file; only the arguments decide the answer.
    """
    if project is not None:
        return project.folder / config.notes_folder / note_name(plan)
    return Path(vault) / config.notes_fallback_folder / note_name(plan)


def vault_relative(path: Path, vault: Path) -> Optional[str]:
    """``path`` below the vault root with ``/`` separators (links resolved on both sides), None when it is outside."""
    relative = os.path.relpath(os.path.realpath(path), os.path.realpath(vault))
    if relative == ".." or relative.startswith(".." + os.sep) or os.path.isabs(relative):
        return None
    return relative.replace(os.sep, "/")


def _ledger_name(path: Path, vault: Path) -> Optional[str]:
    """The note name below the vault for the ledger and the answer: links resolved, else the path as written."""
    relative = vault_relative(path, vault)
    if relative is None:  # an entry in the vault that links to a file elsewhere
        try:
            relative = path.relative_to(vault).as_posix()
        except ValueError:
            return None
    return relative


def _one_line(text: str) -> str:
    return " ".join(text.split())


def _cell(text: str) -> str:
    return _one_line(text).replace("|", "\\|")


def render(plan: events.PlanClosed, project_name: Optional[str]) -> str:
    """The text of the note: frontmatter, the title, the goal, the phases, the counts and the closing line."""
    fields: List[Tuple[str, Any]] = [("type", "plan-closed"), ("plan", plan.plan_id)]
    if plan.short_id:
        fields.append(("short_id", plan.short_id))
    if plan.status:
        fields.append(("status", plan.status))
    fields.append(("closed", plan.closed))
    if project_name:
        fields.append(("project", project_name))
    if plan.repository:
        fields.append(("repository", plan.repository))
    fields += [("event_id", plan.event_id), ("event_source", plan.event_source), ("tags", ["plan", "closed"])]
    parts = [frontmatter.render(fields), f"# {_one_line(plan.title)}\n"]
    if plan.goal and plan.goal.strip():
        quoted = [f"> {line}".rstrip() for line in plan.goal.strip().splitlines()]
        parts.append("\n".join(quoted) + "\n")
    if plan.phases:
        rows = ["| Phase | Title | Status |", "| --- | --- | --- |"]
        rows += [f"| {_cell(p.id)} | {_cell(p.title)} | {_cell(p.status)} |" for p in plan.phases]
        parts.append("\n".join(rows) + "\n")
    if plan.counts:
        parts.append("Counts: " + ", ".join(f"{_COUNT_LABELS[key]} {number}" for key, number in plan.counts) + ".\n")
    parts.append(f"Closed {plan.closed}.\n")
    return "\n".join(parts)


# --- the lock and the ledger -------------------------------------------------------------------------------

class LedgerLock:
    """Proof that the caller holds ``notes.lock`` (valid only inside ``with _ledger_lock(...)``)."""

    def __init__(self, directory: Path, fd: int) -> None:
        self.directory = directory
        self.ledger = directory / LEDGER_FILE
        self.fd = fd
        self.held = True
        self.warnings: List[str] = []

    def require(self) -> None:
        if not self.held:
            raise RuntimeError("the notes lock is not held")


@contextmanager
def _ledger_lock(directory: PathLike, deadline_s: float = LOCK_DEADLINE_S) -> Iterator[LedgerLock]:
    """``flock(notes.lock, LOCK_EX)`` in ``directory`` (the state folder), waiting at most ``deadline_s`` (I3)."""
    folder = Path(directory)
    try:
        ensure_dir(folder)
        fd = os.open(folder / LOCK_FILE, os.O_CREAT | os.O_RDWR, 0o600)
    except OSError as exc:
        raise BrainError(errors.NOTE_IO, f"the notes lock in {folder} cannot be opened: {exc.strerror or exc}") from None
    try:
        stop = time.monotonic() + deadline_s
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if exc.errno not in (errno.EAGAIN, errno.EACCES):
                    raise BrainError(errors.NOTE_IO, f"the notes lock cannot be taken: {exc.strerror or exc}") from None
                if time.monotonic() >= stop:
                    raise BrainError(errors.LEDGER_LOCKED,
                                     f"another brain process holds the notes lock for more than {deadline_s:g} s; "
                                     "the next delivery retries") from None
                time.sleep(LOCK_POLL_S)
        lock = LedgerLock(folder, fd)
        try:
            yield lock
        finally:
            lock.held = False
    finally:
        os.close(fd)  # closing the descriptor releases the flock


def _read_ledger(lock: LedgerLock) -> Dict[str, Dict[str, Any]]:
    """The ledger by event id and vault; a broken line is skipped with a warning (I6)."""
    lock.require()
    records: Dict[str, Dict[str, Any]] = {}
    try:
        raw = lock.ledger.read_bytes()
    except FileNotFoundError:
        return records
    for number, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except ValueError:
            record = None
        if (isinstance(record, dict) and isinstance(record.get("event_id"), str)
                and isinstance(record.get("note"), str) and isinstance(record.get("vault"), str)):
            records.setdefault(f"{record['vault']}\0{record['event_id']}", record)
        else:
            lock.warnings.append(f"{lock.ledger}: line {number} is not a note record and was skipped")
    return records


def _append_ledger(lock: LedgerLock, record: Mapping[str, Any]) -> None:
    """Append one line with a single ``write`` and flush it to disk (I6)."""
    lock.require()
    line = (json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(lock.ledger, os.O_RDWR | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        size = os.fstat(fd).st_size
        if size and os.pread(fd, 1, size - 1) != b"\n":  # a torn last line: start the record on a new line
            line = b"\n" + line
        os.write(fd, line)
        os.fsync(fd)
    finally:
        os.close(fd)


# --- the write ---------------------------------------------------------------------------------------------

def _write_all(fd: int, data: bytes) -> None:
    """Write every byte of ``data`` (``os.write`` may store less) and flush it."""
    view = memoryview(data)
    while view:
        view = view[os.write(fd, view):]
    os.fsync(fd)


def _open_temporary(folder: Path, name: str) -> Tuple[int, Path]:
    """Open a new temporary file next to the note; an existing file of any name is never touched."""
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    for _ in range(100):
        tmp = folder / f"{name}.tmp-{os.getpid()}-{os.urandom(4).hex()}"
        try:
            return os.open(tmp, flags, 0o644), tmp
        except FileExistsError:
            continue
    raise OSError(errno.EEXIST, "no free temporary name")


def _unlink_if_ours(path: Path, fd: int) -> None:
    """Remove ``path`` only while it is still the file ``fd`` opened (never a file put there by someone else)."""
    try:
        opened, current = os.fstat(fd), os.lstat(path)
        if (opened.st_dev, opened.st_ino) == (current.st_dev, current.st_ino):
            os.unlink(path)
    except OSError:
        pass


def _create_new(lock: LedgerLock, path: Path, text: str) -> bool:
    """Create ``path`` with ``text`` unless it exists; True when this call created it (I4, I5)."""
    lock.require()
    folder = path.parent
    os.makedirs(folder, exist_ok=True)
    data = text.encode("utf-8")
    fd, tmp = _open_temporary(folder, path.name)
    try:
        try:
            _write_all(fd, data)
        finally:
            os.close(fd)
        try:
            os.link(tmp, path)
        except FileExistsError:
            return False
        except OSError as exc:
            if exc.errno not in _NO_LINKS:
                raise
            # A file system without hard links: create the name exclusively and write in place.
            try:
                target = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            except FileExistsError:
                return False
            try:
                _write_all(target, data)
            except BaseException:
                _unlink_if_ours(path, target)  # a retry must find the name free
                raise
            finally:
                os.close(target)
        return True
    finally:
        try:
            os.unlink(tmp)
        except FileNotFoundError:
            pass


def _suffixed(path: Path, number: int) -> Path:
    return path if number == 1 else path.with_name(f"{path.stem} ({number}){path.suffix}")


def _write_once(lock: LedgerLock, path: Path, text: str, event_id: str, *, vault: Path,
                now: datetime.datetime) -> Tuple[str, Path]:
    """I2-I7: ``("created", path)`` or ``("duplicate", path of the existing note)``. Needs the lock."""
    lock.require()
    records = _read_ledger(lock)
    known = records.get(f"{vault}\0{event_id}")
    if known is not None:
        return "duplicate", vault / known["note"]

    def record(note: Path) -> None:
        name = _ledger_name(note, vault)
        if name is not None:  # without a name the frontmatter scan below still finds the note
            _append_ledger(lock, {"event_id": event_id, "note": name, "vault": str(vault),
                                  "time": now.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")})

    for number in range(1, MAX_SUFFIX + 1):
        candidate = _suffixed(path, number)
        if os.path.lexists(candidate):
            if frontmatter.read(candidate).get("event_id") == event_id:
                record(candidate)  # repairs a ledger that lost this event
                return "duplicate", candidate
            continue
        if _create_new(lock, candidate, text):
            record(candidate)
            return "created", candidate
        if frontmatter.read(candidate).get("event_id") == event_id:  # created by someone else meanwhile
            record(candidate)
            return "duplicate", candidate
    raise BrainError(errors.NOTE_IO, f"no free name for {path.name} after {MAX_SUFFIX} tries")


def _announce(plan: events.PlanClosed, note: str, project_root: Optional[Path], env: Optional[Mapping[str, str]],
              home: Optional[PathLike], warnings: List[str]) -> None:
    """Emit ``brain.note.created``; best effort, a failure is a warning and never changes the answer.

    Data that breaks the schema of the event is not emitted (``BRAIN_EVENT_NOT_EMITTED: ...: EVENT_DATA_INVALID``);
    under ``SKM_CONTRACTS_STRICT=1`` it raises ``ExtError('EVENT_DATA_INVALID')`` instead.
    """
    data = {"note": note, "plan_id": plan.plan_id, "event_id": plan.event_id}
    try:
        problem = check_data(data, CREATED_SCHEMA, DATA_DIR, env=env)
        if problem is not None:
            warnings.append(f"BRAIN_EVENT_NOT_EMITTED: {CREATED_EVENT}: EVENT_DATA_INVALID: {problem}")
            return
        _emit(CREATED_EVENT, data, source="brain", subject=plan.plan_id, project=project_root,
              dataschema=CREATED_SCHEMA, causationid=plan.event_id, env=env, home=home)
    except Exception as exc:  # the note is written; announcing it must not turn that into a failure
        if isinstance(exc, ExtError) and exc.code == "EVENT_DATA_INVALID" and contracts_strict(env):
            raise
        warnings.append(f"{CREATED_EVENT} was not emitted: {exc}")


def handle(event_doc: Any, *, project_root: Optional[PathLike], settings: _settings.BrainSettings,
           env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None,
           now: Optional[datetime.datetime] = None, dry_run: bool = False,
           lock_deadline_s: float = LOCK_DEADLINE_S) -> NoteResult:
    """``brain note``: write the note of a ``planner.plan.closed`` event once.

    Raises :class:`BrainError` ``EVENT_DATA_INVALID`` (do not retry) or ``VAULT_UNAVAILABLE``, ``NOTE_IO``,
    ``LEDGER_LOCKED`` (temporary).
    """
    if not settings.notes_enabled:
        return NoteResult("skipped", "NOTES_DISABLED")
    plan, reason = events.parse_plan_closed(event_doc)
    if plan is None:
        return NoteResult("skipped", reason)
    environment = os.environ if env is None else env
    home_path = _settings.home_dir(environment, home)
    info = _vault.resolve_vault(settings, env=environment, home=home_path)
    result = NoteResult("ok")
    result.warnings.extend(list(settings.warnings) + list(info.warnings))
    if info.path is None:
        return NoteResult("skipped", "VAULT_NOT_CONFIGURED", warnings=result.warnings)
    vault_root = info.path
    if not info.exists or not os.access(vault_root, os.W_OK | os.X_OK):
        raise BrainError(errors.VAULT_UNAVAILABLE, f"vault {vault_root} is missing or not writable "
                         f"(source: {info.source}); the next delivery retries")
    root = Path(project_root) if project_root is not None else None
    found = None
    if root is not None:
        found = catalog.find_project(vault_root, root, projects_dir=settings.projects_dir, home=home_path,
                                     warnings=result.warnings)
    name = found.name if found is not None else (root.name if root is not None else None)
    path = note_path(settings, vault_root, found, plan)
    if vault_relative(path, vault_root) is None:  # a catalog entry that points out of the vault
        result.warnings.append(_settings.warning(
            errors.CATALOG_INVALID, f"the folder {found.folder if found else path} of the project is outside "
            f"the vault; the note goes to {settings.notes_fallback_folder}"))
        path = note_path(settings, vault_root, None, plan)
    relative = vault_relative(path, vault_root)
    if relative is None:
        raise BrainError(errors.CONFIG_NOTES_FOLDER, f"the notes folder of {path.parent} is outside the vault")
    if dry_run:
        return NoteResult("skipped", "DRY_RUN", relative, result.warnings)
    text = render(plan, name)
    moment = now or datetime.datetime.now(datetime.timezone.utc)
    try:
        with _ledger_lock(state_dir("brain", env=environment, home=home_path), lock_deadline_s) as lock:
            outcome, written = _write_once(lock, path, text, plan.event_id, vault=vault_root, now=moment)
            result.warnings.extend(lock.warnings)
    except OSError as exc:
        raise BrainError(errors.NOTE_IO, f"the note cannot be written: {exc.strerror or exc}") from None
    result.note = _ledger_name(written, vault_root)
    note = result.note or written.name
    if outcome == "duplicate":
        result.status, result.reason = "skipped", "DUPLICATE_EVENT"
        return result
    _announce(plan, note, root, environment, home_path, result.warnings)
    return result


def warn(messages: List[str]) -> None:
    """Print the warnings of a result to standard error, once each."""
    for message in dict.fromkeys(messages):
        print(f"brain: warning: {message}", file=sys.stderr)
