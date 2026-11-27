"""Claude Code launch plan, isolated client home, credential mount, and Landlock wrapping."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from skm.adapters.runtimes._cli_session.launch import (
    LaunchCommand,
    apply_proxy_env,
    base_child_env,
    ensure_private_dir,
    env_auth_present,
    home_from_env,
    landlock_argv,
    prepare_client_home,
    reject_secrets_in_argv,
    require_client_credentials,
    resolve_workdir,
    write_allow_dirs,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.ids import Digest
from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership, SecretStr
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.process.argv_rules import check_argv

from .permissions import RenderedPermissions, can_skip_permissions, render_permission_flags

if TYPE_CHECKING:
    from skm.adapters.runtimes._cli_session.proxy_bridge import LocalProxyBridge

    from .detect import ProbedBinary

__all__: list[str] = []

WRITABLE_CLIENT_HOME_DIRS: Final[tuple[str, ...]] = ("projects", "todos", "statsig", "debug", "tmp")
CREDENTIAL_FILENAME: Final = ".credentials.json"
SETUP_TOKEN_ENV: Final = "CLAUDE_CODE_OAUTH_TOKEN"
AUTH_ENV_NAMES: Final = ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", SETUP_TOKEN_ENV)
_SECURE_STORAGE_ENV: Final = "CLAUDE_SECURESTORAGE_CONFIG_DIR"
_STRIPPED_ISOLATED_ENV: Final = frozenset(
    {
        "CLAUDE_CONFIG_DIR",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
    }
)


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    """Complete verified Claude CLI launch specification for a single step."""

    command: LaunchCommand
    claude_argv: tuple[str, ...]
    stdin: bytes
    client_home: Path | None
    permissions: RenderedPermissions
    setting_sources: str
    safe_mode: bool


def _provider_override(name: str) -> bool:
    return name.startswith(("ANTHROPIC_", "CLAUDE_CODE_USE_"))


def without_ambient_auth(environ: Mapping[str, str]) -> dict[str, str]:
    """Keep host routing and credential variables out of Claude invocations, including probes."""
    return {
        name: value
        for name, value in environ.items()
        if not _provider_override(name) and name not in {SETUP_TOKEN_ENV, _SECURE_STORAGE_ENV}
    }


def compute_launch_config_digest(
    *,
    adapter_version: str,
    allow_skip_permissions: bool,
    copy_credentials: bool,
    use_setup_token: bool = False,
) -> Digest:
    """Canonical SHA-256 digest of static launch template without per-step entropy."""
    template = {
        "adapter_version": adapter_version,
        "allow_skip_permissions": allow_skip_permissions,
        "base_flags": [
            "-p",
            "--output-format",
            "stream-json",
            "--verbose",
            "--permission-prompts",
            "none",
        ],
        "copy_credentials": copy_credentials,
        "setup_token": use_setup_token,
        "mandatory_env": {
            "CLAUDE_CODE_DISABLE_AUTO_MEMORY": "1",
            "CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1",
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "DISABLE_AUTOUPDATER": "1",
        },
        "setting_sources": {
            "trusted_full_access": "user,project",
            "unattended": "user",
        },
    }
    encoded = json.dumps(template, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def prepare_isolated_client_home(
    request: AgentRequest,
    *,
    workdir: Path,
    user_home: Path | None,
    copy_credentials: bool,
    has_env_auth: bool,
) -> Path:
    """Prepare ``0700`` isolated client home and optionally copy ``0600`` ``.credentials.json``."""
    client_home, target_cred = prepare_client_home(
        request,
        workdir=workdir,
        writable_dirs=WRITABLE_CLIENT_HOME_DIRS,
        credential_filename=CREDENTIAL_FILENAME,
    )

    if copy_credentials and not target_cred.is_file() and user_home is not None:
        source_cred = user_home / ".claude" / CREDENTIAL_FILENAME
        if source_cred.is_file() and not source_cred.is_symlink():
            atomic_write(target_cred, source_cred.read_bytes(), mode=0o600, private=True)

    require_client_credentials(
        target_cred, has_env_auth=has_env_auth, runtime_id="claude_code", display_name="Claude Code"
    )

    return client_home


def build_child_environment(
    request: AgentRequest,
    *,
    host_environ: Mapping[str, str],
    client_home: Path | None,
    proxy_bridge: LocalProxyBridge | None = None,
    setup_token: SecretStr | None = None,
) -> Mapping[str, str]:
    """Construct minimal allowlisted child environment with mandatory Claude isolation overrides."""
    env = base_child_env(
        request,
        host_environ=without_ambient_auth(host_environ),
        home=client_home,
        stripped=_STRIPPED_ISOLATED_ENV if client_home is not None else (),
    )

    # Mandatory isolation invariants (Dossier §3.3): cannot be overridden by extra_env.
    env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] = "1"
    env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"
    env["CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC"] = "1"
    env["DISABLE_AUTOUPDATER"] = "1"
    if client_home is not None:
        env.pop(_SECURE_STORAGE_ENV, None)
        env["HOME"] = str(client_home)
        env["CLAUDE_CONFIG_DIR"] = str(client_home)
        env["TMPDIR"] = str(client_home / "tmp")
    if setup_token is not None:
        env = {name: value for name, value in env.items() if not _provider_override(name)}
        env[SETUP_TOKEN_ENV] = setup_token.reveal()

    apply_proxy_env(env, proxy_bridge)
    return MappingProxyType(env)


def build_launch_plan(  # noqa: PLR0913 - explicit launch boundary without ambient reads
    request: AgentRequest,
    *,
    binary_path: str,
    step_dir: Path,
    ownership: ProcessOwnership,
    host_environ: Mapping[str, str],
    proxy_bridge: LocalProxyBridge | None = None,
    probed: ProbedBinary | None = None,
    policy_profile: str | None = None,
    allow_skip_permissions: bool = False,
    copy_credentials: bool = True,
    user_home: Path | None = None,
    setup_token: SecretStr | None = None,
    extra_dirs: Sequence[str] = (),
    python_executable: str = sys.executable,
    wrap_landlock: bool = True,
) -> LaunchPlan:
    """Assemble argv, isolated client home, step settings/MCP files, and stdin payload."""
    resolved_workdir = resolve_workdir(request)
    resolved_step_dir = ensure_private_dir(step_dir)
    if resolved_step_dir.is_relative_to(resolved_workdir):
        raise ValidationFailed(
            ErrorCode.RUNTIME_INVALID_REQUEST,
            "step_dir must be outside workdir",
            details={"reason": "step_dir_inside_worktree"},
        )

    effective_policy_profile = policy_profile or request.labels.get("policy_profile")
    trusted_full_access = effective_policy_profile == "trusted-full-access"
    setting_sources = "user,project" if trusted_full_access else "user"

    safe_mode = True if probed is None else probed.safe_mode_supported
    permission_mode_supported = True if probed is None else probed.permission_mode_supported
    strict_mcp_supported = True if probed is None else probed.strict_mcp_supported

    effective_user_home = home_from_env(user_home, host_environ)

    has_env_auth = setup_token is not None or env_auth_present(request, {}, AUTH_ENV_NAMES)

    client_home: Path | None = None
    if request.config_mode == "isolated":
        if sys.platform == "darwin" and not has_env_auth:
            # Claude Code #92252: CLAUDE_CONFIG_DIR selects a different Keychain namespace.
            # An isolated launch must never fall back to the user's default Keychain account.
            raise CapabilityUnavailable(
                ErrorCode.RUNTIME_AUTH_EXPIRED,
                "isolated Claude Code on macOS requires a setup token or explicit API credentials",
                details={"runtime_id": "claude_code", "reason": "macos_keychain_namespace"},
            )
        client_home = prepare_isolated_client_home(
            request,
            workdir=resolved_workdir,
            user_home=effective_user_home,
            copy_credentials=copy_credentials and setup_token is None,
            has_env_auth=has_env_auth,
        )

    env = build_child_environment(
        request,
        host_environ=host_environ,
        client_home=client_home,
        proxy_bridge=proxy_bridge,
        setup_token=setup_token,
    )

    rendered_perms = render_permission_flags(
        request,
        step_dir=resolved_step_dir,
        proxy_bridge=proxy_bridge,
        permission_mode_supported=permission_mode_supported,
        strict_mcp_supported=strict_mcp_supported,
        policy_profile=effective_policy_profile,
        allow_skip_permissions=allow_skip_permissions,
        extra_dirs=extra_dirs,
    )

    argv_list: list[str] = [
        binary_path,
        "-p",
        "--output-format",
        "stream-json",
        "--verbose",
        "--model",
        request.model,
    ]
    if request.effort is not None:
        argv_list.extend(("--effort", request.effort.value))
    argv_list.extend(("--permission-prompts", "none"))
    if safe_mode and not trusted_full_access:
        argv_list.append("--safe-mode")
    if request.session_policy == "ephemeral":
        argv_list.append("--no-session-persistence")
    argv_list.extend(("--setting-sources", setting_sources))
    argv_list.extend(("--settings", str(rendered_perms.settings_path)))
    argv_list.extend(rendered_perms.argv)
    if request.resume_session_ref is not None:
        argv_list.extend(("--resume", request.resume_session_ref))

    claude_argv = check_argv(argv_list)
    if "--bare" in claude_argv:
        raise ValueError("--bare is forbidden for Claude Code (breaks OAuth)")
    if "--dangerously-skip-permissions" in claude_argv and not can_skip_permissions(
        request,
        policy_profile=effective_policy_profile,
        allow_skip_permissions=allow_skip_permissions,
    ):
        raise ValueError("--dangerously-skip-permissions is forbidden outside opted-in trusted-full-access")

    reject_secrets_in_argv(request, claude_argv, "Claude Code")

    final_argv = claude_argv
    if wrap_landlock and request.isolation_profile is IsolationProfile.LANDLOCK:
        rw_dirs = write_allow_dirs(request, resolved_workdir)
        if client_home is not None:
            rw_dirs.append(client_home)
        final_argv = landlock_argv(claude_argv, rw_dirs, python_executable=python_executable)

    command = LaunchCommand(
        argv=final_argv,
        env=env,
        cwd=resolved_workdir,
        ownership=ownership,
    )
    return LaunchPlan(
        command=command,
        claude_argv=claude_argv,
        stdin=request.rendered_prompt.encode("utf-8"),
        client_home=client_home,
        permissions=rendered_perms,
        setting_sources=setting_sources,
        safe_mode=safe_mode and not trusted_full_access,
    )
