"""Codex CLI launch plan, isolated CODEX_HOME, credential mount, and Landlock wrapping."""

from __future__ import annotations

import os
import stat
import sys
from collections.abc import Mapping
from contextlib import ExitStack
from dataclasses import dataclass, replace
from pathlib import Path
from tempfile import mkdtemp
from types import MappingProxyType
from typing import TYPE_CHECKING, Final

from skm.adapters.runtimes._cli_session.binding import canonical_launch_digest
from skm.adapters.runtimes._cli_session.launch import (
    LaunchCommand,
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
from skm.modules.runtimes.domain.request import AgentRequest, ProcessOwnership
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.process.argv_rules import check_argv

from .permissions import (
    RenderedPermissions,
    SandboxMode,
    can_bypass_approvals_and_sandbox,
    render_codex_config_toml,
    render_permission_flags,
)

if TYPE_CHECKING:
    from skm.modules.runtimes.domain.request import McpServerSpec

    from .detect import ProbedBinary

__all__: list[str] = []

WRITABLE_CLIENT_HOME_DIRS: Final[tuple[str, ...]] = ("sessions", "cache", "tmp")
CREDENTIAL_FILENAME: Final = "auth.json"
_AUTH_ENV_NAMES: Final = ("OPENAI_API_KEY", "CODEX_API_KEY")
_VERIFICATION_SOCKET: Final = "{stage_tool_socket}"
_STRIPPED_ISOLATED_ENV: Final = frozenset(
    {
        "CODEX_HOME",
        "CODEX_HOME_USER",
        "XDG_CONFIG_HOME",
        "XDG_CACHE_HOME",
        "XDG_DATA_HOME",
        "XDG_STATE_HOME",
    }
)


@dataclass(frozen=True, slots=True)
class LaunchPlan:
    """Complete verified Codex CLI launch specification for a single step."""

    command: LaunchCommand
    codex_argv: tuple[str, ...]
    stdin: bytes
    client_home: Path | None
    permissions: RenderedPermissions
    sandbox_mode: SandboxMode


def compute_launch_config_digest(
    *,
    adapter_version: str,
    allow_full_access: bool,
    copy_credentials: bool,
    request_bypass: bool = False,
) -> Digest:
    """Key inventory probes by adapter settings. Launch evidence uses the rendered plan."""
    template = {
        "adapter_version": adapter_version,
        "allow_full_access": allow_full_access,
        "base_flags": [
            "-a",
            "never",
            "exec",
            "--json",
            "-",
        ],
        "copy_credentials": copy_credentials,
        "isolated_env": {
            "CODEX_HOME": "{client_home}",
            "HOME": "{client_home}",
        },
        "cli_auth_credentials_store": "file",
        "request_bypass": request_bypass,
        "writable_home_dirs": list(WRITABLE_CLIENT_HOME_DIRS),
    }
    return canonical_launch_digest(template)


def _verified_stage_tool_config(request: AgentRequest, config: str) -> str:
    socket_path = request.stage_tool_socket
    if socket_path is None:
        return config

    # Only worker-bound broker metadata can substitute a dynamic value in the attested template.
    if config != render_codex_config_toml(request):
        raise ValueError("Codex launch configuration changed after rendering")
    servers: list[McpServerSpec] = []
    for server in request.mcp_servers:
        if server.name != "skm":
            servers.append(server)
            continue
        if server.env != {"SKM_STAGE_SOCKET": socket_path} or server.secret_env_names:
            raise ValueError("The configured SKM MCP server differs from the worker broker")
        servers.append(replace(server, env={"SKM_STAGE_SOCKET": _VERIFICATION_SOCKET}))
    return render_codex_config_toml(replace(request, mcp_servers=tuple(servers)))


def _launch_template_digest(
    request: AgentRequest,
    plan: LaunchPlan,
    *,
    copy_credentials: bool,
    state_home: Path,
) -> Digest:
    command = plan.command
    argv = list(plan.codex_argv[1:])
    if request.resume_session_ref is not None:
        argv[4] = "{session_ref}"
    # The selected model and effort are workload inputs. Preserve the rendered option syntax.
    argv[argv.index("--model") + 1] = "{model}"
    if request.effort is not None:
        effort_index = argv.index(f'model_reasoning_effort="{request.effort.value}"')
        argv[effort_index] = 'model_reasoning_effort="{effort}"'

    # The wrapper grants the attempt's state home while CODEX_HOME may use a private launch home.
    roots = {str(command.cwd): {"root": "workdir"}, str(state_home): {"root": "client_home"}}
    if plan.client_home is not None:
        roots[str(plan.client_home)] = {"root": "client_home"}
        roots[str(plan.client_home / "tmp")] = {"root": "client_home", "relative": "tmp"}
    wrapper = [roots.get(arg, arg) for arg in command.argv[: len(command.argv) - len(plan.codex_argv)]]
    secret_names = set(request.secret_env) | set(_AUTH_ENV_NAMES)
    env = {
        name: (
            {"secret": name}
            if name in secret_names
            else roots.get(value, value)
            if name in {"HOME", "CODEX_HOME", "TMPDIR"}
            else value
        )
        for name, value in command.env.items()
    }
    if request.stage_tool_socket is not None:
        if command.env.get("SKM_STAGE_SOCKET") != request.stage_tool_socket:
            raise ValueError("The worker broker socket differs from the Codex launch environment")
        env["SKM_STAGE_SOCKET"] = _VERIFICATION_SOCKET
    config = plan.permissions.config_path.read_text(encoding="utf-8")
    template: dict[str, object] = {
        "argv": argv,
        "wrapper": wrapper,
        "isolation_profile": str(request.isolation_profile),
        "ownership": command.ownership.kind,
        "sandbox_mode": plan.sandbox_mode,
        "config_mode": request.config_mode,
        "config": _verified_stage_tool_config(request, config),
        "session_policy": request.session_policy,
        "network": (request.permissions.network.mode, request.permissions.network.hosts),
        "env": env,
        "credential_copy": copy_credentials,
        "client_home_writable_dirs": WRITABLE_CLIENT_HOME_DIRS if plan.client_home else (),
    }
    if request.stage_tool_socket is not None:
        template["worker_stage_tool"] = True
    return canonical_launch_digest(template)


def _resolve_credential_source(
    *,
    user_home: Path | None,
    codex_home_user: Path | None,
) -> Path | None:
    if codex_home_user is not None:
        return codex_home_user / CREDENTIAL_FILENAME
    if user_home is not None:
        return user_home / ".codex" / CREDENTIAL_FILENAME
    return None


def prepare_isolated_client_home(
    request: AgentRequest,
    *,
    workdir: Path,
    user_home: Path | None,
    codex_home_user: Path | None = None,
    copy_credentials: bool,
    has_env_auth: bool,
) -> Path:
    """Prepare ``0700`` isolated ``CODEX_HOME`` and optionally copy ``0600`` ``auth.json``."""
    client_home, target_cred = prepare_client_home(
        request,
        workdir=workdir,
        writable_dirs=WRITABLE_CLIENT_HOME_DIRS,
        credential_filename=CREDENTIAL_FILENAME,
    )

    source_cred = _resolve_credential_source(
        user_home=user_home,
        codex_home_user=codex_home_user,
    )
    if source_cred is not None and source_cred.is_symlink():
        raise ValidationFailed(
            ErrorCode.RUNTIME_INVALID_REQUEST,
            "source auth.json must not be a symlink",
            details={"reason": "source_credentials_symlink"},
        )

    if copy_credentials and not target_cred.is_file() and source_cred is not None and source_cred.is_file():
        atomic_write(target_cred, source_cred.read_bytes(), mode=0o600, private=True)

    require_client_credentials(
        target_cred, has_env_auth=has_env_auth, runtime_id="codex", display_name="Codex"
    )

    return client_home


def build_child_environment(
    request: AgentRequest,
    *,
    host_environ: Mapping[str, str],
    client_home: Path | None,
) -> Mapping[str, str]:
    """Construct minimal allowlisted child environment with mandatory Codex isolation overrides."""
    env = base_child_env(
        request,
        host_environ=host_environ,
        home=client_home,
        stripped=_STRIPPED_ISOLATED_ENV if client_home is not None else (),
    )
    if client_home is not None:
        env.pop("CODEX_HOME_USER", None)
        env["HOME"] = str(client_home)
        env["CODEX_HOME"] = str(client_home)
        env["TMPDIR"] = str(client_home / "tmp")

    return MappingProxyType(env)


def _read_native_wallet(source: Path | None) -> bytes:
    limit = 1024 * 1024
    try:
        if source is None:
            raise ValueError("selected account is missing")
        with ExitStack() as stack:
            parent = os.open(source.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            stack.callback(os.close, parent)
            directory = os.fstat(parent)
            if directory.st_uid != os.geteuid() or directory.st_mode & 0o022:
                raise ValueError("wallet directory is not owner-controlled")
            flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC
            with os.fdopen(os.open(source.name, flags, dir_fd=parent), "rb") as wallet:
                facts = os.fstat(wallet.fileno())
                if (
                    not stat.S_ISREG(facts.st_mode)
                    or facts.st_uid != os.geteuid()
                    or facts.st_mode & 0o077
                    or not 0 < facts.st_size <= limit
                ):
                    raise ValueError("wallet is not a bounded owner-only file")
                contents = wallet.read(limit + 1)
        if not 0 < len(contents) <= limit:
            raise ValueError("wallet is not a bounded owner-only file")
    except (OSError, ValueError):
        raise CapabilityUnavailable(
            ErrorCode.RUNTIME_AUTH_EXPIRED, "Selected Codex wallet is unavailable"
        ) from None
    return contents


def _prepare_launch_home(step_dir: Path, state_home: Path, wallet: bytes | None) -> Path:
    """Give this launch its own config and wallet while keeping attempt-scoped session state."""
    home = Path(mkdtemp(prefix="codex-home-", dir=step_dir))
    for name in WRITABLE_CLIENT_HOME_DIRS:
        (home / name).symlink_to(state_home / name, target_is_directory=True)
    if wallet is not None:
        atomic_write(home / CREDENTIAL_FILENAME, wallet, mode=0o600, private=True)
    return home


def _render_codex_argv(
    request: AgentRequest,
    *,
    binary_path: str,
    rendered_perms: RenderedPermissions,
) -> tuple[str, ...]:
    if request.resume_session_ref is not None:
        argv_list: list[str] = [
            binary_path,
            "-a",
            "never",
            "exec",
            "resume",
            request.resume_session_ref,
            "--json",
            *rendered_perms.argv,
            "--model",
            request.model,
        ]
    else:
        argv_list = [
            binary_path,
            "-a",
            "never",
            "exec",
            "--json",
            *rendered_perms.argv,
            "--model",
            request.model,
        ]

    if request.effort is not None:
        argv_list.extend(("-c", f'model_reasoning_effort="{request.effort.value}"'))
    # Shared by fresh and resume, after --model, so resume argv[4] stays the session ref.
    argv_list.extend(("-c", "features.multi_agent=false", "-c", "features.multi_agent_v2=false"))
    if request.session_policy == "ephemeral":
        argv_list.append("--ephemeral")
    if rendered_perms.bypass_approvals_and_sandbox:
        argv_list.append("--dangerously-bypass-approvals-and-sandbox")
    argv_list.append("-")
    return check_argv(argv_list)


def build_launch_plan(  # noqa: PLR0913 - explicit launch boundary without ambient reads
    request: AgentRequest,
    *,
    binary_path: str,
    step_dir: Path,
    ownership: ProcessOwnership,
    host_environ: Mapping[str, str],
    probed: ProbedBinary | None = None,
    policy_profile: str | None = None,
    allow_full_access: bool = False,
    copy_credentials: bool = True,
    user_home: Path | None = None,
    codex_home_user: Path | None = None,
    request_bypass: bool = False,
    python_executable: str = sys.executable,
    wrap_landlock: bool = True,
) -> LaunchPlan:
    """Assemble Codex argv, isolated CODEX_HOME, step/home config.toml, and stdin payload."""
    resolved_workdir = resolve_workdir(request)
    resolved_step_dir = ensure_private_dir(step_dir)
    if resolved_step_dir.is_relative_to(resolved_workdir):
        raise ValidationFailed(
            ErrorCode.RUNTIME_INVALID_REQUEST,
            "step_dir must be outside workdir",
            details={"reason": "step_dir_inside_worktree"},
        )

    effective_policy_profile = policy_profile or request.labels.get("policy_profile")
    bypass_supported = True if probed is None else probed.bypass_supported
    landlock_containment_ok = request.isolation_profile is not IsolationProfile.LANDLOCK or wrap_landlock
    if request_bypass and (
        not landlock_containment_ok
        or not can_bypass_approvals_and_sandbox(
            request,
            policy_profile=effective_policy_profile,
            allow_full_access=allow_full_access,
            bypass_supported=bypass_supported,
            request_bypass=request_bypass,
        )
    ):
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            (
                "Codex --dangerously-bypass-approvals-and-sandbox requires active "
                "Landlock/container containment and trusted-full-access opt-in"
            ),
            details={
                "runtime_id": "codex",
                "reason": "bypass_containment_required",
                "isolation_profile": str(request.isolation_profile),
            },
        )

    effective_user_home = home_from_env(user_home, host_environ, "HOME")
    effective_codex_home_user = home_from_env(codex_home_user, host_environ, "CODEX_HOME_USER")

    state_home: Path | None = None
    client_home: Path | None = None
    has_env_auth = env_auth_present(request, host_environ, _AUTH_ENV_NAMES)
    if request.verification_context is not None and not has_env_auth and request.config_mode != "isolated":
        raise CapabilityUnavailable(
            ErrorCode.RUNTIME_AUTH_EXPIRED, "Verified Codex native login requires a private launch wallet"
        )
    if request.config_mode == "isolated":
        if request.verification_context is None:
            state_home = client_home = prepare_isolated_client_home(
                request,
                workdir=resolved_workdir,
                user_home=effective_user_home,
                codex_home_user=effective_codex_home_user,
                copy_credentials=copy_credentials,
                has_env_auth=has_env_auth,
            )
        else:
            state_home, _ = prepare_client_home(
                request,
                workdir=resolved_workdir,
                writable_dirs=WRITABLE_CLIENT_HOME_DIRS,
                credential_filename=CREDENTIAL_FILENAME,
            )
            source = _resolve_credential_source(
                user_home=effective_user_home, codex_home_user=effective_codex_home_user
            )
            wallet = None if has_env_auth else _read_native_wallet(source if copy_credentials else None)
            client_home = _prepare_launch_home(resolved_step_dir, state_home, wallet)
    config_target_dir = client_home if client_home is not None else resolved_step_dir
    rendered_perms = render_permission_flags(
        request,
        config_dir=config_target_dir,
        policy_profile=effective_policy_profile,
        allow_full_access=allow_full_access,
        bypass_supported=bypass_supported,
        request_bypass=request_bypass,
    )
    env = build_child_environment(
        request,
        host_environ=host_environ,
        client_home=client_home,
    )
    codex_argv = _render_codex_argv(
        request,
        binary_path=binary_path,
        rendered_perms=rendered_perms,
    )
    if "--dangerously-bypass-approvals-and-sandbox" in codex_argv and (
        not landlock_containment_ok
        or not can_bypass_approvals_and_sandbox(
            request,
            policy_profile=effective_policy_profile,
            allow_full_access=allow_full_access,
            bypass_supported=bypass_supported,
            request_bypass=request_bypass,
        )
    ):
        msg = (
            "--dangerously-bypass-approvals-and-sandbox is forbidden "
            "without external sandbox and policy opt-in"
        )
        raise ValueError(msg)

    reject_secrets_in_argv(request, codex_argv, "Codex")

    final_argv = codex_argv
    if wrap_landlock and request.isolation_profile is IsolationProfile.LANDLOCK:
        rw_dirs = write_allow_dirs(request, resolved_workdir)
        if state_home is not None:
            rw_dirs.append(state_home)
        final_argv = landlock_argv(codex_argv, rw_dirs, python_executable=python_executable)

    command = LaunchCommand(
        argv=final_argv,
        env=env,
        cwd=resolved_workdir,
        ownership=ownership,
    )
    plan = LaunchPlan(
        command=command,
        codex_argv=codex_argv,
        stdin=request.rendered_prompt.encode("utf-8"),
        client_home=client_home,
        permissions=rendered_perms,
        sandbox_mode=rendered_perms.sandbox_mode,
    )
    if state_home is not None:
        command = replace(
            command,
            verification_template=_launch_template_digest(
                request, plan, copy_credentials=copy_credentials, state_home=state_home
            ),
        )
        plan = replace(plan, command=command)
    return plan
