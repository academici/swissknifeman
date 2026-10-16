"""Retry decision table: a pure function of the failure class, the stage state and the run policy.

No I/O and no system clock. The class of a failure comes from a normalized error/v1 record or from the
kind of the terminal event, never from message text. A decision names its reasons; the caller records it.
"""
from __future__ import annotations

from dataclasses import dataclass

ACTIONS = ("stop", "retry", "retry_after", "fallback_route", "replan", "reconcile")
# The error/v1 classes of aicore in schema order; a test compares them with the schema enum.
ERROR_CLASSES = (
    "authentication", "authorization", "quota", "rate_limit", "invalid_request", "model_unavailable",
    "content_policy", "transport", "provider_internal", "timeout", "context_limit", "unknown",
)
UNKNOWN_OUTCOME = "unknown_outcome"
DEFAULT_ACTIONS = {
    "authentication": "stop", "authorization": "stop", "invalid_request": "stop", "content_policy": "stop",
    "quota": "retry_after", "rate_limit": "retry_after",
    "model_unavailable": "retry", "provider_internal": "retry", "transport": "retry", "timeout": "retry",
    "context_limit": "replan", "unknown": "stop", UNKNOWN_OUTCOME: "reconcile",
}
RATE_LIMIT_DEFAULT_WAIT_S = 30
_REPEATING = frozenset({"retry", "retry_after", "fallback_route"})
_KIND_CLASS = {
    "quota_block": "quota", "quota_blocked": "quota", "auth_block": "authentication",
    "auth_blocked": "authentication", "timeout": "timeout", "provider_error": "provider_internal",
    "unknown_outcome": UNKNOWN_OUTCOME, "failed": "unknown",
}


@dataclass(frozen=True)
class RetryInputs:
    error_class: str            # an error/v1 class, or "unknown_outcome"
    stage_writes: bool          # the role's write_authority is not "none"
    worktree_dirty: bool        # the stage worktree has a non-empty diff
    receipt_unresolved: bool    # an effect receipt with outcome "unknown" is not reconciled
    attempts_used: int          # attempts made so far, including the one that just failed
    stage_retries_max: int      # stages[].retries.max, 0 when absent
    budget_left: int            # retries_budget.total_max minus the retries already used
    retry_after_s: int | None = None
    current_route: dict | None = None
    max_wait_s: int | None = None   # the longest wait the caller accepts; None = no limit (the earlier behaviour)


@dataclass(frozen=True)
class RetryDecision:
    action: str
    reason_codes: tuple
    wait_s: int | None = None
    route: dict | None = None   # only for fallback_route; the caller must emit an event that explains it


def class_of(kind_or_status: str, error: dict | None = None) -> str:
    """Failure class of a terminal event kind or stage status; an error/v1 record decides when given."""
    if error is not None:
        return error["class"]
    try:
        return _KIND_CLASS[kind_or_status]
    except KeyError:
        raise ValueError(f"{kind_or_status!r} is not a failure kind or status") from None


def _same_route(left: dict | None, right: dict) -> bool:
    return left is not None and all(left.get(key) == right.get(key) for key in ("provider", "model_class"))


def _other_route(inputs: RetryInputs, policy: dict) -> dict | None:
    for route in policy.get("fallback_routes") or ():
        if not _same_route(inputs.current_route, route):
            return dict(route)
    return None


def decide(inputs: RetryInputs, policy: dict) -> RetryDecision:
    """Apply the rules in order; the reasons of every rule that fired are kept."""
    cls = inputs.error_class
    if cls not in DEFAULT_ACTIONS:
        raise ValueError(f"unknown failure class {cls!r}")
    configured = (policy.get("on_error") or {}).get(cls)
    if configured is not None:
        action, reasons = configured["action"], ["ACTION_FROM_POLICY"]
    else:
        action, reasons = DEFAULT_ACTIONS[cls], ["ACTION_DEFAULT"]
    if cls == UNKNOWN_OUTCOME:
        # The request may have been executed: a writing stage is never repeated without reconciliation.
        if inputs.stage_writes:
            return RetryDecision("reconcile", tuple(reasons + ["UNKNOWN_OUTCOME_WRITE"]))
        action = "retry"
        reasons.append("UNKNOWN_OUTCOME_READ_ONLY")
    if action in _REPEATING and inputs.stage_writes and (inputs.worktree_dirty or inputs.receipt_unresolved):
        return RetryDecision("reconcile", tuple(reasons + ["PARTIAL_CHANGES"]))
    if action in _REPEATING:
        limit = (configured or {}).get("max")
        if (inputs.attempts_used > inputs.stage_retries_max or inputs.budget_left <= 0
                or (limit is not None and inputs.attempts_used > limit)):
            return RetryDecision("stop", tuple(reasons + ["BUDGET_EXHAUSTED"]))
    if action == "retry_after":
        wait = inputs.retry_after_s
        why = None
        if wait is None and cls == "quota":
            why = "RETRY_AFTER_UNKNOWN"
        else:
            wait = RATE_LIMIT_DEFAULT_WAIT_S if wait is None else wait
            if inputs.max_wait_s is not None and wait > inputs.max_wait_s:
                why = "WAIT_TOO_LONG"
        if why is not None:
            # A reset that is unknown or too far away is not waited for: another declared route, else a stop.
            route = _other_route(inputs, policy) if inputs.max_wait_s is not None else None
            if route is not None:
                return RetryDecision("fallback_route", tuple(reasons + [why, "FALLBACK_ROUTE"]), route=route)
            return RetryDecision("stop", tuple(reasons + [why]))
        return RetryDecision("retry_after", tuple(reasons), wait_s=wait)
    if action == "fallback_route":
        route = _other_route(inputs, policy)
        if route is not None:
            return RetryDecision("fallback_route", tuple(reasons + ["FALLBACK_ROUTE"]), route=route)
        return RetryDecision("stop", tuple(reasons + ["FALLBACK_UNDECLARED"]))
    if action == "replan":
        reasons.append("CONTEXT_LIMIT")
    return RetryDecision(action, tuple(reasons))
