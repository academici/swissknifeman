"""One explicitly opted-in Claude Code task in a disposable repository."""

from .conftest import LiveRuntime


def test_claude_code_small_task(live_runtime: LiveRuntime) -> None:
    live_runtime("claude_code")
