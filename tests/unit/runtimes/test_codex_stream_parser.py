"""Regression tests for Codex JSONL observations."""

from skm.adapters.runtimes.codex.stream_parser import CodexStreamParser
from skm.modules.runtimes.public import Effort


def test_turn_without_reasoning_effort_keeps_previous_observation() -> None:
    parser = CodexStreamParser()
    list(parser.feed(b'{"type":"turn.completed","reasoning_effort":"high"}'))
    list(parser.feed(b'{"type":"turn.started"}'))
    list(parser.feed(b'{"type":"turn.completed"}'))

    assert parser.finish(exit_code=0).observed_effort is Effort.HIGH
