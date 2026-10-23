"""The limits of a run as targets: a round past its target runs while the last correction made progress, up to the
ceiling; the run-wide ``<name>_batch`` limits count every piece of the run. The beacons, plan notes and the batch
counters of the run state are ``application/limits_service.py``."""
from __future__ import annotations

from typing import Optional

# The limits of the whole run (``limits.<name>_batch``) and the field of a piece's state that each one counts.
BATCH_FIELDS = {"review_rounds": "review_rounds_used", "corrections": "corrections_at", "findings": "findings_at"}
BATCH_LIMITS = tuple(BATCH_FIELDS)


def over_target(name: str, target: int, used: int, progress: bool, factor: int, scope: str = "") -> tuple:
    """``(refusal, past)`` of the target and ceiling rule for one limit (``scope`` "batch: " for a limit of the run):
    ``refusal`` says why no more round may run; ``past`` is the text of a round that goes past the target."""
    if used < target:
        return None, None
    ceiling = target * factor
    if used >= ceiling:
        return f"{scope}the ceiling of {ceiling} for {name} (target {target} × {factor}) is reached", None
    if not progress:
        return f"{scope}past the target of {target} for {name} the last correction made no progress", None
    return None, (f"{scope}{name}: round {used + 1} goes past the target of {target} (ceiling {ceiling}) because the "
                  "last correction made progress")


def piece_count(row: dict, key: str) -> int:
    value = row.get(key, 0)
    return sum(value.values()) if isinstance(value, dict) else len(value) if isinstance(value, list) else int(value)


def batch_used(items: dict, ref: str, name: str, own: int) -> int:
    """What the whole run has used of ``name`` (``review_rounds``, ``corrections``, ``findings``): the other pieces of
    ``items`` from their own state, piece ``ref`` as ``own``. Derived from piece state, so a resume does not count twice."""
    key = BATCH_FIELDS[name]
    return sum(piece_count(row, key) for other, row in items.items() if other != ref) + own


def review_wall(name: str, cap, used: int, ref: str) -> Optional[str]:
    """Why no more review round may run when the plan bounds them (``review.rounds_max`` as ``cap``): the plan's bound
    is a wall, no round goes past it on progress; ``None`` without one or below it."""
    if name == "review_rounds" and isinstance(cap, int) and used >= cap:
        return f"the plan allows at most {cap} review round(s) for {ref} (review.rounds_max)"
    return None


def round_target(name: str, limits: dict, used: int, progress: bool) -> tuple:
    """``(refusal, past)`` of one more round of ``name`` after ``used`` of them under the run ``limits``; review rounds
    are a wall too (owner, D24): a review is the safety net of finished work, not a loop, so their factor is 1."""
    factor = 1 if name == "review_rounds" else limits["ceiling_factor"]
    return over_target(name, limits[name], used, progress, factor)


def batch_counts(items: dict, ref: str, own_state: dict) -> dict:
    """``{name: used}`` of every run-wide limit, piece ``ref`` counted from ``own_state``."""
    return {key: batch_used(items, ref, key, piece_count(own_state, BATCH_FIELDS[key])) for key in BATCH_LIMITS}
