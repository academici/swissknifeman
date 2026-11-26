"""Thirteen Claude/editor checks over read-only observations (integrations §5.6).

Native key catalog snapshot: Claude settings, 2026-08-02 (the adapter capability date).
Unknown keys are advisory; they never prevent a native client from reading its configuration.
"""

from __future__ import annotations

import re
import shlex
from collections.abc import Callable, Iterable
from fnmatch import fnmatchcase
from typing import cast

from skm.kernel.errors import ValidationFailed
from skm.kernel.generated._codec import SecretRef
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.integrations.domain.reports import CheckResult

from .context import DoctorContext, finding, mapping, strings

__all__ = ["CHECKS", "hook_commands"]

_TOP_KEYS = frozenset(
    (
        "$schema",
        "permissions",
        "hooks",
        "env",
        "model",
        "language",
        "outputStyle",
        "statusLine",
        "includeCoAuthoredBy",
        "cleanupPeriodDays",
        "disableAllHooks",
        "enabledPlugins",
        "extraKnownMarketplaces",
        "skipDangerousModePermissionPrompt",
        "sandbox",
        "apiKeyHelper",
        "forceLoginMethod",
        "forceLoginOrgUUID",
        "companyAnnouncements",
        "attribution",
        "alwaysThinkingEnabled",
        "plansDirectory",
        "respectGitignore",
        "spinnerVerbs",
        "awsAuthRefresh",
        "awsCredentialExport",
        "mcpServers",
        "enableAllProjectMcpServers",
        "enabledMcpjsonServers",
        "disabledMcpjsonServers",
        "feedbackSurveyState",
    )
)
_PERMISSION_KEYS = frozenset(
    ("allow", "deny", "ask", "defaultMode", "additionalDirectories", "disableBypassPermissionsMode")
)
_SECRET = re.compile(
    r"sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{20,}"
    r"|xox[abp]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16}|Bearer\s+\S{20,}"
)
_SECRET_KEY = re.compile(r"api[_-]?key|token|secret|password", re.IGNORECASE)


def _native(ctx: DoctorContext):
    return (layer for layer in ctx.layers if layer.get("layer") != "vscode")


def _rules(ctx: DoctorContext, kind: str) -> tuple[str, ...]:
    return strings(mapping(ctx.effective.get("permissions")).get(kind))


def _expected(ctx: DoctorContext):
    return mapping(ctx.expected.get("permissions"))


