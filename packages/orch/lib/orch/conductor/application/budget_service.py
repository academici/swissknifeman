"""Token accounting of the run: the durable fresh-token slot of each logical step, the limit in force, the admission of
a model call, unmetered attempts and the informational ``tokens_max`` beacon. The rules are ``policies/budget.py``;
this module keeps the state they read and says what they decide."""
from __future__ import annotations

import threading
from typing import Optional

from orch.conductor.domain.item import Item
from orch.conductor.policies import budget as budget_rules
from orch.conductor.policies.budget import DEFAULT_CHARGE, HARD_LIMITS, _USAGE


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
        slot = budget_rules.known_stage_usage(item, key)
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
    """The limit ``key`` in force for ``item`` (:func:`policies.budget.effective_limit`): the raises of the run state,
    the frozen ``limits_run`` of the run and the piece's options."""
    return budget_rules.effective_limit(
        key, limit_raises=self.state.get("limit_raises", []),
        limits_run=self.run_doc.get("limits_run", {}) if key == "run_tokens_hard_max" else None,
        item_options=item.options, item_ref=item.ref)


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
    keys = HARD_LIMITS if scope in ("all", "attempt") else {"item": HARD_LIMITS[:1], "run": HARD_LIMITS[1:]}.get(scope, ())
    stage_max = int(((getattr(item, "policy", None) or {}).get("budgets") or {}).get("stage_tokens_max") or 0)
    stage_used, step_key = 0, None
    if scope == "attempt" and stage_max:
        step = stage_bucket(self)
        stage_used = int(step.get("input", 0)) + int(step.get("output", 0))
        step_key = stage_key(self)
    stop = budget_rules.admission(
        scope=scope, item_ref=item.ref, run_id=self.run_id, item_tokens=item.state.get("tokens", {}),
        run_tokens=self.state.get("tokens", {}), limits={key: effective_limit(self, item, key) for key in keys},
        item_limits=(item.options or {}).get("limits") or {}, usage_incomplete=bool(item.state.get("usage_incomplete")),
        usage_unmetered=self.state.get("usage_unmetered") or [], stage_max=stage_max, stage_used=stage_used,
        stage_key=step_key)
    if stop is not None:
        raise stop


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
