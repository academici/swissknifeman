from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Barrier, Event

import pytest

from fakes.clock import FrozenClock
from skm.adapters.runtimes._cli_session.runtime import load_static_declarations
from skm.adapters.runtimes.claude_code import runtime as claude
from skm.adapters.runtimes.pool import ProviderPoolManager, ProviderSlot
from skm.adapters.runtimes.pool.rate_limit import RateLimitAction, classify_rate_limit
from skm.kernel.error_codes import ErrorCode
from skm.modules.runtimes.domain.error_rules import RuntimeSignals, classify
from skm.platform.fs.file_lock import FileLock

_NOW = datetime(2026, 6, 1, tzinfo=UTC)
_SLOTS = (ProviderSlot("claude_code", "a"), ProviderSlot("claude_code", "b"))


@pytest.mark.parametrize(
    ("headers", "message"),
    [
        ({}, "quota exceeded"),
        ({}, "Weekly limit reached"),
        ({"Anthropic-Ratelimit-Unified-Status": "rejected"}, "rate limited"),
        ({"anthropic-ratelimit-unified-5h-utilization": "1.0"}, "rate limited"),
    ],
)
def test_quota_wins_over_short_retry_after(headers: dict[str, str], message: str) -> None:
    reset_at = _NOW + timedelta(minutes=10)
    decision = classify_rate_limit(
        429, now=_NOW, headers={**headers, "Retry-After": "5"}, message=message, reset_at=reset_at
    )
    assert decision is not None
    assert decision.action == RateLimitAction.ROTATE_SLOT
    assert decision.is_quota_exhausted
    assert decision.cooldown_until == reset_at
    assert decision.wait_s == 0


def test_unknown_429_waits_once_and_burst_stays_within_limits() -> None:
    assert classify_rate_limit(529, now=_NOW) is None
    first = classify_rate_limit(429, now=_NOW)
    assert first is not None
    assert first.action == RateLimitAction.WAIT_SAME_SLOT
    assert first.wait_s == 5
    retry = classify_rate_limit(429, now=_NOW, attempt=2, reset_at="garbage")
    assert retry is not None
    assert retry.action == RateLimitAction.ROTATE_SLOT
    assert not retry.is_quota_exhausted
    assert retry.cooldown_until == _NOW + timedelta(seconds=60)

    burst = classify_rate_limit(
        429, now=_NOW, retry_after="6", attempt=2, total_wait_s=4, max_total_wait_s=10
    )
    assert burst is not None
    assert burst.action == RateLimitAction.WAIT_SAME_SLOT
    assert burst.wait_s == 6
    for bounded in (
        classify_rate_limit(429, now=_NOW, retry_after=7, total_wait_s=4, max_total_wait_s=10),
        classify_rate_limit(429, now=_NOW, retry_after=1, attempt=2, max_attempts=2),
    ):
        assert bounded is not None
        assert bounded.action == RateLimitAction.ROTATE_SLOT
        assert not bounded.is_quota_exhausted


@pytest.mark.parametrize("message", ["session limit reached", "weekly limit reached"])
def test_claude_error_rules_preserve_explicit_quota_on_429(message: str) -> None:
    _, rules = load_static_declarations(Path(claude.__file__).parent)
    signals = RuntimeSignals(http_status=429, fatal_text=message)
    assert classify("claude_code", signals, rules, now_unix=0).code is ErrorCode.QUOTA_EXHAUSTED


def test_rotation_is_shared_and_releases_lock_before_sleep(tmp_path: Path) -> None:
    clock = FrozenClock(_NOW)
    first = ProviderPoolManager(tmp_path / "pool", _SLOTS, clock=clock)
    second = ProviderPoolManager(tmp_path / "pool", _SLOTS, clock=clock)
    quota = classify_rate_limit(429, now=_NOW, message="session limit")
    burst = classify_rate_limit(429, now=_NOW, retry_after=5)
    assert quota is not None
    assert burst is not None
    waiting, released = Event(), Event()

    def sleep(seconds: float) -> None:
        assert seconds == 5
        with FileLock(tmp_path / "pool/rotation.lock").hold(timeout_seconds=1):
            waiting.set()
        assert released.wait(5)

    herd = Barrier(4)

    def rotate() -> None:
        herd.wait(5)
        assert second.handle_rate_limit("a", "opus", quota).action is RateLimitAction.ROTATE_SLOT

    with ThreadPoolExecutor(max_workers=5) as executor:
        retry = executor.submit(first.handle_rate_limit, "a", "opus", burst, sleep=sleep)
        try:
            assert waiting.wait(5)
            rotations = [executor.submit(rotate) for _ in range(4)]
            for rotation in rotations:
                rotation.result(timeout=5)
            assert first.route_generation == second.route_generation == 1
        finally:
            released.set()
        assert retry.result(timeout=5).action is RateLimitAction.ROTATE_SLOT

    same_model = first.acquire_ranked(_SLOTS, "step-1", ttl_seconds=60, model="opus")
    other_model = second.acquire_ranked(_SLOTS, "step-2", ttl_seconds=60, model="sonnet")
    assert same_model is not None
    assert same_model.slot.slot_id == "b"
    assert other_model is not None
    assert other_model.slot.slot_id == "a"
    second.release(other_model)
    clock.advance(timedelta(seconds=60))
    expired = first.acquire_ranked(_SLOTS, "step-3", ttl_seconds=60, model="opus")
    assert expired is not None
    assert expired.slot.slot_id == "a"
