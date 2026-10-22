"""Token accounting, informational budgets and hard admission limits on accounted fresh tokens."""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Optional

from aicore.content.budget import estimate_tokens

from orch.conductor.domain.item import Item
from orch.conductor.domain.stop import Stop

HARD_LIMITS = ("tokens_hard_max", "run_tokens_hard_max")
DEFAULT_CHARGE = 50000  # limits.unmetered_charge_tokens when an item carries no options of its own
_USAGE = ("input", "cached", "output")  # the keys of one attempt; fresh spend is input + output


def _thread_local(self):
    """The conductor's thread-local (the agent handle lives there too); created only when a caller has none."""
    local = getattr(self, "_local", None)
    if local is None:
        self._local = local = threading.local()
    return local


def stage_key(self):
    """The logical step of this thread, else the single-threaded ``_current_step``."""
    local = getattr(self, "_local", None)
    found = getattr(local, "stage_key", None) if local is not None else None
    if found:
        return found
    return getattr(self, "_current_step", None)


def stage_bucket(self):
    """Fresh-token bucket of the logical step bound on this thread, else the legacy ``_step_tokens`` slot.

    Callers that never bind a stage (unit fixtures, a charge outside a step) keep writing ``_step_tokens``.
    """
    local = getattr(self, "_local", None)
    slot = getattr(local, "stage_tokens", None) if local is not None else None
    if isinstance(slot, dict):
        return slot
    bucket = getattr(self, "_step_tokens", None)
    if not isinstance(bucket, dict):
        self._step_tokens = bucket = {"input": 0, "output": 0}
    return bucket


def _read_object(path: Path) -> Optional[dict]:
    try:
        found = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return found if isinstance(found, dict) else None


def _add_usage(total: dict, usage: dict) -> None:
    for name in _USAGE:
        total[name] = int(total.get(name, 0)) + int(usage.get(name, 0) or 0)


def known_stage_usage(item: Item, key: str) -> dict:
    """Known fresh usage of logical step ``key`` already stored for ``item``.

    The piece's ``stage_usage`` record wins. Without it (a run saved before that record), receipts that name the
    step are summed, then the usage files of agents whose request names the step. Anything else starts at zero:
    the old shared counter was not kept across a process.
    """
    saved = (item.state.get("stage_usage") or {}).get(key) if isinstance(item.state, dict) else None
    if isinstance(saved, dict):
        return saved
    total = {"input": 0, "output": 0}
    labelled = False
    for attempts in (item.state.get("usage_by_agent") or {}).values():
        if not isinstance(attempts, dict):
            continue
        for receipt in attempts.values():
            if not isinstance(receipt, dict) or receipt.get("step") != key:
                continue
            labelled = True
            _add_usage(total, receipt)
    if labelled:
        return total
    directory = getattr(item, "directory", None)
    agents = Path(directory) / "agents" if directory else None
    if agents is not None and agents.is_dir():
        from_files = {"input": 0, "output": 0}
        found = False
        for request_path in agents.glob("*/request.json"):
            request = _read_object(request_path) or {}
            if request.get("step") != key:
                continue
            usage = _read_object(request_path.with_name("usage.json"))
            if not usage:
                continue
            found = True
            _add_usage(from_files, usage)
        if found:
            return from_files
    return total


def bind_stage(self, item: Item, key: str):
    """Bind this thread to the durable usage of logical step ``(item, key)``.

    Re-entering the step (a resume, a retry that comes back through ``step``) keeps that usage. A new key gets
    its own slot, starting at the known amount or zero. Returns the previous binding so a nested call can restore it.
    """
    with self.store.mutating():
        return _bind_stage_locked(self, item, key)


def _bind_stage_locked(self, item: Item, key: str):
    local = _thread_local(self)
    previous = (getattr(local, "stage_key", None), getattr(local, "stage_item", None),
                getattr(local, "stage_tokens", None))
    slots = getattr(self, "_stage_slots", None)
    if not isinstance(slots, dict):
        self._stage_slots = slots = {}
    identity = (item.ref, key)
    slot = slots.get(identity)
    if slot is None:
        slot = known_stage_usage(item, key)
        slots[identity] = slot
        saved = (item.state.get("stage_usage") or {}).get(key) if isinstance(item.state, dict) else None
        if saved is not slot and any(int(slot.get(name, 0) or 0) for name in _USAGE):
            item.state.setdefault("stage_usage", {})[key] = slot
    local.stage_key = key
    local.stage_item = item.ref
    local.stage_tokens = slot
    self._current_step = key
    return previous


def restore_stage(self, previous) -> None:
    """Put back the binding :func:`bind_stage` returned (a nested group review or strategist call)."""
    key, item_ref, slot = previous
    local = _thread_local(self)
    local.stage_key = key
    local.stage_item = item_ref
    local.stage_tokens = slot
    if key:
        self._current_step = key


