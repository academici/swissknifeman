"""The limits of a run as targets, applied to the run: whether one more round may run (``policies/allowance.py``
decides), the run-wide batch counters in the state, and the LIMIT_OVER beacon and plan note of a round past its
target."""
from __future__ import annotations

from typing import Optional

from orch.conductor.application import budget_service
from orch.conductor.domain.item import Item
from orch.conductor.policies import allowance as allowance_rules


def allowance(self, item: Item, name: str, used: int, progress: bool, emit: bool = True) -> Optional[str]:
    """``None`` when one more round of ``name`` (``review_rounds``, ``corrections``, ``check_fixes``) may run after
    ``used`` of them, else why not. The limit is a target: past it a round still runs while the last one made
    progress, up to ``ceiling_factor`` times the target; every such round prints a LIMIT_OVER beacon and leaves a
    plan note, so a long fight with a piece of work is visible, and a correction that changes nothing ends it."""
    limits = item.options["limits"]
    cap = item.input_doc.get("review_rounds_max") if name == "review_rounds" else None
    walled = allowance_rules.review_wall(name, cap, used, item.ref)
    if walled:
        return walled
    # what the last review round finds is corrected without another review (review.final_correction), marked review_debt
    why, past = allowance_rules.round_target(name, limits, used, progress)
    self._limit_over(item, past, emit)
    if why or name not in allowance_rules.BATCH_LIMITS:
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
    self.state["batch"] = allowance_rules.batch_counts(items, item.ref, item.state)
    why, past = allowance_rules.over_target(f"{name}_batch", target, allowance_rules.batch_used(items, item.ref, name, used),
                                            progress, limits["ceiling_factor"], "batch: ")
    self._limit_over(item, past, emit)
    return why


def limit_over(self, item: Item, past: Optional[str], emit: bool) -> None:
    """The LIMIT_OVER beacon and plan note of a round that goes past its target."""
    if past and emit:
        self.progress.emit("info", item=item.ref, reason_code="LIMIT_OVER", message=past)
        self._beacon_event("orch.run.warning", item, {"reason_code": "LIMIT_OVER", "step": budget_service.stage_key(self)})
        self._plan_note(item, past)
