"""Trusted host subscriptions. All process, clock and local state IO belongs to gateways."""

from __future__ import annotations

import json
import posixpath
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict
from typing import Any, Protocol, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.gateways import host_gateway
from skm.kernel.ids import ProjectId
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
from skm.modules.integrations.domain.presets import (
    CLAUDE_SETTINGS,
    PRESET_SUBSCRIPTION_DIGESTS,
    PRESET_SUBSCRIPTIONS,
    Preset,
    preset_of_renderer,
    preset_subscription_config,
)
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated.documents import host_command_output_from_json
from skm.modules.integrations.generated.queries import GetAppliedState
from skm.modules.integrations.generated.views import AppliedStateView
from skm.modules.integrations.ports import HostCommandRunner

from .hook_state import HookState
from .observe import list_all_projections

__all__ = [
    "SubscriptionState",
    "bound_preset",
    "load_policy",
    "run_host_subscriptions",
    "run_one",
    "scope_preset_subscriptions",
    "setting",
]


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


def bound_preset(
    ctx: HostContext,
    state: HookState,
    target: TargetId,
    project: str,
    binding: str,
    timeout: int,
    *,
    settings_path: str | None = None,
) -> Preset | None:
    return cast(
        "Preset | None",
        state.call(lambda: _applied_preset(ctx, target, project, binding, settings_path), timeout),
    )


def _applied_preset(
    ctx: HostContext, target: TargetId, project: str, binding: str, settings_path: str | None
) -> Preset | None:
    view = ctx.client.ask(
        GetAppliedState(
            project_id=UUID(project), checkout_binding_id=UUID(binding), target=cast("Any", target.value)
        )
    )
    assert isinstance(view, AppliedStateView)  # noqa: S101
    if view.projection is None or view.projection.state == "removed":
        return None
    return next(
        (
            preset
            for file in view.files
            if (settings_path is None or file.relative_path == settings_path)
            and (preset := preset_of_renderer(file.renderer)) is not None
        ),
        None,
    )


def scope_preset_subscriptions(
    ctx: HostContext,
    target: TargetId,
    project: str,
    binding: str,
    policy: dict[str, Any],
    *,
    state: HookState | None = None,
    timeout: int = 0,
) -> dict[str, Any]:
    subscriptions = policy.get("subscriptions", ())
    possible = {
        sub["id"] for sub in subscriptions if PRESET_SUBSCRIPTION_DIGESTS.get(sub["id"]) == sub["digest"]
    }
    if target is not TargetId.CLAUDE_CODE or not possible:
        return policy

    def resolve() -> tuple[set[str], set[str]]:
        preset = _applied_preset(ctx, target, project, binding, CLAUDE_SETTINGS)
        local_ids = possible.intersection(preset_subscription_config(preset, target))
        excluded = _other_applied_preset_ids(ctx, target, project, binding, possible - local_ids)
        ambiguous = possible - local_ids - excluded
        if ambiguous:
            # A cached policy can contain a removed preset, and unrelated settings can change its generation.
            current = load_policy(ctx, project, target.value)
            current_ids = {
                sub["id"]
                for sub in current["subscriptions"]
                if PRESET_SUBSCRIPTION_DIGESTS.get(sub["id"]) == sub["digest"]
            }
            excluded.update(ambiguous - current_ids)
        return local_ids, excluded

    local_ids, excluded = resolve() if state is None else state.call(resolve, timeout)
    return {
        **policy,
        "subscriptions": [
            {**sub, "preset_check": True} if sub["id"] in local_ids else sub
            for sub in subscriptions
            if sub["id"] not in excluded
        ],
    }


def _other_applied_preset_ids(
    ctx: HostContext, target: TargetId, project: str, binding: str, possible: set[str]
) -> set[str]:
    # A configured command can exactly match a preset command. Check its applied
    # records before treating the shared digest as a checkout-specific preset.
    found: set[str] = set()
    if possible:
        for summary in list_all_projections(ctx, ProjectId(UUID(project))):
            other = str(summary.checkout_binding_id)
            if summary.target != target.value or summary.state == "removed" or other == binding:
                continue
            preset = _applied_preset(ctx, target, project, other, CLAUDE_SETTINGS)
            found.update(possible.intersection(preset_subscription_config(preset, target)))
            if found == possible:
                break
    return found


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


