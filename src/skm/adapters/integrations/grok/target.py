"""Concrete ``IntegrationTarget`` implementation for Grok (integrations §4.8, §6)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Final, cast

from skm.kernel.errors import ValidationFailed
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

from .config_toml import GROK_CONFIG_PATH, render_config_toml
from .hooks import GROK_HOOKS_PATH, render_hooks
from .hooks import normalize_hook_payload as _normalize_hook_payload
from .hooks import render_hook_decision as _render_hook_decision
from .instructions import GROK_INSTRUCTIONS_PATH, render_instructions
from .skills import render_skills

__all__ = [
    "GROK_LAYER_SPECS",
    "GROK_RENDERER_VERSION",
    "GrokTarget",
    "load_capabilities",
    "read_grok_layers",
]

GROK_RENDERER_VERSION: Final[str] = "grok@1"
_CAPABILITIES_FILE: Final[Path] = Path(__file__).with_name("capabilities.toml")

GROK_LAYER_SPECS: Final[tuple[tuple[str, str, str, str, str], ...]] = (
    ("user", "home", "grok.user_config", "~/.grok/config.toml", "toml"),
    ("project", "checkout", GROK_CONFIG_PATH, GROK_CONFIG_PATH, "toml"),
    ("hooks", "checkout", GROK_HOOKS_PATH, GROK_HOOKS_PATH, "json"),
)


def _parse_layer_bytes(layer_id: str, display_path: str, fmt: str, raw: bytes | None) -> ClientLayer:
    if raw is None:
        return {
            "layer": layer_id,
            "path": display_path,
            "exists": False,
            "valid": True,
            "data": None,
            "error": None,
        }

    if fmt == "json":
        try:
            parsed_json = parse_json_document(raw)
        except ValueError:
            return {
                "layer": layer_id,
                "path": display_path,
                "exists": True,
                "valid": False,
                "data": None,
                "error": "invalid_json",
            }
        return {
            "layer": layer_id,
            "path": display_path,
            "exists": True,
            "valid": True,
            "data": cast("JsonObject", parsed_json),
            "error": None,
        }

    try:
        text = raw.decode("utf-8")
        parsed_toml = decode_document(text, "toml")
    except (UnicodeDecodeError, ValueError, TypeError, ValidationFailed):
        return {
            "layer": layer_id,
            "path": display_path,
            "exists": True,
            "valid": False,
            "data": None,
            "error": "invalid_toml",
        }
    return {
        "layer": layer_id,
        "path": display_path,
        "exists": True,
        "valid": True,
        "data": parsed_toml,
        "error": None,
    }


def read_grok_layers(fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]:
    """Read Grok user/project TOML layers and checkout hook JSON without mutating any file."""
    layers: list[ClientLayer] = []
    for layer_id, origin, selector, display_path, fmt in GROK_LAYER_SPECS:
        if origin == "home":
            try:
                raw = home.read(cast("Any", selector))
            except (KeyError, ValueError):
                raw = None
        else:
            raw = fs.read(selector)
        layers.append(_parse_layer_bytes(layer_id, display_path, fmt, raw))
    return tuple(layers)


@lru_cache(maxsize=1)
def load_capabilities() -> TargetCapabilities:
    """Load and parse ``capabilities.toml`` for ``TargetId.GROK``."""
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


class GrokTarget:
    """Native file renderer, camelCase hook codec, and layer reader for Grok."""

    target_id: TargetId = TargetId.GROK
    renderer_version: str = GROK_RENDERER_VERSION

    def capabilities(self) -> TargetCapabilities:
        return load_capabilities()

    def render(self, inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
        files: list[DesiredFile] = []
        instructions_file = render_instructions(inputs)
        if instructions_file is not None:
            files.append(instructions_file)
        files.extend(render_skills(inputs))
        files.append(render_config_toml(inputs))
        hooks_file = render_hooks(inputs)
        if hooks_file is not None:
            files.append(hooks_file)
        # Surface.AGENTS is honestly UNSUPPORTED on Grok: emit zero agent files.
        return merge_and_render_bundle_assets(
            inputs,
            target=TargetId.GROK,
            renderer="grok.bundle_assets@1",
            files=files,
        )

    def normalize_hook_payload(
        self, event_name: str, payload: Mapping[str, JsonValue]
    ) -> NormalizedHookEvent:
        return _normalize_hook_payload(event_name, payload)

    def render_hook_decision(self, event: NormalizedHookEvent, decision: HookDecision) -> HookOutput:
        return _render_hook_decision(event, decision)

    def client_layers(self, fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]:
        return read_grok_layers(fs, home)

    def instruction_paths(self) -> tuple[str, ...]:
        return (GROK_INSTRUCTIONS_PATH,)

    def summarize_session(self, payload: Mapping[str, JsonValue], fs: CheckoutFs) -> JsonObject | None:
        _ = (payload, fs)
        return None
