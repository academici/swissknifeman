"""Cursor CLI and IDE permissions renderers (integrations §4.8, §5.3, §5.4)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from skm.adapters.integrations._render import json_doc
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonValue
from skm.modules.integrations.domain.contracts import SourceRef
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.merged_json import OwnedKeyPath, extract_owned
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.profiles import PermissionProfile
from skm.modules.integrations.domain.target import Surface, TargetId
from skm.modules.policy.public import (
    FORGE_API_HOSTS,
    GIT_NETWORK_SUBCOMMANDS,
    PROJECTION_CARRIER_HEADS,
    CommandMode,
    CommandRule,
    NetworkMode,
    OperationName,
    PathPolicy,
    PathRule,
    PathScope,
    PermissionSet,
    representable_paths,
)

__all__ = [
    "CURSOR_CLI_FORBIDDEN_MODE_KEYS",
    "CURSOR_CLI_PATH",
    "CURSOR_DENY_FLOOR",
    "CURSOR_IDE_PERMISSIONS_PATH",
    "CURSOR_PERMISSIONS_RENDERER",
    "CursorRules",
    "render_cli_permissions",
    "render_cursor_rules",
    "render_ide_permissions",
    "validate_no_cli_mode_keys",
]

CURSOR_CLI_PATH: Final[str] = ".cursor/cli.json"
CURSOR_IDE_PERMISSIONS_PATH: Final[str] = ".cursor/permissions.json"
CURSOR_PERMISSIONS_RENDERER: Final[str] = "cursor.permissions@1"
CURSOR_CLI_FORBIDDEN_MODE_KEYS: Final[tuple[str, ...]] = (
    "approvalMode",
    "sandbox",
    "approval_mode",
    "sandbox_mode",
)
CURSOR_DENY_FLOOR: Final[tuple[str, ...]] = (
    "Read(.env*)",
    "Read(**/.env*)",
    "Read(**/*.pem)",
    "Read(**/id_rsa*)",
    "Write(**/.env*)",
    "Write(**/*.key)",
    "Write(**/*.pem)",
)

_CLI_OWNED_KEYS: Final[tuple[OwnedKeyPath, ...]] = (
    OwnedKeyPath(("permissions", "allow"), "replace"),
    OwnedKeyPath(("permissions", "deny"), "replace"),
)
_AUTO_RUN_BLOCK_INSTRUCTIONS: Final[str] = (
    "Do not execute destructive git commands or write outside the checkout."
)
_DOMAIN_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9.-]+$")
_PLAIN_CMD_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_./:@=-]+(?:\s+[A-Za-z0-9_./:@=-]+)*$")
_SUBCOMMAND_RISK_PROBES: Final[tuple[str, ...]] = (
    "", " -D probe", " delete", " expire", " -X POST probe", " -i probe", " --force"
)  # fmt: skip
_PROFILE_BASELINE_ALLOW: Final[Mapping[PermissionProfile, tuple[str, ...]]] = {
    PermissionProfile.OBSERVE: (
        "Read(**)", "Shell(git status)", "Shell(git diff)", "Shell(git log)", "Shell(ls)", "Mcp(*:*_recall)"
    ),
    PermissionProfile.WORKSPACE_CONTAINED: (
        "Read(**)", "Write(**)", "Shell(git status)", "Shell(git diff)", "WebFetch(cursor.com)"
    ),
    PermissionProfile.TRUSTED_FULL_ACCESS: (
        "Read(**)", "Write(**)", "Shell(**)", "Mcp(*:*)", "WebFetch(*)"
    ),
}  # fmt: skip
_PROFILE_BASELINE_TERMINAL: Final[Mapping[PermissionProfile, tuple[str, ...]]] = {
    PermissionProfile.OBSERVE: ("git status", "git diff", "git log", "ls"),
    PermissionProfile.WORKSPACE_CONTAINED: ("git status", "git diff"),
    PermissionProfile.TRUSTED_FULL_ACCESS: ("*",),
}


@dataclass(frozen=True, slots=True)
class CursorRules:
    """Rendered Cursor CLI ``permissions.{allow,deny}`` lists and IDE allowlists."""

    allow: tuple[str, ...]
    deny: tuple[str, ...]
    mcp_allowlist: tuple[str, ...] = ()
    terminal_allowlist: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class _ParsedPermissions:
    fs_read: tuple[PathPolicy, ...]
    fs_write: tuple[PathPolicy, ...]
    tool_groups: tuple[frozenset[str], ...]
    has_explicit_tools: bool
    modify_denied: bool
    cmd_mode: str
    cmd_allow_items: Sequence[object]
    cmd_deny_patterns: Sequence[str]
    cmd_ask_patterns: Sequence[str]
    inline_interpreters: frozenset[str]
    trust_inline: bool
    net_mode: str
    net_hosts: Sequence[Sequence[str] | frozenset[str]]


def validate_no_cli_mode_keys(mapping_doc: Mapping[str, object]) -> None:
    """Refuse CLI approval/sandbox mode keys in project ``.cursor/cli.json`` (integrations §4.8, §5.3)."""
    present: list[JsonValue] = [key for key in CURSOR_CLI_FORBIDDEN_MODE_KEYS if key in mapping_doc]
    perms_sub = mapping_doc.get("permissions")
    if isinstance(perms_sub, Mapping):
        sub_map = cast("Mapping[str, object]", perms_sub)
        present.extend(f"permissions.{k}" for k in CURSOR_CLI_FORBIDDEN_MODE_KEYS if k in sub_map)
    if present:
        raise ValidationFailed(
            ErrorCode.INTEGRATION_BOUNDARY_INVALID,
            f"Cursor project cli.json forbids approval/sandbox mode keys: {present!r}",
            details={"target": TargetId.CURSOR.value, "forbidden_keys": present},
        )


def _dedup(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _is_safe_rule_arg(text: str) -> bool:
    return bool(text) and not any(ch in text for ch in ("\0", "\n", "\r", ")"))


def _tool_matches(pattern: str, tool: str) -> bool:
    return (
        pattern == tool
        or (pattern == "mcp:*" and tool.startswith("mcp:"))
        or (pattern.startswith("mcp:") and pattern.endswith("/*") and tool.startswith(pattern[:-1]))
    )


def _tool_allowed_groups(groups: Sequence[frozenset[str]], tool: str, *, default_if_empty: bool) -> bool:
    return default_if_empty if not groups else all(any(_tool_matches(p, tool) for p in g) for g in groups)


def _as_seq(raw: object) -> Sequence[object]:
    return (
        cast("Sequence[object]", raw)
        if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes))
        else ()
    )


def _as_str_map(raw: object) -> Mapping[str, object]:
    return cast("Mapping[str, object]", raw) if isinstance(raw, Mapping) else {}


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


def _parse_str_groups(raw: object) -> tuple[tuple[str, ...], ...]:
    seq = _as_seq(raw)
    if not seq:
        return ()
    if all(isinstance(x, str) for x in seq):
        return (tuple(str(x) for x in seq),)
    return tuple(tuple(str(x) for x in _as_seq(grp)) for grp in seq if _as_seq(grp))


def _coerce_permissions(perms: PermissionSet | Mapping[str, Any]) -> _ParsedPermissions:
    if isinstance(perms, PermissionSet):
        return _ParsedPermissions(
            perms.fs_read,
            perms.fs_write,
            perms.tools,
            True,
            perms.operations[OperationName.MODIFY_WRITE_SET].deny,
            perms.commands.mode.value,
            perms.commands.allow,
            perms.commands.deny_patterns,
            perms.commands.ask_patterns,
            perms.commands.inline_interpreters,
            perms.commands.trust_inline_interpreters,
            perms.network.mode.value,
            perms.network.hosts,
        )
    mod_op = _as_str_map(_as_str_map(perms.get("operations")).get(OperationName.MODIFY_WRITE_SET.value))
    cmds_map, net_map = _as_str_map(perms.get("commands")), _as_str_map(perms.get("network"))
    return _ParsedPermissions(
        _parse_path_policies(perms.get("fs_read")),
        _parse_path_policies(perms.get("fs_write")),
        tuple(frozenset(g) for g in _parse_str_groups(perms.get("tools"))),
        perms.get("tools") is not None,
        mod_op.get("deny") is True,
        str(cmds_map.get("mode", CommandMode.DENYLIST.value)),
        _as_seq(cmds_map.get("allow", ())),
        tuple(str(x) for x in _as_seq(cmds_map.get("deny_patterns"))),
        tuple(str(x) for x in _as_seq(cmds_map.get("ask_patterns"))),
        frozenset(str(x) for x in _as_seq(cmds_map.get("inline_interpreters"))),
        bool(cmds_map.get("trust_inline_interpreters", False)),
        str(net_map.get("mode", NetworkMode.NONE.value)),
        _parse_str_groups(net_map.get("hosts")),
    )


def _worktree_projection(policies: Sequence[PathPolicy]) -> PathPolicy | None:
    if not policies:
        return None

    def _keep(rules: Sequence[PathRule]) -> tuple[PathRule, ...]:
        return tuple(
            PathRule(PathScope.WORKTREE, r.pattern)
            for r in rules
            if r.scope is PathScope.WORKTREE and r.mount in (None, "main")
        )

    return representable_paths(tuple(PathPolicy(_keep(pol.allow), _keep(pol.deny)) for pol in policies))


def _explicit_fs_denies(policies: Sequence[PathPolicy], *, write: bool) -> list[str]:
    verb = "Write" if write else "Read"
    out: list[str] = []
    for pol in policies:
        for rule in pol.deny:
            if rule.scope is PathScope.WORKTREE and rule.mount in (None, "main"):
                arg = rule.pattern
            elif rule.scope is PathScope.HOME:
                arg = f"~/{rule.pattern.lstrip('/')}"
            else:
                continue
            if _is_safe_rule_arg(arg):
                out.append(f"{verb}({arg})")
    return out


def _intersect_clean_domains(host_groups: Sequence[Sequence[str] | frozenset[str]]) -> tuple[str, ...]:
    if not host_groups:
        return ()
    candidates = _dedup(h for group in host_groups for h in group if _DOMAIN_RE.fullmatch(h))

    def _matches(pat: str, host: str) -> bool:
        p, t = pat.lower().partition(":")[0], host.lower().rstrip(".")
        return (t.endswith(p[1:]) and len(t) > len(p) - 1) if p.startswith("*.") else t == p

    return tuple(
        h
        for h in candidates
        if all(any(":" not in pat and _matches(pat, h) for pat in g) for g in host_groups)
    )


def _matches_any_regex(patterns: Sequence[str], prefix: str) -> bool:
    for pat in patterns:
        try:
            if any(re.search(pat, f"{prefix}{probe}") is not None for probe in _SUBCOMMAND_RISK_PROBES):
                return True
        except re.error:
            return True
    return False


def _coerce_command_item(item: object) -> tuple[str, Sequence[str] | None, str | None] | None:
    if isinstance(item, str):
        cleaned = item.strip().removesuffix(" *").strip()
        if not cleaned:
            return None
        return (cleaned.split()[0], None, cleaned) if " " in cleaned else (cleaned, None, None)
    if isinstance(item, CommandRule):
        return item.program, (None if item.subcommands is None else sorted(item.subcommands)), None
    if isinstance(item, Mapping):
        imap = cast("Mapping[str, object]", item)
        raw_prog, raw_subs = imap.get("program"), imap.get("subcommands")
        if isinstance(raw_prog, str) and raw_prog.strip():
            if raw_subs is None:
                return raw_prog.strip(), None, None
            if isinstance(raw_subs, (frozenset, set)):
                subs: Sequence[str] = sorted(str(s) for s in cast("Iterable[object]", raw_subs))
                return (raw_prog.strip(), subs, None) if subs else None
            seq_subs = [str(s) for s in _as_seq(raw_subs)]
            if seq_subs or raw_subs == ():
                return raw_prog.strip(), seq_subs, None
    return None


def _extract_command_prefixes(
    allow_items: Sequence[object], *, inline_interpreters: frozenset[str], trust_inline: bool
) -> list[str]:
    prefixes: list[str] = []
    has_py_inline = any(p.startswith("python") for p in inline_interpreters)
    for item in allow_items:
        coerced = _coerce_command_item(item)
        if coerced is None or coerced[0] in PROJECTION_CARRIER_HEADS:
            continue
        program, subs, literal_prefix = coerced
        if literal_prefix is not None:
            prefixes.append(literal_prefix)
        elif subs is None:
            is_inline = program in inline_interpreters or (program.startswith("python") and has_py_inline)
            if trust_inline or not is_inline:
                prefixes.append(program)
        else:
            prefixes.extend(f"{program} {sub.replace(':', ' ')}" for sub in subs if sub and "*" not in sub)
    return prefixes


def _prefix_allowed_by_network(prefix: str, net_mode: str, allowed_domains: frozenset[str]) -> bool:
    words = prefix.split()
    if words[:1] == ["git"] and len(words) > 1 and words[1] in GIT_NETWORK_SUBCOMMANDS:
        return net_mode == NetworkMode.ANY.value
    forge_host = FORGE_API_HOSTS.get(words[0]) if words else None
    if forge_host is not None:
        return net_mode == NetworkMode.ANY.value or (
            net_mode == NetworkMode.ALLOWLIST.value and forge_host in allowed_domains
        )
    return True


def _render_fs_rules(
    parsed: _ParsedPermissions, *, default_tool_ok: bool, profile: PermissionProfile
) -> tuple[list[str], list[str]]:
    allow: list[str] = []
    denies = _explicit_fs_denies(parsed.fs_read, write=False)
    if (
        _tool_allowed_groups(parsed.tool_groups, "fs.read", default_if_empty=default_tool_ok)
        and (rep_read := _worktree_projection(parsed.fs_read)) is not None
    ):
        denied_r = {r.pattern for r in rep_read.deny}
        allow.extend(
            f"Read({r.pattern})"
            for r in rep_read.allow
            if r.pattern not in denied_r and _is_safe_rule_arg(r.pattern)
        )
    denies.extend(_explicit_fs_denies(parsed.fs_write, write=True))
    can_write = (
        profile is not PermissionProfile.OBSERVE
        and not parsed.modify_denied
        and any(
            _tool_allowed_groups(parsed.tool_groups, t, default_if_empty=default_tool_ok)
            for t in ("fs.write", "fs.edit")
        )
    )
    if can_write and (rep_write := _worktree_projection(parsed.fs_write)) is not None:
        denied_w = {r.pattern for r in rep_write.deny}
        allow.extend(
            f"Write({r.pattern})"
            for r in rep_write.allow
            if r.pattern not in denied_w and _is_safe_rule_arg(r.pattern)
        )
    return allow, denies


def _render_command_rules(
    parsed: _ParsedPermissions,
    *,
    default_tool_ok: bool,
    allowed_domains: frozenset[str],
    profile: PermissionProfile,
) -> tuple[list[str], list[str], list[str]]:
    cli_allow: list[str] = []
    terminal_allow: list[str] = []
    denies: list[str] = []
    for pat in parsed.cmd_deny_patterns:
        plain = pat.strip().removesuffix(" *").strip()
        if _PLAIN_CMD_PREFIX_RE.fullmatch(plain) and _is_safe_rule_arg(plain):
            denies.append(f"Shell({plain})")
    if (
        not _tool_allowed_groups(parsed.tool_groups, "shell.run", default_if_empty=default_tool_ok)
        or parsed.cmd_mode == CommandMode.NONE.value
    ):
        return cli_allow, terminal_allow, denies
    if parsed.cmd_mode == CommandMode.ALLOWLIST.value:
        for prefix in _extract_command_prefixes(
            parsed.cmd_allow_items,
            inline_interpreters=parsed.inline_interpreters,
            trust_inline=parsed.trust_inline,
        ):
            if not _is_safe_rule_arg(prefix):
                continue
            if _matches_any_regex(parsed.cmd_deny_patterns, prefix):
                denies.append(f"Shell({prefix})")
            elif not _matches_any_regex(parsed.cmd_ask_patterns, prefix) and _prefix_allowed_by_network(
                prefix, parsed.net_mode, allowed_domains
            ):
                cli_allow.append(f"Shell({prefix})")
                terminal_allow.append(prefix)
    elif (
        parsed.cmd_mode == CommandMode.DENYLIST.value
        and not parsed.cmd_deny_patterns
        and not parsed.cmd_ask_patterns
        and profile is PermissionProfile.TRUSTED_FULL_ACCESS
    ):
        cli_allow.append("Shell(**)")
        terminal_allow.append("*")
    return cli_allow, terminal_allow, denies


def _render_mcp_rules(
    parsed: _ParsedPermissions, *, profile: PermissionProfile
) -> tuple[list[str], list[str]]:
    if not parsed.tool_groups:
        return [], []
    if _tool_allowed_groups(parsed.tool_groups, "mcp:any/any", default_if_empty=False):
        spec = "*:*_recall" if profile is PermissionProfile.OBSERVE else "*:*"
        return [f"Mcp({spec})"], [spec]
    mcp_cli: list[str] = []
    mcp_ide: list[str] = []
    for group in parsed.tool_groups:
        for pat in sorted(group):
            if not pat.startswith("mcp:") or pat == "mcp:*":
                continue
            rest = pat[4:]
            raw_spec: str | None = None
            if rest.endswith("/*") and (srv := rest[:-2]) and _is_safe_rule_arg(srv):
                raw_spec = f"{srv}:*"
            elif "/" in rest:
                srv, _, tool = rest.partition("/")
                if srv and tool and _is_safe_rule_arg(f"{srv}:{tool}"):
                    raw_spec = f"{srv}:{tool}"
            if raw_spec and _tool_allowed_groups(parsed.tool_groups, pat, default_if_empty=False):
                eff = (
                    f"{raw_spec[:-1]}*_recall"
                    if profile is PermissionProfile.OBSERVE and raw_spec.endswith(":*")
                    else raw_spec
                )
                mcp_cli.append(f"Mcp({eff})")
                mcp_ide.append(eff)
    return mcp_cli, mcp_ide


def render_cursor_rules(
    perms: PermissionSet | Mapping[str, Any],
    *,
    profile: PermissionProfile = PermissionProfile.WORKSPACE_CONTAINED,
) -> CursorRules:
    """Render ``PermissionSet`` or ``NormalizedPermissions`` to ``CursorRules`` (never wider than input)."""
    resolved_profile = PermissionProfile(profile)
    if isinstance(perms, Mapping):
        validate_no_cli_mode_keys(perms)
        if not any(k in perms for k in ("fs_read", "fs_write", "commands", "network", "tools", "operations")):
            deny_set: frozenset[str] = frozenset(CURSOR_DENY_FLOOR)
            mcp_base = (
                ("*:*_recall",)
                if resolved_profile is PermissionProfile.OBSERVE
                else ("*:*",)
                if resolved_profile is PermissionProfile.TRUSTED_FULL_ACCESS
                else ()
            )
            return CursorRules(
                allow=_dedup(r for r in _PROFILE_BASELINE_ALLOW[resolved_profile] if r not in deny_set),
                deny=CURSOR_DENY_FLOOR,
                mcp_allowlist=mcp_base,
                terminal_allowlist=_PROFILE_BASELINE_TERMINAL[resolved_profile],
            )
    parsed = _coerce_permissions(perms)
    default_tool_ok = not parsed.has_explicit_tools
    clean_domains = _intersect_clean_domains(parsed.net_hosts)
    fs_allow, fs_denies = _render_fs_rules(parsed, default_tool_ok=default_tool_ok, profile=resolved_profile)
    cmd_allow, term_allow, cmd_denies = _render_command_rules(
        parsed,
        default_tool_ok=default_tool_ok,
        allowed_domains=frozenset(clean_domains),
        profile=resolved_profile,
    )
    mcp_cli, mcp_ide = _render_mcp_rules(parsed, profile=resolved_profile)
    allow = [*fs_allow, *cmd_allow, *mcp_cli]
    if _tool_allowed_groups(parsed.tool_groups, "web.fetch", default_if_empty=default_tool_ok):
        if parsed.net_mode == NetworkMode.ALLOWLIST.value:
            allow.extend(f"WebFetch({d})" for d in clean_domains)
        elif (
            parsed.net_mode == NetworkMode.ANY.value
            and resolved_profile is PermissionProfile.TRUSTED_FULL_ACCESS
        ):
            allow.append("WebFetch(*)")
    deny_tuple = _dedup((*CURSOR_DENY_FLOOR, *fs_denies, *cmd_denies))
    deny_lookup = frozenset(deny_tuple)
    return CursorRules(
        allow=_dedup(rule for rule in allow if rule not in deny_lookup),
        deny=deny_tuple,
        mcp_allowlist=_dedup(mcp_ide),
        terminal_allowlist=_dedup(term_allow),
    )


def _permission_source_refs(inputs: ProjectionInputs) -> tuple[SourceRef, ...]:
    perm_digest = inputs.permissions.get("digest")
    if isinstance(perm_digest, str) and perm_digest:
        return (
            {"kind": "permissions", "digest": perm_digest},
            {"kind": "profile", "key": inputs.profile.value},
        )
    return ({"kind": "profile", "key": inputs.profile.value},)


def render_cli_permissions(inputs: ProjectionInputs) -> DesiredFile:
    """Render ``.cursor/cli.json`` owning ``permissions.{allow,deny}`` without mode keys."""
    rules = render_cursor_rules(inputs.permissions, profile=inputs.profile)
    raw_doc: dict[str, Any] = {"permissions": {"allow": list(rules.allow), "deny": list(rules.deny)}}
    boundary = ManagedBoundary(Ownership.MERGED_JSON, owned_keys=_CLI_OWNED_KEYS)
    managed_bytes = json_doc.dumps_bytes(extract_owned(raw_doc, boundary.owned_keys))
    return DesiredFile(
        target=TargetId.CURSOR,
        surface=Surface.PERMISSIONS,
        relative_path=CURSOR_CLI_PATH,
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=_permission_source_refs(inputs),
        renderer=CURSOR_PERMISSIONS_RENDERER,
    )


def render_ide_permissions(inputs: ProjectionInputs) -> DesiredFile:
    """Render ``.cursor/permissions.json`` ``MANAGED_FILE`` IDE allowlists narrowed by ``PermissionSet``."""
    rules = render_cursor_rules(inputs.permissions, profile=inputs.profile)
    doc: dict[str, Any] = {}
    if inputs.profile is not PermissionProfile.TRUSTED_FULL_ACCESS:
        doc["autoRun"] = {"block_instructions": _AUTO_RUN_BLOCK_INSTRUCTIONS}
    doc["mcpAllowlist"] = list(rules.mcp_allowlist)
    doc["terminalAllowlist"] = list(rules.terminal_allowlist)
    managed_bytes = json_doc.dumps_bytes(doc)
    return DesiredFile(
        target=TargetId.CURSOR,
        surface=Surface.PERMISSIONS,
        relative_path=CURSOR_IDE_PERMISSIONS_PATH,
        boundary=ManagedBoundary(Ownership.MANAGED_FILE),
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=_permission_source_refs(inputs),
        renderer=CURSOR_PERMISSIONS_RENDERER,
    )
