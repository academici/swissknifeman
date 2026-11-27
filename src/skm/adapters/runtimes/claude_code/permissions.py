"""Claude Code permission flag rendering, step settings.json, MCP config, and denial hints."""

from __future__ import annotations

import json
import posixpath
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from skm.adapters.runtimes._cli_session.launch import apply_proxy_env
from skm.kernel.isolation import IsolationProfile
from skm.modules.runtimes.domain.classes import RoleId
from skm.modules.runtimes.domain.request import AgentRequest
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.process.argv_rules import check_argv

if TYPE_CHECKING:
    from skm.adapters.runtimes._cli_session.proxy_bridge import LocalProxyBridge

__all__: list[str] = []

_READ_TOOLS: Final = ("Read", "Grep", "Glob")
_WRITE_TOOLS: Final = ("Edit", "Write")
_DISALLOWED_ON_READONLY: Final = ("Edit", "Write", "NotebookEdit")
_SAFE_PROG_RE: Final = re.compile(r"^[A-Za-z0-9._+-]{1,64}$")
_SAFE_MCP_NAME_RE: Final = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


@dataclass(frozen=True, slots=True)
class RenderedPermissions:
    """Rendered CLI flags and private step-dir configuration paths for one step."""

    argv: tuple[str, ...]
    settings_path: Path
    mcp_path: Path | None


def can_skip_permissions(
    request: AgentRequest,
    *,
    policy_profile: str | None,
    allow_skip_permissions: bool,
) -> bool:
    """``--dangerously-skip-permissions`` requires ``trusted-full-access``, host opt-in, and isolation."""
    return (
        policy_profile == "trusted-full-access"
        and allow_skip_permissions
        and request.isolation_profile is not IsolationProfile.NONE
    )


def _shell_allowed(request: AgentRequest) -> bool:
    if request.role is RoleId.SCOUT:
        return False
    mode = request.permissions.commands.mode
    if mode == "none":
        return False
    return not (mode == "allowlist" and not request.permissions.commands.programs)


def _shell_allow_rules(request: AgentRequest) -> tuple[str, ...]:
    if not _shell_allowed(request):
        return ()
    commands = request.permissions.commands
    if commands.mode == "allowlist":
        rules: list[str] = []
        for program in commands.programs:
            cleaned = program.strip()
            if not cleaned or any(ch in cleaned for ch in ("\0", ",", "\n", "\r", ")")):
                raise ValueError(f"unsafe command allowlist prefix: {program!r}")
            rules.append(f"Bash({cleaned} *)")
        return tuple(rules)
    return ("Bash",)


def _extra_directories(request: AgentRequest, extra_dirs: Sequence[str]) -> tuple[str, ...]:
    workdir_norm = posixpath.normpath(request.workdir)
    seen: set[str] = {workdir_norm}
    added: list[str] = []
    candidates = (
        *request.permissions.fs_read.roots(),
        *request.permissions.fs_write.roots(),
        *extra_dirs,
    )
    for raw in candidates:
        if not raw:
            continue
        norm = posixpath.normpath(raw)
        if norm not in seen:
            seen.add(norm)
            added.append(norm)
    return tuple(added)


def _build_settings_document(
    request: AgentRequest,
    *,
    writable: bool,
    shell_rules: tuple[str, ...],
    trusted_full_access: bool,
) -> dict[str, object]:
    allow: list[str] = list(_READ_TOOLS)
    deny: list[str] = []
    if writable:
        allow.extend(_WRITE_TOOLS)
    else:
        deny.extend(_DISALLOWED_ON_READONLY)

    if shell_rules:
        allow.extend(shell_rules)
    else:
        deny.append("Bash")

    if "Task" in request.permissions.tools:
        allow.append("Task")

    deny.extend(f"Bash({pattern})" for pattern in request.permissions.commands.deny_patterns if pattern)

    ask = [f"Bash({pattern})" for pattern in request.permissions.commands.ask_patterns if pattern]
    network = request.permissions.network
    allowed_domains = list(network.hosts) if network.mode == "allowlist" else []

    return {
        "disableAllHooks": not trusted_full_access,
        "enableAllProjectMcpServers": False,
        "permissions": {
            "allow": allow,
            "ask": ask,
            "defaultMode": "acceptEdits" if writable else "default",
            "deny": deny,
        },
        "sandbox": {
            "allowUnsandboxedCommands": False,
            "autoAllowBashIfSandboxed": False,
            "enabled": True,
            "network": {
                "allowLocalBinding": False,
                "allowedDomains": allowed_domains,
            },
        },
    }


