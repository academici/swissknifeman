"""Deterministic process/containment ports; synthetic proof is separate from real OS proof."""

from __future__ import annotations

import json
import signal
import threading
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from fakes.clock import FakeMonotonic, FrozenClock
from skm.adapters.runtimes._cli_session.observation import LiveQueue
from skm.adapters.runtimes._cli_session.session import CliSession, FinalOutcome, SessionLimits
from skm.adapters.runtimes._cli_session.transcript import TranscriptWriter
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.execution.host.isolation import WrappedCommand
from skm.modules.runtimes import public as rt
from skm.modules.runtimes.domain.session_events import session_event_from_json
from skm.platform.fs.storage_budget import StorageBudget, StorageOwnerIdentity
from skm.platform.process.identity import ProcessIdentity

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures/runtimes/fake"


class VirtualSleeper:
    def __init__(self, clock: FakeMonotonic) -> None:
        self.clock = clock
        self.calls: list[float] = []
        self.on_sleep: Callable[[float], None] | None = None

    def sleep(self, seconds: float) -> None:
        self.calls.append(seconds)
        self.clock.advance(seconds)
        if self.on_sleep is not None:
            self.on_sleep(seconds)


class WireParser:
    """Tiny fixture decoder. The shared lifecycle, not this parser, owns terminal events."""

    def __init__(self) -> None:
        self.terminal = False
        self.outcome = FinalOutcome()
        self.lines: list[bytes] = []

    def feed(self, line: bytes) -> Iterable[rt.SessionEvent]:
        self.lines.append(line)
        data = json.loads(line)
        kind = data["type"]
        if kind == "fake_result":
            self.terminal = True
            self.outcome = replace(self.outcome, final_text=data["final_text"])
            return ()
        if kind == "error":
            self.outcome = replace(
                self.outcome,
                is_error=True,
                signals=rt.RuntimeSignals(
                    http_status=data.get("http_status"),
                    fatal_text=data.get("error"),
                    is_error=True,
                ),
            )
            return ()
        data.update(seq=1, at="2026-01-01T00:00:00Z")
        if kind == "text_delta":
            data.setdefault("channel", "assistant")
        if kind == "session_started":
            data.setdefault("session_ref", None)
            data.setdefault("model", None)
            data.setdefault("runtime_version", None)
            self.outcome = replace(self.outcome, model=data["model"], session_ref=data["session_ref"])
        if kind == "tool_requested":
            preview = data.setdefault("args_preview", "")
            data["args_digest"] = "sha256:" + sha256(preview.encode()).hexdigest()
        if kind == "tool_completed":
            data.setdefault("duration_ms", None)
        if kind == "usage_reported":
            usage = replace(
                rt.unknown_usage(),
                input_tokens=data["usage"].get("input_tokens"),
                output_tokens=data["usage"].get("output_tokens"),
                status=rt.UsageStatus.REPORTED,
                source="stream:result",
            )
            self.outcome = replace(self.outcome, usage=usage)
            return (rt.UsageReported(1, FrozenClock().now(), usage, True),)
        event = session_event_from_json(data)
        return (event,)

    def finish(self, exit_code: int | None) -> FinalOutcome:
        return self.outcome

    def is_terminal(self, line: bytes) -> bool:
        return json.loads(line).get("type") == "fake_result"

    def saw_terminal(self) -> bool:
        return self.terminal


class FakeChild:
    pid = pgid = 999_999_991
    identity = ProcessIdentity(pid, 42, "synthetic-boot")

    def __init__(self, clock: FakeMonotonic, stdout: bytes, stderr: bytes, code: int | None) -> None:
        self.clock, self.stdout, self.stderr, self.exit_code = clock, stdout, stderr, code
        self.started = clock.monotonic()
        self.code: int | None = None
        self.stdin_written = 0
        self.stdin_closed = False
        self.close_count = 0
        self.pump_count = 0
        self.sent: list[int] = []
        self.ignore = False
        self.unknown = False
        self.denied = False
        self.escaped = False
        self.broken_stdin = False
        self.emitted = False
        self.owner: rt.ProcessOwnership | None = None
        self.on_stdout: Callable[[bytes], None] = lambda _: None
        self.on_stderr: Callable[[bytes], None] = lambda _: None

    def confirmed(self, ownership: rt.ProcessOwnership) -> bool:
        return self.owner == ownership

    def empty(self) -> bool | None:
        if self.unknown:
            return None
        return self.code is not None and not self.escaped

    def signal(self, sig: int) -> None:
        if self.denied:
            raise PermissionError("synthetic EPERM")
        self.sent.append(sig)
        if not self.ignore or sig == signal.SIGKILL:
            self.code = -sig
            self.escaped = False

    def poll(self) -> int | None:
        if self.emitted and self.clock.monotonic() - self.started >= 0.1 and self.code is None:
            self.code = self.exit_code
        return self.code

    def pump(self) -> None:
        self.pump_count += 1
        if not self.emitted:
            self.emitted = True
            if self.stdout:
                self.on_stdout(self.stdout)
            if self.stderr:
                self.on_stderr(self.stderr)

    def write_stdin(self, data: bytes) -> None:
        if self.broken_stdin:
            raise BrokenPipeError
        self.stdin_written += len(data)

    def close_stdin(self) -> None:
        self.stdin_closed = True

    def close(self) -> None:
        self.close_count += 1


