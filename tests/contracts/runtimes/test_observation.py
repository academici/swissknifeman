"""Capture completeness, live loss and independent clock domains are separate facts."""

from __future__ import annotations

import json
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import override

import pytest

from skm.adapters.runtimes._cli_session.observation import LiveQueue
from skm.adapters.runtimes._cli_session.session import SessionLimits
from skm.kernel.error_codes import ErrorCode
from skm.modules.runtimes import public as rt
from skm.modules.runtimes.domain.observation import ToolVisibility, canonical_observation_bytes
from skm.platform.schema.registry import SchemaRegistry

from .conftest import WireParser, build


def test_disconnected_live_sink_does_not_block_capture_cancel_or_heartbeat(tmp_path: Path) -> None:
    live = LiveQueue(max_bytes=1024, max_entries=2)
    wire = b'{"type":"text_delta","text":"flood"}\n' * 1000
    harness = build(tmp_path, stdout=wire, stderr=b"stderr flood\n" * 1000, exit_code=None, live=live)
    beats: list[float] = []

    def heartbeat(_: float) -> None:
        beats.append(harness.clock.monotonic())
        harness.cancel.set()

    harness.sleeper.on_sleep = heartbeat
    result = harness.session.result()
    assert beats
    assert result.failure is not None
    assert result.failure.code == ErrorCode.SESSION_CANCELLED
    assert result.observation is not None
    capture = result.observation.capture
    assert capture.coverage == "complete"
    assert capture.bytes_seen == capture.bytes_retained == len(wire) + len(harness.child.stderr)
    assert capture.live_events_dropped == live.dropped > 0
    assert capture.gaps == ("live_delivery_gap",)
    assert live.bytes_queued <= 1024
    assert harness.child.pump_count > 1


def test_live_queue_is_bounded_by_bytes_and_entries_and_never_waits_for_consumer() -> None:
    live = LiveQueue(max_bytes=5, max_entries=2)
    assert live.offer(b"1234")
    assert not live.offer(b"56")
    assert live.take() == b"1234"
    assert live.offer(b"1")
    assert live.offer(b"2")
    assert not live.offer(b"3")
    assert live.dropped == 2


@pytest.mark.parametrize("hours", [-24, 24])
def test_utc_jump_cannot_move_quiet_runtime_deadline(tmp_path: Path, hours: int) -> None:
    harness = build(
        tmp_path,
        stdout=b"",
        exit_code=None,
        limits=SessionLimits(
            wall_timeout_seconds=0.2,
            idle_timeout_seconds=0.05,
            poll_interval_seconds=0.05,
        ),
    )
    harness.sleeper.on_sleep = lambda _: harness.utc.advance(timedelta(hours=hours))
    result = harness.session.result()
    assert result.failure is not None
    assert result.failure.code == ErrorCode.RUNTIME_TIMEOUT
    assert result.exit.duration_ms == 200
    assert result.observation is not None
    assert result.observation.timing.duration_ms == 200


def test_restart_has_fresh_epoch_and_durations_are_not_summed(tmp_path: Path) -> None:
    first = build(tmp_path / "first").session.result().observation
    second = build(tmp_path / "second").session.result().observation
    assert first is not None
    assert second is not None
    assert first.timing.clock_domain_id != second.timing.clock_domain_id
    assert first.timing.duration_ms == second.timing.duration_ms == 100


@pytest.mark.parametrize("source", ["stdout", "stderr", "both", "infinite_line"])
def test_joint_stream_ceiling_is_checked_before_write(tmp_path: Path, source: str) -> None:
    kwargs = {"stdout": b"", "stderr": b""}
    if source in ("stdout", "both"):
        kwargs["stdout"] = b'{"type":"text_delta","text":"flood"}\n' * 40
    if source in ("stderr", "both"):
        kwargs["stderr"] = b"flood stderr\n" * 100
    if source == "infinite_line":
        kwargs["stdout"] = b"x" * 4096
    harness = build(
        tmp_path,
        stdout=kwargs["stdout"],
        stderr=kwargs["stderr"],
        exit_code=None,
        limits=SessionLimits(
            poll_interval_seconds=0.05,
            max_stream_bytes=1000,
        ),
    )
    result = harness.session.result()
    assert result.failure is not None
    assert result.failure.code == ErrorCode.RUNTIME_CRASHED
    assert result.failure.details == {"reason": "stream_too_large"}
    assert harness.writer.used <= 1000
    assert sum(path.stat().st_size for path in harness.writer.step_dir.iterdir()) <= 1000
    assert len(harness.session.tail.pending) <= 1000
    assert result.observation is not None
    assert result.observation.capture.coverage == "partial"
    assert result.observation.capture.truncated
    assert result.observation.capture.bytes_dropped == len(kwargs["stdout"]) + len(kwargs["stderr"])
    assert (
        harness.budget.snapshot(harness.writer.step_dir.parent.parent, min_free_bytes=0).reserved_bytes == 0
    )


def test_one_native_record_may_emit_many_events_without_fabricated_gaps(tmp_path: Path) -> None:
    class MultiParser(WireParser):
        @override
        def feed(self, line):
            events = tuple(super().feed(line))
            return events * 2

    harness = build(
        tmp_path,
        parser=MultiParser(),
        stdout=(
            b'{"type":"text_delta","text":"a","seq":1}\n'
            b'{"type":"text_delta","text":"b","seq":1}\n'
            b'{"type":"text_delta","text":"c"}\n'
            b'{"type":"fake_result","final_text":"done"}\n'
        ),
    )
    events = list(harness.session.run())
    assert rt.validate_event_stream(events) == ()
    assert len([event for event in events if isinstance(event, rt.TextDelta)]) == 6
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    result = harness.session.result()
    assert result.observation is not None
    assert "provider_sequence_gap" not in result.observation.capture.gaps


