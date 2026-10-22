"""Events: the envelope, ``build_event``, ``emit`` and reading the journal.

An event follows ``event/v1`` (a CloudEvents 1.0 subset). ``emit`` is for the *source* of an event: it
raises :class:`~aicore.ext.errors.ExtError` only when the call itself is wrong (type, source, data, size,
a ``Secret``) and otherwise never breaks the caller: a failing journal gives a warning and ``None``
(``strict=True`` raises instead). After journaling, ``emit`` starts delivery to the subscribers
(:mod:`aicore.ext.delivery`) in the mode of the call or of the configuration: ``background`` (a detached
deliverer process), ``sync`` (before ``emit`` returns) or ``off``. stdlib and ``aicore`` only.
"""
from __future__ import annotations

import dataclasses
import datetime
import fnmatch
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple, Union

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


_data_sets: Dict[Path, Tuple[Any, List[str]]] = {}


def contracts_strict(env: Optional[Mapping[str, str]] = None) -> bool:
    """True when ``SKM_CONTRACTS_STRICT=1`` (in ``env`` or in the process): a contract violation raises instead of
    being reported. The test runners set it."""
    return "1" in (os.environ.get("SKM_CONTRACTS_STRICT"), (env or {}).get("SKM_CONTRACTS_STRICT"))


def validate_data(data: object, dataschema_id: str, contract_dir: PathLike) -> List[str]:
    """Messages of every violation of the data schema ``dataschema_id`` by ``data`` (empty when valid).

    ``contract_dir`` is the ``schemas/event-data/v1`` directory of the emitting module; aicore does not know where
    modules keep it. The directory is loaded once per path. An id that no schema of the directory carries is one
    problem, ``dataschema <id> is not in <dir>``.
    """
    directory = Path(contract_dir).resolve()
    loaded = _data_sets.get(directory)
    if loaded is None:
        loaded = _data_sets[directory] = _schema.load_contract_set(directory)
    registry, kinds = loaded
    kind = next((name for name in kinds if f"{registry.urn_prefix}{name}:{registry.version}" == dataschema_id), None)
    if kind is None:
        return [f"dataschema {dataschema_id} is not in {contract_dir}"]
    return [f"{issue.path or '/'}: {issue.message}" if not issue.message.startswith(f"{issue.path or '/'}:")
            else issue.message for issue in _schema.validate(data, kind, registry)]


def check_data(data: object, dataschema_id: str, contract_dir: PathLike, *,
               env: Optional[Mapping[str, str]] = None) -> Optional[str]:
    """The emitter's gate before :func:`emit`: ``None`` when ``data`` fits its schema, else the first problem.

    Under ``SKM_CONTRACTS_STRICT=1`` a violation raises ``ExtError('EVENT_DATA_INVALID')`` instead, so a test sees it.
    """
    if _contains_secret(data):
        return None  # build_event refuses it with EVENT_SECRET, which is the more useful answer
    problems = validate_data(data, dataschema_id, contract_dir)
    if not problems:
        return None
    if contracts_strict(env):
        raise ExtError("EVENT_DATA_INVALID", problems[0])
    return problems[0]


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
         config_file: Optional[PathLike] = None, **attrs: Any) -> Optional[Event]:
    """Journal an event of module ``source``, start its delivery and return it with its ``offset``.

    ``project`` is a project root (its journal) or None (the machine journal). ``delivery`` is
    ``background``, ``sync`` or ``off``; None takes ``events.delivery`` of the configuration. A failing
    journal returns ``None``; a failing configuration or delivery start still returns the stored event.
    Both are warnings unless ``strict``, which raises them. Other keyword arguments go to :func:`build_event`.
    """
    if delivery is not None and delivery not in DELIVERY_MODES:
        raise ExtError("EVENT_INVALID", f"delivery must be one of {', '.join(DELIVERY_MODES)}")
    event = build_event(type, data, source=source, subject=subject, **attrs)
    line = canonical_json_bytes(event.to_json())
    root = os.path.abspath(project) if project is not None else None
    try:
        jdir = journal.journal_dir(root, env=env, home=home)
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
    stored = dataclasses.replace(event, offset=offset)
    _start_delivery(jdir, offset, root, delivery, strict=strict, env=env, home=home, config_file=config_file)
    return stored


def _start_delivery(jdir: Path, offset: int, root: Optional[str], mode: Optional[str], *, strict: bool,
                    env: Optional[Mapping[str, str]], home: Optional[PathLike],
                    config_file: Optional[PathLike]) -> None:
    """The delivery step of :func:`emit`: never raises unless ``strict`` (the source must not break)."""
    from . import delivery as _delivery  # delivery reads events: imported late to avoid a cycle
    from . import settings as _settings
    try:
        if mode is None:
            try:
                mode = _settings.load(root, env=env, home=home, config_file=config_file).delivery
            except ExtError as exc:
                _delivery.record_config_error(jdir, exc)
                raise
        if mode == "sync":
            _delivery.deliver(jdir, trigger_offset=offset, project=root, env=env, home=home,
                              config_file=config_file)
        elif mode == "background":
            _delivery.spawn_background(jdir, trigger_offset=offset, project=root, env=env,
                                       config_file=config_file, strict=strict)
    except ExtError as exc:
        if strict:
            raise
        warn_once(exc.code, f"events were not delivered: {exc.message}", key=str(jdir))
    except (OSError, ValueError) as exc:
        if strict:
            raise ExtError("DELIVERY_IO", f"events were not delivered: {exc}") from None
        warn_once("DELIVERY_IO", f"events were not delivered: {exc}", key=str(jdir))


def _problem(offset: int, code: str, message: str) -> Problem:
    return {"offset": offset, "code": code, "message": message}


def parse_line(offset: int, line: Optional[bytes], problem: Optional[str]) -> Tuple[Optional[Event], Optional[Problem]]:
    """One entry of :func:`aicore.ext.journal.iter_lines` as ``(event, None)`` or ``(None, problem)``."""
    if problem is not None or line is None:
        if problem == "too-long":
            return None, _problem(offset, "EVENT_LINE_TOO_LONG", f"line is longer than {journal.MAX_LINE} bytes")
        return None, _problem(offset, "EVENT_MALFORMED", "empty line")
    try:
        doc = json.loads(line.decode("utf-8"))
    except (ValueError, RecursionError):
        return None, _problem(offset, "EVENT_MALFORMED", "line is not JSON")
    if isinstance(doc, dict) and isinstance(doc.get("specversion"), str) and doc["specversion"] != SPECVERSION:
        return None, _problem(offset, "EVENT_VERSION_UNSUPPORTED",
                              f"specversion {doc['specversion']!r} is not supported")
    issues = validate_document(doc)
    if issues:
        return None, _problem(offset, "EVENT_MALFORMED", issues[0])
    return Event.from_json(doc, offset), None


def iter_events(jdir: PathLike, start: int = 0) -> Iterator[Tuple[int, Optional[Event], Optional[Problem]]]:
    """``(offset, event, problem)`` for each complete line of the journal in ``jdir`` from byte ``start``."""
    for offset, line, problem in journal.iter_lines(jdir, start):
        event, found = parse_line(offset, line, problem)
        yield offset, event, found


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
    for _offset, event, problem in iter_events(jdir):
        if problem is not None:
            problems.append(problem)
        else:
            events.append(event)
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
