"""The early fake uses the final port, real processes, and honest synthetic observations."""

from __future__ import annotations

import dataclasses
import json
import runpy
import signal
import threading
from datetime import timedelta
from pathlib import Path
from time import monotonic as elapsed
from typing import Any, cast
from unittest.mock import Mock
from uuid import UUID, uuid4

import pytest

from fakes.clock import FakeMonotonic, FrozenClock
from fakes.runtimes import RUN, runtime_request
from skm.adapters.runtimes.fake import runtime as fake_runtime
from skm.adapters.runtimes.fake.runtime import FakeRuntime, RuntimeStartError
from skm.adapters.runtimes.fake.scenarios import ScenarioError, load_scenario, select_scenario
from skm.bootstrap.runtimes import RUNTIME_FACTORIES
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, CapabilityUnavailable, NotFound
from skm.kernel.ids import HostId
from skm.kernel.isolation import PluginIsolationProfile
from skm.modules.runtimes.domain.classes import RoleId
from skm.modules.runtimes.domain.detection import DetectProbe
from skm.modules.runtimes.domain.observation import observation_to_json
from skm.modules.runtimes.domain.result import RuntimeResult, result_to_json, validate_result_observation
from skm.modules.runtimes.domain.session_events import (
    CancelIgnored,
    SessionCompleted,
    SessionFailed,
    SessionStarted,
    TextDelta,
    UsageReported,
    session_event_to_json,
    validate_event_stream,
)
from skm.modules.runtimes.domain.usage import UsageStatus
from skm.modules.runtimes.ports import AgentRuntime, SessionHandle
from skm.platform.process.identity import ProcessIdentity, group_alive, identity_of
from skm.platform.process.ownership import OwnershipUnavailable
from skm.platform.process.runner import ProcessHandle, TerminationResult
from skm.platform.schema.registry import SchemaRegistry
from support.runtime_bootstrap import TestRuntimeRegistry

FIXTURES = Path(__file__).resolve().parents[3] / "fixtures/runtimes/fake"
EPOCH = UUID("01928f61-4444-7aaa-8bbb-2c3d4e5f6a7c")


@pytest.fixture(scope="module")
def schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def runtime(tmp_path: Path, name: str = "success", **kwargs: Any) -> FakeRuntime:
    return FakeRuntime(
        allow_pgroup_best_effort=True,
        state_dir=tmp_path / "state",
        scenario=FIXTURES / f"{name}.toml",
        **kwargs,
    )


def workdir(tmp_path: Path) -> Path:
    path = tmp_path / "workdir"
    path.mkdir(exist_ok=True)
    return path


def valid_result(result: RuntimeResult, schemas: SchemaRegistry, step: str) -> None:
    assert result.observation is not None
    assert validate_result_observation(result, request_id=UUID(step)) == ()
    assert schemas.validate("urn:skm:runtimes:runtime-result:v1", result_to_json(result)) == ()
    assert (
        schemas.validate("urn:skm:runtimes:runtime-observation:v1", observation_to_json(result.observation))
        == ()
    )


def test_success_final_port_events_and_minimal_observation(tmp_path: Path, schemas: SchemaRegistry) -> None:
    clock, monotonic = FrozenClock(), FakeMonotonic()
    fake: AgentRuntime = runtime(tmp_path, clock=clock, monotonic=monotonic, clock_domain_id=EPOCH)
    req = runtime_request(workdir(tmp_path))
    handle = fake.start(req)
    assert handle.pid is not None
    assert handle.pid > 0
    assert handle.ownership is not None
    assert handle.ownership.owner is req.process_owner
    assert handle.ownership.kind == "pgroup_best_effort"
    assert handle.ownership.ref == str(handle.pid)
    monotonic.advance(0.042)
    events = list(fake.events(handle))
    observed_at = clock.now()
    monotonic.advance(10)
    clock.advance(timedelta(hours=1))
    result = fake.result(handle)
    assert isinstance(events[-1], SessionCompleted)
    assert validate_event_stream(events) == ()
    for event in events:
        assert schemas.validate("urn:skm:runtimes:session-event:v1", session_event_to_json(event)) == ()
    valid_result(result, schemas, req.request_id)
    assert result.outcome == "completed"
    assert result.model == "fake-model"
    assert result.usage.status is UsageStatus.REPORTED
    assert result.usage.input_tokens == 1200
    assert result.usage.cost_usd_micros is None  # provider claim is not catalog-computed money
    assert result.observation is not None
    obs = result.observation
    assert obs.request_id == UUID(req.request_id)
    assert obs.timing.clock_domain_id == EPOCH
    assert obs.timing.duration_ms == 42
    assert obs.timing.first_observed_at == obs.timing.last_observed_at == observed_at
    assert obs.binding.provider_reported_model == result.model
    assert obs.binding.model_source == "provider_stream"
    assert obs.binding.runtime_version is obs.binding.adapter_version is None
    assert obs.binding.executable_sha256 is obs.binding.verification_key is None
    assert obs.capture.coverage == "complete"
    assert obs.capture.bytes_seen is not None
    assert obs.capture.bytes_seen > 0
    assert obs.capture.bytes_seen == obs.capture.bytes_retained
    assert obs.capture.bytes_dropped == 0
    assert obs.capture.truncated is False
    assert obs.tools.coverage == "partial"
    assert obs.tools.observed_calls == 1
    assert (Path(req.workdir) / "src/app.py").read_text().endswith("return 42\n")
    assert identity_of(handle.pid) is None
    assert not group_alive(handle.pid)
    assert fake.result(handle) is result
    assert list(fake.events(handle)) == events
    assert fake.result(handle).observation is obs


