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
