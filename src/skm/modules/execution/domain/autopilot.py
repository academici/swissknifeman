"""Pure session policy and the ordered AP1-AP20 stop table (execution §5.15)."""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import error_for
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.transitions import TransitionDeclaration

if TYPE_CHECKING:
    from datetime import datetime

    from skm.kernel.ids import PrincipalId, ProjectId, RunId, WorkspaceId
    from skm.modules.execution.domain.run import Run


class AutopilotStateKind(StrEnum):
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    DRAINING = "draining"
    STOPPED = "stopped"


@dataclass(frozen=True, slots=True)
class AutopilotState:
    project_id: ProjectId
    workspace_id: WorkspaceId
    state: AutopilotStateKind
    emergency: bool
    current_run_id: RunId | None
    session_started_at: datetime | None
    counters: JsonObject
    session_limits: JsonObject
    stop_code: str | None
    stop_detail: str | None
    updated_by: PrincipalId
    updated_at: datetime
    row_version: int


@dataclass(frozen=True, slots=True)
class AutopilotPolicy:
    allowed: bool = False
    enabled: bool = False
    accept_advisories: bool = False
    max_runs: int = 20
    max_wall_seconds: int = 43200
    max_no_progress_runs: int = 2
    max_auto_decisions: int = 10
    quota_wait_max_seconds: int = 21600
    max_waiting_runs: int = 3
    max_no_improvement_rounds: int = 2
    poll_seconds: int = 30
    # Additional generated settings; old constructor calls remain valid.
    queue: tuple[str, ...] = ()
    max_consecutive_failures: int = 3
    stop_on: tuple[str, ...] = ()


SESSION_LIMITS = ("max_runs", "max_wall_seconds", "max_auto_decisions")
TRANSIENT_CODES = frozenset(
    {"RUNTIME_TIMEOUT", "MODEL_UNAVAILABLE", "RUNTIME_TRANSPORT", "RUNTIME_OVERLOADED"}
)
STOP_CODES = (
    "AUTOPILOT_NO_WORK",
    "AUTOPILOT_DRAINED",
    "AUTOPILOT_STOPPED",
    "AUTOPILOT_MAX_RUNS",
    "AUTOPILOT_MAX_WALL",
    "AUTOPILOT_NOT_ALLOWED",
    "AUTOPILOT_DISABLED",
    "AUTOPILOT_BUSY",
    "AUTOPILOT_NOT_READY",
    "AUTOPILOT_OWNER_NEEDED",
    "AUTOPILOT_BUDGET",
    "AUTOPILOT_QUOTA",
    "AUTOPILOT_REPEATED_BLOCKER",
    "AUTOPILOT_STATE_INVALID",
    "AUTOPILOT_CHECKOUT_LOST",
    "AUTOPILOT_NO_IMPROVEMENT",
    "AUTOPILOT_NO_PROGRESS",
    "AUTOPILOT_DECISIONS_EXCEEDED",
    "AUTOPILOT_RECOVERY_EXHAUSTED",
    "AUTOPILOT_RUN_STOPPED",
)
OWNER_CODES = frozenset((STOP_CODES[5], *STOP_CODES[8:]))


def effective_policy(policy: AutopilotPolicy, limits: JsonObject) -> AutopilotPolicy:
    return replace(
        policy,
        **{
            key: min(getattr(policy, key), int(raw))
            for key in SESSION_LIMITS
            if isinstance(raw := limits.get(key), int | float)
        },
    )


def narrow_limits(previous: JsonObject, requested: JsonObject, policy: AutopilotPolicy) -> JsonObject:
    """Remember configured ceilings too: a later start cannot restore spent authority."""
    return {
        key: min(
            [
                getattr(policy, key),
                *[
                    int(raw)
                    for source in (previous, requested)
                    if isinstance(raw := source.get(key), int | float)
                ],
            ]
        )
        for key in SESSION_LIMITS
    }


