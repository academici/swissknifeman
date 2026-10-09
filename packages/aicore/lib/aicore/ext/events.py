"""Events: the envelope, ``build_event``, ``emit`` and reading the journal.

An event follows ``event/v1`` (a CloudEvents 1.0 subset). ``emit`` is for the *source* of an event: it
raises :class:`~aicore.ext.errors.ExtError` only when the call itself is wrong (type, source, data, size,
a ``Secret``) and otherwise never breaks the caller: a failing journal gives a warning and ``None``
(``strict=True`` raises instead). Delivery to subscribers is not part of this module yet, so ``emit`` only
journals, as with ``delivery="off"``. stdlib and ``aicore`` only.
"""
from __future__ import annotations

import dataclasses
import datetime
import fnmatch
import json
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from ..config import Secret
from ..util import schema as _schema
from ..util.digest import canonical_json_bytes
from . import journal
from .errors import ExtError, warn_once

MAX_DATA_BYTES = 65536
SPECVERSION = "1.0"
SOURCE_PREFIX = "urn:swissknifeman:module:"
DELIVERY_MODES = ("background", "sync", "off")
_SCHEMA_DIR = Path(__file__).resolve().parents[3] / "schemas" / "event" / "v1"
_MODULE_ID = re.compile(r"^[a-z][a-z0-9-]*$")
_TYPE = re.compile(r"^[a-z][a-z0-9-]*(\.[a-z][a-z0-9-]*){2,}$")
_ID = re.compile(r"^[0-9a-f]{32}$")
# Envelope fields in the order of the event/v1 table; everything else is an extension attribute.
_FIELDS = ("specversion", "id", "source", "type", "time", "subject", "datacontenttype", "dataschema", "data",
           "traceparent", "causationid", "correlationid")

PathLike = Union[str, "os.PathLike[str]"]
Problem = Dict[str, Any]


@dataclass(frozen=True)
class Event:
    """One event; ``offset`` is its byte address in the journal when it came from or went to one."""

    id: str
    source: str
    type: str
    time: str
    subject: Optional[str] = None
    data: Optional[Dict[str, Any]] = None
    dataschema: Optional[str] = None
    traceparent: Optional[str] = None
    causationid: Optional[str] = None
    correlationid: Optional[str] = None
    extensions: Dict[str, Any] = field(default_factory=dict)
    offset: Optional[int] = None

    @property
    def module(self) -> str:
        """The id of the emitting module (``source`` without its URN prefix)."""
        return self.source[len(SOURCE_PREFIX):] if self.source.startswith(SOURCE_PREFIX) else self.source

    def to_json(self) -> Dict[str, Any]:
        """The ``event/v1`` document: only the fields that are set, in table order, then the extensions."""
        values = {
            "specversion": SPECVERSION, "id": self.id, "source": self.source, "type": self.type,
            "time": self.time, "subject": self.subject,
            "datacontenttype": "application/json" if self.data is not None else None,
            "dataschema": self.dataschema, "data": self.data, "traceparent": self.traceparent,
            "causationid": self.causationid, "correlationid": self.correlationid,
        }
        out = {name: values[name] for name in _FIELDS if values[name] is not None}
        for name in sorted(self.extensions):
            out[name] = self.extensions[name]
        return out

    @classmethod
    def from_json(cls, doc: Mapping[str, Any], offset: Optional[int] = None) -> "Event":
        """The event of a valid ``event/v1`` document; unknown attributes go to ``extensions``."""
        extensions = {name: value for name, value in doc.items() if name not in _FIELDS}
        return cls(id=doc["id"], source=doc["source"], type=doc["type"], time=doc["time"],
                   subject=doc.get("subject"), data=doc.get("data"), dataschema=doc.get("dataschema"),
                   traceparent=doc.get("traceparent"), causationid=doc.get("causationid"),
                   correlationid=doc.get("correlationid"), extensions=extensions, offset=offset)


_registry: Optional[Tuple[Any, str]] = None


def _contract() -> Tuple[Any, str]:
    global _registry
    if _registry is None:
        _registry = _schema.load_contract(_SCHEMA_DIR)
    return _registry


