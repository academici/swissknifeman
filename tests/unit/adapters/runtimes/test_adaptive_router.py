from dataclasses import replace
from pathlib import Path

from skm.adapters.runtimes.pool import (
    AdaptiveExecutorRouter,
    ProviderPoolManager,
    ProviderSlot,
    QuotaGroup,
    QuotaProber,
    QuotaReply,
)
from skm.modules.runtimes.domain.capability import Capability


def test_static_weights_rank_only_admitted_slots_with_usable_quota(tmp_path: Path) -> None:
    groups = tuple(QuotaGroup(str(i)) for i in range(6))
    slots = tuple(
        ProviderSlot(runtime, slot)
        for runtime, slot in [
            ("light", "light-a"),
            ("heavy", "b"),
            ("heavy", "a"),
            ("banned", "banned"),
            ("missing", "missing"),
            ("busy", "busy"),
            ("limited", "limited"),
            ("downgraded", "fallback"),
            ("unknown", "unknown"),
            ("poor", "poor"),
            ("heavy", "rate"),
        ]
    )
    weights = {s.runtime_id: 100 for s in slots} | {"heavy": 10, "light": 5}
    router = AdaptiveExecutorRouter(weights)
    weights["light"] = 1000
    need = {Capability.STRUCTURED_RESULT}
    capabilities = {s.runtime_id: need for s in slots} | {"missing": set()}
    allowed = set(capabilities) - {"banned"}

    def transport(slot: ProviderSlot, group: QuotaGroup) -> QuotaReply | None:
        if group == groups[1]:
            return {
                "limited": QuotaReply(200, 0),
                "rate": QuotaReply(429, 99),
                "unknown": None,
                "poor": QuotaReply(200, 1),
            }.get(slot.slot_id, QuotaReply(200, 10))
        return QuotaReply(200, 19)

    prober = QuotaProber(groups, transport)
    readings = [
        replace(row, opus_fallback=True) if row.slot.runtime_id == "downgraded" else row
        for s in slots
        for row in prober.probe(s)
    ]

    def rank(order):
        return router.rank(
            order,
            group_id="1",
            allowed=allowed,
            available_slots=set(slots) - {slots[5]},
            capabilities=capabilities,
            required=need,
            minimum_remaining=2,
        )

    ranked = rank(readings)
    assert ranked == rank(reversed(readings)) == (slots[2], slots[1], slots[0])
    pool = ProviderPoolManager(tmp_path / "pool", slots)
    assert pool.acquire(slots[2].slot_id, "other", ttl_seconds=60) is not None
    lease = pool.acquire_ranked(ranked, "step", ttl_seconds=60)
    assert lease is not None
    assert lease.slot == slots[1]
    assert (
        router.rank(
            readings,
            group_id="1",
            allowed=set(),
            available_slots=set(slots),
            capabilities=capabilities,
            required=need,
        )
        == ()
    )
