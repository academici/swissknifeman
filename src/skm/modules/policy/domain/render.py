"""Rendering and proofs of representation (policy §§5.11, 13 ``is_subset``).

A consumer that can express only a single path policy, a single operation decision or a single host list
must not widen the conjunction it received. ``representable_paths`` and ``operation_document`` return the
equivalent single form or refuse; ``view_document`` raises ``CAPABILITY_UNAVAILABLE`` (``reason:
permissions_not_representable``) instead of rounding a rule towards "allow". ``request_violations`` checks a
serialized permission request against a ceiling; every inclusion it cannot prove is reported as widening.
"""

from __future__ import annotations

import posixpath
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.isolation import IsolationProfile
from skm.kernel.json_types import JsonObject, JsonValue

from .commands import COMMAND_MODE_ORDER, CommandMode, CommandPolicy
from .network import NETWORK_MODE_ORDER, NetworkMode, flatten_hosts, pattern_subsumes
from .operations import OperationDecision, OperationName, OperationRule, Requirement
from .paths import PathPolicy, PathRule, PathScope, ScopeRoots, subsumes
from .permission_set import PermissionSet, tool_allowed
from .profiles import parse_layer

__all__ = [
    "IsolationGrants",
    "IsolationProperty",
    "Violation",
    "isolation_grants",
    "isolation_requirements",
    "operation_document",
    "representable_paths",
    "request_violations",
    "view_document",
]

_ALTERNATION_RE = re.compile(
    r"(?P<prefix>.*)\((?P<names>[A-Za-z0-9_-]+(?:\|[A-Za-z0-9_-]+)*)\)(?P<tail>\(\\s\|\$\))?", re.DOTALL
)


@dataclass(frozen=True, slots=True)
class IsolationGrants:
    profile: str
    rw_paths: tuple[str, ...]
    ro_paths: tuple[str, ...]


class IsolationProperty(StrEnum):
    """A guarantee an isolation backend must *prove* before a unit is spawned (adapters §7.3).

    The profile name selects a mechanism, not a set of guarantees: ``worktree`` and a write-only Landlock
    ruleset prove ``fs_write`` at most, never the others. A property outside what the backend itself enforces
    counts only through a companion proof bound to the exact paths, hosts and launch of the request and
    enforced by its launcher before the spawn; a label or a free-text claim is no proof.
    """

    FS_WRITE = "fs_write"
    FS_READ = "fs_read"
    NETWORK_NONE = "network_none"
    NETWORK_ALLOWLIST = "network_allowlist"
    CREDENTIALS = "credentials"
    LIFECYCLE = "lifecycle"
    RESOURCES = "resources"
    DISK_QUOTA = "disk_quota"
    CONFIG = "config"


@dataclass(frozen=True, slots=True)
class Violation:
    field: str
    reason: str
    detail: str = ""

    def to_json(self) -> JsonObject:
        return {"field": self.field, "reason": self.reason, "detail": self.detail}


def _unrepresentable(field: str, detail: str) -> CapabilityUnavailable:
    return CapabilityUnavailable(
        ErrorCode.CAPABILITY_UNAVAILABLE,
        f"permissions cannot be represented without widening ({field})",
        details={"reason": "permissions_not_representable", "field": field, "detail": detail},
    )


def representable_paths(policies: tuple[PathPolicy, ...]) -> PathPolicy | None:
    """One policy equal to the conjunction when provable by prefixes, else ``None`` (the adapter refuses)."""
    deny = tuple(dict.fromkeys(rule for policy in policies for rule in policy.deny))
    # candidates in order of their allow count (ties: each one is tried)
    for candidate in sorted(policies, key=lambda policy: len(policy.allow)):
        if all(
            all(any(subsumes(outer, inner) for outer in policy.allow) for inner in candidate.allow)
            for policy in policies
            if policy is not candidate
        ):
            return PathPolicy(candidate.allow, deny)
    return None


