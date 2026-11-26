"""Shared ``AgentRuntime`` session management for headless CLI runtime adapters.

Claude Code, Codex and Grok drive their CLI identically once a launch plan exists: private step
state, a storage-budgeted transcript, a ``CliSession`` on a driver thread, buffered events,
cancellation classification and auth-state tracking. ``CliAgentRuntime`` owns that lifecycle; an
adapter supplies its detector, launch plan, stream parser and self-loaded context.
"""

from __future__ import annotations

import os
import shutil
import threading
import time
from abc import abstractmethod
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar, Final, Literal, Protocol, override
from uuid import UUID

from skm.adapters.runtimes.pool.quota_prober import opus_fallback
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, SkmError
from skm.modules.runtimes.domain.capability import Capability, RuntimeCapabilities, parse_capabilities
from skm.modules.runtimes.domain.detection import CancellationResult, DetectProbe
from skm.modules.runtimes.domain.error_rules import ErrorClass, ErrorRule, parse_error_rules
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership, SecretStr, validate_request
from skm.modules.runtimes.domain.result import RuntimeResult
from skm.modules.runtimes.domain.session_events import CancelIgnored, SessionEvent
from skm.modules.runtimes.ports import AgentRuntime, SessionHandle
from skm.platform.config.sources.document import decode_document
from skm.platform.fs.storage_budget import StorageBudget, StorageOwnerIdentity
from skm.platform.logging.logger import get_logger
from skm.platform.process.identity import ProcessIdentity, identity_of, is_same_process
from skm.platform.system_clock import SystemClock, SystemMonotonic

from .binding import bind_launch, bind_observation, verified_probe
from .cancel import Sleeper
from .observation import LiveQueue
from .probe import HELP_TIMEOUT_SECONDS, VERSION_TIMEOUT_SECONDS, ProbeCacheKey
from .session import CliSession, ProcessRunner, SessionLimits, StreamParser, TrustedProcessRunner
from .transcript import TranscriptWriter

if TYPE_CHECKING:
    from skm.kernel.clock import Clock, Monotonic
    from skm.modules.execution.ports import WrappedCommand
    from skm.modules.runtimes.domain.ids import Digest

__all__: list[str] = []

_RETRY_AFTER_CLASSES: Final = frozenset({ErrorClass.RATE_LIMIT, ErrorClass.QUOTA})
_WAIT_SECONDS: Final = 0.05
_LOG = get_logger("adapters.runtimes")

type OwnershipKind = Literal["cgroup", "container", "pgroup_best_effort"]


class ProbedCli(Protocol):
    """Probe facts every CLI adapter needs to launch and describe its binary."""

    @property
    def binary_locator(self) -> str: ...

    @property
    def binary_realpath(self) -> str: ...

    @property
    def binary_sha256(self) -> Digest: ...

    @property
    def version(self) -> str | None: ...

    @property
    def missing_required_flags(self) -> tuple[str, ...]: ...

    @property
    def cache_key(self) -> ProbeCacheKey: ...


class CliProbeDetector[P](Protocol):
    """The probing side of an adapter's ``CliDetector``."""

    @property
    def last_probed(self) -> P | None: ...

    def probe(
        self,
        *,
        binary: str,
        environ: Mapping[str, str],
        env_allowlist: tuple[str, ...],
        adapter_version: str,
        launch_config_digest: Digest,
        version_timeout_seconds: float = ...,
        help_timeout_seconds: float = ...,
    ) -> P: ...


class _SystemSleeper:
    def sleep(self, seconds: float) -> None:
        time.sleep(max(0.0, seconds))


@cache
def load_static_declarations(package_dir: Path) -> tuple[RuntimeCapabilities, tuple[ErrorRule, ...]]:
    """Parse an adapter's ``capabilities.toml`` and ``error_rules.toml`` once per package."""
    caps_raw = decode_document((package_dir / "capabilities.toml").read_text(encoding="utf-8"), "toml")
    rules_raw = decode_document((package_dir / "error_rules.toml").read_text(encoding="utf-8"), "toml")
    caps = parse_capabilities(caps_raw)
    normalized_rules = tuple(
        rule if rule.error_class in _RETRY_AFTER_CLASSES else replace(rule, retry_after_from=None)
        for rule in parse_error_rules(rules_raw)
    )
    return caps, normalized_rules