class FakeRunner:
    def __init__(self, child: FakeChild) -> None:
        self.child = child
        self.available = True
        self.spawns = 0

    def validate(self, command: WrappedCommand) -> None:
        if not self.available:
            raise CapabilityUnavailable(ErrorCode.SANDBOX_UNAVAILABLE, "synthetic backend unavailable")

    def spawn(
        self,
        command: WrappedCommand,
        *,
        marker: Path,
        on_stdout: Callable[[bytes], None],
        on_stderr: Callable[[bytes], None],
    ) -> FakeChild:
        assert marker.is_file()
        assert marker.stat().st_mode & 0o777 == 0o600
        assert json.loads(marker.read_bytes())["ref"] == command.ownership.ref
        self.spawns += 1
        self.child.owner = command.ownership
        self.child.on_stdout, self.child.on_stderr = on_stdout, on_stderr
        return self.child


@dataclass
class Harness:
    session: CliSession
    child: FakeChild
    runner: FakeRunner
    parser: WireParser
    clock: FakeMonotonic
    utc: FrozenClock
    sleeper: VirtualSleeper
    writer: TranscriptWriter
    budget: StorageBudget
    cancel: threading.Event
    command: WrappedCommand


def budget_for(state: Path, *, free: int = 10**10) -> StorageBudget:
    return StorageBudget(
        state / "locks",
        free_bytes=lambda _: free,
        identity=lambda: StorageOwnerIdentity("synthetic-boot", 123, "42"),
        owner_alive=lambda _: True,
    )


def build(
    root: Path,
    *,
    stdout: bytes = b'{"type":"fake_result","final_text":"done"}\n',
    stderr: bytes = b"",
    exit_code: int | None = 0,
    limits: SessionLimits | None = None,
    parser: WireParser | None = None,
    live: LiveQueue | None = None,
) -> Harness:
    root.mkdir(parents=True, exist_ok=True)
    state, workdir = root / "state", root / "workdir"
    workdir.mkdir(exist_ok=True)
    step = uuid4()
    owner = rt.ProcessOwner(
        uuid4(), uuid4(), uuid4(), uuid4(), "step", step, "synthetic-owner-nonce", str(state / "identities")
    )
    ownership = rt.ProcessOwnership(owner, "cgroup", f"synthetic/{step}")
    command = WrappedCommand(("synthetic-no-exec",), {}, workdir, ownership)
    limits = limits or SessionLimits(poll_interval_seconds=0.05)
    budget = budget_for(state)
    reservation = budget.reserve(
        state, owner_id=str(step), max_bytes=limits.max_stream_bytes, min_free_bytes=0, max_files=3
    )
    writer = TranscriptWriter(
        state / "steps" / str(step), reservation, max_stream_bytes=limits.max_stream_bytes, workdir=workdir
    )
    clock, utc = FakeMonotonic(), FrozenClock()
    sleeper = VirtualSleeper(clock)
    child = FakeChild(clock, stdout, stderr, exit_code)
    runner = FakeRunner(child)
    parser, cancel = parser or WireParser(), threading.Event()
    session = CliSession(
        command,
        stdin=b"private prompt",
        parser=parser,
        limits=limits,
        transcript=writer,
        identity_dir=state / "identities",
        step_id=step,
        clock=clock,
        sleeper=sleeper,
        cancel_event=cancel,
        process=runner,
        utc_clock=utc,
        live=live,
    )
    return Harness(session, child, runner, parser, clock, utc, sleeper, writer, budget, cancel, command)
