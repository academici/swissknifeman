"""Reading ``planner.plan.closed``: the data the subscriber expects, checked against its contract fixtures.

The emitting module defines the event; this module states what the consumer reads. Only ``plan_id`` and
``title`` are required, every other known field is optional and must have its type when present, and unknown
fields are ignored on every level so that the emitter can grow the data without breaking the subscriber.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Any, Dict, Mapping, Optional, Tuple

from aicore.ext import events as _events

from . import errors
from .errors import BrainError

EVENT_TYPE = "planner.plan.closed"
IGNORED = "EVENT_TYPE_IGNORED"
COUNT_KEYS = ("items", "done", "done_with_deviations", "cancelled")

_RFC3339 = re.compile(r"^(\d{4})-(\d{2})-(\d{2})[Tt ](\d{2}):(\d{2}):(\d{2})(?:\.(\d+))?([Zz]|[+-]\d{2}:\d{2})$")


@dataclass(frozen=True)
class Phase:
    id: str
    title: str
    status: str


@dataclass(frozen=True)
class PlanClosed:
    """A closed plan as the subscriber reads it, with the identity of the event that announced it."""

    event_id: str
    event_source: str
    event_time: str
    plan_id: str
    title: str
    short_id: Optional[str] = None
    status: Optional[str] = None
    goal: Optional[str] = None
    closed_at: Optional[str] = None
    repository: Optional[str] = None
    phases: Tuple[Phase, ...] = ()
    counts: Tuple[Tuple[str, int], ...] = ()

    @property
    def closed(self) -> str:
        """The closing time as written: ``closed_at``, else the time of the event."""
        return self.closed_at or self.event_time

    def closed_utc(self) -> datetime.datetime:
        """The closing time as an aware UTC datetime."""
        return parse_time(self.closed, "closed_at" if self.closed_at else "time")


def _invalid(message: str) -> BrainError:
    return BrainError(errors.EVENT_DATA_INVALID, message)


def parse_time(text: str, field: str) -> datetime.datetime:
    """An RFC 3339 timestamp as an aware UTC datetime; ``EVENT_DATA_INVALID`` when it is not one."""
    match = _RFC3339.match(text)
    if not match:
        raise _invalid(f"{field} is not an RFC 3339 timestamp: {text!r}")
    year, month, day, hour, minute, second = (int(match.group(i)) for i in range(1, 7))
    fraction = (match.group(7) or "0")[:6].ljust(6, "0")
    zone = match.group(8)
    try:
        offset = datetime.timedelta(0)
        if zone not in ("Z", "z"):
            sign = 1 if zone[0] == "+" else -1
            offset = sign * datetime.timedelta(hours=int(zone[1:3]), minutes=int(zone[4:6]))
        moment = datetime.datetime(year, month, day, hour, minute, min(second, 59), int(fraction),
                                   tzinfo=datetime.timezone.utc)
    except (ValueError, OverflowError):
        raise _invalid(f"{field} is not a valid timestamp: {text!r}") from None
    return moment - offset


def _text(data: Mapping[str, Any], key: str, *, required: bool = False) -> Optional[str]:
    if key not in data or data[key] is None:
        if required:
            raise _invalid(f"data.{key} is required")
        return None
    value = data[key]
    if not isinstance(value, str):
        raise _invalid(f"data.{key} must be a string")
    if required and not value.strip():
        raise _invalid(f"data.{key} must not be empty")
    return value


def _phases(data: Mapping[str, Any]) -> Tuple[Phase, ...]:
    value = data.get("phases")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise _invalid("data.phases must be an array")
    found = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise _invalid(f"data.phases[{index}] must be an object")
        fields = []
        for key in ("id", "title", "status"):
            text = item.get(key, "")
            if not isinstance(text, str):
                raise _invalid(f"data.phases[{index}].{key} must be a string")
            fields.append(text)
        found.append(Phase(*fields))
    return tuple(found)


def _counts(data: Mapping[str, Any]) -> Tuple[Tuple[str, int], ...]:
    value = data.get("counts")
    if value is None:
        return ()
    if not isinstance(value, dict):
        raise _invalid("data.counts must be an object")
    found = []
    for key in COUNT_KEYS:
        if key in value:
            number = value[key]
            if isinstance(number, bool) or not isinstance(number, int) or number < 0:
                raise _invalid(f"data.counts.{key} must be a non-negative integer")
            found.append((key, number))
    return tuple(found)


def parse_plan_closed(doc: Any) -> Tuple[Optional[PlanClosed], Optional[str]]:
    """Read an ``event/v1`` document as a closed plan.

    Returns ``(plan, None)``, or ``(None, "EVENT_TYPE_IGNORED")`` for an event of another type. Anything that is not a
    valid ``event/v1`` document of ``specversion`` ``1.0``, or whose data lacks ``plan_id`` or ``title`` or gives
    a known field the wrong type, raises ``BrainError("EVENT_DATA_INVALID")`` (exit 65: do not retry).
    """
    if not isinstance(doc, dict):
        raise _invalid("the event is not a JSON object")
    version = doc.get("specversion")
    if version != _events.SPECVERSION:
        raise _invalid(f"specversion {version!r} is not supported; this subscriber reads {_events.SPECVERSION!r}")
    problems = _events.validate_document(doc)
    if problems:
        raise _invalid(f"the event is not a valid event/v1 document: {problems[0]}")
    event = _events.Event.from_json(doc)
    if event.type != EVENT_TYPE:
        return None, IGNORED
    data: Optional[Dict[str, Any]] = event.data
    if not isinstance(data, dict):
        raise _invalid("data must be an object")
    closed_at = _text(data, "closed_at")
    if closed_at is not None:
        parse_time(closed_at, "closed_at")
    parse_time(event.time, "time")
    plan = PlanClosed(
        event_id=event.id, event_source=event.source, event_time=event.time,
        plan_id=_text(data, "plan_id", required=True) or "", title=_text(data, "title", required=True) or "",
        short_id=_text(data, "short_id"), status=_text(data, "status"), goal=_text(data, "goal"),
        closed_at=closed_at, repository=_text(data, "repository"), phases=_phases(data), counts=_counts(data))
    artifacts = data.get("artifacts")
    if artifacts is not None and not isinstance(artifacts, list):
        raise _invalid("data.artifacts must be an array")
    return plan, None
