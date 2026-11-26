"""Ownership, subscription validity, local trust and capability checks (integrations §5.6)."""

from __future__ import annotations

import hashlib

from skm.kernel.json_types import JsonObject
from skm.modules.integrations.domain.hook_events import HookClass, HookEventKind
from skm.modules.integrations.domain.hook_subscriptions import ExecutionLocation, validate_subscription
from skm.modules.integrations.domain.managed_block import extract_blocks, parse_markers
from skm.modules.integrations.domain.reports import CheckResult

from .context import DoctorContext, finding, strings

__all__ = ["CHECKS", "local_settings_gitignored"]


def local_settings_gitignored(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    return finding(
        ctx,
        "local.settings_gitignored",
        "warning",
        "Local settings ignored by git",
        (
            (str(layer.get("path")), "Local settings are not confirmed gitignored")
            for layer in ctx.layers
            if layer.get("layer") == "local"
            and layer.get("exists") is True
            and layer.get("gitignored") is not True
        ),
    )


def projection_drift(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    return finding(
        ctx,
        "projection.drift",
        "warning",
        "Applied projection matches checkout",
        (
            (path, "Projection conflict, unsafe boundary, missing file or unfinished apply")
            for path in ctx.drift_paths
        ),
        "Inspect projection drift before applying or adopting changes",
    )


def checkout_marker(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    """Enforcement hooks only run in a checkout whose ``.skm/project.json`` names this project."""
    detail = {
        "missing": "Checkout marker is missing: enforcement hooks deny every call (checkout_marker_missing)",
        "mismatch": "Checkout marker names another project or is unreadable (checkout_marker_mismatch)",
    }.get(ctx.checkout_marker or "")
    return finding(
        ctx,
        "projection.checkout_marker",
        "error" if ctx.enforcement_enabled else "warning",
        "Checkout marker matches the project",
        () if detail is None else ((".skm/project.json", detail),),
        "Run skm repo bind --write-marker in the checkout",
    )


def marker_digest(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    problems: list[tuple[str | None, str]] = []
    for path, raw in ctx.marker_files.items():
        markers = parse_markers(raw)
        ids = tuple(marker.block_id for marker in markers or () if marker.kind == "begin")
        if markers is None or extract_blocks(raw, ids) is None:
            problems.append((path, "Malformed managed block boundary"))
            continue
        for begin, end in zip(markers[::2], markers[1::2], strict=True):
            body = raw[begin.end : end.start].replace(b"\r\n", b"\n")
            if hashlib.sha256(body).hexdigest()[:12] != begin.digest:
                problems.append((path, "Managed block digest mismatch: " + begin.block_id))
    return finding(ctx, "projection.marker_digest", "warning", "Managed block digests match", problems)


def subscriptions_valid(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    violations = list(ctx.subscription_violations)
    for sub in ctx.subscriptions:
        violations.extend(
            validate_subscription(sub, hookable_types=ctx.hookable_types, sink_ids=ctx.sink_ids)
        )
    problems = [(violation.key, violation.reason) for violation in violations]
    problems.extend(
        ("hooks.subscriptions." + str(fact["id"]), "Subscription validation failed")
        for fact in ctx.subscription_facts
        if fact.get("valid") is not True
    )
    return finding(
        ctx,
        "hooks.subscriptions_valid",
        "error",
        "Hook subscriptions valid",
        problems,
    )


def _facts(ctx: DoctorContext) -> tuple[JsonObject, ...]:
    typed: tuple[JsonObject, ...] = tuple(
        {
            "id": sub.id,
            "enabled": sub.enabled,
            "execution_location": sub.execution_location.value,
            "class": sub.hook_class.value,
            "event_types": list(sub.event_types),
            "digest": sub.digest,
        }
        for sub in ctx.subscriptions
    )
    return typed + ctx.subscription_facts


def subscriptions_untrusted(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    results: list[CheckResult] = []
    for sub in _facts(ctx):
        if (
            sub["enabled"] is True
            and sub["execution_location"] == ExecutionLocation.HOST.value
            and (ctx.trusted.get(str(sub["id"])) != sub["digest"])
        ):
            level = "warning" if sub["class"] == HookClass.ENFORCEMENT.value else "info"
            results.extend(
                finding(
                    ctx,
                    "hooks.subscriptions_untrusted",
                    level,
                    "Host subscription trust",
                    [
                        (
                            "hooks.subscriptions." + str(sub["id"]),
                            "Enabled host subscription has no matching trusted digest",
                        )
                    ],
                    "Review and trust the subscription on this host",
                )
            )
    return tuple(results) or finding(
        ctx, "hooks.subscriptions_untrusted", "info", "Host subscription trust", ()
    )


def event_unsupported(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    problems: list[tuple[str | None, str]] = []
    for sub in _facts(ctx):
        if sub["enabled"] is not True or sub["execution_location"] != ExecutionLocation.HOST.value:
            continue
        for pattern in strings(sub["event_types"]):
            kinds = (
                set(HookEventKind)
                if pattern == "client:*"
                else {kind for kind in HookEventKind if pattern == "client:" + kind.value}
            )
            if kinds - ctx.supported_kinds:
                problems.append(
                    (
                        "hooks.subscriptions." + str(sub["id"]),
                        "Subscription requests a hook event unsupported by the target",
                    )
                )
    return finding(ctx, "hooks.event_unsupported", "warning", "Subscription events supported", problems)


CHECKS = (
    projection_drift,
    checkout_marker,
    marker_digest,
    subscriptions_valid,
    subscriptions_untrusted,
    event_unsupported,
)
