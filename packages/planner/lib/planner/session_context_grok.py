"""Grok Build raw-runtime adapter for :mod:`planner.session_context`.

``grok`` and ``agent`` are the same Grok binary on PATH. Cursor's CLI is
``cursor-agent``; identity here is ``GROK_SESSION_ID``, never process name alone.
"""
from __future__ import annotations

import os

from planner.session_context import SessionContext, SessionContextError


_ENVIRONMENT_VARIABLE = "GROK_SESSION_ID"


def current() -> SessionContext | None:
    """Return Grok's observed session identity, if this is a Grok process."""
    value = os.environ.get(_ENVIRONMENT_VARIABLE)
    if value is None:
        return None
    session_id = value.strip()
    if not session_id or any(char.isspace() for char in session_id):
        raise SessionContextError(
            "Grok session context is invalid: GROK_SESSION_ID is empty or contains a space")
    return SessionContext(provider="grok", session_id=session_id, source=_ENVIRONMENT_VARIABLE)