def _covers(rule: PathRule, scope: PathScope, mount: str | None, relative: str) -> bool:
    """``rule`` allows every path at and below ``relative`` (``""``: the scope root)."""
    if rule.scope is not scope or rule.mount not in {None, mount}:
        return False
    if rule.pattern == "**":
        return True
    prefix = rule.pattern[:-3] if rule.pattern.endswith("/**") else ""
    return (
        bool(prefix) and not _has_glob(prefix) and (relative == prefix or relative.startswith(prefix + "/"))
    )


def _allowed(policies: tuple[PathPolicy, ...], scope: PathScope, mount: str | None, relative: str) -> bool:
    return bool(policies) and all(
        any(_covers(rule, scope, mount, relative) for rule in policy.allow) for policy in policies
    )


def _below(relative: str, outer: str) -> bool:
    return relative != outer and (not outer or relative.startswith(outer + "/"))


def _dirs(policies: tuple[PathPolicy, ...], scope: PathScope, mount: str | None) -> tuple[str, ...]:
    """Outermost relative directories (``""``: the root) that every policy allows completely. An explicit
    empty ``allow`` yields none; a rule that is not ``**`` or ``P/**`` is never granted (narrower)."""
    candidates = {""} | {
        rule.pattern[:-3]
        for policy in policies
        for rule in policy.allow
        if rule.scope is scope and rule.mount in {None, mount} and rule.pattern.endswith("/**")
    }
    allowed = [relative for relative in sorted(candidates) if _allowed(policies, scope, mount, relative)]
    return tuple(relative for relative in allowed if not any(_below(relative, outer) for outer in allowed))


def _has_glob(text: str) -> bool:
    return any(char in text for char in "*?[")


def _deny_inside(
    policies: tuple[PathPolicy, ...], scope: PathScope, mount: str | None, relative: str
) -> PathRule | None:
    """A deny rule that may match a path at or below ``relative``: a directory grant cannot carry it."""
    for policy in policies:
        for rule in policy.deny:
            if rule.scope is not scope or rule.mount not in {None, mount}:
                continue
            cut = [index for index, char in enumerate(rule.pattern) if char in "*?["]
            literal = rule.pattern[: cut[0]] if cut else rule.pattern
            if not relative or literal.startswith(relative + "/") or (relative + "/").startswith(literal):
                return rule
    return None


def _not_representable(profile: str, field: str, path: str, rule: PathRule | None) -> CapabilityUnavailable:
    return CapabilityUnavailable(
        ErrorCode.SANDBOX_UNAVAILABLE,
        f"isolation profile {profile} cannot represent the {field} restriction under {path}",
        details={
            "profile": profile,
            "reason": "restriction_not_representable",
            "field": field,
            "path": path,
            "rule": "" if rule is None else f"{rule.scope}:{rule.pattern}",
        },
    )


@dataclass(frozen=True, slots=True)
class _Root:
    scope: PathScope
    mount: str | None
    path: str
    writable: bool
    readable: bool


def _root_grants(perms: PermissionSet, profile: str, root: _Root) -> tuple[list[str], list[str]]:
    """Read-write and read-only directories of one root. A writable directory is readable as well, so it
    must pass ``fs_read`` too; a deny rule inside a granted directory refuses the profile (§5.11)."""

    def join(relative: str) -> str:
        return posixpath.join(root.path, relative) if relative else root.path

    writable = _dirs(perms.fs_write, root.scope, root.mount) if root.writable else ()
    for relative in writable:
        for field, policies in (("fs_write", perms.fs_write), ("fs_read", perms.fs_read)):
            rule = _deny_inside(policies, root.scope, root.mount, relative)
            if rule is not None:
                raise _not_representable(profile, field, join(relative), rule)
        if not _allowed(perms.fs_read, root.scope, root.mount, relative):
            raise _not_representable(profile, "fs_read", join(relative), None)
    readable: list[str] = []
    for relative in _dirs(perms.fs_read, root.scope, root.mount) if root.readable else ():
        if relative in writable or any(_below(relative, outer) for outer in writable):
            continue
        rule = _deny_inside(perms.fs_read, root.scope, root.mount, relative)
        if rule is not None:
            raise _not_representable(profile, "fs_read", join(relative), rule)
        readable.append(relative)
    return [join(relative) for relative in writable], [join(relative) for relative in readable]