def _write_mcp_config(request: AgentRequest, step_dir: Path, proxy_bridge: LocalProxyBridge | None) -> Path:
    servers: dict[str, object] = {}
    secret_values = tuple(secret.reveal() for secret in request.secret_env.values())
    for server in request.mcp_servers:
        if not _SAFE_MCP_NAME_RE.fullmatch(server.name):
            raise ValueError(f"invalid MCP server name: {server.name!r}")
        argv = check_argv(server.command)
        env_map: dict[str, str] = dict(server.env)
        for secret_name in server.secret_env_names:
            # Never materialize secret plaintext in mcp.json; expand from child env at runtime.
            env_map[secret_name] = f"${{{secret_name}}}"
        apply_proxy_env(env_map, proxy_bridge)
        servers[server.name] = {
            "args": list(argv[1:]),
            "command": argv[0],
            "env": env_map,
            "type": "stdio",
        }
    payload = json.dumps(
        {"mcpServers": servers},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    if any(secret and secret in payload for secret in secret_values):
        raise ValueError("secret plaintext must never enter mcp.json")
    mcp_path = step_dir / "mcp.json"
    atomic_write(mcp_path, (payload + "\n").encode("utf-8"), mode=0o600, private=True)
    return mcp_path


def render_permission_flags(
    request: AgentRequest,
    *,
    step_dir: Path,
    permission_mode_supported: bool = True,
    strict_mcp_supported: bool = True,
    policy_profile: str | None = None,
    allow_skip_permissions: bool = False,
    extra_dirs: Sequence[str] = (),
    proxy_bridge: LocalProxyBridge | None = None,
) -> RenderedPermissions:
    """Write ``<step_dir>/settings.json`` (and optional ``mcp.json``) and render Claude CLI flags."""
    if step_dir.resolve().is_relative_to(Path(request.workdir).resolve()):
        raise ValueError("step_dir must be outside request.workdir")

    writable = bool(request.permissions.fs_write.allow)
    shell_rules = _shell_allow_rules(request)
    trusted_full = policy_profile == "trusted-full-access"
    skip_perms = can_skip_permissions(
        request,
        policy_profile=policy_profile,
        allow_skip_permissions=allow_skip_permissions,
    )

    settings_doc = _build_settings_document(
        request,
        writable=writable,
        shell_rules=shell_rules,
        trusted_full_access=trusted_full,
    )
    settings_path = step_dir / "settings.json"
    settings_bytes = (
        json.dumps(settings_doc, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"
    ).encode("utf-8")
    atomic_write(settings_path, settings_bytes, mode=0o600, private=True)

    tools: list[str] = []
    if shell_rules:
        tools.append("Bash")
    if writable:
        tools.extend(("Read", "Edit", "Write", "Grep", "Glob"))
    else:
        tools.extend(("Read", "Grep", "Glob"))
    if "Task" in request.permissions.tools:
        tools.append("Task")

    flags: list[str] = ["--tools", ",".join(tools)]
    if not writable:
        flags.extend(("--disallowedTools", ",".join(_DISALLOWED_ON_READONLY)))
    elif permission_mode_supported and not skip_perms:
        flags.extend(("--permission-mode", "acceptEdits"))

    if shell_rules:
        flags.extend(("--allowedTools", ",".join(shell_rules)))

    if skip_perms:
        flags.append("--dangerously-skip-permissions")

    for directory in _extra_directories(request, extra_dirs):
        flags.extend(("--add-dir", directory))

    mcp_path: Path | None = None
    if request.mcp_servers:
        mcp_path = _write_mcp_config(request, step_dir, proxy_bridge)
        flags.extend(("--mcp-config", str(mcp_path)))
        if strict_mcp_supported:
            flags.append("--strict-mcp-config")

    return RenderedPermissions(argv=tuple(flags), settings_path=settings_path, mcp_path=mcp_path)


def denial_hint(tool: str, tool_input: object) -> str:
    """Produce a bounded, secret-free diagnostic hint for a denied tool call (never raw arguments)."""
    clean_tool = tool.strip()
    if clean_tool in ("Edit", "Write", "NotebookEdit", "MultiEdit"):
        return "filesystem write denied by step permission policy"
    if clean_tool == "Bash":
        if isinstance(tool_input, dict):
            raw_cmd = tool_input.get("command")  # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
            if isinstance(raw_cmd, str) and raw_cmd.strip():
                first = posixpath.basename(raw_cmd.strip().split()[0])
                if _SAFE_PROG_RE.fullmatch(first):
                    return f"shell command '{first}' denied by step command policy"
        return "shell command denied by step command policy"
    if clean_tool in ("Read", "Glob", "Grep"):
        return "filesystem read denied by step permission policy"
    if clean_tool in ("WebFetch", "WebSearch"):
        return "network access denied by step permission policy"
    if clean_tool.startswith("mcp__"):
        return "MCP tool call denied by step permission policy"
    return "tool call denied by step permission policy"
