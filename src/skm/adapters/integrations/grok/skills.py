"""Skill directory renderer for ``.agents/skills/<skill_key>/...`` (integrations §4.8, §5.2)."""

from typing import Final

from skm.adapters.integrations.codex.skills import (
    SKILL_LISTING_MAX_CHARS,
)
from skm.adapters.integrations.codex.skills import (
    render_skills as render_skill_files,
)
from skm.modules.integrations.domain.desired import DesiredFile, ProjectionInputs

__all__ = [
    "GROK_SKILLS_PREFIX",
    "GROK_SKILLS_RENDERER",
    "SKILL_LISTING_MAX_CHARS",
    "render_skills",
]

GROK_SKILLS_PREFIX: Final[str] = ".agents/skills"
GROK_SKILLS_RENDERER: Final[str] = "grok.skills@1"


def render_skills(inputs: ProjectionInputs) -> tuple[DesiredFile, ...]:
    """Render managed skill files using the shared projection format."""
    return render_skill_files(inputs, prefix=GROK_SKILLS_PREFIX, renderer=GROK_SKILLS_RENDERER)
