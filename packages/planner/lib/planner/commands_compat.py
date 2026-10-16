"""Parsing of the deprecated `task:<id>` command spelling for one minor release.

Compatibility alias: remove in the next minor release.
"""
from __future__ import annotations

import sys

from planner import COMMAND_NAMESPACE, LEGACY_NAMESPACE

_LEGACY_PREFIX = f"{LEGACY_NAMESPACE}:"


def normalize_command_id(text: str) -> tuple[str, bool]:
    """Map `task:<id>` and `/task:<id>` to `planner:<id>`; return `(text, deprecated)`, other text unchanged."""
    if not isinstance(text, str):
        return text, False
    slash = "/" if text.startswith("/") else ""
    bare = text[len(slash):]
    if not bare.startswith(_LEGACY_PREFIX):
        return text, False
    return f"{slash}{COMMAND_NAMESPACE}:{bare[len(_LEGACY_PREFIX):]}", True


def warn_deprecated(text: str) -> None:
    """Write the one-line `TASK_COMMAND_DEPRECATED` warning for a legacy spelling to stderr."""
    bare = text.lstrip("/")
    print(f"TASK_COMMAND_DEPRECATED: {bare} is deprecated; use "
          f"{COMMAND_NAMESPACE}:{bare[len(_LEGACY_PREFIX):]}", file=sys.stderr)
