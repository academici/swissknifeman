"""Cursor raw-runtime adapter for :mod:`task.session_context`."""
from __future__ import annotations

import os

from task.session_context import SessionContext, SessionContextError


_ENVIRONMENT_VARIABLE = "CURSOR_CONVERSATION_ID"


def current() -> SessionContext | None:
    """Return Cursor's observed conversation identity, if this is a Cursor process."""
    value = os.environ.get(_ENVIRONMENT_VARIABLE)
    if value is None:
        return None
    session_id = value.strip()
    if not session_id or any(char.isspace() for char in session_id):
        raise SessionContextError(
            "Cursor session context is invalid: CURSOR_CONVERSATION_ID is empty or contains a space")
    return SessionContext(provider="cursor", session_id=session_id, source=_ENVIRONMENT_VARIABLE)
