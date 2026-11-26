"""Shared CLI lifecycle: bounded capture, monotonic deadlines and one settled terminal."""

from __future__ import annotations

import json
import math
import signal
import threading
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field, replace
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Protocol, cast
from uuid import UUID

from skm.kernel.clock import Clock, Monotonic
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.json_types import JsonValue
from skm.modules.runtimes import public as runtimes
from skm.modules.runtimes.domain.error_rules import ErrorRule
from skm.modules.runtimes.domain.observation import ObservationBinding, ToolVisibility
from skm.modules.runtimes.domain.session_events import StopReason, session_event_to_json
from skm.platform.process.ownership import discard, launch
from skm.platform.system_clock import SystemClock

from .activity import TreeCpuWatch
from .cancel import Sleeper, TerminationOutcome, terminate_group
from .identity import GroupProcess, OwnedContainment, claim_marker, remove_marker, update_marker
from .observation import LiveQueue, ObservationCapture
from .signals import SignalCollector
from .stream import StreamTail
from .transcript import TranscriptWriter

if TYPE_CHECKING:
    from skm.modules.execution.ports import WrappedCommand
    from skm.platform.process.identity import ProcessIdentity

__all__: list[str] = []


@dataclass(frozen=True)
class SessionLimits:
    wall_timeout_seconds: float = 3600
    idle_timeout_seconds: float = 900
    result_grace_seconds: float = 30
    poll_interval_seconds: float = 2
    cpu_sample_seconds: float = 30
    cpu_progress_seconds: float = 1
    max_stream_bytes: int = 256 * 1024 * 1024

    def __post_init__(self) -> None:
        seconds = (
            self.wall_timeout_seconds,
            self.idle_timeout_seconds,
            self.result_grace_seconds,
            self.poll_interval_seconds,
            self.cpu_sample_seconds,
            self.cpu_progress_seconds,
        )
        if any(not math.isfinite(value) or value < 0 for value in seconds):
            raise ValueError("session durations must be finite and nonnegative")
        if self.poll_interval_seconds == 0 or self.max_stream_bytes <= 0:
            raise ValueError("poll interval and stream ceiling must be positive")

    @classmethod
    def from_poll_interval_ms(
        cls,
        poll_interval_ms: int,
        *,
        wall_timeout_seconds: float = 3600,
        idle_timeout_seconds: float = 900,
        result_grace_seconds: float = 30,
        max_stream_bytes: int = 256 * 1024 * 1024,
    ) -> SessionLimits:
        return cls(
            poll_interval_seconds=poll_interval_ms / 1000.0,
            wall_timeout_seconds=wall_timeout_seconds,
            idle_timeout_seconds=idle_timeout_seconds,
            result_grace_seconds=result_grace_seconds,
            max_stream_bytes=max_stream_bytes,
        )


@dataclass(frozen=True)
class FinalOutcome:
    final_text: str = ""
    session_ref: str | None = None
    model: str | None = None
    usage: runtimes.UsageReport = field(default_factory=runtimes.unknown_usage)
    signals: runtimes.RuntimeSignals = field(default_factory=runtimes.RuntimeSignals)
    is_error: bool = False
    stop_reason: StopReason = StopReason.END_TURN
    tools: ToolVisibility = field(default_factory=lambda: ToolVisibility("unavailable", None))
    denials: tuple[runtimes.ToolDenial, ...] = ()
    structured: JsonValue | None = None
    observed_effort: runtimes.Effort | None = None


class StreamParser(Protocol):
    def feed(self, line: bytes) -> Iterable[runtimes.SessionEvent]: ...
    def finish(self, exit_code: int | None) -> FinalOutcome: ...
    def is_terminal(self, line: bytes) -> bool: ...
    def saw_terminal(self) -> bool: ...


class SessionProcess(OwnedContainment, Protocol):
    pid: int
    pgid: int
    identity: ProcessIdentity
    stdin_written: int

    def poll(self) -> int | None: ...
    def pump(self) -> None: ...
    def write_stdin(self, data: bytes) -> None: ...
    def close_stdin(self) -> None: ...
    def close(self) -> None: ...