def validate_document(doc: object) -> List[str]:
    """Messages of every ``event/v1`` violation of ``doc`` (empty when it is valid)."""
    registry, kind = _contract()
    return [issue.message for issue in _schema.validate(doc, kind, registry)]


def _now_text(now: Union[datetime.datetime, str, None]) -> str:
    if isinstance(now, str):
        return now
    moment = datetime.datetime.now(datetime.timezone.utc) if now is None else now
    if moment.tzinfo is not None:
        moment = moment.astimezone(datetime.timezone.utc)
    return f"{moment.strftime('%Y-%m-%dT%H:%M:%S')}.{moment.microsecond // 1000:03d}Z"


def _contains_secret(value: object) -> bool:
    stack = [value]
    seen = set()
    while stack:
        item = stack.pop()
        if isinstance(item, Secret):
            return True
        if isinstance(item, (dict, list, tuple)):
            if id(item) in seen:
                continue
            seen.add(id(item))
            if isinstance(item, dict):
                stack.extend(item.keys())
                stack.extend(item.values())
            else:
                stack.extend(item)
    return False


def build_event(type: str, data: Optional[Mapping[str, Any]] = None, *, source: str,
                subject: Optional[str] = None, dataschema: Optional[str] = None,
                traceparent: Optional[str] = None, causationid: Optional[str] = None,
                correlationid: Optional[str] = None, now: Union[datetime.datetime, str, None] = None,
                id: Optional[str] = None) -> Event:
    """Build and validate an event; ``ExtError`` ``EVENT_INVALID``, ``EVENT_SECRET`` or ``EVENT_DATA_TOO_LARGE``.

    ``source`` is a module id, ``type`` is ``<module>.<subject>.<verb>`` and starts with that id.
    """
    if not isinstance(source, str) or not _MODULE_ID.match(source):
        raise ExtError("EVENT_INVALID", "source must be a module id such as 'planner'")
    if not isinstance(type, str) or not _TYPE.match(type):
        raise ExtError("EVENT_INVALID", "type must look like <module>.<subject>.<verb>")
    if type.split(".")[0] != source:
        raise ExtError("EVENT_INVALID", f"type {type!r} must start with the source module {source!r}")
    payload: Optional[Dict[str, Any]] = None
    if data is not None:
        if not isinstance(data, Mapping):
            raise ExtError("EVENT_INVALID", "data must be a JSON object (a mapping) or None")
        if _contains_secret(data):
            raise ExtError("EVENT_SECRET", "data contains a Secret; pass a reference instead")
        try:
            raw = canonical_json_bytes(data)
        except (TypeError, ValueError, RecursionError):
            raise ExtError("EVENT_INVALID", "data must be plain JSON: objects, lists, strings, integers, "
                           "booleans and null (no floats)") from None
        if len(raw) > MAX_DATA_BYTES:
            raise ExtError("EVENT_DATA_TOO_LARGE", f"data is {len(raw)} bytes, the limit is {MAX_DATA_BYTES}; "
                           "store it with aicore.state.blobs and send an artifact-ref")
        payload = json.loads(raw.decode("utf-8"))
    if id is not None and not (isinstance(id, str) and _ID.match(id)):
        raise ExtError("EVENT_INVALID", "id must be 32 lowercase hex digits")
    event = Event(id=id or uuid.uuid4().hex, source=SOURCE_PREFIX + source, type=type, time=_now_text(now),
                  subject=subject, data=payload, dataschema=dataschema, traceparent=traceparent,
                  causationid=causationid, correlationid=correlationid)
    problems = validate_document(event.to_json())
    if problems:
        raise ExtError("EVENT_INVALID", problems[0])
    try:
        canonical_json_bytes(event.to_json())
    except (TypeError, ValueError):  # for example a lone surrogate in subject: not encodable as UTF-8
        raise ExtError("EVENT_INVALID", "the event contains text that cannot be encoded as UTF-8") from None
    return event


