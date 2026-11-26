"""Codex ``AgentRuntime`` adapter with isolated ``CODEX_HOME`` configuration."""

from __future__ import annotations

import posixpath
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, Final, override

from skm.adapters.runtimes._cli_session.launch import home_from_env
from skm.adapters.runtimes._cli_session.probe import (
    ProbeCommandRunner,
    default_os_kernel,
    default_probe_runner,
)
from skm.adapters.runtimes._cli_session.runtime import (
    CliAgentRuntime,
    OwnershipKind,
    help_timeout,
    version_timeout,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.runtimes.domain.capability import SelfLoadedSource, SelfLoadKind
from skm.modules.runtimes.domain.ids import RuntimeId
from skm.modules.runtimes.domain.installation import AuthState

from .detect import LOGIN_TIMEOUT_SECONDS, CodexDetector, ProbedBinary, apply_probe_to_capabilities
from .launch import build_launch_plan, compute_launch_config_digest
from .stream_parser import CodexStreamParser

if TYPE_CHECKING:
    from skm.adapters.runtimes._cli_session.cancel import Sleeper
    from skm.adapters.runtimes._cli_session.observation import LiveQueue
    from skm.adapters.runtimes._cli_session.session import ProcessRunner, StreamParser
    from skm.kernel.clock import Clock, Monotonic
    from skm.modules.execution.ports import WrappedCommand
    from skm.modules.runtimes.domain.detection import DetectProbe
    from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership
    from skm.platform.fs.storage_budget import StorageBudget

__all__ = ["CodexRuntime"]

_PACKAGE_DIR: Final = Path(__file__).resolve().parent


class CodexRuntime(CliAgentRuntime[ProbedBinary]):
    """Production ``AgentRuntime`` adapter for headless ``codex -a never exec --json``."""

    runtime_id: RuntimeId = "codex"
    display_name = "Codex"
    default_binary = "codex"
    short_name = "codex"
    sensitive_env_names = ("OPENAI_API_KEY", "CODEX_API_KEY")

    def __init__(  # noqa: PLR0913 - explicit host injection boundary without ambient reads
        self,
        *,
        state_dir: Path | None = None,
        binary: str | None = None,
        environ: Mapping[str, str] | None = None,
        local_auth: Callable[[], Mapping[str, str]] | None = None,
        copy_credentials: bool = True,
        allow_full_access: bool = False,
        policy_profile: str | None = None,
        user_home: Path | None = None,
        codex_home_user: Path | None = None,
        request_bypass: bool = False,
        allow_pgroup_best_effort: bool = True,
        require_exec_binding: bool = False,
        ownership_kind: OwnershipKind = "pgroup_best_effort",
        process_runner: ProcessRunner | None = None,
        probe_runner: ProbeCommandRunner = default_probe_runner,
        os_kernel_fn: Callable[[], str] = default_os_kernel,
        storage_budget: StorageBudget | None = None,
        clock: Clock | None = None,
        monotonic: Monotonic | None = None,
        sleeper: Sleeper | None = None,
        poll_interval_seconds: float = 0.05,
        result_grace_seconds: float = 30.0,
        live_queue_factory: Callable[[], LiveQueue | None] | None = None,
    ) -> None:
        self._copy_credentials = copy_credentials
        self._allow_full_access = allow_full_access
        self._policy_profile = policy_profile
        self._codex_home_user = codex_home_user
        self._request_bypass = request_bypass
        self._detector = CodexDetector(run_cmd=probe_runner, os_kernel_fn=os_kernel_fn)
        super().__init__(
            package_dir=_PACKAGE_DIR,
            detector=self._detector,
            apply_probe=apply_probe_to_capabilities,
            state_dir=state_dir,
            binary=binary,
            environ=environ,
            local_auth=local_auth,
            user_home=user_home,
            allow_pgroup_best_effort=allow_pgroup_best_effort,
            require_exec_binding=require_exec_binding,
            ownership_kind=ownership_kind,
            process_runner=process_runner,
            storage_budget=storage_budget,
            clock=clock,
            monotonic=monotonic,
            sleeper=sleeper,
            poll_interval_seconds=poll_interval_seconds,
            result_grace_seconds=result_grace_seconds,
            live_queue_factory=live_queue_factory,
        )

    @property
    @override
    def launch_config_digest(self) -> str:
        return compute_launch_config_digest(
            adapter_version=self._static_caps.adapter_version,
            allow_full_access=self._allow_full_access,
            copy_credentials=self._copy_credentials,
            request_bypass=self._request_bypass,
        )

    @override
    def _detect_details(self, probed: ProbedBinary) -> dict[str, str]:
        return {"launch_config_kind": "inventory_probe"}

    @override
    def self_loaded_context(self, request: AgentRequest) -> tuple[SelfLoadedSource, ...]:
        """Codex reads ``AGENTS.md`` upwards from ``cwd`` even when ``CODEX_HOME`` is isolated."""
        locator = posixpath.normpath(request.workdir)
        return (
            SelfLoadedSource(
                kind=SelfLoadKind.PROJECT_INSTRUCTIONS,
                locator=locator,
                files=("AGENTS.md",),
                when="start",
                trust="untrusted",
            ),
        )

    @override
    def _probe_for_detect(self, candidate: str, probe: DetectProbe) -> ProbedBinary:
        login_timeout = (
            min(float(probe.timeout_seconds), LOGIN_TIMEOUT_SECONDS)
            if probe.timeout_seconds > 0
            else LOGIN_TIMEOUT_SECONDS
        )
        return self._detector.probe(
            binary=candidate,
            environ=self._native_login_environment(),
            env_allowlist=probe.env_allowlist,
            adapter_version=self._static_caps.adapter_version,
            launch_config_digest=self.launch_config_digest,
            version_timeout_seconds=version_timeout(probe),
            help_timeout_seconds=help_timeout(probe),
            login_timeout_seconds=login_timeout,
        )

    def _native_login_environment(self) -> Mapping[str, str]:
        env = dict(self._environ)
        env.pop("CODEX_HOME", None)
        home = home_from_env(self._codex_home_user, env, "CODEX_HOME_USER")
        if home is None:
            user_home = home_from_env(self._user_home, env)
            home = None if user_home is None else user_home / ".codex"
        if home is not None:
            env["CODEX_HOME"] = str(home)
        return env

    @override
    def _observe_detected(self, probed: ProbedBinary) -> AuthState:
        with self._lock:
            self._auth_state = probed.auth_state
        return probed.auth_state

    @override
    def _verify_bound_account(self, command: WrappedCommand, program: tuple[str, ...]) -> None:
        if any(command.env.get(name) for name in self.sensitive_env_names):
            return
        if (
            not command.env.get("CODEX_HOME")
            or self._detector.login_status(program, command.env) is not AuthState.OK
        ):
            raise CapabilityUnavailable(ErrorCode.RUNTIME_AUTH_EXPIRED, "Codex native login is unavailable")

    @override
    def _build_launch(
        self,
        request: AgentRequest,
        probed: ProbedBinary,
        *,
        step_dir: Path,
        ownership: ProcessOwnership,
    ) -> tuple[WrappedCommand, bytes]:
        plan = build_launch_plan(
            request,
            binary_path=probed.binary_realpath,
            step_dir=step_dir,
            ownership=ownership,
            host_environ=self._environ,
            probed=probed,
            policy_profile=self._policy_profile,
            allow_full_access=self._allow_full_access,
            copy_credentials=self._copy_credentials,
            user_home=self._user_home,
            codex_home_user=self._codex_home_user,
            request_bypass=self._request_bypass,
        )
        return plan.command.as_wrapped(), plan.stdin

    @override
    def _make_parser(
        self,
        request: AgentRequest,
        probed: ProbedBinary,
        redact: Callable[[str], str],
    ) -> StreamParser:
        return CodexStreamParser(
            default_model=request.model,
            runtime_version=probed.version,
            redact=redact,
        )
