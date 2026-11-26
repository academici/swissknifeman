"""Supervised, read-only Gemini CLI sessions."""

from __future__ import annotations

import json
import os
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
from skm.adapters.runtimes._cli_session.wire_values import bounded_model
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.capability import SelfLoadedSource
from skm.modules.runtimes.domain.classes import RoleId
from skm.platform.process.environment import build_env

from .detect import GeminiCliDetector, ProbedBinary, apply_probe_to_capabilities
from .stream_parser import GeminiCliStreamParser

if TYPE_CHECKING:
    from skm.adapters.runtimes._cli_session.session import ProcessRunner
    from skm.modules.execution.ports import WrappedCommand
    from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership
    from skm.platform.fs.storage_budget import StorageBudget

__all__ = ["GeminiCliRuntime"]

_API_KEY = "GEMINI_API_KEY"
_TLS_ENV = ("SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS")
_LAUNCH_FLAGS = ("--output-format", "stream-json", "--approval-mode", "plan", "--prompt", "")
_SETTINGS = {
    "advanced": {"ignoreLocalEnv": True},
    "security": {"auth": {"selectedType": "gemini-api-key"}, "disableYoloMode": True},
    "hooksConfig": {"enabled": False},
    "tools": {"core": ["list_directory", "read_file", "glob", "search_file_content"]},
    "general": {"enableAutoUpdate": False},
}
_WORKSPACE_CONFIG = (
    ".env",
    ".gemini/.env",
    ".gemini/settings.json",
    ".gemini/policies",
    ".gemini/commands",
    ".gemini/extensions",
)
_SYSTEM_CONFIG = (Path("/etc/gemini-cli/settings.json"), Path("/etc/gemini-cli/system-defaults.json"))


class GeminiCliRuntime(CliAgentRuntime[ProbedBinary]):
    runtime_id = "gemini_cli"
    display_name = "Gemini CLI"
    default_binary = "gemini"
    short_name = "gemini"
    accept_lingering_result = False
    scratch_directories = ("gemini-home", "tmp")
    sensitive_env_names = (_API_KEY,)

    def __init__(  # noqa: PLR0913 - injected host and process bindings
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
        super().__init__(
            package_dir=Path(__file__).parent,
            detector=GeminiCliDetector(run_cmd=probe_runner, os_kernel_fn=default_os_kernel),
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
        return canonical_launch_digest(
            {
                "adapter_version": self._static_caps.adapter_version,
                "argv": (*_LAUNCH_FLAGS, "--model", "{model}"),
                "settings": _SETTINGS,
                "env": (_API_KEY, *_TLS_ENV),
                "workspace_config": _WORKSPACE_CONFIG,
                "system_config": tuple(map(str, _SYSTEM_CONFIG)),
                "isolation": "landlock-abi3:step-home,tmp,protect-workdir",
            }
        )

    @override
    def _detect_details(self, probed: ProbedBinary) -> dict[str, str]:
        del probed
        return {"launch_config_kind": "inventory_probe"}

    @override
    def self_loaded_context(self, request: AgentRequest) -> tuple[SelfLoadedSource, ...]:
        workdir = str(Path(request.workdir))
        return tuple(
            SelfLoadedSource(load.kind, load.locator.replace("{workdir}", workdir), load.files, load.when)
            for load in self._static_caps.self_loads
        )

    @override
    def _validate_start(self, request: AgentRequest) -> None:
        if (
            request.isolation_profile is not IsolationProfile.LANDLOCK
            or request.permissions.fs_write.allow
            or request.role is RoleId.REGISTRAR
        ):
            raise CapabilityUnavailable(
                ErrorCode.SANDBOX_UNAVAILABLE, "Gemini CLI requires a read-only Landlock checkout"
            )
        if request.config_mode != "isolated" or request.mcp_servers:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE, "Gemini CLI requires a private home and runs without MCP"
            )
        if bounded_model(request.model) != request.model:
            raise CapabilityUnavailable(
                ErrorCode.MODEL_UNAVAILABLE, "Gemini CLI requires a valid model selector"
            )
        if request.rendered_prompt.lstrip().startswith("/"):
            raise ValidationFailed(
                ErrorCode.RUNTIME_INVALID_REQUEST, "Gemini CLI prompt starts with a slash command"
            )

    @override
    def _build_launch(
        self, request: AgentRequest, probed: ProbedBinary, *, step_dir: Path, ownership: ProcessOwnership
    ) -> tuple[WrappedCommand, bytes]:
        workdir = resolve_workdir(request)
        step = step_dir.resolve(strict=True)
        if step.is_relative_to(workdir) or workdir.is_relative_to(step):
            raise CapabilityUnavailable(
                ErrorCode.SANDBOX_UNAVAILABLE, "Gemini CLI state and checkout must be separate"
            )
        workspace_config: list[Path] = []
        for root in (workdir, *workdir.parents):
            workspace_config.extend(root / name for name in _WORKSPACE_CONFIG)
            if (root / ".git").exists():
                break
        for path in (*workspace_config, *_SYSTEM_CONFIG):
            if path.exists() or path.is_symlink():
                raise CapabilityUnavailable(
                    ErrorCode.SANDBOX_UNAVAILABLE,
                    "Gemini CLI startup configuration detected",
                    details={"path": str(path)},
                )

        home = ensure_private_dir(step / "gemini-home")
        temp = ensure_private_dir(step / "tmp")
        settings = home / "settings.json"
        settings.write_text(json.dumps(_SETTINGS, sort_keys=True), encoding="utf-8")
        allowed_env = (_API_KEY, *_TLS_ENV)
        extra = {key: value for key, value in request.extra_env.items() if key in allowed_env}
        if secret := request.secret_env.get(_API_KEY):
            extra[_API_KEY] = secret.reveal()
        env = build_env(self._environ, allow=allowed_env, extra=extra, home=home)
        safe_path = os.pathsep.join(
            entry for entry in env.get("PATH", "").split(os.pathsep) if os.path.isabs(entry)
        )
        env["PATH"] = safe_path or os.defpath
        if not env.get(_API_KEY):
            raise CapabilityUnavailable(ErrorCode.RUNTIME_AUTH_EXPIRED, "GEMINI_API_KEY is required")
        env.update(
            GEMINI_CLI_HOME=str(home),
            GEMINI_CLI_SYSTEM_SETTINGS_PATH=str(settings),
            GEMINI_CLI_SYSTEM_DEFAULTS_PATH=str(home / "system-defaults.json"),
            TMPDIR=str(temp),
            XDG_CONFIG_HOME=str(home / ".config"),
            XDG_CACHE_HOME=str(home / ".cache"),
            XDG_DATA_HOME=str(home / ".local/share"),
            XDG_STATE_HOME=str(home / ".local/state"),
        )

        # Route effort is admission metadata for this client and has no native CLI flag.
        argv = (probed.binary_realpath, *_LAUNCH_FLAGS, "--model", request.model)
        wrapped = landlock_argv(
            argv, (home, temp), python_executable=sys.executable, protected=(str(workdir),)
        )
        return (
            LaunchCommand(
                wrapped, env, workdir, ownership, verification_template=self.launch_config_digest
            ).as_wrapped(),
            request.rendered_prompt.encode(),
        )

    @override
    def _make_parser(
        self, request: AgentRequest, probed: ProbedBinary, redact: Callable[[str], str]
    ) -> GeminiCliStreamParser:
        return GeminiCliStreamParser(model=request.model, version=probed.version, redact=redact)
