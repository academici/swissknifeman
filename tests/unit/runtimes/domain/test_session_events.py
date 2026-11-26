"""Session event stream contract (runtimes §4.6, §5 validate_event_stream)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.modules.runtimes.domain.error_rules import (
    ErrorClass,
    ErrorRule,
    ErrorScope,
    ProcessOutcome,
    ProviderFailure,
    RuntimeSignals,
    classify,
    parse_error_rules,
    process_failure,
)
from skm.modules.runtimes.domain.session_events import (
    CancelIgnored,
    SessionCompleted,
    SessionEvent,
    SessionFailed,
    SessionStarted,
    StopReason,
    TextDelta,
    ToolCompleted,
    ToolRequested,
    UsageReported,
    session_event_from_json,
    session_event_to_json,
    validate_event_stream,
)
from skm.modules.runtimes.domain.usage import SubagentUsage, UsageReport, UsageStatus, unknown_usage
from skm.platform.schema.registry import SchemaRegistry

ROOT = Path(__file__).resolve().parents[4]
SAMPLE = ROOT / "tests/fixtures/corpus/examples/runtimes/session-events.jsonl"
URN = "urn:skm:runtimes:session-event:v1"
T0 = datetime(2026, 10, 25, 14, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


@cache
def registry() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def at(seq: int) -> datetime:
    return T0 + timedelta(seconds=seq)


def usage(status: UsageStatus = UsageStatus.REPORTED) -> UsageReport:
    if status is UsageStatus.UNKNOWN:
        return unknown_usage()
    return UsageReport(10, 5, None, None, None, None, status, "stream:result", SubagentUsage(False, True))


def started(seq: int = 1) -> SessionStarted:
    return SessionStarted(seq, at(seq), "ref-1", "model-x", "1.0")


def cumulative(seq: int, status: UsageStatus = UsageStatus.REPORTED) -> UsageReported:
    return UsageReported(seq, at(seq), usage(status), cumulative=True)


def completed(seq: int) -> SessionCompleted:
    return SessionCompleted(seq, at(seq), StopReason.END_TURN, DIGEST)


def failed(seq: int, failure: ProviderFailure | None = None) -> SessionFailed:
    return SessionFailed(seq, at(seq), failure or process_failure(ProcessOutcome.STREAM_INCOMPLETE))


def rules(events: list[SessionEvent]) -> list[str]:
    return [violation.rule for violation in validate_event_stream(events)]


def load_sample() -> list[SessionEvent]:
    return [session_event_from_json(json.loads(line)) for line in SAMPLE.read_text().splitlines() if line]


def test_sample_stream_is_valid_and_round_trips_through_the_schema() -> None:
    events = load_sample()
    assert rules(events) == []
    originals = [json.loads(line) for line in SAMPLE.read_text().splitlines() if line]
    for event, original in zip(events, originals, strict=True):
        encoded = session_event_to_json(event)
        assert registry().validate(URN, encoded) == ()
        assert session_event_from_json(encoded) == event
        assert encoded["type"] == original["type"]
        assert encoded["seq"] == original["seq"]


def test_completed_stream_without_usage_is_valid() -> None:
    assert rules([started(), TextDelta(2, at(2), "assistant", "ok"), completed(3)]) == []


@pytest.mark.parametrize(
    ("events", "expected"),
    [
        pytest.param(
            [started(), cumulative(2), completed(3), completed(4)], ["duplicate_terminal"], id="two-completed"
        ),
        pytest.param(
            [started(), cumulative(2), completed(3), failed(4)], ["duplicate_terminal"], id="completed-failed"
        ),
        pytest.param(
            [started(), cumulative(2), completed(3), TextDelta(4, at(4), "assistant", "late")],
            ["event_after_terminal"],
            id="after-terminal",
        ),
        pytest.param([started(), TextDelta(2, at(2), "assistant", "x")], ["missing_terminal"], id="partial"),
        pytest.param([], ["missing_terminal"], id="empty"),
    ],
)
def test_partial_and_duplicate_terminal_are_rejected(events: list[SessionEvent], expected: list[str]) -> None:
    assert rules(events) == expected


@pytest.mark.parametrize("seqs", [(1, 3, 2), (1, 2, 2)], ids=["decreasing", "repeated"])
def test_seq_strictly_increases(seqs: tuple[int, int, int]) -> None:
    first, middle, last = seqs
    events: list[SessionEvent] = [
        started(first),
        TextDelta(middle, at(middle), "assistant", "x"),
        completed(last),
    ]
    assert "seq_not_increasing" in rules(events)


def test_seq_is_adapter_owned_and_wall_clock_jumps_are_not_violations() -> None:
    # at is the observer UTC; a backward clock jump is not a seq violation.
    events: list[SessionEvent] = [
        SessionStarted(1, at(10), None, None, None),
        TextDelta(2, at(1), "assistant", "x"),
        completed(3),
    ]
    assert rules(events) == []


def test_failed_needs_cumulative_usage_first() -> None:
    assert rules([started(), failed(2)]) == ["failed_without_usage"]
    delta = UsageReported(2, at(2), usage(), cumulative=False)
    assert rules([started(), delta, failed(3)]) == ["failed_without_usage"]
    assert rules([started(), cumulative(2), failed(3)]) == []


@pytest.mark.parametrize("first", [UsageStatus.UNKNOWN, UsageStatus.REPORTED], ids=["unknown", "measured"])
def test_delta_after_cumulative_makes_it_stale_before_failed(first: UsageStatus) -> None:
    delta = UsageReported(3, at(3), usage(), cumulative=False)
    assert rules([started(), cumulative(2, first), delta, failed(4)]) == ["failed_without_usage"]
    unknown_delta = UsageReported(3, at(3), usage(UsageStatus.UNKNOWN), cumulative=False)
    assert rules([started(), cumulative(2, first), unknown_delta, failed(4)]) == ["failed_without_usage"]
    # A new total covering the delta makes the report current again.
    assert rules([started(), cumulative(2, first), delta, cumulative(4), failed(5)]) == []


def test_events_without_usage_between_cumulative_and_failed_keep_it_current() -> None:
    events: list[SessionEvent] = [
        started(),
        cumulative(2),
        TextDelta(3, at(3), "assistant", "x"),
        CancelIgnored(4, at(4), "SIGTERM"),
        failed(5, process_failure(ProcessOutcome.WALL_TIMEOUT)),
    ]
    assert rules(events) == []


def test_usage_before_failed_may_be_unknown_but_is_never_zero() -> None:
    # Nothing known: the adapter still reports, with status unknown and null counters.
    events: list[SessionEvent] = [started(), cumulative(2, UsageStatus.UNKNOWN), failed(3)]
    assert rules(events) == []
    reported = events[1]
    assert isinstance(reported, UsageReported)
    assert reported.usage.input_tokens is None
    assert reported.usage.status is UsageStatus.UNKNOWN


@pytest.mark.parametrize(
    "outcome",
    [
        ProcessOutcome.CANCELLED,
        ProcessOutcome.CANCEL_IGNORED,
        ProcessOutcome.WALL_TIMEOUT,
        ProcessOutcome.CLEANUP_UNCONFIRMED,
    ],
)
def test_cancel_ignored_is_not_terminal_and_precedes_an_allowed_failure(outcome: ProcessOutcome) -> None:
    events: list[SessionEvent] = [
        started(),
        CancelIgnored(2, at(2), "SIGTERM"),
        cumulative(3, UsageStatus.ESTIMATED),
        failed(4, process_failure(outcome)),
    ]
    assert rules(events) == []


def test_cancel_ignored_alone_does_not_end_a_stream() -> None:
    assert rules([started(), CancelIgnored(2, at(2), "SIGINT")]) == ["missing_terminal"]


def test_cancel_ignored_before_completed_is_rejected() -> None:
    events: list[SessionEvent] = [started(), CancelIgnored(2, at(2), "SIGINT"), completed(3)]
    assert rules(events) == ["cancel_ignored_terminal"]


def test_cancel_ignored_before_an_unrelated_failure_is_rejected() -> None:
    events: list[SessionEvent] = [
        started(),
        CancelIgnored(2, at(2), "SIGTERM"),
        cumulative(3),
        failed(4, process_failure(ProcessOutcome.STREAM_INCOMPLETE)),
    ]
    assert rules(events) == ["cancel_ignored_terminal"]


@pytest.mark.parametrize("seq", [0, -1, True])
def test_seq_starts_at_one(seq: int) -> None:
    with pytest.raises(ValueError, match="seq"):
        TextDelta(seq, T0, "assistant", "x")


NAIVE = datetime(2026, 1, 1)  # noqa: DTZ001 - the invalid input under test


@pytest.mark.parametrize("moment", [NAIVE, datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=3)))])
def test_at_is_tz_aware_utc(moment: datetime) -> None:
    with pytest.raises(ValueError, match="UTC"):
        TextDelta(1, moment, "assistant", "x")


def test_event_field_bounds() -> None:
    with pytest.raises(ValueError, match="args_preview"):
        ToolRequested(1, T0, "c1", "Read", "x" * 501, DIGEST)
    with pytest.raises(ValueError, match="args_digest"):
        ToolRequested(1, T0, "c1", "Read", "{}", "md5:00")
    with pytest.raises(ValueError, match="duration_ms"):
        ToolCompleted(1, T0, "c1", "ok", -1)  # pyright: ignore[reportArgumentType]
    with pytest.raises(ValueError, match="signal"):
        CancelIgnored(1, T0, "SIGKILL")  # pyright: ignore[reportArgumentType]


def test_closed_union_refuses_unknown_type() -> None:
    with pytest.raises(ValueError, match="unknown session event type"):
        session_event_from_json({"type": "session_paused", "seq": 1, "at": "2026-10-25T14:00:00Z"})
    assert registry().validate(URN, {"type": "session_paused", "seq": 1, "at": "2026-10-25T14:00:00Z"}) != ()


def test_failed_event_with_failure_round_trips_through_the_schema() -> None:
    failure = process_failure(
        ProcessOutcome.STREAM_INCOMPLETE, details={"exit_code": 0, "last_event_type": "item"}
    )
    event = failed(5, failure)
    encoded = session_event_to_json(event)
    assert registry().validate(URN, encoded) == ()
    decoded = session_event_from_json(encoded)
    assert decoded == event
    assert isinstance(decoded, SessionFailed)
    assert decoded.failure.code is ErrorCode.RUNTIME_STREAM_INCOMPLETE
    assert dict(decoded.failure.details) == {"exit_code": 0, "last_event_type": "item"}


# Classification of the failure carried by session_failed (§4.9; port of legacy provider errors).

RULES_DOC: dict[str, Any] = {
    "rules": [
        {
            "runtime_id": "claude_code",
            "error_class": "rate_limit",
            "code": "RATE_LIMITED",
            "scope": "account",
            "signal_any": {"limit_status": ["rejected"], "is_error": [True]},
            "signal_not_in": {},
            "text_contains_any": [],
            "retryable": None,
            "safe_message": None,
            "retry_after_from": "limit_resets_at",
        },
        {
            "runtime_id": "claude_code",
            "error_class": "authentication",
            "code": "RUNTIME_AUTH_EXPIRED",
            "scope": "account",
            "signal_any": {},
            "signal_not_in": {"http_status": [200]},
            "text_contains_any": ["Invalid API key", "don\u2019t have access"],
            "retryable": None,
            "safe_message": "log in again",
            "retry_after_from": None,
        },
        {
            "runtime_id": "codex",
            "error_class": "context_limit",
            "code": "CONTEXT_OVERFLOW",
            "scope": "request",
            "signal_any": {},
            "signal_not_in": {},
            "text_contains_any": ["context window"],
            "retryable": None,
            "safe_message": None,
            "retry_after_from": None,
        },
    ]
}


def test_error_rules_document_is_schema_valid_and_parsed_in_order() -> None:
    assert registry().validate("urn:skm:runtimes:error-rules:v1", RULES_DOC) == ()
    parsed = parse_error_rules(RULES_DOC)
    assert [rule.code for rule in parsed] == [
        ErrorCode.RATE_LIMITED,
        ErrorCode.RUNTIME_AUTH_EXPIRED,
        ErrorCode.CONTEXT_OVERFLOW,
    ]


def test_first_matching_rule_of_the_runtime_wins_with_retry_after() -> None:
    signals = RuntimeSignals(
        is_error=True, limit_status="rejected", limit_resets_at=1_000_060, http_status=429
    )
    failure = classify("claude_code", signals, parse_error_rules(RULES_DOC), now_unix=1_000_000)
    assert (failure.error_class, failure.code, failure.retryable) == (
        ErrorClass.RATE_LIMIT,
        ErrorCode.RATE_LIMITED,
        True,
    )
    assert failure.retry_after_seconds == 60
    assert failure.evidence == "structured"
    late = classify("claude_code", signals, parse_error_rules(RULES_DOC), now_unix=2_000_000)
    assert late.retry_after_seconds == 0


def test_signal_any_needs_every_key_and_type_strict_values() -> None:
    rules_ = parse_error_rules(RULES_DOC)
    only_status = RuntimeSignals(limit_status="rejected")
    assert (
        classify("claude_code", only_status, rules_, now_unix=0).code
        is ErrorCode.RUNTIME_FAILURE_UNCLASSIFIED
    )
    rule = ErrorRule(
        "fake",
        ErrorClass.QUOTA,
        ErrorCode.QUOTA_EXHAUSTED,
        ErrorScope.ACCOUNT,
        {"exit_code": (1,)},
        {},
        (),
        None,
        None,
        None,
    )
    assert rule.matches(RuntimeSignals(exit_code=1))
    flag = ErrorRule(
        "fake",
        ErrorClass.QUOTA,
        ErrorCode.QUOTA_EXHAUSTED,
        ErrorScope.ACCOUNT,
        {"is_error": (True,)},
        {},
        (),
        None,
        None,
        None,
    )
    assert not flag.matches(RuntimeSignals(is_error=None, exit_code=1))


def test_text_markers_casefold_and_signal_not_in_needs_the_signal() -> None:
    rules_ = parse_error_rules(RULES_DOC)
    text = RuntimeSignals(stderr_tail="ERROR: You DON'T HAVE ACCESS", http_status=401)
    failure = classify("claude_code", text, rules_, now_unix=0)
    assert (failure.code, failure.safe_message, failure.retryable) == (
        ErrorCode.RUNTIME_AUTH_EXPIRED,
        "log in again",
        False,
    )
    assert "ACCESS" not in failure.safe_message  # raw provider text is never copied
    without_status = RuntimeSignals(stderr_tail="invalid api key")
    assert (
        classify("claude_code", without_status, rules_, now_unix=0).code
        is ErrorCode.RUNTIME_FAILURE_UNCLASSIFIED
    )
    assert classify(
        "claude_code", RuntimeSignals(stderr_tail="invalid api key", http_status=200), rules_, now_unix=0
    ).code is (ErrorCode.RUNTIME_FAILURE_UNCLASSIFIED)


def test_rules_of_other_runtimes_never_apply() -> None:
    signals = RuntimeSignals(fatal_text="context window exceeded", exit_code=1)
    rules_ = parse_error_rules(RULES_DOC)
    assert classify("codex", signals, rules_, now_unix=0).code is ErrorCode.CONTEXT_OVERFLOW
    assert classify("claude_code", signals, rules_, now_unix=0).code is ErrorCode.RUNTIME_CRASHED


@pytest.mark.parametrize(
    ("exit_code", "code", "retryable"),
    [
        (1, ErrorCode.RUNTIME_CRASHED, True),
        (-9, ErrorCode.RUNTIME_CRASHED, True),
        (0, ErrorCode.RUNTIME_FAILURE_UNCLASSIFIED, False),
        (None, ErrorCode.RUNTIME_FAILURE_UNCLASSIFIED, False),
    ],
)
def test_unmatched_failures_default_to_crash_or_unknown(
    exit_code: int | None, code: ErrorCode, retryable: bool
) -> None:
    failure = classify("fake", RuntimeSignals(exit_code=exit_code), (), now_unix=0)
    assert (failure.code, failure.retryable) == (code, retryable)


def test_process_outcome_table_and_rule_limits() -> None:
    incomplete = process_failure(ProcessOutcome.STREAM_INCOMPLETE, details={"exit_code": 0})
    assert (incomplete.error_class, incomplete.retryable, incomplete.evidence) == (
        ErrorClass.TRANSPORT,
        True,
        "process",
    )
    assert dict(process_failure(ProcessOutcome.WALL_TIMEOUT).details) == {"kind": "wall_timeout"}
    assert process_failure(ProcessOutcome.EMPTY_OUTPUT).code is ErrorCode.RESULT_INVALID
    assert process_failure(ProcessOutcome.CANCEL_IGNORED).cancelled
    with pytest.raises(ValueError, match="process outcome"):
        ErrorRule(
            "fake",
            ErrorClass.CANCELLED,
            ErrorCode.SESSION_CANCELLED,
            ErrorScope.SESSION,
            {},
            {},
            ("x",),
            None,
            None,
            None,
        )
    with pytest.raises(ValueError, match="condition"):
        ErrorRule(
            "fake",
            ErrorClass.QUOTA,
            ErrorCode.QUOTA_EXHAUSTED,
            ErrorScope.ACCOUNT,
            {},
            {},
            (),
            None,
            None,
            None,
        )
    with pytest.raises(ValueError, match="unknown signal"):
        ErrorRule(
            "fake",
            ErrorClass.QUOTA,
            ErrorCode.QUOTA_EXHAUSTED,
            ErrorScope.ACCOUNT,
            {"status": ("x",)},
            {},
            (),
            None,
            None,
            None,
        )
