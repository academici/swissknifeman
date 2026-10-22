"""The files of a conductor run: atomic JSON, the runtime folder of the runs and the run store (``run.json``,
``state.json``, the kept ``--options`` copy, the numbers of the agent runs)."""
from __future__ import annotations

import json
from contextlib import contextmanager, ExitStack
import os
from pathlib import Path
import re
import shutil
import threading
from typing import Any

from aicore.state import project_state_dir
from aicore.util.io import durable_replace

from orch.conductor import records
from orch.conductor.domain.stop import Stop

RUN_FILE, STATE_FILE = "run.json", "state.json"
OPTIONS_COPY = "options.json"
REPORTS = Path(".swissknifeman") / "orch" / "reports"  # observer reports: run output, ignored
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")
_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*$")


def runs_root(project: Path) -> Path:
    """The ignored runtime folder of every conductor run of a project."""
    return project_state_dir(project, "orch") / "conductor"


def safe(text: str) -> str:
    """``text`` as one folder name: runs of other characters become ``-``; a name of dots only (``..``) is never a
    folder of its own, so a reference cannot lead out of the run folder."""
    name = _SAFE.sub("-", text).strip("-")
    return name if name.strip(".") else "x"


def write_json(path: Path, doc: Any) -> Path:
    """Replace ``path`` crash-safely: a unique temporary file (two threads of one run may write the same file), fsync of
    the file and of its folder, then the rename; a crash leaves the old file or the new one, never a torn one."""
    durable_replace(path, (json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))
    return path


def read_json(path: Path) -> Any:
    """The document at ``path``, None when there is none; ``STATE_CORRUPT`` (with the path) when it is not JSON."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (UnicodeDecodeError, ValueError) as error:
        raise Stop("STATE_CORRUPT", f"{path} is not JSON ({error}): restore it from the run's progress.jsonl or "
                   "remove the run folder and start again") from None


class RunStore:
    """The folder of one conductor run (``runs_root(project)/<run_id>``): what was asked (``run.json``), what happened
    (``state.json``) and the copy of ``--options``; it numbers the agent runs of the run, one at a time."""

    def __init__(self, project: Path, run_id: str):
        if not _RUN_ID.match(run_id or ""):  # ``--run ../x`` must not reach a folder outside the runs
            raise Stop("RUN_UNKNOWN", f"{run_id!r} is not a run id (cnd-<UTC stamp>-<hex>)")
        self.run_id = run_id
        self.project = Path(project)
        self.directory = runs_root(project) / run_id
        # Invariant I2: every mutation of the run state and every save of ``state.json`` happens under this one lock
        # (threads of checks, of roles and the main loop share the state). Re-entrant: a mutation that saves nests.
        # Order of locks: the questions lock first, this one second, never the other way round.
        self.lock = threading.RLock()

    @contextmanager
    def ownership(self, command: str, *, checkout: bool = False, create: bool = False):
        """Acquire checkout then run, before any run/state read; release both on every exit."""
        from orch.conductor.infrastructure.lease import CheckoutLock, RunLease, checkout_toplevel

        with ExitStack() as stack:
            if checkout:
                stack.enter_context(CheckoutLock(self.directory.parent, checkout_toplevel(self.project)).acquire(
                    command, self.run_id))
            if create:
                self.directory.mkdir(parents=True, mode=0o700)
            elif not self.directory.is_dir():
                raise Stop("RUN_UNKNOWN", f"no conductor run {self.run_id} in {self.directory.parent}")
            try:
                stack.enter_context(RunLease(self.directory).acquire(command))
            except FileNotFoundError:
                raise Stop("RUN_UNKNOWN", f"no conductor run {self.run_id} in {self.directory.parent}") from None
            yield

    def load(self) -> tuple:
        """``(run_doc, state)`` of an earlier run, both checked against records/v1 (a run written before it is migrated
        in memory, its files stay as they are); ``RUN_UNKNOWN`` when either file is missing, ``RUN_INVALID`` /
        ``STATE_INVALID`` when one does not match its schema."""
        with self.lock:
            run_doc = records.read(self.directory / RUN_FILE, "run")
            state = records.read(self.directory / STATE_FILE, "state")
        if run_doc is None or state is None:
            raise Stop("RUN_UNKNOWN", f"no conductor run {self.run_id} in {self.directory.parent}")
        return run_doc, state

    def create(self, run_doc: dict) -> None:
        """Write ``run.json``; the folders of the runs are the owner's only (``0700``): prompts, streams and answers
        hold code, provider errors and whatever a role printed."""
        self.directory.mkdir(parents=True, exist_ok=True)
        for folder in (self.directory.parent, self.directory):
            os.chmod(folder, 0o700)
        self.save_run(run_doc)

    def save_run(self, run_doc: dict) -> None:
        """Replace ``run.json`` (a ``--ready`` batch names its lane after the first claim)."""
        with self.lock:
            records.write(self.directory / RUN_FILE, run_doc, "run")

    def keep_options(self, options_file: Path) -> None:
        """Keep ``--options`` with the run: ``resume`` must not depend on a file that may be gone (a cleaned /tmp)."""
        try:
            shutil.copyfile(options_file, self.directory / OPTIONS_COPY)
        except OSError as error:
            raise Stop("OPTIONS_INVALID", f"{options_file}: cannot keep a copy with the run: {error}") from None

    def mutating(self):
        """The context of a state mutation (the run-store lock): ``with store.mutating(): state[...] = ...``. Progress
        lines, bus events and beacons are emitted after leaving it."""
        return self.lock

    def save(self, state: dict) -> None:
        """Check ``state`` against records/v1 and replace ``state.json``; ``STATE_INVALID`` leaves the file as it was."""
        with self.lock:  # validation and json.dumps walk the state: a thread that changes it meanwhile must wait
            records.write(self.directory / STATE_FILE, state, "state")

    def next_agent(self, state: dict) -> int:
        """The number of a new agent run, counted in ``state.agents`` and saved at once (roles may start in threads)."""
        with self.lock:
            number = state["agents"] = state.get("agents", 0) + 1
            self.save(state)
        return number
