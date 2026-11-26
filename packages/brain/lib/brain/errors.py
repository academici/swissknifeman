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
DOCS_CONFLICT = "DOCS_CONFLICT"
EVENT_DATA_INVALID = "EVENT_DATA_INVALID"
VAULT_UNAVAILABLE = "VAULT_UNAVAILABLE"
NOTE_IO = "NOTE_IO"
LEDGER_LOCKED = "LEDGER_LOCKED"

# Exit statuses (sysexits): a subscriber that gets bad event data must not be retried (65), a temporary
# failure of the machine (vault, disk, lock, configuration) is retried by the next delivery (75).
EXIT_DATA_INVALID = 65
EXIT_TEMPORARY = 75
_TEMPORARY = frozenset({VAULT_UNAVAILABLE, NOTE_IO, LEDGER_LOCKED, CONFIG_INVALID, CONFIG_NOTES_FOLDER})


def exit_status(code: str) -> int:
    """The process exit status of a failure code: 65 bad event data, 75 temporary failure, else 1."""
    if code == EVENT_DATA_INVALID:
        return EXIT_DATA_INVALID
    return EXIT_TEMPORARY if code in _TEMPORARY else 1


class BrainError(Exception):
    """A brain failure with a stable ``code``; ``str()`` is ``<code>: <message>``."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
