"""Codex hook registrations, payload normalization, and decision rendering (integrations §4.7, §4.8, §5.5)."""

from __future__ import annotations

import posixpath
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Final, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ProjectId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.integrations.domain.hook_events import (
    HookClass,
    HookEventKind,
    HookSurfaceId,
    NormalizedHookEvent,
)
from skm.modules.integrations.domain.hook_rules import HookDecision, HookMode, HookVerdict
from skm.modules.integrations.domain.target import Surface, TargetId

if TYPE_CHECKING:
    from skm.modules.integrations.domain.contracts import HookOutput, SourceRef
    from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs

__all__ = [
    "CODEX_HOOKS_PATH",
    "CODEX_HOOKS_RENDERER",
    "CODEX_HOOK_EVENTS",
    "MAX_PROMPT_BYTES",
    "build_hook_command",
    "normalize_hook_payload",
    "render_hook_decision",
    "render_hook_entries",
    "render_hooks",
]

CODEX_HOOKS_PATH: Final[str] = ".codex/hooks.json"
CODEX_HOOKS_RENDERER: Final[str] = "codex.hooks@1"
MAX_PROMPT_BYTES: Final[int] = 4096

CODEX_HOOK_EVENTS: Final[tuple[str, ...]] = (
    "PreToolUse",
    "PostToolUse",
    "PermissionRequest",
    "UserPromptSubmit",
    "SubagentStop",
    "Stop",
    "SessionStart",
    "SessionEnd",
)

_SURFACE_BINDINGS_ORDER: Final[tuple[tuple[HookSurfaceId, tuple[tuple[str, str | None], ...]], ...]] = (
    (HookSurfaceId.GIT_GUARDRAILS, (("PreToolUse", "^Bash$"),)),
    (HookSurfaceId.SAFE_DIRS, (("PreToolUse", "^Bash$"),)),
    (HookSurfaceId.PLAN_GUARD, (("PreToolUse", "^apply_patch$"),)),
    (HookSurfaceId.PACK_GUARD, (("PreToolUse", "^apply_patch$"),)),
    (HookSurfaceId.CHANGELOG_GATE, (("PreToolUse", "^Bash$"),)),
    (HookSurfaceId.REVIEW_GATE, (("PreToolUse", "^Bash$"), ("SubagentStop", None))),
    (HookSurfaceId.COMMAND_LOG, (("PreToolUse", "^Bash$"),)),
    (HookSurfaceId.SESSION_CONTEXT, (("SessionStart", "startup|resume|clear|compact"),)),
    (HookSurfaceId.RUN_REPORT, (("SessionEnd", None),)),
)

_SUBSCRIPTION_EVENT_BINDINGS: Final[Mapping[HookEventKind, tuple[str, str | None]]] = {
    HookEventKind.SESSION_START: ("SessionStart", "startup|resume|clear|compact"),
    HookEventKind.SESSION_END: ("SessionEnd", None),
    HookEventKind.USER_PROMPT: ("UserPromptSubmit", None),
    HookEventKind.PRE_SHELL: ("PreToolUse", "^Bash$"),
    HookEventKind.PRE_TOOL: ("PreToolUse", "^apply_patch$"),
    HookEventKind.POST_TOOL: ("PostToolUse", None),
    HookEventKind.PERMISSION_REQUEST: ("PermissionRequest", None),
    HookEventKind.SUBAGENT_STOP: ("SubagentStop", None),
    HookEventKind.STOP: ("Stop", None),
}

_SURFACE_LOOKUP: Final[Mapping[str, HookSurfaceId]] = {
    **{sid.value.rpartition(".")[2]: sid for sid in HookSurfaceId},
    **{sid.value: sid for sid in HookSurfaceId},
}

_PATCH_FILE_PREFIXES: Final[tuple[str, ...]] = (
    "*** Update File:",
    "*** Add File:",
    "*** Delete File:",
    "*** Move to:",
)


def build_hook_command(
    client_event: str,
    surface: HookSurfaceId,
    project_id: ProjectId,
    *,
    hook_class: HookClass | None = None,
) -> str:
    """Format the canonical ``skm-hook`` command line for a Codex hook entry."""
    if hook_class is not None:
        return (
            f"skm-hook {client_event} --target {TargetId.CODEX.value}"
            f" --surface {surface.value} --class {hook_class.value} --project {project_id}"
        )
    return (
        f"skm-hook {client_event} --target {TargetId.CODEX.value}"
        f" --surface {surface.value} --project {project_id}"
    )


def _hook_entry(matcher: str | None, command: str) -> JsonObject:
    inner: list[JsonValue] = [{"type": "command", "command": command}]
    if matcher is not None:
        return {"matcher": matcher, "hooks": inner}
    return {"hooks": inner}