def remember_stage(self, item: Item, bucket: dict) -> None:
    """Keep ``bucket`` as the piece's durable usage of the logical step bound on this thread."""
    local = getattr(self, "_local", None)
    key = getattr(local, "stage_key", None) if local is not None else None
    if not key or getattr(local, "stage_item", None) != getattr(item, "ref", None):
        return
    if getattr(local, "stage_tokens", None) is not bucket:
        return
    item.state.setdefault("stage_usage", {})[key] = bucket


def effective_limit(self, item: Item, key: str) -> int:
    """An explicit raise (including zero to remove a limit), else the frozen run cap or the piece's options. A raise of
    ``tokens_hard_max`` names the piece it was made for and holds for that piece only; an older record without ``item``
    holds for every piece, as it did when it was written."""
    for change in reversed(self.state.get("limit_raises", [])):
        if change["key"] == key and (key != "tokens_hard_max" or change.get("item") in (None, item.ref)):
            return change["to"]
    if key == "run_tokens_hard_max" and key in self.run_doc.get("limits_run", {}):
        return self.run_doc["limits_run"][key]["value"]
    return ((item.options or {}).get("limits") or {}).get(key, 0) or 0


def hard_limited(self, item: Item) -> bool:
    """Whether a hard token limit (of the piece or of the run) is in force for ``item``."""
    return any(effective_limit(self, item, key) > 0 for key in HARD_LIMITS)


def admit(self, item: Item, scope: str = "all") -> None:
    """Stop admission once accounted fresh usage reaches a hard limit; cache reads do not count.

    ``scope`` selects ``item``, ``run`` or both (``all``); ``attempt`` is what runs before every model call (a repeat, a
    repair, a fallback, a group review, the strategist): both, and the fresh tokens the logical step has already used
    against the run policy's ``budgets.stage_tokens_max``. That amount is per ``(item, step)``, kept across an interrupt
    and a resume, and separate when two steps overlap; it is not reset when the step function runs again. A single model
    call can cross the boundary: this check never interrupts one. Usage a model attempt did not report is not zero: with
    a hard limit in force the piece stops (``limits.unmetered`` ``stop``, the default) or has been charged a fixed amount
    per attempt (``charge``, see :func:`charge_unmetered`). ``stage_tokens_max`` 0 (the shipped default) does not apply.
    """
    for name, key, state, label in (
            ("item", "tokens_hard_max", item.state, item.ref),
            ("run", "run_tokens_hard_max", self.state, f"run {self.run_id}")):
        if scope not in ("all", "attempt", name):
            continue
        limit = effective_limit(self, item, key)
        tokens = state.get("tokens", {})
        used = int(tokens.get("input", 0)) + int(tokens.get("output", 0))
        if limit and used >= limit:
            raise Stop("TOKEN_BUDGET", f"{label} used {used} fresh tokens >= {key} {limit}; needs_replan: split the item "
                       f"or raise the limit (conduct resume --run {self.run_id} --raise-limit {key}=<value>)")
    if scope in ("all", "attempt") and ((item.options or {}).get("limits") or {}).get("unmetered", "stop") != "charge":
        own = bool(item.state.get("usage_incomplete")) and hard_limited(self, item)
        # unknown usage of any piece of the run escapes a run-wide limit: it is kept at run scope, not only in the piece
        unknown = sorted(self.state.get("usage_unmetered") or []) if effective_limit(self, item, "run_tokens_hard_max") > 0 else []
        if own or unknown:
            named = ", ".join(unknown) if unknown else item.ref
            raise Stop("TOKEN_BUDGET_UNMETERED", f"{named}: a model attempt reported no usage while a hard token limit is "
                       "set; resume with an --options file that sets limits.unmetered to \"charge\" (a fixed "
                       "limits.unmetered_charge_tokens per attempt without usage), or set it in [orch.conductor.limits]")
    stage_max = int(((getattr(item, "policy", None) or {}).get("budgets") or {}).get("stage_tokens_max") or 0)
    if scope == "attempt" and stage_max:
        step = stage_bucket(self)
        used = int(step.get("input", 0)) + int(step.get("output", 0))
        if used >= stage_max:
            raise Stop("TOKEN_BUDGET", f"{item.ref} step {stage_key(self) or '-'} used {used} fresh tokens >= "
                       f"budgets.stage_tokens_max {stage_max} of the run policy; needs_replan: split the item or "
                       "raise stage_tokens_max in the policy")

# Budget classes of the blocks (knowledge/p9-prompt#budgets). Only the measure and a beacon: nothing is cut. The kinds the
# design does not list belong to the frame or the task material of their role (progress, candidate, review_scope, diff,
# findings, instruction), so they count as core; ``retrieval`` is what the sources answered (``research``).
BUDGET_CLASSES = {
    "core": ("role_text", "input", "verification", "result_contract", "answers", "correction", "progress", "candidate",
             "review_scope", "diff", "findings", "instruction"),
    "supporting": ("repository_rules", "skill", "skill_names", "context_map", "expected_paths", "focus", "run_rules",
                   "stub"),
    "retrieval": ("research",),
}
BUDGET_LIMITS = {"core": "prompt_core_tokens", "supporting": "prompt_supporting_tokens",
                 "retrieval": "prompt_retrieval_tokens"}  # the ``limits`` keys of the run options