def isolation_grants(perms: PermissionSet, roots: ScopeRoots, profile: str) -> IsolationGrants:
    """FS grants of one isolation profile; never wider than worktrees, materials, tmp and safe dirs (S-55)
    nor than ``fs_read``/``fs_write``: a root is granted only as far as every policy allows it."""
    if profile not in perms.allowed_isolation:
        # §5.11 names Forbidden; the kernel files SANDBOX_UNAVAILABLE under the capability category
        raise CapabilityUnavailable(
            ErrorCode.SANDBOX_UNAVAILABLE,
            f"isolation profile {profile} is not allowed by the permissions",
            details={"profile": profile, "allowed": list[JsonValue](sorted(perms.allowed_isolation))},
        )
    candidates = [
        _Root(PathScope.WORKTREE, mount, root, writable=True, readable=True)
        for mount, root in sorted(roots.worktrees.items())
    ]
    if roots.tmp is not None:
        candidates.append(_Root(PathScope.TMP, None, roots.tmp, writable=True, readable=False))
    if roots.materials is not None:
        candidates.append(_Root(PathScope.MATERIALS, None, roots.materials, writable=False, readable=True))
    candidates.extend(
        _Root(PathScope.SAFE_DIR, None, root, writable=False, readable=True) for root in roots.safe_dirs
    )
    if profile == IsolationProfile.NONE.value and roots.home is not None:
        candidates.append(_Root(PathScope.HOME, None, roots.home, writable=True, readable=True))
    rw: list[str] = []
    ro: list[str] = []
    for root in candidates:
        writable, readable = _root_grants(perms, profile, root)
        rw.extend(writable)
        ro.extend(readable)
    return IsolationGrants(profile, tuple(dict.fromkeys(rw)), tuple(dict.fromkeys(ro)))


def _reads_unrestricted(policies: tuple[PathPolicy, ...]) -> bool:
    """Every layer allows ``**`` of every scope and denies nothing: all of the filesystem is readable.

    ``any`` matches only paths outside every scope root, so ``any:**`` alone leaves home, worktrees,
    materials, tmp and safe dirs unreadable: the read stays confined and needs a proof."""
    return bool(policies) and all(
        not policy.deny
        and all(
            any(rule.scope is scope and rule.mount is None and rule.pattern == "**" for rule in policy.allow)
            for scope in PathScope
        )
        for policy in policies
    )


def isolation_requirements(
    perms: PermissionSet,
    *,
    credentials: bool = False,
    resources: bool = False,
    disk_quota: bool = False,
    config: bool = False,
) -> frozenset[IsolationProperty]:
    """Properties the permissions require an isolation backend to enforce; none is dropped as "close enough".

    Writes are always confined and the unit lifecycle always owned. A scoped ``fs_read`` is a read
    confinement (host secrets stay out of reach), an ``allowlist`` network needs an egress boundary (an
    allowlist that admits no host needs ``network_none``) and ``any`` needs nothing. The keyword flags carry
    what the permissions do not state: declared credential mounts, resource limits, a disk quota and client
    config isolation requested by the runtime or an extension.
    """
    required = {IsolationProperty.FS_WRITE, IsolationProperty.LIFECYCLE}
    if not _reads_unrestricted(perms.fs_read):
        required.add(IsolationProperty.FS_READ)
    mode = perms.network.mode
    if mode is NetworkMode.ALLOWLIST and not flatten_hosts(perms.network.hosts):
        mode = NetworkMode.NONE
    if mode is NetworkMode.NONE:
        required.add(IsolationProperty.NETWORK_NONE)
    elif mode is NetworkMode.ALLOWLIST:
        required.add(IsolationProperty.NETWORK_ALLOWLIST)
    for flag, item in (
        (credentials, IsolationProperty.CREDENTIALS),
        (resources, IsolationProperty.RESOURCES),
        (disk_quota, IsolationProperty.DISK_QUOTA),
        (config, IsolationProperty.CONFIG),
    ):
        if flag:
            required.add(item)
    return frozenset(required)