def _run_preset(
    ctx: HostContext,
    state: SubscriptionState,
    sub: Mapping[str, Any],
    document: dict[str, Any],
    root: str,
    env: Mapping[str, str],
    timeout_ms: int,
) -> tuple[HostOutcomeStatus, str | None, str | None, int]:
    preset_check = PRESET_SUBSCRIPTIONS[sub["id"]]
    event = document["event"]
    if (
        tuple(sub["argv"]) != preset_check.argv
        or sub["class"] != preset_check.hook_class.value
        or event["kind"] != preset_check.event.value
        or sub["cwd"] != "checkout"
    ):
        return HostOutcomeStatus.FAILED, "Invalid preset check command.", None, 0

    arguments: tuple[tuple[str, ...], ...] = ((),)
    if preset_check.extension is not None:
        resolver = ctx.gateways.get(HookState)
        files = dict.fromkeys(
            resolver.resolve(path, event["cwd"])
            for path in event["paths"]
            if path.endswith(preset_check.extension)
        )
        arguments = tuple(
            (path,)
            for path in files
            if path.endswith(preset_check.extension) and path.startswith(root.rstrip("/") + "/")
        )

    deadline = state.monotonic() + timeout_ms / 1000
    runner = ctx.gateways.get(HostCommandRunner)
    duration = 0
    for args in arguments:
        remaining = int((deadline - state.monotonic()) * 1000)
        if remaining <= 0 or ctx.cancel.cancelled:
            return HostOutcomeStatus.SKIPPED_BUDGET, None, None, duration
        result = runner.run(
            (*preset_check.argv, *args),
            cwd=state.cwd("checkout", root),
            env=env,
            stdin=b"",
            timeout_ms=remaining,
        )
        duration += result.duration_ms
        if result.timed_out or result.exit_code != 0:
            status = HostOutcomeStatus.TIMEOUT if result.timed_out else HostOutcomeStatus.FAILED
            message = f"{preset_check.id} {'timed out' if result.timed_out else 'failed'}."
            return status, message, message if preset_check.extension else None, duration
    return HostOutcomeStatus.OK, None, None, duration


def _run_command(
    ctx: HostContext,
    state: SubscriptionState,
    sub: Mapping[str, Any],
    document: dict[str, Any],
    root: str,
    env: Mapping[str, str],
    timeout_ms: int,
) -> tuple[HostOutcomeStatus, HostCommandVerdict, str | None, str | None, int]:
    if sub.get("preset_check") is True:
        status, reason, context, duration = _run_preset(ctx, state, sub, document, root, env, timeout_ms)
        return status, HostCommandVerdict.NONE, reason, context, duration

    raw = json.dumps(document, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    result = ctx.gateways.get(HostCommandRunner).run(
        sub["argv"],
        cwd=state.cwd(sub["cwd"], root),
        env=env,
        stdin=raw,
        timeout_ms=timeout_ms,
    )
    duration = result.duration_ms
    if result.timed_out:
        return HostOutcomeStatus.TIMEOUT, HostCommandVerdict.NONE, None, None, duration
    if result.exit_code != 0:
        return HostOutcomeStatus.FAILED, HostCommandVerdict.NONE, None, None, duration
    if sub["class"] == "observation":
        return HostOutcomeStatus.OK, HostCommandVerdict.NONE, None, None, duration
    try:
        if len(result.stdout) > 65536:
            raise ValueError("output limit")
        output = cast(
            "dict[str, Any]", host_command_output_from_json(json.loads(result.stdout.decode("utf-8")))
        )
        return (
            HostOutcomeStatus.OK,
            HostCommandVerdict(output["decision"]),
            output.get("reason"),
            output.get("additional_context"),
            duration,
        )
    except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
        return HostOutcomeStatus.INVALID_OUTPUT, HostCommandVerdict.NONE, None, None, duration


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
            env["PATH"] = (
                ":".join(path for path in env.get("PATH", "").split(":") if posixpath.isabs(path))
                or "/usr/bin:/bin"
            )
            env.update(
                SKM_HOOK_SUBSCRIPTION_ID=sub["id"],
                SKM_PROJECT_ID=document["project_id"],
                SKM_HOOK_EVENT_KIND=document["event"]["kind"],
            )
            status, verdict, reason, context, duration = _run_command(
                ctx, state, sub, document, checkout_root or document["event"]["cwd"], env, timeout_ms
            )
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