def test_explicit_native_sequence_gap_marks_partial_capture(tmp_path: Path) -> None:
    harness = build(
        tmp_path,
        stdout=(
            b'{"type":"text_delta","text":"a","seq":1}\n'
            b'{"type":"text_delta","text":"b","seq":3}\n'
            b'{"type":"fake_result","final_text":"done"}\n'
        ),
    )
    result = harness.session.result()
    assert result.observation is not None
    assert result.observation.capture.coverage == "partial"
    assert result.observation.capture.gaps == ("provider_sequence_gap",)


def test_model_tools_and_launch_identity_are_not_filled_from_guesses(tmp_path: Path) -> None:
    harness = build(tmp_path)
    binding = harness.session.binding
    result = harness.session.result()
    assert result.observation is not None
    observation = result.observation
    assert result.model is observation.binding.provider_reported_model is None
    assert observation.tools.observed_calls is None
    assert observation.tools.coverage == "unavailable"
    assert observation.binding.runtime_version is binding.runtime_version is None
    assert observation.binding.executable_sha256 is None
    assert rt.validate_result_observation(result, request_id=harness.session.step_id) == ()
    encoded = canonical_observation_bytes(observation)
    assert len(encoded) <= 16_384
    assert SchemaRegistry.load_default().validate(observation.schema, json.loads(encoded)) == ()
    assert harness.session.result().observation is observation


def test_single_primary_capture_is_charged_once_and_events_do_not_consume_disk_budget(tmp_path: Path) -> None:
    wire = json.dumps({"type": "text_delta", "text": "x" * 550}).encode() + b"\n"
    wire += b'{"type":"fake_result","final_text":"done"}\n'
    harness = build(tmp_path, stdout=wire, limits=SessionLimits(max_stream_bytes=1000))
    events = list(harness.session.run())
    assert rt.validate_event_stream(events) == ()
    assert any(isinstance(event, rt.TextDelta) for event in events)
    result = harness.session.result()
    assert result.outcome == "completed"
    assert (harness.writer.step_dir / "stream.jsonl").read_bytes() == wire
    assert harness.writer.used == sum(path.stat().st_size for path in harness.writer.step_dir.iterdir())
    assert harness.writer.used < 1000
    assert result.observation is not None
    assert result.observation.capture.bytes_seen == result.observation.capture.bytes_retained == len(wire)
    assert result.observation.capture.bytes_dropped == 0
    assert not result.observation.capture.truncated


@pytest.mark.parametrize("overflow", ["sidecar", "final_redaction"])
def test_late_capture_ceiling_keeps_raw_loss_and_truncation_facts_consistent(
    tmp_path: Path, overflow: str
) -> None:
    wire = b'{"type":"fake_result","final_text":"done"}\n'
    harness = build(
        tmp_path,
        stdout=wire,
        stderr=b"@" * 10 if overflow == "final_redaction" else b"",
        limits=SessionLimits(max_stream_bytes=128 if overflow == "final_redaction" else len(wire)),
    )
    harness.writer.register_secret("@")
    events = list(harness.session.run())
    result = harness.session.result()
    assert rt.validate_event_stream(events) == ()
    assert result.failure is not None
    assert result.failure.code == ErrorCode.RUNTIME_CRASHED
    assert result.failure.details == {"reason": "stream_too_large"}
    assert result.exit.output_truncated
    assert result.observation is not None
    capture = result.observation.capture
    assert capture.coverage == "partial"
    assert capture.gaps == ("capture_gap",)
    assert capture.truncated
    # Sidecar loss cannot manufacture raw bytes that never arrived or erase a stored record.
    assert capture.bytes_dropped == (10 if overflow == "final_redaction" else 0)
    assert capture.bytes_retained == len(wire)
    assert capture.bytes_seen == len(wire) + (10 if overflow == "final_redaction" else 0)
    assert rt.validate_result_observation(result, request_id=harness.session.step_id) == ()


@pytest.mark.parametrize("explicit_tools", [False, True])
def test_tool_requests_upgrade_unavailable_visibility_and_outcome_denials_survive(
    tmp_path: Path, explicit_tools: bool
) -> None:
    harness = build(
        tmp_path,
        stdout=(
            b'{"type":"tool_requested","call_id":"one","tool":"read","args_preview":"private"}\n'
            b'{"type":"tool_requested","call_id":"two","tool":"read"}\n'
            b'{"type":"fake_result","final_text":"done"}\n'
        ),
    )
    tools = ToolVisibility("complete", 3) if explicit_tools else ToolVisibility("unavailable", None)
    denials = (rt.ToolDenial("write", "permission denied"),)
    harness.parser.outcome = replace(harness.parser.outcome, tools=tools, denials=denials)
    events = list(harness.session.run())
    assert rt.validate_event_stream(events) == ()
    result = harness.session.result()
    assert result.outcome == "completed"
    assert result.denials == denials
    assert result.observation is not None
    assert result.observation.tools == (tools if explicit_tools else ToolVisibility("partial", 2))
    assert b"private" not in canonical_observation_bytes(result.observation)
