"""Shared terminal output and termination helpers."""
import re
import sys
from datetime import datetime, timezone

_FRAC_RE = re.compile(r"\.(\d+)")


def die(msg, code=1):
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(code)


def warn(msg):
    print(f"WARN: {msg}", file=sys.stderr)


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(s):
    """Parse ISO-8601 into an aware datetime, returning ``None`` on failure.

    Normalize ``Z`` and fractional seconds before ``fromisoformat``.
    """
    if not isinstance(s, str):
        return None
    t = s.strip()
    if not t:
        return None
    t = _FRAC_RE.sub(lambda m: "." + (m.group(1) + "000000")[:6], t, count=1)
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def confirm(prompt):
    if not sys.stdin.isatty():
        return False
    return input(f"{prompt} [y/N] ").strip().lower() in ("y", "yes")
