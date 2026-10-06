"""Engine Port: the binding protocol, port errors and the pure RunState reducer."""
from __future__ import annotations

from collections.abc import Iterator, Mapping
import copy
import json
from typing import Protocol, runtime_checkable

from orch import CONTRACT_VERSION
from orch import contracts

BINDINGS = ("native", "cao", "claude-only")
# Order follows the error table in docs/engine-port.md; tests compare both.
PORT_ERROR_CODES = (
    "INPUT_INVALID", "POLICY_INVALID", "ROLE_UNKNOWN", "ROUTE_UNDERSHOOT", "CAPABILITY_UNSUPPORTED",
    "RESUME_REFUSED", "RUN_UNKNOWN", "NOT_IMPLEMENTED", "SEQ_ORDER", "AFTER_TERMINAL",
)
TERMINAL = {
    "quota_block": "quota_blocked", "auth_block": "auth_blocked", "timeout": "timeout",
    "cancelled": "cancelled", "failed": "failed", "completed": "completed",
    "unknown_outcome": "unknown_outcome",
}
# Terminal statuses after which a stage may start the next attempt.
RETRYABLE = frozenset({"failed", "timeout", "quota_blocked", "auth_blocked", "unknown_outcome"})
# Terminal events that carry a cause class into stage-result errors; none of them is a task failure.
ERROR_CLASS = {"quota_block": "quota", "auth_block": "auth", "timeout": "timeout", "provider_error": "provider"}
EOF_MESSAGE = "stream ended without terminal event"


class PortError(Exception):
    def __init__(self, code: str, message: str, data: dict | None = None):
        if code not in PORT_ERROR_CODES:
            raise ValueError(f"unknown port error code: {code!r}")
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.data = data if data is not None else {}


@runtime_checkable
class EnginePort(Protocol):
    binding: str  # one of BINDINGS

    def capabilities(self) -> list[dict]: ...

    def prepare(self, input_doc: dict, policy: dict, roles: Mapping[str, dict], *,
                provider: str | None = None, dry_run: bool = True) -> dict: ...

    def run(self, launch_plan: dict) -> str: ...

    def watch(self, run_id: str) -> Iterator[dict]: ...

    def cancel(self, run_id: str) -> dict: ...

    def resume(self, run_id: str) -> str: ...

    def results(self, run_id: str) -> dict: ...