def start_session(
    state: AutopilotState,
    policy: AutopilotPolicy,
    now: datetime,
    *,
    new_session: bool = False,
    reason: str = "",
    clear_emergency: bool = False,
    limits: JsonObject | None = None,
) -> tuple[AutopilotState, bool]:
    if not policy.allowed or not policy.enabled:
        raise error_for(ErrorCode.AUTOPILOT_NOT_ENABLED, "autopilot is disabled or disallowed")
    if state.emergency and not clear_emergency:
        raise error_for(ErrorCode.EMERGENCY_STOPPED, "clear_emergency is required")
    if new_session and not reason.strip():
        raise error_for(ErrorCode.SCHEMA_INVALID, "new_session requires a reason")
    if state.state not in {AutopilotStateKind.IDLE, AutopilotStateKind.PAUSED, AutopilotStateKind.STOPPED}:
        raise error_for(ErrorCode.INVALID_TRANSITION, "autopilot cannot start in this state")
    reset = state.state is AutopilotStateKind.IDLE or new_session
    if not reset and state.session_started_at is None:
        raise error_for(ErrorCode.INVALID_TRANSITION, "no session to continue; use new_session with a reason")
    counters: JsonObject = (
        {
            "runs_started": 0,
            "auto_decisions": 0,
            "no_progress_runs": 0,
            "recoveries": 0,
            "infra_failures": 0,
            "last_blocker": None,
        }
        if reset
        else dict(state.counters)
    )
    return replace(
        state,
        state=AutopilotStateKind.RUNNING,
        emergency=False,
        session_started_at=now if reset else state.session_started_at,
        counters=counters,
        session_limits=narrow_limits({} if reset else state.session_limits, limits or {}, policy),
        stop_code=None,
        stop_detail=None,
    ), reset


@dataclass(frozen=True, slots=True)
class AutopilotFacts:
    """Persisted observations supplied by the application; no hidden reads or clock."""

    has_work: bool = True
    active: bool = False
    stopped_by_command: bool = False
    busy: bool = False
    not_ready: bool = False
    owner_needed: bool = False
    waiting_runs: int = 0
    budget_exhausted: bool = False
    quota_exhausted: bool = False
    quota_reset_at: datetime | None = None
    repeated_blocker: bool = False
    state_invalid: bool = False
    checkout_lost: bool = False
    no_improvement_rounds: int = 0
    recovery_open: bool = False
    run_stopped: bool = False


@dataclass(frozen=True, slots=True)
class StopCondition:
    id: str
    code: str
    met: bool
    value: int | float | bool
    limit: int | float | bool

    @property
    def owner_required(self) -> bool:
        return self.code in OWNER_CODES


def counter(state: AutopilotState, key: str) -> float:
    raw = state.counters.get(key, 0)
    return float(raw) if isinstance(raw, int | float) else 0