def operation_document(rule: OperationRule) -> JsonObject:
    """The single profile row equal to ``rule`` (§4.3 in reverse) or ``CAPABILITY_UNAVAILABLE``."""
    risk: JsonObject = {} if rule.risk is None else {"risk": rule.risk.value}
    if rule.deny:
        return {"decision": OperationDecision.DENY.value, **risk}
    if Requirement.INTENT in rule.requires:
        return {"decision": OperationDecision.INTENT.value, **risk}
    conditions = [
        name
        for name, present in (
            ("task_authority", Requirement.TASK_AUTHORITY in rule.requires),
            ("capability", bool(rule.capabilities)),
            ("ask", Requirement.ASK in rule.requires),
        )
        if present
    ]
    if (
        len(conditions) > 1
        or len(rule.capabilities) > 1
        or (rule.warn and conditions and conditions != ["ask"])
    ):
        raise _unrepresentable("operations", f"conditions {sorted(conditions)} warn={rule.warn}")
    if conditions == ["capability"]:
        capability = next(iter(rule.capabilities)).value
        return {"decision": OperationDecision.CAPABILITY.value, "capability": capability, **risk}
    if conditions:
        return {"decision": conditions[0], **risk}
    return {"decision": OperationDecision.WARN.value if rule.warn else OperationDecision.ALLOW.value, **risk}


def _rule_doc(rule: PathRule) -> JsonObject:
    doc: JsonObject = {"scope": rule.scope.value, "pattern": rule.pattern}
    if rule.mount is not None:
        doc["mount"] = rule.mount
    return doc


def _policy_doc(policy: PathPolicy) -> JsonObject:
    return {
        "allow": [_rule_doc(rule) for rule in policy.allow],
        "deny": [_rule_doc(rule) for rule in policy.deny],
    }


def _commands_doc(commands: CommandPolicy) -> JsonObject:
    programs = sorted(rule.program for rule in commands.allow if rule.subcommands is None)
    subcommands: JsonObject = {
        rule.program: cast("JsonValue", sorted(rule.subcommands))
        for rule in sorted(commands.allow, key=lambda item: item.program)
        if rule.subcommands is not None
    }
    return {
        "mode": commands.mode.value,
        "programs": cast("list[JsonValue]", programs),
        "subcommands": subcommands,
        "deny_patterns": list[JsonValue](commands.deny_patterns),
        "ask_patterns": list[JsonValue](commands.ask_patterns),
        "inline_interpreters": list[JsonValue](sorted(commands.inline_interpreters)),
        "trust_inline_interpreters": commands.trust_inline_interpreters,
    }


