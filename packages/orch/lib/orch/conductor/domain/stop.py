"""The honest stop of a conductor run."""
from __future__ import annotations


class Stop(Exception):
    """An honest stop of the run: a stable code and what happened."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