def _current_storage_identity() -> StorageOwnerIdentity:
    ident = identity_of(os.getpid())
    if ident is not None and ident.boot_id and ident.start_ticks is not None:
        return StorageOwnerIdentity(ident.boot_id, ident.pid, str(ident.start_ticks))
    return StorageOwnerIdentity("local-boot", os.getpid(), "0")


def _storage_owner_alive(owner: StorageOwnerIdentity) -> bool | None:
    if owner.boot_id == "local-boot":
        return owner.pid == os.getpid()
    try:
        ticks = int(owner.start_identity)
    except ValueError:
        return None
    try:
        return is_same_process(ProcessIdentity(owner.pid, ticks, owner.boot_id))
    except OSError:
        return None


def _disk_free_bytes(path: Path) -> int:
    target = path if path.exists() else path.parent
    return shutil.disk_usage(target).free


def private_dir(path: Path) -> Path:
    """Create ``path`` with mode 0700 (forcing it on an existing directory) and return its realpath."""
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(path, 0o700)
    return path.resolve(strict=True)


def version_timeout(probe: DetectProbe) -> float:
    """Detect-time ``--version`` timeout: the probe budget, capped at the default."""
    if probe.timeout_seconds > 0:
        return min(float(probe.timeout_seconds), VERSION_TIMEOUT_SECONDS)
    return VERSION_TIMEOUT_SECONDS


def help_timeout(probe: DetectProbe) -> float:
    """Detect-time ``--help`` timeout: the probe budget, but never below the default."""
    if probe.timeout_seconds > 0:
        return max(float(probe.timeout_seconds), HELP_TIMEOUT_SECONDS)
    return HELP_TIMEOUT_SECONDS


class _SpawningCliSession(CliSession):
    """Thin subclass exposing process startup PID/ticks without touching protected fields externally."""

    def spawn_process(self) -> tuple[int | None, int | None]:
        with self._lock:
            if self._process is None:
                self._start()
            proc = self._process
        if proc is None:
            return None, None
        return proc.pid, proc.identity.start_ticks


@dataclass
class _ManagedSession:
    handle: SessionHandle
    requested_model: str
    cli_session: _SpawningCliSession
    cancel_event: threading.Event
    cond: threading.Condition = field(default_factory=threading.Condition)
    emitted: list[SessionEvent] = field(default_factory=list[SessionEvent])
    done: bool = False
    cancellation: CancellationResult | None = None
    driver: threading.Thread | None = None


