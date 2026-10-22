"""The limits of a run as targets: a round past its target runs while the last correction made progress, up to the
ceiling; the run-wide ``<name>_batch`` limits count every piece of the run."""
from __future__ import annotations

from typing import Optional

from orch.conductor.domain.item import Item
from orch.conductor.policies import budget as token_budget

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


def allowance(self, item: Item, name: str, used: int, progress: bool, emit: bool = True) -> Optional[str]:
    """``None`` when one more round of ``name`` (``review_rounds``, ``corrections``, ``check_fixes``) may run after
    ``used`` of them, else why not. The limit is a target: past it a round still runs while the last one made
    progress, up to ``ceiling_factor`` times the target; every such round prints a LIMIT_OVER beacon and leaves a
    plan note, so a long fight with a piece of work is visible, and a correction that changes nothing ends it."""
    limits = item.options["limits"]
    cap = item.input_doc.get("review_rounds_max") if name == "review_rounds" else None
    if isinstance(cap, int) and used >= cap:  # the plan's bound is a wall: no round goes past it on progress
        return f"the plan allows at most {cap} review round(s) for {item.ref} (review.rounds_max)"
    why, past = over_target(name, limits[name], used, progress, limits["ceiling_factor"])
    self._limit_over(item, past, emit)
    if why or name not in BATCH_LIMITS:
        return why
    return self._batch_allowance(item, name, used, progress, emit)


def batch_allowance(self, item: Item, name: str, used: int, progress: bool, emit: bool = True) -> Optional[str]:
    """The limit ``<name>_batch`` of the whole run, with the same target and ceiling rule; 0 has no limit.
    The refusal text starts with ``batch:``."""
    limits = item.options["limits"]
    target = limits.get(f"{name}_batch", 0)
    if not target:
        return None
    items = self.state["items"]
    self.state["batch"] = {key: batch_used(items, item.ref, key, piece_count(item.state, BATCH_FIELDS[key]))
                           for key in BATCH_LIMITS}
    why, past = over_target(f"{name}_batch", target, batch_used(items, item.ref, name, used), progress,
                            limits["ceiling_factor"], "batch: ")
    self._limit_over(item, past, emit)
    return why


def limit_over(self, item: Item, past: Optional[str], emit: bool) -> None:
    """The LIMIT_OVER beacon and plan note of a round that goes past its target."""
    if past and emit:
        self.progress.emit("info", item=item.ref, reason_code="LIMIT_OVER", message=past)
        self._beacon_event("orch.run.warning", item, {"reason_code": "LIMIT_OVER", "step": token_budget.stage_key(self)})
        self._plan_note(item, past)
