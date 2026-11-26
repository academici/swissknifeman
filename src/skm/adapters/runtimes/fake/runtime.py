"""Explicitly constructed, subprocess-backed AgentRuntime for synthetic early M3 tests.

No production registration and no live capability evidence. The shared CLI machinery of
``_cli_session`` does not change this port; the early collector is local to fake.
"""

from __future__ import annotations

import json
import re
import signal
import sys
import threading
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from functools import cache
from hashlib import sha256
from pathlib import Path
from typing import TYPE_CHECKING, cast, override
from uuid import UUID, uuid4

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, CapabilityUnavailable
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    RuntimeCapabilities,
    SelfLoadedSource,
)
from skm.modules.runtimes.domain.detection import CancellationResult, DetectProbe
from skm.modules.runtimes.domain.error_rules import (
    ErrorClass,
    ErrorScope,
    ProcessOutcome,
    ProviderFailure,
    RuntimeSignals,
    classify,
    process_failure,
)
from skm.modules.runtimes.domain.ids import format_utc
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.domain.observation import (
    OBSERVATION_SCHEMA,
    CaptureObservation,
    ObservationBinding,
    ObservationTiming,
    RuntimeObservation,
    ToolVisibility,
)
from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership, validate_request
from skm.modules.runtimes.domain.result import ExitInfo, RuntimeResult
from skm.modules.runtimes.domain.session_events import (
    CancelIgnored,
    SessionCompleted,
    SessionEvent,
    SessionFailed,
    SessionStarted,
    StopReason,
    ToolRequested,
    UsageReported,
    session_event_from_json,
    session_event_to_json,
)
from skm.modules.runtimes.domain.usage import (
    SubagentUsage,
    UsageReport,
    UsageStatus,
    merge_usage,
    unknown_usage,
)
from skm.modules.runtimes.ports import SessionHandle
from skm.platform.process.runner import ProcessHandle, spawn
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.system_clock import SystemClock, SystemMonotonic

from .scenarios import Scenario, ScenarioError, load_scenario, select_scenario

if TYPE_CHECKING:
    from skm.kernel.clock import Clock, Monotonic
    from skm.kernel.json_types import JsonObject, JsonValue

__all__ = ["FakeRuntime"]


class RuntimeStartError(BackendUnavailable):
    """Adapter-local startup error; gateway callers can catch ``BackendUnavailable``."""

    @override
    def __init__(self, failure: ProviderFailure) -> None:
        self.failure = failure
        super().__init__(
            failure.code,
            failure.safe_message,
            details=failure.details,
            retryable=failure.retryable,
        )


@cache
def _schemas() -> SchemaRegistry:
    return SchemaRegistry.load_default()


def _digest(text: str) -> str:
    return "sha256:" + sha256(text.encode("utf-8")).hexdigest()


def _usage(data: JsonValue) -> UsageReport:
    if not isinstance(data, dict):
        raise ValueError("usage must be an object")
    # Owner contract: money is computed from catalog pricing, never copied from provider claims.
    return UsageReport(
        input_tokens=cast("int | None", data.get("input_tokens")),
        output_tokens=cast("int | None", data.get("output_tokens")),
        cache_read_tokens=cast("int | None", data.get("cache_read_tokens")),
        cache_write_tokens=cast("int | None", data.get("cache_write_tokens")),
        reasoning_tokens=cast("int | None", data.get("reasoning_tokens")),
        cost_usd_micros=None,
        status=UsageStatus.REPORTED,
        source="stream:result",
        subagents=SubagentUsage(used=None, disclosed=False),
    )