def view_document(perms: PermissionSet) -> JsonObject:
    """``PermissionSetView`` without ``digest``; refuses what the single-form fields cannot express. An
    allowlist whose conjunction admits no host stays ``allowlist`` with no hosts: §5.3 N1 still allows
    ``web.search`` and asks about an unknown destination there, ``none`` denies both."""
    network_hosts = (
        sorted(flatten_hosts(perms.network.hosts)) if perms.network.mode is NetworkMode.ALLOWLIST else []
    )
    return {
        "fs_read": [_policy_doc(policy) for policy in perms.fs_read],
        "fs_write": [_policy_doc(policy) for policy in perms.fs_write],
        "commands": _commands_doc(perms.commands),
        "network": {"mode": perms.network.mode.value, "hosts": list[JsonValue](network_hosts)},
        "tools": [list[JsonValue](sorted(tools)) for tools in perms.tools],
        "operations": {name.value: operation_document(perms.operations[name]) for name in OperationName},
        "external_effects": list[JsonValue](sorted(item.value for item in perms.external_effects)),
        "effects_need_approval": list[JsonValue](sorted(item.value for item in perms.effects_need_approval)),
        "allowed_isolation": list[JsonValue](sorted(perms.allowed_isolation)),
        "sources": list[JsonValue](perms.sources),
    }


def _paths_violations(
    field: str, requested: tuple[PathPolicy, ...], ceiling: tuple[PathPolicy, ...]
) -> list[Violation]:
    merged = representable_paths(requested)
    if merged is None:
        return [Violation(field, "not_provable", "requested path conjunction is not representable")]
    found: list[Violation] = []
    for policy in ceiling:
        found.extend(
            Violation(field, "widens", f"allow {rule.scope}:{rule.pattern}")
            for rule in merged.allow
            if not any(subsumes(outer, rule) for outer in policy.allow)
        )
        found.extend(
            Violation(field, "drops_deny", f"deny {rule.scope}:{rule.pattern}")
            for rule in policy.deny
            if not any(subsumes(own, rule) for own in merged.deny)
        )
    return found


def _alternation(pattern: str) -> tuple[str, frozenset[str], str] | None:
    """``prefix``, names and tail of ``prefix(a|b)`` or ``prefix(a|b)(\\s|$)``; ``None`` for any other shape.
    A prefix that does not compile alone means the group is not a top-level one."""
    match = _ALTERNATION_RE.fullmatch(pattern)
    if match is None:
        return None
    try:
        re.compile(match["prefix"])
    except re.error:
        return None
    return match["prefix"], frozenset(match["names"].split("|")), match["tail"] or ""


def _pattern_kept(pattern: str, own: tuple[str, ...]) -> bool:
    """A pattern of the ceiling still applies: listed verbatim, or proved by a pattern with the same prefix,
    at least the same names and the same tail or none, which matches wherever ``pattern`` matches."""
    if pattern in own:
        return True
    limit = _alternation(pattern)
    if limit is None:
        return False
    prefix, names, tail = limit
    return any(
        other is not None and other[0] == prefix and names <= other[1] and other[2] in {tail, ""}
        for other in map(_alternation, own)
    )


def _commands_violations(requested: CommandPolicy, ceiling: CommandPolicy) -> list[Violation]:
    found: list[Violation] = []
    if COMMAND_MODE_ORDER[requested.mode] < COMMAND_MODE_ORDER[ceiling.mode]:
        found.append(Violation("commands.mode", "widens", requested.mode.value))
    if requested.mode is CommandMode.ALLOWLIST:
        limits = (
            {rule.program: rule for rule in ceiling.allow} if ceiling.mode is CommandMode.ALLOWLIST else None
        )
        for rule in requested.allow:
            limit = None if limits is None else limits.get(rule.program)
            if limits is None:
                continue
            if limit is None or not (
                limit.subcommands is None
                or (rule.subcommands is not None and rule.subcommands <= limit.subcommands)
            ):
                found.append(Violation("commands.allow", "widens", rule.program))
    for name, own, limit in (
        ("commands.deny_patterns", requested.deny_patterns, ceiling.deny_patterns),
        ("commands.ask_patterns", requested.ask_patterns, ceiling.ask_patterns),
    ):
        found.extend(
            Violation(name, "drops_pattern", pattern) for pattern in limit if not _pattern_kept(pattern, own)
        )
    missing = ceiling.inline_interpreters - requested.inline_interpreters
    found.extend(Violation("commands.inline_interpreters", "drops", item) for item in sorted(missing))
    if requested.trust_inline_interpreters and not ceiling.trust_inline_interpreters:
        found.append(Violation("commands.trust_inline_interpreters", "widens", "true"))
    return found


