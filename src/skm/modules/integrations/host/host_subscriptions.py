"""Trusted host subscriptions. All process, clock and local state IO belongs to gateways."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from typing import Any, Protocol, cast

from skm.application_bus.host import HostContext
from skm.kernel.gateways import host_gateway
from skm.modules.integrations.domain.hook_events import HookClass, HookSurfaceId, NormalizedHookEvent
from skm.modules.integrations.domain.hook_outcomes import (
    HostCommandVerdict,
    HostHookOutcome,
    HostOutcomeStatus,
    combine_outcomes,
)
from skm.modules.integrations.domain.hook_rules import HookDecision, HookVerdict
from skm.modules.integrations.domain.hook_subscriptions import (
    Backoff,
    FailurePolicy,
    RetrySpec,
    next_attempt_at,
)
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated.documents import host_command_output_from_json
from skm.modules.integrations.ports import HostCommandRunner

__all__ = ["SubscriptionState", "load_policy", "run_host_subscriptions", "run_one", "setting"]


@host_gateway
class SubscriptionState(Protocol):
    def host_config(self) -> object | None: ...
    def request(self, name: str, payload: dict[str, Any]) -> object: ...
    def new_id(self) -> str: ...
    def monotonic(self) -> float: ...
    def environment(self, allowed: Sequence[str], refs: Mapping[str, str]) -> dict[str, str]: ...
    def cwd(self, kind: str, checkout: str) -> Any: ...
    def parallel(
        self, actions: Sequence[Callable[[], HostHookOutcome]], limit: int
    ) -> list[HostHookOutcome]: ...
    def audit(self, record: dict[str, Any]) -> None: ...
    def enqueue(self, document: dict[str, Any], limit: int) -> None: ...
    def locked(self) -> Any: ...
    def pending(self) -> list[tuple[str, dict[str, Any]]]: ...
    def replace(self, key: str, document: dict[str, Any] | None) -> None: ...
    def now(self) -> Any: ...
    def start_drain(self, bootstrap_path: str | None) -> None: ...


def setting(ctx: HostContext, key: str, default: Any) -> Any:
    source = ctx.config
    if ctx.gateways.has(SubscriptionState):
        fresh = ctx.gateways.get(SubscriptionState).host_config()
        source = source if fresh is None else fresh
    value = cast("Any", source).get(key)
    return default if value is None else value


def load_policy(ctx: HostContext, project: str, target: str = TargetId.CLAUDE_CODE.value) -> dict[str, Any]:
    state = ctx.gateways.get(SubscriptionState)
    query = state.request("integrations.get_hook_policy", {"project_id": project, "target": target})
    result: Any = ctx.client.ask(query)
    return dict(result.to_json() if hasattr(result, "to_json") else result)


def _input(
    event: NormalizedHookEvent, sub: Mapping[str, Any], policy: Mapping[str, Any], ctx: HostContext
) -> dict[str, Any]:
    return {
        "schema": "urn:skm:integrations:host-command-input:v1",
        "subscription_id": sub["id"],
        "class": sub["class"],
        "project_id": policy["project_id"],
        "host_id": str(ctx.host_id),
        "target": event.target.value,
        "event": {
            "schema": "urn:skm:integrations:defs:v1#/$defs/hook_event",
            **asdict(event),
            "paths": list(event.paths),
        },
    }


def run_one(
    ctx: HostContext,
    sub: Mapping[str, Any],
    document: dict[str, Any],
    timeout_ms: int,
    *,
    checkout_root: str | None = None,
) -> HostHookOutcome:
    state = ctx.gateways.get(SubscriptionState)
    status, verdict, reason, context, duration = HostOutcomeStatus.OK, HostCommandVerdict.NONE, None, None, 0
    trusted = setting(ctx, "hooks.host.trusted", {})
    if trusted.get(sub["id"]) != sub["digest"]:
        status = HostOutcomeStatus.UNTRUSTED
    elif timeout_ms <= 0 or ctx.cancel.cancelled:
        status = HostOutcomeStatus.SKIPPED_BUDGET
    else:
        try:
            env = state.environment(sub["env_allow"], sub["env_refs"])
            # Defense in depth: credentials and bootstrap variables can never be requested by a subscription.
            env = {name: value for name, value in env.items() if not name.upper().startswith("SKM_")}
            env.update(
                SKM_HOOK_SUBSCRIPTION_ID=sub["id"],
                SKM_PROJECT_ID=document["project_id"],
                SKM_HOOK_EVENT_KIND=document["event"]["kind"],
            )
            raw = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode(
                "utf-8"
            )
            result = ctx.gateways.get(HostCommandRunner).run(
                sub["argv"],
                cwd=state.cwd(sub["cwd"], checkout_root or document["event"]["cwd"]),
                env=env,
                stdin=raw,
                timeout_ms=timeout_ms,
            )
            duration = result.duration_ms
            if result.timed_out:
                status = HostOutcomeStatus.TIMEOUT
            elif result.exit_code != 0:
                status = HostOutcomeStatus.FAILED
            elif sub["class"] != "observation":
                try:
                    if len(result.stdout) > 65536:
                        raise ValueError("output limit")
                    output = cast(
                        "dict[str, Any]",
                        host_command_output_from_json(json.loads(result.stdout.decode("utf-8"))),
                    )
                    verdict = HostCommandVerdict(output["decision"])
                    reason, context = output.get("reason"), output.get("additional_context")
                except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                    status = HostOutcomeStatus.INVALID_OUTPUT
        except Exception:  # noqa: BLE001 - no provider or secret data in outcomes/audit
            status = HostOutcomeStatus.FAILED
    outcome = HostHookOutcome(
        str(sub["id"]),
        HookClass(sub["class"]),
        FailurePolicy(sub["failure_policy"]),
        status,
        verdict,
        reason,
        context,
        duration,
    )
    state.audit(
        {
            "subscription_id": sub["id"],
            "digest": sub["digest"],
            "status": status.value,
            "verdict": verdict.value,
            "duration_ms": duration,
            "occurred_at": state.now().isoformat(),
        }
    )
    return outcome


def run_host_subscriptions(
    event: NormalizedHookEvent, cls: HookClass, policy: Mapping[str, Any], hctx: HostContext, budget_ms: int
) -> HookDecision:
    state = hctx.gateways.get(SubscriptionState)
    deadline = state.monotonic() + budget_ms / 1000
    subs = sorted(
        (
            sub
            for sub in policy.get("subscriptions", ())
            if sub["class"] == cls.value and f"client:{event.kind.value}" in sub["event_types"]
        ),
        key=lambda sub: sub["id"],
    )
    documents = {sub["id"]: _input(event, sub, policy, hctx) for sub in subs}

    def launch(sub: Mapping[str, Any]) -> HostHookOutcome:
        remaining = int((deadline - state.monotonic()) * 1000) - 100
        return run_one(
            hctx,
            sub,
            documents[sub["id"]],
            min(sub["timeout_ms"], remaining),
            checkout_root=policy.get("checkout_root"),
        )

    outcomes = state.parallel(
        [lambda sub=sub: launch(sub) for sub in subs],
        max(1, int(setting(hctx, "hooks.host.max_parallel", 4))),
    )
    limit = int(setting(hctx, "hooks.host.spool_max_items", 1000))
    for sub, outcome in zip(subs, outcomes, strict=True):
        if (
            limit > 0
            and cls is HookClass.OBSERVATION
            and sub["failure_policy"] == "retry"
            and outcome.status in {HostOutcomeStatus.FAILED, HostOutcomeStatus.TIMEOUT}
        ):
            retry = sub["retry"]
            available = next_attempt_at(
                RetrySpec(retry["max_attempts"], Backoff(**retry["backoff"])),
                attempt=1,
                now=state.now(),
                jitter=1.0,
            )
            state.enqueue(
                {
                    "input": documents[sub["id"]],
                    "digest": sub["digest"],
                    "attempts": 1,
                    "available_at": available.isoformat(),
                    "checkout_root": policy.get("checkout_root"),
                },
                limit,
            )
    return combine_outcomes(
        HookDecision(HookVerdict.NONE, HookSurfaceId.SUBSCRIPTIONS, None, None, None, None), outcomes
    )
