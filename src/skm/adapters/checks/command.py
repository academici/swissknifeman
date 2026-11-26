"""Check execution: mandatory sandbox wrap, DEVNULL stdin, bounded capture and owned reap."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Any, Protocol, cast, override

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.modules.execution.ports import CheckRunner
from skm.modules.runtimes.public import ProcessOwnership
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.safe_paths import safe_join
from skm.platform.fs.storage_budget import BudgetedFile, StorageBudget
from skm.platform.logging.redaction import DEFAULT_PATTERNS, Redactor
from skm.platform.process.identity import ProcessIdentity

from .lifecycle import (
    CheckLaunchError,
    TrustedCheckLauncher,
    claim_marker,
    clear_environment,
    environment_guard,
    remove_marker,
    terminate_group,
    update_marker,
)

__all__ = ["CommandCheckRunner", "command_check_runner", "reproduction_runner"]

_SAFE_ENV = frozenset({"PATH", "LANG", "LC_ALL", "TZ", "TERM"})
_IDENTIFIERS = frozenset(
    {"SKM_CHECK_ID", "SKM_CHECK_RUN", "SKM_CHECK_TASK", "SKM_CHECK_ATTEMPT", "SKM_CHECK_OUTPUT"}
)
_TRUNCATED = b"\n[truncated]\n"


class CommandCheckRunner(CheckRunner, Protocol):
    """Host check gateway; factory injects sandbox and shared StorageBudget."""


@dataclass(frozen=True)
class CheckFacts:
    exit_code: int | None
    timed_out: bool
    spawn_error: str | None
    interrupted: bool
    stdout_path: Path
    stderr_path: Path
    report_files: tuple[Path, ...]
    duration_seconds: float


class CheckProcess(Protocol):
    pid: int
    identity: ProcessIdentity

    def confirmed(self, ownership: ProcessOwnership) -> bool: ...
    def empty(self) -> bool | None: ...
    def signal(self, sig: int) -> None: ...
    def poll(self) -> int | None: ...
    def pump(self) -> None: ...
    def close(self) -> None: ...


class CheckLauncher(Protocol):
    def validate(self, command: Any) -> None: ...
    def spawn(
        self,
        command: Any,
        *,
        marker: Path,
        on_stdout: Callable[[bytes], None],
        on_stderr: Callable[[bytes], None],
    ) -> CheckProcess: ...


class _Capture:
    def __init__(self, out: BudgetedFile, err: BudgetedFile, maximum: int, redactor: Redactor) -> None:
        self.files, self.maximum, self.redactor = {"stdout": out, "stderr": err}, maximum, redactor
        self.used = 0
        self.pending = {"stdout": bytearray(), "stderr": bytearray()}
        self.truncated = False
        self.activity = 0
        self.discard: set[str] = set()

    def _write(self, stream: str, raw: bytes) -> None:
        safe = self.redactor.text(raw.decode("utf-8", "replace")).encode("utf-8")
        remaining = self.maximum - len(_TRUNCATED) - self.used
        if len(safe) > remaining:
            if remaining > 0:
                self.files[stream].write(safe[:remaining])
                self.used += remaining
            if not self.truncated:
                self.files[stream].write(_TRUNCATED)
                self.used += len(_TRUNCATED)
                self.truncated = True
        elif not self.truncated:
            self.files[stream].write(safe)
            self.used += len(safe)

    def feed(self, stream: str, chunk: bytes) -> None:
        self.activity += len(chunk)
        if self.truncated:
            return  # producer pipes are still drained; no unbounded buffers/queues
        pending = self.pending[stream]
        for piece in chunk.splitlines(keepends=True):
            ended = piece.endswith((b"\n", b"\r"))
            if stream not in self.discard:
                if len(pending) + len(piece) <= 65_536:
                    pending.extend(piece)
                else:
                    pending.clear()
                    self.discard.add(stream)
                    self._write(stream, _TRUNCATED)
            if ended:
                if stream not in self.discard:
                    self._write(stream, bytes(pending))
                pending.clear()
                self.discard.discard(stream)

    def finish(self) -> None:
        for stream, pending in self.pending.items():
            if pending and not self.truncated:
                self._write(stream, bytes(pending))
            pending.clear()


class _Sleep:
    @staticmethod
    def sleep(seconds: float) -> None:
        time.sleep(seconds)


@dataclass
class _PendingCheck:
    process: CheckProcess
    ownership: ProcessOwnership
    marker: Path
    intent: Path
    reaped: bool = False


class CheckExecutor:
    kind = "command"
    definition_schema_urn = "urn:skm:planning:specification:v1#/$defs/command_definition"

    def __init__(  # noqa: PLR0913 - explicit host factory dependencies
        self,
        *,
        storage: StorageBudget,
        capture_floor_bytes: int,
        state_dir: Path,
        isolation_registry: Any,
        profile: str,
        host: Any,
        sanitized_env: Mapping[str, str],
        process: CheckLauncher | None = None,
        allow_pgroup_best_effort: bool = False,
        max_timeout_seconds: int = 7200,
    ) -> None:
        if capture_floor_bytes < 0 or max_timeout_seconds < 1:
            raise ValueError("negative capture admission floor")
        self.storage, self.floor, self.state_dir = storage, capture_floor_bytes, state_dir
        self.max_timeout = max_timeout_seconds
        self.registry, self.profile, self.host = isolation_registry, profile, host
        self.base_env = {key: value for key, value in sanitized_env.items() if key in _SAFE_ENV}
        self.process = process or TrustedCheckLauncher(allowed=allow_pgroup_best_effort and profile == "none")
        self._blocked: set[str] = set()
        self._recovery: dict[str, _PendingCheck] = {}
        self._pending: list[CheckProcess] = []  # uncertain containment remains owned for reconcile

    def argv(self, request: Any) -> tuple[str, ...]:
        argv = request.definition.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(v, str) or not v or "\0" in v for v in cast("list[object]", argv))
        ):
            raise ValueError("command requires nonempty argv")
        return tuple(cast("list[str]", argv))

    def reconcile(self, deps: Any) -> bool:
        """Retry only the retained handle; absent ownership never authorizes clearing a latch."""
        key = str(deps.environment.environment_id)
        record = self._recovery.get(key)
        if record is None:
            return False
        with environment_guard(self.state_dir, deps.environment, recovery=True) as quarantine:
            try:
                if not record.reaped:
                    stop = terminate_group(
                        ownership=record.ownership,
                        mode="reap",
                        backend=record.process,
                        clock=deps.monotonic,
                        sleeper=_Sleep(),
                        grace_int_seconds=0,
                        grace_term_seconds=0.1,
                        drain=lambda: None,
                    )
                    if not stop.stopped:
                        return False
                    record.process.close()
                    record.reaped = True
                if record.marker.exists():
                    remove_marker(record.marker, record.ownership)
                record.intent.unlink(missing_ok=True)
                clear_environment(quarantine, deps.environment, record.ownership)
            except (OSError, ValueError, RuntimeError):
                return False
            self._pending.remove(record.process)
            del self._recovery[key]
            self._blocked.discard(key)
            return True

    def run(self, request: Any, deps: Any) -> CheckFacts:
        if str(deps.environment.environment_id) in self._blocked:
            raise error_for(ErrorCode.CHECKOUT_BUSY, "check containment requires confirmed reap/reconcile")
        with environment_guard(self.state_dir, deps.environment) as quarantine:
            return self._run(request, deps, quarantine)

    def _run(self, request: Any, deps: Any, quarantine: Path) -> CheckFacts:  # noqa: PLR0912, PLR0915 - one owned check lifecycle
        owner = request.isolation.owner
        if owner.unit_kind != "check" or owner.unit_id != request.check_execution_id:
            raise ValueError("check owner must bind the exact check execution")
        directory = safe_join(self.state_dir / "checks", str(request.check_execution_id))
        directory.mkdir(mode=0o700, parents=True, exist_ok=False)
        out, err = directory / "stdout", directory / "stderr"
        started = deps.monotonic.monotonic()
        facts = CheckFacts(None, False, None, False, out, err, (), 0)
        maximum = request.output_limits.get("capture_max_bytes", 50 * 1024 * 1024)
        if not isinstance(maximum, int) or isinstance(maximum, bool) or maximum < 128:
            raise ValueError("invalid capture byte ceiling")
        if directory.resolve().is_relative_to(request.cwd.resolve()):
            raise ValueError("check capture must be outside checkout")
        # Storage admission precedes wrap/spawn. Both streams share this one reservation.
        with self.storage.reserve(
            directory, owner_id=str(owner.unit_id), max_bytes=maximum, max_files=2, min_free_bytes=self.floor
        ) as reservation:
            capture = _Capture(
                reservation.open_file(out),
                reservation.open_file(err),
                maximum,
                Redactor((*DEFAULT_PATTERNS, re.compile(r"(?i)Bearer\s+\S+"))),
            )
            process: CheckProcess | None = None
            marker: Path | None = None
            wrapped: Any = None
            intent = Path(owner.identity_dir) / (str(owner.unit_id) + ".intent.json")
            cleaned = False
            try:
                argv = self.argv(request)
                if not 0 < request.timeout_seconds <= self.max_timeout or request.idle_timeout_seconds < 0:
                    raise ValueError("invalid check timeout")
                if self.profile == "none" and (
                    request.isolation.read_only_root or request.isolation.network != "full"
                ):
                    raise error_for(
                        ErrorCode.SANDBOX_UNAVAILABLE,
                        "unconfined checks cannot enforce read-only or network restrictions",
                    )
                env = {
                    "COMPOSER_PROCESS_TIMEOUT": "0",
                    **self.base_env,
                    **{k: v for k, v in request.env_allow.items() if k in _SAFE_ENV | _IDENTIFIERS},
                }
                home = self.state_dir / "check-home" / str(owner.attempt_id)
                home.mkdir(mode=0o700, parents=True, exist_ok=True)
                temporary = directory / "tmp"
                temporary.mkdir(mode=0o700)
                env.update(
                    {
                        "HOME": str(home),
                        "TMPDIR": str(temporary),
                        "CI": "1",
                        "PYTHONUNBUFFERED": "1",
                        "SKM_CHECK_ID": str(owner.unit_id),
                        "SKM_CHECK_ATTEMPT": str(owner.attempt_id),
                    }
                )
                if request.cwd != request.isolation.workdir or not any(
                    request.cwd.resolve().is_relative_to(p.resolve())
                    for p in deps.environment.mounts.values()
                ):
                    raise ValueError("check cwd differs from its admitted environment/isolation")
                if request.isolation.credential_mounts:
                    raise error_for(
                        ErrorCode.SANDBOX_UNAVAILABLE,
                        "check credential mounts require a dedicated build credential adapter",
                    )
                spec = replace(request.isolation, env=env)
                intent = Path(owner.identity_dir) / (str(owner.unit_id) + ".intent.json")
                intent.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
                if intent.exists():
                    raise ValueError("check launch is already prepared or uncertain")
                atomic_write(
                    intent, json.dumps(asdict(owner), default=str).encode(), mode=0o600, private=True
                )
                backend = self.registry.get(self.profile)
                available = backend.available(self.host)
                if available.get("available") is not True:
                    raise error_for(ErrorCode.SANDBOX_UNAVAILABLE, "required check sandbox unavailable")
                # Backend.wrap verifies the actual required properties before any process starts.
                wrapped = backend.wrap(argv, spec)
                if wrapped.ownership.owner != owner:
                    raise ValueError("wrapped process belongs to another owner")
                self.process.validate(wrapped)
                marker = claim_marker(Path(owner.identity_dir), wrapped.ownership)
                deps.cancel.raise_if_cancelled()
                atomic_write(
                    quarantine,
                    json.dumps(
                        {
                            "environment_id": str(deps.environment.environment_id),
                            "locator": deps.environment.locator,
                            **asdict(wrapped.ownership),
                        },
                        default=str,
                    ).encode(),
                    mode=0o600,
                    private=True,
                )
                process = self.process.spawn(
                    wrapped,
                    marker=marker,
                    on_stdout=lambda chunk: capture.feed("stdout", chunk),
                    on_stderr=lambda chunk: capture.feed("stderr", chunk),
                )
                update_marker(marker, process.identity, ownership=wrapped.ownership, pgid=process.pid)
                idle_at = started
                observed_activity = capture.activity
                while True:
                    process.pump()
                    code = process.poll()
                    if code is not None:
                        facts = replace(facts, exit_code=code)
                        break
                    now = deps.monotonic.monotonic()
                    if capture.activity != observed_activity:
                        idle_at, observed_activity = now, capture.activity
                    if now - started >= request.timeout_seconds:
                        facts = replace(facts, timed_out=True)
                        break
                    if deps.cancel.cancelled:
                        facts = replace(facts, interrupted=True)
                        break
                    if request.idle_timeout_seconds and now - idle_at >= request.idle_timeout_seconds:
                        deps.log.debug("check_idle_suspected", check_execution_id=str(owner.unit_id))
                        idle_at = now  # diagnostic only: never a second kill deadline
                    deps.cancel.wait(0.01)
                stop = terminate_group(
                    ownership=wrapped.ownership,
                    mode="cancel",
                    backend=process,
                    clock=deps.monotonic,
                    sleeper=_Sleep(),
                    grace_int_seconds=0.1,
                    grace_term_seconds=0.1,
                    drain=process.pump,
                )
                process.pump()
                if stop.stopped:
                    process.close()
                    cleaned = True
                    remove_marker(marker, wrapped.ownership)
                    intent.unlink()
                else:
                    facts = replace(facts, exit_code=None, interrupted=True)
                    self._pending.append(process)
                reports: list[Path] = []
                for relative in request.definition.get("report_files", ()):
                    path = safe_join(request.cwd, relative)
                    if path.is_file():
                        reports.append(path)
                    else:
                        capture.feed("stderr", f"report file missing: {relative}\n".encode())
                facts = replace(facts, report_files=tuple(reports))
            except CheckLaunchError as error:
                process = error.process
                if not isinstance(error.primary, Exception):
                    raise error.primary from error
                facts = replace(
                    facts,
                    spawn_error="CHECK_COMMAND_NOT_FOUND"
                    if isinstance(error.primary, FileNotFoundError)
                    else type(error.primary).__name__,
                )
            except SkmError as error:
                facts = replace(facts, spawn_error=str(error.code))
            except FileNotFoundError:
                facts = replace(facts, spawn_error="CHECK_COMMAND_NOT_FOUND")
            except (OSError, ValueError, RuntimeError) as error:
                facts = replace(facts, spawn_error=type(error).__name__, interrupted=process is not None)
            finally:
                if (
                    process is not None
                    and wrapped is not None
                    and not cleaned
                    and process not in self._pending
                ):
                    # An IO/poll/marker failure after spawn must still attempt bounded shutdown.
                    try:
                        stop = terminate_group(
                            ownership=wrapped.ownership,
                            mode="cancel",
                            backend=process,
                            clock=deps.monotonic,
                            sleeper=_Sleep(),
                            grace_int_seconds=0.1,
                            grace_term_seconds=0.1,
                            drain=process.pump,
                        )
                        if stop.stopped:
                            process.close()
                            cleaned = True
                            if marker is not None:
                                remove_marker(marker, wrapped.ownership)
                            intent.unlink(missing_ok=True)
                    except (OSError, ValueError, RuntimeError):
                        pass  # retain durable owner and containment for reconcile
                if process is not None and not cleaned and process not in self._pending:
                    self._pending.append(process)
                if cleaned and wrapped is not None:
                    clear_environment(quarantine, deps.environment, wrapped.ownership)
                elif quarantine.exists():
                    key = str(deps.environment.environment_id)
                    self._blocked.add(key)
                    if process is not None and marker is not None and wrapped is not None:
                        self._recovery[key] = _PendingCheck(process, wrapped.ownership, marker, intent)
                    facts = replace(facts, exit_code=None, interrupted=True)
                capture.finish()
        return replace(facts, duration_seconds=max(0, deps.monotonic.monotonic() - started))


class ReproductionRunner(CheckExecutor):
    @override
    def argv(self, request: Any) -> tuple[str, ...]:
        if not request.isolation.read_only_root or request.isolation.workdir in request.isolation.writable:
            raise error_for(ErrorCode.SANDBOX_UNAVAILABLE, "reproduction requires read-only isolation")
        return super().argv(request)


def command_check_runner(**kwargs: Any) -> CheckRunner:
    return cast("CheckRunner", CheckExecutor(**kwargs))


def reproduction_runner(**kwargs: Any) -> CheckRunner:
    return cast("CheckRunner", ReproductionRunner(**kwargs))
