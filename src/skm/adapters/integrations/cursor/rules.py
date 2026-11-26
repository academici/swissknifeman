"""Cursor ``.cursor/rules/<slug>.mdc`` rule renderer and validator (integrations §4.8)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Final

from skm.adapters.integrations._render import markdown_rules
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.modules.integrations.domain.contracts import SourceRef
from skm.modules.integrations.domain.desired import DesiredFile
from skm.modules.integrations.domain.ownership import ManagedBoundary, Ownership, sha256_tagged
from skm.modules.integrations.domain.target import Surface, TargetId

__all__ = [
    "CURSOR_RULES_PREFIX",
    "CURSOR_RULES_RENDERER",
    "render_mdc_rule",
    "validate_mdc_rule",
]

CURSOR_RULES_PREFIX: Final[str] = ".cursor/rules"
CURSOR_RULES_RENDERER: Final[str] = "cursor.rules@1"

_RULE_SLUG_RE: Final[re.Pattern[str]] = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def render_mdc_rule(
    slug: str,
    *,
    description: str,
    body: str,
    always_apply: bool | None = True,
    globs: str | Sequence[str] | None = None,
    surface: Surface = Surface.INSTRUCTIONS,
    source_refs: tuple[SourceRef, ...] = (),
    renderer: str = CURSOR_RULES_RENDERER,
) -> DesiredFile:
    """Render a single ``.cursor/rules/<slug>.mdc`` ``MANAGED_FILE`` entry."""
    if not _RULE_SLUG_RE.fullmatch(slug):
        raise ValidationFailed(
            ErrorCode.INTEGRATION_UNSAFE_TARGET,
            f"invalid Cursor MDC rule slug {slug!r}",
            details={"rule_slug": slug},
        )
    if not description.strip():
        raise ValidationFailed(
            ErrorCode.INTEGRATION_BOUNDARY_INVALID,
            f"Cursor MDC rule {slug!r} requires a non-empty description",
            details={"rule_slug": slug},
        )

    managed_bytes = markdown_rules.dumps_bytes(
        description=description,
        body=body,
        always_apply=always_apply,
        globs=globs,
    )
    return DesiredFile(
        target=TargetId.CURSOR,
        surface=surface,
        relative_path=f"{CURSOR_RULES_PREFIX}/{slug}.mdc",
        boundary=ManagedBoundary(Ownership.MANAGED_FILE),
        managed_bytes=managed_bytes,
        managed_digest=sha256_tagged(managed_bytes),
        source_refs=source_refs,
        renderer=renderer,
    )


def validate_mdc_rule(content: bytes | str, *, require_always_apply: bool = False) -> dict[str, object]:
    """Validate UTF-8 ``.mdc`` frontmatter conformance or raise ``INTEGRATION_BOUNDARY_INVALID``."""
    try:
        text = content.decode("utf-8") if isinstance(content, bytes) else content
        return markdown_rules.validate_frontmatter(text, require_always_apply=require_always_apply)
    except (UnicodeDecodeError, ValueError) as exc:
        raise ValidationFailed(
            ErrorCode.INTEGRATION_BOUNDARY_INVALID,
            f"invalid Cursor MDC rule frontmatter: {exc}",
        ) from exc
