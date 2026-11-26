"""Claude Code permissions and settings renderers (integrations §4.8, §5.3, §5.4)."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, cast

from skm.adapters.integrations._render import json_doc
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
    EffectKind,
    NetworkMode,
    OperationName,
    PathPolicy,
    PathRule,
    PathScope,
    PermissionSet,
    representable_paths,
)

from .hooks import CLAUDE_HOOK_EVENTS, render_hook_entries

__all__ = [
    "CLAUDE_DENY_FLOOR",
    "CLAUDE_LOCAL_SETTINGS_PATH",
    "CLAUDE_SETTINGS_PATH",
    "CLAUDE_SETTINGS_RENDERER",
    "ClaudeRules",
    "default_mode_for_profile",
    "render_claude_rules",
    "render_local_settings",
    "render_project_settings",
]

CLAUDE_SETTINGS_PATH: Final[str] = ".claude/settings.json"
CLAUDE_LOCAL_SETTINGS_PATH: Final[str] = ".claude/settings.local.json"
CLAUDE_SETTINGS_RENDERER: Final[str] = "claude_code.settings@1"

CLAUDE_DENY_FLOOR: Final[tuple[str, ...]] = (
    "Read(.env)",
    "Read(.env.*)",
    "Read(**/*.pem)",
    "Read(**/*.key)",
    "Read(~/.ssh/**)",
    "Read(~/.aws/**)",
    "Bash(sudo *)",
)

_NATIVE_PASSTHROUGH_TOOLS: Final[tuple[str, ...]] = ("Agent", "TodoWrite", "Workflow")
_DOMAIN_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9.-]+$")
_PLAIN_CMD_PREFIX_RE: Final[re.Pattern[str]] = re.compile(r"^[A-Za-z0-9_./:@=-]+(?:\s+[A-Za-z0-9_./:@=-]+)*$")
_SUBCOMMAND_RISK_PROBES: Final[tuple[str, ...]] = (
    "",
    " -D probe",
    " delete",
    " expire",
    " -X POST probe",
    " -i probe",
    " --force",
)

_PROFILE_DEFAULT_MODE: Final[Mapping[PermissionProfile, str]] = {
    PermissionProfile.OBSERVE: "default",
    PermissionProfile.WORKSPACE_CONTAINED: "acceptEdits",
    PermissionProfile.TRUSTED_FULL_ACCESS: "bypassPermissions",
}

_PROJECT_OWNED_KEYS: Final[tuple[OwnedKeyPath, ...]] = (
    OwnedKeyPath(("permissions", "allow"), "replace"),
    OwnedKeyPath(("permissions", "ask"), "replace"),
    OwnedKeyPath(("permissions", "deny"), "replace"),
    *(OwnedKeyPath(("hooks", ev), "list_union_tagged") for ev in CLAUDE_HOOK_EVENTS),
)

_LOCAL_OWNED_KEYS: Final[tuple[OwnedKeyPath, ...]] = (
    OwnedKeyPath(("permissions", "defaultMode"), "replace"),
)


@dataclass(frozen=True, slots=True)
class ClaudeRules:
    """Rendered Claude Code ``permissions.{allow,ask,deny}`` lists."""

    allow: tuple[str, ...]
    ask: tuple[str, ...]
    deny: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _ParsedPermissions:
    fs_read: tuple[PathPolicy, ...]
    fs_write: tuple[PathPolicy, ...]
    tool_groups: tuple[frozenset[str], ...]
    has_explicit_tools: bool
    modify_denied: bool
    git_push_denied: bool
    cmd_mode: str
    cmd_allow_items: Sequence[object]
    cmd_ask_items: Sequence[str]
    cmd_deny_patterns: Sequence[str]
    cmd_ask_patterns: Sequence[str]
    inline_interpreters: frozenset[str]
    trust_inline: bool
    net_mode: str
    net_hosts: Sequence[Sequence[str] | frozenset[str]]
    need_approval: frozenset[str]


def default_mode_for_profile(profile: PermissionProfile) -> str:
    """Map resolved ``PermissionProfile`` to Claude Code ``permissions.defaultMode``."""
    return _PROFILE_DEFAULT_MODE[PermissionProfile(profile)]


def _dedup(items: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def _is_safe_rule_arg(text: str) -> bool:
    return bool(text) and not any(ch in text for ch in ("\0", "\n", "\r", ")"))


def _tool_matches(pattern: str, tool: str) -> bool:
    if pattern == tool:
        return True
    if pattern == "mcp:*":
        return tool.startswith("mcp:")
    if pattern.startswith("mcp:") and pattern.endswith("/*"):
        return tool.startswith(pattern[:-1])
    return False


def _tool_allowed_groups(groups: Sequence[frozenset[str]], tool: str, *, default_if_empty: bool) -> bool:
    if not groups:
        return default_if_empty
    return all(any(_tool_matches(pat, tool) for pat in group) for group in groups)


def _str_list(raw: object) -> tuple[str, ...]:
    if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)):
        return tuple(str(x) for x in cast("Sequence[object]", raw))
    return ()


def _parse_path_rules(raw: object) -> tuple[PathRule, ...]:
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
            pat_val = rmap.get("pattern")
            mount_val = rmap.get("mount")
            if isinstance(pat_val, str):
                rules.append(
                    PathRule(
                        PathScope(str(rmap.get("scope", "worktree"))),
                        pat_val,
                        mount_val if isinstance(mount_val, str) else None,
                    )
                )
    return tuple(rules)


def _parse_path_policies(raw: object) -> tuple[PathPolicy, ...]:
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return ()
    policies: list[PathPolicy] = []
    for item in cast("Sequence[object]", raw):
        if isinstance(item, PathPolicy):
            policies.append(item)
        elif isinstance(item, Mapping):
            imap = cast("Mapping[str, object]", item)
            policies.append(
                PathPolicy(_parse_path_rules(imap.get("allow")), _parse_path_rules(imap.get("deny")))
            )
    return tuple(policies)


def _parse_tool_groups(raw_tools: object) -> tuple[frozenset[str], ...]:
    if not isinstance(raw_tools, Sequence) or isinstance(raw_tools, (str, bytes)) or not raw_tools:
        return ()
    seq_tools = cast("Sequence[object]", raw_tools)
    if all(isinstance(t, str) for t in seq_tools):
        return (frozenset(str(t) for t in seq_tools),)
    return tuple(
        frozenset(str(t) for t in cast("Sequence[object]", grp))
        for grp in seq_tools
        if isinstance(grp, Sequence) and not isinstance(grp, (str, bytes))
    )


def _parse_host_groups(raw_hosts: object) -> tuple[Sequence[str], ...]:
    if not isinstance(raw_hosts, Sequence) or isinstance(raw_hosts, (str, bytes)) or not raw_hosts:
        return ()
    seq_hosts = cast("Sequence[object]", raw_hosts)
    if all(isinstance(h, str) for h in seq_hosts):
        return ([str(h) for h in seq_hosts],)
    return tuple(
        [str(h) for h in cast("Sequence[object]", grp)]
        for grp in seq_hosts
        if isinstance(grp, Sequence) and not isinstance(grp, (str, bytes))
    )


def _as_str_map(raw: object) -> Mapping[str, object]:
    if isinstance(raw, Mapping):
        return cast("Mapping[str, object]", raw)
    return {}


def _coerce_permissions(perms: PermissionSet | Mapping[str, Any]) -> _ParsedPermissions:
    if isinstance(perms, PermissionSet):
        return _ParsedPermissions(
            fs_read=perms.fs_read,
            fs_write=perms.fs_write,
            tool_groups=perms.tools,
            has_explicit_tools=True,
            modify_denied=perms.operations[OperationName.MODIFY_WRITE_SET].deny,
            git_push_denied=perms.operations[OperationName.GIT_PUSH].deny,
            cmd_mode=perms.commands.mode.value,
            cmd_allow_items=perms.commands.allow,
            cmd_ask_items=(),
            cmd_deny_patterns=perms.commands.deny_patterns,
            cmd_ask_patterns=perms.commands.ask_patterns,
            inline_interpreters=perms.commands.inline_interpreters,
            trust_inline=perms.commands.trust_inline_interpreters,
            net_mode=perms.network.mode.value,
            net_hosts=perms.network.hosts,
            need_approval=frozenset(e.value for e in perms.effects_need_approval),
        )

    ops_map = _as_str_map(perms.get("operations"))
    mod_op = _as_str_map(ops_map.get(OperationName.MODIFY_WRITE_SET.value))
    push_op = _as_str_map(ops_map.get(OperationName.GIT_PUSH.value))

    cmds_map = _as_str_map(perms.get("commands"))
    raw_allow: object = cmds_map.get("allow", ())
    allow_seq: Sequence[object] = (
        cast("Sequence[object]", raw_allow)
        if isinstance(raw_allow, Sequence) and not isinstance(raw_allow, (str, bytes))
        else ()
    )

    net_map = _as_str_map(perms.get("network"))

    return _ParsedPermissions(
        fs_read=_parse_path_policies(perms.get("fs_read")),
        fs_write=_parse_path_policies(perms.get("fs_write")),
        tool_groups=_parse_tool_groups(perms.get("tools")),
        has_explicit_tools=(perms.get("tools") is not None),
        modify_denied=(mod_op.get("deny") is True),
        git_push_denied=(push_op.get("deny") is True),
        cmd_mode=str(cmds_map.get("mode", CommandMode.DENYLIST.value)),
        cmd_allow_items=allow_seq,
        cmd_ask_items=_str_list(cmds_map.get("ask")),
        cmd_deny_patterns=_str_list(cmds_map.get("deny_patterns")),
        cmd_ask_patterns=_str_list(cmds_map.get("ask_patterns")),
        inline_interpreters=frozenset(_str_list(cmds_map.get("inline_interpreters"))),
        trust_inline=bool(cmds_map.get("trust_inline_interpreters", False)),
        net_mode=str(net_map.get("mode", NetworkMode.NONE.value)),
        net_hosts=_parse_host_groups(net_map.get("hosts")),
        need_approval=frozenset(_str_list(perms.get("effects_need_approval"))),
    )


def _worktree_projection(policies: Sequence[PathPolicy]) -> PathPolicy | None:
    if not policies:
        return None
    projected = tuple(
        PathPolicy(
            allow=tuple(
                PathRule(PathScope.WORKTREE, r.pattern)
                for r in pol.allow
                if r.scope is PathScope.WORKTREE and r.mount in (None, "main")
            ),
            deny=tuple(
                PathRule(PathScope.WORKTREE, r.pattern)
                for r in pol.deny
                if r.scope is PathScope.WORKTREE and r.mount in (None, "main")
            ),
        )
        for pol in policies
    )
    return representable_paths(projected)


def _explicit_fs_denies(policies: Sequence[PathPolicy], *, write: bool) -> list[str]:
    out: list[str] = []
    for pol in policies:
        for rule in pol.deny:
            if rule.scope is PathScope.WORKTREE and rule.mount in (None, "main"):
                arg = rule.pattern
            elif rule.scope is PathScope.HOME:
                arg = f"~/{rule.pattern.lstrip('/')}"
            else:
                continue
            if not _is_safe_rule_arg(arg):
                continue
            out.extend((f"Edit({arg})", f"Write({arg})")) if write else out.append(f"Read({arg})")
    return out


def _host_matches_pattern(pattern: str, host: str) -> bool:
    pat = pattern.lower().partition(":")[0]
    target = host.lower().rstrip(".")
    if pat.startswith("*."):
        return target.endswith(pat[1:]) and len(target) > len(pat) - 1
    return target == pat


def _intersect_clean_domains(host_groups: Sequence[Sequence[str] | frozenset[str]]) -> tuple[str, ...]:
    if not host_groups:
        return ()
    candidates: list[str] = []
    for group in host_groups:
        for raw_host in group:
            if _DOMAIN_RE.fullmatch(raw_host) and raw_host not in candidates:
                candidates.append(raw_host)
    return tuple(
        host
        for host in candidates
        if all(
            any(":" not in pat and _host_matches_pattern(pat, host) for pat in group) for group in host_groups
        )
    )


def _is_inline_interpreter(program: str, inline_interpreters: frozenset[str]) -> bool:
    if program in inline_interpreters:
        return True
    return program.startswith("python") and any(p.startswith("python") for p in inline_interpreters)


def _matches_any_regex(patterns: Sequence[str], prefix: str) -> bool:
    for pat in patterns:
        try:
            if any(re.search(pat, f"{prefix}{probe}") is not None for probe in _SUBCOMMAND_RISK_PROBES):
                return True
        except re.error:
            return True
    return False


def _plain_prefix_from_pattern(raw: str) -> str | None:
    trimmed = raw.strip().removesuffix(" *").strip()
    return trimmed if _PLAIN_CMD_PREFIX_RE.fullmatch(trimmed) else None


def _coerce_subcommands(raw_subs: object) -> Sequence[str] | None:
    if raw_subs is None:
        return None
    if isinstance(raw_subs, (frozenset, set)):
        return sorted(str(s) for s in cast("Iterable[object]", raw_subs))
    if isinstance(raw_subs, Sequence) and not isinstance(raw_subs, (str, bytes)):
        return [str(s) for s in cast("Sequence[object]", raw_subs)]
    return ()


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
        raw_prog = imap.get("program")
        if isinstance(raw_prog, str) and raw_prog.strip():
            subs = _coerce_subcommands(imap.get("subcommands"))
            return None if subs == () and imap.get("subcommands") != () else (raw_prog.strip(), subs, None)
    return None


def _extract_command_prefixes(
    allow_items: Sequence[object],
    *,
    inline_interpreters: frozenset[str],
    trust_inline: bool,
) -> list[str]:
    prefixes: list[str] = []
    for item in allow_items:
        coerced = _coerce_command_item(item)
        if coerced is None:
            continue
        program, subs, literal_prefix = coerced
        if program in PROJECTION_CARRIER_HEADS:
            continue
        if literal_prefix is not None:
            prefixes.append(literal_prefix)
        elif subs is None:
            if not trust_inline and _is_inline_interpreter(program, inline_interpreters):
                continue
            prefixes.append(program)
        else:
            prefixes.extend(f"{program} {sub.replace(':', ' ')}" for sub in subs if sub and "*" not in sub)
    return prefixes


def _render_fs_rules(parsed: _ParsedPermissions, *, default_tool_ok: bool) -> tuple[list[str], list[str]]:
    allow: list[str] = []
    denies = _explicit_fs_denies(parsed.fs_read, write=False)
    if _tool_allowed_groups(parsed.tool_groups, "fs.read", default_if_empty=default_tool_ok):
        rep_read = _worktree_projection(parsed.fs_read)
        if rep_read is not None:
            denied_r = {r.pattern for r in rep_read.deny}
            allow.extend(
                f"Read({r.pattern})"
                for r in rep_read.allow
                if r.pattern not in denied_r and _is_safe_rule_arg(r.pattern)
            )

    denies.extend(_explicit_fs_denies(parsed.fs_write, write=True))
    can_edit = _tool_allowed_groups(parsed.tool_groups, "fs.edit", default_if_empty=default_tool_ok)
    can_write = _tool_allowed_groups(parsed.tool_groups, "fs.write", default_if_empty=default_tool_ok)
    if not parsed.modify_denied and (can_edit or can_write):
        rep_write = _worktree_projection(parsed.fs_write)
        if rep_write is not None:
            denied_w = {r.pattern for r in rep_write.deny}
            for rule in rep_write.allow:
                if rule.pattern in denied_w or not _is_safe_rule_arg(rule.pattern):
                    continue
                if can_edit:
                    allow.append(f"Edit({rule.pattern})")
                if can_write:
                    allow.append(f"Write({rule.pattern})")
    return allow, denies


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


def _render_command_rules(
    parsed: _ParsedPermissions, *, default_tool_ok: bool, allowed_domains: frozenset[str]
) -> tuple[list[str], list[str], list[str]]:
    allow: list[str] = []
    ask: list[str] = []
    denies = [
        f"Bash({plain} *)"
        for pat in parsed.cmd_deny_patterns
        if (plain := _plain_prefix_from_pattern(pat)) is not None and _is_safe_rule_arg(plain)
    ]
    can_shell = _tool_allowed_groups(parsed.tool_groups, "shell.run", default_if_empty=default_tool_ok)
    if not can_shell or parsed.cmd_mode == CommandMode.NONE.value:
        return allow, ask, denies

    if parsed.cmd_mode == CommandMode.ALLOWLIST.value:
        prefixes = _extract_command_prefixes(
            parsed.cmd_allow_items,
            inline_interpreters=parsed.inline_interpreters,
            trust_inline=parsed.trust_inline,
        )
        for prefix in prefixes:
            if not _is_safe_rule_arg(prefix):
                continue
            if _matches_any_regex(parsed.cmd_deny_patterns, prefix):
                denies.append(f"Bash({prefix} *)")
            elif not _matches_any_regex(parsed.cmd_ask_patterns, prefix) and _prefix_allowed_by_network(
                prefix, parsed.net_mode, allowed_domains
            ):
                allow.append(f"Bash({prefix} *)")

    ask.extend(
        f"Bash({plain_ask} *)"
        for raw_ask in (*parsed.cmd_ask_items, *parsed.cmd_ask_patterns)
        if (plain_ask := _plain_prefix_from_pattern(raw_ask)) is not None and _is_safe_rule_arg(plain_ask)
    )
    if EffectKind.GIT_PUSH.value in parsed.need_approval and not parsed.git_push_denied:
        ask.append("Bash(git push *)")
    return allow, ask, denies


def render_claude_rules(perms: PermissionSet | Mapping[str, Any]) -> ClaudeRules:
    """Render ``PermissionSet`` or ``NormalizedPermissions`` to ``ClaudeRules`` (never wider than input)."""
    parsed = _coerce_permissions(perms)
    default_tool_ok = not parsed.has_explicit_tools
    clean_domains = _intersect_clean_domains(parsed.net_hosts)

    fs_allow, fs_denies = _render_fs_rules(parsed, default_tool_ok=default_tool_ok)
    cmd_allow, cmd_ask, cmd_denies = _render_command_rules(
        parsed, default_tool_ok=default_tool_ok, allowed_domains=frozenset(clean_domains)
    )

    allow = [*fs_allow, *cmd_allow]
    if (
        _tool_allowed_groups(parsed.tool_groups, "web.fetch", default_if_empty=default_tool_ok)
        and parsed.net_mode == NetworkMode.ALLOWLIST.value
    ):
        allow.extend(f"WebFetch(domain:{d})" for d in clean_domains)

    if parsed.tool_groups:
        allow.extend(
            tool
            for tool in _NATIVE_PASSTHROUGH_TOOLS
            if _tool_allowed_groups(parsed.tool_groups, tool, default_if_empty=False)
        )

    deny_tuple = _dedup((*CLAUDE_DENY_FLOOR, *fs_denies, *cmd_denies))
    deny_lookup = frozenset(deny_tuple)
    clean_allow = _dedup(rule for rule in allow if rule not in deny_lookup)
    clean_ask = _dedup(rule for rule in cmd_ask if rule not in deny_lookup and rule not in clean_allow)
    return ClaudeRules(allow=clean_allow, ask=clean_ask, deny=deny_tuple)


def render_project_settings(inputs: ProjectionInputs) -> DesiredFile:
    """Render ``.claude/settings.json`` combining ``permissions`` and ``hooks`` owned paths."""
    rules = render_claude_rules(inputs.permissions)
    hook_entries = render_hook_entries(inputs)

    raw_doc: dict[str, Any] = {
        "permissions": {
            "allow": list(rules.allow),
            "ask": list(rules.ask),
            "deny": list(rules.deny),
        },
    }
    if hook_entries:
        raw_doc["hooks"] = {ev: hook_entries[ev] for ev in CLAUDE_HOOK_EVENTS if ev in hook_entries}

    boundary = ManagedBoundary(Ownership.MERGED_JSON, owned_keys=_PROJECT_OWNED_KEYS)
    canonical_doc = extract_owned(raw_doc, boundary.owned_keys)
    managed_bytes = json_doc.dumps_bytes(canonical_doc)

    refs: list[SourceRef] = []
    perm_digest = inputs.permissions.get("digest")
    if isinstance(perm_digest, str) and perm_digest:
        refs.append({"kind": "permissions", "digest": perm_digest})
    if hook_entries:
        refs.append({"kind": "hooks", "key": "integrations.hooks.mode"})

    return DesiredFile(
        target=TargetId.CLAUDE_CODE,
        surface=Surface.PERMISSIONS,
        relative_path=CLAUDE_SETTINGS_PATH,
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=tuple(refs),
        renderer=CLAUDE_SETTINGS_RENDERER,
    )


def render_local_settings(inputs: ProjectionInputs) -> DesiredFile:
    """Render ``.claude/settings.local.json`` owning ``permissions.defaultMode``."""
    mode = default_mode_for_profile(inputs.profile)
    boundary = ManagedBoundary(Ownership.MERGED_JSON, owned_keys=_LOCAL_OWNED_KEYS)
    canonical_doc = extract_owned({"permissions": {"defaultMode": mode}}, boundary.owned_keys)
    managed_bytes = json_doc.dumps_bytes(canonical_doc)
    return DesiredFile(
        target=TargetId.CLAUDE_CODE,
        surface=Surface.PERMISSIONS,
        relative_path=CLAUDE_LOCAL_SETTINGS_PATH,
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=({"kind": "profile", "key": inputs.profile.value},),
        renderer=CLAUDE_SETTINGS_RENDERER,
    )