def _canonical(event: dict) -> str:
    return json.dumps(event, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


class RunState:
    """Fold run-events of one run into per-stage state; no I/O and no system clock.

    An event is checked completely before any state changes, so a rejected event
    leaves the reducer exactly as it was.
    """

    def __init__(self, run_id: str):
        self.run_id = run_id
        self._seen: dict[int, str] = {}
        self._last_seq: int | None = None
        self._stages: dict[str, dict] = {}

    def apply(self, event: dict) -> None:
        issues = [issue for issue in contracts.validate(event, "run-event") if issue.level == "error"]
        if issues:
            raise PortError("INPUT_INVALID", "run-event does not match exec/v1",
                            {"issues": [issue._asdict() for issue in issues]})
        if event["run_id"] != self.run_id:
            raise PortError("RUN_UNKNOWN", f"event belongs to run {event['run_id']!r}, not {self.run_id!r}")
        seq, encoded = event["seq"], _canonical(event)
        if seq in self._seen:
            if self._seen[seq] == encoded:
                return  # idempotent replay
            raise PortError("SEQ_ORDER", f"seq {seq} repeated with different content")
        if self._last_seq is not None and seq < self._last_seq:
            raise PortError("SEQ_ORDER", f"seq {seq} is lower than last seen {self._last_seq}")
        stage = self._next_stage(event)
        self._seen[seq] = encoded
        self._last_seq = seq
        self._stages[event["stage_id"]] = stage

    def _next_stage(self, event: dict) -> dict:
        stage_id, kind, attempt = event["stage_id"], event["kind"], event["attempt"]
        current = self._stages.get(stage_id)
        # An earlier attempt is terminal by construction: a retry starts only after it ended.
        # Check all event kinds, including a delayed started event, before retry handling.
        if current is not None and (attempt < current["attempt"] or
                                    (attempt == current["attempt"] and current["status"] != "running")):
            raise PortError("AFTER_TERMINAL", f"stage {stage_id!r} attempt {attempt} already ended")
        if kind == "started":
            if current is None:
                if attempt != 1:
                    raise PortError("INPUT_INVALID", f"stage {stage_id!r} must start with attempt 1")
            elif current["status"] == "running":
                if attempt == current["attempt"]:
                    raise PortError("INPUT_INVALID", f"stage {stage_id!r} attempt {attempt} already started")
                raise PortError("INPUT_INVALID", f"stage {stage_id!r} attempt {current['attempt']} is still running")
            elif current["status"] not in RETRYABLE:
                raise PortError("AFTER_TERMINAL", f"stage {stage_id!r} ended {current['status']}; no retry allowed")
            elif attempt != current["attempt"] + 1:
                raise PortError("INPUT_INVALID",
                                f"stage {stage_id!r} retry must be attempt {current['attempt'] + 1}, got {attempt}")
            stage = {"status": "running", "attempt": attempt, "errors": [], "route_observed": None,
                     "usage": None, "started_at": event["ts"], "finished_at": None}
        else:
            if current is None:
                raise PortError("INPUT_INVALID", f"stage {stage_id!r} received {kind!r} before started")
            if attempt > current["attempt"]:
                raise PortError("INPUT_INVALID", f"stage {stage_id!r} attempt {attempt} has not started")
            stage = dict(current, errors=list(current["errors"]))
            if kind in ERROR_CLASS:
                error = {"class": ERROR_CLASS[kind], "message": event.get("summary", kind.replace("_", " "))}
                if "raw_ref" in event:
                    error["raw_ref"] = event["raw_ref"]["path"]
                stage["errors"].append(error)
            if kind in TERMINAL:
                stage["status"] = TERMINAL[kind]
                stage["finished_at"] = event["ts"]
                if kind == "completed":
                    usage = event.get("data", {}).get("usage")
                    stage["usage"] = copy.deepcopy(usage) if isinstance(usage, dict) else None
        if "route_observed" in event:
            stage["route_observed"] = dict(event["route_observed"])
        stage["last_seq"] = event["seq"]
        stage["last_ts"] = event["ts"]
        return stage

    def close(self) -> None:
        """End of stream: a running stage never becomes success without a terminal event."""
        for stage in self._stages.values():
            if stage["status"] == "running":
                stage["status"] = "unknown_outcome"
                stage["errors"].append({"class": "transport", "message": EOF_MESSAGE})

    def stages(self) -> dict[str, dict]:
        keys = ("status", "attempt", "last_seq", "last_ts", "route_observed", "errors")
        return {stage_id: {key: copy.deepcopy(stage[key]) for key in keys}
                for stage_id, stage in self._stages.items()}

    def stage_result(self, stage_id: str, *, role: str, requested_route: dict, input_digest: str,
                     instructions_digest: str) -> dict:
        """Build the skeleton stage-result of the stage's latest attempt."""
        stage = self._stages.get(stage_id)
        if stage is None:
            raise PortError("INPUT_INVALID", f"stage {stage_id!r} has no events")
        if stage["status"] == "running":
            raise PortError("INPUT_INVALID", f"stage {stage_id!r} is still running; call close() first")
        result = {
            "$schema": contracts.URN_PREFIX + "stage-result:v1",
            "contract_version": CONTRACT_VERSION,
            "run_id": self.run_id,
            "stage_id": stage_id,
            "attempt": stage["attempt"],
            "role": role,
            "status": stage["status"],
            "route": {"requested": dict(requested_route)},
            "hashes": {"input": input_digest, "instructions": instructions_digest},
            "usage": _usage(stage["usage"]),
            "started_at": stage["started_at"],
        }
        if stage["route_observed"] is not None:
            result["route"]["observed"] = dict(stage["route_observed"], source="event")
        if stage["errors"]:
            result["errors"] = [dict(error) for error in stage["errors"]]
        if stage["finished_at"] is not None:
            result["finished_at"] = stage["finished_at"]
        issues = [issue for issue in contracts.validate(result, "stage-result") if issue.level == "error"]
        if issues:
            raise PortError("INPUT_INVALID", "stage-result does not match exec/v1",
                            {"issues": [issue._asdict() for issue in issues]})
        return result


def _usage(reported: dict | None) -> dict:
    """Unknown usage is never zero: numbers appear only when the provider reported them."""
    numbers = {}
    for key in ("input_tokens", "output_tokens"):
        value = (reported or {}).get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            numbers[key] = value
    return {"status": "reported", **numbers} if numbers else {"status": "unknown"}