class ProcessRunner(Protocol):
    """Required backends must validate pinned launch dependencies and attach before exec."""

    def validate(self, command: WrappedCommand) -> None: ...
    def spawn(
        self,
        command: WrappedCommand,
        *,
        marker: Path,
        on_stdout: Callable[[bytes], None],
        on_stderr: Callable[[bytes], None],
    ) -> SessionProcess: ...


class TrustedProcessRunner:
    """Linux pidfd-backed process-group mode, admitted only by explicit host consent.

    The caller provides any required executable binding before the runner starts a child.
    """

    def __init__(self, *, allow_pgroup_best_effort: bool = False, require_exec_binding: bool = False) -> None:
        self.allowed, self.require_exec_binding = allow_pgroup_best_effort, require_exec_binding

    def validate(self, command: WrappedCommand) -> None:
        if (
            not self.allowed
            or command.ownership.kind != "pgroup_best_effort"
            or (self.require_exec_binding and not getattr(command, "exec_bound", False))
        ):
            raise CapabilityUnavailable(
                ErrorCode.SANDBOX_UNAVAILABLE, "required containment or executable binding unavailable"
            )

    def spawn(
        self,
        command: WrappedCommand,
        *,
        marker: Path,
        on_stdout: Callable[[bytes], None],
        on_stderr: Callable[[bytes], None],
    ) -> SessionProcess:
        self.validate(command)
        if not marker.is_file():
            raise ValueError("ownership marker must exist before exec")
        pipes, owned = launch(command.argv, cwd=command.cwd, env=command.env)
        try:
            return GroupProcess(pipes, owned, command.ownership, on_stdout, on_stderr)
        except BaseException as error:
            discard(pipes, owned, error)
            raise


