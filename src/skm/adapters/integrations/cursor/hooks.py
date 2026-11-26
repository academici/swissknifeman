"""Cursor hook bindings, payload normalization, and decision rendering (integrations §4.7, §4.8, §5.5)."""

from __future__ import annotations

import posixpath
from collections.abc import Mapping, Sequence
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
    "CURSOR_HOOKS_PATH",
    "CURSOR_HOOKS_RENDERER",
    "CURSOR_HOOKS_VERSION",
    "CURSOR_HOOK_EVENTS",
    "build_hook_command",
    "normalize_hook_payload",
    "render_hook_decision",
    "render_hook_entries",
    "render_hooks",
]

CURSOR_HOOKS_PATH: Final[str] = ".cursor/hooks.json"
CURSOR_HOOKS_RENDERER: Final[str] = "cursor.hooks@1"
CURSOR_HOOKS_VERSION: Final[int] = 1

CURSOR_HOOK_EVENTS: Final[tuple[str, ...]] = (
    "sessionStart",
    "beforeShellExecution",
    "afterShellExecution",
    "preToolUse",
    "subagentStop",
    "stop",
    "sessionEnd",
)

_PERMISSION_BEARING_EVENTS: Final[frozenset[str]] = frozenset({"beforeShellExecution", "preToolUse"})

_SURFACE_BINDINGS_ORDER: Final[
    tuple[tuple[HookSurfaceId, tuple[tuple[str, str | None, int | None], ...]], ...]
] = (
    (HookSurfaceId.GIT_GUARDRAILS, (("beforeShellExecution", r"\bgit\b", None),)),
    (HookSurfaceId.SAFE_DIRS, (("beforeShellExecution", None, None),)),
    (HookSurfaceId.PLAN_GUARD, (("preToolUse", "^(Write|Delete)$", None),)),
    (HookSurfaceId.PACK_GUARD, (("preToolUse", "^(Write|Delete|Task|MCP:.*)$", None),)),
    (HookSurfaceId.CHANGELOG_GATE, (("beforeShellExecution", "git.*commit", None),)),
    (
        HookSurfaceId.REVIEW_GATE,
        (("beforeShellExecution", "git.*commit", None), ("subagentStop", None, 3)),
    ),
    (HookSurfaceId.COMMAND_LOG, (("afterShellExecution", None, None),)),
    (HookSurfaceId.SESSION_CONTEXT, (("sessionStart", None, None),)),
    (HookSurfaceId.RUN_REPORT, (("sessionEnd", None, None),)),
)

_SUBSCRIPTION_EVENT_BINDINGS: Final[Mapping[HookEventKind, tuple[str, str | None, int | None]]] = {
    HookEventKind.SESSION_START: ("sessionStart", None, None),
    HookEventKind.SESSION_END: ("sessionEnd", None, None),
    HookEventKind.PRE_SHELL: ("beforeShellExecution", None, None),
    HookEventKind.POST_SHELL: ("afterShellExecution", None, None),
    HookEventKind.PRE_TOOL: ("preToolUse", "^(Write|Delete|Task|MCP:.*)$", None),
    HookEventKind.SUBAGENT_STOP: ("subagentStop", None, 3),
    HookEventKind.STOP: ("stop", None, 3),
}

_SURFACE_LOOKUP: Final[Mapping[str, HookSurfaceId]] = {
    **{sid.value.rpartition(".")[2]: sid for sid in HookSurfaceId},
    **{sid.value: sid for sid in HookSurfaceId},
}

_PATH_REQUIRED_TOOLS: Final[Mapping[str, str]] = {
    "Write": "write",
    "Edit": "edit",
    "Delete": "delete",
}


def build_hook_command(
    client_event: str,
    surface: HookSurfaceId,
    project_id: ProjectId,
    *,
    hook_class: HookClass | None = None,
) -> str:
    """Format the canonical ``skm-hook`` command line for a Cursor hook entry."""
    if hook_class is not None:
        return (
            f"skm-hook {client_event} --target {TargetId.CURSOR.value}"
            f" --surface {surface.value} --class {hook_class.value} --project {project_id}"
        )
    return (
        f"skm-hook {client_event} --target {TargetId.CURSOR.value}"
        f" --surface {surface.value} --project {project_id}"
    )


