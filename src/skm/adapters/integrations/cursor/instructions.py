"""Cursor ``.cursor/rules/skm-instructions.mdc`` instruction renderer (integrations §4.8, §5.1)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Final, cast

from skm.modules.integrations.domain.contracts import InstructionBlock, SourceRef
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs
from skm.modules.integrations.domain.target import Surface

from .rules import CURSOR_RULES_PREFIX, render_mdc_rule

__all__ = [
    "CURSOR_INSTRUCTIONS_DESCRIPTION",
    "CURSOR_INSTRUCTIONS_PATH",
    "CURSOR_INSTRUCTIONS_RENDERER",
    "CURSOR_INSTRUCTIONS_SLUG",
    "render_instructions",
]

CURSOR_INSTRUCTIONS_SLUG: Final[str] = "skm-instructions"
CURSOR_INSTRUCTIONS_PATH: Final[str] = f"{CURSOR_RULES_PREFIX}/{CURSOR_INSTRUCTIONS_SLUG}.mdc"
CURSOR_INSTRUCTIONS_RENDERER: Final[str] = "cursor.instructions@1"
CURSOR_INSTRUCTIONS_DESCRIPTION: Final[str] = "Repository instructions and guidelines"


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
            return raw.replace("\r\n", "\n").strip("\n")
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


def render_instructions(inputs: ProjectionInputs) -> DesiredFile | None:
    """Render ``.cursor/rules/skm-instructions.mdc`` with ``alwaysApply: true``."""
    core_on = _block_enabled(inputs.instructions_core)
    proj_on = _block_enabled(inputs.instructions_project)
    if not core_on and not proj_on:
        return None

    sections: list[str] = []
    if core_on:
        core_text = _block_text(inputs.instructions_core)
        if core_text:
            sections.append(core_text)
    if proj_on:
        proj_text = _block_text(inputs.instructions_project)
        if proj_text:
            sections.append(proj_text)

    combined_body = "\n\n".join(sections)
    return render_mdc_rule(
        CURSOR_INSTRUCTIONS_SLUG,
        description=CURSOR_INSTRUCTIONS_DESCRIPTION,
        body=combined_body,
        always_apply=True,
        surface=Surface.INSTRUCTIONS,
        source_refs=_collect_source_refs(inputs.instructions_core, inputs.instructions_project),
        renderer=CURSOR_INSTRUCTIONS_RENDERER,
    )
