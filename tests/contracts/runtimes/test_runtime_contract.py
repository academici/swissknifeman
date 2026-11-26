"""Offline runtime contract cases; synthetic ports do not assert live provider support."""

from __future__ import annotations

import dataclasses
import io
import json
import signal
from pathlib import Path
from typing import override

import pytest

from skm.adapters.runtimes._cli_session.session import SessionLimits, TrustedProcessRunner
from skm.adapters.runtimes.fake import scenarios
from skm.adapters.runtimes.fake.runtime import FakeRuntime
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.runtimes import public as rt
from skm.plugin_api.testing import ContractCase, run_contract_suite

from .conftest import FIXTURES, WireParser, build


class ScenarioHang(Exception):
    """Synthetic child pause; OS/backend proof remains a separate case."""


def fixture_output(
    tmp_path: Path,
    name: str,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[bytes, bytes, int | None]:
    scenario = scenarios.load_scenario(FIXTURES / f"{name}.toml")
    assert scenario.name == name
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    stdout = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", write_through=True)
    stderr = io.TextIOWrapper(io.BytesIO(), encoding="utf-8", write_through=True)

    def pause() -> None:
        raise ScenarioHang

    with monkeypatch.context() as child:
        child.chdir(workdir)
        child.setattr("sys.stdout", stdout)
        child.setattr("sys.stderr", stderr)
        child.setattr("sys.stdin", io.StringIO("synthetic prompt"))
        child.setattr(
            "sys.argv",
            [
                "scenario",
                json.dumps(scenario.document),
                "resume" if name == "resume_unsupported" else "fresh",
            ],
        )
        child.setattr(signal, "signal", lambda *_: None)
        child.setattr(signal, "pause", pause)
        with pytest.raises((SystemExit, ScenarioHang)) as stopped:
            scenarios._process()
    code = stopped.value.code if isinstance(stopped.value, SystemExit) else None
    assert code is None or isinstance(code, int)
    return stdout.buffer.getvalue(), stderr.buffer.getvalue(), code


@pytest.mark.parametrize(
    ("name", "code"),
    [
        ("success", None),
        ("tool_request", None),
        ("usage_missing", None),
        ("malformed", ErrorCode.RUNTIME_STREAM_INCOMPLETE),
        ("partial_stream", ErrorCode.RUNTIME_CRASHED),
        ("crash", ErrorCode.RUNTIME_CRASHED),
        ("exit0_no_terminal", ErrorCode.RUNTIME_STREAM_INCOMPLETE),
        ("timeout", ErrorCode.RUNTIME_TIMEOUT),
        ("cancel_ignored", ErrorCode.CANCEL_IGNORED),
        ("resume_unsupported", ErrorCode.RUNTIME_CRASHED),
    ],
)
def test_ten_synthetic_scenarios(
    tmp_path: Path,
    name: str,
    code: ErrorCode | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    wire, stderr, exit_code = fixture_output(tmp_path, name, monkeypatch)
    limits = SessionLimits(wall_timeout_seconds=0.15, poll_interval_seconds=0.05)
    harness = build(
        tmp_path,
        stdout=wire,
        stderr=stderr,
        exit_code=exit_code,
        limits=limits,
    )
    if name == "cancel_ignored":
        harness.child.ignore = True
        harness.cancel.set()
    events = list(harness.session.run())
    assert rt.validate_event_stream(events) == ()
    result = harness.session.result()
    terminals = [event for event in events if isinstance(event, (rt.SessionCompleted, rt.SessionFailed))]
    assert len(terminals) == 1
    assert [event.seq for event in events] == list(range(1, len(events) + 1))
    assert isinstance(events[-2], rt.UsageReported)
    assert events[-2].usage == result.usage
    if name == "success":
        assert result.usage.status is rt.UsageStatus.REPORTED
        assert result.usage.input_tokens == 1200
    else:
        assert result.usage.status is rt.UsageStatus.UNKNOWN
        assert result.usage.input_tokens is None
    assert (None if result.failure is None else result.failure.code) == code
    assert harness.session.result() is result
    assert harness.child.close_count == 1
    assert not list(harness.session.identity_dir.glob("*.json"))
    if name == "cancel_ignored":
        assert [event.signal for event in events if isinstance(event, rt.CancelIgnored)] == [
            "SIGINT",
            "SIGTERM",
        ]
        assert harness.child.sent == [signal.SIGINT, signal.SIGTERM, signal.SIGKILL]
        assert harness.child.pump_count > 10  # cancellation continues draining


def test_usage_is_preserved_on_crash(tmp_path: Path) -> None:
    harness = build(tmp_path, exit_code=7)
    usage = dataclasses.replace(
        rt.unknown_usage(), input_tokens=31, status=rt.UsageStatus.ESTIMATED, source="estimated:prompt"
    )
    harness.parser.outcome = dataclasses.replace(harness.parser.outcome, usage=usage)
    result = harness.session.result()
    assert result.failure is not None
    assert result.failure.code == ErrorCode.RUNTIME_CRASHED
    assert result.usage.input_tokens == 31
    assert result.usage.status is rt.UsageStatus.ESTIMATED
    assert isinstance(list(harness.session.run())[-2], rt.UsageReported)


@pytest.mark.parametrize("broken_finish", [False, True])
def test_partial_stream_usage_survives_unknown_or_broken_finish(tmp_path: Path, broken_finish: bool) -> None:
    class PartialParser(WireParser):
        @override
        def finish(self, exit_code):
            if broken_finish:
                raise ValueError("truncated final usage")
            return dataclasses.replace(self.outcome, usage=rt.unknown_usage())

    harness = build(
        tmp_path,
        parser=PartialParser(),
        exit_code=7,
        stdout=(b'{"type":"usage_reported","usage":{"input_tokens":31},"cumulative":true}\n'),
    )
    result = harness.session.result()
    assert result.failure is not None
    assert result.usage.input_tokens == 31
    assert isinstance(list(harness.session.run())[-2], rt.UsageReported)


@pytest.mark.parametrize("ignore", [False, True])
def test_native_completion_grace_stops_lingering_child_without_changing_success(
    tmp_path: Path, ignore: bool
) -> None:
    harness = build(
        tmp_path,
        exit_code=None,
        limits=SessionLimits(
            result_grace_seconds=0.1,
            poll_interval_seconds=0.05,
        ),
    )
    harness.child.ignore = ignore
    events = list(harness.session.run())
    assert rt.validate_event_stream(events) == ()
    assert not any(isinstance(event, rt.CancelIgnored) for event in events)
    result = harness.session.result()
    assert result.outcome == "completed"
    assert result.lingered
    assert result.exit.exit_code == 0
    assert result.exit.signal is None


@pytest.mark.parametrize("trigger", ["exit", "cancelled", "wall_timeout", "parser_invalid", "capture_failed"])
def test_stop_classification_and_events_remain_valid_with_malformed_output(
    tmp_path: Path, trigger: str
) -> None:
    harness = build(
        tmp_path,
        stdout=b"not json\n",
        exit_code=None,
        limits=SessionLimits(wall_timeout_seconds=0.1, poll_interval_seconds=0.05),
    )
    harness.child.ignore = True
    if trigger == "exit":
        harness.child.code = 7
    elif trigger == "cancelled":
        harness.cancel.set()
    elif trigger == "capture_failed":
        harness.writer.failed = True
    if trigger == "wall_timeout":
        harness.session._start()
        harness.clock.advance(0.1)
    events = list(harness.session.run())
    result = harness.session.result()
    assert rt.validate_event_stream(events) == ()
    assert result.failure is not None
    expected = {
        "exit": ErrorCode.RUNTIME_CRASHED,
        "cancelled": ErrorCode.CANCEL_IGNORED,
        "wall_timeout": ErrorCode.RUNTIME_TIMEOUT,
        "parser_invalid": ErrorCode.RUNTIME_STREAM_INCOMPLETE,
        "capture_failed": ErrorCode.RUNTIME_STREAM_INCOMPLETE,
    }
    assert result.failure.code == expected[trigger]
    ignored = [event for event in events if isinstance(event, rt.CancelIgnored)]
    assert len(ignored) == (2 if trigger in ("cancelled", "wall_timeout") else 0)


def test_timing_sidecar_shares_the_capture_reservation(tmp_path: Path) -> None:
    harness = build(tmp_path)
    result = harness.session.result()
    assert result.outcome == "completed"
    sidecar = harness.writer.step_dir / "stream.times"
    assert sidecar.read_text() == f"0.0 {len(harness.child.stdout)}\n"
    assert sidecar.stat().st_mode & 0o777 == 0o600


def test_input_broken_pipe_and_native_result_are_compatible(tmp_path: Path) -> None:
    harness = build(tmp_path)
    harness.child.broken_stdin = True
    result = harness.session.result()
    assert result.outcome == "completed"
    assert harness.child.stdin_closed


def test_quiet_runtime_survives_idle_suspicion_until_wall_deadline(tmp_path: Path) -> None:
    harness = build(
        tmp_path,
        stdout=b"",
        exit_code=None,
        limits=SessionLimits(
            wall_timeout_seconds=0.3,
            idle_timeout_seconds=0.05,
            poll_interval_seconds=0.05,
        ),
    )
    checked: list[bool] = []

    def heartbeat(_: float) -> None:
        if 0.15 <= harness.clock.monotonic() < 0.3:
            assert harness.session.idle_suspected
            assert harness.child.sent == []
            checked.append(True)

    harness.sleeper.on_sleep = heartbeat
    result = harness.session.result()
    assert checked
    assert result.failure is not None
    assert result.failure.code == ErrorCode.RUNTIME_TIMEOUT


def test_poll_interval_is_converted_at_input_boundary_once() -> None:
    assert SessionLimits.from_poll_interval_ms(2000).poll_interval_seconds == 2.0


@pytest.mark.parametrize("dependency", ["binary", "wrapper", "interpreter", "launch_dependency"])
def test_mutated_launch_dependencies_refused_without_binding(tmp_path: Path, dependency: str) -> None:
    """Current launcher has no immutable exec binding: enforcing use must refuse even valid locators."""
    harness = build(tmp_path / "session")
    executable = tmp_path / dependency
    canary = tmp_path / "canary"
    executable.write_text("verified version\n")
    # Verification/exec barrier: same version string, replacement security-relevant contents.
    executable.write_text(f"verified version\ntouch {canary}\n")
    ownership = dataclasses.replace(harness.command.ownership, kind="pgroup_best_effort")
    command = dataclasses.replace(harness.command, argv=(str(executable),), ownership=ownership)
    harness.session.command, harness.session.ownership = command, ownership
    harness.session.runner = TrustedProcessRunner(allow_pgroup_best_effort=True, require_exec_binding=True)
    with pytest.raises(CapabilityUnavailable) as error:
        harness.session.result()
    assert error.value.code == ErrorCode.SANDBOX_UNAVAILABLE
    assert not canary.exists()
    assert not harness.session.identity_dir.exists()
    assert (
        harness.budget.snapshot(harness.writer.step_dir.parent.parent, min_free_bytes=0).reserved_bytes == 0
    )


def test_base_plugin_contract_harness_runs_runtime_cases(tmp_path: Path) -> None:
    # plugin_api.testing.runtime_contract_suite is absent in the frozen dependency and outside this write set.
    def terminal_and_result() -> None:
        harness = build(tmp_path)
        result = harness.session.result()
        assert result.outcome == "completed"
        assert harness.session.result() is result

    report = run_contract_suite(
        "runtime:synthetic", [ContractCase("terminal-and-result", terminal_and_result)]
    )
    report.raise_for_failures()
    assert report.passed == ("terminal-and-result",)


def test_fake_runtime_scenarios_use_existing_unchanged_port(tmp_path: Path) -> None:
    from fakes.runtimes import runtime_request

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    runtime = FakeRuntime(
        state_dir=tmp_path / "state", scenario=FIXTURES / "usage_missing.toml", allow_pgroup_best_effort=True
    )
    handle = runtime.start(runtime_request(workdir))
    result = runtime.result(handle)
    assert result.outcome == "completed"
    assert result.usage.status is rt.UsageStatus.UNKNOWN
    assert runtime.result(handle) is result


def test_grok_and_cursor_adapters_satisfy_port_and_refusal_contracts(tmp_path: Path) -> None:
    from dataclasses import replace

    from fakes.runtimes import runtime_request
    from skm.adapters.runtimes.cursor.runtime import CursorRuntime
    from skm.adapters.runtimes.grok.runtime import GrokRuntime
    from skm.adapters.runtimes.grok.stream_parser import GrokStreamParser
    from skm.kernel.isolation import IsolationProfile

    workdir = tmp_path / "workdir"
    workdir.mkdir()
    base_req = runtime_request(workdir)

    cursor_rt = CursorRuntime(environ={})
    cursor_caps = cursor_rt.capabilities()
    assert cursor_caps.runtime_id == "cursor"
    assert cursor_caps.status(rt.Capability.HEADLESS_EXECUTION) is rt.CapabilityStatus.UNKNOWN
    with pytest.raises(CapabilityUnavailable) as cursor_err:
        cursor_rt.start(replace(base_req, runtime_id="cursor"))
    assert cursor_err.value.code is ErrorCode.CAPABILITY_UNAVAILABLE
    assert cursor_err.value.details.get("capability") == "headless_execution"

    grok_rt = GrokRuntime(state_dir=tmp_path / "grok-state", environ={})
    grok_caps = grok_rt.capabilities()
    assert grok_caps.runtime_id == "grok"
    assert grok_caps.status(rt.Capability.CONFIG_ISOLATION) is rt.CapabilityStatus.UNSUPPORTED
    with pytest.raises(CapabilityUnavailable) as grok_err:
        grok_rt.start(replace(base_req, runtime_id="grok", isolation_profile=IsolationProfile.WORKTREE))
    assert grok_err.value.code is ErrorCode.SANDBOX_UNAVAILABLE

    grok_fixture = (
        Path(__file__).resolve().parents[2] / "fixtures/runtimes/grok/streaming-messages-json.jsonl"
    ).read_bytes()
    parser = GrokStreamParser(runtime_version="0.1.0")
    emitted: list[rt.SessionEvent] = []
    for raw_line in grok_fixture.splitlines():
        emitted.extend(parser.feed(raw_line))
    assert parser.saw_terminal() is True
    outcome = parser.finish(0)
    assert outcome.is_error is False
    assert outcome.final_text == "checked"
    assert outcome.usage.cost_usd_micros is None
    assert outcome.usage.source == "grok.stream"
    assert any(isinstance(ev, rt.UsageReported) for ev in emitted)
