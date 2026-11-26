"""Wrapper-owned frozen observations and bounded, nonblocking live enqueue."""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from skm.modules.runtimes.domain.observation import (
    OBSERVATION_SCHEMA,
    CaptureObservation,
    ObservationBinding,
    ObservationTiming,
    RuntimeObservation,
    ToolVisibility,
    canonical_observation_bytes,
    validate_runtime_observation,
)

if TYPE_CHECKING:
    from skm.modules.runtimes.domain.classes import Effort

__all__: list[str] = []

MAX_COUNTER = 2**63 - 1


class LiveQueue:
    """The network consumer owns delivery and deadlines; capture only calls offer()."""

    def __init__(self, *, max_bytes: int, max_entries: int = 256) -> None:
        if max_bytes <= 0 or max_entries <= 0:
            raise ValueError("live queue needs finite positive ceilings")
        self.max_bytes, self.max_entries = max_bytes, max_entries
        self.dropped = 0
        self.bytes_queued = 0
        self._queue: deque[bytes] = deque()
        self._lock = threading.Lock()

    def offer(self, message: bytes) -> bool:
        if not self._lock.acquire(blocking=False):
            self.dropped = min(MAX_COUNTER, self.dropped + 1)
            return False
        try:
            if len(self._queue) >= self.max_entries or len(message) > self.max_bytes - self.bytes_queued:
                self.dropped = min(MAX_COUNTER, self.dropped + 1)
                return False
            self._queue.append(message)
            self.bytes_queued += len(message)
            return True
        finally:
            self._lock.release()

    def take(self) -> bytes | None:
        with self._lock:
            if not self._queue:
                return None
            message = self._queue.popleft()
            self.bytes_queued -= len(message)
            return message


@dataclass
class ObservationCapture:
    request_id: UUID
    binding: ObservationBinding
    started: float
    clock_domain_id: UUID = field(default_factory=uuid4)
    bytes_seen: int = 0
    bytes_retained: int = 0
    first_at: datetime | None = None
    last_at: datetime | None = None
    flags: set[str] = field(default_factory=set[str])
    gaps: set[str] = field(default_factory=set[str])
    truncated: bool = False
    _native_seq: int | None = None
    _frozen: RuntimeObservation | None = None

    def ingress(self, size: int, retained: int, at: datetime) -> None:
        self.first_at = self.first_at or at
        self.last_at = at
        self.bytes_seen = min(MAX_COUNTER, self.bytes_seen + size)
        self.bytes_retained = min(MAX_COUNTER, self.bytes_retained + retained)

    def native_sequence(self, seq: int | None) -> None:
        if seq is None:
            return
        if self._native_seq is not None and seq > self._native_seq + 1:
            self.gaps.add("provider_sequence_gap")
        self._native_seq = seq if self._native_seq is None else max(seq, self._native_seq)

    def freeze(
        self,
        *,
        ended: float | None,
        model: str | None,
        observed_effort: Effort | None = None,
        live_dropped: int = 0,
        tools: ToolVisibility | None = None,
    ) -> RuntimeObservation:
        if self._frozen is not None:
            return self._frozen
        if live_dropped:
            self.gaps.add("live_delivery_gap")
        dropped = self.bytes_seen - self.bytes_retained
        partial = bool(self.flags or dropped or self.truncated or self.gaps - {"live_delivery_gap"})
        value = RuntimeObservation(
            OBSERVATION_SCHEMA,
            self.request_id,
            replace(
                self.binding,
                provider_reported_model=model,
                model_source="unavailable" if model is None else "provider_stream",
                observed_effort=observed_effort,
            ),
            ObservationTiming(
                self.clock_domain_id,
                None if ended is None else max(0, int((ended - self.started) * 1000)),
                self.first_at,
                self.last_at,
            ),
            CaptureObservation(
                "partial" if partial else "complete",
                self.bytes_seen,
                self.bytes_retained,
                dropped,
                self.truncated or bool(dropped),
                tuple(sorted(self.gaps)),
                tuple(sorted(self.flags)),
                live_dropped,
            ),
            tools if tools is not None else ToolVisibility("unavailable", None),
        )
        if validate_runtime_observation(value, request_id=self.request_id, provider_reported_model=model):
            raise ValueError("invalid runtime observation facts")
        if len(canonical_observation_bytes(value)) > 16_384:
            raise ValueError("runtime observation ceiling")
        self._frozen = value
        return value
