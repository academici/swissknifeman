"""Process logging configuration, live thresholds and atomic JSONL/text writes."""

import json
import os
import sys
from collections.abc import Mapping
from dataclasses import dataclass, replace
from threading import RLock
from typing import Literal, TextIO

from skm.kernel.json_types import JsonObject
from skm.platform.logging.envelope import LOG_FIELDS, context_fields, safe_fields, valid_name
from skm.platform.logging.redaction import Redactor
from skm.platform.system_clock import SystemClock

__all__ = ["configure_logging", "detail_enabled", "emit", "reconfigure_logging", "register_secret"]

type Level = Literal["debug", "info", "warning", "error"]
type Detail = Literal["normal", "debug"]
type Format = Literal["json", "text"]
_LEVELS = {"debug": 10, "info": 20, "warning": 30, "error": 40}
_DETAIL_EVENTS = frozenset(("adapters.postgres.sql", "platform.process.run", "config.resolved"))
_DETAIL_FIELDS = {
    "bus.command.started": frozenset(("operation", "schema_urn")),
    "bus.command.completed": frozenset(("result_digest",)),
}
_LOCK = RLock()
_CLOCK = SystemClock()


@dataclass(frozen=True, slots=True)
class _Settings:
    level: str
    detail: Detail
    fmt: Format
    stream: TextIO | None
    redactor: Redactor
    host: str


@dataclass(slots=True)
class _State:
    settings: _Settings


_state = _State(_Settings("info", "normal", "json", None, Redactor(), "localhost"))


def _validate(level: str, detail: str) -> None:
    if level not in _LEVELS:
        raise ValueError("invalid logging level")
    if detail not in ("normal", "debug"):
        raise ValueError("invalid logging detail")


def configure_logging(
    *, level: str, detail: Detail, fmt: Format, stream: TextIO, redactor: Redactor, host: str
) -> None:
    """Bootstrap owns the stream; no stdlib/root handlers are installed."""
    _validate(level, detail)
    if fmt not in ("json", "text"):
        raise ValueError("invalid logging format")
    if "host" not in safe_fields("logging.configured", {"host": host}):
        raise ValueError("invalid logging host")
    with _LOCK:
        _state.settings = _Settings(level, detail, fmt, stream, redactor, host)


def reconfigure_logging(*, level: str, detail: Detail) -> None:
    _validate(level, detail)
    with _LOCK:
        _state.settings = replace(_state.settings, level=level, detail=detail)


def register_secret(value: str) -> None:
    """Register a revealed credential with the active process log sink."""
    with _LOCK:
        _state.settings.redactor.register_secret(value)


def detail_enabled() -> bool:
    with _LOCK:
        return _state.settings.detail == "debug"


def _render(record: JsonObject, fmt: Format) -> str:
    if fmt == "json":
        return json.dumps(record, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    # JSON literals escape controls/newlines, preventing physical line injection.
    timestamp = record.get("ts")
    time = timestamp[11:19] if type(timestamp) is str and len(timestamp) == 24 else timestamp
    prefix = " ".join(
        str(value) for value in (time, record.get("level"), record.get("component"), record.get("event"))
    )
    extra = " ".join(
        f"{key}={json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':'))}"
        for key, value in record.items()
        if key not in {"ts", "level", "component", "event"}
    )
    return prefix + (" " + extra if extra else "")


def emit(component: str, level: Level, event: str, fields: Mapping[str, object]) -> None:
    """Single projection and final redaction for both formats, serialized under the sink lock.

    A sink that cannot take the line loses it; the caller's operation never fails because of its log.
    """
    if not valid_name(event):
        raise ValueError("logging event must be a bounded dotted identifier")
    with _LOCK:
        settings = _state.settings
        if _LEVELS[level] < _LEVELS[settings.level]:
            return
        if settings.detail == "normal" and event in _DETAIL_EVENTS:
            return
        selected: dict[str, object] = {**context_fields(), **fields}
        selected.update(
            ts=_CLOCK.now().isoformat(timespec="milliseconds").replace("+00:00", "Z"),
            level=level,
            component=component,
            event=event,
            pid=os.getpid(),
            host=settings.host,
        )
        projected = safe_fields(event, selected)
        if settings.detail == "normal":
            for name in _DETAIL_FIELDS.get(event, ()):
                projected.pop(name, None)
        ordered = {
            name: projected[name]
            for name in (*LOG_FIELDS, *sorted(projected.keys() - set(LOG_FIELDS)))
            if name in projected
        }
        redacted = settings.redactor.document(ordered)
        if not isinstance(redacted, dict):
            raise TypeError("redacted log envelope must be an object")
        line = _render(redacted, settings.fmt)
        stream = settings.stream if settings.stream is not None else sys.stderr
        try:
            stream.write(line + "\n")
            stream.flush()
        except (OSError, ValueError):
            # Operational logs are best effort: a full disk, a closed pipe, a hung-up terminal or a closed
            # sink drops the line instead of failing the operation it describes (a committed command, a tick).
            return
