"""Command policy and its narrowing (policy §§4.2, 4.4).

Strictness ``none > allowlist > denylist``. ``allow`` matters in ``allowlist`` mode: when both sides list
programs the result is their intersection by program, with ``None ∩ S = S`` and ``S ∩ T`` for subcommands;
an empty subcommand intersection removes the program. Patterns and interpreters accumulate (first ``a``,
then the new ones); ``trust_inline_interpreters`` is an AND. A ``CommandRule.program`` is a basename label for
matching and UX, not the identity of a binary (§5.2a).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

__all__ = [
    "COMMAND_MODE_ORDER",
    "CommandMode",
    "CommandPolicy",
    "CommandRule",
    "CommandsLayer",
    "intersect_allow",
    "narrow_commands",
    "stricter_command_mode",
    "subcommand_allowed",
]


class CommandMode(StrEnum):
    NONE = "none"
    ALLOWLIST = "allowlist"
    DENYLIST = "denylist"


COMMAND_MODE_ORDER: dict[CommandMode, int] = {
    CommandMode.DENYLIST: 0,
    CommandMode.ALLOWLIST: 1,
    CommandMode.NONE: 2,
}


@dataclass(frozen=True, slots=True)
class CommandRule:
    program: str
    subcommands: frozenset[str] | None  # None: any; "sub" first positional; "noun:verb" / "*:verb" two (gh)


@dataclass(frozen=True, slots=True)
class CommandPolicy:
    mode: CommandMode
    allow: tuple[CommandRule, ...]
    deny_patterns: tuple[str, ...]
    ask_patterns: tuple[str, ...]
    inline_interpreters: frozenset[str]
    trust_inline_interpreters: bool

    def rule(self, program: str) -> CommandRule | None:
        return next((rule for rule in self.allow if rule.program == program), None)


@dataclass(frozen=True, slots=True)
class CommandsLayer:
    """The command part of a permission layer; ``None`` fields do not narrow."""

    mode: CommandMode | None = None
    allow: tuple[CommandRule, ...] | None = None  # a program list implies an allowlist restriction
    deny_patterns: tuple[str, ...] = ()
    ask_patterns: tuple[str, ...] = ()
    inline_interpreters: frozenset[str] = frozenset()
    trust_inline_interpreters: bool | None = None


def stricter_command_mode(a: CommandMode, b: CommandMode) -> CommandMode:
    return a if COMMAND_MODE_ORDER[a] >= COMMAND_MODE_ORDER[b] else b


def intersect_allow(a: tuple[CommandRule, ...], b: tuple[CommandRule, ...]) -> tuple[CommandRule, ...]:
    """Programs listed on both sides; subcommand sets intersect, an empty intersection drops the program."""
    others = {rule.program: rule for rule in b}
    result: list[CommandRule] = []
    for rule in a:
        other = others.get(rule.program)
        if other is None:
            continue
        if rule.subcommands is None:
            subcommands = other.subcommands
        elif other.subcommands is None:
            subcommands = rule.subcommands
        else:
            subcommands = rule.subcommands & other.subcommands
        if subcommands is None or subcommands:
            result.append(CommandRule(rule.program, subcommands))
    return tuple(result)


def _union[T](first: tuple[T, ...], second: tuple[T, ...]) -> tuple[T, ...]:
    return first + tuple(item for item in dict.fromkeys(second) if item not in first)


def narrow_commands(a: CommandPolicy, layer: CommandsLayer) -> CommandPolicy:
    layer_mode = layer.mode
    layer_allow = layer.allow
    if layer_mode is None and layer_allow is not None:
        layer_mode = CommandMode.ALLOWLIST
    elif layer_mode is CommandMode.ALLOWLIST and layer_allow is None:
        layer_allow = ()
    mode = a.mode if layer_mode is None else stricter_command_mode(a.mode, layer_mode)
    allow = a.allow
    if layer_allow is not None and layer_mode is CommandMode.ALLOWLIST:
        # a denylist carries no program list; under none the list of an earlier allowlist still bounds
        allow = layer_allow if a.mode is CommandMode.DENYLIST else intersect_allow(a.allow, layer_allow)
    trust = a.trust_inline_interpreters
    if layer.trust_inline_interpreters is not None:
        trust = trust and layer.trust_inline_interpreters
    return CommandPolicy(
        mode=mode,
        allow=allow,
        deny_patterns=_union(a.deny_patterns, layer.deny_patterns),
        ask_patterns=_union(a.ask_patterns, layer.ask_patterns),
        inline_interpreters=a.inline_interpreters | layer.inline_interpreters,
        trust_inline_interpreters=trust,
    )


def subcommand_allowed(rule: CommandRule, positionals: tuple[str, ...]) -> bool:
    """``sub`` matches the first positional, ``noun:verb``/``*:verb`` the first two."""
    if rule.subcommands is None:
        return True
    first = positionals[0] if positionals else None
    second = positionals[1] if len(positionals) > 1 else None
    if first is not None and first in rule.subcommands:
        return True
    if first is None or second is None:
        return False
    return f"{first}:{second}" in rule.subcommands or f"*:{second}" in rule.subcommands
