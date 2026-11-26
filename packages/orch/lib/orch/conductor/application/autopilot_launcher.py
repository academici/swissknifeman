"""Launch and identify child conductors for the autopilot."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import sys
from typing import Optional

from orch.conductor import process, records
from orch.conductor.application.autopilot_status import DETACHED, OPTIONS_DOC, STATE_DOC, child_problem
from orch.conductor.domain.stop import Stop
from orch.conductor.infrastructure import detach
from orch.conductor.infrastructure.files import runs_root

ORCH_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "orch.py"


class ProcessLauncher:
    """Launch children and signal them only while their identity still matches."""

    def __init__(self, project: Path, plan: str, config_file: Optional[Path] = None):
        self.project, self.plan, self.config_file = Path(project), plan, config_file
        self.root = runs_root(self.project)

    def ack_path(self, current: dict) -> Path:
        return self.root / DETACHED / f"{current['run_id']}.{current['launch_id']}.ack.json"

    def argv(self, current: dict) -> list:
        argv = [sys.executable, str(ORCH_SCRIPT), *(["--config", str(self.config_file)] if self.config_file else []),
                "--project", str(self.project), "conduct", current["kind"]]
        if current["kind"] == "run":
            return argv + ["--plan", self.plan, "--items", *current["items"], "--options", str(self.root / OPTIONS_DOC),
                           "--json-lines", "--run-id", current["run_id"]]
        retry = current.get("retry") if current["kind"] == "resume" else None  # of a continue: its saved pieces only
        return argv + ["--run", current["run_id"], *(["--retry", *retry] if retry else []), "--json-lines"]

    def start(self, current: dict) -> dict:
        env = {detach.STATE_ENV: str(self.root / STATE_DOC), detach.LAUNCH_ENV: current["launch_id"]}
        return detach.spawn(self.argv(current), project=self.project, launcher="autopilot", log_dir=self.root / DETACHED,
                            env=env, ack_nonce=current["launch_id"])

    def acknowledged(self, current: dict, child: dict) -> dict:
        return detach.wait_ack(self.ack_path(current), current["launch_id"], current["run_id"], child)

    def ack_of(self, current: dict) -> Optional[dict]:
        try:
            found = records.read(self.ack_path(current), "detach-ack")
        except Stop:
            return None
        mine = (current["launch_id"], current["run_id"], "started")
        return found if found and (found["nonce"], found["run_id"], found["status"]) == mine else None

    def alive(self, child: dict) -> bool:
        detach.poll_children()
        return child.get("start_ticks") is not None and process.start_ticks(child["pid"]) == child["start_ticks"]

    def interrupt(self, directory: Path, current: dict) -> Optional[str]:
        """Signal the child PID only while its whole identity matches."""
        problem = child_problem(directory, current)
        if problem:
            return problem
        try:
            os.kill(current["pid"], signal.SIGINT)
        except ProcessLookupError:
            return f"pid {current['pid']} is gone"
        return None