def test_unreported_model_tools_usage_stay_unknown(tmp_path: Path, schemas: SchemaRegistry) -> None:
    fake = runtime(tmp_path, "unreported")
    req = runtime_request(workdir(tmp_path))
    result = fake.result(fake.start(req))
    valid_result(result, schemas, req.request_id)
    assert result.model is None
    assert req.model == "resolved-model"
    assert result.usage.status is UsageStatus.UNKNOWN
    assert result.usage.input_tokens is result.usage.output_tokens is result.usage.cost_usd_micros is None
    assert result.observation is not None
    assert result.observation.binding.provider_reported_model is None
    assert result.observation.binding.model_source == "unavailable"
    assert result.observation.tools.coverage == "unavailable"
    assert result.observation.tools.observed_calls is None


def test_cancel_at_kill_boundary_reaps_child_preserves_work_and_freezes_result(
    tmp_path: Path,
    schemas: SchemaRegistry,
) -> None:
    fake = runtime(tmp_path, "kill-boundary")
    req = runtime_request(workdir(tmp_path))
    handle = fake.start(req)
    try:
        for event in fake.events(handle):
            if isinstance(event, TextDelta) and event.text == "kill boundary reached":
                break
        before = elapsed()
        cancelled = fake.cancel(handle, grace_seconds=0.05)
        assert elapsed() - before < 5  # cancellation must not wait for the 30-second wall timeout
        assert cancelled.stopped
        assert cancelled.ignored
        assert cancelled.signal_used == "SIGKILL"
        events = list(fake.events(handle))
        assert any(isinstance(event, CancelIgnored) for event in events)
        assert isinstance(events[-1], SessionFailed)
        assert validate_event_stream(events) == ()
        result = fake.result(handle)
        valid_result(result, schemas, req.request_id)
        assert result.outcome == "cancelled"
        assert result.failure is not None
        assert result.failure.code is ErrorCode.CANCEL_IGNORED
        assert result.exit.signal == "SIGKILL"
        assert result.observation is not None
        assert result.observation.capture.bytes_seen
        assert fake.cancel(handle, grace_seconds=0.05) is cancelled
        assert fake.result(handle) is result
        assert handle.pid is not None
        assert identity_of(handle.pid) is None
        assert not group_alive(handle.pid)
        assert (Path(req.workdir) / "before-cancel.txt").read_text() == "preserved\n"
        assert not (Path(req.workdir) / "after-cancel.txt").exists()
    finally:
        fake.cancel(handle, grace_seconds=0)


def test_regular_cancel_and_injected_timeout(tmp_path: Path, schemas: SchemaRegistry) -> None:
    for timeout in (False, True):
        mono = FakeMonotonic()
        fake = runtime(tmp_path, "timeout", monotonic=mono)
        req = runtime_request(workdir(tmp_path), step=uuid4())
        handle = fake.start(req)
        try:
            assert isinstance(next(fake.events(handle)), SessionStarted)
            if timeout:
                mono.advance(31)
            else:
                assert fake.cancel(handle, grace_seconds=0.2).stopped
            result = fake.result(handle)
            valid_result(result, schemas, req.request_id)
            assert result.failure is not None
            assert result.failure.code is (
                ErrorCode.RUNTIME_TIMEOUT if timeout else ErrorCode.SESSION_CANCELLED
            )
            assert validate_event_stream(list(fake.events(handle))) == ()
        finally:
            fake.cancel(handle, grace_seconds=0)