def _hook_entry(
    matcher: str | None,
    command: str,
    *,
    loop_limit: int | None = None,
) -> JsonObject:
    entry: JsonObject = {"command": command}
    if matcher is not None:
        entry["matcher"] = matcher
    if loop_limit is not None:
        entry["loop_limit"] = loop_limit
    return entry


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
    """Build SKM-tagged hook entries grouped by Cursor camelCase hook event name."""
    modes = _resolve_modes(inputs.hook_modes)
    by_event: dict[str, list[JsonObject]] = {}

    for surface_id, bindings in _SURFACE_BINDINGS_ORDER:
        mode = modes.get(surface_id, HookMode.OFF)
        if mode is HookMode.OFF:
            continue
        for client_event, matcher, loop_limit in bindings:
            cmd = build_hook_command(client_event, surface_id, inputs.project_id)
            by_event.setdefault(client_event, []).append(_hook_entry(matcher, cmd, loop_limit=loop_limit))

    for sub_event in inputs.host_subscription_events:
        mapped = _SUBSCRIPTION_EVENT_BINDINGS.get(sub_event.kind)
        if mapped is None:
            continue
        client_event, matcher, loop_limit = mapped
        for hook_cls in sub_event.classes:
            cmd = build_hook_command(
                client_event,
                HookSurfaceId.SUBSCRIPTIONS,
                inputs.project_id,
                hook_class=hook_cls,
            )
            by_event.setdefault(client_event, []).append(_hook_entry(matcher, cmd, loop_limit=loop_limit))

    return by_event


def render_hooks(inputs: ProjectionInputs) -> DesiredFile | None:
    """Render ``.cursor/hooks.json`` with ``version = 1`` and ``list_union_tagged`` per event."""
    from skm.adapters.integrations._render import json_doc
    from skm.modules.integrations.domain.desired import DesiredFile
    from skm.modules.integrations.domain.merged_json import OwnedKeyPath, extract_owned
    from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged

    entries = render_hook_entries(inputs)
    if not entries:
        return None

    raw_doc: dict[str, Any] = {
        "version": CURSOR_HOOKS_VERSION,
        "hooks": {ev: entries[ev] for ev in CURSOR_HOOK_EVENTS if ev in entries},
    }
    owned_keys = (
        OwnedKeyPath(("version",), "replace"),
        *(OwnedKeyPath(("hooks", ev), "list_union_tagged") for ev in CURSOR_HOOK_EVENTS),
    )
    boundary = ManagedBoundary(Ownership.MERGED_JSON, owned_keys=owned_keys)
    canonical_doc = extract_owned(raw_doc, boundary.owned_keys)
    managed_bytes = json_doc.dumps_bytes(canonical_doc)
    refs: list[SourceRef] = [{"kind": "hooks", "key": "integrations.hooks.mode"}]
    if inputs.host_subscription_events:
        refs.append({"kind": "hooks", "key": "hooks.subscriptions"})
    return DesiredFile(
        target=TargetId.CURSOR,
        surface=Surface.HOOKS,
        relative_path=CURSOR_HOOKS_PATH,
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=tuple(refs),
        renderer=CURSOR_HOOKS_RENDERER,
    )


def _invalid_payload(message: str, **details: JsonValue) -> ValidationFailed:
    return ValidationFailed(ErrorCode.HOOK_PAYLOAD_INVALID, message, details=dict(details))


def _require_nonempty_str(payload: Mapping[str, JsonValue], field: str, event_name: str) -> str:
    val = payload.get(field)
    if not isinstance(val, str) or not val.strip():
        raise _invalid_payload(
            f"Cursor hook {event_name!r} payload requires non-empty string field {field!r}",
            event_name=event_name,
            field=field,
        )
    return val


def _optional_session_id(payload: Mapping[str, JsonValue], event_name: str, *, required: bool) -> str | None:
    if required:
        return _require_nonempty_str(payload, "session_id", event_name)
    raw = payload.get("session_id")
    if raw is None:
        return None
    if not isinstance(raw, str) or not raw.strip():
        raise _invalid_payload(
            f"Cursor hook {event_name!r} optional field 'session_id' must be a non-empty string",
            event_name=event_name,
            field="session_id",
        )
    return raw


def _resolve_cwd(payload: Mapping[str, JsonValue], event_name: str, *, required: bool) -> str:
    raw_cwd = payload.get("cwd")
    if raw_cwd is not None:
        if not isinstance(raw_cwd, str) or not raw_cwd.strip():
            raise _invalid_payload(
                f"Cursor hook {event_name!r} field 'cwd' must be a non-empty string",
                event_name=event_name,
                field="cwd",
            )
        return raw_cwd

    raw_roots = payload.get("workspace_roots")
    if raw_roots is not None:
        if not isinstance(raw_roots, Sequence) or isinstance(raw_roots, (str, bytes)):
            raise _invalid_payload(
                f"Cursor hook {event_name!r} field 'workspace_roots' must be a list of strings",
                event_name=event_name,
                field="workspace_roots",
            )
        roots_seq = cast("Sequence[object]", raw_roots)
        if any(not isinstance(item, str) or not item.strip() for item in roots_seq):
            raise _invalid_payload(
                f"Cursor hook {event_name!r} 'workspace_roots' entries must be non-empty strings",
                event_name=event_name,
                field="workspace_roots",
            )
        if roots_seq:
            return cast("str", roots_seq[0])

    if required:
        raise _invalid_payload(
            f"Cursor hook {event_name!r} requires 'cwd' or non-empty 'workspace_roots'",
            event_name=event_name,
            field="cwd",
        )
    return ""


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


