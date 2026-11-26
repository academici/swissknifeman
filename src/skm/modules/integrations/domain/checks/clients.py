"""Cursor and Codex native configuration checks (integrations §5.6)."""

from __future__ import annotations

import json

from skm.kernel.json_types import JsonObject
from skm.modules.integrations.domain.reports import CheckResult

from .context import DoctorContext, finding, mapping

__all__ = ["CODEX_CHECKS", "CURSOR_CHECKS"]


def _cursor_hooks(ctx: DoctorContext):
    return [
        (str(layer.get("path")), mapping(mapping(layer.get("data")).get("hooks")))
        for layer in ctx.layers
        if layer.get("layer") in ("hooks", "claude_user", "claude_project", "claude_local")
    ]


def _surfaces(hooks: JsonObject) -> set[str]:
    """Compare native and compatibility event names by their shared semantic surface."""
    aliases = {
        "PreToolUse": "pre_tool",
        "preToolUse": "pre_tool",
        "beforeShellExecution": "pre_shell",
        "SessionStart": "session_start",
        "sessionStart": "session_start",
        "Stop": "stop",
        "stop": "stop",
        "PostToolUse": "post_tool",
        "postToolUse": "post_tool",
    }
    surfaces: set[str] = set()
    for event, entries in hooks.items():
        surfaces.add(aliases.get(event, event))
        if event == "PreToolUse" and "Bash" in json.dumps(entries):
            surfaces.add("pre_shell")
    return surfaces


def single_writer_overlap(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    native = set[str]().union(
        *(_surfaces(hooks) for path, hooks in _cursor_hooks(ctx) if path == ".cursor/hooks.json")
    )
    return finding(
        ctx,
        "cursor.single_writer_overlap",
        "warning",
        "Hook surface writers",
        (
            (path, "Native and compatibility hooks both register the same event surface")
            for path, hooks in _cursor_hooks(ctx)
            if path != ".cursor/hooks.json" and native & _surfaces(hooks)
        ),
    )


def duplicate_hook_registrations(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    problems: list[tuple[str | None, str]] = []
    seen: set[tuple[str, str]] = set()
    for path, hooks in _cursor_hooks(ctx):
        for event, entries in hooks.items():
            for entry in entries if isinstance(entries, list) else []:
                key = (event, json.dumps(entry, sort_keys=True))
                if key in seen:
                    problems.append((path, "Duplicate registration for hook event " + event))
                seen.add(key)
    return finding(
        ctx, "cursor.duplicate_hook_registrations", "warning", "Unique hook registrations", problems
    )


def compat_binding_notice(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    return finding(
        ctx,
        "cursor.compat_binding_notice",
        "info",
        "Compatibility hook ownership",
        (
            (path, "Claude compatibility hooks in Cursor are not managed by SKM")
            for path, hooks in _cursor_hooks(ctx)
            if hooks and path != ".cursor/hooks.json"
        ),
    )


def layers_readable(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    return finding(
        ctx,
        "codex.layers_readable",
        "warning",
        "Native TOML layers readable",
        (
            (str(layer.get("path")), "Layer is unreadable or invalid TOML")
            for layer in ctx.layers
            if layer.get("valid") is not True
        ),
    )


def project_overrides_machine_key(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    machine = frozenset(("model_provider", "auth", "notify", "profile", "otel", "telemetry"))
    return finding(
        ctx,
        "codex.project_overrides_machine_key",
        "error",
        "Machine-local settings isolated",
        (
            (str(layer.get("path")), "Project declares machine-local key " + key)
            for layer in ctx.layers
            if layer.get("layer") == "project"
            for key in sorted(mapping(layer.get("data")).keys() & machine)
        ),
    )


def hooks_feature_disabled(ctx: DoctorContext) -> tuple[CheckResult, ...]:
    return finding(
        ctx,
        "codex.hooks_feature_disabled",
        "warning",
        "Native hooks enabled",
        (
            [(".codex/config.toml", "Effective features.hooks=false disables native hooks")]
            if mapping(ctx.effective.get("features")).get("hooks") is False
            else []
        ),
    )


CURSOR_CHECKS = (single_writer_overlap, duplicate_hook_registrations, compat_binding_notice)
CODEX_CHECKS = (layers_readable, project_overrides_machine_key, hooks_feature_disabled)