@pytest.mark.parametrize("scenario", ["exit0-no-terminal", "crash"])
def test_no_success_without_native_terminal(tmp_path: Path, schemas: SchemaRegistry, scenario: str) -> None:
    fake = runtime(tmp_path, scenario)
    req = runtime_request(workdir(tmp_path))
    result = fake.result(fake.start(req))
    valid_result(result, schemas, req.request_id)
    assert result.outcome == "failed"
    assert result.failure is not None
    expected = ErrorCode.RUNTIME_CRASHED if scenario == "crash" else ErrorCode.RUNTIME_STREAM_INCOMPLETE
    assert result.failure.code is expected
    assert result.final_text == ""


def test_script_rework_review_question_and_persisted_run_role_task_counters(
    tmp_path: Path,
    schemas: SchemaRegistry,
) -> None:
    def call(role: RoleId, task: str = "P1.1/U1", run: UUID = RUN) -> dict[str, Any]:
        # Reconstructing the adapter must preserve invocation counts, as a worker restart does.
        fake = FakeRuntime(
            allow_pgroup_best_effort=True, state_dir=tmp_path / "state", script=FIXTURES / "script.toml"
        )
        req = runtime_request(workdir(tmp_path), step=uuid4(), run=run, role=role, task_key=task)
        result = fake.result(fake.start(req))
        payload = json.loads(result.final_text)
        assert schemas.validate(req.result_schema_urn or "", payload) == ()
        return payload

    assert call(RoleId.EXECUTOR)["status"] == "done"
    red = runpy.run_path(str(workdir(tmp_path) / "src/app.py"))
    with pytest.raises(AssertionError):
        assert red["answer"]() == 42
    assert call(RoleId.REVIEWER)["verdict"] == "red"
    assert call(RoleId.EXECUTOR)["status"] == "done"
    green = runpy.run_path(str(workdir(tmp_path) / "src/app.py"))
    assert green["answer"]() == 42
    assert call(RoleId.REVIEWER)["verdict"] == "green"
    assert call(RoleId.REVIEWER, task="other-task")["verdict"] == "red"
    assert call(RoleId.REVIEWER, run=uuid4())["verdict"] == "red"
    question = call(RoleId.EXECUTOR, task="P-question")
    assert question["status"] == "blocked"
    assert question["questions"][0]["blocking"]
    # Execution tests consume this fixture with advisor.enabled=false or question_policy=queue.


def test_same_script_is_deterministic_with_injected_clocks(tmp_path: Path) -> None:
    outcomes = []
    for name in ("one", "two"):
        root = tmp_path / name
        root.mkdir()
        fake = FakeRuntime(
            allow_pgroup_best_effort=True,
            state_dir=root / "state",
            script=FIXTURES / "script.toml",
            clock=FrozenClock(),
            monotonic=FakeMonotonic(),
            clock_domain_id=EPOCH,
        )
        req = runtime_request(workdir(root))
        outcomes.append(result_to_json(fake.result(fake.start(req))))
    assert outcomes[0] == outcomes[1]


@pytest.mark.parametrize("action", ["write_file", "delete_file"])
@pytest.mark.parametrize("path", ["../outside.txt", "/outside.txt"])
def test_escape_paths_are_refused_before_spawn(tmp_path: Path, action: str, path: str) -> None:
    scenario = tmp_path / "escape.toml"
    scenario.write_text(f'scenario="escape"\n[[step]]\naction="{action}"\npath="{path}"\ncontent="bad"\n')
    with pytest.raises(ScenarioError, match="relative to workdir"):
        load_scenario(scenario)


