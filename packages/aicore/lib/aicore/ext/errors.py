"""Errors of the extension layer: one exception type with a stable code, and one-per-process warnings."""
from __future__ import annotations

import sys
from typing import Set, Tuple


class ExtError(Exception):
    """A refusal or failure of the extension layer; ``str()`` is ``<CODE>: <message>``."""

    def __init__(self, code: str, message: str):
        super().__init__(code, message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


# Codes raised as ``ExtError`` or reported in results by the extension layer; a code is never renamed.
CODES = frozenset({
    "PROCESS_SPAWN",
    "PROCESS_TIMEOUT",
    "PROCESS_EXIT",
    "PROTOCOL_STDOUT",
    "PROTOCOL_STDOUT_TOO_LARGE",
    "PLUGIN_SECRET_UNSUPPORTED",
    "PLUGIN_PROFILE_UNAVAILABLE",
    "PLUGIN_MANIFEST_INVALID",
    "PLUGIN_PROTOCOL_UNSUPPORTED",
    "PLUGIN_REQUIRES_UNSATISFIED",
    "PLUGIN_ID_MISMATCH",
    "PLUGIN_POINT_UNKNOWN",
    "PLUGIN_HANDSHAKE_MISMATCH",
    "PLUGIN_RESPONSE_INVALID",
    "PLUGIN_NOT_FOUND",
    "PLUGIN_SECRET_UNRESOLVED",
    "OVERLAY_SLOT_UNKNOWN",
    "OVERLAY_TOO_LARGE",
    "OVERLAY_MISSING",
    "OVERLAY_INVALID",
    "EVENT_INVALID",
    "EVENT_SECRET",
    "EVENT_DATA_TOO_LARGE",
    "EVENT_NOT_FOUND",
    "EVENT_TYPE_UNDECLARED",
    "EVENT_MALFORMED",
    "EVENT_LINE_TOO_LONG",
    "EVENT_VERSION_UNSUPPORTED",
    "JOURNAL_LOCKED",
    "JOURNAL_IO",
    "JOURNAL_LINE_TOO_LARGE",
    "CONFIG_INVALID",
    "UNIT_INVALID",
    "SUBSCRIPTION_INVALID",
    "SUBSCRIPTION_UNKNOWN",
    "SUBSCRIPTION_INACTIVE",
    "PLUGIN_UNAVAILABLE",
    "DELIVERY_LOCKED",
    "DELIVERY_IO",
    "DELIVERY_SPAWN",
    "DELIVERY_CURSORS_INVALID",
    "JOURNAL_RESET",
})

_WARNED: Set[Tuple[str, str]] = set()


def warn_once(code: str, message: str, *, key: str = "") -> bool:
    """Write ``aicore: <CODE>: <message>`` to stderr once per process for a ``(code, key)`` pair.

    Returns True when the warning was written. ``key`` tells apart several subjects of one code.
    """
    marker = (code, key)
    if marker in _WARNED:
        return False
    _WARNED.add(marker)
    try:
        sys.stderr.write(f"aicore: {code}: {message}\n")
        sys.stderr.flush()
    except (OSError, ValueError):  # a closed stderr must not break the caller
        pass
    return True


def reset_warnings() -> None:
    """Forget the warnings already written (for tests)."""
    _WARNED.clear()
