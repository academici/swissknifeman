"""Confirmation of a risky request by an HMAC token bound to the request, the backend epoch and the session secret.

The first request answers ``428 CONFIRMATION_REQUIRED`` with ``details {confirm_token, risk, summary}``; the UI
shows the summary and repeats the same request with ``confirm_token``. A token from another epoch, purpose or
payload does not match.
"""
from __future__ import annotations

import hashlib
import hmac
from typing import Any, Optional

from aicore.util.digest import canonical_json_bytes

from ..errors import GuiError


def token(secret: str, epoch: str, purpose: str, payload: Any) -> str:
    message = canonical_json_bytes({"purpose": purpose, "epoch": epoch, "payload": payload})
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def require(state, purpose: str, payload: Any, given: Optional[str], *, risk: str, summary: str) -> None:
    """Return when ``given`` confirms this request; raise ``CONFIRMATION_REQUIRED`` otherwise."""
    expected = token(state.sessions.secret, state.epoch, purpose, payload)
    if isinstance(given, str) and hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
        return
    raise GuiError("CONFIRMATION_REQUIRED", "this request needs a confirmation",
                   details={"confirm_token": expected, "risk": risk, "summary": summary})
