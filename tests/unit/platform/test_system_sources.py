"""System clock, monotonic, entropy and UUIDv7 sources, plus the deterministic fakes used in their place."""

import builtins
import itertools
import os
import threading
import time
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from uuid import RFC_4122, UUID

import pytest

from fakes.clock import FakeMonotonic, FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.kernel.clock import Clock, Monotonic
from skm.kernel.entropy import EntropySource
from skm.kernel.id_generator import IdGenerator
from skm.kernel.ids import UUID7_MAX_RAND_A, uuid7_timestamp_ms
from skm.platform.system_clock import SystemClock, SystemMonotonic
from skm.platform.system_entropy import SystemEntropy
from skm.platform.system_ids import Uuid7Generator

EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


def _ms(moment: datetime) -> int:
    return (moment - EPOCH) // timedelta(milliseconds=1)


def test_system_clock_is_timezone_aware_utc() -> None:
    clock: Clock = SystemClock()
    before = time.time()
    now = clock.now()
    after = time.time()
    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
    assert before - 1 <= now.timestamp() <= after + 1


def test_system_monotonic_never_goes_back() -> None:
    source: Monotonic = SystemMonotonic()
    readings = [source.monotonic() for _ in range(100)]
    assert readings == sorted(readings)
    assert all(isinstance(value, float) for value in readings)


