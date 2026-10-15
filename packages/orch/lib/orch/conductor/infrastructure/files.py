"""The files of a conductor run: atomic JSON, the runtime folder of the runs and the run store (``run.json``,
``state.json``, the kept ``--options`` copy, the numbers of the agent runs)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import threading
from typing import Any

from aicore.state import project_state_dir
from aicore.util.io import durable_replace

from orch.conductor.domain.stop import Stop

RUN_FILE, STATE_FILE = "run.json", "state.json"
OPTIONS_COPY = "options.json"
REPORTS = Path(".swissknifeman") / "orch" / "reports"  # observer reports: run output, ignored
_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def runs_root(project: Path) -> Path:
    """The ignored runtime folder of every conductor run of a project."""
    return project_state_dir(project, "orch") / "conductor"


def safe(text: str) -> str:
    return _SAFE.sub("-", text).strip("-") or "x"


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
        self.run_id = run_id
        self.directory = runs_root(project) / run_id
        self._agents_lock = threading.Lock()

    def load(self) -> tuple:
        """``(run_doc, state)`` of an earlier run; ``RUN_UNKNOWN`` when either file is missing."""
        run_doc, state = read_json(self.directory / RUN_FILE), read_json(self.directory / STATE_FILE)
        if run_doc is None or state is None:
            raise Stop("RUN_UNKNOWN", f"no conductor run {self.run_id} in {self.directory.parent}")
        return run_doc, state

    def create(self, run_doc: dict) -> None:
        """Write ``run.json``; the folders of the runs are the owner's only (``0700``): prompts, streams and answers
        hold code, provider errors and whatever a role printed."""
        self.directory.mkdir(parents=True, exist_ok=True)
        for folder in (self.directory.parent, self.directory):
            os.chmod(folder, 0o700)
        write_json(self.directory / RUN_FILE, run_doc)

    def keep_options(self, options_file: Path) -> None:
        """Keep ``--options`` with the run: ``resume`` must not depend on a file that may be gone (a cleaned /tmp)."""
        try:
            shutil.copyfile(options_file, self.directory / OPTIONS_COPY)
        except OSError as error:
            raise Stop("OPTIONS_INVALID", f"{options_file}: cannot keep a copy with the run: {error}") from None

    def save(self, state: dict) -> None:
        write_json(self.directory / STATE_FILE, state)

    def next_agent(self, state: dict) -> int:
        """The number of a new agent run, counted in ``state.agents`` and saved at once (roles may start in threads)."""
        with self._agents_lock:
            number = state["agents"] = state.get("agents", 0) + 1
            self.save(state)
        return number
