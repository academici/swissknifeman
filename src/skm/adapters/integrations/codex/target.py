"""Concrete ``IntegrationTarget`` implementation for Codex (integrations §4.8, §6)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Final, cast

from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.integrations.domain.bundle import merge_and_render_bundle_assets
from skm.modules.integrations.domain.contracts import ClientLayer, HookBinding, HookOutput
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookSurfaceId, NormalizedHookEvent
from skm.modules.integrations.domain.hook_rules import HookDecision
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetCapabilities, TargetId
from skm.modules.integrations.ports import CheckoutFs, UserHomeReader
from skm.platform.config.sources.document import decode_document

from .agents import render_agents
from .config_toml import render_config_toml
from .doctor_layers import read_codex_layers
from .hooks import normalize_hook_payload as _normalize_hook_payload
from .hooks import render_hook_decision as _render_hook_decision
from .hooks import render_hooks
from .instructions import CODEX_INSTRUCTIONS_PATH, render_instructions
from .skills import render_skills

__all__ = [
    "CODEX_RENDERER_VERSION",
    "CodexTarget",
    "load_capabilities",
]

CODEX_RENDERER_VERSION: Final[str] = "codex@1"
_CAPABILITIES_FILE: Final[Path] = Path(__file__).with_name("capabilities.toml")


@lru_cache(maxsize=1)
def load_capabilities() -> TargetCapabilities:
    """Load and parse ``capabilities.toml`` for ``TargetId.CODEX``."""
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


class CodexTarget:
    """Native file renderer, hook codec, and layer reader for Codex."""

    target_id: TargetId = TargetId.CODEX
    renderer_version: str = CODEX_RENDERER_VERSION

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
        files.extend(render_agents(inputs))
        return merge_and_render_bundle_assets(
            inputs,
            target=TargetId.CODEX,
            renderer="codex.bundle_assets@1",
            files=files,
        )

    def normalize_hook_payload(
        self, event_name: str, payload: Mapping[str, JsonValue]
    ) -> NormalizedHookEvent:
        return _normalize_hook_payload(event_name, payload)

    def render_hook_decision(self, event: NormalizedHookEvent, decision: HookDecision) -> HookOutput:
        return _render_hook_decision(event, decision)

    def client_layers(self, fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]:
        return read_codex_layers(fs, home)

    def instruction_paths(self) -> tuple[str, ...]:
        return (CODEX_INSTRUCTIONS_PATH,)

    def summarize_session(self, payload: Mapping[str, JsonValue], fs: CheckoutFs) -> JsonObject | None:
        _ = (payload, fs)
        return None