def layer_json_valid(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    return finding(
        ctx,
        "claude.layer_json_valid",
        "error",
        "Settings layers parse",
        (
            (str(layer.get("path")), "Layer is unreadable or invalid JSON")
            for layer in ctx.layers
            if layer.get("valid") is not True
        ),
    )


def noncanonical_keys(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    problems: list[tuple[str | None, str]] = []
    for layer in _native(ctx):
        data = mapping(layer.get("data"))
        keys = [
            *sorted(data.keys() - _TOP_KEYS),
            *(
                f"permissions.{key}"
                for key in sorted(mapping(data.get("permissions")).keys() - _PERMISSION_KEYS)
            ),
        ]
        if keys:
            problems.append((str(layer.get("path")), "Unknown keys: " + ", ".join(keys)))
    return finding(ctx, "claude.noncanonical_keys", "warning", "Native settings keys", problems)


def default_mode_conflict(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    modes = [
        (str(layer.get("path")), mapping(mapping(layer.get("data")).get("permissions")).get("defaultMode"))
        for layer in _native(ctx)
    ]
    distinct = {str(value) for _, value in modes if value is not None}
    return finding(
        ctx,
        "claude.default_mode_conflict",
        "warning",
        "Permission mode precedence",
        (
            (path, "Conflicting permissions.defaultMode declarations; later layer wins")
            for path, value in modes
            if len(distinct) > 1 and value is not None
        ),
    )


def profile_conformance(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    actual = mapping(ctx.effective.get("permissions"))
    problems: list[tuple[str | None, str]] = [
        (None, f"Effective permissions.{key} differs from the projection profile")
        for key, value in _expected(ctx).items()
        if key in ("allow", "deny", "defaultMode") and actual.get(key) != value
    ]
    return finding(ctx, "claude.profile_conformance", "warning", "Projection profile conformance", problems)


def hook_commands(value: object) -> tuple[str, ...]:
    """Find nested native hook commands without evaluating shell text."""
    if isinstance(value, dict):
        doc = cast("JsonObject", value)
        command = doc.get("command")
        own = (command,) if isinstance(command, str) else ()
        return own + tuple(cmd for item in doc.values() for cmd in hook_commands(item))
    if isinstance(value, list):
        return tuple(cmd for item in cast("list[JsonValue]", value) for cmd in hook_commands(item))
    return ()


def hooks_resolvable(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    problems: list[tuple[str | None, str]] = []
    for layer in _native(ctx):
        hooks = mapping(mapping(layer.get("data")).get("hooks"))
        for event, entries in hooks.items():
            if event not in ctx.known_hook_events:
                problems.append((str(layer.get("path")), "Unknown hook event: " + event))
            for command in hook_commands(entries):
                try:
                    argv = shlex.split(command)
                except ValueError:
                    argv = []
                if not argv or argv[0] not in ctx.commands:
                    problems.append((str(layer.get("path")), "Hook executable is not resolvable"))
    return finding(ctx, "claude.hooks_resolvable", "error", "Hook commands resolvable", problems)


def dead_allow_rules(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    allow = _rules(ctx, "allow")
    return finding(
        ctx,
        "claude.dead_allow_rules",
        "info",
        "Redundant allow rules",
        (
            (None, "An exact Bash allow rule is covered by a wildcard allow rule")
            for rule in allow
            if rule.startswith("Bash(")
            and not any(c in rule for c in "*?[")
            and any(
                pattern != rule and "*" in pattern and fnmatchcase(rule, pattern.replace(":*", "*"))
                for pattern in allow
            )
        ),
    )


def allow_deny_overlap(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    return finding(
        ctx,
        "claude.allow_deny_overlap",
        "warning",
        "Allow/deny overlap",
        (
            (None, "The same permission rule appears in allow and deny")
            for _ in set(_rules(ctx, "allow")) & set(_rules(ctx, "deny"))
        ),
    )


def additional_dirs_missing(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    paths = strings(mapping(ctx.effective.get("permissions")).get("additionalDirectories"))
    return finding(
        ctx,
        "claude.additional_dirs_missing",
        "warning",
        "Additional directories exist",
        (
            (
                path,
                "Additional directory is missing"
                if ctx.directories.get(path) is False
                else "Additional directory could not be observed",
            )
            for path in paths
            if ctx.directories.get(path) is not True
        ),
    )


def secrets_in_env(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    problems: list[tuple[str | None, str]] = []
    for layer in _native(ctx):
        for key, value in mapping(mapping(layer.get("data")).get("env")).items():
            if not isinstance(value, str):
                continue
            if value.startswith("secret:"):
                try:
                    SecretRef.parse(value)
                except ValidationFailed:
                    pass
                else:
                    continue
            if _SECRET.search(value) or (_SECRET_KEY.search(key) and len(value) >= 8):
                problems.append((str(layer.get("path")), "Secret-like env value at key " + key))
    return finding(
        ctx,
        "claude.secrets_in_env",
        "error",
        "No secrets in env",
        problems,
        "Use a secret reference instead of storing credentials in client settings",
    )


def bypass_without_skip_dialog(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    bypass = mapping(ctx.effective.get("permissions")).get("defaultMode") == "bypassPermissions"
    return finding(
        ctx,
        "claude.bypass_without_skip_dialog",
        "warning",
        "Bypass dialog configured",
        (
            [(None, "Bypass mode has no skipDangerousModePermissionPrompt=true")]
            if bypass and ctx.effective.get("skipDangerousModePermissionPrompt") is not True
            else []
        ),
    )


def ask_rules_expected_empty(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    return finding(
        ctx,
        "claude.ask_rules_expected_empty",
        "info",
        "Profile ask rules",
        (
            [(None, "Projection profile expects an empty ask list")]
            if _expected(ctx).get("ask") == [] and _rules(ctx, "ask")
            else []
        ),
    )


def _editor(ctx: DoctorContext) -> JsonObject:
    return next(
        (mapping(layer.get("data")) for layer in ctx.layers if layer.get("layer") == "vscode"),
        dict[str, JsonValue](),
    )


def initial_mode_mismatch(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    mode = _editor(ctx).get("claudeCode.initialPermissionMode")
    actual = mapping(ctx.effective.get("permissions")).get("defaultMode", "default")
    return finding(
        ctx,
        "vscode.initial_mode_mismatch",
        "warning",
        "Editor permission mode",
        (
            [("~/.config/Code/User/settings.json", "Editor initial mode differs from effective defaultMode")]
            if mode is not None and mode != actual
            else []
        ),
    )


def bypass_toggle_missing(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    bypass = mapping(ctx.effective.get("permissions")).get("defaultMode") == "bypassPermissions"
    return finding(
        ctx,
        "vscode.bypass_toggle_missing",
        "info",
        "Editor bypass toggle",
        (
            [("~/.config/Code/User/settings.json", "Editor bypass toggle is absent or disabled")]
            if bypass and _editor(ctx).get("claudeCode.allowDangerouslySkipPermissions") is not True
            else []
        ),
    )


CHECKS: tuple[Callable[[DoctorContext], Iterable[CheckResult]], ...] = (
    layer_json_valid,
    noncanonical_keys,
    default_mode_conflict,
    profile_conformance,
    hooks_resolvable,
    dead_allow_rules,
    allow_deny_overlap,
    additional_dirs_missing,
    secrets_in_env,
    bypass_without_skip_dialog,
    ask_rules_expected_empty,
    initial_mode_mismatch,
    bypass_toggle_missing,
)
