"""Rank available account slots using static provider weights and current probe evidence."""

from collections.abc import Iterable, Mapping, Set

from skm.adapters.runtimes.pool.provider_pool import ProviderSlot
from skm.adapters.runtimes.pool.quota_prober import QuotaReading
from skm.modules.runtimes.domain.capability import Capability

__all__ = ["AdaptiveExecutorRouter"]


class AdaptiveExecutorRouter:
    def __init__(self, weights: Mapping[str, int]) -> None:
        self._weights = dict(weights)
        if any(type(weight) is not int or weight < 0 for weight in self._weights.values()):
            raise ValueError("provider weights must be nonnegative integers")

    def rank(
        self,
        snapshots: Iterable[QuotaReading],
        *,
        group_id: str,
        allowed: Set[str],
        available_slots: Set[ProviderSlot],
        capabilities: Mapping[str, Set[Capability]],
        required: Set[Capability],
        minimum_remaining: int = 1,
    ) -> tuple[ProviderSlot, ...]:
        """Rank known capacity for one group. The caller still acquires the selected slot's lease."""
        if minimum_remaining < 1:
            raise ValueError("minimum remaining quota must be positive")
        eligible: set[ProviderSlot] = set()
        seen: set[ProviderSlot] = set()
        for reading in snapshots:
            if reading.group.group_id != group_id:
                continue
            slot = reading.slot
            if slot in seen:
                raise ValueError("multiple quota readings for the same slot and group")
            seen.add(slot)
            if (
                slot in available_slots
                and slot.runtime_id in allowed
                and slot.runtime_id in capabilities
                and required <= capabilities[slot.runtime_id]
                and reading.state == "available"
                and reading.remaining is not None
                and reading.remaining >= minimum_remaining
                and reading.opus_fallback is not True
            ):
                eligible.add(slot)
        return tuple(
            sorted(eligible, key=lambda s: (-self._weights.get(s.runtime_id, 0), s.runtime_id, s.slot_id))
        )
