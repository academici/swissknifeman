"""Grok hook registrations, camelCase payload normalization, and decision rendering (§4.7, §4.8, §5.5)."""

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
from skm.modules.integrations.domain.hook_rules import HookDecision, HookMode, HookVerdict
from skm.modules.integrations.domain.target import Surface, TargetId

if TYPE_CHECKING:
    from skm.modules.integrations.domain.contracts import HookOutput, SourceRef
    from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs

__all__ = [
    "GROK_HOOKS_DESCRIPTION",
    "GROK_HOOKS_PATH",
    "GROK_HOOKS_RENDERER",
    "GROK_HOOK_EVENTS",
    "MAX_PROMPT_BYTES",
    "build_hook_command",
    "normalize_hook_payload",
    "render_hook_decision",
    "render_hook_entries",
    "render_hooks",
]

GROK_HOOKS_PATH: Final[str] = ".grok/hooks/skm.json"
GROK_HOOKS_RENDERER: Final[str] = "grok.hooks@1"
GROK_HOOKS_DESCRIPTION: Final[str] = "Managed provider-native lifecycle hooks."
MAX_PROMPT_BYTES: Final[int] = 4096

GROK_HOOK_EVENTS: Final[tuple[str, ...]] = (
    "PreToolUse",
    "PostToolUse",
    "UserPromptSubmit",
    "SubagentStop",
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
    HookEventKind.SUBAGENT_STOP: ("SubagentStop", None),
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
    """Format the canonical ``skm-hook`` command line for a Grok hook entry."""
    if hook_class is not None:
        return (
            f"skm-hook {client_event} --target {TargetId.GROK.value}"
            f" --surface {surface.value} --class {hook_class.value} --project {project_id}"
        )
    return (
        f"skm-hook {client_event} --target {TargetId.GROK.value}"
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
    """Build SKM hook entries grouped by Grok hook event name."""
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
    """Render ``.grok/hooks/skm.json`` as a ``MANAGED_FILE`` (Grok loads all ``.grok/hooks/*.json``)."""
    from skm.adapters.integrations._render import json_doc
    from skm.modules.integrations.domain.desired import DesiredFile
    from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged

    entries = render_hook_entries(inputs)
    if not entries:
        return None

    doc: JsonObject = {
        "description": GROK_HOOKS_DESCRIPTION,
        "hooks": {ev: cast("list[JsonValue]", entries[ev]) for ev in GROK_HOOK_EVENTS if ev in entries},
    }
    managed_bytes = json_doc.dumps_bytes(doc)
    refs: list[SourceRef] = [{"kind": "hooks", "key": "integrations.hooks.mode"}]
    if inputs.host_subscription_events:
        refs.append({"kind": "hooks", "key": "hooks.subscriptions"})
    return DesiredFile(
        target=TargetId.GROK,
        surface=Surface.HOOKS,
        relative_path=GROK_HOOKS_PATH,
        boundary=ManagedBoundary(Ownership.MANAGED_FILE),
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=tuple(refs),
        renderer=GROK_HOOKS_RENDERER,
    )


def _invalid_payload(message: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(ErrorCode.HOOK_PAYLOAD_INVALID, message, details=dict(details))


def _require_nonempty_str(payload: Mapping[str, JsonValue], field: str, event_name: str) -> str:
    val = payload.get(field)
    if not isinstance(val, str) or not val.strip():
        raise _invalid_payload(
            f"Grok hook {event_name!r} payload requires non-empty string field {field!r}",
            event_name=event_name,
            field=field,
        )
    return val


def _optional_nonempty_str(payload: Mapping[str, JsonValue], field: str, event_name: str) -> str | None:
    if field not in payload or payload[field] is None:
        return None
    return _require_nonempty_str(payload, field, event_name)


def _optional_cwd(payload: Mapping[str, JsonValue], event_name: str) -> str:
    if "cwd" not in payload or payload["cwd"] is None:
        return ""
    val = payload["cwd"]
    if not isinstance(val, str) or not val.strip():
        raise _invalid_payload(
            f"Grok hook {event_name!r} field 'cwd' must be a non-empty string when present",
            event_name=event_name,
            field="cwd",
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
            f"Grok hook {event_name!r} for apply_patch requires non-empty string toolInput.input",
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
                        f"Grok hook {event_name!r} apply_patch header has empty or invalid path",
                        event_name=event_name,
                        tool_name="apply_patch",
                    )
                rel = _relativize_path(candidate, cwd)
                if rel not in found:
                    found.append(rel)
                break

    if not found:
        raise _invalid_payload(
            f"Grok hook {event_name!r} apply_patch payload contains no file headers",
            event_name=event_name,
            tool_name="apply_patch",
        )
    return tuple(found)


def _extract_tool_paths(tool_input: Mapping[str, JsonValue], cwd: str) -> tuple[str, ...]:
    collected: list[str] = []
    for key in ("filePath", "file_path", "path"):
        fp = tool_input.get(key)
        if isinstance(fp, str) and fp.strip():
            rel = _relativize_path(fp, cwd)
            if rel not in collected:
                collected.append(rel)
            break
    edits = tool_input.get("edits")
    if isinstance(edits, Sequence) and not isinstance(edits, (str, bytes)):
        for item in edits:
            if isinstance(item, Mapping):
                for key in ("filePath", "file_path", "path"):
                    ep = item.get(key)
                    if isinstance(ep, str) and ep.strip():
                        rel = _relativize_path(ep, cwd)
                        if rel not in collected:
                            collected.append(rel)
                        break
    return tuple(collected)


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
                f"Grok hook {event_name!r} for Bash requires non-empty toolInput.command",
                event_name=event_name,
                tool_name=raw_tool,
            )
        kind = HookEventKind.POST_TOOL if event_name == "PostToolUse" else HookEventKind.PRE_SHELL
        return kind, "shell", cmd, ()

    base_kind = HookEventKind.POST_TOOL if event_name == "PostToolUse" else HookEventKind.PRE_TOOL

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
            f"Malformed Grok MCP tool name {raw_tool!r}",
            event_name=event_name,
            tool_name=raw_tool,
        )

    norm_name = "edit" if raw_tool == "MultiEdit" else raw_tool.lower()
    return base_kind, norm_name, None, _extract_tool_paths(tool_input, cwd)


def normalize_hook_payload(event_name: str, payload: Mapping[str, JsonValue]) -> NormalizedHookEvent:
    """Normalize a raw Grok camelCase hook JSON payload into ``NormalizedHookEvent`` (§4.7)."""
    if not isinstance(cast("object", payload), Mapping):
        raise _invalid_payload("Grok hook payload must be a JSON object", event_name=event_name)
    if event_name not in GROK_HOOK_EVENTS:
        raise _invalid_payload(f"Unsupported Grok hook event {event_name!r}", event_name=event_name)

    declared_event = _require_nonempty_str(payload, "hookEventName", event_name)
    if declared_event != event_name:
        raise _invalid_payload(
            f"hookEventName {declared_event!r} does not match invoked event {event_name!r}",
            event_name=event_name,
        )

    if event_name == "SessionStart":
        session_id = _require_nonempty_str(payload, "sessionId", event_name)
        cwd = _require_nonempty_str(payload, "cwd", event_name)
        return NormalizedHookEvent(
            target=TargetId.GROK,
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
        session_id = _require_nonempty_str(payload, "sessionId", event_name)
        cwd = _optional_cwd(payload, event_name)
        raw_prompt = payload.get("prompt")
        if not isinstance(raw_prompt, str):
            raise _invalid_payload(
                "Grok hook 'UserPromptSubmit' payload requires string field 'prompt'",
                event_name=event_name,
                field="prompt",
            )
        return NormalizedHookEvent(
            target=TargetId.GROK,
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
        session_id = _optional_nonempty_str(payload, "sessionId", event_name)
        cwd = _optional_cwd(payload, event_name)
        raw_tool = _require_nonempty_str(payload, "toolName", event_name)
        raw_input = payload.get("toolInput")
        if not isinstance(raw_input, Mapping):
            raise _invalid_payload(
                f"Grok hook {event_name!r} payload requires object field 'toolInput'",
                event_name=event_name,
                field="toolInput",
            )
        kind, norm_tool, command, paths = _normalize_tool_event(
            event_name, raw_tool, cast("Mapping[str, JsonValue]", raw_input), cwd
        )
        return NormalizedHookEvent(
            target=TargetId.GROK,
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
        session_id = _require_nonempty_str(payload, "sessionId", event_name)
        cwd = _optional_cwd(payload, event_name)
        stop_active = payload.get("stopHookActive")
        if stop_active is not None and not isinstance(stop_active, bool):
            raise _invalid_payload(
                "Grok hook 'SubagentStop' field 'stopHookActive' must be boolean when present",
                event_name=event_name,
                field="stopHookActive",
            )
        sub_status = None if stop_active is None else ("active" if stop_active else "idle")
        return NormalizedHookEvent(
            target=TargetId.GROK,
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

    session_id = _require_nonempty_str(payload, "sessionId", event_name)
    cwd = _optional_cwd(payload, event_name)
    reason = _require_nonempty_str(payload, "reason", event_name)
    return NormalizedHookEvent(
        target=TargetId.GROK,
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
    """Render ``HookDecision`` as Grok ``client_output`` (exit 2 + stderr on deny/ask)."""
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
