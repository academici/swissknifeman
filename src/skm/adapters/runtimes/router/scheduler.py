"""Select accounts and coordinate cooldowns for the local router."""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import TYPE_CHECKING, cast

from skm.adapters.runtimes.pool.failover import FailoverCandidate, FailoverController, FailoverPolicy
from skm.adapters.runtimes.pool.rate_limit import RateLimitAction, classify_rate_limit
from skm.modules.runtimes.public import SubagentUsage, UsageReport, UsageStatus
from skm.platform.system_clock import SystemClock

if TYPE_CHECKING:
    from collections.abc import Mapping
    from datetime import datetime

    from skm.adapters.runtimes.pool.provider_pool import ProviderSlot, SlotModel
    from skm.kernel.clock import Clock
    from skm.modules.runtimes.public import Pricing

__all__ = ["Route", "Scheduler", "failover_policy", "valid_success"]

type Conversation = tuple[str, str]


@dataclass(frozen=True, slots=True)
class Route:
    slot: ProviderSlot
    model: SlotModel
    hot_pool: bool = False


def valid_success(path: str, body: object) -> bool:
    if not isinstance(body, dict):
        return False
    match path, cast("dict[str, object]", body):
        case "/v1/messages/count_tokens", {"input_tokens": int(count)}:
            return type(count) is int and count >= 0
        case "/v1/messages", {"content": content}:
            return _nonempty_list(content)
        case "/v1/responses", {"output": output}:
            return _nonempty_list(output)
        case "/v1/chat/completions", {"choices": choices} if isinstance(choices, list):
            return any(_valid_choice(choice) for choice in cast("list[object]", choices))
        case _:
            return False


def _nonempty_list(value: object) -> bool:
    return isinstance(value, list) and len(cast("list[object]", value)) > 0


def _valid_choice(choice: object) -> bool:
    if not isinstance(choice, dict):
        return False
    message = cast("dict[str, object]", choice).get("message")
    if not isinstance(message, dict):
        return False
    fields = cast("dict[str, object]", message)
    content = fields.get("content")
    return (
        (isinstance(content, str) and bool(content.strip()))
        or _nonempty_list(content)
        or _nonempty_list(fields.get("tool_calls"))
    )


def failover_policy(table: Mapping[str, object]) -> FailoverPolicy:
    flags = {"enabled", "explicit_consent", "tos_acknowledged", "fresh_session"}
    ceiling = table.get("cost_ceiling_usd_micros")
    if (
        set(table) - flags - {"cost_ceiling_usd_micros"}
        or (ceiling is not None and (type(ceiling) is not int or ceiling < 0))
        or any(type(table.get(flag, False)) is not bool for flag in flags)
    ):
        raise ValueError("invalid failover policy")
    return FailoverPolicy(
        enabled=table.get("enabled") is True,
        explicit_consent=table.get("explicit_consent") is True,
        tos_acknowledged=table.get("tos_acknowledged") is True,
        fresh_session=table.get("fresh_session") is True,
        cost_ceiling_usd_micros=ceiling,
    )


class Scheduler:
    """One lock protects cooldown and sticky state. Callers perform waits outside it."""

    def __init__(self, policy: FailoverPolicy, hold_max_s: float, clock: Clock | None = None) -> None:
        self._failover = FailoverController(policy)
        self._hold_max_s = hold_max_s
        self._clock = clock or SystemClock()
        self._lock = Lock()
        self._cooldowns: dict[str, datetime] = {}
        self._held: dict[str, object] = {}
        self._sticky: OrderedDict[Conversation, str] = OrderedDict()

    def candidates(
        self,
        routes: tuple[Route, ...],
        conversation: Conversation | None,
        *,
        internal: bool,
    ) -> tuple[Route, ...]:
        with self._lock:
            pinned = self._sticky.get(conversation) if conversation is not None else None
            now = self._clock.now()
            eligible = (
                route
                for route in routes
                if (not internal or route.slot.transport != "cli_subprocess")
                and route.slot.slot_id not in self._held
                and self._cooldowns.get(route.slot.slot_id, now) <= now
            )
            return tuple(sorted(eligible, key=lambda route: (route.slot.slot_id != pinned, route.slot.tier)))

    def pin(self, conversation: Conversation | None, route: Route) -> None:
        if conversation is not None:
            with self._lock:
                self._sticky[conversation] = route.slot.slot_id
                self._sticky.move_to_end(conversation)
                if len(self._sticky) > 4096:
                    self._sticky.popitem(last=False)

    def eligible(self, route: Route, claim: object | None = None) -> bool:
        with self._lock:
            now = self._clock.now()
            slot = route.slot.slot_id
            owner = self._held.get(slot)
            return (owner is None or owner is claim) and self._cooldowns.get(slot, now) <= now

    def retry_delay(
        self,
        route: Route,
        headers: Mapping[str, str],
        message: str,
        attempt: int,
        waited: float,
        claim: object | None = None,
    ) -> float | None:
        with self._lock:
            decision = classify_rate_limit(
                429,
                now=self._clock.now(),
                headers=headers,
                message=message,
                attempt=attempt,
                total_wait_s=waited,
                burst_max_s=self._hold_max_s,
                max_total_wait_s=self._hold_max_s,
            )
            if decision is None:
                return None
            slot_id = route.slot.slot_id
            if decision.action == RateLimitAction.WAIT_SAME_SLOT:
                owner = self._held.get(slot_id)
                if owner is not None and owner is not claim:
                    return None
                if claim is not None:
                    self._held[slot_id] = claim
                return decision.wait_s
            if decision.cooldown_until is None:
                return None
            previous = self._cooldowns.get(slot_id, decision.cooldown_until)
            self._cooldowns[slot_id] = max(previous, decision.cooldown_until)
            return None

    def release_hold(self, route: Route, claim: object) -> None:
        with self._lock:
            slot = route.slot.slot_id
            if self._held.get(slot) is claim:
                del self._held[slot]

    def permits_floor(self, route: Route, pricing: Pricing | None, input_tokens: int, limit: int) -> bool:
        estimate = UsageReport(
            input_tokens,
            limit,
            None,
            None,
            None,
            None,
            UsageStatus.ESTIMATED,
            "router:request",
            SubagentUsage(False, True),
        )
        candidate = FailoverCandidate(route.slot, route.slot.runtime_id, pricing, estimate)
        return self._failover.route_local_proxy(candidate, consumed_host_private=False) is not None

    def cooldowns(self) -> dict[str, str]:
        with self._lock:
            now = self._clock.now()
            return {slot: until.isoformat() for slot, until in self._cooldowns.items() if until > now}
