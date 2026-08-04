"""Deterministic scheduler over the frozen Artifex run and authority contracts."""
from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Callable

from . import authority, store


class SchedulerRefusal(ValueError):
    """A named scheduler refusal; callers must preserve the durable state."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(f"{reason}: {detail}" if detail else reason)
        self.reason = reason
        self.detail = detail


@dataclass(frozen=True)
class DefaultActivityPort:
    """The P2 activity port: it makes no external call and refuses before a boundary."""

    def __call__(self, _slice: dict) -> dict:
        return {"kind": "provider_unavailable", "reason": "PROVIDER_UNAVAILABLE"}


def _identity(value: dict) -> tuple[str, int, str]:
    try:
        slice_id = value["slice_id"]
        attempt = value["attempt"]
        key = value["idempotency_key"]
    except KeyError as exc:
        raise SchedulerRefusal("SLICE_INPUT_MISSING", str(exc)) from exc
    if not isinstance(slice_id, str) or not slice_id or not isinstance(attempt, int) or attempt < 1:
        raise SchedulerRefusal("SLICE_INPUT_MISSING", "slice identity")
    if not isinstance(key, str) or len(key) != 64:
        raise SchedulerRefusal("SLICE_INPUT_MISSING", "idempotency key")
    return slice_id, attempt, key


def ready_set(slices: list[dict], accepted: set[str]) -> list[dict]:
    """Return a lexical, dependency-ready selection with the frozen parallel ceiling."""
    if not isinstance(slices, list):
        raise SchedulerRefusal("SLICE_INPUT_MISSING", "slices")
    by_id = {row.get("slice_id"): row for row in slices if isinstance(row, dict)}
    if len(by_id) != len(slices) or any(not isinstance(key, str) or not key for key in by_id):
        raise SchedulerRefusal("SLICE_INPUT_MISSING", "duplicate or missing slice_id")
    ready = []
    for slice_value in sorted(slices, key=lambda row: row["slice_id"]):
        if slice_value["slice_id"] in accepted:
            continue
        dependencies = slice_value.get("dependencies", [])
        if not isinstance(dependencies, list) or any(not isinstance(dep, str) for dep in dependencies):
            raise SchedulerRefusal("SLICE_INPUT_MISSING", "dependencies")
        if any(dep not in by_id for dep in dependencies):
            raise SchedulerRefusal("DEPENDENCY_UNKNOWN")
        if all(dep in accepted for dep in dependencies):
            ready.append(slice_value)
    if not ready:
        return []
    isolated = [row for row in ready if row.get("read_only") is True or row.get("worktree_isolated") is True]
    return isolated[:2] if len(isolated) == len(ready) else ready[:1]


class Scheduler:
    """Explicit store appends around one injected activity and deterministic validation."""

    def __init__(self, run_store: store.RunStore, frozen_authority: authority.FrozenAuthority, *,
                 now: Callable[[], str], activity: Callable[[dict], dict] | None = None,
                 validate: Callable[[dict, dict], bool] | None = None) -> None:
        self.store = run_store
        self.frozen = frozen_authority
        self.now = now
        self.activity = activity or DefaultActivityPort()
        self.validate = validate or (lambda _slice, observation: observation.get("kind") == "success")

    def _payload(self, replay: dict, event: str, slice_value: dict | None, *, evidence: dict) -> dict:
        expected = self.store.rules.get(replay["state"], {}).get("on", {}).get(event)
        if expected is None:
            raise SchedulerRefusal(self.store.rules.get(replay["state"], {}).get("otherwise", "ILLEGAL_TRANSITION"))
        if event in {"freeze_run", "finish_run"}:
            slice_id = attempt = key = None
        else:
            if slice_value is None:
                raise SchedulerRefusal("SLICE_INPUT_MISSING", event)
            slice_id, attempt, key = _identity(slice_value)
        return {
            "ts": self.now(), "run_id": self.store.run_dir.name, "slice_id": slice_id, "attempt": attempt,
            "event": event, "state_before": replay["state"], "state_after": expected,
            "idempotency_key": key, "input_hashes": dict(slice_value.get("input_hashes", {})) if slice_value else {},
            "evidence": copy.deepcopy(evidence), "redaction": {"status": "clean"},
        }

    def _append(self, event: str, slice_value: dict | None, *, evidence: dict) -> dict:
        replay = self.store.replay()
        return self.store.append_event(self._payload(replay, event, slice_value, evidence=evidence))

    @staticmethod
    def _decision_input(slice_value: dict) -> dict:
        value = copy.deepcopy(slice_value.get("authority_input", {}))
        if not isinstance(value, dict):
            raise SchedulerRefusal("SLICE_INPUT_MISSING", "authority_input")
        value["intent_sequence"] = slice_value["attempt"]
        return value

    def _decision(self, slice_value: dict) -> dict:
        return authority.evaluate(self._decision_input(slice_value), self.frozen, f"schedule:{slice_value['slice_id']}:{slice_value['attempt']}")

    def _budget_decision(self, slice_value: dict) -> dict:
        value = self._decision_input(slice_value)
        value["budget_available"] = False
        return authority.evaluate(value, self.frozen, f"budget:{slice_value['slice_id']}:{slice_value['attempt']}")

    @staticmethod
    def _budget_exceeded(slice_value: dict) -> bool:
        budget = slice_value.get("budget", {})
        used = slice_value.get("used", {})
        if not isinstance(budget, dict) or not isinstance(used, dict):
            raise SchedulerRefusal("SLICE_INPUT_MISSING", "budget")
        limits = ("attempts", "tokens", "cost", "duration", "turns")
        for key in limits:
            limit = budget.get(key)
            value = used.get(key, 0)
            if not isinstance(limit, int) or limit < 1 or not isinstance(value, int) or value < 0:
                raise SchedulerRefusal("BUDGET_INVALID", key)
            if value >= limit:
                return True
        return False

    def _trip_budget(self, slice_value: dict, decision: dict) -> dict:
        return self._append("budget_exhausted", slice_value, evidence={"authority_decision": decision})

    def schedule(self, slices: list[dict], *, accepted: set[str] | None = None) -> dict:
        """Select one legal slice and record its full P2 boundary sequence."""
        accepted = set() if accepted is None else set(accepted)
        with self.store.acquire_writer():
            replay = self.store.replay()
            if replay["state"] == "BUDGET_EXHAUSTED":
                raise SchedulerRefusal("BUDGET_LIMIT")
            if replay["state"] != "READY":
                raise SchedulerRefusal("ILLEGAL_TRANSITION", str(replay["state"]))
            selected = ready_set(slices, accepted)
            if not selected:
                return {"status": "idle", "selected": []}
            slice_value = selected[0]
            _identity(slice_value)
            decision = self._decision(slice_value)
            if decision["reason_code"] == "RETRY_BUDGET_EXHAUSTED":
                record = self._trip_budget(slice_value, decision)
                return {"status": "budget_exhausted", "record": record, "decision": decision}
            if self._budget_exceeded(slice_value):
                decision = self._budget_decision(slice_value)
                if decision["reason_code"] != "BUDGET_EXHAUSTED":
                    return {"status": "owner_attention", "decision": decision}
                record = self._trip_budget(slice_value, decision)
                return {"status": "budget_exhausted", "record": record, "decision": decision}
            if not decision["allowed"]:
                return {"status": "owner_attention", "decision": decision}
            self._append("append_intent", slice_value, evidence={"authority_decision": decision})
            observation = self.activity(copy.deepcopy(slice_value))
            if not isinstance(observation, dict):
                raise SchedulerRefusal("UNKNOWN_SCHEMA_VERSION", "activity result")
            if observation.get("kind") == "provider_unavailable":
                record = self._append("provider_unavailable", slice_value, evidence={"observation": observation})
                return {"status": "provider_unavailable", "record": record, "decision": decision}
            if observation.get("kind") != "success":
                raise SchedulerRefusal("UNKNOWN_SCHEMA_VERSION", "activity kind")
            self._append("boundary_started", slice_value, evidence={"boundary": "activity"})
            self._append("append_observation", slice_value, evidence={"observation": observation})
            event = "validation_green" if self.validate(slice_value, observation) else "validation_red"
            record = self._append(event, slice_value, evidence={"validation": event})
            return {"status": "accepted" if event == "validation_green" else "rolled_back", "record": record,
                    "decision": decision}

    def reconcile(self, slice_value: dict, observed: str) -> dict:
        """Apply only the frozen reconciliation outcomes for an unresolved intent."""
        events = {"preimage": "reconcile_preimage", "postimage": "reconcile_postimage",
                  "partial": "reconcile_partial", "third": "reconcile_third_state"}
        if observed not in events:
            raise SchedulerRefusal("POSTIMAGE_THIRD_STATE")
        with self.store.acquire_writer():
            record = self._append(events[observed], slice_value, evidence={"reconcile": observed})
            if observed == "postimage":
                event = "validation_green" if self.validate(slice_value, {"kind": "success"}) else "validation_red"
                record = self._append(event, slice_value, evidence={"validation": event})
            return {"status": record["state_after"], "record": record}

    def owner_decision(self, slice_value: dict, decision: str) -> dict:
        if decision not in {"continue", "abort"}:
            raise SchedulerRefusal("OWNER_DECISION_REQUIRED")
        with self.store.acquire_writer():
            record = self._append(f"owner_decision_{decision}", slice_value, evidence={"owner": decision})
            return {"status": record["state_after"], "record": record}