def test_system_entropy_reads_os_urandom(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def fake_urandom(n: int) -> bytes:
        calls.append(n)
        return b"\x07" * n

    monkeypatch.setattr(os, "urandom", fake_urandom)
    source: EntropySource = SystemEntropy()
    assert source.bytes(5) == b"\x07" * 5
    assert calls == [5]


@pytest.mark.parametrize("size", [0, 1, 16, 32, 1000])
def test_system_entropy_returns_the_requested_length(size: int) -> None:
    data = SystemEntropy().bytes(size)
    assert isinstance(data, bytes)
    assert len(data) == size


def test_system_entropy_calls_differ() -> None:
    source = SystemEntropy()
    assert len({source.bytes(32) for _ in range(20)}) == 20


def test_system_entropy_rejects_bad_sizes() -> None:
    source = SystemEntropy()
    with pytest.raises(ValueError, match=">= 0"):
        source.bytes(-1)
    for bad in (True, 1.5, "8"):
        wrong: Any = bad
        with pytest.raises(TypeError):
            source.bytes(wrong)


def test_uuid7_generator_default_entropy_is_the_system_source() -> None:
    generator: IdGenerator = Uuid7Generator(SystemClock())
    first, second = generator.new_id(), generator.new_id()
    assert first.version == 7
    assert second > first


def test_ten_thousand_ids_strictly_increase_with_the_real_clock() -> None:
    generator = Uuid7Generator(SystemClock(), SystemEntropy())
    ids = [generator.new_id() for _ in range(10_000)]
    assert all(left < right for left, right in itertools.pairwise(ids))
    assert len(set(ids)) == len(ids)


def test_id_layout_is_rfc_9562_v7() -> None:
    clock = FrozenClock(datetime(2026, 3, 4, 5, 6, 7, 891_999, tzinfo=UTC))
    value = Uuid7Generator(clock, DeterministicEntropy()).new_id()
    assert value.version == 7
    assert value.variant == RFC_4122
    assert uuid7_timestamp_ms(value) == _ms(clock.now())
    assert (value.int >> 64) & 0xFFF <= UUID7_MAX_RAND_A >> 1


def test_clock_rollback_does_not_break_monotonicity() -> None:
    clock = FrozenClock()
    generator = Uuid7Generator(clock, DeterministicEntropy())
    first = generator.new_id()
    clock.advance(timedelta(seconds=-60))
    after_rollback = [generator.new_id() for _ in range(50)]
    ids = [first, *after_rollback]
    assert all(left < right for left, right in itertools.pairwise(ids))
    assert {uuid7_timestamp_ms(item) for item in after_rollback} == {uuid7_timestamp_ms(first)}
    clock.advance(timedelta(seconds=120))
    recovered = generator.new_id()
    assert recovered > ids[-1]
    assert uuid7_timestamp_ms(recovered) == _ms(clock.now())


def test_counter_overflow_advances_the_timestamp_and_stays_increasing() -> None:
    clock = FrozenClock()
    generator = Uuid7Generator(clock, DeterministicEntropy(b"overflow"))
    ids = [generator.new_id() for _ in range(UUID7_MAX_RAND_A + 200)]
    assert all(left < right for left, right in itertools.pairwise(ids))
    start = _ms(clock.now())
    stamps = [uuid7_timestamp_ms(item) for item in ids]
    assert stamps[0] == start
    assert stamps[-1] > start
    assert stamps == sorted(stamps)


def test_generator_is_thread_safe() -> None:
    generator = Uuid7Generator(SystemClock(), SystemEntropy())
    buckets: list[list[UUID]] = [[] for _ in range(8)]

    def work(bucket: list[UUID]) -> None:
        bucket.extend(generator.new_id() for _ in range(500))

    threads = [threading.Thread(target=work, args=(bucket,)) for bucket in buckets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    everything = [item for bucket in buckets for item in bucket]
    assert len(set(everything)) == len(everything) == 4000
    assert all(bucket == sorted(bucket) for bucket in buckets)


def test_randomness_comes_only_from_the_injected_entropy() -> None:
    clock = FrozenClock()
    left_entropy, right_entropy = DeterministicEntropy(b"left"), DeterministicEntropy(b"right")
    left = [Uuid7Generator(clock, left_entropy).new_id() for _ in range(3)]
    again = DeterministicEntropy(b"left")
    assert [Uuid7Generator(FrozenClock(), again).new_id() for _ in range(3)] == left
    right = [Uuid7Generator(FrozenClock(), right_entropy).new_id() for _ in range(3)]
    assert left != right
    assert set(left_entropy.requested) == {2, 8}


def test_a_short_entropy_read_is_rejected() -> None:
    class Short:
        def bytes(self, n: int) -> builtins.bytes:
            return b"\x00" * (n - 1)

    with pytest.raises(ValueError, match="expected"):
        Uuid7Generator(FrozenClock(), Short()).new_id()


def test_naive_clock_is_rejected() -> None:
    class Naive:
        def now(self) -> datetime:
            return datetime(2026, 1, 1)  # noqa: DTZ001 - the point of the test

    with pytest.raises(ValueError, match="timezone-aware"):
        Uuid7Generator(Naive(), DeterministicEntropy()).new_id()


def test_the_id_generator_is_not_a_csprng() -> None:
    ids = SequentialIds()
    assert not hasattr(ids, "bytes"), "an IdGenerator must not be usable as an EntropySource"
    assert not hasattr(Uuid7Generator(SystemClock()), "bytes")
    assert not hasattr(SystemClock(), "bytes")
    first, second = ids.new_id(), ids.new_id()
    assert second.int - first.int == 1, "fake ids are predictable and therefore never secrets"


def test_sequential_ids_are_unique_and_increasing() -> None:
    ids = SequentialIds()
    values = [ids.new_id() for _ in range(100)]
    assert values == sorted(values)
    assert len(set(values)) == 100
    assert all(item.version == 7 for item in values)
    assert next(SequentialIds().new_id() for _ in range(2)) == values[0]


def test_frozen_clock_accepts_only_utc() -> None:
    with pytest.raises(ValueError, match="UTC"):
        FrozenClock(datetime(2026, 1, 1))  # noqa: DTZ001 - naive on purpose
    with pytest.raises(ValueError, match="UTC"):
        FrozenClock(datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=3))))
    clock = FrozenClock()
    assert clock.now() == clock.now()
    clock.advance(timedelta(seconds=1, microseconds=5))
    assert clock.now().microsecond == 123461
    clock.set(datetime(2030, 1, 1, tzinfo=UTC))
    assert clock.now().year == 2030


def test_fake_monotonic_only_moves_forward() -> None:
    source = FakeMonotonic(10.0)
    source.advance(2.5)
    assert source.monotonic() == 12.5
    with pytest.raises(ValueError, match="backwards"):
        source.advance(-1)


def test_deterministic_entropy_is_repeatable_and_never_repeats_itself() -> None:
    first, second = DeterministicEntropy(), DeterministicEntropy()
    assert first.bytes(70) == second.bytes(70)
    assert len(first.bytes(0)) == 0
    assert first.bytes(32) != first.bytes(32)
    with pytest.raises(ValueError, match=">= 0"):
        first.bytes(-1)