def _normalize_pre_tool_use(
    event_name: str,
    raw_tool: str,
    tool_input: Mapping[str, JsonValue],
    cwd: str,
) -> tuple[str, tuple[str, ...]]:
    if raw_tool in _PATH_REQUIRED_TOOLS:
        norm_tool = _PATH_REQUIRED_TOOLS[raw_tool]
        raw_fp = tool_input.get("file_path")
        if raw_fp is None:
            raw_fp = tool_input.get("path")
        if not isinstance(raw_fp, str) or not raw_fp.strip() or "\x00" in raw_fp:
            raise _invalid_payload(
                f"Cursor hook {event_name!r} for {raw_tool!r} requires non-empty path in tool_input",
                event_name=event_name,
                tool_name=raw_tool,
            )
        return norm_tool, (_relativize_path(raw_fp, cwd),)

    if raw_tool in ("Task", "Agent"):
        return "task", ()

    if raw_tool.startswith("MCP:"):
        parts = raw_tool.split(":", 2)
        if len(parts) == 3 and parts[1].strip() and parts[2].strip():
            return f"mcp:{parts[1]}:{parts[2]}", ()
        raise _invalid_payload(
            f"Malformed Cursor MCP tool name {raw_tool!r}",
            event_name=event_name,
            tool_name=raw_tool,
        )

    if raw_tool.startswith("mcp__"):
        parts = raw_tool.split("__", 2)
        if len(parts) == 3 and parts[1].strip() and parts[2].strip():
            return f"mcp:{parts[1]}:{parts[2]}", ()
        raise _invalid_payload(
            f"Malformed Cursor MCP tool name {raw_tool!r}",
            event_name=event_name,
            tool_name=raw_tool,
        )

    opt_fp = tool_input.get("file_path") or tool_input.get("path")
    paths = (_relativize_path(opt_fp, cwd),) if isinstance(opt_fp, str) and opt_fp.strip() else ()
    return raw_tool.lower(), paths


