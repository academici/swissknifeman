"""Codex-only raw-runtime adapter for ``task.session_context``."""
from __future__ import annotations

import os

from task.session_context import SessionContext, SessionContextError


_ENVIRONMENT_VARIABLE = "CODEX_THREAD_ID"


def current() -> SessionContext | None:
    """Return Codex's observed thread identity without exposing raw runtime details."""
    value = os.environ.get(_ENVIRONMENT_VARIABLE)
    if value is None:
        return None
    session_id = value.strip()
    if not session_id or any(char.isspace() for char in session_id):
        raise SessionContextError("Codex session context is invalid: CODEX_THREAD_ID is empty or contains a space")
    return SessionContext(provider="codex", session_id=session_id, source="CODEX_THREAD_ID")
