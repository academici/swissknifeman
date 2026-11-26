"""Grant or revoke local host trust for the current subscription digest."""

from __future__ import annotations

from typing import Any, cast

from skm.application_bus.host import HostContext
from skm.kernel.errors import Conflict, NotFound
from skm.kernel.generated.error_codes import ErrorCode
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.integrations.generated.host import (
    TrustHookSubscriptionRequest,
    TrustHookSubscriptionResult,
    trust_hook_subscription_request_from_json,
)

from .host_subscriptions import SubscriptionState, load_policy, setting

__all__ = ["SPEC", "run"]


def run(ctx: HostContext, request: TrustHookSubscriptionRequest) -> TrustHookSubscriptionResult:
    data = cast("dict[str, Any]", trust_hook_subscription_request_from_json(request))
    sid = data["subscription_id"]
    state = ctx.gateways.get(SubscriptionState)
    policy = load_policy(ctx, data["project_id"])
    sub = next((sub for sub in policy["subscriptions"] if sub["id"] == sid), None)
    revoke = bool(data.get("revoke", False))
    if sub is None and not revoke:
        raise NotFound(ErrorCode.NOT_FOUND, "host subscription not found")
    expected = data.get("expected_digest")
    actual = sub["digest"] if sub is not None else None
    if expected is not None and expected != actual:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            "hook subscription changed after review; inspect it again before granting trust",
            details={"subscription_id": sid, "expected_digest": expected, "actual_digest": actual},
        )
    trusted = dict(setting(ctx, "hooks.host.trusted", {}))
    digest = sub["digest"] if sub else trusted.get(sid, "")
    if revoke:
        trusted.pop(sid, None)
    else:
        trusted[sid] = digest
    # trusted is a map-valued registered key; per-id dotted keys are not registry entries.
    command = state.request(
        "settings.set_value",
        {
            "scope": {"level": "host", "scope_id": str(ctx.host_id)},
            "key": "hooks.host.trusted",
            "value": trusted,
            "reason": "revoke hook trust" if revoke else "trust reviewed hook digest",
            "confirmed": True,
        },
    )
    ctx.client.dispatch(command, idempotency_key=f"hook-trust:{state.new_id()}")
    return cast("Any", {"subscription_id": sid, "digest": digest, "trusted": not revoke})


SPEC = HostOperationSpec(
    "integrations.host.trust_hook_subscription", run, dict, dict, cast("Any", frozenset({"cli"}))
)
