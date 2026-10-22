"""UTC-aware time helpers: one writer format and one tolerant RFC 3339 reader. stdlib only.

Every datetime that leaves this module is timezone-aware. A naive input is read as UTC, never as local time, so the
result does not depend on ``TZ``.
"""
from __future__ import annotations

import math
import re
from datetime import datetime, timezone
from typing import Optional, Union

STAMP_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_FRACTION = re.compile(r"\.(\d+)")

Moment = Union[datetime, str]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_stamp(moment: Union[datetime, int, float, None] = None) -> str:
    """``%Y-%m-%dT%H:%M:%SZ`` of ``moment`` (a datetime, an epoch in seconds, or now); a naive datetime is UTC."""
    if moment is None:
        moment = utc_now()
    elif not isinstance(moment, datetime):
        moment = datetime.fromtimestamp(math.floor(moment), timezone.utc)  # whole seconds, truncated as ``gmtime`` does
    elif moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).strftime(STAMP_FORMAT)


def parse_rfc3339(text: object, *, convert: bool = True) -> Optional[datetime]:
    """An aware datetime from an RFC 3339 / ISO 8601 text (``Z`` or an offset, any number of fraction digits,
    truncated to microseconds), in UTC; a naive text is UTC. ``None`` when ``text`` is not a string or does not parse.
    ``convert=False`` keeps the offset the text names."""
    if not isinstance(text, str):
        return None
    value = text.strip()
    if not value:
        return None
    value = _FRACTION.sub(lambda match: "." + (match.group(1) + "000000")[:6], value, count=1)
    if value.endswith(("Z", "z")):
        value = value[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc) if convert else parsed


def _moment(value: Moment) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
    return parse_rfc3339(value)


def epoch(text: Moment) -> Optional[float]:
    """Seconds since the Unix epoch of a text (or datetime); ``None`` when it does not parse."""
    moment = _moment(text)
    return None if moment is None else moment.timestamp()


def seconds_between(start: Moment, end: Moment) -> Optional[float]:
    """Seconds from ``start`` to ``end`` (texts or datetimes); ``None`` when either does not parse."""
    first, last = _moment(start), _moment(end)
    if first is None or last is None:
        return None
    return (last - first).total_seconds()
