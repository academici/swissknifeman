"""Read independent quota groups for one account using a host-supplied transport."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from skm.adapters.runtimes.pool.provider_pool import ProviderSlot
    from skm.modules.runtimes.domain.observation import RuntimeObservation

__all__ = ["QuotaGroup", "QuotaProber", "QuotaReading", "QuotaReply", "opus_fallback"]

type QuotaState = Literal[
    "available", "exhausted", "payment_required", "rate_limited", "overloaded", "unknown"
]

# Covers CLI aliases and qualified/versioned model IDs, including Bedrock's dotted identifiers.
_OPUS = re.compile(r"(?:^|[.:/])(?:claude-(?:[0-9.]+-)?)?opus(?:$|[-.:@\[])", re.IGNORECASE)


def opus_fallback(requested: str, observation: RuntimeObservation | None) -> bool | None:
    """None means the provider did not identify the model used for an Opus request."""
    if not _OPUS.search(requested.rsplit("/", 1)[-1]):
        return False
    if observation is None or observation.binding.model_source != "provider_stream":
        return None
    reported = observation.binding.provider_reported_model
    if not reported or reported.casefold() in {"unknown", "default", "auto", "latest"}:
        return None
    return not bool(_OPUS.search(reported.rsplit("/", 1)[-1]))


@dataclass(frozen=True, slots=True)
class QuotaGroup:
    group_id: str
    requested_model: str = ""


@dataclass(frozen=True, slots=True)
class QuotaReply:
    """Normalized transport response. Only a local runtime wrapper may supply an observation."""

    http_status: int
    remaining: int | None = None
    observation: RuntimeObservation | None = None


@dataclass(frozen=True, slots=True)
class QuotaReading:
    slot: ProviderSlot
    group: QuotaGroup
    state: QuotaState
    remaining: int | None = None
    reported_model: str | None = None
    opus_fallback: bool | None = None


class QuotaProber:
    def __init__(
        self,
        groups: Sequence[QuotaGroup],
        transport: Callable[[ProviderSlot, QuotaGroup], QuotaReply | None],
        *,
        required_groups: int | None = 6,
    ) -> None:
        self.groups = tuple(groups)
        ids = {group.group_id for group in self.groups}
        if required_groups is not None and len(self.groups) != required_groups:
            raise ValueError("expected six distinct named quota groups")
        if len(ids) != len(self.groups) or any(not name.strip() for name in ids):
            message = (
                "expected distinct named quota groups"
                if required_groups is None
                else "expected six distinct named quota groups"
            )
            raise ValueError(message)
        self._transport = transport

    def probe(self, slot: ProviderSlot) -> tuple[QuotaReading, ...]:
        return tuple(self._read(slot, group) for group in self.groups)

    def _read(self, slot: ProviderSlot, group: QuotaGroup) -> QuotaReading:
        try:
            reply = self._transport(slot, group)
        except OSError:
            reply = None
        if reply is None:
            return QuotaReading(slot, group, "unknown")
        state: QuotaState = "unknown"
        remaining = None
        if reply.http_status == 402:
            state = "payment_required"
        elif reply.http_status == 429:
            state = "rate_limited"
        elif reply.http_status == 529:
            state = "overloaded"
        elif 200 <= reply.http_status < 300 and type(reply.remaining) is int and reply.remaining >= 0:
            remaining = reply.remaining
            state = "exhausted" if remaining == 0 else "available"
        observation = reply.observation
        if observation is not None and observation.binding.runtime_id != slot.runtime_id:
            return QuotaReading(slot, group, "unknown")
        reported = (
            observation.binding.provider_reported_model
            if observation is not None and observation.binding.model_source == "provider_stream"
            else None
        )
        return QuotaReading(
            slot, group, state, remaining, reported, opus_fallback(group.requested_model, observation)
        )
