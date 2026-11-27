"""Grok CLI ``AgentRuntime`` adapter with mandatory sandbox containment."""

from __future__ import annotations

import json
import os
import posixpath
import stat
from collections.abc import Callable, Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast, override

from skm.adapters.runtimes._cli_session.probe import (
    ProbeCommandRunner,
    default_os_kernel,
    default_probe_runner,
)
from skm.adapters.runtimes._cli_session.runtime import (
    CliAgentRuntime,
    OwnershipKind,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.modules.runtimes.domain.capability import SelfLoadedSource, SelfLoadKind
from skm.modules.runtimes.domain.ids import RuntimeId
from skm.platform.config.sources.document import decode_toml
from skm.platform.system_clock import SystemClock

from .detect import GrokDetector, ProbedBinary, apply_probe_to_capabilities
from .launch import build_launch_plan, compute_launch_config_digest, enforce_containment_invariants
from .stream_parser import GrokStreamParser

if TYPE_CHECKING:
    from skm.adapters.runtimes._cli_session.cancel import Sleeper
    from skm.adapters.runtimes._cli_session.observation import LiveQueue
    from skm.adapters.runtimes._cli_session.proxy_bridge import LocalProxyBridge
    from skm.adapters.runtimes._cli_session.session import ProcessRunner, StreamParser
    from skm.kernel.clock import Clock, Monotonic
    from skm.modules.execution.ports import WrappedCommand
    from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership
    from skm.platform.fs.storage_budget import StorageBudget

__all__ = ["GrokRuntime", "grok_account_available"]

_PACKAGE_DIR: Final = Path(__file__).resolve().parent
_MAX_ACCOUNT_FILE_BYTES: Final = 128 * 1024
_DEFAULT_ISSUER: Final = "https://auth.x.ai"
_DEFAULT_CLIENT: Final = "b1a00492-073a-47ea-816f-4c329264a828"
_LEGACY_SCOPE: Final = "https://accounts.x.ai/sign-in"
_API_KEY_SCOPE: Final = "xai::api_key"


def _active_native_credential(scope: str, raw: object, now: datetime) -> bool:
    if not isinstance(raw, dict):
        return False
    credential = cast("dict[str, object]", raw)
    key, mode = credential.get("key"), credential.get("auth_mode")
    if (
        not isinstance(key, str)
        or not key.strip()
        or not isinstance(mode, str)
        or mode not in {"oidc", "external", "api_key"}
        or not isinstance(credential.get("user_id"), str)
    ):
        return False
    api_key = scope == _API_KEY_SCOPE
    if api_key != (mode == "api_key"):
        return False
    created, expiry = credential.get("create_time"), credential.get("expires_at")
    if not isinstance(created, str) or (expiry is not None and not isinstance(expiry, str)):
        return False
    try:
        issued_at = datetime.fromisoformat(created)
        expires_at = datetime.fromisoformat(expiry) if expiry is not None else None
        if expires_at is None and not api_key:
            expires_at = issued_at + timedelta(days=30)
    except (ValueError, OverflowError):
        return False
    return (
        issued_at.utcoffset() is not None
        and issued_at <= now
        and (expires_at is None or (expires_at.utcoffset() is not None and now < expires_at))
    )


def _account_file(path: Path, *, forbidden_mode: int) -> bytes:
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as stream:
        facts = os.fstat(stream.fileno())
        if (
            not stat.S_ISREG(facts.st_mode)
            or facts.st_uid != os.geteuid()
            or facts.st_mode & forbidden_mode
            or facts.st_size > _MAX_ACCOUNT_FILE_BYTES
        ):
            raise ValueError("Invalid Grok account file")
        encoded = stream.read(_MAX_ACCOUNT_FILE_BYTES + 1)
    if len(encoded) > _MAX_ACCOUNT_FILE_BYTES:
        raise ValueError("Grok account file is too large")
    return encoded


def _auth_config(path: Path) -> dict[str, object]:
    try:
        config = decode_toml(_account_file(path, forbidden_mode=0o022).decode("utf-8"))
    except FileNotFoundError:
        return {}
    alias, explicit = config.get("auth", {}), config.get("grok_com_config", {})
    if not isinstance(alias, dict) or not isinstance(explicit, dict):
        raise ValueError("Invalid Grok authentication configuration")
    return {**cast("dict[str, object]", alias), **cast("dict[str, object]", explicit)}


def _native_auth_scope(config: dict[str, object]) -> str:
    # Grok gives OIDC precedence; its default OAuth2 provider supplies omitted fields.
    oidc = config.get("oidc")
    provider = oidc if oidc is not None else config.get("oauth2", {})
    if not isinstance(provider, dict):
        raise ValueError("Invalid Grok authentication provider")
    fields = cast("dict[str, object]", provider)
    issuer = fields.get("issuer", None if oidc is not None else _DEFAULT_ISSUER)
    client = fields.get("client_id", None if oidc is not None else _DEFAULT_CLIENT)
    if (
        not isinstance(issuer, str)
        or not issuer.startswith("https://")
        or not isinstance(client, str)
        or not client
    ):
        raise ValueError("Grok authentication requires an HTTPS issuer and client")
    return f"{issuer.rstrip('/')}::{client}"


def _native_auth_exists(state: Path, now: datetime) -> bool:
    config = _auth_config(state / "config.toml")
    auth: object = json.loads(_account_file(state / "auth.json", forbidden_mode=0o077))
    if not isinstance(auth, dict):
        return False
    credentials = cast("dict[str, object]", auth)
    scope = _native_auth_scope(config)
    if scope not in credentials:
        scope = _LEGACY_SCOPE
    requirements = _auth_config(state / "requirements.toml")
    allow_keys = (
        config.get("disable_api_key_auth") is not True
        and "force_login_team_uuid" not in config
        and "force_login_team_uuid" not in requirements
    )
    return _active_native_credential(scope, credentials.get(scope), now) or (
        allow_keys and _active_native_credential(_API_KEY_SCOPE, credentials.get(_API_KEY_SCOPE), now)
    )


def grok_account_available(home: Path | None) -> bool:
    """Check the selected private native auth.json without exposing or refreshing credentials."""
    if home is None:
        return False
    grok_state = home / ".grok"
    try:
        if home.resolve(strict=True) != home:
            return False
        for directory in (home, grok_state):
            metadata = directory.lstat()
            if (
                not stat.S_ISDIR(metadata.st_mode)
                or metadata.st_uid != os.geteuid()
                or metadata.st_mode & 0o077
            ):
                return False
        return _native_auth_exists(grok_state, SystemClock().now())
    except (OSError, RuntimeError, ValueError, RecursionError):
        return False


class GrokRuntime(CliAgentRuntime[ProbedBinary]):
    """Production ``AgentRuntime`` adapter for headless ``grok --output-format streaming-messages-json``."""

    runtime_id: RuntimeId = "grok"
    display_name = "Grok"
    default_binary = "grok"
    short_name = "grok"
    scratch_directories = ("tmp",)

    def __init__(  # noqa: PLR0913 - explicit host injection boundary without ambient reads
        self,
        *,
        state_dir: Path | None = None,
        binary: str | None = None,
        environ: Mapping[str, str] | None = None,
        user_home: Path | None = None,
        account_home: Path | None = None,
        wrap_landlock: bool = True,
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
        self._account_home = account_home
        if account_home is not None:
            user_home = account_home
            environ = {**(environ or {}), "HOME": str(account_home)}
        self._wrap_landlock = wrap_landlock
        self._subagent_disclosed = subagent_disclosed
        self._detector = GrokDetector(run_cmd=probe_runner, os_kernel_fn=os_kernel_fn)
        super().__init__(
            package_dir=_PACKAGE_DIR,
            detector=self._detector,
            apply_probe=apply_probe_to_capabilities,
            state_dir=state_dir,
            binary=binary,
            environ=environ,
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
        return compute_launch_config_digest(adapter_version=self._static_caps.adapter_version)

    @override
    def self_loaded_context(self, request: AgentRequest) -> tuple[SelfLoadedSource, ...]:
        """Report all unsuppressible Grok user and worktree discovery paths (adapters §5.11)."""
        norm_workdir = posixpath.normpath(request.workdir)
        return (
            SelfLoadedSource(
                kind=SelfLoadKind.PROJECT_SETTINGS,
                locator=f"{norm_workdir}/.grok",
                files=(".grok/**",),
                when="start",
                trust="untrusted",
            ),
            SelfLoadedSource(
                kind=SelfLoadKind.PROJECT_INSTRUCTIONS,
                locator=norm_workdir,
                files=("AGENTS.md", ".claude/rules/**"),
                when="start",
                trust="untrusted",
            ),
            SelfLoadedSource(
                kind=SelfLoadKind.SKILLS,
                locator=norm_workdir,
                files=(".grok/skills/**", ".claude/skills/**"),
                when="on_access",
                trust="untrusted",
            ),
            SelfLoadedSource(
                kind=SelfLoadKind.SKILLS,
                locator="~/.grok/skills",
                files=("~/.grok/skills/**", "~/.agents/skills/**"),
                when="on_access",
                trust="untrusted",
            ),
            SelfLoadedSource(
                kind=SelfLoadKind.PLUGINS,
                locator="~/.grok/plugins",
                files=(),
                when="start",
                trust="untrusted",
            ),
            SelfLoadedSource(
                kind=SelfLoadKind.USER_CONFIG,
                locator="~/.grok",
                files=("config.toml",),
                when="start",
                trust="untrusted",
            ),
        )

    @override
    def _validate_start(self, request: AgentRequest) -> None:
        if self._account_home is not None and not grok_account_available(self._account_home):
            raise CapabilityUnavailable(ErrorCode.RUNTIME_AUTH_EXPIRED, "Local Grok account is unavailable")
        enforce_containment_invariants(request, wrap_landlock=self._wrap_landlock)

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
            host_environ=self._environ,
            user_home=self._user_home,
            wrap_landlock=self._wrap_landlock,
            proxy_bridge=proxy_bridge,
        )
        return plan.command.as_wrapped(), plan.stdin

    @override
    def _make_parser(
        self,
        request: AgentRequest,
        probed: ProbedBinary,
        redact: Callable[[str], str],
    ) -> StreamParser:
        return GrokStreamParser(
            runtime_version=probed.version,
            redact=redact,
            subagent_disclosed=self._subagent_disclosed,
        )
