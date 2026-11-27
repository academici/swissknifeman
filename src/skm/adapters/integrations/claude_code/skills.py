"""Skill directory renderer for ``.claude/skills/<skill_key>/...`` (integrations §4.8, §5.2)."""

from typing import Final

from skm.adapters.integrations.codex.skills import render_skills as render_skill_files
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs

__all__ = [
    "CLAUDE_SKILLS_PREFIX",
    "CLAUDE_SKILLS_RENDERER",
    "SKILL_LISTING_MAX_CHARS",
    "render_skills",
]

CLAUDE_SKILLS_PREFIX: Final[str] = ".claude/skills"
CLAUDE_SKILLS_RENDERER: Final[str] = "claude_code.skills@1"
SKILL_LISTING_MAX_CHARS: Final[int] = 1536


def render_skills(inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
    """Use the shared skill renderer so invocation frontmatter is identical across clients."""
    return render_skill_files(inputs, prefix=CLAUDE_SKILLS_PREFIX, renderer=CLAUDE_SKILLS_RENDERER)
