"""Antigravity raw-runtime adapter for :mod:`planner.session_context`."""
from __future__ import annotations

import os

from planner.session_context import SessionContext, SessionContextError


_ENVIRONMENT_VARIABLE = "ANTIGRAVITY_SESSION_ID"


def current() -> SessionContext | None:
    """Return Antigravity's observed session identity, if this is an Antigravity process."""
    value = os.environ.get(_ENVIRONMENT_VARIABLE)
    if value is None:
        return None
    session_id = value.strip()
    if not session_id or any(char.isspace() for char in session_id):
        raise SessionContextError(
            "Antigravity session context is invalid: ANTIGRAVITY_SESSION_ID is empty or contains a space")
    return SessionContext(provider="antigravity", session_id=session_id, source=_ENVIRONMENT_VARIABLE)
