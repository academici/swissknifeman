"""Gemini CLI stream framing and cumulative usage normalization."""

from __future__ import annotations

import json

import pytest

from skm.adapters.runtimes.gemini_cli.stream_parser import GeminiCliStreamParser
from skm.adapters.runtimes.gemini_cli.usage import parse_usage
from skm.bootstrap.builtins import builtin_runtime_data
from skm.kernel.error_codes import ErrorCode
from skm.modules.runtimes.domain.error_rules import classify
from skm.modules.runtimes.domain.usage import UsageStatus

_MODEL = "gemini-3.8-flash"


@pytest.mark.parametrize(
    ("stats", "fresh", "cache", "output", "status"),
    [
        ({"input_tokens": 10, "cached": 4, "output_tokens": 2, "models": {"other": {}}}, 6, 4, 2, "reported"),
        ({"input_tokens": 10, "input": 6}, 6, None, None, "reported"),
        ({"input_tokens": 10, "output_tokens": 0}, None, None, 0, "reported"),
        ({"input_tokens": 2, "cached": 4}, None, 4, None, "reported"),
        ({"input_tokens": True, "cached": -1, "output_tokens": "4"}, None, None, None, "unknown"),
        (None, None, None, None, "unknown"),
    ],
)
def test_usage_normalization(
    stats: object, fresh: int | None, cache: int | None, output: int | None, status: str
) -> None:
    usage = parse_usage(stats)
    assert (usage.input_tokens, usage.cache_read_tokens, usage.output_tokens) == (fresh, cache, output)
    assert usage.status is UsageStatus(status)
    assert usage.reasoning_tokens is None
    assert usage.cost_usd_micros is None


@pytest.mark.parametrize(
    "invalid",
    [
        {"type": "init", "session_id": "other", "model": _MODEL},
        {"type": "result", "status": "unknown"},
    ],
)
def test_invalid_protocol_cannot_complete(invalid: dict[str, str]) -> None:
    parser = GeminiCliStreamParser(model=_MODEL, version="0.68.0")
    parser.feed(json.dumps({"type": "init", "session_id": "session", "model": _MODEL}).encode())
    with pytest.raises(ValueError, match="Invalid Gemini CLI"):
        parser.feed(json.dumps(invalid).encode())
    parser.feed(b'{"type":"result","status":"success"}')
    assert not parser.saw_terminal()


def test_mismatched_model_and_duplicate_terminal_are_rejected() -> None:
    parser = GeminiCliStreamParser(model=_MODEL, version=None)
    with pytest.raises(ValueError, match="session or model"):
        parser.feed(b'{"type":"init","session_id":"session","model":"another-model"}')

    parser = GeminiCliStreamParser(model=_MODEL, version=None)
    parser.feed(json.dumps({"type": "init", "session_id": "session", "model": _MODEL}).encode())
    parser.feed(b'{"type":"result","status":"success"}')
    assert parser.saw_terminal()
    with pytest.raises(ValueError, match="after its result"):
        parser.feed(b'{"type":"result","status":"success"}')
    assert not parser.saw_terminal()


@pytest.mark.parametrize(
    ("status", "message", "error_code"),
    [
        (401, "Expired synthetic key", ErrorCode.RUNTIME_AUTH_EXPIRED),
        (429, "Try again later", ErrorCode.RATE_LIMITED),
        (429, "Daily quota exhausted", ErrorCode.QUOTA_EXHAUSTED),
    ],
)
def test_terminal_error_is_classified_and_redacted(status: int, message: str, error_code: ErrorCode) -> None:
    secret = "synthetic-key"
    parser = GeminiCliStreamParser(
        model=_MODEL, version="0.68.0", redact=lambda text: text.replace(secret, "***")
    )
    event = {
        "type": "result",
        "status": "error",
        "error": {"code": status, "message": f"{message}: {secret}"},
    }
    line = json.dumps(event).encode()
    parser.feed(line)
    assert parser.is_terminal(line)
    outcome = parser.finish(1)
    assert not parser.saw_terminal()
    assert outcome.is_error
    assert not outcome.final_text
    assert outcome.signals.fatal_text == f"{message}: ***"
    data = next(item for item in builtin_runtime_data() if item.runtime_id == "gemini_cli")
    assert classify("gemini_cli", outcome.signals, data.error_rules, now_unix=0).code is error_code
