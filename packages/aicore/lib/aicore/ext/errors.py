"""Errors of the extension layer: one exception type with a stable code."""
from __future__ import annotations


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
})
