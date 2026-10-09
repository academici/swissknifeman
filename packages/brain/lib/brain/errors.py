"""brain errors: one exception with a stable code."""
from __future__ import annotations

VAULT_NOT_FOUND = "VAULT_NOT_FOUND"
VAULT_MISSING = "VAULT_MISSING"
PROJECT_NOT_IN_VAULT = "PROJECT_NOT_IN_VAULT"
CATALOG_INVALID = "CATALOG_INVALID"
CATALOG_AMBIGUOUS = "CATALOG_AMBIGUOUS"
BRAIN_LEGACY_CONFIG = "BRAIN_LEGACY_CONFIG"
BRAIN_LEGACY_ENV = "BRAIN_LEGACY_ENV"
CONFIG_INVALID = "CONFIG_INVALID"
CONFIG_NOTES_FOLDER = "CONFIG_NOTES_FOLDER"


class BrainError(Exception):
    """A brain failure with a stable ``code``; ``str()`` is ``<code>: <message>``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
