"""Tool calls, decisions and ``check_tool_call`` (policy §§5.3, 5.3a).

Every step of §5.3 runs and records its decision; the result is the first ``Deny`` in step order, else the
first ``Ask``, else ``Allow`` with the collected warnings. An unattended agent cannot answer a question, so
``Ask`` becomes ``Deny(approval_unavailable_unattended)`` keeping the original rule. A line outside the
supported shell subset asks (``unsupported_syntax``) while every deny check still runs. Warnings are never
dropped and never turn a deny into an allow. The check is a preflight; it does not replace isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import StrEnum

from .allowlist import segment_allowlisted
from .calls import (
    FileRead,
    McpCall,
    RunCommand,
    ToolCall,
    WebAccess,
    tool_name,
)
from .classify import Classification, classify
from .command_classes import INLINE_FLAGS, is_carrier
from .commands import CommandMode, CommandPolicy
from .network import NetworkMode
from .operations import PathFacts, TaskAuthority, evaluate_operation
from .paths import PathPolicy, PathScope, ScopeRoots, classify_path, is_protected
from .permission_set import PermissionSet, tool_allowed
from .rm_guard import rm_is_safe
from .shell_scan import ShellScan, scan
from .shell_words import SimpleCommand, parse
from .tool_intent import EffectKind, EnforcementMode

__all__ = [
    "DECISION_CODES",
    "Allow",
    "Ask",
    "DecisionOutcome",
    "Deny",
    "EnforcementMode",
    "ToolDecision",
    "check_tool_call",
    "write_roots",
]

DECISION_CODES = frozenset(
    {
        "tool_not_allowed",
        "path_protected",
        "path_outside_scope",
        "path_denied",
        "commands_disabled",
        "command_denied",
        "rm_outside_write_scope",
        "operation_denied",
        "requires_intent",
        "requires_task_authority",
        "capability_not_granted",
        "network_denied",
        "approval_unavailable_unattended",
    }
)


class DecisionOutcome(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"
    WARN = "warn"


@dataclass(frozen=True, slots=True)
class Allow:
    warnings: tuple[str, ...] = ()
    allowlisted: bool = False


@dataclass(frozen=True, slots=True)
class Ask:
    rule: str
    reason: str


@dataclass(frozen=True, slots=True)
class Deny:
    code: str
    rule: str
    reason: str


type ToolDecision = Allow | Ask | Deny


@dataclass(slots=True)
class _Decisions:
    denies: list[Deny] = field(default_factory=list[Deny])
    asks: list[Ask] = field(default_factory=list[Ask])
    warnings: list[str] = field(default_factory=list[str])

    def deny(self, code: str, rule: str, reason: str) -> None:
        self.denies.append(Deny(code, rule, reason))

    def ask(self, rule: str, reason: str) -> None:
        self.asks.append(Ask(rule, reason))

    def result(self, *, allowlisted: bool) -> ToolDecision:
        if self.denies:
            return self.denies[0]
        if self.asks:
            return self.asks[0]
        return Allow(tuple(dict.fromkeys(self.warnings)), allowlisted)


def write_roots(perms: PermissionSet, roots: ScopeRoots) -> tuple[str, ...]:
    """Roots of the scopes where every ``fs_write`` policy allows ``**`` (the ``rm`` roots of C4)."""

    def everywhere(scope: PathScope, mount: str | None = None) -> bool:
        return bool(perms.fs_write) and all(
            any(
                rule.scope is scope and rule.pattern == "**" and rule.mount in {None, mount}
                for rule in policy.allow
            )
            for policy in perms.fs_write
        )

    result = [root for mount, root in roots.worktrees.items() if everywhere(PathScope.WORKTREE, mount)]
    single = (
        (PathScope.MATERIALS, roots.materials),
        (PathScope.TMP, roots.tmp),
        (PathScope.HOME, roots.home),
    )
    result.extend(root for scope, root in single if root is not None and everywhere(scope))
    result.extend(root for root in roots.safe_dirs if everywhere(PathScope.SAFE_DIR))
    return tuple(result)


def _paths(decisions: _Decisions, policies: tuple[PathPolicy, ...], path: str, roots: ScopeRoots) -> None:
    """F1/F2: every policy of the conjunction allows the resolved path."""
    scoped = classify_path(path, roots)
    for policy in policies:
        if policy.allows(scoped):
            continue
        if scoped.scope is PathScope.ANY and not policy.allows_scope(PathScope.ANY):
            decisions.deny("path_outside_scope", path, f"{path} is outside every allowed scope")
        else:
            decisions.deny("path_denied", path, f"{path} is not allowed in scope {scoped.scope}")
        return


def _empty_write_scope(
    decisions: _Decisions, paths: tuple[str, ...], roots: ScopeRoots, authority: TaskAuthority
) -> None:
    if authority.write_scope == ():
        for path in paths:
            if classify_path(path, roots).scope is PathScope.WORKTREE:
                decisions.deny("path_denied", path, "the task declares an empty write scope")


def _protected(decisions: _Decisions, paths: tuple[str, ...], roots: ScopeRoots) -> None:
    for path in paths:
        if is_protected(path, roots):
            decisions.deny("path_protected", path, f"{path} is SKM state")


def _external_writes(decisions: _Decisions, paths: tuple[str, ...], roots: ScopeRoots) -> None:
    for path in paths:
        if classify_path(path, roots).scope in {PathScope.ANY, PathScope.HOME, PathScope.SAFE_DIR}:
            decisions.deny(
                "requires_intent",
                EffectKind.FS_WRITE_EXTERNAL.value,
                "external writes require the trusted host",
            )
            return


def _operations(
    decisions: _Decisions, perms: PermissionSet, found: Classification, authority: TaskAuthority
) -> None:
    for hit in found.hits:
        outcome = evaluate_operation(perms.operations[hit.operation], hit, authority)
        if outcome.outcome == "deny":
            decisions.deny(outcome.code, hit.operation.value, outcome.reason)
        elif outcome.outcome == "ask":
            decisions.ask(hit.operation.value, f"{outcome.reason}: {hit.subject}")
        elif outcome.warn:
            decisions.warnings.append(hit.operation.value)


def _network(decisions: _Decisions, perms: PermissionSet, found: Classification) -> None:
    """N1; remote and forge hosts are only hints for the destination, never exceptions from any list."""
    network = perms.network
    for target in found.network:
        if network.mode is NetworkMode.NONE:
            decisions.deny("network_denied", target.host or "network", "network is disabled")
        elif network.mode is NetworkMode.ANY:
            continue
        elif target.host is None:
            decisions.ask("network_unresolved", f"destination of {target.subject!r} is unknown")
        elif not network.allows(target.host, target.port):
            decisions.deny("network_denied", target.host, f"{target.host} is not in every host allowlist")


def _patterns(patterns: tuple[str, ...], texts: tuple[str, ...]) -> int | None:
    for index, pattern in enumerate(patterns):
        if any(re.search(pattern, text) for text in texts):
            return index
    return None


def _head_texts(words: tuple[SimpleCommand, ...] | None) -> tuple[str, ...]:
    """Wrappers and program of each command as the shell reads them: ``'kill' 1`` runs what ``kill 1`` runs,
    while the visible text hides a quoted word. Arguments stay out: ``echo 'sudo'`` only prints a word."""
    return tuple(" ".join((*command.wrappers, command.program)) for command in words or ())


def _inline(commands: CommandPolicy, words: tuple[SimpleCommand, ...]) -> SimpleCommand | None:
    for command in words:
        head = command.head
        family = "python" if head.startswith("python") else head
        listed = head in commands.inline_interpreters or (
            family == "python" and any(name.startswith("python") for name in commands.inline_interpreters)
        )
        flags = INLINE_FLAGS.get(family, frozenset())
        if listed and any(arg in flags or arg.split("=", 1)[0] in flags for arg in command.argv[1:]):
            return command
    return None


def _command_asks(
    decisions: _Decisions,
    commands: CommandPolicy,
    shell: ShellScan,
    texts: tuple[str, ...],
    words: tuple[SimpleCommand, ...] | None,
) -> bool:
    """C5-C8 against ``commands``; returns whether every segment is allowlisted (C8)."""
    allowlist = commands.mode is CommandMode.ALLOWLIST
    if allowlist and words is not None and not commands.trust_inline_interpreters:
        inline = _inline(commands, words)
        if inline is not None:
            decisions.ask("inline_interpreter", f"{inline.head} runs inline code")
    if allowlist and shell.dynamic:
        decisions.ask("dynamic_construct", "the command computes part of itself at run time")
    index = _patterns(commands.ask_patterns, texts)
    if index is not None:
        decisions.ask(f"ask:{index}", f"matches ask pattern {index}")
    listed = words is not None and all(segment_allowlisted(segment, commands) for segment in words)
    if allowlist and not listed:
        decisions.ask("not_allowlisted", "a command is not on the allowlist")
    return listed


def _reference_allowlisted(
    reference: CommandPolicy | None,
    shell: ShellScan,
    texts: tuple[str, ...],
    words: tuple[SimpleCommand, ...] | None,
) -> bool:
    """``allowlisted`` outside allowlist mode: the line passes C3, C5-C8 of the built-in read-only data."""
    if reference is None or words is None:
        return False
    probe = _Decisions()
    if _patterns(reference.deny_patterns, texts) is not None:
        return False
    listed = _command_asks(probe, reference, shell, texts, words)
    return listed and not probe.asks


def _run_command(
    decisions: _Decisions,
    perms: PermissionSet,
    call: RunCommand,
    roots: ScopeRoots,
    facts: PathFacts,
    authority: TaskAuthority,
    reference: CommandPolicy | None,
) -> bool:
    commands = perms.commands
    shell = scan(call.command)
    parsed = parse(call.command)
    words = parsed.commands if parsed.supported else None
    if words is None:
        decisions.ask("unsupported_syntax", parsed.error or "unsupported shell syntax")
    found = classify(call, roots=roots, facts=facts, authority=authority, words=words)
    _protected(decisions, found.paths, roots)
    if commands.mode is CommandMode.NONE:
        decisions.deny("commands_disabled", "C1", "commands are disabled")
    carriers = words is None or any(is_carrier(command.head) for command in words)
    texts = (
        *((shell.visible_text, call.command) if carriers else (shell.visible_text,)),
        *_head_texts(words),
    )
    index = _patterns(commands.deny_patterns, texts)
    if index is not None:
        decisions.deny("command_denied", f"deny:{index}", f"matches deny pattern {index}")
    cwd = facts.resolve(call.cwd, "/")
    if not rm_is_safe(
        call.command, cwd, write_roots(perms, roots), roots.protected, roots.home, resolve=facts.resolve
    ):
        decisions.deny("rm_outside_write_scope", "C4", "a deletion leaves the write scope")
    for path in found.writes:
        _paths(decisions, perms.fs_write, path, roots)
    _empty_write_scope(decisions, found.writes, roots, authority)
    _external_writes(decisions, found.writes, roots)
    for rule, reason in found.asks:
        decisions.ask(rule, reason)
    _operations(decisions, perms, found, authority)
    _network(decisions, perms, found)
    listed = _command_asks(decisions, commands, shell, texts, words)
    if commands.mode is CommandMode.ALLOWLIST:
        return listed
    return _reference_allowlisted(reference, shell, texts, words)


def check_tool_call(
    perms: PermissionSet,
    call: ToolCall,
    *,
    roots: ScopeRoots,
    facts: PathFacts,
    authority: TaskAuthority,
    mode: EnforcementMode,
    reference: CommandPolicy | None = None,
) -> ToolDecision:
    """§5.3; ``reference`` is the command policy of the built-in ``read-only`` profile (``allowlisted``
    of step R)."""
    decisions = _Decisions()
    tool = tool_name(call)
    allowlisted = False
    if not tool_allowed(perms.tools, tool):
        decisions.deny("tool_not_allowed", tool, f"tool {tool} is not allowed")
    elif isinstance(call, RunCommand):
        allowlisted = _run_command(decisions, perms, call, roots, facts, authority, reference)
    elif isinstance(call, WebAccess):
        if call.tool == "web.search" and perms.network.mode is NetworkMode.NONE:
            decisions.deny("network_denied", "web.search", "network is disabled")
        _network(decisions, perms, classify(call, roots=roots, facts=facts, authority=authority, words=None))
    elif not isinstance(call, McpCall):
        found = classify(call, roots=roots, facts=facts, authority=authority, words=None)
        _protected(decisions, found.paths, roots)
        policies = perms.fs_read if isinstance(call, FileRead) else perms.fs_write
        for path in found.paths:
            _paths(decisions, policies, path, roots)
        if not isinstance(call, FileRead):
            _empty_write_scope(decisions, found.writes, roots, authority)
            _external_writes(decisions, found.writes, roots)
        _operations(decisions, perms, found, authority)
    decision = decisions.result(allowlisted=allowlisted)
    if isinstance(decision, Ask) and mode is EnforcementMode.AGENT_UNATTENDED:
        return Deny("approval_unavailable_unattended", decision.rule, decision.reason)
    return decision