def _rule_violation(
    name: OperationName, requested: OperationRule, ceiling: OperationRule
) -> Violation | None:
    if requested.deny or Requirement.INTENT in requested.requires:
        return None
    if (
        ceiling.deny
        or Requirement.INTENT in ceiling.requires
        or not ceiling.requires <= requested.requires
        or not ceiling.capabilities <= requested.capabilities
        or (ceiling.warn and not requested.warn and not requested.requires)
    ):
        return Violation(f"operations.{name.value}", "widens", "")
    return None


def request_violations(requested: Mapping[str, JsonValue], ceiling: PermissionSet) -> tuple[Violation, ...]:
    """``is_subset``: every field of a ``urn:skm:policy:permission-request:v1`` document that may widen."""
    profile_id = requested.get("profile_id")
    layer_doc = {key: value for key, value in requested.items() if key != "profile_id"}
    layer = parse_layer(layer_doc, source=f"request:{profile_id or 'anonymous'}")
    found: list[Violation] = []
    if layer.fs_read is not None:
        found.extend(_paths_violations("fs_read", (layer.fs_read,), ceiling.fs_read))
    if layer.fs_write is not None:
        found.extend(_paths_violations("fs_write", (layer.fs_write,), ceiling.fs_write))
    if layer.commands is not None:
        own = layer.commands
        commands = CommandPolicy(
            mode=own.mode or (CommandMode.ALLOWLIST if own.allow is not None else ceiling.commands.mode),
            allow=own.allow or (),
            deny_patterns=own.deny_patterns,
            ask_patterns=own.ask_patterns,
            inline_interpreters=own.inline_interpreters,
            trust_inline_interpreters=bool(own.trust_inline_interpreters),
        )
        found.extend(_commands_violations(commands, ceiling.commands))
    if layer.network is not None:
        found.extend(_network_violations(layer.network.mode, layer.network.hosts, ceiling))
    if layer.tools is not None:
        found.extend(
            Violation("tools", "widens", tool)
            for tool in sorted(layer.tools)
            if not tool_allowed(ceiling.tools, tool)
        )
    for name, rule in (layer.operations or {}).items():
        violation = _rule_violation(name, rule, ceiling.operations[name])
        if violation is not None:
            found.append(violation)
    if layer.external_effects is not None:
        widened = layer.external_effects - ceiling.external_effects
        found.extend(Violation("external_effects", "widens", item.value) for item in sorted(widened))
        own_need = layer.effects_need_approval or frozenset()
        dropped = (ceiling.effects_need_approval & layer.external_effects) - own_need
        found.extend(Violation("effects_need_approval", "drops", item.value) for item in sorted(dropped))
    if layer.allowed_isolation is not None:
        widened_isolation = layer.allowed_isolation - ceiling.allowed_isolation
        found.extend(Violation("allowed_isolation", "widens", item) for item in sorted(widened_isolation))
    return tuple(found)


def _network_violations(
    mode: NetworkMode | None, hosts: frozenset[str] | None, ceiling: PermissionSet
) -> list[Violation]:
    limit = ceiling.network
    if mode is None:
        mode = NetworkMode.ALLOWLIST if hosts is not None else limit.mode
    if NETWORK_MODE_ORDER[mode] < NETWORK_MODE_ORDER[limit.mode]:
        return [Violation("network.mode", "widens", mode.value)]
    if mode is not NetworkMode.ALLOWLIST or limit.mode is NetworkMode.ANY:
        return []
    allowed = flatten_hosts(limit.hosts)
    return [
        Violation("network.hosts", "widens", host)
        for host in sorted(hosts or ())
        if not any(pattern_subsumes(outer, host) for outer in allowed)
    ]
