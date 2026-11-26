"""One explicitly opted-in Codex task in a disposable repository."""

from .conftest import LiveRuntime


def test_codex_small_task(live_runtime: LiveRuntime) -> None:
    live_runtime("codex")
