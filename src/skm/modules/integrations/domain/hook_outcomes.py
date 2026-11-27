"""Host hook subscription outcome types and pure combination rules (integrations §4.10, §5.8.5)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .hook_events import HookClass, HookSurfaceId
from .hook_rules import HookDecision, HookVerdict
from .hook_subscriptions import FailurePolicy

__all__ = [
    "HostCommandVerdict",
    "HostHookOutcome",
    "HostOutcomeStatus",
    "combine_outcomes",
]

_CONTEXT_MAX_CHARS: Final = 4000
_VERDICT_RANK: Final[dict[HookVerdict, int]] = {
    HookVerdict.NONE: 0,
    HookVerdict.ALLOW: 1,
    HookVerdict.CONTEXT: 2,
    HookVerdict.ASK: 3,
    HookVerdict.DENY: 4,
}


class HostCommandVerdict(StrEnum):
    DENY = "deny"
    ASK = "ask"
    NONE = "none"


class HostOutcomeStatus(StrEnum):
    OK = "ok"
    FAILED = "failed"
    TIMEOUT = "timeout"
    INVALID_OUTPUT = "invalid_output"
    UNTRUSTED = "untrusted"
    SKIPPED_BUDGET = "skipped_budget"


@dataclass(frozen=True, slots=True)
class HostHookOutcome:
    subscription_id: str
    hook_class: HookClass
    failure_policy: FailurePolicy
    status: HostOutcomeStatus
    verdict: HostCommandVerdict
    reason: str | None
    additional_context: str | None
    duration_ms: int


def _untrusted_message(subscription_id: str) -> str:
    return (
        f"hook subscription {subscription_id} is not trusted on this host; "
        f'review it with "skm hooks show {subscription_id}" and run "skm hooks trust {subscription_id}"'
    )


def _evaluate_outcome(outcome: HostHookOutcome) -> tuple[HookVerdict, str | None, str | None]:
    if outcome.hook_class is HookClass.ENFORCEMENT and outcome.failure_policy is FailurePolicy.DENY:
        if outcome.status is HostOutcomeStatus.OK:
            if outcome.verdict is HostCommandVerdict.DENY:
                return HookVerdict.DENY, None, outcome.reason
            if outcome.verdict is HostCommandVerdict.ASK:
                return HookVerdict.ASK, None, outcome.reason
            return HookVerdict.NONE, None, None
        if outcome.status is HostOutcomeStatus.UNTRUSTED:
            return HookVerdict.ASK, "HOOK_SUBSCRIPTION_UNTRUSTED", _untrusted_message(outcome.subscription_id)
        msg = outcome.reason or f"hook subscription {outcome.subscription_id} failed ({outcome.status.value})"
        return HookVerdict.DENY, "HOOK_SUBSCRIPTION_FAILED", msg
    if outcome.hook_class is HookClass.WORKFLOW and outcome.additional_context:
        return HookVerdict.CONTEXT, None, None
    return HookVerdict.NONE, None, None


def combine_outcomes(builtin: HookDecision, outcomes: Sequence[HostHookOutcome]) -> HookDecision:
    """Combine host subscription outcomes with ``builtin`` by strictness ``DENY > ASK > CONTEXT > NONE``."""
    ordered = sorted(outcomes, key=lambda item: item.subscription_id)
    best_verdict = builtin.verdict
    best_surface = builtin.surface
    best_reason = builtin.reason_code
    best_user = builtin.user_message
    best_agent = builtin.agent_message

    contexts: list[str] = []
    if builtin.additional_context:
        contexts.append(builtin.additional_context)

    for outcome in ordered:
        verdict, reason_code, message = _evaluate_outcome(outcome)
        if verdict is HookVerdict.CONTEXT and outcome.additional_context:
            contexts.append(outcome.additional_context)
        if _VERDICT_RANK[verdict] > _VERDICT_RANK[best_verdict]:
            best_verdict = verdict
            best_surface = HookSurfaceId.SUBSCRIPTIONS
            best_reason = reason_code
            best_user = message
            best_agent = message

    merged_context = "\n\n".join(contexts)[:_CONTEXT_MAX_CHARS] if contexts else None
    final_context = merged_context if best_verdict is HookVerdict.CONTEXT else None
    keep_context = best_verdict not in {HookVerdict.DENY, HookVerdict.ASK}
    if builtin.additional_context and keep_context and final_context is None:
        final_context = merged_context
    return HookDecision(
        verdict=best_verdict,
        surface=best_surface,
        reason_code=best_reason,
        user_message=best_user,
        agent_message=best_agent,
        additional_context=final_context,
    )
