"""The usage ledger of a run: the receipts of each agent run and attempt, and the sums of the run, the piece and the
logical step they add to (a replayed receipt replaces its contribution, an incomplete one is said)."""
from __future__ import annotations

from typing import Optional

from orch.conductor import agents
from orch.conductor.domain.item import Item


def add_tokens(self, item: Item, usage: dict, *, usage_complete: Optional[bool] = None,
               attempt: Optional[str] = None) -> None:
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
            receipt = {**delta, "usage_complete": usage_complete}
            if step_name:  # so a resume can rebuild this step when the stage record is missing
                receipt["step"] = step_name
            previous = attempts.get(attempt or handle["id"], {})
            delta = {key: receipt[key] - previous.get(key, 0) for key in agents.USAGE_KEYS}
            attempts[attempt or handle["id"]] = receipt
            handle["usage"] = {key: sum(row[key] for row in attempts.values()) for key in agents.USAGE_KEYS}
            completeness = [row["usage_complete"] for row in attempts.values()]
            handle["usage_complete"] = (False if False in completeness else True if True in completeness else None)
        for bucket in (self.state.setdefault("tokens", {"input": 0, "output": 0}),
                       item.state.setdefault("tokens", {"input": 0, "output": 0}), step_bucket):
            for key in agents.USAGE_KEYS:
                bucket[key] = bucket.get(key, 0) + delta[key]
        if callable(remember_stage):
            remember_stage(item, step_bucket)
        self._save()
    if usage_complete is False:
        self.role_ports.unmetered(item, attempt)
