"""Select explicitly authorized host routes before admitting a fresh runtime session."""

from collections.abc import Iterable
from dataclasses import dataclass, field

from skm.adapters.runtimes.pool.provider_pool import ProviderSlot
from skm.modules.execution.domain.session import Fresh
from skm.modules.runtimes.domain.ids import is_runtime_id
from skm.modules.runtimes.public import Pricing, UsageReport, cost

__all__ = ["FailoverCandidate", "FailoverController", "FailoverDecision", "FailoverPolicy"]


@dataclass(frozen=True, slots=True, kw_only=True)
class FailoverPolicy:
    enabled: bool = False
    explicit_consent: bool = False
    tos_acknowledged: bool = False
    cost_ceiling_usd_micros: int | None = None
    fresh_session: bool = False


@dataclass(frozen=True, slots=True)
class FailoverCandidate:
    """An eligible host slot, its canonical cloud ID, and its tariff and fresh-session usage estimate."""

    slot: ProviderSlot
    provider_id: str
    pricing: Pricing | None
    estimated_usage: UsageReport


@dataclass(frozen=True, slots=True)
class FailoverDecision:
    slot: ProviderSlot
    provider_id: str
    estimated_cost_usd_micros: int
    via_local_proxy: bool
    session: Fresh = field(init=False, default=Fresh("ROUTE_CHANGED", handoff=False))


class FailoverController:
    """Gate host-selected routes. The host supplies admission facts and acquires the selected slot."""

    def __init__(self, policy: FailoverPolicy | None = None) -> None:
        self._policy = policy if policy is not None else FailoverPolicy()

    def select_failover(
        self,
        candidates: Iterable[FailoverCandidate],
        *,
        source_provider_id: str,
        http_status: int | None,
        is_quota_exhausted: bool = False,
        consumed_host_private: bool | None = None,
    ) -> FailoverDecision | None:
        """Select the first eligible, affordable slot on another cloud after overload or quota exhaustion."""
        ceiling = self._routing_ceiling(consumed_host_private)
        if ceiling is None or type(http_status) is not int:
            return None
        if http_status != 529 and (http_status != 429 or is_quota_exhausted is not True):
            return None
        if not is_runtime_id(source_provider_id):
            return None
        for candidate in candidates:
            if candidate.provider_id == source_provider_id:
                continue
            decision = self._price_route(candidate, ceiling, via_local_proxy=False)
            if decision is not None:
                return decision
        return None

    def route_local_proxy(
        self, proxy: FailoverCandidate, *, consumed_host_private: bool | None = None
    ) -> FailoverDecision | None:
        """Approve the host's configured local proxy slot under the same routing gates."""
        ceiling = self._routing_ceiling(consumed_host_private)
        if ceiling is None:
            return None
        return self._price_route(proxy, ceiling, via_local_proxy=True)

    def _routing_ceiling(self, consumed_host_private: bool | None) -> int | None:
        policy = self._policy
        ceiling = policy.cost_ceiling_usd_micros
        if (
            policy.enabled is True
            and policy.explicit_consent is True
            and policy.tos_acknowledged is True
            and policy.fresh_session is True
            and consumed_host_private is False
            and type(ceiling) is int
            and ceiling >= 0
        ):
            return ceiling
        return None

    @staticmethod
    def _price_route(
        candidate: FailoverCandidate, ceiling: int, *, via_local_proxy: bool
    ) -> FailoverDecision | None:
        if not is_runtime_id(candidate.provider_id):
            return None
        estimate = cost(candidate.estimated_usage, candidate.pricing)
        if estimate is None or estimate > ceiling:
            return None
        return FailoverDecision(candidate.slot, candidate.provider_id, estimate, via_local_proxy)
