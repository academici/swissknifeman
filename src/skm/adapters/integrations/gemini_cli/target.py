"""Gemini CLI project instructions and skills projection."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from types import MappingProxyType

from skm.adapters.integrations.codex.instructions import render_instructions
from skm.adapters.integrations.codex.skills import render_skills
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import CapabilityUnavailable
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.integrations.domain.bundle import merge_and_render_bundle_assets
from skm.modules.integrations.domain.contracts import ClientLayer, HookOutput
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.hook_events import NormalizedHookEvent
from skm.modules.integrations.domain.hook_rules import HookDecision
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetCapabilities, TargetId
from skm.modules.integrations.ports import CheckoutFs, UserHomeReader

__all__ = ["GeminiCliTarget"]

_INSTRUCTIONS = "GEMINI.md"
_CAPABILITIES = TargetCapabilities(
    target=TargetId.GEMINI_CLI,
    surfaces=MappingProxyType(
        {
            surface: SurfaceSupport.NATIVE
            if surface in (Surface.INSTRUCTIONS, Surface.SKILLS)
            else SurfaceSupport.UNSUPPORTED
            for surface in Surface
        }
    ),
    hook_surfaces=MappingProxyType({}),
    tested_client_version="unverified",
    verified_at=date(2026, 11, 23),
)


class GeminiCliTarget:
    target_id = TargetId.GEMINI_CLI
    renderer_version = "gemini_cli@1"

    def capabilities(self) -> TargetCapabilities:
        return _CAPABILITIES

    def render(self, inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
        files = list(render_skills(inputs, prefix=".gemini/skills", renderer="gemini_cli.skills@1"))
        instructions = render_instructions(inputs, path=_INSTRUCTIONS, renderer="gemini_cli.instructions@1")
        if instructions is not None:
            files.append(instructions)
        return merge_and_render_bundle_assets(
            inputs, target=self.target_id, renderer="gemini_cli.bundle_assets@1", files=files
        )

    def normalize_hook_payload(
        self, event_name: str, payload: Mapping[str, JsonValue]
    ) -> NormalizedHookEvent:
        del event_name, payload
        raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "Gemini CLI hooks are unsupported")

    def render_hook_decision(self, event: NormalizedHookEvent, decision: HookDecision) -> HookOutput:
        del event, decision
        raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "Gemini CLI hooks are unsupported")

    def client_layers(self, fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]:
        del fs, home
        return ()

    def instruction_paths(self) -> tuple[str, ...]:
        return (_INSTRUCTIONS,)

    def summarize_session(self, payload: Mapping[str, JsonValue], fs: CheckoutFs) -> JsonObject | None:
        del payload, fs
        return None
