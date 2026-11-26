"""Outbox fan-out subscriber of the ``integrations`` module (integrations §5.8.2, §10)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache
from typing import TYPE_CHECKING, Final, cast
from uuid import UUID

from skm.application_bus.registry import SubscriberSpec
from skm.kernel.errors import NotFound
from skm.kernel.ids import ProjectId, ScopeId
from skm.kernel.json_types import JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.integrations.domain.events import HookTestRequested
from skm.modules.integrations.domain.hook_subscriptions import (
    ExecutionLocation,
    HookSubscription,
    ScopeLevel,
    Violation,
    matches,
    parse_subscriptions,
    validate_subscription,
)
from skm.modules.workspace import public as workspace
from skm.platform.config.merge import is_unset_marker
from skm.platform.schema.registry import SchemaRegistry

if TYPE_CHECKING:
    from skm.application_bus.context import SubscriberContext
    from skm.kernel.events import EventEnvelope
    from skm.kernel.ports_uow import UnitOfWork
    from skm.platform.config.effective import EffectiveConfig

__all__ = [
    "CONSUMER_ID",
    "DEFAULT_FANOUT_LIMIT",
    "HOOK_TEST_REQUESTED_URN",
    "SPEC",
    "SUBSCRIBERS",
    "HookSubscriptionsValidator",
    "default_hookable_event_types",
    "default_subscribed_event_types",
    "fan_out_hook_deliveries",
    "fanout_limit",
    "read_hook_subscriptions",
    "registered_sink_ids",
    "subscriber_for",
]

CONSUMER_ID: Final = "integrations.fan_out_hook_deliveries"
HOOK_TEST_REQUESTED_URN: Final = HookTestRequested.event_type

# Modules always present in any BusRegistry that includes ``integrations`` (self + dependency closure).
_DEPENDENCY_CLOSURE_MODULES: Final = frozenset(
    {
        "access",
        "settings",
        "workspace",
        "artifacts",
        "policy",
        "extensions",
        "runtimes",
        "integrations",
    }
)


DEFAULT_FANOUT_LIMIT = 32


@lru_cache(maxsize=1)
def _default_hookable() -> frozenset[str]:
    schemas = SchemaRegistry.load_default()
    return frozenset(urn for urn in schemas.urns() if schemas.get(urn).get("x-skm-hookable") is True)


def default_hookable_event_types(schemas: SchemaRegistry | None = None) -> frozenset[str]:
    """All event type URNs marked ``"x-skm-hookable": true`` in the schema registry."""
    if schemas is None:
        return _default_hookable()
    return frozenset(urn for urn in schemas.urns() if schemas.get(urn).get("x-skm-hookable") is True)


@dataclass(frozen=True, slots=True)
class HookSubscriptionsValidator:
    """The immutable registry snapshot shared by config writes and resilient subscription reads."""

    hookable_types: frozenset[str]
    sink_ids: frozenset[str]

    def __call__(self, values: Mapping[str, JsonValue]) -> str | None:
        value = values["hooks.subscriptions"]
        if value is None:
            return None
        if not isinstance(value, Mapping):
            return "hooks.subscriptions must be an object"
        subscriptions, violations = parse_subscriptions(cast("Mapping[str, JsonValue]", value), {})
        problems = [*violations]
        for subscription in subscriptions:
            problems.extend(
                validate_subscription(
                    subscription, hookable_types=self.hookable_types, sink_ids=self.sink_ids
                )
            )
        if not problems:
            return None
        return "; ".join(f"{item.key}: {item.reason} ({item.message})" for item in problems)


def registered_sink_ids(config: EffectiveConfig) -> frozenset[str]:
    """Use the same admitted sink snapshot as this effective config's write validator."""
    validator = config.registry.validator("integrations.hook_subscriptions")
    return validator.sink_ids if isinstance(validator, HookSubscriptionsValidator) else frozenset()


def fanout_limit(config: EffectiveConfig) -> int:
    """Effective ``hooks.fanout.max_subscriptions_per_event`` without failing on sibling key errors."""
    res = config.resolution("hooks.fanout.max_subscriptions_per_event")
    if (
        res.present
        and isinstance(res.value, int)
        and not isinstance(res.value, bool)
        and 1 <= res.value <= 128
    ):
        return res.value
    return DEFAULT_FANOUT_LIMIT


def _provenance_map(config: EffectiveConfig) -> dict[str, ScopeLevel]:
    resolution = config.resolution("hooks.subscriptions")
    provenance: dict[str, ScopeLevel] = {}
    for step in resolution.trace:
        if step.status not in ("used", "winner"):
            continue
        if step.contribution.op == "unset":
            provenance.clear()
            continue
        level_name = step.contribution.layer.level.value
        level: ScopeLevel = (
            cast("ScopeLevel", level_name)
            if level_name in ("instance", "workspace", "project")
            else "instance"
        )
        raw_val = step.contribution.value
        if isinstance(raw_val, Mapping):
            for sub_id, sub_raw in raw_val.items():
                if is_unset_marker(sub_raw):
                    provenance.pop(sub_id, None)
                elif isinstance(sub_raw, Mapping):
                    provenance[sub_id] = level
    return provenance


