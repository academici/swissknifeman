"""Antigravity CLI adapter for the worker's supervised session lifecycle."""

from __future__ import annotations

import hashlib
import json
import posixpath
import sys
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import TYPE_CHECKING, override

from skm.adapters.runtimes._cli_session.binding import canonical_launch_digest
from skm.adapters.runtimes._cli_session.launch import (
    LaunchCommand,
    ensure_private_dir,
    landlock_argv,
    resolve_workdir,
)
from skm.adapters.runtimes._cli_session.probe import (
    ProbeCommandRunner,
    default_os_kernel,
    default_probe_runner,
)
from skm.adapters.runtimes._cli_session.runtime import CliAgentRuntime, OwnershipKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.capability import SelfLoadedSource
from skm.modules.runtimes.domain.classes import Effort, RoleId
from skm.platform.process.environment import build_env

from .detect import AntigravityDetector, ProbedBinary, apply_probe_to_capabilities
from .stream_parser import AntigravityStreamParser

if TYPE_CHECKING:
    from skm.adapters.runtimes._cli_session.session import ProcessRunner
    from skm.modules.execution.ports import WrappedCommand
    from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership
    from skm.platform.fs.storage_budget import StorageBudget

__all__ = ["AntigravityRuntime"]

_PACKAGE_DIR = Path(__file__).parent
_STREAM_FLAGS = ("--input-format", "stream-json", "--output-format", "stream-json")
_LAUNCH_FLAGS = (*_STREAM_FLAGS, "--sandbox", "--disable-slash-commands", "--print", "")
_AUTH_ENV = (
    "AGY_ADC_AUTH",
    "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_CLOUD_QUOTA_PROJECT",
    "GOOGLE_CLOUD_LOCATION",
)
_TLS_ENV = ("SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS")
_SETTINGS = {
    "allowNonWorkspaceAccess": False,
    "agentMode": "plan",
    "permissions": {"deny": ["command(*)", "mcp(*)", "read_url(*)"]},
}
_STARTUP_CONFIGS = (
    ".agents/hooks.json",
    ".agents/rules.json",
    ".agents/skills.json",
    ".agents/agents.json",
    ".agents/plugins.json",
    ".agents/mcp_config.json",
    ".agents/plugins",
    ".agent/hooks.json",
    ".agent/mcp_config.json",
    ".agent/plugins",
    ".antigravity/hooks",
    ".antigravity/config.toml",
    ".mcp.json",
)
_THREE_EFFORT_MODELS = frozenset(
    {
        "claude-sonnet-5-5",
        "claude-opus-5-5",
        "gemini-4-argon",
        "gemini-3.8-flash",
        "gemini-4-carbon",
    }
)
_EFFORT_SUFFIXES = frozenset(effort.value for effort in Effort)


def _model_args(request: AgentRequest) -> tuple[tuple[str, ...], frozenset[str]]:
    base, _, suffix = request.model.rpartition("-")
    family = base if suffix in _EFFORT_SUFFIXES else request.model
    if family in _THREE_EFFORT_MODELS and (suffix == "xhigh" or request.effort is Effort.XHIGH):
        raise CapabilityUnavailable(
            ErrorCode.MODEL_UNAVAILABLE, "Requested AGY model supports low through high"
        )
    if suffix in _EFFORT_SUFFIXES:
        if request.effort is not None and suffix != request.effort.value:
            raise CapabilityUnavailable(
                ErrorCode.MODEL_UNAVAILABLE, "AGY model selector conflicts with requested effort"
            )
        return ("--model", request.model), frozenset({base, request.model})
    if request.effort is None:
        return ("--model", request.model), frozenset({request.model})
    effort = request.effort.value
    return ("--model", request.model, "--effort", effort), frozenset(
        {request.model, f"{request.model}-{effort}"}
    )


