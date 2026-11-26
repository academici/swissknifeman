"""Codex permission profile mapping, deny-floor, and representability checks (integrations §4.8, §5.4)."""

from __future__ import annotations

import posixpath
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable, ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.policy.public import (
    CommandMode,
    OperationName,
    PathPolicy,
    PathRule,
    PathScope,
    PermissionSet,
)

__all__ = [
    "CODEX_DENY_FLOOR_PATTERNS",
    "CODEX_MACHINE_LOCAL_KEYS",
    "CodexMode",
    "render_codex_mode",
    "validate_codex_permissions",
    "validate_no_machine_local_keys",
]

CODEX_MACHINE_LOCAL_KEYS: Final[tuple[str, ...]] = (
    "model_provider",
    "auth",
    "notify",
    "profile",
    "otel",
    "telemetry",
)

CODEX_DENY_FLOOR_PATTERNS: Final[tuple[str, ...]] = (
    ".env",
    ".env.*",
    ".env*",
    "**/.env",
    "**/.env.*",
    "**/.env*",
    "**/*.pem",
    "**/*.key",
    "**/id_rsa*",
    "~/.ssh/**",
    "~/.aws/**",
)

_SENSITIVE_BASENAMES: Final[frozenset[str]] = frozenset(
    {
        ".env",
        ".env*",
        ".env.*",
        "*.pem",
        "*.key",
        "id_rsa",
        "id_rsa*",
    }
)

_SENSITIVE_HOME_PREFIXES: Final[tuple[str, ...]] = (".ssh", ".aws")


@dataclass(frozen=True, slots=True)
class CodexMode:
    """Rendered Codex ``approval_policy`` and ``sandbox_mode`` pair."""

    approval_policy: str
    sandbox_mode: str


_PROFILE_MODES: Final[Mapping[PermissionProfile, CodexMode]] = {
    PermissionProfile.OBSERVE: CodexMode(approval_policy="untrusted", sandbox_mode="read-only"),
    PermissionProfile.WORKSPACE_CONTAINED: CodexMode(approval_policy="never", sandbox_mode="workspace-write"),
    PermissionProfile.TRUSTED_FULL_ACCESS: CodexMode(
        approval_policy="never", sandbox_mode="danger-full-access"
    ),
}


def validate_no_machine_local_keys(mapping: Mapping[str, object]) -> None:
    """Refuse machine-local Codex keys in project-scoped configuration inputs."""
    present = [key for key in CODEX_MACHINE_LOCAL_KEYS if key in mapping]
    if present:
        keys_json: list[JsonValue] = list(present)
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            f"Codex project configuration must not set machine-local keys: {', '.join(present)}",
            details={"keys": keys_json, "target": "codex"},
        )