@dataclass
class _Session:
    request: AgentRequest
    scenario: Scenario
    started: float
    clock: Clock
    monotonic: Monotonic
    epoch: UUID
    schemas: SchemaRegistry
    process: ProcessHandle | None = None
    handle: SessionHandle | None = None
    events: list[SessionEvent] = field(default_factory=list[SessionEvent])
    lock: threading.RLock = field(default_factory=threading.RLock)
    finish_lock: threading.Lock = field(default_factory=threading.Lock)
    finished: threading.Event = field(default_factory=threading.Event)
    pending: bytearray = field(default_factory=bytearray)
    capture: bytearray = field(default_factory=bytearray)
    bytes_seen: int = 0
    flags: set[str] = field(default_factory=set[str])
    first_at: datetime | None = None
    last_at: datetime | None = None
    model: str | None = None
    session_ref: str | None = None
    usage: UsageReport = field(default_factory=unknown_usage)
    final_text: str | None = None
    result: RuntimeResult | None = None
    cancellation: CancellationResult | None = None

    def feed(self, chunk: bytes, *, stdout: bool) -> None:
        with self.lock:
            if self.result is not None:
                return
            at = self.clock.now()
            self.first_at = self.first_at or at
            self.last_at = at
            self.bytes_seen += len(chunk)
            remaining = max(0, self.request.limits.max_output_bytes - len(self.capture))
            admitted = chunk[:remaining]
            self.capture.extend(admitted)
            if stdout:
                self.pending.extend(admitted)
                while b"\n" in self.pending:
                    line, _, rest = self.pending.partition(b"\n")
                    self.pending = bytearray(rest)
                    self._line(bytes(line))

    def record_stderr(self, chunk: bytes) -> None:
        self.feed(chunk, stdout=False)

    def _line(self, line: bytes) -> None:
        try:
            data = json.loads(line.decode("utf-8"))
            if not isinstance(data, dict):
                raise ValueError("fake wire record must be an object")
            self._record(cast("JsonObject", data))
        except UnicodeError:
            self.flags.add("invalid_utf8")
        except (ValueError, KeyError, TypeError):
            self.flags.add("malformed_json")

    def _record(self, data: JsonObject) -> None:
        kind = data["type"]
        if kind == "fake_result":
            if self.final_text is not None or not isinstance(data.get("final_text"), str):
                raise ValueError("invalid fake terminal")
            self.final_text = cast("str", data["final_text"])
            return
        if self.final_text is not None or kind in ("session_completed", "session_failed", "cancel_ignored"):
            raise ValueError("only the wrapper assigns terminal/cancel events")
        data = {**data, "seq": len(self.events) + 1, "at": format_utc(self.clock.now())}
        if kind == "session_started":
            data.setdefault("session_ref", None)
            data.setdefault("model", None)
            data.setdefault("runtime_version", None)
        elif kind == "text_delta":
            data.setdefault("channel", "assistant")
        elif kind == "tool_requested":
            data.setdefault("args_preview", "")
            if not isinstance(data["args_preview"], str):
                raise ValueError("args_preview must be a string")
            data["args_digest"] = _digest(data["args_preview"])
        elif kind == "tool_completed":
            data["duration_ms"] = None  # no tool timing anchors in early fake wire
        if kind == "usage_reported":
            usage = _usage(data["usage"])
            event = UsageReported(
                len(self.events) + 1, self.clock.now(), usage, cast("bool", data.get("cumulative", True))
            )
        else:
            event = session_event_from_json(data)
        if self.schemas.validate("urn:skm:runtimes:session-event:v1", session_event_to_json(event)):
            raise ValueError("fake wire event violates the final event schema")
        if isinstance(event, SessionStarted):
            if (
                event.model is not None
                and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,199}", event.model) is None
            ):
                raise ValueError("reported model violates the observation contract")
            self.model, self.session_ref = event.model, event.session_ref
        elif isinstance(event, UsageReported):
            self.usage = merge_usage(self.usage, event.usage, cumulative=event.cumulative)
        self.events.append(event)