def emit(type: str, data: Optional[Mapping[str, Any]] = None, *, source: str, subject: Optional[str] = None,
         project: Optional[PathLike] = None, delivery: Optional[str] = None, strict: bool = False,
         env: Optional[Mapping[str, str]] = None, home: Optional[PathLike] = None,
         **attrs: Any) -> Optional[Event]:
    """Journal an event of module ``source``; return it with its ``offset``, or None when it was not stored.

    ``project`` is a project root (its journal) or None (the machine journal). A failing journal is a
    warning and ``None`` unless ``strict``. ``delivery`` is checked (``background``, ``sync``, ``off``) but
    delivery itself is not available yet. Other keyword arguments go to :func:`build_event`.
    """
    if delivery is not None and delivery not in DELIVERY_MODES:
        raise ExtError("EVENT_INVALID", f"delivery must be one of {', '.join(DELIVERY_MODES)}")
    event = build_event(type, data, source=source, subject=subject, **attrs)
    line = canonical_json_bytes(event.to_json())
    try:
        jdir = journal.journal_dir(project, env=env, home=home)
        offset = journal.append(jdir, line)
    except ExtError as exc:
        if strict:
            raise
        warn_once(exc.code, f"event {event.type} was not stored: {exc.message}", key=str(project))
        return None
    except (OSError, ValueError) as exc:
        if strict:
            raise ExtError("JOURNAL_IO", f"the journal cannot be written: {exc}") from None
        warn_once("JOURNAL_IO", f"event {event.type} was not stored: {exc}", key=str(project))
        return None
    return dataclasses.replace(event, offset=offset)


def _problem(offset: int, code: str, message: str) -> Problem:
    return {"offset": offset, "code": code, "message": message}


def read_events(project: Optional[PathLike] = None, *, types: Optional[Sequence[str]] = None,
                since_id: Optional[str] = None, limit: Optional[int] = None,
                env: Optional[Mapping[str, str]] = None,
                home: Optional[PathLike] = None) -> Tuple[List[Event], List[Problem]]:
    """Events of the journal in order, and the problems found: ``[{"offset", "code", "message"}]``.

    ``types`` are shell-style patterns (case-sensitive), any of which must match. ``since_id`` keeps only
    events after the event with that id (``EVENT_NOT_FOUND`` when there is none). ``limit`` keeps the last N
    matches. Broken lines are skipped and reported, never raised.
    """
    if limit is not None and limit < 0:
        raise ExtError("EVENT_INVALID", "limit must not be negative")
    jdir = journal.journal_dir(project, env=env, home=home)
    events: List[Event] = []
    problems: List[Problem] = []
    for offset, line, problem in journal.iter_lines(jdir):
        if problem is not None:
            if problem == "too-long":
                problems.append(_problem(offset, "EVENT_LINE_TOO_LONG",
                                         f"line is longer than {journal.MAX_LINE} bytes"))
            else:
                problems.append(_problem(offset, "EVENT_MALFORMED", "empty line"))
            continue
        try:
            doc = json.loads(line.decode("utf-8"))
        except (ValueError, RecursionError):
            problems.append(_problem(offset, "EVENT_MALFORMED", "line is not JSON"))
            continue
        if isinstance(doc, dict) and doc.get("specversion") not in (None, SPECVERSION) \
                and isinstance(doc.get("specversion"), str):
            problems.append(_problem(offset, "EVENT_VERSION_UNSUPPORTED",
                                     f"specversion {doc['specversion']!r} is not supported"))
            continue
        issues = validate_document(doc)
        if issues:
            problems.append(_problem(offset, "EVENT_MALFORMED", issues[0]))
            continue
        events.append(Event.from_json(doc, offset))
    if since_id is not None:
        for index, event in enumerate(events):
            if event.id == since_id:
                events = events[index + 1:]
                break
        else:
            raise ExtError("EVENT_NOT_FOUND", f"no event with id {since_id}")
    if types:
        events = [event for event in events if any(fnmatch.fnmatchcase(event.type, pattern) for pattern in types)]
    if limit is not None:
        events = events[len(events) - limit:] if limit else []
    return events, problems