def _extract_path_policies(raw: object) -> tuple[PathPolicy, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    policies: list[PathPolicy] = []
    for item in cast("Sequence[object]", raw):
        if isinstance(item, PathPolicy):
            policies.append(item)
        elif isinstance(item, Mapping):
            imap = cast("Mapping[str, object]", item)
            policies.append(PathPolicy(_extract_rules(imap.get("allow")), _extract_rules(imap.get("deny"))))
    return tuple(policies)


def _extract_rules(raw: object) -> tuple[PathRule, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    rules: list[PathRule] = []
    for entry in cast("Sequence[object]", raw):
        if isinstance(entry, PathRule):
            rules.append(entry)
        elif isinstance(entry, str):
            rules.append(PathRule(PathScope.WORKTREE, entry))
        elif isinstance(entry, Mapping):
            rmap = cast("Mapping[str, object]", entry)
            pat = rmap.get("pattern")
            mount = rmap.get("mount")
            if isinstance(pat, str):
                rules.append(
                    PathRule(
                        PathScope(str(rmap.get("scope", "worktree"))),
                        pat,
                        mount if isinstance(mount, str) else None,
                    )
                )
    return tuple(rules)


def _weakens_deny_floor(rule: PathRule) -> bool:
    norm = posixpath.normpath(rule.pattern).lstrip("/")
    if norm in ("", ".", "**", "*"):
        return False
    if rule.scope is PathScope.HOME:
        first = norm.split("/", 1)[0]
        if first in _SENSITIVE_HOME_PREFIXES:
            return True
    base = posixpath.basename(norm)
    if base in _SENSITIVE_BASENAMES or base.startswith(".env.") or base.startswith("id_rsa"):
        return True
    return norm.endswith((".pem", ".key"))


def _check_path_representability(
    fs_read: Sequence[PathPolicy],
    fs_write: Sequence[PathPolicy],
    mode: CodexMode,
) -> None:
    denied_patterns: set[str] = set()
    for pol in (*fs_read, *fs_write):
        for dr in pol.deny:
            denied_patterns.add(f"{dr.scope.value}:{dr.pattern}")

    for pol in (*fs_read, *fs_write):
        for ar in pol.allow:
            if _weakens_deny_floor(ar) and f"{ar.scope.value}:{ar.pattern}" not in denied_patterns:
                raise CapabilityUnavailable(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    f"Codex permissions cannot weaken the SKM deny floor for {ar.pattern!r}",
                    details={"target": "codex", "reason": "deny_floor_weakened", "pattern": ar.pattern},
                )

    for pol in fs_read:
        if pol.deny:
            read_pats: list[JsonValue] = [r.pattern for r in pol.deny]
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "Codex project config cannot enforce fine-grained fs_read deny globs natively",
                details={
                    "target": "codex",
                    "reason": "unrepresentable_fs_read_deny",
                    "patterns": read_pats,
                },
            )

    if mode.sandbox_mode != "read-only":
        for pol in fs_write:
            if pol.deny:
                write_pats: list[JsonValue] = [r.pattern for r in pol.deny]
                raise CapabilityUnavailable(
                    ErrorCode.CAPABILITY_UNAVAILABLE,
                    "Codex writable sandbox cannot enforce fine-grained fs_write deny globs",
                    details={
                        "target": "codex",
                        "reason": "unrepresentable_fs_write_deny",
                        "patterns": write_pats,
                    },
                )


def validate_codex_permissions(
    mode: CodexMode,
    permissions: PermissionSet | Mapping[str, Any] | None,
) -> None:
    """Ensure ``mode`` does not widen unrepresentable ``permissions`` or weaken the deny floor."""
    if permissions is None:
        return

    if isinstance(permissions, PermissionSet):
        fs_read: Sequence[PathPolicy] = permissions.fs_read
        fs_write: Sequence[PathPolicy] = permissions.fs_write
        modify_denied = permissions.operations[OperationName.MODIFY_WRITE_SET].deny
        has_fs_write_field = True
        cmd_mode = permissions.commands.mode.value
        tool_groups: tuple[frozenset[str], ...] = permissions.tools
    else:
        validate_no_machine_local_keys(permissions)
        fs_read = _extract_path_policies(permissions.get("fs_read"))
        fs_write = _extract_path_policies(permissions.get("fs_write"))
        ops = permissions.get("operations")
        mod_op = (
            cast("Mapping[str, object]", ops).get(OperationName.MODIFY_WRITE_SET.value)
            if isinstance(ops, Mapping)
            else None
        )
        modify_denied = (
            isinstance(mod_op, Mapping) and cast("Mapping[str, object]", mod_op).get("deny") is True
        )
        has_fs_write_field = "fs_write" in permissions and permissions.get("fs_write") is not None
        cmds = permissions.get("commands")
        cmd_mode = (
            str(cast("Mapping[str, object]", cmds).get("mode", CommandMode.DENYLIST.value))
            if isinstance(cmds, Mapping)
            else CommandMode.DENYLIST.value
        )
        raw_tools = permissions.get("tools")
        if isinstance(raw_tools, Sequence) and not isinstance(raw_tools, (str, bytes)) and raw_tools:
            seq_tools = cast("Sequence[object]", raw_tools)
            if all(isinstance(t, str) for t in seq_tools):
                tool_groups = (frozenset(str(t) for t in seq_tools),)
            else:
                tool_groups = tuple(
                    frozenset(str(t) for t in cast("Sequence[object]", g))
                    for g in seq_tools
                    if isinstance(g, Sequence) and not isinstance(g, (str, bytes))
                )
        else:
            tool_groups = ()

    _check_path_representability(fs_read, fs_write, mode)

    if mode.sandbox_mode != "read-only":
        no_writable_paths = has_fs_write_field and bool(fs_write) and all(not p.allow for p in fs_write)
        if modify_denied or no_writable_paths:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                f"Codex sandbox_mode={mode.sandbox_mode!r} would exceed read-only PermissionSet ceiling",
                details={"target": "codex", "reason": "write_forbidden_by_permissions"},
            )

    if mode.approval_policy == "never":
        shell_forbidden_by_tools = bool(tool_groups) and not all("shell.run" in grp for grp in tool_groups)
        if cmd_mode == CommandMode.NONE.value or shell_forbidden_by_tools:
            raise CapabilityUnavailable(
                ErrorCode.CAPABILITY_UNAVAILABLE,
                "Codex approval_policy='never' cannot enforce forbidden shell execution",
                details={"target": "codex", "reason": "shell_forbidden_by_permissions"},
            )


def render_codex_mode(
    profile: PermissionProfile,
    permissions: PermissionSet | Mapping[str, Any] | None = None,
) -> CodexMode:
    """Map resolved ``PermissionProfile`` to ``CodexMode`` and verify ``permissions`` representability."""
    mode = _PROFILE_MODES[PermissionProfile(profile)]
    validate_codex_permissions(mode, permissions)
    return mode