def normalize_hook_payload(event_name: str, payload: Mapping[str, JsonValue]) -> NormalizedHookEvent:
    """Normalize a raw Cursor camelCase hook JSON payload into ``NormalizedHookEvent`` (integrations §4.7)."""
    if not isinstance(cast("object", payload), Mapping):
        raise _invalid_payload("Cursor hook payload must be a JSON object", event_name=event_name)
    if event_name not in CURSOR_HOOK_EVENTS:
        raise _invalid_payload(f"Unsupported Cursor hook event {event_name!r}", event_name=event_name)

    declared_event = _require_nonempty_str(payload, "hook_event_name", event_name)
    if declared_event != event_name:
        raise _invalid_payload(
            f"hook_event_name {declared_event!r} does not match invoked event {event_name!r}",
            event_name=event_name,
        )
    _require_nonempty_str(payload, "conversation_id", event_name)

    if event_name == "sessionStart":
        session_id = _optional_session_id(payload, event_name, required=True)
        cwd = _resolve_cwd(payload, event_name, required=False)
        return NormalizedHookEvent(
            target=TargetId.CURSOR,
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

    session_id = _optional_session_id(payload, event_name, required=False)

    if event_name == "beforeShellExecution":
        command = _require_nonempty_str(payload, "command", event_name)
        cwd = _resolve_cwd(payload, event_name, required=True)
        return NormalizedHookEvent(
            target=TargetId.CURSOR,
            kind=HookEventKind.PRE_SHELL,
            session_id=session_id,
            cwd=cwd,
            tool_name="shell",
            command=command,
            paths=(),
            prompt=None,
            stop_status=None,
            raw_event_name=event_name,
        )

    if event_name == "afterShellExecution":
        command = _require_nonempty_str(payload, "command", event_name)
        cwd = _resolve_cwd(payload, event_name, required=True)
        duration = payload.get("duration")
        if isinstance(duration, bool) or not isinstance(duration, (int, float)) or duration < 0:
            raise _invalid_payload(
                "Cursor hook 'afterShellExecution' requires non-negative numeric field 'duration'",
                event_name=event_name,
                field="duration",
            )
        sandbox = payload.get("sandbox")
        if not isinstance(sandbox, bool):
            raise _invalid_payload(
                "Cursor hook 'afterShellExecution' requires boolean field 'sandbox'",
                event_name=event_name,
                field="sandbox",
            )
        return NormalizedHookEvent(
            target=TargetId.CURSOR,
            kind=HookEventKind.POST_SHELL,
            session_id=session_id,
            cwd=cwd,
            tool_name="shell",
            command=command,
            paths=(),
            prompt=None,
            stop_status=None,
            raw_event_name=event_name,
        )

    if event_name == "preToolUse":
        raw_tool = _require_nonempty_str(payload, "tool_name", event_name)
        cwd = _resolve_cwd(payload, event_name, required=True)
        raw_input = payload.get("tool_input")
        if not isinstance(raw_input, Mapping):
            raise _invalid_payload(
                "Cursor hook 'preToolUse' payload requires object field 'tool_input'",
                event_name=event_name,
                field="tool_input",
            )
        norm_tool, paths = _normalize_pre_tool_use(
            event_name, raw_tool, cast("Mapping[str, JsonValue]", raw_input), cwd
        )
        return NormalizedHookEvent(
            target=TargetId.CURSOR,
            kind=HookEventKind.PRE_TOOL,
            session_id=session_id,
            cwd=cwd,
            tool_name=norm_tool,
            command=None,
            paths=paths,
            prompt=None,
            stop_status=None,
            raw_event_name=event_name,
        )

    if event_name in ("subagentStop", "stop"):
        status = _require_nonempty_str(payload, "status", event_name)
        loop_count = payload.get("loop_count")
        if isinstance(loop_count, bool) or not isinstance(loop_count, int) or loop_count < 0:
            raise _invalid_payload(
                f"Cursor hook {event_name!r} requires non-negative integer field 'loop_count'",
                event_name=event_name,
                field="loop_count",
            )
        cwd = _resolve_cwd(payload, event_name, required=False)
        kind = HookEventKind.SUBAGENT_STOP if event_name == "subagentStop" else HookEventKind.STOP
        return NormalizedHookEvent(
            target=TargetId.CURSOR,
            kind=kind,
            session_id=session_id,
            cwd=cwd,
            tool_name=None,
            command=None,
            paths=(),
            prompt=None,
            stop_status=status,
            raw_event_name=event_name,
        )

    reason = _require_nonempty_str(payload, "reason", event_name)
    cwd = _resolve_cwd(payload, event_name, required=False)
    return NormalizedHookEvent(
        target=TargetId.CURSOR,
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
    """Render ``HookDecision`` as Cursor ``client_output`` (exit 0 + JSON ``permission`` on stdout)."""
    if decision.verdict is HookVerdict.DENY:
        user_msg = (
            decision.user_message
            or decision.agent_message
            or decision.reason_code
            or f"skm hook {decision.surface.value}: deny"
        )
        agent_msg = decision.agent_message or decision.user_message or decision.reason_code or user_msg
        return {
            "exit_code": 0,
            "stdout": {
                "permission": "deny",
                "user_message": user_msg,
                "agent_message": agent_msg,
            },
            "stderr": "",
        }

    if decision.verdict is HookVerdict.ASK:
        user_msg = (
            decision.user_message
            or decision.agent_message
            or decision.reason_code
            or f"skm hook {decision.surface.value}: ask"
        )
        agent_msg = decision.agent_message or decision.user_message or decision.reason_code or user_msg
        return {
            "exit_code": 0,
            "stdout": {
                "permission": "ask",
                "user_message": user_msg,
                "agent_message": agent_msg,
            },
            "stderr": "",
        }

    if decision.verdict is HookVerdict.CONTEXT:
        text = (
            decision.additional_context
            if decision.additional_context is not None
            else (decision.agent_message or decision.user_message or "")
        )
        if text:
            return {
                "exit_code": 0,
                "stdout": {
                    "permission": "allow",
                    "agent_message": text,
                },
                "stderr": "",
            }
        if event.raw_event_name in _PERMISSION_BEARING_EVENTS:
            return {"exit_code": 0, "stdout": {"permission": "allow"}, "stderr": ""}
        return {"exit_code": 0, "stdout": "", "stderr": ""}

    if decision.verdict is HookVerdict.ALLOW or event.raw_event_name in _PERMISSION_BEARING_EVENTS:
        return {"exit_code": 0, "stdout": {"permission": "allow"}, "stderr": ""}

    return {"exit_code": 0, "stdout": "", "stderr": ""}