@pytest.mark.parametrize("action", ["write_file", "delete_file"])
@pytest.mark.parametrize("directory", [False, True])
def test_symlinks_cannot_mutate_outside_workdir(tmp_path: Path, action: str, directory: bool) -> None:
    wd = workdir(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "kept.txt"
    target.write_text("keep")
    (wd / "link").symlink_to(outside if directory else target, target_is_directory=directory)
    path = "link/kept.txt" if directory else "link"
    scenario = tmp_path / "escape.toml"
    scenario.write_text(f'scenario="escape"\n[[step]]\naction="{action}"\npath="{path}"\ncontent="bad"\n')
    fake = FakeRuntime(allow_pgroup_best_effort=True, state_dir=tmp_path / "state", scenario=scenario)
    req = runtime_request(wd)
    result = fake.result(fake.start(req))
    assert result.outcome == "failed"
    assert result.exit.exit_code == 2
    assert target.read_text() == "keep"


def test_unknown_scenario_and_bad_inputs_are_explicit(tmp_path: Path) -> None:
    with pytest.raises(ScenarioError, match="cannot read fake input"):
        load_scenario(tmp_path / "missing.toml")
    script = tmp_path / "script.toml"
    script.write_text('[[rule]]\nrole="reviewer"\nscenario="missing.toml"\n')
    with pytest.raises(ScenarioError, match="unknown fake scenario"):
        select_scenario(script, role="executor", task_key="P1", invocation=1)
    script.write_text("scenario = [")
    with pytest.raises(ScenarioError, match="cannot read fake input"):
        load_scenario(script)
    script.write_bytes(b'scenario = "\xff"\n')
    with pytest.raises(ScenarioError, match="cannot read fake input"):
        load_scenario(script)
    # The child receives the document as JSON: a TOML-only value (a datetime) is refused when read.
    script.write_text('scenario = "dated"\nwhen = 2026-01-01T00:00:00Z\n')
    with pytest.raises(ScenarioError, match="cannot read fake input"):
        load_scenario(script)


@pytest.mark.parametrize(
    "body",
    [
        "[[step]]\naction=[]",
        '[[step]]\naction="run_shell"',
        '[[step]]\naction="sleep_ms"\nms=-1',
        '[[step]]\naction="raw"\ndata=1',
        '[[step]]\naction="emit"\nevent="bad"',
        '[[step]]\naction="write_file"\npath="x"\ncontent=1',
        '[[step]]\naction="exit"\nexit_code=256',
        'ignore_signals="yes"',
        "exit_code=true",
        "usage=[]",
        "[result]\ntext=42",
    ],
)
def test_invalid_scenario_shapes_are_explicit(tmp_path: Path, body: str) -> None:
    path = tmp_path / "invalid.toml"
    path.write_text('scenario="invalid"\n' + body + "\n")
    with pytest.raises(ScenarioError):
        load_scenario(path)


@pytest.mark.parametrize(
    "wire",
    [
        "not json\n",
        '{"type":"text_delta","text":"tail"}',
        '{"type":"text_delta","channel":"invalid","text":"bad"}\n',
        '{"type":"session_completed"}\n',
        '{"type":"tool_requested","call_id":"c1","tool":"Edit","args_preview":42}\n',
        '{"type":"session_started","model":"invalid model"}\n',
    ],
)
def test_parser_failures_do_not_become_complete_capture_or_success(
    tmp_path: Path,
    schemas: SchemaRegistry,
    wire: str,
) -> None:
    path = tmp_path / "invalid-wire.toml"
    path.write_text('scenario="invalid-wire"\n[[step]]\naction="raw"\ndata=' + json.dumps(wire) + "\n")
    fake = FakeRuntime(allow_pgroup_best_effort=True, state_dir=tmp_path / "state", scenario=path)
    req = runtime_request(workdir(tmp_path))
    result = fake.result(fake.start(req))
    valid_result(result, schemas, req.request_id)
    assert result.outcome == "failed"
    assert result.observation is not None
    assert result.observation.capture.coverage == "partial"
    assert result.observation.capture.parser_flags


def test_stdout_and_stderr_bytes_are_counted_once_and_retention_is_bounded(
    tmp_path: Path,
    schemas: SchemaRegistry,
) -> None:
    wd = workdir(tmp_path)
    (wd / "link").symlink_to(tmp_path)
    wire = json.dumps({"type": "text_delta", "text": "hello Ω"}, ensure_ascii=False) + "\n"
    scenario = tmp_path / "capture.toml"
    scenario.write_text(
        'scenario="capture"\n[[step]]\naction="raw"\ndata='
        + json.dumps(wire)
        + '\n[[step]]\naction="write_file"\npath="link/escape"\ncontent="bad"\n'
    )
    stderr = b"fake scenario error: scenario file path escapes workdir through a symlink\n"
    seen = len(wire.encode("utf-8")) + len(stderr)
    for limit in (1024, 32):
        fake = FakeRuntime(allow_pgroup_best_effort=True, state_dir=tmp_path / "state", scenario=scenario)
        req = runtime_request(wd, step=uuid4())
        req = dataclasses.replace(req, limits=dataclasses.replace(req.limits, max_output_bytes=limit))
        result = fake.result(fake.start(req))
        valid_result(result, schemas, req.request_id)
        assert result.observation is not None
        capture = result.observation.capture
        assert capture.bytes_seen == seen
        assert capture.bytes_retained == min(limit, seen)
        assert capture.bytes_dropped == max(0, seen - limit)
        assert capture.truncated is (limit < seen)
        assert capture.coverage == ("partial" if limit < seen else "complete")


def test_utc_can_jump_backwards_without_changing_monotonic_duration(tmp_path: Path) -> None:
    path = tmp_path / "clock.toml"
    path.write_text("""scenario="clock"
[[step]]
action="emit"
event={type="session_started"}
[[step]]
action="sleep_ms"
ms=500
[result]
text="synthetic result"
""")
    clock, mono = FrozenClock(), FakeMonotonic()
    fake = FakeRuntime(
        allow_pgroup_best_effort=True,
        state_dir=tmp_path / "state",
        scenario=path,
        clock=clock,
        monotonic=mono,
    )
    handle = fake.start(runtime_request(workdir(tmp_path)))
    assert isinstance(next(fake.events(handle)), SessionStarted)
    clock.advance(-timedelta(days=1))
    mono.advance(0.042)
    result = fake.result(handle)
    assert result.observation is not None
    timing = result.observation.timing
    assert timing.first_observed_at is not None
    assert timing.last_observed_at is not None
    assert timing.last_observed_at < timing.first_observed_at
    assert timing.duration_ms == 42


def test_missing_workdir_wrong_runtime_and_foreign_handle_are_refused(tmp_path: Path) -> None:
    fake = runtime(tmp_path)
    with pytest.raises(ScenarioError, match="workdir does not exist"):
        fake.start(runtime_request(tmp_path / "missing"))
    req = runtime_request(workdir(tmp_path))
    handle = fake.start(req)
    try:
        with pytest.raises(ScenarioError, match="already started"):
            fake.start(req)
        with pytest.raises(ValueError, match="does not belong"):
            runtime(tmp_path).result(handle)
        with pytest.raises(ValueError, match="does not belong"):
            fake.cancel(dataclasses.replace(handle, pid=12345), grace_seconds=0)
    finally:
        fake.cancel(handle, grace_seconds=0)


def test_fake_requires_explicit_test_composition_and_claims_no_live_installation(tmp_path: Path) -> None:
    assert "fake" not in RUNTIME_FACTORIES
    settings = json.loads((FIXTURES.parents[3] / "src/skm/schemas/settings/runtimes.v1.json").read_text())
    assert "fake" not in settings["properties"]["allowed"]["default"]
    assert TestRuntimeRegistry().ids() == frozenset()
    with pytest.raises(NotFound):
        TestRuntimeRegistry().get("fake")
    fake = runtime(tmp_path)
    registry = TestRuntimeRegistry(fake)
    assert registry.ids() == frozenset({"fake"})
    assert registry.get("fake") is fake
    probe = DetectProbe(HostId(RUN), None, (), 5)
    detected = fake.detect(probe)
    assert detected.version is detected.binary_locator is None
    assert "synthetic" in detected.details["evidence"]
    for record in fake.capabilities().records.values():
        assert record.evidence.startswith("fixture:")
        assert record.verification_context is record.last_verified_at is None
    assert fake.self_loaded_context(runtime_request(workdir(tmp_path))) == ()


def controlled_session(
    tmp_path: Path, schemas: SchemaRegistry
) -> tuple[FakeRuntime, fake_runtime._Session, SessionHandle, Mock]:
    """Drive lifecycle failures without an OS process or a racing collector thread."""
    clock, mono = FrozenClock(), FakeMonotonic()
    fake = runtime(tmp_path, clock=clock, monotonic=mono)
    req = runtime_request(workdir(tmp_path))
    process = Mock(spec=ProcessHandle)
    process.pid = process.pgid = 73001  # diagnostic only: this double never sends an OS signal
    process.identity = ProcessIdentity(process.pid, 1, None)
    process.wait.return_value = None
    process.terminate.return_value = TerminationResult(signal.SIGTERM, True, False, None)
    handle = SessionHandle("fake", req.request_id, process.pid, 1, clock.now(), None)
    session = fake_runtime._Session(
        req,
        load_scenario(FIXTURES / "success.toml"),
        mono.monotonic(),
        clock,
        mono,
        EPOCH,
        schemas,
        process=cast("ProcessHandle", process),
        handle=handle,
    )
    fake._sessions[req.request_id] = session
    session.feed(b'{"type":"session_started","model":"fake-model"}\n', stdout=True)
    session.feed(b'{"type":"usage_reported","usage":{"input_tokens":42}}\n', stdout=True)
    return fake, session, handle, process


def assert_cleanup_failed(
    fake: FakeRuntime, session: fake_runtime._Session, handle: SessionHandle, schemas: SchemaRegistry
) -> RuntimeResult:
    assert session.finished.is_set()
    result = fake.result(handle)
    valid_result(result, schemas, handle.request_id)
    assert result.outcome == "failed"
    assert result.failure is not None
    assert result.failure.code is ErrorCode.RUNTIME_CRASHED
    assert result.failure.details["reason"] == "cleanup_unconfirmed"
    assert not result.failure.retryable
    assert result.observation is not None
    assert result.observation.timing.duration_ms is None
    assert result.observation.capture.coverage == "partial"
    assert "capture_gap" in result.observation.capture.gaps
    assert result.usage.status is UsageStatus.REPORTED
    assert result.usage.input_tokens == 42
    events = list(fake.events(handle))
    assert validate_event_stream(events) == ()
    assert sum(isinstance(event, (SessionFailed, SessionCompleted)) for event in events) == 1
    assert isinstance(events[-2], UsageReported)
    assert events[-2].usage is result.usage
    assert fake.result(handle) is result
    assert not fake.cancel(handle, grace_seconds=0).stopped
    return result


def test_sigint_ignored_sigterm_honored_is_session_cancelled(tmp_path: Path, schemas: SchemaRegistry) -> None:
    fake, session, handle, process = controlled_session(tmp_path, schemas)
    process.wait.side_effect = [None, -signal.SIGTERM]
    cancelled = fake.cancel(handle, grace_seconds=0.05)
    assert cancelled.stopped
    assert not cancelled.ignored
    assert cancelled.signal_used == "SIGTERM"
    result = fake.result(handle)
    valid_result(result, schemas, handle.request_id)
    assert result.failure is not None
    assert result.failure.code is ErrorCode.SESSION_CANCELLED
    assert result.usage.status is UsageStatus.REPORTED
    assert result.usage.input_tokens == 42
    events = list(fake.events(handle))
    assert [event.signal for event in events if isinstance(event, CancelIgnored)] == ["SIGINT"]
    assert validate_event_stream(events) == ()
    assert session.finished.is_set()
    assert fake.cancel(handle, grace_seconds=0) is cancelled


@pytest.mark.parametrize("path", ["natural", "cancel_probe", "cancel_reap", "timeout"])
@pytest.mark.parametrize("error_type", [ProcessLookupError, RuntimeError])
def test_wait_failure_is_terminal_and_preserves_cleanly_drained_capture(
    tmp_path: Path, schemas: SchemaRegistry, path: str, error_type: type[Exception]
) -> None:
    fake, session, handle, process = controlled_session(tmp_path, schemas)
    session.feed(b'{"type":"fake_result","final_text":"native success"}\n', stdout=True)
    session.record_stderr(b"diagnostic\n")
    seen = session.bytes_seen
    error = error_type("process_status_unknown: status consumed elsewhere")
    if path in ("natural", "cancel_probe"):
        process.wait.side_effect = error
    else:
        process.wait.side_effect = [None, error]
    if path == "timeout":
        cast("FakeMonotonic", session.monotonic).advance(31)
    if path.startswith("cancel"):
        assert not fake.cancel(handle, grace_seconds=0).stopped
    else:
        fake._collect(session)
    result = assert_cleanup_failed(fake, session, handle, schemas)
    assert result.observation is not None
    capture = result.observation.capture
    assert capture.bytes_seen == capture.bytes_retained == seen
    assert capture.bytes_dropped == 0
    assert capture.truncated is False
    assert capture.parser_flags == ()


@pytest.mark.parametrize("path", ["cancel", "timeout", "collector"])
@pytest.mark.parametrize("termination_raises", [False, True])
def test_cleanup_unconfirmed_degrades_observation_and_freezes_late_output(
    tmp_path: Path, schemas: SchemaRegistry, path: str, termination_raises: bool
) -> None:
    fake, session, handle, process = controlled_session(tmp_path, schemas)
    session.feed(b'{"type":"fake_result","final_text":"native success"}\n', stdout=True)
    if termination_raises:
        process.terminate.side_effect = RuntimeError("cleanup worker could not start")
    else:
        process.terminate.return_value = TerminationResult(
            signal.SIGKILL, False, True, "process_group_cleanup_unconfirmed"
        )
    if path == "timeout":
        cast("FakeMonotonic", session.monotonic).advance(31)
    elif path == "collector":
        process.wait.side_effect = RuntimeError("cleanup worker could not start")
    if path == "cancel":
        assert not fake.cancel(handle, grace_seconds=0).stopped
    else:
        fake._collect(session)
    result = assert_cleanup_failed(fake, session, handle, schemas)
    snapshot = (
        session.bytes_seen,
        bytes(session.capture),
        bytes(session.pending),
        tuple(session.events),
        session.first_at,
        session.last_at,
        session.usage,
        frozenset(session.flags),
    )
    cast("FrozenClock", session.clock).advance(timedelta(seconds=1))
    session.feed(b'{"type":"text_delta","text":"late stdout"}\n', stdout=True)
    session.feed(b"late stderr via feed", stdout=False)
    session.record_stderr(b"late stderr")
    assert snapshot == (
        session.bytes_seen,
        bytes(session.capture),
        bytes(session.pending),
        tuple(session.events),
        session.first_at,
        session.last_at,
        session.usage,
        frozenset(session.flags),
    )
    assert fake.result(handle) is result


def test_partial_stream_is_stream_incomplete_and_keeps_usage(tmp_path: Path, schemas: SchemaRegistry) -> None:
    fake, session, handle, process = controlled_session(tmp_path, schemas)
    session.feed(b'{"type":"text_delta","text":"unfinished"}', stdout=True)
    process.wait.return_value = 0
    fake._collect(session)
    result = fake.result(handle)
    valid_result(result, schemas, handle.request_id)
    assert result.failure is not None
    assert result.failure.code is ErrorCode.RUNTIME_STREAM_INCOMPLETE
    assert result.usage.status is UsageStatus.REPORTED
    assert result.usage.input_tokens == 42


@pytest.mark.parametrize(
    ("profile", "consent"),
    [
        ("container", False),
        ("container", True),
        ("landlock", False),
        ("landlock", True),
        ("example:contained", False),
        ("example:contained", True),
        ("worktree", False),
        ("none", False),
    ],
)
def test_required_containment_or_missing_consent_refuses_before_spawn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, profile: str, consent: bool
) -> None:
    fake = FakeRuntime(
        state_dir=tmp_path / "state",
        scenario=FIXTURES / "success.toml",
        allow_pgroup_best_effort=consent,
    )
    req = dataclasses.replace(
        runtime_request(workdir(tmp_path)), isolation_profile=cast("PluginIsolationProfile", profile)
    )
    spawning = Mock(side_effect=AssertionError("unexpected subprocess spawn"))
    monkeypatch.setattr(fake_runtime, "spawn", spawning)
    with pytest.raises(CapabilityUnavailable) as caught:
        fake.start(req)
    assert caught.value.code is ErrorCode.SANDBOX_UNAVAILABLE
    assert caught.value.details["profile"] == profile
    spawning.assert_not_called()
    assert fake._sessions == {}
    assert not (tmp_path / "state").exists()