class FakeRuntime:
    """Fixed scenario or ordered script, with per-run durable invocation counters.

    Construction is the explicit override. ``state_dir`` is worker.state_dir; scenario mutations
    themselves are restricted to request.workdir. All observations describe synthetic executions.
    ``allow_pgroup_best_effort`` is host/test consent, not full-lifecycle containment evidence.
    """

    runtime_id = "fake"

    def __init__(
        self,
        *,
        state_dir: Path,
        scenario: Path | None = None,
        script: Path | None = None,
        clock: Clock | None = None,
        monotonic: Monotonic | None = None,
        clock_domain_id: UUID | None = None,
        allow_pgroup_best_effort: bool = False,
    ) -> None:
        if (scenario is None) == (script is None):
            raise ValueError("choose exactly one fake scenario or script")
        self._scenario = scenario
        self._script = script
        self._state_dir = state_dir
        self._clock = clock if clock is not None else SystemClock()
        self._monotonic = monotonic if monotonic is not None else SystemMonotonic()
        self._epoch = clock_domain_id if clock_domain_id is not None else uuid4()
        self._allow_pgroup_best_effort = allow_pgroup_best_effort
        self._schemas = _schemas()
        self._sessions: dict[str, _Session] = {}
        self._start_lock = threading.Lock()

    def capabilities(self) -> RuntimeCapabilities:
        records = {
            cap: CapabilityRecord(
                cap, CapabilityStatus.ADAPTED, "fixture:fake", None, "Synthetic tests only", None
            )
            for cap in (
                Capability.HEADLESS_EXECUTION,
                Capability.EFFORT_CONTROL,
                Capability.STRUCTURED_RESULT,
                Capability.STREAM_EVENTS,
                Capability.RELIABLE_CANCELLATION,
                Capability.USAGE_REPORTING,
                Capability.WORKSPACE_BINDING,
            )
        }
        return RuntimeCapabilities(self.runtime_id, "0.1.0", records, (), False, None)

    def detect(self, probe: DetectProbe) -> RuntimeInstallation:
        return RuntimeInstallation(
            probe.host_id,
            self.runtime_id,
            None,
            None,
            AuthState.UNKNOWN,
            self._clock.now(),
            {"evidence": "synthetic fixture; no live provider installation"},
        )

    def self_loaded_context(self, request: AgentRequest) -> tuple[SelfLoadedSource, ...]:  # noqa: ARG002
        return ()

    def _select(self, request: AgentRequest) -> Scenario:
        if self._scenario is not None:
            return load_scenario(self._scenario)
        assert self._script is not None  # noqa: S101 - constructor invariant
        run_id = str(UUID(request.labels["run_id"]))
        path = self._state_dir / "fake" / f"{run_id}.json"
        try:
            loaded: object = json.loads(path.read_text()) if path.exists() else dict[str, int]()
            if not isinstance(loaded, dict):
                raise ValueError("counters must be an object")
            raw_counts = cast("dict[str, object]", loaded)
            if any(not isinstance(v, int) or isinstance(v, bool) or v < 0 for v in raw_counts.values()):
                raise ValueError("counters must be non-negative integers")
            counts = cast("dict[str, int]", loaded)
            key = json.dumps([request.role.value, request.labels.get("task_key", "")])
            invocation = counts.get(key, 0) + 1
        except (OSError, ValueError, TypeError) as error:
            raise ScenarioError(f"cannot read fake invocation state {path}") from error
        scenario = select_scenario(
            self._script,
            role=request.role.value,
            task_key=request.labels.get("task_key", ""),
            invocation=invocation,
        )
        counts[key] = invocation
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(counts, sort_keys=True))
        temporary.replace(path)
        return scenario

    def start(self, request: AgentRequest) -> SessionHandle:
        validate_request(request, self.capabilities())
        # This closed scenario runner has no verified sandbox or full-lifecycle backend. Consent
        # admits only synthetic none/worktree scenarios, never a downgrade of a required profile.
        if not self._allow_pgroup_best_effort or request.isolation_profile not in (
            IsolationProfile.NONE,
            IsolationProfile.WORKTREE,
        ):
            raise CapabilityUnavailable(
                ErrorCode.SANDBOX_UNAVAILABLE,
                "fake requires explicit consent to best-effort process-group cleanup",
                details={"profile": str(request.isolation_profile)},
            )
        workdir = Path(request.workdir)
        if not workdir.is_dir():
            raise ScenarioError(f"fake workdir does not exist: {workdir}")
        with self._start_lock:
            if request.request_id in self._sessions:
                raise ScenarioError("fake request_id already started")
            session = _Session(
                request,
                self._select(request),
                self._monotonic.monotonic(),
                self._clock,
                self._monotonic,
                self._epoch,
                self._schemas,
            )
            with session.finish_lock:
                # scenarios.py holds the child entry point inside this leaf's allowed write set.
                try:
                    child = spawn(
                        (
                            sys.executable,
                            "-m",
                            "skm.adapters.runtimes.fake.scenarios",
                            json.dumps(session.scenario.document),
                            "resume" if request.resume_session_ref else "fresh",
                        ),
                        cwd=workdir,
                        env={},
                        line_mode=False,
                        on_stdout=lambda chunk: session.feed(chunk, stdout=True),
                        on_stderr=session.record_stderr,
                    )
                    session.process = child
                    handle = SessionHandle(
                        self.runtime_id,
                        request.request_id,
                        child.pid,
                        child.identity.start_ticks,
                        self._clock.now(),
                        ProcessOwnership(request.process_owner, "pgroup_best_effort", str(child.pgid)),
                    )
                    session.handle = handle
                    # Publish only a session with a collector; a large prompt must not block start
                    # or its timeout enforcement. Finalization waits for the complete startup attempt.
                    threading.Thread(
                        target=self._collect, args=(session,), daemon=True, name=f"skm-fake-{child.pid}"
                    ).start()
                    threading.Thread(
                        target=self._write_prompt,
                        args=(session,),
                        daemon=True,
                        name=f"skm-fake-input-{child.pid}",
                    ).start()
                    self._sessions[request.request_id] = session
                except BaseException as error:
                    failure = ProviderFailure(
                        ErrorClass.CRASH,
                        ErrorCode.RUNTIME_CRASHED,
                        False,
                        "fake subprocess could not start",
                        None,
                        ErrorScope.SESSION,
                        "process",
                    )
                    if session.process is not None:
                        try:
                            stopped = session.process.terminate(grace_seconds=0)
                            if not stopped.exited:
                                failure = process_failure(ProcessOutcome.CLEANUP_UNCONFIRMED)
                        except (OSError, ValueError, RuntimeError):
                            failure = process_failure(ProcessOutcome.CLEANUP_UNCONFIRMED)
                        self._finish(session, None, failure)
                    if isinstance(error, (OSError, ValueError, RuntimeError)):
                        raise RuntimeStartError(failure) from error
                    raise
                return handle

    def _write_prompt(self, session: _Session) -> None:
        assert session.process is not None  # noqa: S101 - spawned session
        try:
            try:
                session.process.write_stdin(session.request.rendered_prompt.encode("utf-8"))
            except BrokenPipeError:
                pass  # early exit is classified by the final drain
            except ValueError as error:
                # The supervisor can close stdin on natural exit while this writer is active.
                if str(error) != "process stdin is closed":
                    raise
            finally:
                session.process.close_stdin()
        except (OSError, ValueError, RuntimeError):
            with session.finish_lock:
                if session.result is None:
                    self._fail_cleanup(session)

    def _session(self, handle: SessionHandle) -> _Session:
        session = self._sessions.get(handle.request_id)
        if session is None or session.handle is not handle:
            raise ValueError("session handle does not belong to this fake runtime")
        return session

    def events(self, handle: SessionHandle) -> Iterator[SessionEvent]:
        session = self._session(handle)
        index = 0
        while True:
            with session.lock:
                ready = session.events[index:]
                index += len(ready)
                done = session.result is not None
            yield from ready
            if done:
                return
            session.finished.wait(0.02)

    def result(self, handle: SessionHandle) -> RuntimeResult:
        session = self._session(handle)
        for _ in self.events(handle):
            pass
        assert session.result is not None  # noqa: S101 - terminal freezes the result
        return session.result

    def _poll(self, session: _Session) -> None:
        assert session.process is not None  # noqa: S101 - only published after spawn
        code = session.process.wait(timeout_seconds=0.02)
        timed_out = session.monotonic.monotonic() - session.started >= session.request.limits.timeout_seconds
        if code is None and not timed_out:
            return
        with session.finish_lock:
            if session.result is not None:
                return
            if code is not None:
                self._finish(session, code)
            elif timed_out:
                stopped = session.process.terminate(grace_seconds=0.05)
                code = session.process.wait(0)
                failure = (
                    ProcessOutcome.WALL_TIMEOUT
                    if stopped.exited and code is not None
                    else ProcessOutcome.CLEANUP_UNCONFIRMED
                )
                self._finish(session, code, process_failure(failure))

    def _collect(self, session: _Session) -> None:
        # Freeze timing at final drain, independently of when the worker asks for result().
        try:
            while not session.finished.is_set():
                self._poll(session)
        except (OSError, ValueError, RuntimeError):
            with session.finish_lock:
                if session.result is None:
                    self._fail_cleanup(session)
        finally:
            session.finished.set()

    def _fail_cleanup(self, session: _Session) -> None:
        assert session.process is not None  # noqa: S101 - spawned session
        try:
            session.process.terminate(grace_seconds=0)
        except (OSError, ValueError, RuntimeError):
            pass  # retained platform ownership survives a failed cleanup attempt
        finally:
            # A lost status cannot be reconstructed by another termination attempt. Keep the
            # measured ingress counters: a wait failure is not evidence of failed pipe capture.
            self._finish(session, None, process_failure(ProcessOutcome.CLEANUP_UNCONFIRMED))

    def cancel(self, handle: SessionHandle, *, grace_seconds: float) -> CancellationResult:
        session = self._session(handle)
        assert session.process is not None  # noqa: S101 - only published after spawn
        with session.finish_lock:
            if session.cancellation is not None:
                return session.cancellation
            if session.result is not None:
                failure = session.result.failure
                stopped = failure is None or failure.details.get("reason") != "cleanup_unconfirmed"
                session.cancellation = CancellationResult(stopped, None, False)
                return session.cancellation
            used, ignored = None, False
            try:
                code = session.process.wait(0)
                if code is not None:
                    self._finish(session, code)
                    return CancellationResult(True, None, False)
                stopped = session.process.terminate(grace_seconds=grace_seconds)
                used = signal.Signals(stopped.signal_sent).name if stopped.signal_sent else None
                ignored = stopped.ignored or used == "SIGKILL"
                session.cancellation = CancellationResult(stopped.exited, used, ignored)
                outcome = ProcessOutcome.CANCEL_IGNORED if ignored else ProcessOutcome.CANCELLED
                with session.lock:
                    if ignored or used == "SIGTERM":
                        session.events.append(
                            CancelIgnored(len(session.events) + 1, self._clock.now(), "SIGINT")
                        )
                code = session.process.wait(0)
                if not stopped.exited or code is None:
                    outcome = ProcessOutcome.CLEANUP_UNCONFIRMED
                    session.cancellation = CancellationResult(False, used, ignored)
                self._finish(session, code, process_failure(outcome))
            except (OSError, ValueError, RuntimeError):
                session.cancellation = CancellationResult(False, used, ignored)
                self._fail_cleanup(session)
            return session.cancellation

    def _finish(self, session: _Session, code: int | None, failure: ProviderFailure | None = None) -> None:
        with session.lock:
            if session.result is not None:
                return
            if session.pending:
                session.flags.add("incomplete_tail")
            dropped = session.bytes_seen - len(session.capture)
            if failure is None:
                failure = self._failure(session, code, dropped)
            duration = max(0, int((self._monotonic.monotonic() - session.started) * 1000))
            observation = self._observation(
                session,
                duration,
                dropped,
                cleanup_unconfirmed=failure is not None
                and failure.details.get("reason") == "cleanup_unconfirmed",
            )
            text = (session.final_text or "") if failure is None else ""
            session.events.append(
                UsageReported(len(session.events) + 1, self._clock.now(), session.usage, True)
            )
            terminal = (
                SessionCompleted(
                    len(session.events) + 1, self._clock.now(), StopReason.END_TURN, _digest(text)
                )
                if failure is None
                else SessionFailed(len(session.events) + 1, self._clock.now(), failure)
            )
            session.events.append(terminal)
            session.result = RuntimeResult(
                outcome="completed" if failure is None else "cancelled" if failure.cancelled else "failed",
                final_text=text,
                structured=None,
                session_ref=session.session_ref,
                model=session.model,
                usage=session.usage,
                failure=failure,
                exit=ExitInfo(
                    code if code is None or code >= 0 else None,
                    signal.Signals(-code).name if code is not None and code < 0 else None,
                    bool(dropped),
                    duration,
                ),
                lingered=False,
                denials=(),
                api_retries=0,
                transcript_path=None,
                stderr_path=None,
                observation=observation,
            )
            session.finished.set()

    @staticmethod
    def _failure(session: _Session, code: int | None, dropped: int) -> ProviderFailure | None:
        if dropped:
            return process_failure(ProcessOutcome.STREAM_TOO_LARGE)
        if code != 0:
            return classify(
                "fake", RuntimeSignals(exit_code=code), (), now_unix=int(session.clock.now().timestamp())
            )
        if session.flags or session.final_text is None:
            return process_failure(ProcessOutcome.STREAM_INCOMPLETE)
        if not session.final_text.strip():
            return process_failure(ProcessOutcome.EMPTY_OUTPUT)
        return None

    @staticmethod
    def _observation(
        session: _Session, duration: int, dropped: int, *, cleanup_unconfirmed: bool
    ) -> RuntimeObservation:
        calls = sum(isinstance(event, ToolRequested) for event in session.events)
        # Observed tools are a partial scope, never proof of complete native-tool visibility.
        return RuntimeObservation(
            OBSERVATION_SCHEMA,
            UUID(session.request.request_id),
            ObservationBinding(
                "fake",
                None,
                None,
                None,
                None,
                session.model,
                "unavailable" if session.model is None else "provider_stream",
            ),
            ObservationTiming(
                session.epoch, None if cleanup_unconfirmed else duration, session.first_at, session.last_at
            ),
            CaptureObservation(
                "partial" if cleanup_unconfirmed or dropped or session.flags else "complete",
                session.bytes_seen,
                len(session.capture),
                dropped,
                bool(dropped),
                ("capture_gap",) if cleanup_unconfirmed else (),
                tuple(sorted(session.flags)),
                None,
            ),
            ToolVisibility("partial" if calls else "unavailable", calls if calls else None),
        )
