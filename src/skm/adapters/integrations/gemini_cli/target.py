"""Gemini CLI project settings, hooks and shared skills."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType

from skm.adapters.integrations._render import json_doc
from skm.adapters.integrations.codex.instructions import render_instructions
from skm.adapters.integrations.codex.skills import render_skills
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.integrations.domain.bundle import merge_and_render_bundle_assets
from skm.modules.integrations.domain.contracts import ClientLayer, HookOutput
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.hook_events import (
    HookClass,
    HookEventKind,
    HookSurfaceId,
    NormalizedHookEvent,
)
from skm.modules.integrations.domain.hook_rules import HookDecision, HookVerdict
from skm.modules.integrations.domain.merged_json import OwnedKeyPath, extract_owned, parse_json_document
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetCapabilities, TargetId
from skm.modules.integrations.ports import CheckoutFs, UserHomeReader

__all__ = ["GeminiCliTarget"]

_SETTINGS = ".gemini/settings.json"
_INSTRUCTIONS = ("AGENTS.md", "GEMINI.md")
_EDIT_TOOLS = ("write_file", "replace")
_SHELL = "run_shell_command"
# See tests/fixtures/integrations/gemini-cli/0.71.1/hooks.json.
_CAPABILITIES = TargetCapabilities(
    target=TargetId.GEMINI_CLI,
    surfaces=MappingProxyType(
        {
            Surface.INSTRUCTIONS: SurfaceSupport.CONFIG_NATIVE,
            Surface.SKILLS: SurfaceSupport.NATIVE,
            Surface.PERMISSIONS: SurfaceSupport.CONFIG_NATIVE,
            Surface.HOOKS: SurfaceSupport.HOOK_NATIVE,
            Surface.MCP: SurfaceSupport.UNSUPPORTED,
            Surface.AGENTS: SurfaceSupport.UNSUPPORTED,
        }
    ),
    hook_surfaces=MappingProxyType(
        {
            HookSurfaceId.COMMAND_LOG: {"class": "observation", "bindings": [{"event": "AfterTool"}]},
            HookSurfaceId.SAFE_DIRS: {"class": "enforcement", "bindings": [{"event": "BeforeTool"}]},
            HookSurfaceId.SUBSCRIPTIONS: {"class": "workflow", "bindings": [{"event": "AfterTool"}]},
        }
    ),
    tested_client_version="0.71.1",
    verified_at=date(2026, 11, 27),
)


def _entry(
    inputs: ProjectionInputs,
    event: str,
    tools: tuple[str, ...],
    surface: HookSurfaceId,
    timeout: int,
    hook_class: HookClass | None = None,
) -> JsonObject:
    command = f"skm-hook {event} --target gemini_cli --surface {surface.value} --project {inputs.project_id}"
    if hook_class is not None:
        command += f" --class {hook_class.value}"
    return {
        "matcher": "^(" + "|".join(tools) + ")$",
        "hooks": [{"type": "command", "command": command, "timeout": timeout}],
    }


def _render_settings(inputs: ProjectionInputs) -> DesiredFile:
    before: list[JsonValue] = [
        _entry(inputs, "BeforeTool", (*_EDIT_TOOLS, _SHELL), HookSurfaceId.SAFE_DIRS, 5000)
    ]
    after: list[JsonValue] = []
    for event in inputs.host_subscription_events:
        if event.kind is HookEventKind.POST_TOOL:
            after.extend(
                _entry(inputs, "AfterTool", _EDIT_TOOLS, HookSurfaceId.SUBSCRIPTIONS, 30000, cls)
                for cls in event.classes
            )
    if not after:
        after.append(_entry(inputs, "AfterTool", _EDIT_TOOLS, HookSurfaceId.COMMAND_LOG, 30000))
    document = {
        "context": {"fileName": list(_INSTRUCTIONS)},
        "advanced": {"ignoreLocalEnv": True},
        "hooks": {"BeforeTool": before, "AfterTool": after},
    }
    boundary = ManagedBoundary(
        Ownership.MERGED_JSON,
        owned_keys=(
            OwnedKeyPath(("context", "fileName"), "replace"),
            OwnedKeyPath(("advanced", "ignoreLocalEnv"), "replace"),
            *(OwnedKeyPath(("hooks", event), "list_union_tagged") for event in ("BeforeTool", "AfterTool")),
        ),
    )
    managed = json_doc.dumps_bytes(extract_owned(document, boundary.owned_keys))
    return DesiredFile(
        TargetId.GEMINI_CLI,
        Surface.PERMISSIONS,
        _SETTINGS,
        boundary,
        managed,
        sha256_tagged(managed),
        (),
        "gemini_cli.settings@1",
    )


def _required(payload: Mapping[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip() or "\0" in value:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, f"Gemini CLI hook requires {key}")
    return value


def _layer(name: str, path: str, raw: bytes | None) -> ClientLayer:
    try:
        data = None if raw is None else parse_json_document(raw)
    except ValueError:
        return {
            "layer": name,
            "path": path,
            "exists": True,
            "valid": False,
            "data": None,
            "error": "invalid_json",
        }
    return {"layer": name, "path": path, "exists": raw is not None, "valid": True, "data": data}


class GeminiCliTarget:
    target_id = TargetId.GEMINI_CLI
    renderer_version = "gemini_cli@2"

    def capabilities(self) -> TargetCapabilities:
        return _CAPABILITIES

    def render(self, inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
        files = [_render_settings(inputs), *render_skills(inputs, renderer="gemini_cli.skills@2")]
        instructions = render_instructions(inputs, renderer="gemini_cli.instructions@2")
        if instructions is not None:
            files.append(instructions)
        return merge_and_render_bundle_assets(
            inputs,
            target=self.target_id,
            renderer="gemini_cli.bundle_assets@2",
            files=files,
        )

    def normalize_hook_payload(
        self, event_name: str, payload: Mapping[str, JsonValue]
    ) -> NormalizedHookEvent:
        if event_name not in {"BeforeTool", "AfterTool"} or payload.get("hook_event_name") != event_name:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid Gemini CLI hook event")
        post = event_name == "AfterTool"
        tool = _required(payload, "tool_name")
        raw = payload.get("tool_input")
        if not isinstance(raw, dict) or (post and not isinstance(payload.get("tool_response"), dict)):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid Gemini CLI tool hook fields")
        if tool in _EDIT_TOOLS:
            kind = HookEventKind.POST_TOOL if post else HookEventKind.PRE_TOOL
            command, paths = None, (_required(raw, "file_path"),)
            normalized_tool = "write" if tool == "write_file" else "edit"
        elif tool == _SHELL and not post:
            kind = HookEventKind.PRE_SHELL
            command, paths, normalized_tool = _required(raw, "command"), (), "shell"
        else:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Unsupported Gemini CLI hook tool")
        return NormalizedHookEvent(
            self.target_id,
            kind,
            _required(payload, "session_id"),
            _required(payload, "cwd"),
            normalized_tool,
            command,
            paths,
            None,
            None,
            event_name,
        )

    def render_hook_decision(self, event: NormalizedHookEvent, decision: HookDecision) -> HookOutput:
        reason = decision.agent_message or decision.user_message or decision.reason_code
        if decision.verdict in (HookVerdict.DENY, HookVerdict.ASK):
            return {"exit_code": 2, "stdout": "", "stderr": reason or "SKM blocked this operation."}
        output: JsonObject = {}
        if decision.additional_context and event.raw_event_name == "AfterTool":
            output["hookSpecificOutput"] = {"additionalContext": decision.additional_context}
        return {"exit_code": 0, "stdout": output, "stderr": ""}

    def client_layers(self, fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]:
        try:
            raw = home.read("gemini.user_settings")
        except (OSError, ValueError, ValidationFailed):
            raw = b"\0"
        return (
            _layer("user", "~/" + _SETTINGS, raw),
            _layer("project", _SETTINGS, fs.read(_SETTINGS)),
        )

    def instruction_paths(self) -> tuple[str, ...]:
        return _INSTRUCTIONS

    def summarize_session(self, payload: Mapping[str, JsonValue], fs: CheckoutFs) -> JsonObject | None:
        del payload, fs
        return None