class AntigravityRuntime(CliAgentRuntime[ProbedBinary]):
    runtime_id = "antigravity"
    display_name = "Antigravity"
    default_binary = "agy"
    short_name = "agy"
    sensitive_env_names = _AUTH_ENV
    accept_lingering_result = False
    scratch_directories = ("agy-home", "tmp")

    def __init__(  # noqa: PLR0913 - injected worker and process bindings
        self,
        *,
        state_dir: Path | None = None,
        binary: str | None = None,
        environ: Mapping[str, str] | None = None,
        local_auth: Callable[[], Mapping[str, str]] | None = None,
        probe_runner: ProbeCommandRunner = default_probe_runner,
        process_runner: ProcessRunner | None = None,
        storage_budget: StorageBudget | None = None,
        allow_pgroup_best_effort: bool = True,
        require_exec_binding: bool = False,
        ownership_kind: OwnershipKind = "pgroup_best_effort",
        result_grace_seconds: float = 30.0,
    ) -> None:
        detector = AntigravityDetector(run_cmd=probe_runner, os_kernel_fn=default_os_kernel)
        super().__init__(
            package_dir=_PACKAGE_DIR,
            detector=detector,
            apply_probe=apply_probe_to_capabilities,
            state_dir=state_dir,
            binary=binary,
            environ=environ,
            local_auth=local_auth,
            user_home=None,
            allow_pgroup_best_effort=allow_pgroup_best_effort,
            require_exec_binding=require_exec_binding,
            ownership_kind=ownership_kind,
            process_runner=process_runner,
            storage_budget=storage_budget,
            clock=None,
            monotonic=None,
            sleeper=None,
            poll_interval_seconds=0.05,
            result_grace_seconds=result_grace_seconds,
            live_queue_factory=None,
        )

    @property
    @override
    def launch_config_digest(self) -> str:
        template = [
            self._static_caps.adapter_version,
            _LAUNCH_FLAGS,
            _SETTINGS,
            _AUTH_ENV,
            _STARTUP_CONFIGS,
            "landlock-abi3:step-home,tmp",
        ]
        return "sha256:" + hashlib.sha256(json.dumps(template, sort_keys=True).encode()).hexdigest()

    @override
    def _detect_details(self, probed: ProbedBinary) -> dict[str, str]:
        del probed
        return {"launch_config_kind": "inventory_probe"}

    @override
    def self_loaded_context(self, request: AgentRequest) -> tuple[SelfLoadedSource, ...]:
        return tuple(
            SelfLoadedSource(
                load.kind,
                load.locator.replace("{workdir}", posixpath.normpath(request.workdir)),
                load.files,
                load.when,
            )
            for load in self._static_caps.self_loads
        )

    @override
    def _validate_start(self, request: AgentRequest) -> None:
        if request.role is RoleId.REGISTRAR or request.isolation_profile is not IsolationProfile.LANDLOCK:
            raise CapabilityUnavailable(
                ErrorCode.SANDBOX_UNAVAILABLE, "AGY requires the Landlock profile and cannot register changes"
            )
        if request.config_mode != "isolated" or request.mcp_servers:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "AGY requires a private client home and cannot bind MCP servers",
            )
        if request.permissions.fs_write.allow:
            raise CapabilityUnavailable(
                ErrorCode.SANDBOX_UNAVAILABLE, "AGY's supervised launch supports read-only checkouts"
            )
        _model_args(request)

    @override
    def _build_launch(
        self, request: AgentRequest, probed: ProbedBinary, *, step_dir: Path, ownership: ProcessOwnership
    ) -> tuple[WrappedCommand, bytes]:
        workdir = resolve_workdir(request)
        # Managed checkouts can carry executable customization, even with an empty HOME.
        for root in (workdir, *workdir.parents):
            for relative in _STARTUP_CONFIGS:
                path = root / relative
                if path.exists() or path.is_symlink():
                    raise CapabilityUnavailable(
                        ErrorCode.SANDBOX_UNAVAILABLE,
                        "AGY workspace startup configuration detected",
                        details={"path": str(path)},
                    )
            if (root / ".git").exists():
                break
        step = step_dir.resolve(strict=True)
        if step.is_relative_to(workdir) or workdir.is_relative_to(step):
            raise CapabilityUnavailable(
                ErrorCode.SANDBOX_UNAVAILABLE, "AGY state and checkout must not overlap"
            )
        home = ensure_private_dir(step / "agy-home")
        temp = ensure_private_dir(step / "tmp")

        # The agent receives native provider authentication, TLS roots, and explicit allowlisted/extra env
        # only. The SKM assignment token (request.secret_env) is neither a Google credential nor usable
        # without an explicitly bound SKM MCP server.
        env = build_env(
            self._environ,
            allow=(*_AUTH_ENV, *_TLS_ENV, *request.env_allowlist),
            extra={
                **request.extra_env,
                **{name: secret.reveal() for name, secret in request.secret_env.items() if name in _AUTH_ENV},
            },
            home=home,
        )
        env.update(
            TMPDIR=str(temp),
            XDG_CONFIG_HOME=str(home / ".config"),
            XDG_CACHE_HOME=str(home / ".cache"),
            XDG_DATA_HOME=str(home / ".local/share"),
            XDG_STATE_HOME=str(home / ".local/state"),
        )

        model_args, _ = _model_args(request)
        settings = json.dumps(_SETTINGS, sort_keys=True)
        argv = (probed.binary_realpath, *_LAUNCH_FLAGS, *model_args, "--settings", settings)
        wrapped = landlock_argv(
            argv, (home, temp), python_executable=sys.executable, protected=(str(workdir),)
        )
        template = canonical_launch_digest(
            {
                "adapter_version": self._static_caps.adapter_version,
                "launch_flags": _LAUNCH_FLAGS,
                "settings": _SETTINGS,
                "auth_env": _AUTH_ENV,
                "tls_env": _TLS_ENV,
                "env_allowlist": sorted(set(request.env_allowlist)),
                "extra_env_keys": sorted(request.extra_env),
                "startup_configs": _STARTUP_CONFIGS,
                "isolation_profile": str(request.isolation_profile),
                "landlock": "landlock-abi3:step-home,tmp,protect-workdir",
            }
        )
        payload = {"event": "user", "message": {"content": request.rendered_prompt}}
        stdin = (json.dumps(payload, ensure_ascii=False) + "\n").encode()
        return LaunchCommand(
            wrapped, env, workdir, ownership, verification_template=template
        ).as_wrapped(), stdin

    @override
    def _make_parser(
        self, request: AgentRequest, probed: ProbedBinary, redact: Callable[[str], str]
    ) -> AntigravityStreamParser:
        _, models = _model_args(request)
        return AntigravityStreamParser(
            models=models, version=probed.version, workdir=str(resolve_workdir(request)), redact=redact
        )