@pytest.mark.parametrize("error", [OwnershipUnavailable("no pidfd support"), OSError("spawn failed")])
def test_spawn_errors_use_runtime_start_error_and_leave_no_session(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error: OSError
) -> None:
    fake = runtime(tmp_path)
    monkeypatch.setattr(fake_runtime, "spawn", Mock(side_effect=error))
    with pytest.raises(RuntimeStartError) as caught:
        fake.start(runtime_request(workdir(tmp_path)))
    assert caught.value.failure.code is ErrorCode.RUNTIME_CRASHED
    assert isinstance(caught.value, BackendUnavailable)
    assert caught.value.__cause__ is error
    assert fake._sessions == {}


@pytest.mark.parametrize("thread_name", ["skm-fake-73001", "skm-fake-input-73001"])
@pytest.mark.parametrize("cleanup_raises", [False, True])
def test_thread_start_failure_cleans_up_without_publishing_a_session(
    tmp_path: Path,
    schemas: SchemaRegistry,
    monkeypatch: pytest.MonkeyPatch,
    thread_name: str,
    cleanup_raises: bool,
) -> None:
    fake, session, _, process = controlled_session(tmp_path, schemas)
    fake._sessions.clear()
    monkeypatch.setattr(fake_runtime, "spawn", Mock(return_value=process))
    original = threading.Thread.start

    def fail(thread: threading.Thread) -> None:
        if thread.name == thread_name:
            raise RuntimeError("thread unavailable")
        original(thread)

    monkeypatch.setattr(threading.Thread, "start", fail)
    if cleanup_raises:
        process.terminate.side_effect = RuntimeError("cleanup thread unavailable")
    with pytest.raises(RuntimeStartError) as caught:
        fake.start(session.request)
    assert caught.value.failure.code is ErrorCode.RUNTIME_CRASHED
    if cleanup_raises:
        assert caught.value.failure.details["reason"] == "cleanup_unconfirmed"
    process.terminate.assert_called()
    assert fake._sessions == {}


