"""Settings sections of the execution module: typed views and section validators (settings spec §B.8.3)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from skm.kernel.json_types import JsonValue
from skm.platform.config.registry import SectionValidatorFn

from .generated.settings import BudgetsSettings, ChecksSettings, ExecutionSettings, WorkerSettings

__all__ = [
    "SECTION_URNS",
    "VALIDATORS",
    "VIEWS",
    "BudgetsSettings",
    "ChecksSettings",
    "ExecutionSettings",
    "WorkerSettings",
]

SECTION_URNS = (
    "urn:skm:settings:execution:v1",
    "urn:skm:settings:budgets:v1",
    "urn:skm:settings:worker:v1",
    "urn:skm:settings:checks:v1",
)

WORK_ROLES: Final = ("scout", "executor", "reviewer", "triager", "advisor", "researcher", "registrar")
INTENSITIES: Final = ("light", "medium", "heavy")


def _timeouts_consistent(values: Mapping[str, JsonValue]) -> str | None:
    """step_wall_seconds == 0 or idle_seconds == 0 or idle_seconds <= step_wall_seconds."""
    idle = values["execution.stall.idle_seconds"]
    step = values["execution.timeouts.step_wall_seconds"]
    if idle is None or step is None:
        return None
    if cast("int", step) != 0 and cast("int", idle) != 0 and cast("int", idle) > cast("int", step):
        return "execution.stall.idle_seconds must not exceed execution.timeouts.step_wall_seconds"
    return None


def _lease_renewal(values: Mapping[str, JsonValue]) -> str | None:
    """renew_every_seconds * 2 < ttl_seconds."""
    ttl = values["execution.lease.ttl_seconds"]
    renew = values["execution.lease.renew_every_seconds"]
    if ttl is None or renew is None:
        return None
    if cast("int", renew) * 2 >= cast("int", ttl):
        return "execution.lease.renew_every_seconds must be less than half of execution.lease.ttl_seconds"
    return None


def _ordered_positive(thresholds: JsonValue) -> bool:
    """Three positive thresholds with light <= medium <= heavy."""
    if not isinstance(thresholds, Mapping):
        return False
    steps = cast("Mapping[str, JsonValue]", thresholds)
    if set(steps) != set(INTENSITIES):
        return False
    numbers = [steps[name] for name in INTENSITIES]
    if not all(isinstance(item, int) and not isinstance(item, bool) and item > 0 for item in numbers):
        return False
    ordered = cast("Sequence[int]", numbers)
    return ordered[0] <= ordered[1] <= ordered[2]


def _work_policy_bounds(values: Mapping[str, JsonValue]) -> str | None:
    """Every effective role, and the reproduction map, has positive thresholds light <= medium <= heavy."""
    by_role = values["execution.work_policy.role_warn_seconds"]
    repro = values["execution.work_policy.repro_warn_seconds"]
    if by_role is not None:
        if not isinstance(by_role, Mapping):
            return "execution.work_policy.role_warn_seconds must be a map of roles"
        roles = cast("Mapping[str, JsonValue]", by_role)
        unknown = sorted(set(roles) - set(WORK_ROLES))
        if unknown:
            return f"execution.work_policy.role_warn_seconds has unknown roles {unknown}"
        for role in WORK_ROLES:
            if role not in roles:
                return f"execution.work_policy.role_warn_seconds has no thresholds for role {role!r}"
            if not _ordered_positive(roles[role]):
                return (
                    f"execution.work_policy.role_warn_seconds[{role!r}] needs positive "
                    "light <= medium <= heavy thresholds"
                )
    if repro is not None and not _ordered_positive(repro):
        return "execution.work_policy.repro_warn_seconds needs positive light <= medium <= heavy thresholds"
    return None


def _health_order(values: Mapping[str, JsonValue]) -> str | None:
    """wait_grace <= hung_after, and idle_seconds == 0 or hung_after <= idle_seconds."""
    grace = values["execution.health.wait_grace_seconds"]
    hung = values["execution.health.hung_after_seconds"]
    idle = values["execution.stall.idle_seconds"]
    if grace is None or hung is None or idle is None:
        return None
    if cast("int", grace) > cast("int", hung):
        return "execution.health.wait_grace_seconds must not exceed hung_after_seconds"
    if cast("int", idle) != 0 and cast("int", hung) > cast("int", idle):
        return "execution.health.hung_after_seconds must not exceed execution.stall.idle_seconds"
    return None


def _handoff_bounds(values: Mapping[str, JsonValue]) -> str | None:
    """max_finding_chars <= max_total_bytes."""
    finding = values["execution.handoff.max_finding_chars"]
    total = values["execution.handoff.max_total_bytes"]
    if finding is None or total is None:
        return None
    if cast("int", finding) > cast("int", total):
        return "execution.handoff.max_finding_chars must not exceed execution.handoff.max_total_bytes"
    return None


def _integration_mode_consistent(values: Mapping[str, JsonValue]) -> str | None:
    """Multi-commit modes require rebase or merge."""
    mode = values["execution.integration.commit_mode"]
    strategy = values["execution.integration.strategy"]
    if mode in ("implementation_and_fixes", "per_stage_attributed") and strategy not in ("rebase", "merge"):
        return f"execution.integration.commit_mode {mode} needs strategy rebase or merge"
    return None


def _task_le_run(values: Mapping[str, JsonValue]) -> str | None:
    """For usd and tokens: run == 0 or task == 0 or task <= run."""
    for unit in ("usd", "tokens"):
        task = values[f"budgets.task.max_{unit}"]
        run = values[f"budgets.run.max_{unit}"]
        if task is None or run is None:
            continue
        if cast("float", run) != 0 and cast("float", task) != 0 and cast("float", task) > cast("float", run):
            return f"budgets.task.max_{unit} must not exceed budgets.run.max_{unit}"
    return None


def _isolation_default(values: Mapping[str, JsonValue]) -> str | None:
    """default_profile in available."""
    available = values["worker.isolation.available"]
    default = values["worker.isolation.default_profile"]
    if available is None or default is None:
        return None
    if default not in cast("list[JsonValue]", available):
        return "worker.isolation.default_profile must be one of worker.isolation.available"
    return None


VIEWS: Mapping[str, type] = {
    "execution": ExecutionSettings,
    "budgets": BudgetsSettings,
    "worker": WorkerSettings,
    "checks": ChecksSettings,
}
VALIDATORS: Mapping[str, SectionValidatorFn] = {
    "execution.timeouts_consistent": _timeouts_consistent,
    "execution.lease_renewal": _lease_renewal,
    "execution.work_policy_bounds": _work_policy_bounds,
    "execution.health_order": _health_order,
    "execution.handoff_bounds": _handoff_bounds,
    "execution.integration_mode_consistent": _integration_mode_consistent,
    "budgets.task_le_run": _task_le_run,
    "worker.isolation_default": _isolation_default,
}
