"""The project of an orch command (``aicore.state.resolve_project``): the root bound by the project-local launcher
(``python3 -I .swissknifeman/launcher.py orch ...``; a ``--project`` naming another folder is ``PROJECT_CONTEXT_CONFLICT``),
else ``--project DIR``, else ``SKM_PROJECT_ROOT``, else the nearest ``.git`` or ``.swissknifeman`` above the working
directory. A command that writes project state needs one and stops with ``PROJECT_CONTEXT_REQUIRED`` without it."""
from __future__ import annotations

from pathlib import Path

from aicore.state import ProjectContext, ProjectContextRequired, resolve_project


def find(explicit: str | Path | None = None) -> ProjectContext | None:
    """The project context of the working directory, or ``None`` without one. A named project that is not a directory
    raises ``ProjectContextRequired``."""
    return resolve_project(Path.cwd(), explicit=explicit)


def require(explicit: str | Path | None = None) -> ProjectContext:
    """:func:`find`, or ``ProjectContextRequired`` (``PROJECT_CONTEXT_REQUIRED``) with the hint to pass ``--project DIR``."""
    context = find(explicit)
    if context is None:
        raise ProjectContextRequired(Path.cwd())
    return context
