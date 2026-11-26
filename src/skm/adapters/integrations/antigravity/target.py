"""Checkout projection for Antigravity CLI and IDE workspace instructions and skills."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
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
from skm.modules.integrations.domain.ownership import sha256_tagged
from skm.modules.integrations.domain.target import Surface, SurfaceSupport, TargetCapabilities, TargetId
from skm.modules.integrations.ports import CheckoutFs, UserHomeReader

__all__ = ["AntigravityTarget"]

_INSTRUCTIONS = ".agents/AGENTS.md"
_CAPABILITIES = TargetCapabilities(
    target=TargetId.ANTIGRAVITY,
    surfaces=MappingProxyType(
        {
            surface: SurfaceSupport.NATIVE
            if surface in (Surface.INSTRUCTIONS, Surface.SKILLS)
            else SurfaceSupport.UNSUPPORTED
            for surface in Surface
        }
    ),
    hook_surfaces=MappingProxyType({}),
    tested_client_version="1.5.13",
    verified_at=date(2026, 11, 20),
)


def _activate_rule(file: DesiredFile) -> DesiredFile:
    if not file.relative_path.startswith(".agents/rules/"):
        return file
    raw = file.managed_bytes.removeprefix(b"\xef\xbb\xbf")
    if raw.startswith((b"---\n", b"---\r\n")):
        newline = b"\r\n" if raw.startswith(b"---\r\n") else b"\n"
        open_len = len(b"---") + len(newline)
        close_marker = newline + b"---"
        end = raw.find(close_marker, open_len)
        if end != -1:
            header = raw[open_len:end]
            if any(line.strip().startswith(b"trigger:") for line in header.splitlines()):
                return (
                    file
                    if raw == file.managed_bytes
                    else replace(file, managed_bytes=raw, managed_digest=sha256_tagged(raw))
                )
            body = raw[:open_len] + b"trigger: always_on" + newline + raw[open_len:]
            return replace(file, managed_bytes=body, managed_digest=sha256_tagged(body))
    body = b"---\ntrigger: always_on\n---\n\n" + raw
    return replace(file, managed_bytes=body, managed_digest=sha256_tagged(body))


class AntigravityTarget:
    target_id = TargetId.ANTIGRAVITY
    renderer_version = "antigravity@1"

    def capabilities(self) -> TargetCapabilities:
        return _CAPABILITIES

    def render(self, inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
        instructions = render_instructions(inputs, path=_INSTRUCTIONS, renderer="antigravity.instructions@1")
        files = merge_and_render_bundle_assets(
            inputs,
            target=self.target_id,
            renderer="antigravity.bundle_assets@1",
            files=[*(() if instructions is None else (instructions,)), *render_skills(inputs)],
        )
        return tuple(_activate_rule(file) for file in files)

    def normalize_hook_payload(
        self, event_name: str, payload: Mapping[str, JsonValue]
    ) -> NormalizedHookEvent:
        del event_name, payload
        raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "Antigravity hooks are unsupported")

    def render_hook_decision(self, event: NormalizedHookEvent, decision: HookDecision) -> HookOutput:
        del event, decision
        raise CapabilityUnavailable(ErrorCode.CAPABILITY_UNAVAILABLE, "Antigravity hooks are unsupported")

    def client_layers(self, fs: CheckoutFs, home: UserHomeReader) -> tuple[ClientLayer, ...]:
        del fs, home
        return ()

    def instruction_paths(self) -> tuple[str, ...]:
        return ("AGENTS.md", "GEMINI.md", _INSTRUCTIONS, ".agents/GEMINI.md")

    def summarize_session(self, payload: Mapping[str, JsonValue], fs: CheckoutFs) -> JsonObject | None:
        del payload, fs
        return None