class CliAgentRuntime[ProbedT: ProbedCli](AgentRuntime):
    """Session lifecycle shared by production CLI runtimes; adapters fill in the CLI specifics."""

    display_name: ClassVar[str]
    """Human name used in error messages, e.g. ``"Claude Code"``."""
    default_binary: ClassVar[str]
    """Binary looked up on ``PATH`` when neither the probe nor the host names one."""
    short_name: ClassVar[str]
    """Short slug for state directories and driver thread names."""
    accept_lingering_result: ClassVar[bool] = True
    scratch_directories: ClassVar[tuple[str, ...]] = ()
    """Step-local directories whose retention ends after confirmed process cleanup."""
    sensitive_env_names: ClassVar[tuple[str, ...]] = ()

    def __init__(  # noqa: PLR0913 - explicit host injection boundary without ambient reads
        self,
        *,
        package_dir: Path,
        detector: CliProbeDetector[ProbedT],
        apply_probe: Callable[[RuntimeCapabilities, ProbedT | None], RuntimeCapabilities],
        state_dir: Path | None,
        binary: str | None,
        environ: Mapping[str, str] | None,
        user_home: Path | None,
        allow_pgroup_best_effort: bool,
        require_exec_binding: bool,
        ownership_kind: OwnershipKind,
        process_runner: ProcessRunner | None,
        storage_budget: StorageBudget | None,
        clock: Clock | None,
        monotonic: Monotonic | None,
        sleeper: Sleeper | None,
        poll_interval_seconds: float,
        result_grace_seconds: float,
        live_queue_factory: Callable[[], LiveQueue | None] | None,
        local_auth: Callable[[], Mapping[str, str]] | None = None,
    ) -> None:
        static_caps, rules = load_static_declarations(package_dir)
        self._static_caps = static_caps
        self._error_rules = rules
        self._probe_detector = detector
        self._apply_probe_fn = apply_probe
        self._state_dir = state_dir
        self._binary = binary
        self._environ: Mapping[str, str] = dict(environ) if environ is not None else {}
        self._user_home = user_home
        self._allow_pgroup_best_effort = allow_pgroup_best_effort
        self._require_exec_binding = require_exec_binding
        self._ownership_kind: OwnershipKind = ownership_kind
        self._process_runner = process_runner
        self._storage_budget = storage_budget
        self._budgets_by_root: dict[Path, StorageBudget] = {}
        self._clock = clock if clock is not None else SystemClock()
        self._monotonic = monotonic if monotonic is not None else SystemMonotonic()
        self._sleeper: Sleeper = sleeper if sleeper is not None else _SystemSleeper()
        self._poll_interval_seconds = poll_interval_seconds
        self._result_grace_seconds = result_grace_seconds
        self._live_queue_factory = live_queue_factory
        self._local_auth = local_auth
        self._auth_state = AuthState.UNKNOWN
        self._lock = threading.RLock()
        self._sessions: dict[str, _ManagedSession] = {}

    # Adapter-specific hooks ------------------------------------------------------------------

    @property
    @abstractmethod
    def launch_config_digest(self) -> str:
        """Digest of the launch configuration that participates in the probe cache key."""

    def _last_probed(self) -> ProbedT | None:
        """Most recent probe of this adapter's detector, if any."""
        return self._probe_detector.last_probed

    def _apply_probe(self, probed: ProbedT | None) -> RuntimeCapabilities:
        """Static capabilities adjusted by what the probed binary supports."""
        return self._apply_probe_fn(self._static_caps, probed)

    def _probe_for_detect(self, candidate: str, probe: DetectProbe) -> ProbedT:
        """Probe ``candidate`` with timeouts derived from a host detect request."""
        return self._probe_detector.probe(
            binary=candidate,
            environ=self._environ,
            env_allowlist=probe.env_allowlist,
            adapter_version=self._static_caps.adapter_version,
            launch_config_digest=self.launch_config_digest,
            version_timeout_seconds=version_timeout(probe),
            help_timeout_seconds=help_timeout(probe),
        )

    @abstractmethod
    def _build_launch(
        self,
        request: AgentRequest,
        probed: ProbedT,
        *,
        step_dir: Path,
        ownership: ProcessOwnership,
    ) -> tuple[WrappedCommand, bytes]:
        """Wrapped command and stdin payload for one step."""

    @abstractmethod
    def _make_parser(
        self,
        request: AgentRequest,
        probed: ProbedT,
        redact: Callable[[str], str],
    ) -> StreamParser:
        """Stream parser for the adapter's machine-readable output."""

    def _validate_start(self, request: AgentRequest) -> None:
        """Adapter preconditions checked before probing the binary; none by default."""
        del request

    def _verify_bound_account(self, command: WrappedCommand, program: tuple[str, ...]) -> None:
        """Check account authority with the attested executable, if the adapter needs it."""
        del command, program

    def _observe_detected(self, probed: ProbedT) -> AuthState:
        """Return the authentication observation associated with this detection."""
        del probed
        return self.auth_state

    def _detect_details(self, probed: ProbedT) -> dict[str, str]:
        """Extra installation details reported after the binary identity."""
        del probed
        return {}

    def _register_launch_secrets(
        self, writer: TranscriptWriter, request: AgentRequest, env: Mapping[str, str]
    ) -> None:
        for secret in request.secret_env.values():
            writer.register_secret(secret.reveal())
        for name in self.sensitive_env_names:
            if value := env.get(name):
                writer.register_secret(value)

    def _with_local_auth(self, request: AgentRequest) -> AgentRequest:
        if self._local_auth is None:
            return request
        credentials = self._local_auth()
        if credentials.keys() - set(self.sensitive_env_names):
            raise CapabilityUnavailable(
                ErrorCode.RUNTIME_AUTH_EXPIRED, "Local account uses an unsupported provider credential"
            )
        provider = {name: SecretStr(value) for name, value in credentials.items()}
        return replace(request, secret_env={**request.secret_env, **provider})

    # Shared lifecycle ------------------------------------------------------------------------

    @property
    def auth_state(self) -> AuthState:
        with self._lock:
            return self._auth_state

    @override
    def capabilities(self) -> RuntimeCapabilities:
        return self._apply_probe(self._last_probed())

    @override
    def detect(self, probe: DetectProbe) -> RuntimeInstallation:
        probed = self._probe_for_detect(probe.binary or self._binary or self.default_binary, probe)
        detected_auth = self._observe_detected(probed)
        details: dict[str, str] = {
            "binary_sha256": probed.binary_sha256,
            "launch_config_digest": probed.cache_key.launch_config_digest,
            "adapter_version": probed.cache_key.adapter_version,
            "os_kernel": probed.cache_key.os_kernel,
            **self._detect_details(probed),
        }
        if probed.missing_required_flags:
            details["missing_flags"] = ",".join(probed.missing_required_flags)[:500]
        return RuntimeInstallation(
            host_id=probe.host_id,
            runtime_id=self.runtime_id,
            version=probed.version,
            binary_locator=probed.binary_locator,
            auth_state=detected_auth,
            detected_at=self._clock.now(),
            details=details,
        )

    @override
    def start(self, request: AgentRequest) -> SessionHandle:  # noqa: PLR0915 - ordered bound spawn lifecycle
        validate_request(request, self.capabilities())
        self._validate_start(request)
        probed = self._probe_for_start(request)
        caps = self._apply_probe(probed)
        if not caps.supports(Capability.HEADLESS_EXECUTION):
            limitation = caps.records[Capability.HEADLESS_EXECUTION].limitations
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                limitation or f"{self.display_name} headless execution is unsupported on this binary",
                details={
                    "capability": Capability.HEADLESS_EXECUTION.value,
                    "runtime_id": self.runtime_id,
                },
            )

        with self._lock:
            if request.request_id in self._sessions:
                raise ValueError(f"session {request.request_id!r} already started")

        state_root = self._resolve_state_root(request)
        steps_parent = private_dir(state_root / "steps")
        step_dir = private_dir(steps_parent / request.request_id)
        identity_dir = private_dir(Path(request.process_owner.identity_dir))
        ownership = ProcessOwnership(
            request.process_owner,
            self._ownership_kind,
            f"{self.runtime_id}/{request.request_id}",
        )

        bound_program = None

        def cleanup_scratch() -> None:
            if bound_program is not None:
                shutil.rmtree(step_dir / ".pinned-bin", ignore_errors=True)
            for name in self.scratch_directories:
                shutil.rmtree(step_dir / name, ignore_errors=True)

        try:
            launch_request = self._with_local_auth(request)
            command, stdin = self._build_launch(
                launch_request, probed, step_dir=step_dir, ownership=ownership
            )
            command, bound_program = bind_launch(request, probed, command, step_dir)
            if bound_program is not None:
                self._verify_bound_account(command, bound_program)
        except BaseException as exc:
            if isinstance(exc, SkmError) and exc.code is ErrorCode.RUNTIME_AUTH_EXPIRED:
                with self._lock:
                    self._auth_state = AuthState.EXPIRED
            cleanup_scratch()
            raise

        limits = SessionLimits(
            wall_timeout_seconds=float(request.limits.timeout_seconds),
            idle_timeout_seconds=float(request.limits.idle_timeout_seconds),
            result_grace_seconds=self._result_grace_seconds,
            poll_interval_seconds=self._poll_interval_seconds,
            max_stream_bytes=max(4096, request.limits.max_output_bytes),
        )
        try:
            reservation = self._budget_for(state_root).reserve(
                state_root,
                owner_id=request.request_id,
                max_bytes=limits.max_stream_bytes,
                min_free_bytes=0,
                max_files=3,
            )
            writer = TranscriptWriter(
                step_dir,
                reservation,
                max_stream_bytes=limits.max_stream_bytes,
                workdir=Path(request.workdir),
            )
        except BaseException:
            cleanup_scratch()
            raise
        self._register_launch_secrets(writer, request, command.env)

        try:
            parser = self._make_parser(request, probed, writer.redact)
            runner: ProcessRunner = (
                self._process_runner
                if self._process_runner is not None
                else TrustedProcessRunner(
                    allow_pgroup_best_effort=self._allow_pgroup_best_effort,
                    require_exec_binding=(
                        self._require_exec_binding or request.verification_context is not None
                    ),
                )
            )
            binding = bind_observation(request, probed, self._static_caps.adapter_version)
            cancel_event = threading.Event()
            live_queue = None if self._live_queue_factory is None else self._live_queue_factory()
            cli_session = _SpawningCliSession(
                command,
                stdin=stdin,
                parser=parser,
                limits=limits,
                transcript=writer,
                identity_dir=identity_dir,
                step_id=UUID(request.request_id),
                clock=self._monotonic,
                sleeper=self._sleeper,
                cancel_event=cancel_event,
                process=runner,
                utc_clock=self._clock,
                binding=binding,
                rules=self._error_rules,
                accept_lingering_result=self.accept_lingering_result,
                live=live_queue,
            )
        except BaseException:
            writer.close()
            cleanup_scratch()
            raise

        try:
            pid, start_ticks = cli_session.spawn_process()
        except BaseException:
            res = cli_session._result  # pyright: ignore[reportPrivateUsage]
            unconfirmed = (
                res is not None
                and res.failure is not None
                and res.failure.details.get("reason") == "cleanup_unconfirmed"
            )
            if not unconfirmed:
                cleanup_scratch()
            raise
        handle = SessionHandle(
            runtime_id=self.runtime_id,
            request_id=request.request_id,
            pid=pid,
            process_start_ticks=start_ticks,
            started_at=self._clock.now(),
            ownership=cli_session.ownership,
        )
        managed = _ManagedSession(
            handle=handle, requested_model=request.model, cli_session=cli_session, cancel_event=cancel_event
        )
        driver = threading.Thread(
            target=self._drive_session,
            args=(managed,),
            daemon=True,
            name=f"skm-{self.short_name}-{request.request_id[:8]}",
        )
        managed.driver = driver
        with self._lock:
            self._sessions[request.request_id] = managed
        driver.start()
        return handle

    @override
    def events(self, handle: SessionHandle) -> Iterator[SessionEvent]:
        managed = self._lookup(handle)
        index = 0
        while True:
            with managed.cond:
                ready = list(managed.emitted[index:])
                index += len(ready)
                done = managed.done
                if not ready and not done:
                    managed.cond.wait(timeout=_WAIT_SECONDS)
                    continue
            yield from ready
            if done:
                with managed.cond:
                    tail = list(managed.emitted[index:])
                yield from tail
                return

    @override
    def cancel(self, handle: SessionHandle, *, grace_seconds: float) -> CancellationResult:
        del grace_seconds  # Escalation follows the normative CliSession cancel stages.
        managed = self._lookup(handle)
        with managed.cond:
            if managed.cancellation is not None:
                return managed.cancellation
            already_done = managed.done
            managed.cancel_event.set()
            managed.cond.notify_all()
            while not managed.done:
                managed.cond.wait(timeout=_WAIT_SECONDS)

            ignored_events = [ev.signal for ev in managed.emitted if isinstance(ev, CancelIgnored)]
            res = managed.cli_session.result()
            failure = res.failure
            stopped = failure is None or failure.details.get("reason") != "cleanup_unconfirmed"
            if already_done and res.outcome != "cancelled":
                result_cancel = CancellationResult(stopped=stopped, signal_used=None, ignored=False)
            elif (failure is not None and failure.code is ErrorCode.CANCEL_IGNORED) or len(
                ignored_events
            ) >= 2:
                result_cancel = CancellationResult(stopped=stopped, signal_used="SIGKILL", ignored=True)
            elif len(ignored_events) == 1:
                result_cancel = CancellationResult(stopped=stopped, signal_used="SIGTERM", ignored=False)
            elif res.outcome == "cancelled":
                result_cancel = CancellationResult(stopped=stopped, signal_used="SIGINT", ignored=False)
            else:
                result_cancel = CancellationResult(stopped=stopped, signal_used=None, ignored=False)
            managed.cancellation = result_cancel
            return result_cancel

    @override
    def result(self, handle: SessionHandle) -> RuntimeResult:
        managed = self._lookup(handle)
        with managed.cond:
            while not managed.done:
                managed.cond.wait(timeout=_WAIT_SECONDS)
        res = managed.cli_session.result()
        self._update_auth_from_result(res)
        return res

    def _drive_session(self, managed: _ManagedSession) -> None:
        try:
            for ev in managed.cli_session.run():
                with managed.cond:
                    managed.emitted.append(ev)
                    managed.cond.notify_all()
            res = managed.cli_session.result()
            self._update_auth_from_result(res)
            if opus_fallback(managed.requested_model, res.observation):
                _LOG.warning("runtimes.silent_opus_fallback", step_id=managed.handle.request_id)
            if res.failure is None or res.failure.details.get("reason") != "cleanup_unconfirmed":
                for name in self.scratch_directories:
                    shutil.rmtree(managed.cli_session.transcript.step_dir / name, ignore_errors=True)
        finally:
            with managed.cond:
                managed.done = True
                managed.cond.notify_all()

    def _update_auth_from_result(self, res: RuntimeResult) -> None:
        with self._lock:
            if res.outcome == "completed":
                self._auth_state = AuthState.OK
            elif res.failure is not None and res.failure.code is ErrorCode.RUNTIME_AUTH_EXPIRED:
                self._auth_state = AuthState.EXPIRED

    def _lookup(self, handle: SessionHandle) -> _ManagedSession:
        with self._lock:
            managed = self._sessions.get(handle.request_id)
        if managed is None or managed.handle is not handle:
            raise ValueError(f"session handle does not belong to this {type(self).__name__} instance")
        return managed

    def _probe_for_start(self, request: AgentRequest) -> ProbedT:
        candidate = self._binary or self.default_binary
        if self._require_exec_binding or request.verification_context is not None:
            return verified_probe(
                request,
                self._last_probed(),
                candidate=candidate,
                environ=self._environ,
                adapter_version=self._static_caps.adapter_version,
                probe_config_digest=self.launch_config_digest,
            )
        try:
            return self._probe_binary(candidate, request.env_allowlist)
        except FileNotFoundError as exc:
            raise CapabilityUnavailable(
                ErrorCode.RUNTIME_NOT_INSTALLED,
                f"{self.display_name} CLI binary is not installed: {candidate}",
                details={"runtime_id": self.runtime_id},
                retryable=False,
            ) from exc

    def _probe_binary(self, candidate: str, env_allowlist: tuple[str, ...]) -> ProbedT:
        """Probe ``candidate`` with default timeouts before a launch."""
        return self._probe_detector.probe(
            binary=candidate,
            environ=self._environ,
            env_allowlist=env_allowlist,
            adapter_version=self._static_caps.adapter_version,
            launch_config_digest=self.launch_config_digest,
        )

    def _resolve_state_root(self, request: AgentRequest) -> Path:
        if self._state_dir is not None:
            return private_dir(self._state_dir)
        owner_parent = Path(request.process_owner.identity_dir).resolve().parent
        return private_dir(owner_parent / f"{self.short_name}-runtime-state")

    def _budget_for(self, state_root: Path) -> StorageBudget:
        if self._storage_budget is not None:
            return self._storage_budget
        with self._lock:
            existing = self._budgets_by_root.get(state_root)
            if existing is not None:
                return existing
            created = StorageBudget(
                private_dir(state_root / "locks"),
                free_bytes=_disk_free_bytes,
                identity=_current_storage_identity,
                owner_alive=_storage_owner_alive,
            )
            self._budgets_by_root[state_root] = created
            return created
