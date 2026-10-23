"""``observe --follow``: the notable lines of a run that is still going, read incrementally (only the lines the journal
gained since the last poll), until the run ends or its conductor is gone."""
from __future__ import annotations

from pathlib import Path
import time

from orch.conductor import progress as progress_mod
from orch.conductor.infrastructure.lease import RunLease
from orch.conductor.observer import reader

LIFECYCLE = ("run.start", "run.resume", "run.end")


def notable(line: dict) -> bool:
    event = line.get("event")
    return bool(event in ("item.end", "run.end", "run.resume") or line.get("reason_code")
                or (event == "info" and "repeating" in line.get("message", ""))
                or (event == "stage.end" and str(line.get("verdict", "")).startswith("red")))


def follow(directory: Path, *, stream, poll_s: float = 2.0, idle_exit_s: float = 0.0, alive=None) -> int:
    """Follow the latest run segment: 0 at its end, 3 after two probes without a live conductor.

    ``idle_exit_s`` is retained for caller compatibility; silence never proves that a run ended.
    """
    cursor = reader.ProgressCursor(directory)
    first = lifecycle = None
    missing = 0
    alive = alive if alive is not None else lambda: RunLease.held(directory)
    while True:
        fresh = cursor.read_new()
        if cursor.restarted:  # the journal was replaced or cut: what was seen before is not its history
            first = lifecycle = None
        for line in fresh:
            first = first or line
            if notable(line):
                print("observer: " + progress_mod.text_line(line), file=stream, flush=True)
            if line.get("event") in LIFECYCLE:
                lifecycle = line["event"]
        if lifecycle == "run.end":
            return 0
        missing = missing + 1 if alive() is False else 0
        if missing >= 2:
            run_id = first.get("run", Path(directory).name) if first else Path(directory).name
            print(f"observer: run {run_id} has no live conductor (orphaned); "
                  f"resume with orch conduct resume --run {run_id}", file=stream, flush=True)
            return 3
        time.sleep(poll_s)
