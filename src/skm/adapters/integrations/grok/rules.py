"""Grok ``.grok/rules/<slug>.md`` plain Markdown rule renderer (integrations §4.8, §5.1)."""

from __future__ import annotations

import re
from typing import Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import SourceRef
from skm.modules.integrations.domain.desired import DesiredFile
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId

__all__ = [
    "GROK_RULES_PREFIX",
    "GROK_RULES_RENDERER",
    "render_markdown_rule",
]

GROK_RULES_PREFIX: Final[str] = ".grok/rules"
GROK_RULES_RENDERER: Final[str] = "grok.rules@1"

_RULE_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def render_markdown_rule(
    slug: str,
    *,
    body: str,
    surface: Surface = Surface.INSTRUCTIONS,
    source_refs: tuple[SourceRef, ...] = (),
    renderer: str = GROK_RULES_RENDERER,
) -> DesiredFile:
    """Render a single ``.grok/rules/<slug>.md`` ``MANAGED_FILE`` entry."""
    if not _RULE_SLUG_RE.fullmatch(slug):
        raise ValidationFailed(
            ErrorCode.INTEGRATION_UNSAFE_TARGET,
            f"invalid Grok Markdown rule slug {slug!r}",
            details={"rule_slug": slug},
        )
    normalized = body.replace("\r\n", "\n").strip("\n")
    if not normalized.strip():
        raise ValidationFailed(
            ErrorCode.INTEGRATION_BOUNDARY_INVALID,
            f"Grok Markdown rule {slug!r} requires a non-empty body",
            details={"rule_slug": slug},
        )

    managed_bytes = f"{normalized}\n".encode()
    return DesiredFile(
        target=TargetId.GROK,
        surface=surface,
        relative_path=f"{GROK_RULES_PREFIX}/{slug}.md",
        boundary=ManagedBoundary(Ownership.MANAGED_FILE),
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=source_refs,
        renderer=renderer,
    )
