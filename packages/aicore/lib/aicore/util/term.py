"""Shared terminal output and termination helpers."""
import sys

from . import timefmt


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg):
    print(f"WARN: {msg}", file=sys.stderr)


def now_iso():
    return timefmt.utc_stamp()


def parse_iso(s):
    """Parse ISO-8601 into an aware datetime, returning ``None`` on failure.

    Normalize ``Z`` and fractional seconds before ``fromisoformat``.
    """
    return timefmt.parse_rfc3339(s, convert=False)


def confirm(prompt):
    if not sys.stdin.isatty():
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
