"""Claude Code raw-runtime adapter for :mod:`task.session_context`."""
from __future__ import annotations

import os

from task.session_context import SessionContext, SessionContextError


_ENVIRONMENT_VARIABLE = "CLAUDE_CODE_SESSION_ID"


def current() -> SessionContext | None:
    """Return Claude Code's observed session identity, if this is a Claude process."""
    value = os.environ.get(_ENVIRONMENT_VARIABLE)
    if value is None:
        return None
    session_id = value.strip()
    if not session_id or any(char.isspace() for char in session_id):
        raise SessionContextError(
            "Claude session context is invalid: CLAUDE_CODE_SESSION_ID is empty or contains a space")
    return SessionContext(
        provider="claude-code", session_id=session_id, source=_ENVIRONMENT_VARIABLE)