def read_hook_subscriptions(
    config: EffectiveConfig,
    *,
    hookable_types: frozenset[str],
    sink_ids: frozenset[str],
) -> tuple[tuple[tuple[HookSubscription, tuple[Violation, ...]], ...], tuple[Violation, ...]]:
    """Read and validate stored ``hooks.subscriptions`` resiliently (integrations §5.8.1).

    Reads ``config.resolution("hooks.subscriptions")`` directly so a broken sibling entry never
    raises ``CONFIG_INVALID`` on read paths; callers inspect per-subscription and parse violations.
    """
    resolution = config.resolution("hooks.subscriptions")
    if not resolution.present or resolution.value is None:
        return (), ()
    if not isinstance(resolution.value, Mapping):
        return (
            (),
            (
                Violation(
                    key="hooks.subscriptions",
                    reason="not_an_object",
                    message="hooks.subscriptions must be an object",
                ),
            ),
        )
    provenance = _provenance_map(config)
    parsed, parse_violations = parse_subscriptions(
        cast("Mapping[str, JsonValue]", resolution.value),
        provenance,
    )
    entries = tuple(
        (sub, validate_subscription(sub, hookable_types=hookable_types, sink_ids=sink_ids)) for sub in parsed
    )
    return entries, parse_violations


def _resolve_event_scope(
    event: EventEnvelope,
    ctx: SubscriberContext,
    uow: UnitOfWork,
) -> tuple[ScopeRef | None, EffectiveConfig]:
    raw_project_id = event.payload.get("project_id")
    if isinstance(raw_project_id, str):
        try:
            parsed = UUID(raw_project_id)
        except ValueError:
            parsed = None
        if parsed is not None:
            try:
                project = workspace.get_project(uow, ProjectId(parsed))
            except NotFound:
                project = None
            if project is not None and (
                event.workspace_id is None or project.workspace_id == event.workspace_id
            ):
                project_scope = ScopeRef(ScopeKind.PROJECT, ScopeId(parsed))
                try:
                    return project_scope, ctx.config_for(project_scope)
                except NotFound:
                    pass
    if event.workspace_id is not None:
        return ScopeRef(ScopeKind.WORKSPACE, ScopeId(event.workspace_id)), ctx.config
    return None, ctx.config


def _visible_to_subscription(
    sub: HookSubscription,
    *,
    scope: ScopeRef | None,
    event: EventEnvelope,
) -> bool:
    """Enforce K-135 visibility rules for ``defined_at`` (integrations §5.8.2 step 5)."""
    if sub.defined_at == "project":
        return scope is not None and scope.kind is ScopeKind.PROJECT
    if sub.defined_at == "workspace":
        return event.workspace_id is not None
    return True


def fan_out_hook_deliveries(event: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork) -> None:
    """Enqueue ``hook:<id>`` outbox rows for matching control-plane subscriptions (§5.8.2)."""
    hookable = default_hookable_event_types()
    is_test = event.type == HOOK_TEST_REQUESTED_URN
    if not is_test and event.type not in hookable:
        return

    scope, cfg = _resolve_event_scope(event, ctx, uow)
    entries, parse_violations = read_hook_subscriptions(
        cfg,
        hookable_types=hookable,
        sink_ids=registered_sink_ids(cfg),
    )
    for violation in parse_violations:
        ctx.log.warning(
            "integrations.hook_subscription_invalid",
            code="HOOK_SUBSCRIPTION_INVALID",
            key=violation.key,
            reason=violation.reason,
            event_id=str(event.id),
        )

    valid: list[HookSubscription] = []
    for sub, violations in entries:
        if violations:
            for violation in violations:
                ctx.log.warning(
                    "integrations.hook_subscription_invalid",
                    code="HOOK_SUBSCRIPTION_INVALID",
                    subscription_id=sub.id,
                    key=violation.key,
                    reason=violation.reason,
                    event_id=str(event.id),
                )
            continue
        valid.append(sub)

    if is_test:
        target_sub_id = event.payload.get("subscription_id")
        matched = [
            sub
            for sub in valid
            if sub.id == target_sub_id and sub.execution_location is ExecutionLocation.CONTROL_PLANE
        ]
    else:
        matched = [
            sub
            for sub in valid
            if sub.enabled
            and sub.execution_location is ExecutionLocation.CONTROL_PLANE
            and matches(sub, event.type)
        ]

    visible = [sub for sub in matched if _visible_to_subscription(sub, scope=scope, event=event)]
    visible.sort(key=lambda item: item.id)

    limit = fanout_limit(cfg)
    if len(visible) > limit:
        ctx.log.error(
            "integrations.hook_fanout_limit",
            code="HOOK_FANOUT_LIMIT",
            event_id=str(event.id),
            event_type=event.type,
            matched=len(visible),
            limit=limit,
        )
        visible = visible[:limit]

    now = ctx.clock.now()
    for sub in visible:
        uow.outbox.enqueue(event_id=event.id, destination=f"hook:{sub.id}", available_at=now)


def subscriber_for(event_types: Iterable[str]) -> SubscriberSpec:
    """Build ``integrations.fan_out_hook_deliveries`` bound to ``event_types`` plus ``HookTestRequested``."""
    return SubscriberSpec(
        consumer_id=CONSUMER_ID,
        event_types=frozenset((*event_types, HOOK_TEST_REQUESTED_URN)),
        handler=fan_out_hook_deliveries,
    )


def default_subscribed_event_types() -> frozenset[str]:
    """Hookable event URNs of ``integrations`` and its dependency closure, plus ``HookTestRequested``."""
    hookable = {
        urn
        for urn in default_hookable_event_types()
        if len(urn.split(":")) >= 3 and urn.split(":")[2] in _DEPENDENCY_CLOSURE_MODULES
    }
    return frozenset((*hookable, HOOK_TEST_REQUESTED_URN))


SPEC = SubscriberSpec(
    consumer_id=CONSUMER_ID,
    event_types=default_subscribed_event_types(),
    handler=fan_out_hook_deliveries,
)

SUBSCRIBERS: tuple[SubscriberSpec, ...] = (SPEC,)
