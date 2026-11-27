"""Concrete ``IntegrationTarget`` implementation for Claude Code (integrations §4.8, §6)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Final, cast

from skm.adapters.integrations.codex.instructions import render_instructions as render_agents_instructions
from skm.adapters.integrations.codex.skills import render_skills as render_shared_skills
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.integrations.domain.bundle import merge_and_render_bundle_assets
from skm.modules.integrations.domain.contracts import ClientLayer, HookBinding, HookOutput
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.hook_events import HookSurfaceId, NormalizedHookEvent
from skm.modules.integrations.domain.hook_rules import HookDecision
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetCapabilities, TargetId
from skm.modules.integrations.ports import CheckoutFs, UserHomeReader
from skm.platform.config.sources.document import decode_document
from skm.platform.system_clock import SystemClock

from .agents import render_agents
from .doctor_layers import read_claude_layers
from .hooks import normalize_hook_payload as _normalize_hook_payload
from .hooks import render_hook_decision as _render_hook_decision
from .instructions import CLAUDE_INSTRUCTIONS_PATH, render_instructions
from .mcp import render_mcp
from .settings import render_local_settings, render_project_settings
from .skills import render_skills

__all__ = [
    "CLAUDE_CODE_RENDERER_VERSION",
    "ClaudeCodeTarget",
    "load_capabilities",
]

CLAUDE_CODE_RENDERER_VERSION: Final[str] = "claude_code@1"
_CAPABILITIES_FILE: Final[Path] = Path(__file__).with_name("capabilities.toml")


@lru_cache(maxsize=1)
def load_capabilities() -> TargetCapabilities:
    """Load and parse ``capabilities.toml`` for ``TargetId.CLAUDE_CODE``."""
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


class ClaudeCodeTarget:
    """Native file renderer, hook codec, and layer reader for Claude Code."""

    target_id: TargetId = TargetId.CLAUDE_CODE
    renderer_version: str = CLAUDE_CODE_RENDERER_VERSION

    def capabilities(self) -> TargetCapabilities:
        return load_capabilities()

    def render(self, inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
        files: list[DesiredFile] = []
        instructions_file = render_instructions(inputs)
        if instructions_file is not None:
            files.append(instructions_file)
        files.extend(render_skills(inputs))
        if inputs.instructions_project.get("zero_shadowing") is True:
            agents_md = render_agents_instructions(inputs)
            if agents_md is not None:
                files.append(agents_md)
            files.extend(render_shared_skills(inputs))
        files.append(render_project_settings(inputs))
        files.append(render_local_settings(inputs))
        mcp_file = render_mcp(inputs)
        if mcp_file is not None:
            files.append(mcp_file)
        files.extend(render_agents(inputs))
        return merge_and_render_bundle_assets(
            inputs,
            target=TargetId.CLAUDE_CODE,
            renderer="claude_code.bundle_assets@1",
            files=files,
        )

    def normalize_hook_payload(
        self, event_name: str, payload: Mapping[str, JsonValue]
    ) -> NormalizedHookEvent:
        return _normalize_hook_payload(event_name, payload)

    def render_hook_decision(self, event: NormalizedHookEvent, decision: HookDecision) -> HookOutput:
        return _render_hook_decision(event, decision)

    def client_layers(self, fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]:
        return read_claude_layers(fs, home)

    def instruction_paths(self) -> tuple[str, ...]:
        return (CLAUDE_INSTRUCTIONS_PATH,)

    def summarize_session(self, payload: Mapping[str, JsonValue], fs: CheckoutFs) -> JsonObject | None:
        path = payload.get("transcript_path")
        session_id = payload.get("session_id")
        observed = payload.get("observed_at")
        if not isinstance(path, str) or not isinstance(session_id, str):
            return None
        transcript = Path(path)
        if not transcript.is_absolute() or transcript.name != session_id + ".jsonl":
            return None
        try:
            observed_at = (
                datetime.fromisoformat(observed) if isinstance(observed, str) else SystemClock().now()
            )
        except ValueError:
            return None

        from .session_summary import summarize_session

        return summarize_session(transcript, session_id=session_id, checkout=fs.root, observed_at=observed_at)
