"""Pure health diagnosis. Observation and liveness never authorize destructive recovery."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from skm.kernel.json_types import JsonObject, JsonValue

if TYPE_CHECKING:
    from .assignment import WorkerOffer
    from .stage_record import StageRecord


class HealthClass(StrEnum):
    RUNNING = "running"
    WAITING_PROVIDER = "waiting_provider"
    WAITING_TOOL = "waiting_tool"
    WAITING_OWNER = "waiting_owner"
    WAITING_BUDGET_RESET = "waiting_budget_reset"
    SUSPECTED_STALL = "suspected_stall"
    HUNG = "hung"
    RECOVERING = "recovering"
    ORPHANED = "orphaned"
    STOPPED = "stopped"
    FINISHED = "finished"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class RunHealth:
    health: HealthClass
    reason_code: str | None
    detail: str
    since: datetime | None
    silent_seconds: float | None
    signal_coverage: tuple[str, ...]
    last_observed_at: datetime | None
    input_watermark: str | int | None
    observation_state: str


def _time(value: object) -> datetime | None:
    """An aware instant, else ``None``: a timestamp without an offset names no instant and cannot be
    compared with ``now``, so it counts as a missing observation."""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    if isinstance(value, datetime) and value.utcoffset() is not None:
        return value
    return None


def _object(value: JsonValue) -> JsonObject:
    """A nested fact object; anything else is an absent one, so a malformed fact proves nothing."""
    return value if isinstance(value, dict) else {}


def _integer(value: JsonValue) -> int:
    if not value:
        return 0
    if isinstance(value, int | float | str):
        return int(value)
    raise TypeError(f"expected a number, got {type(value).__name__}")


def _threshold(thresholds: Mapping[str, JsonValue], key: str, default: float) -> float:
    value = thresholds.get(key, default)
    if isinstance(value, int | float | str):
        return float(value)
    raise TypeError(f"health threshold {key} is not a number")


def classify_run_health(facts: JsonObject, now: datetime) -> RunHealth:  # noqa: PLR0912
    """First matching execution §5.14 rule, with explicit missing/stale coverage.

    Facts are control-plane observations, not worker wall-clock authority. The
    caller supplies freshness and distinct active units from its consistent snapshot.
    """
    status = facts.get("status", "running")
    thresholds = _object(facts.get("thresholds"))
    hung = _threshold(thresholds, "hung_after_seconds", 300)
    idle = _threshold(thresholds, "idle_seconds", 5400)
    grace = _threshold(thresholds, "wait_grace_seconds", 60)
    repeats = int(_threshold(thresholds, "stall_repeat_n", 5))
    observed = _time(facts.get("last_observed_at"))
    progress = _time(facts.get("last_progress_at"))
    heartbeat = _time(facts.get("last_heartbeat_at"))
    since = _time(facts.get("since"))
    silent = None if progress is None else max(0.0, (now - progress).total_seconds())
    stale = facts.get("input_stale") is True
    coverage = tuple(
        key
        for key in ("heartbeat", "cpu", "runtime", "progress")
        if facts.get(f"{key}_available") is True and not stale
    )
    observation = (
        "unknown"
        if stale
        else (
            "progress_observed"
            if facts.get("progress_observed") is True
            else "alive_but_no_progress"
            if facts.get("process_alive") is True
            else "telemetry_unavailable"
            if not coverage
            else "unknown"
        )
    )
    health, reason = HealthClass.RUNNING, None
    active = _integer(facts.get("active_units"))
    reset = _time(facts.get("budget_reset_at"))
    deadline = _time(facts.get("deadline_at"))
    not_before = _time(facts.get("not_before"))
    if status in {"succeeded", "cancelled"}:
        health = HealthClass.FINISHED
    elif status == "paused" and facts.get("stop_code") == "QUOTA_EXHAUSTED" and reset and reset > now:
        health, reason = HealthClass.WAITING_BUDGET_RESET, "QUOTA_EXHAUSTED"
    elif facts.get("open_blocking_request") and not active:
        health, reason = HealthClass.WAITING_OWNER, "WAITING_DECISION"
    elif status in {"paused", "failed"}:
        health, reason = HealthClass.STOPPED, str(facts.get("stop_code") or "RUN_STOPPED")
    elif facts.get("recovery_open"):
        health, reason = HealthClass.RECOVERING, "RECOVERY_IN_PROGRESS"
    elif facts.get("unfinished_stage") and facts.get("lease_expired"):
        health, reason = HealthClass.ORPHANED, "RUN_ORPHANED"
    elif not active and status == "running" and not facts.get("ready_tasks"):
        health, reason = HealthClass.UNKNOWN, "STATUS_UNKNOWN"
    elif not_before and now < not_before and (deadline is None or not_before <= deadline):
        health, reason = HealthClass.WAITING_PROVIDER, "PROVIDER_WAIT"
    elif facts.get("waiting_tool") and deadline:
        overrun = (now - deadline).total_seconds()
        if overrun > hung:
            health, reason = HealthClass.HUNG, "TOOL_DEADLINE_EXCEEDED"
        elif overrun > grace:
            health, reason = HealthClass.SUSPECTED_STALL, "TOOL_DEADLINE_EXCEEDED"
        else:
            health = HealthClass.WAITING_TOOL
    elif heartbeat and (now - heartbeat).total_seconds() > hung and not stale:
        health, reason = HealthClass.HUNG, "HEARTBEAT_STALE"
    elif (
        not stale
        and idle > 0
        and silent is not None
        and silent > idle
        and (
            facts.get("cpu_active") is False
            or (repeats > 0 and _integer(facts.get("repeated_command_count")) >= repeats)
        )
    ):
        health, reason = HealthClass.SUSPECTED_STALL, "STALL_SUSPECTED"
    if health in {
        HealthClass.WAITING_PROVIDER,
        HealthClass.WAITING_TOOL,
        HealthClass.WAITING_OWNER,
        HealthClass.WAITING_BUDGET_RESET,
    }:
        observation = "waiting_known"
    elif health is HealthClass.SUSPECTED_STALL:
        observation = "suspected_stall"
    watermark = facts.get("input_watermark")
    return RunHealth(
        health,
        reason,
        reason or health.value,
        since,
        silent,
        coverage,
        observed,
        watermark if isinstance(watermark, (str, int)) else None,
        observation,
    )


def active_stage_seconds(
    intervals: tuple[tuple[datetime, datetime | None], ...],
    transitions: tuple[tuple[str, datetime], ...],
    now: datetime,
) -> float:
    """Server stage-seconds minus server pause intervals; parallel stages add up."""
    pauses: list[tuple[datetime, datetime]] = []
    paused: datetime | None = None
    for name, at in transitions:
        if name == "run-paused" and paused is None:
            paused = at
        elif name in {"run-resumed", "run-started", "run-finished", "run-cancelled"} and paused:
            pauses.append((paused, at))
            paused = None
    if paused is not None:
        pauses.append((paused, now))
    total = 0.0
    for start, finish in intervals:
        end = finish or now
        elapsed = max(0.0, (end - start).total_seconds())
        for pause_start, pause_end in pauses:
            elapsed -= max(0.0, (min(end, pause_end) - max(start, pause_start)).total_seconds())
        total += max(0.0, elapsed)
    return total


def reap_proven(stage: StageRecord | None, worker: WorkerOffer) -> bool:
    """Authenticate every reported unit and its saved identity before accepting reap."""
    from .stage_record import os_stop_proven

    if stage is None:
        return False
    confirmed: set[tuple[str, str]] = set()
    markers: list[bool] = []  # every accepted proof must confirm the host markers, not only the last one
    saved = {identity.unit_key: identity for identity in stage.process_identities}
    for proof in worker.reaped_steps:
        if proof.get("stage_record_id") != str(stage.id) or proof.get("dead") is not True:
            continue
        raw = _object(proof.get("identity"))
        ownership = _object(raw.get("ownership"))
        owner = _object(ownership.get("owner"))
        kind, unit_id = proof.get("unit_kind"), proof.get("unit_id")
        if (
            not isinstance(kind, str)
            or kind not in {"step", "check", "git_effect"}
            or not isinstance(unit_id, str)
        ):
            continue
        unit = (kind, unit_id)
        expected = {
            "host_id": worker.host_id,
            "attempt_id": stage.attempt_id,
            "stage_record_id": stage.id,
            "unit_kind": kind,
            "unit_id": unit_id,
        }
        if any(str(owner.get(key)) != str(value) for key, value in expected.items()):
            continue
        known = saved.get(unit)
        if known is not None and (
            known.ownership != ownership
            or known.pid != raw.get("pid")
            or known.pgid != raw.get("pgid")
            or known.start_ticks != raw.get("start_ticks")
            or known.boot_id != raw.get("boot_id")
            or known.started_at != _time(raw.get("started_at"))
        ):
            continue
        confirmed.add(unit)
        markers.append(proof.get("host_markers_confirmed", True) is True)
    host_markers = bool(markers) and all(markers)
    return os_stop_proven(stage, confirmed_units=frozenset(confirmed), host_markers_confirmed=host_markers)
