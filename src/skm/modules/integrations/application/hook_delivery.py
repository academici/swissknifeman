"""Two-phase hook outbox consumer: configuration in UoW, external effects after it closes."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, cast

from skm.application_bus.context import ExternalConsumerContext, SubscriberContext
from skm.application_bus.ports import DeliveryPlan, GiveUp, OutboxItem, RetryAt, SendResult, Sent
from skm.application_bus.registry import ExternalConsumerSpec
from skm.kernel.cancel import CancelToken
from skm.kernel.errors import BackendUnavailable, CapabilityUnavailable
from skm.kernel.events import EventEnvelope
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeRef, ScopeRegistry
from skm.modules.integrations.domain.hook_subscriptions import (
    EventSinkTarget,
    ExecutionLocation,
    HookSubscription,
    WebhookTarget,
    effective_max_attempts,
    matches,
    next_attempt_at,
    subscription_json,
)
from skm.modules.integrations.generated.commands import RecordHookDeliveryFailure
from skm.platform.config.secrets import SecretRef

from .subscribers import (
    HOOK_TEST_REQUESTED_URN,
    _resolve_event_scope,  # pyright: ignore[reportPrivateUsage] - reuse the routing owner
    _visible_to_subscription,  # pyright: ignore[reportPrivateUsage] - reuse K-135 routing checks
    default_hookable_event_types,
    read_hook_subscriptions,
    registered_sink_ids,
)

__all__ = ["HOOK_CONSUMER", "HookDeliveryConsumer"]


@dataclass(frozen=True, slots=True)
class _Payload:
    subscription: HookSubscription
    envelope: EventEnvelope
    scope: ScopeRef
    delivery_id: str
    webhook_policy: dict[str, JsonValue]


class HookDeliveryConsumer:
    def __init__(self, context: ExternalConsumerContext) -> None:
        self._ctx = context

    def prepare(
        self, item: OutboxItem, envelope: EventEnvelope, ctx: SubscriberContext, uow: UnitOfWork
    ) -> DeliveryPlan | None:
        scope, config = _resolve_event_scope(envelope, ctx, uow)
        entries, _ = read_hook_subscriptions(
            config, hookable_types=default_hookable_event_types(), sink_ids=registered_sink_ids(config)
        )
        for sub, violations in entries:
            test = envelope.type == HOOK_TEST_REQUESTED_URN
            if (
                sub.id != item.destination.removeprefix("hook:")
                or violations
                or not sub.enabled
                or sub.execution_location is not ExecutionLocation.CONTROL_PLANE
                or (not test and not matches(sub, envelope.type))
                or (test and envelope.payload.get("subscription_id") != sub.id)
                or not _visible_to_subscription(sub, scope=scope, event=envelope)
            ):
                continue
            if scope is None:
                instance = uow.repo(ScopeRegistry).instance()
                scope = ScopeRef(instance.kind, instance.id)
            return DeliveryPlan(
                _Payload(
                    sub,
                    envelope,
                    scope,
                    str(item.id),
                    {
                        key: config.get("hooks.webhook." + key)
                        for key in ("allow_http_loopback", "allow_private_networks", "max_response_bytes")
                    },
                ),
                timeout_seconds=sub.timeout_ms / 1000,
                max_attempts=effective_max_attempts(sub),
            )
        ctx.log.info(
            "integrations.hook_subscription_gone", code="HOOK_SUBSCRIPTION_GONE", delivery_id=str(item.id)
        )
        return None

    def _resolve(self, value: JsonValue) -> JsonValue:
        if isinstance(value, str) and value.startswith("secret://"):
            secret = self._ctx.secrets.resolve(SecretRef.parse(value))
            reveal = getattr(secret, "reveal", None)
            return str(reveal()) if callable(reveal) else str(secret)
        if isinstance(value, dict):
            return {key: self._resolve(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve(item) for item in value]
        return value

    def send(
        self, plan: DeliveryPlan, *, attempt: int, timeout_seconds: float, cancel: CancelToken
    ) -> SendResult:
        cancel.raise_if_cancelled()
        payload = cast("_Payload", plan.payload)
        sub = payload.subscription
        if isinstance(sub.target, WebhookTarget):
            sink_id = "webhook"
        elif isinstance(sub.target, EventSinkTarget):
            sink_id = sub.target.sink_id
        else:
            return GiveUp("host_action_refused")
        try:
            sink = cast(
                "Any", self._ctx.gateways.named("skm.application_bus.subscribers.EventSinkRegistry")
            ).get(sink_id)
        except CapabilityUnavailable:
            return GiveUp("CAPABILITY_UNAVAILABLE")
        target = subscription_json(sub)["target"]
        if not isinstance(sub.target, WebhookTarget):
            target = cast("Mapping[str, JsonValue]", target).get("config", {})
        try:
            config = cast("dict[str, JsonValue]", self._resolve(target))
            config.update(
                delivery_id=payload.delivery_id,
                subscription_id=sub.id,
                attempt=attempt,
                timeout_ms=max(1, int(timeout_seconds * 1000)),
                _webhook_policy=payload.webhook_policy,
            )
            result = sink.deliver(payload.envelope, config)
        except BackendUnavailable:
            return RetryAt(
                next_attempt_at(sub.retry, attempt=attempt, now=self._ctx.clock.now(), jitter=1.0),
                "secret_backend_unavailable",
            )
        cancel.raise_if_cancelled()
        if result.ok:
            return Sent()
        if result.retryable:
            return RetryAt(
                next_attempt_at(
                    sub.retry,
                    attempt=attempt,
                    now=self._ctx.clock.now(),
                    jitter=1.0,
                    retry_after_ms=result.retry_after_ms,
                ),
                result.reason or "delivery_failed",
            )
        return GiveUp(result.reason or "delivery_failed")


def _on_dead(item: OutboxItem, plan: DeliveryPlan | None, error: str) -> object:
    if plan is None:
        return None
    payload = cast("_Payload", plan.payload)
    sub, envelope = payload.subscription, payload.envelope
    status = int(error[5:]) if error.startswith("http_") and error[5:].isdigit() else None
    return RecordHookDeliveryFailure.from_json(
        {
            "delivery_id": str(item.id),
            "subscription_id": sub.id,
            "subscription_digest": sub.digest,
            "event_id": str(envelope.id),
            "event_type": envelope.type,
            "class": sub.hook_class.value,
            "failure_policy": sub.failure_policy.value,
            "attempts": item.attempts,
            "reason": error,
            "status": status,
            "scope": {"kind": payload.scope.kind.value, "id": str(payload.scope.id)},
        }
    )


class _HookConsumerSpec(ExternalConsumerSpec):
    name = "hook"


HOOK_CONSUMER = _HookConsumerSpec(prefix="hook", factory=HookDeliveryConsumer, on_dead=_on_dead)
