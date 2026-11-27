"""Bound filesystem and command facts for the SAFE_DIRS guard."""

from __future__ import annotations

import posixpath
from dataclasses import replace
from typing import Any

from skm.modules.integrations.domain.hook_events import HookEventKind, NormalizedHookEvent
from skm.modules.integrations.domain.hook_rules import (
    HookPolicyContext,
    safe_dirs_violation,
    safe_shell_words,
)

from .hook_state import HookState

__all__ = ["evaluate_safe_dirs"]


def evaluate_safe_dirs(
    state: HookState,
    event: NormalizedHookEvent,
    root: str,
    mount: str,
    policy: dict[str, Any],
    context: HookPolicyContext,
) -> HookPolicyContext:
    def deny(code: str, message: str | None = None) -> HookPolicyContext:
        return replace(context, safe_verdict="deny", safe_reason=code, safe_message=message)

    cwd = event.cwd or root
    if not posixpath.isabs(cwd):
        return deny("HOOK_PATH_INVALID")
    if event.kind is HookEventKind.PRE_TOOL:
        if not event.paths:
            return deny("HOOK_PATH_INVALID")
        resolved = tuple(state.resolve(path, cwd) for path in event.paths)
        if not all(path.startswith(root.rstrip("/") + "/") for path in resolved):
            return deny("HOOK_PATH_INVALID")
        violation = safe_dirs_violation((*event.paths, *resolved), ())
        return deny(*violation) if violation else context
    if event.kind is HookEventKind.PRE_SHELL:
        return _safe_shell(state, event, root, mount, policy, context, cwd)
    return context


def _safe_shell(
    state: HookState,
    event: NormalizedHookEvent,
    root: str,
    mount: str,
    policy: dict[str, Any],
    context: HookPolicyContext,
    cwd: str,
) -> HookPolicyContext:
    from skm.modules.policy.public import (
        Ask,
        Deny,
        EnforcementMode,
        RunCommand,
        ScopeRoots,
        TaskAuthority,
        check_tool_call,
        permission_set_from_view,
    )

    def deny(code: str, message: str | None = None) -> HookPolicyContext:
        return replace(context, safe_verdict="deny", safe_reason=code, safe_message=message)

    command = event.command or ""
    try:
        words = safe_shell_words(command)
    except ValueError:
        return deny("HOOK_COMMAND_INVALID")
    # Shell arguments may embed a destination in the value of an option or assignment.
    operands = (*words, *(word.partition("=")[2] for word in words if "=" in word))
    resolved = tuple(state.resolve(path, cwd) for path in dict.fromkeys(operands) if path)
    violation = safe_dirs_violation((*operands, *resolved), words)
    if violation:
        return deny(*violation)
    permissions = permission_set_from_view(policy["permissions"])
    result = check_tool_call(
        permissions,
        RunCommand(command, cwd),
        roots=ScopeRoots({mount: root}, None, None, state.home, (), (), frozenset()),
        facts=state.facts(root),
        authority=TaskAuthority(None, (), frozenset(), frozenset()),
        mode=EnforcementMode.INTERACTIVE,
    )
    if isinstance(result, Deny):
        return deny(result.code)
    if isinstance(result, Ask):
        if result.rule in {"unsupported_syntax", "unresolved_path"}:
            return deny("HOOK_COMMAND_INVALID")
        return replace(context, safe_verdict="ask")
    return context