def _resolve_modes(
    raw_modes: Mapping[HookSurfaceId, HookMode] | Mapping[object, object],
) -> dict[HookSurfaceId, HookMode]:
    resolved: dict[HookSurfaceId, HookMode] = {}
    for raw_key, raw_val in raw_modes.items():
        sid = raw_key if isinstance(raw_key, HookSurfaceId) else _SURFACE_LOOKUP.get(str(raw_key))
        if sid is None:
            continue
        mode = raw_val if isinstance(raw_val, HookMode) else HookMode(str(raw_val))
        resolved[sid] = mode
    return resolved


def render_hook_entries(inputs: ProjectionInputs) -> dict[str, list[JsonObject]]:
    """Build SKM-tagged hook entries grouped by Codex hook event name."""
    modes = _resolve_modes(inputs.hook_modes)
    by_event: dict[str, list[JsonObject]] = {}

    for surface_id, bindings in _SURFACE_BINDINGS_ORDER:
        mode = modes.get(surface_id, HookMode.OFF)
        if mode is HookMode.OFF:
            continue
        for client_event, matcher in bindings:
            cmd = build_hook_command(client_event, surface_id, inputs.project_id)
            by_event.setdefault(client_event, []).append(_hook_entry(matcher, cmd))

    for sub_event in inputs.host_subscription_events:
        mapped = _SUBSCRIPTION_EVENT_BINDINGS.get(sub_event.kind)
        if mapped is None:
            continue
        client_event, matcher = mapped
        for hook_cls in sub_event.classes:
            cmd = build_hook_command(
                client_event,
                HookSurfaceId.SUBSCRIPTIONS,
                inputs.project_id,
                hook_class=hook_cls,
            )
            by_event.setdefault(client_event, []).append(_hook_entry(matcher, cmd))

    return by_event


def render_hooks(inputs: ProjectionInputs) -> DesiredFile | None:
    """Render ``.codex/hooks.json`` with ``list_union_tagged`` ownership per event."""
    from skm.adapters.integrations._render import json_doc
    from skm.modules.integrations.domain.desired import DesiredFile
    from skm.modules.integrations.domain.merged_json import OwnedKeyPath, extract_owned
    from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged

    entries = render_hook_entries(inputs)
    if not entries:
        return None

    raw_doc: dict[str, Any] = {
        "hooks": {ev: entries[ev] for ev in CODEX_HOOK_EVENTS if ev in entries},
    }
    owned_keys = tuple(OwnedKeyPath(("hooks", ev), "list_union_tagged") for ev in CODEX_HOOK_EVENTS)
    boundary = ManagedBoundary(Ownership.MERGED_JSON, owned_keys=owned_keys)
    canonical_doc = extract_owned(raw_doc, boundary.owned_keys)
    managed_bytes = json_doc.dumps_bytes(canonical_doc)
    refs: list[SourceRef] = [{"kind": "hooks", "key": "integrations.hooks.mode"}]
    if inputs.host_subscription_events:
        refs.append({"kind": "hooks", "key": "hooks.subscriptions"})
    return DesiredFile(
        target=TargetId.CODEX,
        surface=Surface.HOOKS,
        relative_path=CODEX_HOOKS_PATH,
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=tuple(refs),
        renderer=CODEX_HOOKS_RENDERER,
    )


