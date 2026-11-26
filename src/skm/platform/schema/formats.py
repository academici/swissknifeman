"""Own FormatChecker: no optional validator packages, every supported format is listed here (§3.3).

A ``format`` keyword that is not in ``KNOWN_FORMATS`` is rejected when the registry loads, so a schema
can never rely on a check that would silently not run.
"""

import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Final
from urllib.parse import urlsplit
from uuid import UUID

from jsonschema import FormatChecker

__all__ = [
    "FORMAT_CHECKER",
    "KNOWN_FORMATS",
    "is_date",
    "is_date_time",
    "is_duration_seconds",
    "is_email",
    "is_regex",
    "is_uri",
    "is_uuid",
]

_DATE_TIME = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?(?:Z|[+-][0-9]{2}:[0-9]{2})"
)
_DATE = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
_SCHEME = re.compile(r"[a-z][a-z0-9+.-]*")
_SECONDS = re.compile(r"[0-9]+")


def _has_space(value: str) -> bool:
    return any(char.isspace() for char in value)


def is_date_time(value: object) -> bool:
    """RFC 3339: ``T`` separator and a mandatory ``Z`` or ``±HH:MM`` offset."""
    if not isinstance(value, str) or _DATE_TIME.fullmatch(value) is None:
        return False
    # RFC 3339 hours stop at 23; Python 3.15 parses ISO 8601's 24:00:00 as the next midnight.
    if value[11:13] > "23":
        return False
    normalized = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.fromisoformat(normalized)
    except ValueError:
        return False
    return True


def is_date(value: object) -> bool:
    """Exactly ``YYYY-MM-DD`` and a real calendar date."""
    if not isinstance(value, str) or _DATE.fullmatch(value) is None:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def is_uuid(value: object) -> bool:
    """Canonical hyphenated form only (letter case is free)."""
    if not isinstance(value, str):
        return False
    try:
        return str(UUID(value)) == value.lower()
    except ValueError:
        return False


def is_uri(value: object) -> bool:
    """A scheme in ``[a-z][a-z0-9+.-]*`` and no whitespace (minimal check)."""
    if not isinstance(value, str) or not value or _has_space(value):
        return False
    try:
        parts = urlsplit(value)
    except ValueError:
        return False
    return _SCHEME.fullmatch(parts.scheme) is not None


def is_email(value: object) -> bool:
    """One ``@``, non-empty local and domain parts, no whitespace (minimal check)."""
    if not isinstance(value, str) or _has_space(value) or value.count("@") != 1:
        return False
    local, _, domain = value.partition("@")
    return bool(local) and bool(domain)


def is_duration_seconds(value: object) -> bool:
    """A non-negative integer written in decimal digits (env-override values)."""
    return isinstance(value, str) and _SECONDS.fullmatch(value) is not None


def is_regex(value: object) -> bool:
    """A pattern that Python ``re`` compiles; schemas of the policy module declare ``format: regex``."""
    if not isinstance(value, str):
        return False
    try:
        re.compile(value)
    except re.error:
        return False
    return True


def _strings_only(check: Callable[[object], bool]) -> Callable[[object], bool]:
    """JSON Schema applies ``format`` to strings only; other instance types are not this keyword's concern."""

    def wrapped(value: object) -> bool:
        return not isinstance(value, str) or check(value)

    return wrapped


_CHECKS: Final = {
    "date-time": is_date_time,
    "date": is_date,
    "uuid": is_uuid,
    "uri": is_uri,
    "email": is_email,
    "duration-seconds": is_duration_seconds,
    "regex": is_regex,
}

FORMAT_CHECKER: Final = FormatChecker(formats=())
for _name, _check in _CHECKS.items():
    FORMAT_CHECKER.checks(_name)(_strings_only(_check))

KNOWN_FORMATS: Final = frozenset(FORMAT_CHECKER.checkers)
