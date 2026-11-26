"""Permission sets and the narrowing algebra (policy §§4.2, 4.4, 5.12 ``permissions_digest``).

``narrow(a, layer)`` only ever removes actions: conjunction lists grow (fs, network hosts, tools), modes take
the strictest value, operation rules gain conditions, effects and isolation profiles intersect, the effects
needing approval accumulate. A ``None`` field of a layer does not narrow; an explicit empty list allows
nothing (it is never a fallback to defaults). An empty ``allowed_isolation`` makes every launch impossible.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .commands import CommandMode, CommandPolicy, CommandsLayer, narrow_commands
from .network import NetworkLayer, NetworkPolicy, flatten_hosts, narrow_network
from .operations import OperationName, OperationRule, narrow_rule
from .paths import PathPolicy, PathRule
from .tool_intent import EffectKind

__all__ = [
    "PermissionLayer",
    "PermissionSet",
    "canonical_document",
    "narrow",
    "narrow_all",
    "tool_allowed",
]


@dataclass(frozen=True, slots=True)
class PermissionSet:
    fs_read: tuple[PathPolicy, ...]  # conjunction: allowed when every policy allows
    fs_write: tuple[PathPolicy, ...]
    commands: CommandPolicy
    network: NetworkPolicy
    tools: tuple[frozenset[str], ...]  # conjunction of tool lists
    operations: Mapping[OperationName, OperationRule]  # always all 14 keys
    external_effects: frozenset[EffectKind]
    effects_need_approval: frozenset[EffectKind]
    allowed_isolation: frozenset[str]
    sources: tuple[str, ...]

    def __post_init__(self) -> None:
        missing = set(OperationName) - set(self.operations)
        if missing:
            raise ValueError(f"permission set misses operations {sorted(missing)}")
        object.__setattr__(self, "operations", MappingProxyType(dict(self.operations)))


@dataclass(frozen=True, slots=True)
class PermissionLayer:
    """Profile-shaped narrowing (``urn:skm:policy:permission-layer:v1``); ``None`` fields do not narrow."""

    source: str
    fs_read: PathPolicy | None = None
    fs_write: PathPolicy | None = None
    commands: CommandsLayer | None = None
    network: NetworkLayer | None = None
    tools: frozenset[str] | None = None
    operations: Mapping[OperationName, OperationRule] | None = None
    external_effects: frozenset[EffectKind] | None = None
    effects_need_approval: frozenset[EffectKind] | None = None
    allowed_isolation: frozenset[str] | None = None


def _append[T](items: tuple[T, ...], item: T | None) -> tuple[T, ...]:
    if item is None or item in items:
        return items
    return (*items, item)


def narrow(a: PermissionSet, layer: PermissionLayer) -> PermissionSet:
    operations = dict(a.operations)
    for name, rule in (layer.operations or {}).items():
        operations[name] = narrow_rule(operations[name], rule)
    return PermissionSet(
        fs_read=_append(a.fs_read, layer.fs_read),
        fs_write=_append(a.fs_write, layer.fs_write),
        commands=a.commands if layer.commands is None else narrow_commands(a.commands, layer.commands),
        network=a.network if layer.network is None else narrow_network(a.network, layer.network),
        tools=_append(a.tools, layer.tools),
        operations=operations,
        external_effects=a.external_effects
        if layer.external_effects is None
        else a.external_effects & layer.external_effects,
        effects_need_approval=a.effects_need_approval | (layer.effects_need_approval or frozenset()),
        allowed_isolation=a.allowed_isolation
        if layer.allowed_isolation is None
        else a.allowed_isolation & layer.allowed_isolation,
        sources=(*a.sources, layer.source),
    )


def narrow_all(base: PermissionSet, layers: tuple[PermissionLayer | None, ...]) -> PermissionSet:
    result = base
    for layer in layers:
        if layer is not None:
            result = narrow(result, layer)
    return result


def tool_allowed(tools: tuple[frozenset[str], ...], tool: str) -> bool:
    """Every list allows the tool; wildcards exist only for MCP (``mcp:*``, ``mcp:<server>/*``)."""
    return all(any(_tool_matches(pattern, tool) for pattern in allowed) for allowed in tools)


def _tool_matches(pattern: str, tool: str) -> bool:
    if pattern == tool:
        return True
    if pattern == "mcp:*":
        return tool.startswith("mcp:")
    if pattern.startswith("mcp:") and pattern.endswith("/*"):
        return tool.startswith(pattern[:-1])
    return False


def _rule_doc(rule: PathRule) -> dict[str, object]:
    doc: dict[str, object] = {"scope": rule.scope.value, "pattern": rule.pattern}
    if rule.mount is not None:
        doc["mount"] = rule.mount
    return doc


def _policy_doc(policy: PathPolicy) -> dict[str, object]:
    return {
        "allow": [_rule_doc(rule) for rule in policy.allow],
        "deny": [_rule_doc(rule) for rule in policy.deny],
    }


def canonical_document(perms: PermissionSet) -> dict[str, object]:
    """The permission set without ``sources``, sets sorted: the input of ``permissions_digest`` (§5.12)."""
    commands = perms.commands
    return {
        "fs_read": [_policy_doc(policy) for policy in perms.fs_read],
        "fs_write": [_policy_doc(policy) for policy in perms.fs_write],
        "commands": {
            "mode": commands.mode.value,
            "allow": [
                {
                    "program": rule.program,
                    "subcommands": None if rule.subcommands is None else sorted(rule.subcommands),
                }
                for rule in sorted(commands.allow, key=lambda item: item.program)
            ]
            if commands.mode is CommandMode.ALLOWLIST
            else [],
            "deny_patterns": list(commands.deny_patterns),
            "ask_patterns": list(commands.ask_patterns),
            "inline_interpreters": sorted(commands.inline_interpreters),
            "trust_inline_interpreters": commands.trust_inline_interpreters,
        },
        "network": {"mode": perms.network.mode.value, "hosts": sorted(flatten_hosts(perms.network.hosts))},
        "tools": [sorted(tools) for tools in perms.tools],
        "operations": {
            name.value: {
                "deny": rule.deny,
                "requires": sorted(item.value for item in rule.requires),
                "capabilities": sorted(item.value for item in rule.capabilities),
                "warn": rule.warn,
                "risk": None if rule.risk is None else rule.risk.value,
            }
            for name, rule in sorted(perms.operations.items())
        },
        "external_effects": sorted(item.value for item in perms.external_effects),
        "effects_need_approval": sorted(item.value for item in perms.effects_need_approval),
        "allowed_isolation": sorted(perms.allowed_isolation),
    }
