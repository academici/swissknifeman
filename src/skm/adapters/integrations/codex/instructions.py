"""AGENTS.md managed-block instruction renderer for Codex (integrations §4.5, §4.8)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from skm.modules.integrations.domain.contracts import InstructionBlock, SourceRef
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.managed_block import render_block
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.presets import preset_renderer, read_preset
from skm.modules.integrations.domain.target import Surface

__all__ = [
    "CODEX_INSTRUCTIONS_PATH",
    "CODEX_INSTRUCTIONS_RENDERER",
    "CODEX_INSTRUCTION_BLOCK_IDS",
    "render_instructions",
]

CODEX_INSTRUCTIONS_PATH: Final[str] = "AGENTS.md"
CODEX_INSTRUCTIONS_RENDERER: Final[str] = "codex.instructions@1"
CODEX_INSTRUCTION_BLOCK_IDS: Final[tuple[str, str]] = ("instructions.core", "instructions.project")


def _block_enabled(block: InstructionBlock) -> bool:
    if not block:
        return False
    enabled = block.get("enabled")
    if isinstance(enabled, bool):
        return enabled
    return True


def _block_text(block: InstructionBlock) -> str:
    for field in ("content", "text", "body"):
        raw = block.get(field)
        if isinstance(raw, str):
            return raw
    return ""


def _collect_source_refs(core: InstructionBlock, project: InstructionBlock) -> tuple[SourceRef, ...]:
    refs: list[SourceRef] = []
    if _block_enabled(core):
        core_key = core.get("key")
        core_digest = core.get("resource_digest") or core.get("digest")
        if isinstance(core_key, str) and core_key:
            ref: SourceRef = {"kind": "prompt_block", "key": core_key}
            if isinstance(core_digest, str):
                ref["digest"] = core_digest
            refs.append(ref)

    if _block_enabled(project):
        sections = project.get("sections")
        if isinstance(sections, Sequence) and not isinstance(sections, (str, bytes)):
            for item in cast("Sequence[object]", sections):
                if isinstance(item, Mapping):
                    sec = cast("Mapping[str, object]", item)
                    sec_key = sec.get("key")
                    sec_digest = sec.get("digest")
                    if isinstance(sec_key, str) and sec_key:
                        sref: SourceRef = {"kind": "steering", "key": sec_key}
                        if isinstance(sec_digest, str):
                            sref["digest"] = sec_digest
                        refs.append(sref)
        proj_text = project.get("project_text")
        if isinstance(proj_text, str) and proj_text.strip():
            refs.append({"kind": "setting", "key": "integrations.instructions.project_text"})
    return tuple(refs)


def render_instructions(
    inputs: ProjectionInputs,
    *,
    path: str = CODEX_INSTRUCTIONS_PATH,
    renderer: str = CODEX_INSTRUCTIONS_RENDERER,
) -> DesiredFile | None:
    """Render ``AGENTS.md`` managed blocks ``instructions.core`` and ``instructions.project``."""
    core_on = _block_enabled(inputs.instructions_core)
    proj_on = _block_enabled(inputs.instructions_project)
    if not core_on and not proj_on:
        return None

    blocks: list[tuple[str, str]] = []
    if core_on:
        blocks.append(("instructions.core", _block_text(inputs.instructions_core)))
    if proj_on:
        blocks.append(("instructions.project", _block_text(inputs.instructions_project)))

    block_ids = tuple(block_id for block_id, _ in blocks)
    managed_bytes = b"".join(render_block(block_id, body) for block_id, body in blocks)
    boundary = ManagedBoundary(Ownership.MANAGED_BLOCK, block_ids=block_ids)
    return DesiredFile(
        target=inputs.target,
        surface=Surface.INSTRUCTIONS,
        relative_path=path,
        boundary=boundary,
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=_collect_source_refs(inputs.instructions_core, inputs.instructions_project),
        renderer=preset_renderer(renderer, read_preset(inputs.instructions_project.get("preset"))),
    )
