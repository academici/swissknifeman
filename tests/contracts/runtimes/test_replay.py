"""Adversarial replay: reject before expensive decode and never recover success from prose."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from skm.adapters.runtimes._cli_session.activity import TreeCpuWatch, infra_process, read_activity
from skm.adapters.runtimes._cli_session.stream import LINE_BYTES, StreamTail
from skm.kernel.error_codes import ErrorCode
from skm.modules.runtimes import public as rt

from .conftest import build


@pytest.mark.parametrize(
    "wire",
    [
        b"[" * 65 + b"0" + b"]" * 65 + b"\n",
        b"[" + b"0," * 4096 + b"0]\n",
        b'"' + b"x" * LINE_BYTES + b'"\n',
        b"\xff\n",
    ],
    ids=["depth", "members", "line", "utf8"],
)
def test_limits_and_utf8_are_rejected_before_json_decode(wire: bytes) -> None:
    tail = StreamTail(4 * LINE_BYTES)
    with patch("skm.adapters.runtimes._cli_session.stream.json.loads", side_effect=AssertionError("decode")):
        assert tail.advance(wire, final=True) == []
    assert tail.flags
    assert len(tail.pending) <= tail.buffer_limit


@pytest.mark.parametrize(
    "wire",
    [
        b"[" * 64 + b"0" + b"]" * 64,
        b"[" + b"0," * 4095 + b"0]",
        json.dumps({str(i): None for i in range(4096)}).encode(),
        b'"' + b"x" * (LINE_BYTES - 2) + b'"',
    ],
    ids=["depth64", "array4096", "object4096", "line1MiB"],
)
def test_exact_parser_boundaries_are_accepted(wire: bytes) -> None:
    tail = StreamTail(4 * LINE_BYTES)
    assert tail.advance(wire + b"\n", final=True) == [wire]
    assert not tail.flags


def test_strings_cannot_forge_scanner_depth_or_members() -> None:
    line = json.dumps({"text": '[{,}:\\"' * 5000}).encode()
    tail = StreamTail(LINE_BYTES)
    assert tail.advance(line, final=True) == [line]
    assert not tail.flags


def test_empty_records_count_toward_the_100000_limit_before_decode() -> None:
    tail = StreamTail(LINE_BYTES)
    with patch("skm.adapters.runtimes._cli_session.stream.json.loads", side_effect=AssertionError("decode")):
        assert tail.advance(b"\n" * 100_000) == []
        assert not tail.flags
        assert tail.advance(b"\n") == []
    assert tail.records == 100_001
    assert tail.flags == {"parser_limit"}


@pytest.mark.parametrize("wire", [b'"unterminated', b'{"type":', b"{\n", b"NaN\n"])
def test_partial_or_malformed_json_never_reaches_parser(wire: bytes) -> None:
    tail = StreamTail(LINE_BYTES)
    assert tail.advance(wire, final=True) == []
    assert tail.flags


def test_valid_tail_without_newline_is_fed_once() -> None:
    tail = StreamTail(LINE_BYTES)
    assert tail.advance(b'{"type":') == []
    assert tail.advance(b'"fake_result"}') == []
    assert tail.advance(final=True) == [b'{"type":"fake_result"}']
    assert tail.advance(final=True) == []


def test_one_infinite_line_is_bounded_and_reconcile_remains_failed(tmp_path: Path) -> None:
    tail = StreamTail(128)
    for _ in range(100):
        tail.advance(b"x" * 32)
        assert len(tail.pending) <= 128
    assert tail.advance(b'\n{"valid":"json"}\n', final=True) == []
    assert tail.flags == {"parser_limit"}
    harness = build(tmp_path, stdout=b'not json\n{"type":"fake_result","final_text":"done"}\n')
    result = harness.session.result()
    assert result.failure is not None
    assert result.failure.code == ErrorCode.RUNTIME_STREAM_INCOMPLETE
    assert result.final_text == ""


def test_parser_failure_after_native_terminal_cannot_become_success(tmp_path: Path) -> None:
    harness = build(tmp_path, stdout=b'{"type":"fake_result","final_text":"done"}\n\xff\n')
    result = harness.session.result()
    assert result.failure is not None
    assert result.failure.code == ErrorCode.RUNTIME_STREAM_INCOMPLETE
    assert result.observation is not None
    assert result.observation.capture.coverage == "partial"


@pytest.mark.parametrize(
    ("wire", "flag"),
    [
        (b"}\n", "malformed_json"),
        (b"]\n", "malformed_json"),
        (b"{]\n", "malformed_json"),
        (b"[}\n", "malformed_json"),
        (b"\xff}\n", "invalid_utf8"),
        (b"[" * 65 + b"\xff\n", "invalid_utf8"),
    ],
)
@pytest.mark.parametrize("final", [False, True])
def test_syntax_and_utf8_errors_are_distinct_from_resource_limits(
    wire: bytes, flag: str, final: bool
) -> None:
    tail = StreamTail(LINE_BYTES)
    with patch("skm.adapters.runtimes._cli_session.stream.json.loads", side_effect=AssertionError("decode")):
        assert tail.advance(wire.rstrip(b"\n") if final else wire, final=final) == []
    assert tail.flags == {flag}


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_overlong_line_does_not_manufacture_capture_failure(tmp_path: Path, stream: str) -> None:
    wire = b"x" * (LINE_BYTES + 1) + b"\n"
    harness = build(tmp_path, stdout=wire) if stream == "stdout" else build(tmp_path, stderr=wire)
    events = list(harness.session.run())
    result = harness.session.result()
    assert rt.validate_event_stream(events) == ()
    assert not harness.writer.failed
    assert not harness.writer.exceeded
    assert result.observation is not None
    capture = result.observation.capture
    assert "capture_gap" not in capture.gaps
    assert capture.bytes_dropped == len(wire)
    assert capture.truncated
    if stream == "stdout":
        assert result.failure is not None
        assert result.failure.code == ErrorCode.RUNTIME_STREAM_INCOMPLETE
        assert capture.parser_flags == ("parser_limit",)
    else:
        assert result.outcome == "completed"
        assert capture.parser_flags == ()


def test_member_limit_also_counts_nested_array_items() -> None:
    line = b'{"items":[' + b"0," * 4095 + b"0]}\n"
    tail = StreamTail(LINE_BYTES)
    assert tail.advance(line) == []
    assert tail.flags == {"parser_limit"}


def test_cpu_growth_accumulates_between_samples_and_filters_supervisor() -> None:
    ticks = iter((0, 4, 8, 12, None))
    watch = TreeCpuWatch(
        123, sample_seconds=2, progress_seconds=1, ticks_per_second=10, read_ticks=lambda _: next(ticks)
    )
    assert not watch.sample(0)
    assert not watch.due(1)
    assert watch.due(2)
    assert not watch.sample(2)
    assert not watch.sample(4)
    assert watch.sample(6)
    assert watch.last_growth == 6
    assert not watch.sample(8)
    assert infra_process("/bin/ps -eo pid,pcpu")
    assert infra_process("/bin/sh -c ps")
    assert not infra_process("/bin/sh -c expensive-work")
    assert read_activity() == {"reads_total": None, "coverage": "unavailable"}