class CliSession:
    def __init__(  # noqa: PLR0913 - spec-defined injected lifecycle boundary
        self,
        command: WrappedCommand,
        *,
        stdin: bytes,
        parser: StreamParser,
        limits: SessionLimits,
        transcript: TranscriptWriter,
        identity_dir: Path,
        step_id: UUID,
        clock: Monotonic,
        sleeper: Sleeper,
        cancel_event: threading.Event,
        process: ProcessRunner,
        utc_clock: Clock | None = None,
        binding: ObservationBinding | None = None,
        rules: tuple[ErrorRule, ...] = (),
        accept_lingering_result: bool = True,
        live: LiveQueue | None = None,
    ) -> None:
        if step_id != command.ownership.owner.unit_id:
            raise ValueError("session StepId differs from ownership")
        if identity_dir.resolve().is_relative_to(command.cwd.resolve()):
            raise ValueError("ownership markers must be outside workdir")
        if transcript.step_dir.name != str(step_id) or limits.max_stream_bytes != transcript.max_stream_bytes:
            raise ValueError("transcript must match session identity and joint ceiling")
        self.command = replace(command, env=MappingProxyType(dict(command.env)))
        self.ownership = command.ownership
        self.stdin, self.parser, self.limits, self.transcript = stdin, parser, limits, transcript
        self.identity_dir, self.step_id = identity_dir, step_id
        self.clock, self.sleeper, self.cancel_event, self.runner = clock, sleeper, cancel_event, process
        self.utc = utc_clock if utc_clock is not None else SystemClock()
        self.binding = binding or ObservationBinding("fake", None, None, None, None, None, "unavailable")
        self.rules, self.live = rules, live
        self.accept_lingering_result = accept_lingering_result
        self.tail = StreamTail(limits.max_stream_bytes)
        self.signals = SignalCollector(transcript.redactor)
        self._events: list[runtimes.SessionEvent] = []
        self._usage = runtimes.unknown_usage()
        self._lock = threading.RLock()
        self._process: SessionProcess | None = None
        self._marker: Path | None = None
        self._result: runtimes.RuntimeResult | None = None
        self._capture: ObservationCapture | None = None
        self._watch: TreeCpuWatch | None = None
        self._started = self._growth = 0.0
        self._answered: float | None = None
        self.idle_suspected = False

    def _emit(self, event: runtimes.SessionEvent) -> None:
        event = replace(event, seq=len(self._events) + 1, at=self.utc.now())
        if isinstance(event, runtimes.TextDelta):
            event = replace(event, text=self.transcript.redact(event.text))
        elif isinstance(event, runtimes.ToolRequested):
            event = replace(event, args_preview=self.transcript.redact(event.args_preview)[:500])
        encoded = json.dumps(session_event_to_json(event), ensure_ascii=False).encode()
        self._events.append(event)
        if self.live is not None:
            self.live.offer(encoded)

    def _lines(self, lines: list[bytes]) -> None:
        for line in lines:
            try:
                native: object = json.loads(line)
                if isinstance(native, dict) and self._capture is not None:
                    seq = cast("dict[str, object]", native).get("seq")
                    if isinstance(seq, int) and not isinstance(seq, bool) and seq >= 0:
                        self._capture.native_sequence(seq)
                for event in self.parser.feed(line):
                    if isinstance(
                        event, (runtimes.SessionCompleted, runtimes.SessionFailed, runtimes.CancelIgnored)
                    ):
                        raise ValueError("only session owner settles lifecycle")
                    if isinstance(event, runtimes.UsageReported):
                        self._usage = runtimes.merge_usage(
                            self._usage, event.usage, cumulative=event.cumulative
                        )
                    self._emit(event)
                    if self.transcript.exceeded:
                        return
                if self.parser.is_terminal(line):
                    self._answered = self._answered if self._answered is not None else self.clock.monotonic()
            except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
                self.tail.flags.add("malformed_json")
                return

    def _feed(self, chunk: bytes, *, stderr: bool) -> None:
        with self._lock:
            if self._result is not None:
                return
            admitted, safe = self.transcript.write("stderr" if stderr else "stdout", chunk)
            if self._capture is not None:
                self._capture.ingress(len(chunk), len(chunk), self.utc.now())
            if not admitted:
                return  # The process pump still drains/discards until containment stops.
            self._growth = self.clock.monotonic()
            if self._capture is not None and not self.transcript.stamp(
                self._growth - self._started,
                self._capture.bytes_seen,
            ):
                return
            if stderr:
                self.signals.stderr(safe)
            else:
                self._lines(self.tail.advance(chunk))

    def _start(self) -> None:
        try:
            self.runner.validate(self.command)
            if any(self.transcript.redact(arg) != arg for arg in self.command.argv):
                raise ValueError("secrets must not appear in runtime argv")
            self._marker = claim_marker(self.identity_dir, self.ownership)
            self._started = self._growth = self.clock.monotonic()
            self._capture = ObservationCapture(self.step_id, self.binding, self._started)
            self._process = self.runner.spawn(
                self.command,
                marker=self._marker,
                on_stdout=lambda data: self._feed(data, stderr=False),
                on_stderr=lambda data: self._feed(data, stderr=True),
            )
            update_marker(self._marker, self._process.identity, pgid=self._process.pgid)
            self._watch = TreeCpuWatch(
                self._process.pid,
                self.limits.cpu_sample_seconds,
                self.limits.cpu_progress_seconds,
                last_sample=self._started,
                last_growth=self._started,
            )
            self._watch.sample(self._started)
        except BaseException as primary:
            try:
                if self._process is not None:
                    self._stop("startup_failure")
                else:
                    self.transcript.close()
            except BaseException as cleanup:  # noqa: BLE001 - preserve the launch failure
                primary.add_note(f"session startup cleanup failed: {type(cleanup).__name__}")
            raise

    def _write_input(self) -> None:
        child = self._process
        if child is None:
            return
        try:
            if child.stdin_written < len(self.stdin):
                child.write_stdin(self.stdin[child.stdin_written : child.stdin_written + 65_536])
            if child.stdin_written == len(self.stdin):
                child.close_stdin()
        except BrokenPipeError:
            child.close_stdin()

    def _ignored(self, sig: str) -> None:
        self._emit(
            runtimes.CancelIgnored(1, self.utc.now(), "SIGINT" if sig == "SIGINT" else "SIGTERM"),
        )

    def _tick(self) -> None:
        child = self._process
        if child is None:
            return
        child.pump()
        code = child.poll()
        now = self.clock.monotonic()
        reason = self._stop_reason(now, code)
        if code is not None or reason is not None:
            self._stop(reason, exit_code=code)
        else:
            self._write_input()

    def _stop_reason(self, now: float, code: int | None) -> str | None:
        if self.transcript.exceeded:
            return "stream_too_large"
        if code is not None:
            return None
        if self.cancel_event.is_set():
            return "cancelled"
        if self.limits.wall_timeout_seconds and now - self._started >= self.limits.wall_timeout_seconds:
            return "wall_timeout"
        if self.transcript.failed:
            return "capture_failed"
        if self.tail.flags:
            return "parser_invalid"
        if (
            self._answered is not None
            and self.limits.result_grace_seconds
            and (now - self._answered >= self.limits.result_grace_seconds)
        ):
            return "lingering"
        if self._watch is not None and self._watch.due(now) and self._watch.sample(now):
            self._growth = now
        if self.limits.idle_timeout_seconds and now - self._growth >= self.limits.idle_timeout_seconds:
            self.idle_suspected = True
        return None

    def _failure(
        self,
        reason: str | None,
        cleanup: TerminationOutcome,
        code: int | None,
        outcome: FinalOutcome,
    ) -> runtimes.ProviderFailure | None:
        process_outcome = {
            "cancelled": (
                runtimes.ProcessOutcome.CANCEL_IGNORED
                if cleanup.ignored_cancel
                else runtimes.ProcessOutcome.CANCELLED
            ),
            "wall_timeout": runtimes.ProcessOutcome.WALL_TIMEOUT,
            "stream_too_large": runtimes.ProcessOutcome.STREAM_TOO_LARGE,
            "parser_invalid": runtimes.ProcessOutcome.STREAM_INCOMPLETE,
            "capture_failed": runtimes.ProcessOutcome.STREAM_INCOMPLETE,
            "startup_failure": runtimes.ProcessOutcome.CLEANUP_UNCONFIRMED,
        }
        if not cleanup.stopped:
            return runtimes.process_failure(runtimes.ProcessOutcome.CLEANUP_UNCONFIRMED)
        if reason in process_outcome:
            return runtimes.process_failure(process_outcome[reason])
        if (code not in (None, 0) and reason != "lingering") or outcome.is_error:
            signals = self.signals.collect(outcome.signals, code)
            return self.signals.classify(
                self.binding.runtime_id, signals, self.rules, now_unix=int(self.utc.now().timestamp())
            )
        if (
            self.tail.flags
            or not self.parser.saw_terminal()
            or (reason == "lingering" and not self.accept_lingering_result)
        ):
            return runtimes.process_failure(runtimes.ProcessOutcome.STREAM_INCOMPLETE)
        if not outcome.final_text.strip() and outcome.structured is None:
            return runtimes.process_failure(runtimes.ProcessOutcome.EMPTY_OUTPUT)
        return None

    def _stop(self, reason: str | None, *, exit_code: int | None = None) -> None:
        child = self._process
        if child is None or self._result is not None:
            return
        cleanup = terminate_group(
            child.pgid,
            ownership=self.ownership,
            backend=child,
            mode="reap" if reason is None else "cancel",
            clock=self.clock,
            sleeper=self.sleeper,
            on_ignored=self._ignored if reason in ("cancelled", "wall_timeout") else None,
            drain=child.pump,
        )
        child.pump()
        code = child.poll() if exit_code is None else exit_code
        self._lines(self.tail.advance(final=True))
        try:
            outcome = self.parser.finish(code)
            if not outcome.usage.is_empty() or self._usage.is_empty():
                self._usage = runtimes.merge_usage(self._usage, outcome.usage, cumulative=True)
        except (ValueError, TypeError, KeyError, UnicodeError, RecursionError):
            self.tail.flags.add("malformed_json")
            outcome = FinalOutcome(usage=self._usage)
        try:
            self.transcript.close()
        except (OSError, ValueError):
            self.transcript.failed = True
        self.signals.stderr_tail = self.transcript.stderr_tail
        if self.transcript.exceeded:
            reason = "stream_too_large"
        elif self.transcript.failed and reason not in ("cancelled", "wall_timeout"):
            reason = "capture_failed"
        failure = self._failure(reason, cleanup, code, outcome)
        if (
            failure is not None
            and self._usage.status is runtimes.UsageStatus.REPORTED
            and not self.parser.saw_terminal()
        ):
            self._usage = replace(self._usage, status=runtimes.UsageStatus.ESTIMATED)
        self._settle(outcome, failure, code, lingered=reason == "lingering", stopped=cleanup.stopped)
        if cleanup.stopped and self._marker is not None:
            remove_marker(self._marker)
        child.close()

    def _settle(
        self,
        outcome: FinalOutcome,
        failure: runtimes.ProviderFailure | None,
        code: int | None,
        *,
        lingered: bool,
        stopped: bool,
    ) -> None:
        capture = self._capture
        if capture is None:
            raise RuntimeError("session capture was not initialized")
        capture.flags.update(self.tail.flags)
        capture.bytes_retained = max(0, capture.bytes_seen - self.transcript.bytes_dropped)
        capture.truncated = self.transcript.exceeded
        if not stopped or self.transcript.failed or self.transcript.exceeded:
            capture.gaps.add("capture_gap")
        model = outcome.model
        if model is not None and self.transcript.redact(model) != model:
            model = None
        self._emit(runtimes.UsageReported(1, self.utc.now(), self._usage, True))
        terminal = (
            runtimes.SessionCompleted(
                len(self._events) + 1,
                self.utc.now(),
                outcome.stop_reason,
                "sha256:" + sha256(outcome.final_text.encode()).hexdigest(),
            )
            if failure is None
            else runtimes.SessionFailed(len(self._events) + 1, self.utc.now(), failure)
        )
        self._emit(terminal)
        observation = self._freeze(capture, outcome, model, stopped=stopped)
        self._result = runtimes.RuntimeResult(
            outcome="completed" if failure is None else "cancelled" if failure.cancelled else "failed",
            final_text=outcome.final_text if failure is None else "",
            structured=outcome.structured if failure is None else None,
            session_ref=outcome.session_ref,
            model=model,
            usage=self._usage,
            failure=failure,
            exit=runtimes.ExitInfo(
                0 if lingered and self.accept_lingering_result else code,
                signal.Signals(-code).name if not lingered and code is not None and code < 0 else None,
                self.transcript.exceeded,
                max(0, int((self.clock.monotonic() - self._started) * 1000)),
            ),
            lingered=lingered,
            denials=outcome.denials,
            api_retries=outcome.signals.api_retries or 0,
            transcript_path=str(self.transcript.step_dir / "stream.jsonl"),
            stderr_path=str(self.transcript.step_dir / "stream.stderr"),
            observation=observation,
        )

    def _freeze(
        self,
        capture: ObservationCapture,
        outcome: FinalOutcome,
        model: str | None,
        *,
        stopped: bool,
    ) -> runtimes.RuntimeObservation | None:
        tools = outcome.tools
        calls = sum(isinstance(event, runtimes.ToolRequested) for event in self._events)
        if tools.coverage == "unavailable" and calls:
            tools = ToolVisibility("partial", calls)
        try:
            return capture.freeze(
                ended=self.clock.monotonic() if stopped else None,
                model=model,
                observed_effort=outcome.observed_effort,
                tools=tools,
                live_dropped=0 if self.live is None else self.live.dropped,
            )
        except ValueError:
            # Diagnostics never replace the already determined terminal/cleanup outcome.
            return None

    def run(self) -> Iterator[runtimes.SessionEvent]:
        index = 0
        while True:
            with self._lock:
                if self._process is None:
                    self._start()
                if self._result is None:
                    try:
                        self._tick()
                    except (OSError, ValueError, RuntimeError):
                        self._stop("capture_failed")
                ready = self._events[index:]
                index = len(self._events)
                done = self._result is not None
            yield from ready
            if done:
                return
            self.sleeper.sleep(self.limits.poll_interval_seconds)

    def result(self) -> runtimes.RuntimeResult:
        for _ in self.run():
            pass
        if self._result is None:
            raise RuntimeError("session failed to settle")
        return self._result
