"""The project of an orch command: ``--project DIR``, else ``SKM_PROJECT_ROOT``, else the nearest ``.git`` or
``.swissknifeman`` above the working directory (``aicore.state.resolve_project``). A command that writes project state
needs one and stops with ``PROJECT_CONTEXT_REQUIRED`` without it."""
from __future__ import annotations

from pathlib import Path

from aicore.state import ProjectContext, ProjectContextRequired, resolve_project


def find(explicit: str | Path | None = None) -> ProjectContext | None:
    """The project context of the working directory, or ``None`` (a named folder that does not exist is no project)."""
    context = resolve_project(Path.cwd(), explicit=explicit)
    return context if context is not None and context.root.is_dir() else None


def require(explicit: str | Path | None = None) -> ProjectContext:
    """:func:`find`, or ``ProjectContextRequired`` (``PROJECT_CONTEXT_REQUIRED``) with the hint to pass ``--project DIR``."""
    context = find(explicit)
    if context is None:
        raise ProjectContextRequired(explicit if explicit else Path.cwd())
    return context
