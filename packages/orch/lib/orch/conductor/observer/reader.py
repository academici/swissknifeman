"""What the observer reads: the progress journal (whole, or new lines only through ``ProgressCursor``), the state of the
run, the prompt manifests, the agent runs, the inputs and options of the pieces, the actions of the supervisor
(``supervisor.jsonl``) and the event journal of the project. Never the raw streams of the roles. This is the only module
of the package that opens a file; it never writes one."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

from orch.conductor import agents as agents_mod, contract, progress as progress_mod, records
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure.files import OPTIONS_COPY, STATE_FILE, safe

EVENT_TYPES = ("orch.*", "planner.*")
HEAD_BYTES = 64  # the start of the journal that tells a replaced file from the one the cursor has been reading
SUPERVISOR_FILE = "supervisor.jsonl"  # application.supervisor.ACTIONS_FILE, read here without importing the writer


class ProgressCursor:
    """Reads the lines ``progress.jsonl`` gained since the last call, not the whole journal again.

    ``read_new()`` returns the new complete lines (those ended by ``\\n``) that are ``progress-line`` documents. The bytes
    after the last ``\\n`` are a line the writer has not finished: they are kept in ``tail`` and joined with what comes next,
    never parsed early. A complete line that is not a progress line is skipped and counted in ``discarded``, as
    ``progress.read_lines_counted`` does. A journal that became shorter than the offset, was replaced by another file
    (another inode or another start) or disappeared is read from the beginning again (``restarted`` tells the caller)."""

    def __init__(self, directory: Path):
        self.path = Path(directory) / progress_mod.PROGRESS_FILE
        self.offset = 0      # the bytes of the file consumed so far, the unfinished tail included
        self.tail = b""      # the consumed bytes after the last newline: an unfinished line
        self.discarded = 0   # complete lines that were left out
        self.restarted = False
        self._identity = None
        self._head = b""

    def read_new(self) -> list:
        self.restarted = False
        try:
            with self.path.open("rb") as handle:
                found = os.fstat(handle.fileno())
                if self._replaced(handle, found):
                    self._reset()
                handle.seek(self.offset)
                data = handle.read()
                self._identity = (found.st_dev, found.st_ino)
        except FileNotFoundError:
            if self.offset:
                self._reset()
            return []
        except OSError:  # unreadable for now: the state stays, the next call tries again
            return []
        self.offset += len(data)
        self._head = (self._head + data)[:HEAD_BYTES] if len(self._head) < HEAD_BYTES else self._head
        *rows, self.tail = (self.tail + data).split(b"\n")
        lines = []
        for raw in rows:
            try:
                doc = json.loads(raw)
            except ValueError:
                self.discarded += 1 if raw.strip() else 0
                continue
            if isinstance(doc, dict) and not contract.problems(doc, "progress-line"):
                lines.append(doc)
            else:
                self.discarded += 1
        return lines

    def _replaced(self, handle, found) -> bool:
        if not self.offset:
            return False
        if found.st_size < self.offset or self._identity != (found.st_dev, found.st_ino):
            return True
        handle.seek(0)
        return handle.read(len(self._head)) != self._head

    def _reset(self) -> None:
        self.offset, self.tail, self._head, self._identity = 0, b"", b"", None
        self.restarted = True


def read_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def journal(directory: Path) -> tuple:
    """``(lines, discarded)`` of the whole progress journal; the lines of the sidecar of broken ones count as discarded."""
    lines, discarded = progress_mod.read_lines_counted(directory)
    return lines, discarded + progress_mod.quarantined(directory)


def state(directory: Path) -> dict:
    """``state.json`` of the run, ``{}`` when it is not there or does not fit its record (the report is still written,
    from the journal alone, and says why)."""
    try:
        return records.read(Path(directory) / STATE_FILE, "state") or {}
    except OSError:
        return {}
    except Stop as stop:
        print(f"{stop.code}: {stop.message} (the observer report is built without the state)", file=sys.stderr)
        return {}


def manifests(directory: Path) -> list:
    """``[doc]`` of ``<item>/prompts/*.manifest.json`` in path order; a file that cannot be read is skipped."""
    found = []
    for file in sorted(Path(directory).glob("*/prompts/*.manifest.json")):
        try:
            found.append(json.loads(file.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
    return found


def input_docs(directory: Path, state_doc: dict) -> dict:
    """``{ref: input.json of the piece or None}`` for every piece of the state that is a mapping."""
    return {ref: read_json(Path(directory) / safe(str(ref)) / "input.json")
            for ref, item in (state_doc.get("items") or {}).items() if isinstance(item, dict)}


def item_options(directory: Path, state_doc: dict) -> dict:
    """``{ref: options.json of the piece or None}``; a record that does not fit its schema is said on stderr."""
    found = {}
    for ref in (state_doc.get("items") or {}):
        try:
            doc = records.read(Path(directory) / safe(str(ref)) / OPTIONS_COPY, "item-options")
        except (OSError, Stop) as error:
            print(f"{getattr(error, 'code', 'RECORD_INVALID')}: {getattr(error, 'message', error)} "
                  "(executor_runs_checks of the piece unknown)", file=sys.stderr)
            doc = None
        found[ref] = doc
    return found


def agent_runs(directory: Path) -> list:
    """The agent runs of every piece folder: ``{item, **row}``; a folder whose records do not fit is left out and said."""
    found = []
    for folder in sorted(Path(directory).glob("*/")):
        try:
            listed = agents_mod.read(folder)
        except Stop as stop:  # the report is still written; the agent runs of this piece are left out and it says why
            print(f"{stop.code}: {stop.message} (the agent runs of {folder.name} are left out of the observer report)",
                  file=sys.stderr)
            listed = []
        found += [{"item": folder.name, **row} for row in listed]
    return found


def supervisor_actions(directory: Path) -> list:
    """The ``supervisor-action`` documents of ``<run>/supervisor.jsonl`` in order; a line that is not one is skipped, and a
    run the supervisor never acted on has none."""
    try:
        text = (Path(directory) / SUPERVISOR_FILE).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    found = []
    for raw in text.splitlines():
        try:
            doc = json.loads(raw)
        except ValueError:
            continue
        if isinstance(doc, dict) and not records.problems(doc, "supervisor-action"):
            found.append(doc)
    return found


def events(project: Path):
    """``(events, problems)`` of the project's event journal for ``orch.*`` and ``planner.*``; ``(None, [text])`` when the
    journal cannot be read at all."""
    try:
        from aicore.ext import events as journal_events
        found, problems = journal_events.read_events(project, types=list(EVENT_TYPES))
    except Exception as error:  # noqa: BLE001 — the observer reports what it could not read
        return None, [f"{type(error).__name__}: {error}"]
    return found, [f"{item.get('code')}: {item.get('message')}" for item in problems[:5]]