def test_stdin_failure_finalizes_the_session_even_when_cleanup_raises(
    tmp_path: Path, schemas: SchemaRegistry
) -> None:
    fake, session, handle, process = controlled_session(tmp_path, schemas)
    process.write_stdin.side_effect = OSError("stdin failure")
    process.terminate.side_effect = RuntimeError("cleanup thread unavailable")
    fake._write_prompt(session)
    process.close_stdin.assert_called_once()
    assert_cleanup_failed(fake, session, handle, schemas)


def test_blocked_prompt_writer_does_not_block_start_or_the_collector(
    tmp_path: Path, schemas: SchemaRegistry, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake, prior_session, _, process = controlled_session(tmp_path, schemas)
    fake._sessions.clear()
    input_started, release_input, child_exited = threading.Event(), threading.Event(), threading.Event()
    mono = cast("FakeMonotonic", prior_session.monotonic)

    def write(data: bytes) -> None:
        assert len(data) == 2 * 1024 * 1024
        input_started.set()
        assert release_input.wait(5)

    def wait(timeout_seconds: float | None = None) -> int | None:
        return -signal.SIGTERM if child_exited.wait(timeout_seconds) else None

    def terminate(*, grace_seconds: float) -> TerminationResult:
        child_exited.set()
        return TerminationResult(signal.SIGTERM, True, False, None)

    process.write_stdin.side_effect = write
    process.wait.side_effect = wait
    process.terminate.side_effect = terminate
    monkeypatch.setattr(fake_runtime, "spawn", Mock(return_value=process))
    req = dataclasses.replace(prior_session.request, rendered_prompt="x" * (2 * 1024 * 1024))
    handle = fake.start(req)
    try:
        assert input_started.wait(2)
        assert not release_input.is_set()
        mono.advance(31)
        assert fake._session(handle).finished.wait(2)
        result = fake.result(handle)
        assert result.failure is not None
        assert result.failure.code is ErrorCode.RUNTIME_TIMEOUT
        assert not release_input.is_set()
    finally:
        release_input.set()
        fake.cancel(handle, grace_seconds=0)


def test_large_prompt_to_nonreading_child_does_not_block_start_or_timeout(tmp_path: Path) -> None:
    mono = FakeMonotonic()
    fake = runtime(tmp_path, "timeout", monotonic=mono)
    req = dataclasses.replace(runtime_request(workdir(tmp_path)), rendered_prompt="x" * (2 * 1024 * 1024))
    started = threading.Event()
    handles: list[SessionHandle] = []
    errors: list[BaseException] = []

    def start() -> None:
        try:
            handles.append(fake.start(req))
        except BaseException as error:  # noqa: BLE001 - return thread failures to the test caller
            errors.append(error)
        finally:
            started.set()

    starter = threading.Thread(target=start, daemon=True)
    starter.start()
    try:
        assert started.wait(5), "start blocked on the full prompt pipe"
        if errors:
            raise errors[0]
        handle = handles[0]
        assert isinstance(next(fake.events(handle)), SessionStarted)
        mono.advance(31)
        assert fake._session(handle).finished.wait(5)
        result = fake.result(handle)
        assert result.failure is not None
        assert result.failure.code is ErrorCode.RUNTIME_TIMEOUT
    finally:
        session = fake._sessions.get(req.request_id)
        if session is not None and session.handle is not None:
            fake.cancel(session.handle, grace_seconds=0)
        starter.join(5)
