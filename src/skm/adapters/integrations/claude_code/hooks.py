"""Claude Code hook registrations, payload normalization, and decision rendering (integrations §4.7, §5.5)."""

from __future__ import annotations

import posixpath
from collections.abc import Mapping, Sequence
from typing import TYPE_CHECKING, Final, cast

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
from skm.modules.integrations.domain.hook_rules import ENFORCEMENT, HookDecision, HookMode, HookVerdict
from skm.modules.integrations.domain.target import TargetId

if TYPE_CHECKING:
    from skm.modules.integrations.domain.contracts import HookOutput
    from skm.modules.integrations.domain.desired import ProjectionInputs

__all__ = [
    "CLAUDE_HOOKS_RENDERER",
    "CLAUDE_HOOK_EVENTS",
    "MAX_PROMPT_BYTES",
    "build_hook_command",
    "normalize_hook_payload",
    "render_hook_decision",
    "render_hook_entries",
]

CLAUDE_HOOKS_RENDERER: Final[str] = "claude_code.hooks@1"
MAX_PROMPT_BYTES: Final[int] = 4096

CLAUDE_HOOK_EVENTS: Final[tuple[str, ...]] = (
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "SubagentStop",
    "Stop",
    "SessionStart",
    "SessionEnd",
)

_SURFACE_BINDINGS_ORDER: Final[tuple[tuple[HookSurfaceId, tuple[tuple[str, str | None], ...]], ...]] = (
    (HookSurfaceId.GIT_GUARDRAILS, (("PreToolUse", "Bash"),)),
    (HookSurfaceId.SAFE_DIRS, (("PreToolUse", "Edit|Write|MultiEdit|Bash"),)),
    (HookSurfaceId.PLAN_GUARD, (("PreToolUse", "Edit|Write|MultiEdit"),)),
    (HookSurfaceId.PACK_GUARD, (("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit"),)),
    (HookSurfaceId.CHANGELOG_GATE, (("PreToolUse", "Bash"),)),
    (HookSurfaceId.REVIEW_GATE, (("PreToolUse", "Bash"), ("SubagentStop", None))),
    (HookSurfaceId.COMMAND_LOG, (("PreToolUse", "Bash"),)),
    (HookSurfaceId.SESSION_CONTEXT, (("SessionStart", None),)),
    (HookSurfaceId.RUN_REPORT, (("SessionEnd", None),)),
)

_SUBSCRIPTION_EVENT_BINDINGS: Final[Mapping[HookEventKind, tuple[str, str | None]]] = {
    HookEventKind.SESSION_START: ("SessionStart", None),
    HookEventKind.SESSION_END: ("SessionEnd", None),
    HookEventKind.USER_PROMPT: ("UserPromptSubmit", None),
    HookEventKind.PRE_SHELL: ("PreToolUse", "Bash"),
    HookEventKind.PRE_TOOL: ("PreToolUse", "Edit|Write|MultiEdit|NotebookEdit"),
    HookEventKind.POST_TOOL: ("PostToolUse", None),
    HookEventKind.SUBAGENT_STOP: ("SubagentStop", None),
    HookEventKind.STOP: ("Stop", None),
}

_SURFACE_LOOKUP: Final[Mapping[str, HookSurfaceId]] = {
    **{sid.value.rpartition(".")[2]: sid for sid in HookSurfaceId},
    **{sid.value: sid for sid in HookSurfaceId},
}


def build_hook_command(
    client_event: str,
    surface: HookSurfaceId,
    project_id: ProjectId,
    *,
    hook_class: HookClass | None = None,
) -> str:
    """Format the canonical ``skm-hook`` command line for a Claude Code hook entry."""
    if hook_class is not None:
        return (
            f"skm-hook {client_event} --target {TargetId.CLAUDE_CODE.value}"
            f" --surface {surface.value} --class {hook_class.value} --project {project_id}"
        )
    return (
        f"skm-hook {client_event} --target {TargetId.CLAUDE_CODE.value}"
        f" --surface {surface.value} --project {project_id}"
    )


def _hook_entry(matcher: str | None, command: str, *, enforcement: bool) -> JsonObject:
    hook: JsonObject = {"type": "command", "command": command}
    if enforcement:
        hook["onFailure"] = "block"
    inner: list[JsonValue] = [hook]
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
    """Build SKM-tagged hook entries grouped by Claude Code hook event name."""
    modes = _resolve_modes(inputs.hook_modes)
    by_event: dict[str, list[JsonObject]] = {}

    for surface_id, bindings in _SURFACE_BINDINGS_ORDER:
        mode = modes.get(surface_id, HookMode.OFF)
        if mode is HookMode.OFF:
            continue
        for client_event, matcher in bindings:
            cmd = build_hook_command(client_event, surface_id, inputs.project_id)
            by_event.setdefault(client_event, []).append(
                _hook_entry(
                    matcher,
                    cmd,
                    enforcement=surface_id in ENFORCEMENT
                    or (surface_id is HookSurfaceId.REVIEW_GATE and client_event == "PreToolUse"),
                )
            )

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
            by_event.setdefault(client_event, []).append(
                _hook_entry(
                    matcher, cmd, enforcement=hook_cls is HookClass.ENFORCEMENT and client_event != "Stop"
                )
            )

    return by_event


