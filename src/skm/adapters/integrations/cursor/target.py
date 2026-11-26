"""Concrete ``IntegrationTarget`` implementation for Cursor (integrations §4.8, §6)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Final, Literal, cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.integrations.domain.bundle import merge_and_render_bundle_assets
from skm.modules.integrations.domain.contracts import ClientLayer, HookBinding, HookOutput
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookSurfaceId, NormalizedHookEvent
from skm.modules.integrations.domain.hook_rules import HookDecision
from skm.modules.integrations.domain.merged_json import parse_json_document
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetCapabilities, TargetId
from skm.modules.integrations.ports import CheckoutFs, UserHomeReader
from skm.platform.config.sources.document import decode_document

from .agents import render_agents
from .hooks import normalize_hook_payload as _normalize_hook_payload
from .hooks import render_hook_decision as _render_hook_decision
from .hooks import render_hooks
from .instructions import CURSOR_INSTRUCTIONS_PATH, render_instructions
from .mcp import render_mcp
from .permissions import render_cli_permissions, render_ide_permissions
from .skills import render_skills

__all__ = [
    "CURSOR_LAYER_SPECS",
    "CURSOR_RENDERER_VERSION",
    "CursorTarget",
    "load_capabilities",
    "read_cursor_layers",
]

CURSOR_RENDERER_VERSION: Final[str] = "cursor@1"
_CAPABILITIES_FILE: Final[Path] = Path(__file__).with_name("capabilities.toml")

type _HomeLogical = Literal["claude.user_settings", "vscode.user_settings"]

CURSOR_LAYER_SPECS: Final[tuple[tuple[str, str, str, str], ...]] = (
    ("cli", "checkout", ".cursor/cli.json", ".cursor/cli.json"),
    ("ide_permissions", "checkout", ".cursor/permissions.json", ".cursor/permissions.json"),
    ("hooks", "checkout", ".cursor/hooks.json", ".cursor/hooks.json"),
    ("mcp", "checkout", ".cursor/mcp.json", ".cursor/mcp.json"),
    ("claude_user", "home", "claude.user_settings", "~/.claude/settings.json"),
    ("claude_project", "checkout", ".claude/settings.json", ".claude/settings.json"),
    ("claude_local", "checkout", ".claude/settings.local.json", ".claude/settings.local.json"),
    ("vscode", "home", "vscode.user_settings", "~/.config/Code/User/settings.json"),
)


def _parse_json_layer(
    layer_id: str,
    display_path: str,
    raw: bytes | None,
    *,
    gitignored: bool | None = None,
) -> ClientLayer:
    if raw is None:
        missing_layer: ClientLayer = {
            "layer": layer_id,
            "path": display_path,
            "exists": False,
            "valid": True,
            "data": None,
            "error": None,
        }
        if gitignored is not None:
            missing_layer["gitignored"] = gitignored
        return missing_layer

    try:
        parsed = parse_json_document(raw)
    except ValueError:
        err_layer: ClientLayer = {
            "layer": layer_id,
            "path": display_path,
            "exists": True,
            "valid": False,
            "data": None,
            "error": "invalid_json",
        }
        if gitignored is not None:
            err_layer["gitignored"] = gitignored
        return err_layer

    ok_layer: ClientLayer = {
        "layer": layer_id,
        "path": display_path,
        "exists": True,
        "valid": True,
        "data": cast("JsonObject", parsed),
        "error": None,
    }
    if gitignored is not None:
        ok_layer["gitignored"] = gitignored
    return ok_layer


def read_cursor_layers(fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]:
    """Read Cursor checkout layers plus Claude-compat/VS Code layers without mutating any file."""
    layers: list[ClientLayer] = []
    for layer_id, origin, selector, display_path in CURSOR_LAYER_SPECS:
        if origin == "home":
            raw = home.read(cast("_HomeLogical", selector))
            layers.append(_parse_json_layer(layer_id, display_path, raw))
        else:
            raw = fs.read(selector)
            gitignored = fs.is_gitignored(selector) if layer_id == "claude_local" else None
            layers.append(_parse_json_layer(layer_id, display_path, raw, gitignored=gitignored))
    return tuple(layers)


@lru_cache(maxsize=1)
def load_capabilities() -> TargetCapabilities:
    """Load and parse ``capabilities.toml`` for ``TargetId.CURSOR``."""
    raw = decode_document(_CAPABILITIES_FILE.read_text(encoding="utf-8"), "toml")
    target = TargetId(str(raw["target"]))
    raw_surfaces = cast("Mapping[str, object]", raw["surfaces"])
    surfaces = MappingProxyType({Surface(k): SurfaceSupport(str(v)) for k, v in raw_surfaces.items()})
    raw_hook_surfaces = cast("Mapping[str, object]", raw.get("hook_surfaces", {}))
    hook_surfaces: dict[HookSurfaceId, HookBinding] = {}
    for key, val in raw_hook_surfaces.items():
        if isinstance(val, Mapping):
            hook_surfaces[HookSurfaceId(key)] = dict(cast("Mapping[str, JsonValue]", val))
    return TargetCapabilities(
        target=target,
        surfaces=surfaces,
        hook_surfaces=MappingProxyType(hook_surfaces),
        tested_client_version=str(raw["tested_client_version"]),
        verified_at=date.fromisoformat(str(raw["verified_at"])),
    )


class CursorTarget:
    """Native file renderer, camelCase hook codec, and layer reader for Cursor."""

    target_id: TargetId = TargetId.CURSOR
    renderer_version: str = CURSOR_RENDERER_VERSION

    def capabilities(self) -> TargetCapabilities:
        return load_capabilities()

    def render(self, inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
        files: list[DesiredFile] = []
        instructions_file = render_instructions(inputs)
        if instructions_file is not None:
            files.append(instructions_file)
        files.extend(render_skills(inputs))
        files.append(render_cli_permissions(inputs))
        files.append(render_ide_permissions(inputs))
        hooks_file = render_hooks(inputs)
        if hooks_file is not None:
            files.append(hooks_file)
        mcp_file = render_mcp(inputs)
        if mcp_file is not None:
            files.append(mcp_file)
        files.extend(render_agents(inputs))
        return merge_and_render_bundle_assets(
            inputs,
            target=TargetId.CURSOR,
            renderer="cursor.bundle_assets@1",
            files=files,
        )

    def normalize_hook_payload(
        self, event_name: str, payload: Mapping[str, JsonValue]
    ) -> NormalizedHookEvent:
        return _normalize_hook_payload(event_name, payload)

    def render_hook_decision(self, event: NormalizedHookEvent, decision: HookDecision) -> HookOutput:
        return _render_hook_decision(event, decision)

    def client_layers(self, fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]:
        return read_cursor_layers(fs, home)

    def instruction_paths(self) -> tuple[str, ...]:
        return (CURSOR_INSTRUCTIONS_PATH,)

    def summarize_session(self, payload: Mapping[str, JsonValue], fs: CheckoutFs) -> JsonObject | None:
        _ = (payload, fs)
        return None
