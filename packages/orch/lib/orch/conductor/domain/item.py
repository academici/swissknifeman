"""The piece of work the conductor runs now."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


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
    policy: dict = field(default_factory=dict)
    options: dict = field(default_factory=dict)
    sources: dict = field(default_factory=dict)
    routes: dict = field(default_factory=dict)
    launch_plan: dict = field(default_factory=dict)
    route_notes: list = field(default_factory=list)  # routes moved at selection: gated or unavailable provider
