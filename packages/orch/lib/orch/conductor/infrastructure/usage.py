"""The usage ledger of a run: the receipts of each agent run and attempt, and the sums of the run, the piece and the
logical step they add to (a replayed receipt replaces its contribution, an incomplete one is said)."""
from __future__ import annotations

from typing import Any, Optional

from orch.conductor import agents
from orch.conductor.domain.item import Item


def _counter_contribution(state: dict, reported: dict, accounting: dict, previous: dict) -> tuple[dict, dict]:
    """The receipt is its durable watermark; never refund old budgets or guess a reset counter's delta."""
    accounting = dict(accounting)
    counter = accounting.get("counter_id")
    if accounting.get("unavailable"):
        return {"input": previous.get("input", 0),
                **{key: max(reported[key], previous.get(key, 0)) for key in ("cached", "output")}}, accounting
    if not counter:
        return reported, accounting
    accounting["cumulative"] = dict(reported)
    old = previous.get("accounting") or {}
    if old.get("counter_id") == counter and old.get("cumulative") == reported:
        return {key: previous.get(key, 0) for key in agents.USAGE_KEYS}, dict(old)
    snapshots = [(row.get("accounting") or {}).get("cumulative")
                 for item in (state.get("items") or {}).values()
                 for attempts in (item.get("usage_by_agent") or {}).values() for row in attempts.values()
                 if row is not previous and (row.get("accounting") or {}).get("counter_id") == counter]
    snapshots = [row for row in snapshots if isinstance(row, dict)]
    high = {key: max((int(row.get(key, 0)) for row in snapshots), default=0) for key in agents.USAGE_KEYS}
    if (accounting.get("resumed") and not snapshots and not old.get("counter_id")):
        accounting["unavailable"] = "resumed Codex session has no durable usage baseline"
    elif any(reported[key] < max(high[key], (old.get("cumulative") or {}).get(key, 0)) for key in agents.USAGE_KEYS):
        accounting["unavailable"] = "Codex cumulative counter decreased or arrived out of order"
    if accounting.get("unavailable"):
        return {key: previous.get(key, 0) for key in agents.USAGE_KEYS}, accounting
    return {key: reported[key] - high[key] for key in agents.USAGE_KEYS}, accounting


def add_tokens(self, item: Item, usage: dict, *, usage_complete: Optional[bool] = None,
               attempt: Optional[str] = None, accounting: Optional[dict] = None) -> None:
    """Count each agent's attempts once, including retries; replaying a receipt replaces its contribution."""
    handle = getattr(self._local, "agent", None)
    delta = {key: int(usage.get(key, 0)) for key in agents.USAGE_KEYS}
    ports = getattr(self, "role_ports", None)
    stage_key, stage_bucket = getattr(ports, "stage_key", None), getattr(ports, "stage_bucket", None)
    remember_stage = getattr(ports, "remember_stage", None)
    step_name = stage_key() if callable(stage_key) else None
    step_bucket = stage_bucket() if callable(stage_bucket) else self._step_tokens
    with self.store.mutating():  # a role thread and the main loop share the state (I2)
        if handle is not None:
            attempts = item.state.setdefault("usage_by_agent", {}).setdefault(handle["id"], {})
            previous = attempts.get(attempt or handle["id"], {})
            if accounting:
                delta, accounting = _counter_contribution(self.state, delta, accounting, previous)
                if accounting.get("unavailable"):
                    usage_complete = False
            receipt = {**delta, "usage_complete": usage_complete}
            if accounting:
                receipt["accounting"] = accounting
            if step_name:  # so a resume can rebuild this step when the stage record is missing
                receipt["step"] = step_name
            delta = {key: receipt[key] - previous.get(key, 0) for key in agents.USAGE_KEYS}
            attempts[attempt or handle["id"]] = receipt
            handle["usage"] = {key: sum(row[key] for row in attempts.values()) for key in agents.USAGE_KEYS}
            completeness = [row["usage_complete"] for row in attempts.values()]
            handle["usage_complete"] = (False if False in completeness else True if True in completeness else None)
        buckets: list[Any] = [self.state.setdefault("tokens", {"input": 0, "output": 0}),
                               item.state.setdefault("tokens", {"input": 0, "output": 0}), step_bucket]
        for bucket in buckets:
            for key in agents.USAGE_KEYS:
                bucket[key] = bucket.get(key, 0) + delta[key]
        if callable(remember_stage):
            remember_stage(item, step_bucket)
        self._save()
    if usage_complete is False:
        self.role_ports.unmetered(item, attempt)
