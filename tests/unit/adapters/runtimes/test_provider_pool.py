from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from pathlib import Path
from threading import Barrier, Event

import pytest

from fakes.clock import FrozenClock
from skm.adapters.runtimes.pool import ProviderPoolManager, ProviderSlot
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, PreconditionFailed
from skm.platform.fs.atomic_write import atomic_write

_CODEX = ProviderSlot("codex", "a")
_OTHER_CODEX = ProviderSlot("codex", "b")


def test_one_owner_wins_contention_and_can_release(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    first = ProviderPoolManager(root, [_CODEX])
    second = ProviderPoolManager(root, [_CODEX])
    start = Barrier(2)

    def acquire(pool: ProviderPoolManager, owner: str):
        start.wait(timeout=5)
        return pool.acquire("a", owner, ttl_seconds=60)

    with ThreadPoolExecutor(max_workers=2) as threads:
        a = threads.submit(acquire, first, "step-a")
        b = threads.submit(acquire, second, "step-b")
        contenders = (a.result(timeout=5), b.result(timeout=5))

    (winner,) = [lease for lease in contenders if lease is not None]
    assert first.acquire("a", winner.owner_id, ttl_seconds=60) is None
    assert second.release(winner)
    next_lease = first.acquire("a", "next-step", ttl_seconds=60)
    assert next_lease is not None
    assert not first.release(winner)
    assert first.release(next_lease)


def test_expired_idle_lease_cannot_be_used_or_release_successor(tmp_path: Path) -> None:
    clock = FrozenClock()
    pool = ProviderPoolManager(tmp_path / "pool", [_CODEX], clock=clock)
    original = pool.acquire("a", "same-step", ttl_seconds=10)
    assert original is not None
    clock.advance(timedelta(seconds=10))
    successor = pool.acquire("a", "same-step", ttl_seconds=10)
    assert successor is not None
    assert not pool.release(original)
    with pytest.raises(CapabilityUnavailable) as error, pool.use(original):
        pytest.fail("an expired lease reached the provider client")
    assert error.value.details["reason"] == "provider_slot_lease_inactive"
    with pool.use(successor) as home:
        assert home == original.client_home
    assert pool.release(successor)


def test_resume_is_pinned_to_original_pool_and_slot(tmp_path: Path) -> None:
    pool = ProviderPoolManager(tmp_path / "pool", [_CODEX, _OTHER_CODEX])
    first_step = pool.acquire("a", "step-a", ttl_seconds=60)
    assert first_step is not None
    with pool.use(first_step):
        pin = pool.pin_session(first_step, "provider-session")
    assert pool.release(first_step)

    # A different worker can consume the pin with the same stable slot.
    successor = ProviderPoolManager(tmp_path / "pool", [_CODEX, _OTHER_CODEX])
    same_slot = successor.acquire("a", "step-b", ttl_seconds=60)
    switched_slot = successor.acquire("b", "step-c", ttl_seconds=60)
    different_pool = ProviderPoolManager(tmp_path / "other-pool", [_CODEX])
    same_slot_id = different_pool.acquire("a", "step-d", ttl_seconds=60)
    assert same_slot is not None
    assert switched_slot is not None
    assert same_slot_id is not None
    assert same_slot.resume_ref(pin, required=True) == "provider-session"
    assert same_slot.resume_ref(None) is None
    assert switched_slot.resume_ref(pin) is None
    assert same_slot_id.resume_ref(pin) is None
    with pytest.raises(PreconditionFailed) as error:
        switched_slot.resume_ref(pin, required=True)
    assert error.value.code is ErrorCode.ADMISSION_REFUSED
    assert error.value.details["fresh_reason"] == "ROUTE_CHANGED"


def test_refresh_serializes_across_managers_without_blocking_another_slot(tmp_path: Path) -> None:
    root = tmp_path / "pool"
    first = ProviderPoolManager(root, [_CODEX, _OTHER_CODEX])
    second = ProviderPoolManager(root, [_CODEX, _OTHER_CODEX])
    lease = first.acquire("a", "step-a", ttl_seconds=60)
    other = second.acquire("b", "step-b", ttl_seconds=60)
    assert lease is not None
    assert other is not None
    entered = Event()
    finish = Event()
    queued = Event()

    def refresh_first(home: Path) -> None:
        entered.set()
        assert finish.wait(timeout=5)
        atomic_write(home / "auth.json", b'{"token":"rotated"}', mode=0o600, private=True)

    def refresh_second() -> str:
        queued.set()
        return second.refresh(lease, lambda home: (home / "auth.json").read_text(encoding="utf-8"))

    with ThreadPoolExecutor(max_workers=2) as threads:
        running = threads.submit(first.refresh, lease, refresh_first)
        try:
            assert entered.wait(timeout=5)
            waiting = threads.submit(refresh_second)
            assert queued.wait(timeout=5)
            assert second.refresh(other, lambda home: home) == other.client_home
            assert not waiting.done()
        finally:
            finish.set()
        running.result(timeout=5)
        assert waiting.result(timeout=5) == '{"token":"rotated"}'


def test_expiry_during_refresh_preserves_exclusivity_and_fences_waiters(tmp_path: Path) -> None:
    clock = FrozenClock()
    pool = ProviderPoolManager(tmp_path / "pool", [_CODEX], clock=clock)
    lease = pool.acquire("a", "step-a", ttl_seconds=10)
    assert lease is not None
    with ThreadPoolExecutor(max_workers=1) as threads, pool.use(lease):
        clock.advance(timedelta(seconds=10))
        assert threads.submit(pool.acquire, "a", "step-b", ttl_seconds=10).result(timeout=5) is None

    def unexpectedly_refresh(home: Path) -> None:
        pytest.fail(f"expired lease refreshed {home}")

    with pytest.raises(CapabilityUnavailable):
        pool.refresh(lease, unexpectedly_refresh)
    assert pool.acquire("a", "step-b", ttl_seconds=10) is not None


def test_failed_refresh_releases_lock_and_keeps_lease(tmp_path: Path) -> None:
    pool = ProviderPoolManager(tmp_path / "pool", [_CODEX])
    lease = pool.acquire("a", "step-a", ttl_seconds=60)
    assert lease is not None

    def failed_refresh(home: Path) -> None:
        raise RuntimeError("refresh failed")

    with pytest.raises(RuntimeError, match="refresh failed"):
        pool.refresh(lease, failed_refresh)
    assert pool.acquire("a", "step-b", ttl_seconds=60) is None
    assert pool.refresh(lease, lambda home: home) == lease.client_home
    assert pool.release(lease)