def budget_class(kind: str) -> str:
    """``core``, ``supporting`` or ``retrieval``: the budget class of a block kind (a kind nobody listed is supporting)."""
    return next((name for name, kinds in BUDGET_CLASSES.items() if kind in kinds), "supporting")


def budgets(blocks, limits: dict) -> dict:
    """``{class: {tokens, limit}}``: the estimated tokens of the blocks of each class against ``limits[class]``."""
    tokens = {name: 0 for name in BUDGET_CLASSES}
    for block in blocks:
        tokens[budget_class(block.kind)] += estimate_tokens(block.text)
    return {name: {"tokens": tokens[name], "limit": int(limits.get(name) or 0)} for name in BUDGET_CLASSES}


def over_budget(blocks, limits: dict) -> list:
    """``[(class, block, class_tokens, limit)]`` for each class above its limit (0 is no limit), with the heaviest block of
    the class, the first of equals. A report only: the blocks are not touched."""
    found = []
    for name, row in budgets(blocks, limits).items():
        if row["limit"] and row["tokens"] > row["limit"]:
            members = [block for block in blocks if budget_class(block.kind) == name]
            found.append((name, max(members, key=lambda block: estimate_tokens(block.text)), row["tokens"], row["limit"]))
    return found


def unmetered(self, item: Item, attempt: Optional[str] = None) -> None:
    """Remember an unmetered model attempt (``attempt`` names its receipt) and announce it once, even when that attempt
    stops the run; under ``limits.unmetered`` ``charge`` the attempt is charged a fixed amount."""
    with self.store.mutating():  # a role thread gets here while the main loop saves the state (I2)
        first = not item.state.get("usage_incomplete")
        known = item.ref in (self.state.get("usage_unmetered") or [])
        uncharged = not charge_amount(self, item) and not known  # the run keeps what no charge accounts for
        if first:
            item.state["usage_incomplete"] = True
        if uncharged:
            self.state.setdefault("usage_unmetered", []).append(item.ref)
        if first or uncharged:
            self._save()
    charge_unmetered(self, item, attempt)
    if first:  # announced after the lock
        self.progress.emit("info", item=item.ref, reason_code="BUDGET_UNMETERED",
                           message=f"{item.ref}: a model attempt reported no usage; token limits cannot see it")


def charge_amount(self, item: Item) -> int:
    """What an attempt without usage is charged (``limits.unmetered`` ``charge`` with a hard token limit in force), else 0."""
    limits = (item.options or {}).get("limits") or {}
    amount = int(limits.get("unmetered_charge_tokens", DEFAULT_CHARGE) or 0)
    if limits.get("unmetered", "stop") != "charge" or amount <= 0 or not hard_limited(self, item):
        return 0
    return amount


def charge_unmetered(self, item: Item, attempt: Optional[str] = None) -> None:
    """``limits.unmetered`` ``charge``: an attempt that reported no usage costs ``limits.unmetered_charge_tokens`` fresh
    input tokens, counted in the piece, the run and the step and kept apart in ``tokens.charged``. Once per attempt: a
    replayed receipt (``attempt``) is not charged again. Without a hard token limit nothing is charged."""
    amount = charge_amount(self, item)
    if not amount:
        return
    with self.store.mutating():
        charged = item.state.setdefault("usage_charged", [])
        if attempt is not None and attempt in charged:
            return
        if attempt is not None:
            charged.append(attempt)
        step = stage_bucket(self)
        for bucket in (self.state.setdefault("tokens", {"input": 0, "output": 0}),
                       item.state.setdefault("tokens", {"input": 0, "output": 0}), step):
            if bucket is not None:
                bucket["input"] = bucket.get("input", 0) + amount
                if bucket is not step:
                    bucket["charged"] = bucket.get("charged", 0) + amount
        remember_stage(self, item, step)
        self._save()


def budget(self, item: Item) -> None:
    """``tokens_max`` is a beacon: past it a BUDGET_OVER line is printed once per piece, nothing is stopped."""
    limit = item.options["limits"].get("tokens_max") or 0
    tokens = item.state.get("tokens", {})
    used = int(tokens.get("input", 0)) + int(tokens.get("output", 0))  # cache reads are not spend
    with self.store.mutating():
        first = bool(limit and used > limit and not item.state.get("budget_over"))
        if first:
            item.state["budget_over"] = used
            self._save()
    if first:
        self.progress.emit("info", item=item.ref, reason_code="BUDGET_OVER",
                           message=f"{item.ref} used {used} fresh tokens, past tokens_max {limit}; the run goes on")
