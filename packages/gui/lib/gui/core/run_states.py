"""States of a command run (``run/v1`` ``state``) and the allowed transitions: the one source in code.

A transition is stored before its event is published. Every state that is not terminal may become ``lost``: after a
crash the backend marks unfinished runs ``lost`` and never adopts a PID (invariant I11).
"""
from __future__ import annotations

from typing import Dict, FrozenSet

STATES = ("queued", "authorizing", "denied", "starting", "failed_to_start", "running", "cancelling", "succeeded",
          "failed", "cancelled", "timed_out", "lost")

TRANSITIONS: Dict[str, FrozenSet[str]] = {
    "queued": frozenset({"authorizing", "cancelled", "lost"}),
    "authorizing": frozenset({"denied", "starting", "lost"}),
    "starting": frozenset({"failed_to_start", "running", "lost"}),
    "running": frozenset({"succeeded", "failed", "cancelling", "timed_out", "lost"}),
    "cancelling": frozenset({"cancelled", "lost"}),
    "denied": frozenset(),
    "failed_to_start": frozenset(),
    "succeeded": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
    "timed_out": frozenset(),
    "lost": frozenset(),
}

TERMINAL: FrozenSet[str] = frozenset(state for state, targets in TRANSITIONS.items() if not targets)

# States with a process the backend may hold; on start the backend checks them (pid and create time) and marks
# the others lost.
WITH_PROCESS: FrozenSet[str] = frozenset({"starting", "running", "cancelling"})


def can_transition(source: str, target: str) -> bool:
    return target in TRANSITIONS.get(source, frozenset())


def is_terminal(state: str) -> bool:
    return state in TERMINAL
