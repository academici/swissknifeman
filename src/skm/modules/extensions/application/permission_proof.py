"""Whether what a policy profile permits stays inside the ceiling (extensions §4.6 rule 4, §7.1 step 10).

``policy.public.is_subset`` is the comparator and takes a ``urn:skm:policy:permission-request:v1`` document,
so the effective set of the requested profile is written in that form. A set the document cannot express
exactly gives no proof: ``CAPABILITY_UNAVAILABLE``, never a rounded request. Equal sets need no document.

The answer of the comparator is final here: only policy decides which patterns of the ceiling a request keeps,
verbatim or through a provably wider one. A profile that leaves out a pattern counts as wider even under an
allowlist: a listed program takes arbitrary arguments (``env kill 1``, ``echo x >> f``), and nothing here can
prove that no such command line matches. The document states the request as it is, never narrowed to fit.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.json_types import JsonValue
from skm.modules.extensions.domain.permission_guard import widens_permissions
from skm.modules.policy.public import (
    NetworkMode,
    OperationDecision,
    Requirement,
    is_subset,
    permissions_digest,
    representable_paths,
)

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject
    from skm.modules.policy.public import (
        CommandPolicy,
        NetworkPolicy,
        OperationRule,
        PathPolicy,
        PathRule,
        PermissionSet,
        Violation,
    )

__all__ = ["profile_violations"]


def _no_proof(field: str, detail: str) -> CapabilityUnavailable:
    return CapabilityUnavailable(
        ErrorCode.CAPABILITY_UNAVAILABLE,
        f"the permissions of a policy profile cannot be compared with the ceiling ({field})",
        details={"reason": "permission_proof_unavailable", "field": field, "detail": detail},
    )


def _rule(rule: PathRule) -> JsonObject:
    document: JsonObject = {"scope": rule.scope.value, "pattern": rule.pattern}
    if rule.mount is not None:
        document["mount"] = rule.mount
    return document


def _paths(field: str, policies: tuple[PathPolicy, ...]) -> JsonObject:
    merged = representable_paths(policies)
    if merged is None:
        raise _no_proof(field, "the path conjunction has no single form")
    return {"allow": [_rule(item) for item in merged.allow], "deny": [_rule(item) for item in merged.deny]}


def _commands(commands: CommandPolicy) -> JsonObject:
    """A program has one row in the document and ``CommandPolicy.rule`` reads the first of its rules."""
    listed = [rule.program for rule in commands.allow]
    if len(set(listed)) != len(listed):
        raise _no_proof("commands.allow", "a program is listed more than once")
    programs = sorted(rule.program for rule in commands.allow if rule.subcommands is None)
    subcommands: JsonObject = {
        rule.program: cast("JsonValue", sorted(rule.subcommands))
        for rule in commands.allow
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


def _network(network: NetworkPolicy) -> JsonObject:
    """The mode stays as it is: an allowlist that admits no host is no ``none``, ``check_tool_call`` still
    lets ``web.search`` through and asks about an unknown destination. Plain host names flatten through
    ``allows``; the meet of a wildcard or a port has no such test here."""
    if network.mode is not NetworkMode.ALLOWLIST:
        return {"mode": network.mode.value}
    names = sorted({name for hosts in network.hosts for name in hosts})
    if len(network.hosts) > 1 and any("*" in name or ":" in name for name in names):
        raise _no_proof("network.hosts", "the host conjunction names a wildcard or a port")
    hosts = names if len(network.hosts) == 1 else [name for name in names if network.allows(name, None)]
    return {"mode": "allowlist", "hosts": list[JsonValue](hosts)}


def _admits(pattern: str, tool: str) -> bool:
    if pattern == "mcp:*":
        return tool.startswith("mcp:")
    if pattern.startswith("mcp:") and pattern.endswith("/*"):
        return tool.startswith(pattern[:-1])
    return pattern == tool


def _tools(tools: tuple[frozenset[str], ...]) -> JsonObject:
    """The conjunction of the lists: tool patterns nest, so their meet is always one of the patterns. No list
    at all admits every tool, which an ``allow`` list cannot say."""
    if not tools:
        raise _no_proof("tools", "a conjunction without a list admits every tool")
    names = sorted(
        {
            name
            for allowed in tools
            for name in allowed
            if all(any(_admits(pattern, name) for pattern in other) for other in tools)
        }
    )
    return {"allow": list[JsonValue](names)}


def _operation(name: str, rule: OperationRule) -> JsonObject:
    if rule.deny:
        return {"decision": OperationDecision.DENY.value}
    if Requirement.INTENT in rule.requires:
        return {"decision": OperationDecision.INTENT.value}
    conditions = [
        condition
        for condition, present in (
            (OperationDecision.TASK_AUTHORITY, Requirement.TASK_AUTHORITY in rule.requires),
            (OperationDecision.CAPABILITY, bool(rule.capabilities)),
            (OperationDecision.ASK, Requirement.ASK in rule.requires),
        )
        if present
    ]
    if (
        len(conditions) > 1
        or len(rule.capabilities) > 1
        or (rule.warn and conditions and conditions != [OperationDecision.ASK])
    ):
        raise _no_proof(f"operations.{name}", "the conditions have no single decision")
    if conditions == [OperationDecision.CAPABILITY]:
        capability = next(iter(rule.capabilities)).value
        return {"decision": OperationDecision.CAPABILITY.value, "capability": capability}
    if conditions:
        return {"decision": conditions[0].value}
    return {"decision": (OperationDecision.WARN if rule.warn else OperationDecision.ALLOW).value}


def _request(perms: PermissionSet) -> dict[str, JsonValue]:
    return {
        "fs": {"read": _paths("fs_read", perms.fs_read), "write": _paths("fs_write", perms.fs_write)},
        "commands": _commands(perms.commands),
        "network": _network(perms.network),
        "tools": _tools(perms.tools),
        "operations": {
            name.value: _operation(name.value, rule) for name, rule in sorted(perms.operations.items())
        },
        "effects": {
            "allow": list[JsonValue](sorted(item.value for item in perms.external_effects)),
            "need_approval": list[JsonValue](sorted(item.value for item in perms.effects_need_approval)),
        },
        "allowed_isolation": list[JsonValue](sorted(perms.allowed_isolation)),
    }


def profile_violations(requested: PermissionSet, ceiling: PermissionSet) -> tuple[Violation, ...]:
    """What ``requested`` asks for beyond ``ceiling``; ``()``: proven inside it."""
    if permissions_digest(requested) == permissions_digest(ceiling):
        return ()
    return widens_permissions(_request(requested), ceiling, is_subset=is_subset)
