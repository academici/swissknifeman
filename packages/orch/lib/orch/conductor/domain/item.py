"""The piece of work the conductor runs now."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def done_steps(steps: dict) -> dict:
    """Completed results only; an unfinished step is absent to result readers."""
    return {key: step for key, step in steps.items() if step.get("status") == "done"}


def piece_commits(piece: dict) -> list:
    """Every commit of a piece in order: the stage commits of a split run (``commits`` of its state: the implementation
    and the fix commits), then its final commit; one sha for a piece of ``final-only``."""
    shas = [row["sha"] for row in piece.get("commits") or [] if row.get("sha")]
    final = ((done_steps(piece.get("steps") or {}).get("commit") or {}).get("result") or {}).get("sha")
    if final and final not in shas:
        shas.append(final)
    return shas


@dataclass
class Item:
    """What the conductor knows about the piece of work it runs now."""

    ref: str
    orch_run: str
    state: dict
    directory: Path
    claim: dict
    input_doc: dict = field(default_factory=dict)
    artifacts: Optional[Path] = None
    output_write_dirs: list = field(default_factory=list)
    policy: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)
    routes: dict = field(default_factory=dict)
    launch_plan: dict = field(default_factory=dict)
    route_notes: list = field(default_factory=list)  # routes moved at selection: gated or unavailable provider
    escalation: dict = field(default_factory=dict)  # {code, text} of a blocked report, for the item.end line
