"""Exercise a host subscription with synthetic input through the trusted command runner."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any, cast
from uuid import UUID

from skm.application_bus.host import HostContext
from skm.kernel.errors import NotFound
from skm.kernel.generated.error_codes import ErrorCode
from skm.kernel.ids import ProjectId
from skm.kernel.module_manifest import HostOperationSpec
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated.host import (
    TestHostSubscriptionRequest,
    TestHostSubscriptionResult,
    test_host_subscription_request_from_json,
)

from .host_subscriptions import load_policy, run_one, scope_preset_subscriptions
from .observe import resolve_checkout_for_mount

__all__ = ["SPEC", "run"]
__test__ = False


def run(ctx: HostContext, request: TestHostSubscriptionRequest) -> TestHostSubscriptionResult:
    data = cast("dict[str, Any]", test_host_subscription_request_from_json(request))
    policy = load_policy(ctx, data["project_id"])
    sub = next((sub for sub in policy["subscriptions"] if sub["id"] == data["subscription_id"]), None)
    if sub is None:
        raise NotFound(ErrorCode.NOT_FOUND, "host subscription not found")
    location = resolve_checkout_for_mount(ctx, ProjectId(UUID(data["project_id"])), "main")
    scoped = scope_preset_subscriptions(
        ctx,
        TargetId.CLAUDE_CODE,
        data["project_id"],
        str(location.binding_id),
        {**policy, "subscriptions": [sub]},
    )
    if not scoped["subscriptions"]:
        raise NotFound(ErrorCode.NOT_FOUND, "host subscription not found")
    (sub,) = scoped["subscriptions"]
    document = {
        "schema": "urn:skm:integrations:host-command-input:v1",
        "subscription_id": sub["id"],
        "class": sub["class"],
        "project_id": data["project_id"],
        "host_id": str(ctx.host_id),
        "target": TargetId.CLAUDE_CODE.value,
        "event": {
            "schema": "urn:skm:integrations:defs:v1#/$defs/hook_event",
            "kind": data["event_kind"],
            "target": TargetId.CLAUDE_CODE.value,
            "cwd": location.local_locator,
            "command": data.get("command"),
            "paths": data.get("paths", []),
            "session_id": None,
            "tool_name": None,
            "prompt": None,
            "stop_status": None,
            "raw_event_name": "test",
        },
    }
    outcome = run_one(ctx, sub, document, sub["timeout_ms"])
    result = asdict(outcome)
    result["class"] = result.pop("hook_class")
    return cast("Any", result)


SPEC = HostOperationSpec(
    "integrations.host.test_host_subscription", run, dict, dict, cast("Any", frozenset({"cli"}))
)
