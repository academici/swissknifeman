"""Claude Code ``AgentRuntime`` adapter with isolated step configuration."""

from __future__ import annotations

import posixpath
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Final, override

from skm.adapters.runtimes._cli_session.probe import (
    ProbeCommandRunner,
    default_os_kernel,
    default_probe_runner,
)
from skm.adapters.runtimes._cli_session.runtime import (
    CliAgentRuntime,
    OwnershipKind,
)
from skm.modules.runtimes.domain.capability import SelfLoadedSource, SelfLoadKind
from skm.modules.runtimes.domain.ids import RuntimeId

from .detect import ClaudeDetector, ProbedBinary, apply_probe_to_capabilities
from .launch import AUTH_ENV_NAMES, build_launch_plan, compute_launch_config_digest
from .stream_parser import ClaudeStreamParser

if TYPE_CHECKING:
    from skm.adapters.runtimes._cli_session.cancel import Sleeper
    from skm.adapters.runtimes._cli_session.observation import LiveQueue
    from skm.adapters.runtimes._cli_session.proxy_bridge import LocalProxyBridge, ProxyEndpoint
    from skm.adapters.runtimes._cli_session.session import ProcessRunner, StreamParser
    from skm.kernel.clock import Clock, Monotonic
    from skm.modules.execution.ports import WrappedCommand
    from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership, SecretStr
    from skm.platform.fs.storage_budget import StorageBudget

__all__ = ["ClaudeCodeRuntime"]

_PACKAGE_DIR: Final = Path(__file__).resolve().parent


class ClaudeCodeRuntime(CliAgentRuntime[ProbedBinary]):
    """Production ``AgentRuntime`` adapter for headless ``claude -p --output-format stream-json``."""

    runtime_id: RuntimeId = "claude_code"
    display_name = "Claude Code"
    default_binary = "claude"
    short_name = "claude"
    sensitive_env_names = AUTH_ENV_NAMES

    def __init__(  # noqa: PLR0913 - explicit host injection boundary without ambient reads
        self,
        *,
        state_dir: Path | None = None,
        binary: str | None = None,
        environ: Mapping[str, str] | None = None,
        egress_proxy: ProxyEndpoint | None = None,
        local_auth: Callable[[], Mapping[str, str]] | None = None,
        copy_credentials: bool = True,
        allow_skip_permissions: bool = False,
        policy_profile: str | None = None,
        user_home: Path | None = None,
        setup_token: SecretStr | None = None,
        extra_dirs: Sequence[str] = (),
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
        subagent_disclosed: bool = False,
        live_queue_factory: Callable[[], LiveQueue | None] | None = None,
    ) -> None:
        self._copy_credentials = copy_credentials
        self._setup_token = setup_token
        self._allow_skip_permissions = allow_skip_permissions
        self._policy_profile = policy_profile
        self._extra_dirs = tuple(extra_dirs)
        self._subagent_disclosed = subagent_disclosed
        self._detector = ClaudeDetector(run_cmd=probe_runner, os_kernel_fn=os_kernel_fn)
        super().__init__(
            package_dir=_PACKAGE_DIR,
            detector=self._detector,
            apply_probe=apply_probe_to_capabilities,
            state_dir=state_dir,
            binary=binary,
            environ=environ,
            egress_proxy=egress_proxy,
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
            allow_skip_permissions=self._allow_skip_permissions,
            copy_credentials=self._copy_credentials,
            use_setup_token=self._setup_token is not None,
        )

    @override
    def self_loaded_context(self, request: AgentRequest) -> tuple[SelfLoadedSource, ...]:
        effective_profile = self._policy_profile or request.labels.get("policy_profile")
        probed = self._detector.last_probed
        if probed is not None and probed.safe_mode_supported and effective_profile != "trusted-full-access":
            return ()
        locator = f"{posixpath.normpath(request.workdir)}/.claude"
        return (
            SelfLoadedSource(
                kind=SelfLoadKind.SKILLS,
                locator=locator,
                files=(".claude/skills/**", ".claude/agents/**"),
                when="on_access",
                trust="untrusted",
            ),
        )

    @override
    def _detect_details(self, probed: ProbedBinary) -> dict[str, str]:
        return {"safe_mode": "true" if probed.safe_mode_supported else "false"}

    @override
    def _build_launch(
        self,
        request: AgentRequest,
        probed: ProbedBinary,
        *,
        step_dir: Path,
        ownership: ProcessOwnership,
        proxy_bridge: LocalProxyBridge | None = None,
    ) -> tuple[WrappedCommand, bytes]:
        plan = build_launch_plan(
            request,
            binary_path=probed.binary_realpath,
            step_dir=step_dir,
            ownership=ownership,
            proxy_bridge=proxy_bridge,
            host_environ=self._environ,
            probed=probed,
            policy_profile=self._policy_profile,
            allow_skip_permissions=self._allow_skip_permissions,
            copy_credentials=self._copy_credentials,
            user_home=self._user_home,
            setup_token=self._setup_token,
            extra_dirs=self._extra_dirs,
        )
        return plan.command.as_wrapped(), plan.stdin

    @override
    def _make_parser(
        self,
        request: AgentRequest,
        probed: ProbedBinary,
        redact: Callable[[str], str],
    ) -> StreamParser:
        return ClaudeStreamParser(
            runtime_version=probed.version,
            redact=redact,
            subagent_disclosed=self._subagent_disclosed,
        )
