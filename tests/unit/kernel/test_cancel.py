import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from skm.kernel.cancel import Cancelled, CancelSource


def test_first_reason_wins_and_token_is_readonly() -> None:
    source = CancelSource()
    assert not source.token.cancelled
    assert source.token.reason is None
    assert not source.token.wait(0)
    assert not hasattr(source.token, "cancel")
    assert not hasattr(source.token, "set_cancelled")
    source.token.raise_if_cancelled()
    source.cancel("user_cancel")
    source.cancel("timeout")
    assert source.token.wait(100)
    with pytest.raises(Cancelled, match="user_cancel") as caught:
        source.token.raise_if_cancelled()
    assert caught.value.reason == "user_cancel"


def test_parent_cancels_descendants_and_new_children() -> None:
    parent = CancelSource()
    child = CancelSource(parent=parent.token)
    grandchild = CancelSource(parent=child.token)
    independent = CancelSource(parent=parent.token)
    independent.cancel("timeout")
    parent.cancel("shutdown")
    for token in (child.token, grandchild.token, CancelSource(parent=parent.token).token):
        assert token.cancelled
        assert token.reason == "shutdown"
        assert token.wait(0)
    assert independent.token.reason == "timeout"


def test_child_does_not_cancel_parent_or_sibling() -> None:
    parent = CancelSource()
    child = CancelSource(parent=parent.token)
    sibling = CancelSource(parent=parent.token)
    child.cancel("lease_lost")
    assert not parent.token.cancelled
    assert not sibling.token.cancelled


def test_wait_wakes_across_threads() -> None:
    parent = CancelSource()
    child = CancelSource(parent=parent.token)
    waiting = threading.Event()

    def wait() -> bool:
        waiting.set()
        return child.token.wait(5)

    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(wait)
        assert waiting.wait(1)
        parent.cancel("shutdown")
        assert result.result(timeout=1)


def test_a_native_child_waits_without_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    # Parents of the same implementation set their children's events; only a foreign one needs polling.
    parent = CancelSource()
    child = CancelSource(parent=CancelSource(parent=parent.token).token)
    event = child.token._event  # pyright: ignore[reportAttributeAccessIssue] - the native token behind the view
    calls: list[float | None] = []
    real_wait = event.wait

    def counted(timeout: float | None = None) -> bool:
        calls.append(timeout)
        return real_wait(timeout)

    monkeypatch.setattr(event, "wait", counted)
    assert not child.token.wait(0.2)
    assert len(calls) == 1


def test_concurrent_cancel_is_consistent() -> None:
    source = CancelSource()
    children = [CancelSource(parent=source.token) for _ in range(20)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(source.cancel, ["shutdown", "timeout", "lease_lost", "user_cancel"]))
    assert source.token.reason in {"shutdown", "timeout", "lease_lost", "user_cancel"}
    assert all(child.token.reason == source.token.reason for child in children)


def test_foreign_parent_is_observed_without_watcher_thread() -> None:
    source = CancelSource()

    class Foreign:
        @property
        def cancelled(self) -> bool:
            return source.token.cancelled

        @property
        def reason(self) -> str | None:
            return source.token.reason

        def raise_if_cancelled(self) -> None:
            source.token.raise_if_cancelled()

        def wait(self, timeout_seconds: float) -> bool:
            return source.token.wait(timeout_seconds)

    child = CancelSource(parent=Foreign())
    with ThreadPoolExecutor(max_workers=1) as pool:
        result = pool.submit(child.token.wait, 2)
        source.cancel("lease_lost")
        assert result.result(timeout=1)
    assert child.token.reason == "lease_lost"


def test_deep_parent_tree() -> None:
    root = CancelSource()
    child = root
    for _ in range(1500):
        child = CancelSource(parent=child.token)
    root.cancel("shutdown")
    assert child.token.reason == "shutdown"


@pytest.mark.parametrize("seconds", [-1, float("nan"), float("inf")])
def test_invalid_wait(seconds: float) -> None:
    with pytest.raises(ValueError, match="finite"):
        CancelSource().token.wait(seconds)
