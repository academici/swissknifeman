"""Retry decision table (execution §5.5; port of ``orch/retry.py``).

A pure function of the failure class, the stage state and the run policy: no I/O, no clock, no message text.
A decision names the reason of every rule that fired. It decides *infrastructure* repeats only (one more
stage after a transport/provider failure); the other levels keep their own counters and are not folded
into it: HTTP replay, DB serialization retry, result-form retry (§5.8, ``step_max_result_retries``),
semantic rework (task-wide ``rework``/``review`` limits), ``NewAttempt`` (``attempts`` budget) and
reconciliation of an immutable effect. Exhausting one level never resets another, and a change of the
model starts no new budget or counter.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from skm.modules.execution.domain.session import RouteRef

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject

__all__ = [
    "CODE_CLASSES",
    "DEFAULT_ACTIONS",
    "ERROR_CLASSES",
    "RATE_LIMIT_DEFAULT_WAIT_S",
    "STOP_CODES",
    "UNKNOWN_OUTCOME",
    "RetryAction",
    "RetryDecision",
    "RetryInputs",
    "class_for_code",
    "decide_retry",
]

# error/v1 classes of runtimes in schema order; a test compares them with the runtimes ErrorClass values
ERROR_CLASSES: Final = (
    "authentication",
    "authorization",
    "quota",
    "rate_limit",
    "invalid_request",
    "model_unavailable",
    "content_policy",
    "transport",
    "provider_internal",
    "timeout",
    "context_limit",
    "unknown",
)
UNKNOWN_OUTCOME: Final = "unknown_outcome"
RATE_LIMIT_DEFAULT_WAIT_S: Final = 30


class RetryAction(StrEnum):
    STOP = "stop"
    RETRY = "retry"
    RETRY_AFTER = "retry_after"
    FALLBACK_ROUTE = "fallback_route"
    REPLAN = "replan"
    RECONCILE = "reconcile"


DEFAULT_ACTIONS: Final[Mapping[str, RetryAction]] = {
    "authentication": RetryAction.STOP,
    "authorization": RetryAction.STOP,
    "invalid_request": RetryAction.STOP,
    "content_policy": RetryAction.STOP,
    "quota": RetryAction.RETRY_AFTER,
    "rate_limit": RetryAction.RETRY_AFTER,
    "model_unavailable": RetryAction.RETRY,
    "provider_internal": RetryAction.RETRY,
    "transport": RetryAction.RETRY,
    "timeout": RetryAction.RETRY,
    "context_limit": RetryAction.REPLAN,
    "unknown": RetryAction.STOP,
    UNKNOWN_OUTCOME: RetryAction.RECONCILE,
}
# the v2 code the caller records when the decision is ``stop`` (or the action is taken) for the class
STOP_CODES: Final[Mapping[str, str]] = {
    "authentication": "RUNTIME_AUTH_EXPIRED",
    "authorization": "RUNTIME_FORBIDDEN",
    "invalid_request": "RUNTIME_INVALID_REQUEST",
    "content_policy": "CONTENT_REFUSED",
    "quota": "QUOTA_EXHAUSTED",
    "rate_limit": "RATE_LIMITED",
    "model_unavailable": "MODEL_UNAVAILABLE",
    "provider_internal": "RUNTIME_OVERLOADED",
    "transport": "RUNTIME_TRANSPORT",
    "timeout": "RUNTIME_TIMEOUT",
    "context_limit": "CONTEXT_OVERFLOW",
    "unknown": "RUNTIME_FAILURE_UNCLASSIFIED",
    UNKNOWN_OUTCOME: "OUTCOME_UNKNOWN",
}
# A session that ended without a native terminal event is a transport failure even at exit 0 with valid JSON
# in the text (runtimes §4.9, K15); its result is not extracted.
CODE_CLASSES: Final[Mapping[str, str]] = {
    **{code: error_class for error_class, code in STOP_CODES.items()},
    "RUNTIME_STREAM_INCOMPLETE": "transport",
}
_REPEATING: Final = frozenset({RetryAction.RETRY, RetryAction.RETRY_AFTER, RetryAction.FALLBACK_ROUTE})


def class_for_code(code: str) -> str:
    """The retry class of a runtime failure code; an unknown code is ``unknown`` (stop: fail closed)."""
    return CODE_CLASSES.get(code, "unknown")


@dataclass(frozen=True, slots=True)
class RetryInputs:
    error_class: str
    stage_writes: bool  # the role's write_authority is not none, or the stage is integrate
    worktree_dirty: bool
    receipt_unresolved: bool  # an effect receipt with outcome unknown is not reconciled
    attempts_used: int  # including the one that just failed
    stage_retries_max: int
    budget_left: int  # execution.retry.budget_total_max minus the repeats already used by the run
    retry_after_seconds: int | None = None
    current_route: RouteRef | None = None
    max_wait_seconds: int | None = None  # None: any wait is accepted
    role: str | None = (
        None  # selects the ``fallback_routes`` entries of this role; None: unbound entries only
    )
    current_model_class: str | None = (
        None  # RouteRef has no class; needed to tell two routes of one runtime apart
    )


@dataclass(frozen=True, slots=True)
class RetryDecision:
    action: RetryAction
    reason_codes: tuple[str, ...]
    wait_seconds: int | None = None
    route: RouteRef | None = None  # fallback_route only; the caller emits the event that explains it
    route_model_class: str | None = None  # the class of a policy entry that names no concrete model


def _configured(policy: JsonObject, error_class: str) -> Mapping[str, object] | None:
    on_error = policy.get("on_error")
    entry = on_error.get(error_class) if isinstance(on_error, Mapping) else None
    if entry is None:
        return None
    if not isinstance(entry, Mapping):
        raise ValueError(f"retry.on_error.{error_class} must be an object")
    action = entry.get("action")
    if action not in {item.value for item in RetryAction}:
        raise ValueError(f"retry.on_error.{error_class}.action is not a retry action: {action!r}")
    return entry


def _same_route(inputs: RetryInputs, entry: Mapping[str, object]) -> bool:
    """A route is the current one when the runtime matches and nothing the entry names differs.

    Two routes differ by runtime or model class (§5.5 rule 5); an unknown current route or class never
    proves sameness, so a declared fallback is not discarded for lack of facts.
    """
    current = inputs.current_route
    if current is None or entry.get("runtime") != current.runtime_id:
        return False
    if entry.get("model") not in (None, current.model):
        return False
    named_class = entry.get("model_class")
    return named_class is None or named_class == inputs.current_model_class


def _other_route(inputs: RetryInputs, policy: JsonObject) -> Mapping[str, object] | None:
    routes = policy.get("fallback_routes")
    if not isinstance(routes, Sequence) or isinstance(routes, str):
        return None
    for entry in routes:
        if not isinstance(entry, Mapping):
            continue
        # an entry bound to a role is for that role only; an unknown role matches the unbound entries alone
        bound = entry.get("role")
        if bound is not None and bound != inputs.role:
            continue
        if not _same_route(inputs, entry):
            return entry
    return None


def _fallback(entry: Mapping[str, object], reasons: list[str]) -> RetryDecision:
    model, model_class, effort = entry.get("model"), entry.get("model_class"), entry.get("effort")
    route = RouteRef(
        runtime_id=str(entry["runtime"]),
        model=model if isinstance(model, str) else "",
        effort=effort if isinstance(effort, str) else None,
    )
    return RetryDecision(
        RetryAction.FALLBACK_ROUTE,
        tuple(reasons),
        route=route,
        route_model_class=model_class if isinstance(model_class, str) else None,
    )


def _after_wait(inputs: RetryInputs, policy: JsonObject, reasons: list[str]) -> RetryDecision:
    """Rule 5: wait for the reset, or leave for another declared route, or stop; never wait unboundedly."""
    wait, why = inputs.retry_after_seconds, None
    if wait is None and inputs.error_class == "quota":
        why = "RETRY_AFTER_UNKNOWN"
    else:
        wait = wait or RATE_LIMIT_DEFAULT_WAIT_S
        if inputs.max_wait_seconds is not None and wait > inputs.max_wait_seconds:
            why = "WAIT_TOO_LONG"
    if why is None:
        return RetryDecision(RetryAction.RETRY_AFTER, tuple(reasons), wait_seconds=wait)
    # A reset that is unknown or too far away is not waited for: another declared route, else a stop.
    entry = _other_route(inputs, policy) if inputs.max_wait_seconds is not None else None
    if entry is not None:
        return _fallback(entry, [*reasons, why, "FALLBACK_ROUTE"])
    return RetryDecision(RetryAction.STOP, (*reasons, why))


def decide_retry(inputs: RetryInputs, policy: JsonObject) -> RetryDecision:
    """Apply the rules in order; the reasons of every rule that fired are kept.

    ``policy`` is ``{on_error, fallback_routes}`` of ``execution.retry.*``; ``stage_retries_max``,
    ``budget_left`` and ``max_wait_seconds`` come in through ``inputs``. Unknown failure class raises
    ``ValueError`` (a programming error, never a runtime fact: ``class_for_code`` maps codes safely).
    """
    cls = inputs.error_class
    if cls not in DEFAULT_ACTIONS:
        raise ValueError(f"unknown failure class {cls!r}")
    configured = _configured(policy, cls)
    if configured is not None:
        action, reasons = RetryAction(str(configured["action"])), ["ACTION_FROM_POLICY"]
    else:
        action, reasons = DEFAULT_ACTIONS[cls], ["ACTION_DEFAULT"]
    if cls == "content_policy" and action is not RetryAction.STOP:
        # A refusal is final: the same prompt through another route or another try is an evasion of the
        # refusal, so no policy override makes it repeat.
        return RetryDecision(RetryAction.STOP, ("ACTION_DEFAULT", "CONTENT_POLICY_OVERRIDE_IGNORED"))
    if cls == UNKNOWN_OUTCOME:
        # The request may have been executed: a writing stage is never repeated without reconciliation.
        if inputs.stage_writes:
            return RetryDecision(RetryAction.RECONCILE, (*reasons, "UNKNOWN_OUTCOME_WRITE"))
        action = RetryAction.RETRY
        reasons.append("UNKNOWN_OUTCOME_READ_ONLY")
    if action in _REPEATING and inputs.stage_writes and (inputs.worktree_dirty or inputs.receipt_unresolved):
        return RetryDecision(RetryAction.RECONCILE, (*reasons, "PARTIAL_CHANGES"))
    if action in _REPEATING:
        limit = configured.get("max") if configured is not None else None
        if (
            inputs.attempts_used > inputs.stage_retries_max
            or inputs.budget_left <= 0
            or (isinstance(limit, int) and inputs.attempts_used > limit)
        ):
            return RetryDecision(RetryAction.STOP, (*reasons, "BUDGET_EXHAUSTED"))
    if action is RetryAction.RETRY_AFTER:
        return _after_wait(inputs, policy, reasons)
    if action is RetryAction.FALLBACK_ROUTE:
        entry = _other_route(inputs, policy)
        if entry is not None:
            return _fallback(entry, [*reasons, "FALLBACK_ROUTE"])
        return RetryDecision(RetryAction.STOP, (*reasons, "FALLBACK_UNDECLARED"))
    if action is RetryAction.REPLAN:
        reasons.append("CONTEXT_LIMIT")
    return RetryDecision(action, tuple(reasons))