def _invalid_payload(message: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(ErrorCode.HOOK_PAYLOAD_INVALID, message, details=dict(details))


def _require_nonempty_str(payload: Mapping[str, JsonValue], field: str, event_name: str) -> str:
    val = payload.get(field)
    if not isinstance(val, str) or not val.strip():
        raise _invalid_payload(
            f"Claude hook {event_name!r} payload requires non-empty string field {field!r}",
            event_name=event_name,
            field=field,
        )
    return val


def _optional_str(payload: Mapping[str, JsonValue], field: str, event_name: str) -> str | None:
    val = payload.get(field)
    if val is None:
        return None
    if not isinstance(val, str):
        raise _invalid_payload(
            f"Claude hook {event_name!r} field {field!r} must be a string when present",
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


def _extract_edit_paths(
    tool_name: str, tool_input: Mapping[str, JsonValue], cwd: str, event_name: str, *, strict: bool
) -> tuple[str, ...]:
    found: list[str] = []
    primary = tool_input.get("file_path")
    if primary is None and tool_name == "NotebookEdit":
        primary = tool_input.get("notebook_path")
    if isinstance(primary, str) and primary.strip():
        found.append(_relativize_path(primary, cwd))
    elif primary is not None:
        raise _invalid_payload(
            f"Claude hook {event_name!r} tool {tool_name!r} has invalid file_path",
            event_name=event_name,
            tool_name=tool_name,
        )

    if tool_name == "MultiEdit":
        edits = tool_input.get("edits")
        if isinstance(edits, Sequence) and not isinstance(edits, (str, bytes)):
            for item in cast("Sequence[JsonValue]", edits):
                if isinstance(item, Mapping):
                    sub_fp = cast("Mapping[str, JsonValue]", item).get("file_path")
                    if isinstance(sub_fp, str) and sub_fp.strip():
                        rel = _relativize_path(sub_fp, cwd)
                        if rel not in found:
                            found.append(rel)

    if strict and not found:
        raise _invalid_payload(
            f"Claude hook {event_name!r} tool {tool_name!r} requires tool_input.file_path",
            event_name=event_name,
            tool_name=tool_name,
        )
    return tuple(found)


def _normalize_tool(
    event_name: str,
    raw_tool: str,
    tool_input: Mapping[str, JsonValue],
    cwd: str,
    *,
    is_post: bool,
) -> tuple[HookEventKind, str, str | None, tuple[str, ...]]:
    if raw_tool == "Bash":
        cmd = tool_input.get("command")
        if not isinstance(cmd, str) or not cmd.strip():
            raise _invalid_payload(
                f"Claude hook {event_name!r} for Bash requires non-empty tool_input.command",
                event_name=event_name,
                tool_name=raw_tool,
            )
        kind = HookEventKind.POST_TOOL if is_post else HookEventKind.PRE_SHELL
        return kind, "shell", cmd, ()

    if raw_tool in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
        paths = _extract_edit_paths(raw_tool, tool_input, cwd, event_name, strict=True)
        norm_tool = "write" if raw_tool == "Write" else "edit"
        kind = HookEventKind.POST_TOOL if is_post else HookEventKind.PRE_TOOL
        return kind, norm_tool, None, paths

    if raw_tool in ("Task", "Agent"):
        kind = HookEventKind.POST_TOOL if is_post else HookEventKind.PRE_TOOL
        return kind, "task", None, ()

    if raw_tool.startswith("mcp__"):
        parts = raw_tool.split("__", 2)
        if len(parts) == 3 and parts[1] and parts[2]:
            kind = HookEventKind.POST_TOOL if is_post else HookEventKind.PRE_TOOL
            return kind, f"mcp:{parts[1]}:{parts[2]}", None, ()
        raise _invalid_payload(
            f"Malformed Claude MCP tool name {raw_tool!r}",
            event_name=event_name,
            tool_name=raw_tool,
        )

    paths = _extract_edit_paths(raw_tool, tool_input, cwd, event_name, strict=False)
    kind = HookEventKind.POST_TOOL if is_post else HookEventKind.PRE_TOOL
    return kind, raw_tool.lower(), None, paths


def normalize_hook_payload(event_name: str, payload: Mapping[str, JsonValue]) -> NormalizedHookEvent:
    """Normalize a raw Claude Code hook JSON payload into ``NormalizedHookEvent`` (integrations §4.7)."""
    if not isinstance(cast("object", payload), Mapping):
        raise _invalid_payload("Claude hook payload must be a JSON object", event_name=event_name)

    declared_event = payload.get("hook_event_name")
    if declared_event is not None and declared_event != event_name:
        raise _invalid_payload(
            f"hook_event_name {declared_event!r} does not match invoked event {event_name!r}",
            event_name=event_name,
        )

    if event_name == "SessionStart":
        session_id = _require_nonempty_str(payload, "session_id", event_name)
        cwd = _require_nonempty_str(payload, "cwd", event_name)
        _require_nonempty_str(payload, "hook_event_name", event_name)
        _require_nonempty_str(payload, "source", event_name)
        return NormalizedHookEvent(
            target=TargetId.CLAUDE_CODE,
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
        session_id = _require_nonempty_str(payload, "session_id", event_name)
        cwd = _require_nonempty_str(payload, "cwd", event_name)
        raw_prompt = payload.get("prompt")
        if not isinstance(raw_prompt, str):
            raise _invalid_payload(
                "Claude hook 'UserPromptSubmit' payload requires string field 'prompt'",
                event_name=event_name,
                field="prompt",
            )
        return NormalizedHookEvent(
            target=TargetId.CLAUDE_CODE,
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

    if event_name in ("PreToolUse", "PostToolUse"):
        raw_tool = _require_nonempty_str(payload, "tool_name", event_name)
        raw_input = payload.get("tool_input")
        if not isinstance(raw_input, Mapping):
            raise _invalid_payload(
                f"Claude hook {event_name!r} payload requires object field 'tool_input'",
                event_name=event_name,
                field="tool_input",
            )
        if event_name == "PostToolUse" and "tool_response" not in payload:
            raise _invalid_payload(
                "Claude hook 'PostToolUse' payload requires field 'tool_response'",
                event_name=event_name,
                field="tool_response",
            )
        session_id = _optional_str(payload, "session_id", event_name)
        cwd = _optional_str(payload, "cwd", event_name) or ""
        kind, norm_tool, command, paths = _normalize_tool(
            event_name,
            raw_tool,
            cast("Mapping[str, JsonValue]", raw_input),
            cwd,
            is_post=(event_name == "PostToolUse"),
        )
        return NormalizedHookEvent(
            target=TargetId.CLAUDE_CODE,
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

    if event_name in {"Stop", "SubagentStop"}:
        session_id = _require_nonempty_str(payload, "session_id", event_name)
        stop_active = payload.get("stop_hook_active")
        if not isinstance(stop_active, bool):
            raise _invalid_payload(
                f"Claude hook {event_name!r} requires boolean field 'stop_hook_active'",
                event_name=event_name,
                field="stop_hook_active",
            )
        cwd = _optional_str(payload, "cwd", event_name) or ""
        return NormalizedHookEvent(
            target=TargetId.CLAUDE_CODE,
            kind=HookEventKind.STOP if event_name == "Stop" else HookEventKind.SUBAGENT_STOP,
            session_id=session_id,
            cwd=cwd,
            tool_name=None,
            command=None,
            paths=(),
            prompt=None,
            stop_status="active" if stop_active else "idle",
            raw_event_name=event_name,
        )

    if event_name == "SessionEnd":
        session_id = _require_nonempty_str(payload, "session_id", event_name)
        reason = _require_nonempty_str(payload, "reason", event_name)
        cwd = _optional_str(payload, "cwd", event_name) or ""
        return NormalizedHookEvent(
            target=TargetId.CLAUDE_CODE,
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

    raise _invalid_payload(f"Unsupported Claude Code hook event {event_name!r}", event_name=event_name)


def render_hook_decision(event: NormalizedHookEvent, decision: HookDecision) -> HookOutput:
    """Render ``HookDecision`` as Claude Code ``client_output`` (exit 0 + ``hookSpecificOutput``)."""
    if decision.verdict in (HookVerdict.DENY, HookVerdict.ASK):
        perm_decision = "deny" if decision.verdict is HookVerdict.DENY else "ask"
        reason = (
            decision.agent_message
            or decision.user_message
            or decision.reason_code
            or f"skm hook {decision.surface.value}: {perm_decision}"
        )
        sys_msg = decision.user_message or decision.agent_message or reason
        if event.raw_event_name == "Stop":
            return {"exit_code": 0, "stdout": {"decision": "block", "reason": reason}, "stderr": ""}
        if event.raw_event_name == "UserPromptSubmit":
            return {
                "exit_code": 0,
                "stdout": {"decision": "block", "reason": reason, "systemMessage": sys_msg},
                "stderr": "",
            }
        stdout_obj: JsonObject = {
            "hookSpecificOutput": {
                "hookEventName": event.raw_event_name,
                "permissionDecision": perm_decision,
                "permissionDecisionReason": reason,
            },
            "systemMessage": sys_msg,
        }
        return {"exit_code": 0, "stdout": stdout_obj, "stderr": ""}

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

    # ALLOW and NONE emit empty stdout so SKM never elevates client permissions silently.
    return {"exit_code": 0, "stdout": "", "stderr": ""}