def _invalid_payload(message: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(ErrorCode.HOOK_PAYLOAD_INVALID, message, details=dict(details))


def _require_nonempty_str(payload: Mapping[str, JsonValue], field: str, event_name: str) -> str:
    val = payload.get(field)
    if not isinstance(val, str) or not val.strip():
        raise _invalid_payload(
            f"Codex hook {event_name!r} payload requires non-empty string field {field!r}",
            event_name=event_name,
            field=field,
        )
    return val


def _truncate_utf8(text: str, max_bytes: int) -> str:
    encoded = text.encode("utf-8")
    if len(encoded) <= max_bytes:
        return text
    return encoded[:max_bytes].decode("utf-8", errors="ignore")


def _relativize_path(raw_path: str, cwd: str) -> str:
    if not cwd or not raw_path.startswith("/"):
        return raw_path
    norm_cwd = posixpath.normpath(cwd)
    norm_path = posixpath.normpath(raw_path)
    if norm_path == norm_cwd:
        return "."
    prefix = "/" if norm_cwd == "/" else f"{norm_cwd}/"
    if norm_path.startswith(prefix):
        return norm_path[len(prefix) :]
    return raw_path


def _extract_apply_patch_paths(
    tool_input: Mapping[str, JsonValue], cwd: str, event_name: str
) -> tuple[str, ...]:
    raw_patch = tool_input.get("input")
    if raw_patch is None:
        raw_patch = tool_input.get("patch")
    if not isinstance(raw_patch, str) or not raw_patch.strip():
        raise _invalid_payload(
            f"Codex hook {event_name!r} for apply_patch requires non-empty string tool_input.input",
            event_name=event_name,
            tool_name="apply_patch",
        )

    found: list[str] = []
    for raw_line in raw_patch.splitlines():
        for prefix in _PATCH_FILE_PREFIXES:
            if raw_line.startswith(prefix):
                candidate = raw_line[len(prefix) :].strip()
                if not candidate or "\x00" in candidate:
                    raise _invalid_payload(
                        f"Codex hook {event_name!r} apply_patch header has empty or invalid path",
                        event_name=event_name,
                        tool_name="apply_patch",
                    )
                rel = _relativize_path(candidate, cwd)
                if rel not in found:
                    found.append(rel)
                break

    if not found:
        raise _invalid_payload(
            f"Codex hook {event_name!r} apply_patch payload contains no file headers",
            event_name=event_name,
            tool_name="apply_patch",
        )
    return tuple(found)


def _normalize_tool_event(
    event_name: str,
    raw_tool: str,
    tool_input: Mapping[str, JsonValue],
    cwd: str,
) -> tuple[HookEventKind, str, str | None, tuple[str, ...]]:
    if raw_tool == "Bash":
        cmd = tool_input.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            raise _invalid_payload(
                f"Codex hook {event_name!r} for Bash requires non-empty tool_input.command",
                event_name=event_name,
                tool_name=raw_tool,
            )
        if event_name == "PostToolUse":
            kind = HookEventKind.POST_TOOL
        elif event_name == "PermissionRequest":
            kind = HookEventKind.PERMISSION_REQUEST
        else:
            kind = HookEventKind.PRE_SHELL
        return kind, "shell", cmd, ()

    base_kind = (
        HookEventKind.POST_TOOL
        if event_name == "PostToolUse"
        else HookEventKind.PERMISSION_REQUEST
        if event_name == "PermissionRequest"
        else HookEventKind.PRE_TOOL
    )

    if raw_tool == "apply_patch":
        paths = _extract_apply_patch_paths(tool_input, cwd, event_name)
        return base_kind, "apply_patch", None, paths

    if raw_tool in ("Task", "Agent"):
        return base_kind, "task", None, ()

    if raw_tool.startswith("mcp__"):
        parts = raw_tool.split("__", 2)
        if len(parts) == 3 and parts[1] and parts[2]:
            return base_kind, f"mcp:{parts[1]}:{parts[2]}", None, ()
        raise _invalid_payload(
            f"Malformed Codex MCP tool name {raw_tool!r}",
            event_name=event_name,
            tool_name=raw_tool,
        )

    fp = tool_input.get("file_path") or tool_input.get("path")
    extra_paths = (_relativize_path(fp, cwd),) if isinstance(fp, str) and fp.strip() else ()
    return base_kind, raw_tool.lower(), None, extra_paths


def normalize_hook_payload(event_name: str, payload: Mapping[str, JsonValue]) -> NormalizedHookEvent:
    """Normalize a raw Codex hook JSON payload into ``NormalizedHookEvent`` (integrations §4.7)."""
    if not isinstance(cast("object", payload), Mapping):
        raise _invalid_payload("Codex hook payload must be a JSON object", event_name=event_name)
    if event_name not in CODEX_HOOK_EVENTS:
        raise _invalid_payload(f"Unsupported Codex hook event {event_name!r}", event_name=event_name)

    session_id = _require_nonempty_str(payload, "session_id", event_name)
    cwd = _require_nonempty_str(payload, "cwd", event_name)
    declared_event = _require_nonempty_str(payload, "hook_event_name", event_name)
    if declared_event != event_name:
        raise _invalid_payload(
            f"hook_event_name {declared_event!r} does not match invoked event {event_name!r}",
            event_name=event_name,
        )
    _require_nonempty_str(payload, "model", event_name)
    _require_nonempty_str(payload, "source", event_name)

    if event_name == "SessionStart":
        _require_nonempty_str(payload, "permission_mode", event_name)
        return NormalizedHookEvent(
            target=TargetId.CODEX,
            kind=HookEventKind.SESSION_START,
            session_id=session_id,
            cwd=cwd,
            tool_name=None,
            command=None,
            paths=(),
            prompt=None,
            stop_status=None,
            raw_event_name=event_name,
        )

    if event_name == "UserPromptSubmit":
        raw_prompt = payload.get("prompt")
        if not isinstance(raw_prompt, str):
            raise _invalid_payload(
                "Codex hook 'UserPromptSubmit' payload requires string field 'prompt'",
                event_name=event_name,
                field="prompt",
            )
        return NormalizedHookEvent(
            target=TargetId.CODEX,
            kind=HookEventKind.USER_PROMPT,
            session_id=session_id,
            cwd=cwd,
            tool_name=None,
            command=None,
            paths=(),
            prompt=_truncate_utf8(raw_prompt, MAX_PROMPT_BYTES),
            stop_status=None,
            raw_event_name=event_name,
        )

    if event_name in ("PreToolUse", "PostToolUse", "PermissionRequest"):
        raw_tool = _require_nonempty_str(payload, "tool_name", event_name)
        raw_input = payload.get("tool_input")
        if not isinstance(raw_input, Mapping):
            raise _invalid_payload(
                f"Codex hook {event_name!r} payload requires object field 'tool_input'",
                event_name=event_name,
                field="tool_input",
            )
        kind, norm_tool, command, paths = _normalize_tool_event(
            event_name, raw_tool, cast("Mapping[str, JsonValue]", raw_input), cwd
        )
        return NormalizedHookEvent(
            target=TargetId.CODEX,
            kind=kind,
            session_id=session_id,
            cwd=cwd,
            tool_name=norm_tool,
            command=command,
            paths=paths,
            prompt=None,
            stop_status=None,
            raw_event_name=event_name,
        )

    if event_name == "SubagentStop":
        _require_nonempty_str(payload, "agent_type", event_name)
        stop_active = payload.get("stop_hook_active")
        if stop_active is not None and not isinstance(stop_active, bool):
            raise _invalid_payload(
                "Codex hook 'SubagentStop' field 'stop_hook_active' must be boolean when present",
                event_name=event_name,
                field="stop_hook_active",
            )
        sub_status = None if stop_active is None else ("active" if stop_active else "idle")
        return NormalizedHookEvent(
            target=TargetId.CODEX,
            kind=HookEventKind.SUBAGENT_STOP,
            session_id=session_id,
            cwd=cwd,
            tool_name=None,
            command=None,
            paths=(),
            prompt=None,
            stop_status=sub_status,
            raw_event_name=event_name,
        )

    if event_name == "Stop":
        stop_active = payload.get("stop_hook_active")
        if not isinstance(stop_active, bool):
            raise _invalid_payload(
                "Codex hook 'Stop' payload requires boolean field 'stop_hook_active'",
                event_name=event_name,
                field="stop_hook_active",
            )
        last_msg = payload.get("last_assistant_message")
        if not isinstance(last_msg, str):
            raise _invalid_payload(
                "Codex hook 'Stop' payload requires string field 'last_assistant_message'",
                event_name=event_name,
                field="last_assistant_message",
            )
        return NormalizedHookEvent(
            target=TargetId.CODEX,
            kind=HookEventKind.STOP,
            session_id=session_id,
            cwd=cwd,
            tool_name=None,
            command=None,
            paths=(),
            prompt=None,
            stop_status="active" if stop_active else "idle",
            raw_event_name=event_name,
        )

    reason = _require_nonempty_str(payload, "reason", event_name)
    return NormalizedHookEvent(
        target=TargetId.CODEX,
        kind=HookEventKind.SESSION_END,
        session_id=session_id,
        cwd=cwd,
        tool_name=None,
        command=None,
        paths=(),
        prompt=None,
        stop_status=reason,
        raw_event_name=event_name,
    )


def render_hook_decision(event: NormalizedHookEvent, decision: HookDecision) -> HookOutput:
    """Render a Codex decision using the native protocol for the event."""
    if event.raw_event_name == "PermissionRequest" and decision.verdict in (
        HookVerdict.DENY,
        HookVerdict.ASK,
    ):
        message = decision.user_message or decision.agent_message or decision.reason_code or "Denied by SKM"
        return {
            "exit_code": 0,
            "stdout": {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {"behavior": "deny", "message": message},
                }
            },
            "stderr": "",
        }
    if decision.verdict is HookVerdict.DENY:
        msg = (
            decision.agent_message
            or decision.user_message
            or decision.reason_code
            or f"skm hook {decision.surface.value}: deny"
        )
        return {"exit_code": 2, "stdout": "", "stderr": msg}

    if decision.verdict is HookVerdict.ASK:
        base = (
            decision.agent_message
            or decision.user_message
            or decision.reason_code
            or f"skm hook {decision.surface.value}: ask"
        )
        msg = base if base.endswith("(confirmation required)") else f"{base} (confirmation required)"
        return {"exit_code": 2, "stdout": "", "stderr": msg}

    if decision.verdict is HookVerdict.CONTEXT:
        text = (
            decision.additional_context
            if decision.additional_context is not None
            else (decision.agent_message or decision.user_message or "")
        )
        if not text:
            return {"exit_code": 0, "stdout": "", "stderr": ""}
        return {
            "exit_code": 0,
            "stdout": {
                "hookSpecificOutput": {
                    "hookEventName": event.raw_event_name,
                    "additionalContext": text,
                }
            },
            "stderr": "",
        }

    return {"exit_code": 0, "stdout": "", "stderr": ""}
