"""Normalized session event stream (runtimes §4.6, ``urn:skm:runtimes:session-event:v1``).

A closed union discriminated by ``type``. ``seq`` is assigned by the adapter and increases within a session;
``at`` is the adapter's UTC observation time, never a provider timestamp. Exactly one terminal event
(``session_completed`` | ``session_failed``) ends a stream; ``cancel_ignored`` is not terminal.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, ClassVar, Final, Literal, cast

from skm.kernel.error_codes import ErrorCode

from .error_rules import ProviderFailure, failure_from_json, failure_to_json
from .ids import format_utc, is_digest, parse_utc, require_utc
from .usage import UsageReport, usage_from_json, usage_to_json

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject, JsonValue
    from skm.modules.runtimes.domain.ids import Digest, ModelId, SessionRef

__all__ = [
    "AFTER_CANCEL_IGNORED_CODES",
    "CancelIgnored",
    "CheckpointAvailable",
    "SessionCompleted",
    "SessionEvent",
    "SessionFailed",
    "SessionStarted",
    "StopReason",
    "TextDelta",
    "ToolCallStatus",
    "ToolCompleted",
    "ToolRequested",
    "UsageReported",
    "Violation",
    "is_terminal",
    "session_event_from_json",
    "session_event_to_json",
    "validate_event_stream",
]

_ARGS_PREVIEW_MAX: Final = 500
_ID_MAX: Final = 200


@dataclass(frozen=True, slots=True)
class Violation:
    """One broken stream/observation invariant: a stable snake_case rule, the place and a safe message."""

    rule: str
    message: str
    at: str | None = None  # "seq=7", a field path, ...


class ToolCallStatus(StrEnum):
    OK = "ok"
    ERROR = "error"
    DENIED = "denied"


class StopReason(StrEnum):
    END_TURN = "end_turn"
    MAX_TURNS = "max_turns"
    MAX_TOKENS = "max_tokens"
    STOP_SEQUENCE = "stop_sequence"
    OTHER = "other"


def _header(seq: object, at: object) -> None:
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 1:
        raise ValueError("seq must be an int >= 1")
    require_utc(at, "at")


def _text(value: object, name: str, *, max_length: int = _ID_MAX) -> None:
    if not isinstance(value, str) or not 1 <= len(value) <= max_length:
        raise ValueError(f"{name} must be a string of 1..{max_length} characters")


def _optional_count(value: object) -> bool:
    return value is None or (isinstance(value, int) and not isinstance(value, bool) and value >= 0)


def _digest(value: object, name: str) -> None:
    if not is_digest(value):
        raise ValueError(f"{name} must be a sha256 digest")


@dataclass(frozen=True, slots=True)
class SessionStarted:
    TYPE: ClassVar[str] = "session_started"
    seq: int
    at: datetime
    session_ref: SessionRef | None
    model: ModelId | None
    runtime_version: str | None

    def __post_init__(self) -> None:
        _header(self.seq, self.at)
        if self.session_ref is not None:
            _text(self.session_ref, "session_ref")


@dataclass(frozen=True, slots=True)
class TextDelta:
    TYPE: ClassVar[str] = "text_delta"
    seq: int
    at: datetime
    channel: Literal["assistant", "reasoning"]
    text: str

    def __post_init__(self) -> None:
        _header(self.seq, self.at)
        if self.channel not in ("assistant", "reasoning"):
            raise ValueError(f"unknown channel {self.channel!r}")


@dataclass(frozen=True, slots=True)
class ToolRequested:
    TYPE: ClassVar[str] = "tool_requested"
    seq: int
    at: datetime
    call_id: str
    tool: str
    args_preview: str  # <= 500 characters, after redaction
    args_digest: Digest

    def __post_init__(self) -> None:
        _header(self.seq, self.at)
        _text(self.call_id, "call_id")
        _text(self.tool, "tool")
        if not isinstance(self.args_preview, str) or len(self.args_preview) > _ARGS_PREVIEW_MAX:  # pyright: ignore[reportUnnecessaryIsInstance]
            raise ValueError("args_preview must be at most 500 characters")
        _digest(self.args_digest, "args_digest")


@dataclass(frozen=True, slots=True)
class ToolCompleted:
    TYPE: ClassVar[str] = "tool_completed"
    seq: int
    at: datetime
    call_id: str
    status: ToolCallStatus
    duration_ms: int | None

    def __post_init__(self) -> None:
        _header(self.seq, self.at)
        _text(self.call_id, "call_id")
        object.__setattr__(self, "status", ToolCallStatus(self.status))
        if not _optional_count(self.duration_ms):
            raise ValueError("duration_ms must be a non-negative int or None")


@dataclass(frozen=True, slots=True)
class UsageReported:
    TYPE: ClassVar[str] = "usage_reported"
    seq: int
    at: datetime
    usage: UsageReport
    cumulative: bool

    def __post_init__(self) -> None:
        _header(self.seq, self.at)
        if not isinstance(self.usage, UsageReport) or not isinstance(self.cumulative, bool):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("usage_reported needs a UsageReport and a bool cumulative")


@dataclass(frozen=True, slots=True)
class CheckpointAvailable:
    TYPE: ClassVar[str] = "checkpoint_available"
    seq: int
    at: datetime
    session_ref: SessionRef

    def __post_init__(self) -> None:
        _header(self.seq, self.at)
        _text(self.session_ref, "session_ref")


@dataclass(frozen=True, slots=True)
class CancelIgnored:
    """Not terminal: the process outlived the grace after this signal and the adapter escalates."""

    TYPE: ClassVar[str] = "cancel_ignored"
    seq: int
    at: datetime
    signal: Literal["SIGINT", "SIGTERM"]

    def __post_init__(self) -> None:
        _header(self.seq, self.at)
        if self.signal not in ("SIGINT", "SIGTERM"):
            raise ValueError(f"unknown signal {self.signal!r}")


@dataclass(frozen=True, slots=True)
class SessionCompleted:
    """Success; only after the parser saw the native terminal of a successful turn (§4.6 rule 1)."""

    TYPE: ClassVar[str] = "session_completed"
    seq: int
    at: datetime
    stop_reason: StopReason
    final_text_digest: Digest

    def __post_init__(self) -> None:
        _header(self.seq, self.at)
        object.__setattr__(self, "stop_reason", StopReason(self.stop_reason))
        _digest(self.final_text_digest, "final_text_digest")


@dataclass(frozen=True, slots=True)
class SessionFailed:
    TYPE: ClassVar[str] = "session_failed"
    seq: int
    at: datetime
    failure: ProviderFailure

    def __post_init__(self) -> None:
        _header(self.seq, self.at)
        if not isinstance(self.failure, ProviderFailure):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("failure must be ProviderFailure")


type SessionEvent = (
    SessionStarted
    | TextDelta
    | ToolRequested
    | ToolCompleted
    | UsageReported
    | CheckpointAvailable
    | CancelIgnored
    | SessionCompleted
    | SessionFailed
)

# The terminal after cancel_ignored: a confirmed cancel, or the original timeout/cleanup outcome (§4.6 table).
AFTER_CANCEL_IGNORED_CODES: Final = frozenset(
    {
        ErrorCode.SESSION_CANCELLED,
        ErrorCode.CANCEL_IGNORED,
        ErrorCode.RUNTIME_TIMEOUT,
        ErrorCode.RUNTIME_CRASHED,
    }
)


def is_terminal(event: SessionEvent) -> bool:
    return isinstance(event, SessionCompleted | SessionFailed)


def validate_event_stream(events: Sequence[SessionEvent]) -> tuple[Violation, ...]:
    """Contract-suite check of a whole stream (§5): increasing ``seq``, exactly one terminal and nothing after
    it, a current cumulative usage (no delta after it) before ``session_failed``, ``cancel_ignored`` only
    before an allowed failure."""
    found: list[Violation] = []
    previous: int | None = None
    terminal: SessionEvent | None = None
    cumulative_usage = False
    cancel_ignored: CancelIgnored | None = None
    for event in events:
        place = f"seq={event.seq}"
        if previous is not None and event.seq <= previous:
            found.append(Violation("seq_not_increasing", f"seq {event.seq} follows {previous}", place))
        previous = event.seq if previous is None else max(previous, event.seq)
        if terminal is not None:
            rule = "duplicate_terminal" if is_terminal(event) else "event_after_terminal"
            found.append(Violation(rule, f"{event.TYPE} after the terminal {terminal.TYPE}", place))
            continue
        if isinstance(event, UsageReported):
            # A later delta is not in the earlier total: only a new cumulative makes it current again.
            cumulative_usage = event.cumulative
        elif isinstance(event, CancelIgnored):
            cancel_ignored = event
        elif isinstance(event, SessionFailed):
            terminal = event
            if not cumulative_usage:
                found.append(
                    Violation(
                        "failed_without_usage", "session_failed without a current cumulative usage", place
                    )
                )
            if cancel_ignored is not None and event.failure.code not in AFTER_CANCEL_IGNORED_CODES:
                found.append(
                    Violation(
                        "cancel_ignored_terminal",
                        f"session_failed {event.failure.code} cannot follow cancel_ignored",
                        place,
                    )
                )
        elif isinstance(event, SessionCompleted):
            terminal = event
            if cancel_ignored is not None:
                found.append(
                    Violation(
                        "cancel_ignored_terminal", "session_completed cannot follow cancel_ignored", place
                    )
                )
    if terminal is None:
        found.append(Violation("missing_terminal", "the stream has no terminal event"))
    return tuple(found)


def session_event_to_json(event: SessionEvent) -> JsonObject:
    data: JsonObject = {"type": event.TYPE, "seq": event.seq, "at": format_utc(event.at)}
    match event:
        case SessionStarted():
            data |= {
                "session_ref": event.session_ref,
                "model": event.model,
                "runtime_version": event.runtime_version,
            }
        case TextDelta():
            data |= {"channel": event.channel, "text": event.text}
        case ToolRequested():
            data |= {
                "call_id": event.call_id,
                "tool": event.tool,
                "args_preview": event.args_preview,
                "args_digest": event.args_digest,
            }
        case ToolCompleted():
            data |= {"call_id": event.call_id, "status": event.status.value, "duration_ms": event.duration_ms}
        case UsageReported():
            data |= {"usage": usage_to_json(event.usage), "cumulative": event.cumulative}
        case CheckpointAvailable():
            data |= {"session_ref": event.session_ref}
        case CancelIgnored():
            data |= {"signal": event.signal}
        case SessionCompleted():
            data |= {"stop_reason": event.stop_reason.value, "final_text_digest": event.final_text_digest}
        case SessionFailed():
            data |= {"failure": failure_to_json(event.failure)}
    return data


def _object(value: JsonValue, name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{name} must be an object")
    return value


def session_event_from_json(data: Mapping[str, JsonValue]) -> SessionEvent:  # noqa: PLR0911 - one per variant
    """Decode one schema-shaped event; an unknown ``type`` is refused (closed union)."""
    kind = data["type"]
    seq = cast("int", data["seq"])
    at = parse_utc(data["at"], "at")
    if kind == SessionStarted.TYPE:
        return SessionStarted(
            seq=seq,
            at=at,
            session_ref=cast("str | None", data["session_ref"]),
            model=cast("str | None", data["model"]),
            runtime_version=cast("str | None", data["runtime_version"]),
        )
    if kind == TextDelta.TYPE:
        channel = cast("Literal['assistant', 'reasoning']", data["channel"])
        return TextDelta(seq=seq, at=at, channel=channel, text=cast("str", data["text"]))
    if kind == ToolRequested.TYPE:
        return ToolRequested(
            seq=seq,
            at=at,
            call_id=cast("str", data["call_id"]),
            tool=cast("str", data["tool"]),
            args_preview=cast("str", data["args_preview"]),
            args_digest=cast("str", data["args_digest"]),
        )
    if kind == ToolCompleted.TYPE:
        return ToolCompleted(
            seq=seq,
            at=at,
            call_id=cast("str", data["call_id"]),
            status=ToolCallStatus(cast("str", data["status"])),
            duration_ms=cast("int | None", data["duration_ms"]),
        )
    if kind == UsageReported.TYPE:
        usage = usage_from_json(_object(data["usage"], "usage"))
        return UsageReported(seq=seq, at=at, usage=usage, cumulative=cast("bool", data["cumulative"]))
    if kind == CheckpointAvailable.TYPE:
        return CheckpointAvailable(seq=seq, at=at, session_ref=cast("str", data["session_ref"]))
    if kind == CancelIgnored.TYPE:
        return CancelIgnored(seq=seq, at=at, signal=cast("Literal['SIGINT', 'SIGTERM']", data["signal"]))
    if kind == SessionCompleted.TYPE:
        return SessionCompleted(
            seq=seq,
            at=at,
            stop_reason=StopReason(cast("str", data["stop_reason"])),
            final_text_digest=cast("str", data["final_text_digest"]),
        )
    if kind == SessionFailed.TYPE:
        return SessionFailed(seq=seq, at=at, failure=failure_from_json(_object(data["failure"], "failure")))
    raise ValueError(f"unknown session event type {kind!r}")