def evaluate_conditions(
    state: AutopilotState,
    policy: AutopilotPolicy,
    now: datetime,
    facts: AutopilotFacts | None = None,
) -> tuple[StopCondition, ...]:
    facts = facts or AutopilotFacts()
    policy = effective_policy(policy, state.session_limits)
    elapsed = 0 if state.session_started_at is None else (now - state.session_started_at).total_seconds()
    runs = counter(state, "runs_started")
    decisions = counter(state, "auto_decisions")
    no_progress = counter(state, "no_progress_runs")
    quota_wait = None if facts.quota_reset_at is None else (facts.quota_reset_at - now).total_seconds()
    predicates = (
        (
            not facts.has_work and not facts.active and state.state is not AutopilotStateKind.DRAINING,
            False,
            True,
        ),
        (state.state is AutopilotStateKind.DRAINING and not facts.active, False, True),
        (facts.stopped_by_command, False, True),
        (runs >= policy.max_runs, runs, policy.max_runs),
        (elapsed >= policy.max_wall_seconds, elapsed, policy.max_wall_seconds),
        (not policy.allowed, policy.allowed, True),
        (not policy.enabled, policy.enabled, True),
        (facts.busy, facts.busy, True),
        (facts.not_ready, facts.not_ready, True),
        (
            facts.owner_needed or facts.waiting_runs >= policy.max_waiting_runs,
            facts.waiting_runs,
            policy.max_waiting_runs,
        ),
        (facts.budget_exhausted, facts.budget_exhausted, True),
        (
            facts.quota_exhausted and (quota_wait is None or quota_wait > policy.quota_wait_max_seconds),
            quota_wait or 0,
            policy.quota_wait_max_seconds,
        ),
        (facts.repeated_blocker, facts.repeated_blocker, True),
        (
            facts.state_invalid
            or (
                state.state
                in {AutopilotStateKind.RUNNING, AutopilotStateKind.PAUSED, AutopilotStateKind.DRAINING}
                and state.session_started_at is None
            ),
            facts.state_invalid,
            True,
        ),
        (facts.checkout_lost or state.emergency, facts.checkout_lost, True),
        (
            facts.no_improvement_rounds >= policy.max_no_improvement_rounds,
            facts.no_improvement_rounds,
            policy.max_no_improvement_rounds,
        ),
        (no_progress >= policy.max_no_progress_runs, no_progress, policy.max_no_progress_runs),
        (decisions >= policy.max_auto_decisions, decisions, policy.max_auto_decisions),
        (
            facts.recovery_open or counter(state, "infra_failures") >= policy.max_consecutive_failures,
            facts.recovery_open,
            True,
        ),
        (facts.run_stopped, facts.run_stopped, True),
    )
    return tuple(
        StopCondition(f"AP{index}", code, met, value, limit)
        for index, (code, (met, value, limit)) in enumerate(zip(STOP_CODES, predicates, strict=True), 1)
    )


def stop_conditions(
    state: AutopilotState,
    policy: AutopilotPolicy,
    now: datetime,
    facts: AutopilotFacts | None = None,
) -> tuple[str, ...]:
    return tuple(c.code for c in evaluate_conditions(state, policy, now, facts) if c.met)


def classify_outcome(  # noqa: PLR0911 -- closed outcome table
    run: Run | None,
    policy: AutopilotPolicy,
    *,
    now: datetime | None = None,
    quota_reset_at: datetime | None = None,
) -> str:
    if run is None:
        return "continue"
    if run.status.value == "paused" and run.pause_source == "owner":
        return "waiting"
    if run.stop_code == "RESULT_INVALID":
        return "stop(AUTOPILOT_OWNER_NEEDED)"
    if run.stop_code == "BUDGET_EXHAUSTED":
        return "stop(AUTOPILOT_BUDGET)"
    if run.stop_code == "QUOTA_EXHAUSTED":
        if now is not None and quota_reset_at is not None:
            remaining = (quota_reset_at - now).total_seconds()
            if remaining <= 0:
                return (
                    "resume" if run.status.value == "paused" and run.pause_source == "system" else "waiting"
                )
            if remaining <= policy.quota_wait_max_seconds:
                return "wait_quota"
        return "stop(AUTOPILOT_QUOTA)"
    if run.status.value == "paused" and run.pause_source == "system" and run.stop_code in TRANSIENT_CODES:
        return "resume"
    if run.status.value in {"created", "ready", "running", "waiting", "paused"}:
        return "waiting"
    if run.status.value in {"failed", "cancelled"}:
        return "stop(AUTOPILOT_RUN_STOPPED)"
    return "continue"


AUTOPILOT_TRANSITIONS: tuple[TransitionDeclaration, ...] = (
    TransitionDeclaration(None, "`idle`", "`running`"),
    TransitionDeclaration(None, "`stopped`/`paused`", "`running`"),
    TransitionDeclaration(None, "`running`", "`paused`"),
    TransitionDeclaration(None, "`running`/`paused`", "`draining`"),
    TransitionDeclaration(None, "`draining`", "`idle`"),
    TransitionDeclaration(None, "`running`", "`stopped`"),
    TransitionDeclaration(None, "любое", "`stopped`"),
)
