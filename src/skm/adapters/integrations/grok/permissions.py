"""Grok ``[permission] deny`` floor renderer and launch-mode guards (integrations §4.8, §5.3, §5.4)."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.target import TargetId
from skm.modules.policy.public import PathPolicy, PathRule, PathScope, PermissionSet

__all__ = [
    "GROK_DENY_FLOOR",
    "GROK_FORBIDDEN_PROJECT_MODE_KEYS",
    "GROK_LAUNCH_FLAGS",
    "GROK_LAUNCH_MODES",
    "launch_flags_for_profile",
    "launch_mode_for_profile",
    "render_grok_deny",
    "validate_no_project_mode_keys",
]

GROK_DENY_FLOOR: Final[tuple[str, ...]] = (
    "Read(.env*)",
    "Read(**/.env*)",
    "Read(**/*.pem)",
    "Read(**/id_rsa*)",
    "Write(**/.env*)",
    "Write(**/*.key)",
    "Write(**/*.pem)",
)

GROK_FORBIDDEN_PROJECT_MODE_KEYS: Final[tuple[str, ...]] = (
    "permission_mode",
    "permissionMode",
    "mode",
    "ask",
    "acceptEdits",
    "always-approve",
    "always_approve",
    "alwaysApprove",
    "approval_policy",
    "approvalMode",
    "sandbox",
    "sandbox_mode",
)

GROK_LAUNCH_MODES: Final[Mapping[PermissionProfile, str]] = {
    PermissionProfile.OBSERVE: "ask",
    PermissionProfile.WORKSPACE_CONTAINED: "acceptEdits",
    PermissionProfile.TRUSTED_FULL_ACCESS: "always-approve",
}

GROK_LAUNCH_FLAGS: Final[Mapping[PermissionProfile, tuple[str, ...]]] = {
    PermissionProfile.OBSERVE: ("--permission-mode", "ask"),
    PermissionProfile.WORKSPACE_CONTAINED: ("--permission-mode", "acceptEdits"),
    PermissionProfile.TRUSTED_FULL_ACCESS: ("--always-approve",),
}


def launch_mode_for_profile(profile: PermissionProfile) -> str:
    """Return the runtime/user launch mode token for ``profile`` (never written to project config)."""
    return GROK_LAUNCH_MODES[profile]


def launch_flags_for_profile(profile: PermissionProfile) -> tuple[str, ...]:
    """Return CLI launch flags for ``profile`` (user/runtime launch advice only, integrations §5.3)."""
    return GROK_LAUNCH_FLAGS[profile]


def validate_no_project_mode_keys(mapping_doc: Mapping[str, object]) -> None:
    """Refuse permission/launch mode keys in project ``.grok/config.toml`` (integrations §4.8, §5.3)."""
    present: list[JsonValue] = [key for key in GROK_FORBIDDEN_PROJECT_MODE_KEYS if key in mapping_doc]
    for subtable_name in ("ui", "permission", "permissions"):
        sub = mapping_doc.get(subtable_name)
        if isinstance(sub, Mapping):
            sub_map = cast("Mapping[str, object]", sub)
            present.extend(
                f"{subtable_name}.{key}" for key in GROK_FORBIDDEN_PROJECT_MODE_KEYS if key in sub_map
            )
    if present:
        raise ValidationFailed(
            ErrorCode.INTEGRATION_BOUNDARY_INVALID,
            f"Grok project config.toml forbids permission/launch mode keys: {present!r}",
            details={"target": TargetId.GROK.value, "forbidden_keys": present},
        )


def _as_seq(raw: object) -> Sequence[object]:
    return (
        cast("Sequence[object]", raw)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
        else ()
    )


def _parse_path_rules(raw: object) -> tuple[PathRule, ...]:
    rules: list[PathRule] = []
    for entry in _as_seq(raw):
        if isinstance(entry, PathRule):
            rules.append(entry)
        elif isinstance(entry, str):
            rules.append(PathRule(PathScope.WORKTREE, entry))
        elif isinstance(entry, Mapping):
            rmap = cast("Mapping[str, object]", entry)
            pat_val, mount_val = rmap.get("pattern"), rmap.get("mount")
            if isinstance(pat_val, str):
                scope = PathScope(str(rmap.get("scope", "worktree")))
                rules.append(PathRule(scope, pat_val, mount_val if isinstance(mount_val, str) else None))
    return tuple(rules)


def _parse_path_policies(raw: object) -> tuple[PathPolicy, ...]:
    policies: list[PathPolicy] = []
    for item in _as_seq(raw):
        if isinstance(item, PathPolicy):
            policies.append(item)
        elif isinstance(item, Mapping):
            imap = cast("Mapping[str, object]", item)
            policies.append(
                PathPolicy(_parse_path_rules(imap.get("allow")), _parse_path_rules(imap.get("deny")))
            )
    return tuple(policies)


def _is_safe_rule_arg(text: str) -> bool:
    return bool(text) and not any(ch in text for ch in ("\0", "\n", "\r", ")"))


def _format_deny_rules(verb: str, policies: Iterable[PathPolicy]) -> list[str]:
    out: list[str] = []
    for policy in policies:
        for rule in policy.deny:
            if rule.scope is PathScope.WORKTREE and rule.mount in (None, "main"):
                arg = rule.pattern
            elif rule.scope is PathScope.HOME:
                arg = f"~/{rule.pattern.lstrip('/')}"
            else:
                continue
            if _is_safe_rule_arg(arg):
                out.append(f"{verb}({arg})")
    return out


def render_grok_deny(permissions: PermissionSet | Mapping[str, Any]) -> tuple[str, ...]:
    """Render ``[permission] deny`` with mandatory ``GROK_DENY_FLOOR`` plus explicit path denies."""
    if isinstance(permissions, PermissionSet):
        fs_read = permissions.fs_read
        fs_write = permissions.fs_write
    else:
        validate_no_project_mode_keys(permissions)
        fs_read = _parse_path_policies(permissions.get("fs_read"))
        fs_write = _parse_path_policies(permissions.get("fs_write"))

    combined: list[str] = [
        *GROK_DENY_FLOOR,
        *_format_deny_rules("Read", fs_read),
        *_format_deny_rules("Write", fs_write),
    ]
    return tuple(dict.fromkeys(combined))
