"""Claude-compatible ``stream-json`` wire parser shared by CLI runtimes that emit that format.

Claude Code (``--output-format stream-json``) and Grok (``--output-format streaming-messages-json``)
emit the same system/assistant/user/result envelope. Runtimes differ only in usage accounting, the
tool-denial hint and which ``init`` field carries the CLI version, which they inject here.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Final, Protocol, cast

from skm.kernel.json_types import JsonValue
from skm.modules.runtimes.domain.error_rules import RuntimeSignals
from skm.modules.runtimes.domain.observation import ToolVisibility
from skm.modules.runtimes.domain.result import ToolDenial
from skm.modules.runtimes.domain.session_events import (
    SessionEvent,
    SessionStarted,
    StopReason,
    TextDelta,
    ToolCallStatus,
    ToolCompleted,
    ToolRequested,
    UsageReported,
)
from skm.modules.runtimes.domain.usage import UsageReport

from .session import FinalOutcome
from .wire_values import (
    bounded_id,
    bounded_model,
    bounded_version,
    extract_http_status,
    identity_redact,
    nonneg_opt,
)

__all__: list[str] = []

_EPOCH_UTC: Final = datetime(1970, 1, 1, tzinfo=UTC)

_STOP_REASON_MAP: Final[Mapping[str, StopReason]] = {
    "end_turn": StopReason.END_TURN,
    "max_turns": StopReason.MAX_TURNS,
    "max_tokens": StopReason.MAX_TOKENS,
    "stop_sequence": StopReason.STOP_SEQUENCE,
}


def _finite_json(value: object) -> bool:
    """True when ``value`` is JSON and every nested float is finite."""
    pending: list[object] = [value]
    while pending:
        current = pending.pop()
        if current is None or isinstance(current, bool | int | str):
            continue
        if isinstance(current, float):
            if not math.isfinite(current):
                return False
            continue
        if isinstance(current, list):
            pending.extend(cast("list[object]", current))
            continue
        if isinstance(current, dict):
            for key, item in cast("dict[object, object]", current).items():
                if not isinstance(key, str):
                    return False
                pending.append(item)
            continue
        return False
    return True


def _json_value(value: object) -> JsonValue | None:
    """JSON payload from ``structured_output``. Top-level null is not a payload.

    A non-finite float anywhere in the tree rejects the payload.
    """
    if value is None or not _finite_json(value):
        return None
    return cast("JsonValue", value)


def _extract_error_text(data: Mapping[str, object]) -> str | None:
    parts: list[str] = []
    result_val = data.get("result")
    if isinstance(result_val, str) and result_val.strip():
        parts.append(result_val.strip())
    errors_val = data.get("errors")
    if isinstance(errors_val, list):
        for item in cast("list[object]", errors_val):
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, Mapping):
                msg = cast("Mapping[str, object]", item).get("message")
                if isinstance(msg, str) and msg.strip():
                    parts.append(msg.strip())
    err_obj = data.get("error")
    if isinstance(err_obj, str) and err_obj.strip():
        parts.append(err_obj.strip())
    elif isinstance(err_obj, Mapping):
        msg = cast("Mapping[str, object]", err_obj).get("message")
        if isinstance(msg, str) and msg.strip():
            parts.append(msg.strip())
    if not parts:
        return None
    return "; ".join(dict.fromkeys(parts))[:4000]


def _looks_like_permission_denial(content: object, tool_use_result: object) -> bool:
    candidates: list[str] = []
    if isinstance(content, str):
        candidates.append(content)
    elif isinstance(content, list):
        for entry in cast("list[object]", content):
            if isinstance(entry, Mapping):
                txt = cast("Mapping[str, object]", entry).get("text")
                if isinstance(txt, str):
                    candidates.append(txt)
    if isinstance(tool_use_result, str):
        candidates.append(tool_use_result)
    folded = " ".join(candidates).casefold()
    return (
        "permission to use " in folded
        or "permission denied" in folded
        or "blocked by permission" in folded
        or "disallowed tool" in folded
    )


class UsageTracker(Protocol):
    """Runtime-specific token accounting fed by the parser."""

    def mark_tool(self, tool_name: str) -> None: ...

    def record_assistant_usage(self, message_id: str | None, raw_usage: object) -> None: ...

    def record_result_usage(self, raw_usage: object) -> UsageReport | None: ...

    def final_usage(self) -> UsageReport: ...


class StreamJsonParser:
    """Stateful line-by-line parser for Claude-compatible ``stream-json`` output."""

    def __init__(
        self,
        *,
        usage: UsageTracker,
        denial_hint: Callable[[str, object], str],
        version_fields: tuple[str, ...],
        runtime_version: str | None = None,
        redact: Callable[[str], str] = identity_redact,
    ) -> None:
        self._runtime_version = bounded_version(runtime_version)
        self._redact = redact
        self._usage = usage
        self._denial_hint = denial_hint
        self._version_fields = version_fields
        self._seq = 0
        self._saw_init = False
        self._saw_terminal = False
        self._is_error = False
        self._session_ref: str | None = None
        self._model: str | None = None
        self._stop_reason: StopReason = StopReason.END_TURN
        self._result_texts: list[str] = []
        self._structured: JsonValue | None = None
        self._fatal_text: str | None = None
        self._http_status: int | None = None
        self._retry_category: str | None = None
        self._api_retries = 0
        self._limit_status: str | None = None
        self._limit_window: str | None = None
        self._limit_resets_at: int | None = None
        self._tool_calls = 0
        self._tool_by_call_id: dict[str, tuple[str, object]] = {}
        self._completed_calls: set[str] = set()
        self._denied_calls: set[str] = set()
        self._denials: list[ToolDenial] = []

    def _reported_version(self, data: Mapping[str, object]) -> str | None:
        for name in self._version_fields:
            version = bounded_version(data.get(name))
            if version is not None:
                return version
        return self._runtime_version

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def feed(self, line: bytes) -> Iterable[SessionEvent]:
        """Parse one JSONL line into zero or more non-terminal ``SessionEvent`` records."""
        if not line.strip():
            return ()
        try:
            decoded = line.decode("utf-8", "strict")
            parsed: object = json.loads(decoded)
        except (UnicodeError, ValueError, RecursionError):
            return ()
        if not isinstance(parsed, dict):
            return ()
        data = cast("dict[str, object]", parsed)
        kind = data.get("type")
        events: tuple[SessionEvent, ...] = ()
        if kind == "system":
            events = tuple(self._handle_system(data))
        elif kind == "assistant":
            events = tuple(self._handle_assistant(data))
        elif kind == "user":
            events = tuple(self._handle_user(data))
        elif kind == "rate_limit_event":
            self._handle_rate_limit(data)
        elif kind == "result":
            events = tuple(self._handle_result(data))
        return events

    def is_terminal(self, line: bytes) -> bool:
        if not line.strip():
            return False
        try:
            parsed: object = json.loads(line.decode("utf-8", "strict"))
        except (UnicodeError, ValueError, RecursionError):
            return False
        return isinstance(parsed, dict) and cast("dict[str, object]", parsed).get("type") == "result"

    def saw_terminal(self) -> bool:
        return self._saw_terminal and not self._is_error

    def finish(self, exit_code: int | None) -> FinalOutcome:
        terminal_ok = self.saw_terminal()
        signals = RuntimeSignals(
            exit_code=exit_code,
            fatal_text=self._fatal_text,
            is_error=True if self._is_error else (False if self._saw_terminal else None),
            http_status=self._http_status,
            retry_category=self._retry_category,
            api_retries=self._api_retries if self._api_retries > 0 else None,
            limit_status=self._limit_status,
            limit_window=self._limit_window,
            limit_resets_at=self._limit_resets_at,
            terminal=terminal_ok,
        )
        if terminal_ok:
            tools = ToolVisibility("complete", self._tool_calls)
        elif self._saw_init or self._tool_calls > 0:
            tools = ToolVisibility("partial", self._tool_calls)
        else:
            tools = ToolVisibility("unavailable", None)

        return FinalOutcome(
            final_text="\n\n".join(self._result_texts) if terminal_ok else "",
            session_ref=self._session_ref,
            model=self._model,
            usage=self._usage.final_usage(),
            signals=signals,
            is_error=self._is_error,
            stop_reason=self._stop_reason,
            tools=tools,
            denials=tuple(self._denials),
            structured=self._structured if terminal_ok else None,
        )

    def _handle_system(self, data: Mapping[str, object]) -> Iterable[SessionEvent]:
        subtype = data.get("subtype")
        if subtype == "init":
            self._saw_init = True
            session_ref = bounded_id(data.get("session_id"))
            model = bounded_model(data.get("model"))
            version = self._reported_version(data)
            if session_ref is not None:
                self._session_ref = session_ref
            if model is not None and data.get("parent_tool_use_id") is None:
                self._model = model
            yield SessionStarted(
                seq=self._next_seq(),
                at=_EPOCH_UTC,
                session_ref=session_ref,
                model=model,
                runtime_version=version,
            )
            return

        if subtype == "permission_denied":
            raw_call = data.get("tool_use_id") or data.get("call_id") or data.get("id")
            call_id = bounded_id(raw_call) or f"denied-{len(self._denials) + 1}"
            known_tool, known_input = self._tool_by_call_id.get(call_id, ("unknown", None))
            tool_name = bounded_id(data.get("tool_name") or data.get("tool")) or known_tool
            tool_input = data.get("input") if "input" in data else data.get("tool_input", known_input)
            if call_id not in self._denied_calls:
                self._denied_calls.add(call_id)
                self._denials.append(
                    ToolDenial(tool=tool_name, hint=self._denial_hint(tool_name, tool_input))
                )
            if call_id not in self._completed_calls:
                self._completed_calls.add(call_id)
                yield ToolCompleted(
                    seq=self._next_seq(),
                    at=_EPOCH_UTC,
                    call_id=call_id,
                    status=ToolCallStatus.DENIED,
                    duration_ms=nonneg_opt(data.get("duration_ms")),
                )
            return

        if subtype == "api_retry":
            attempt = data.get("attempt") or data.get("retry_attempt")
            if not isinstance(attempt, bool) and isinstance(attempt, int) and attempt > 0:
                self._api_retries = max(self._api_retries, attempt)
            else:
                self._api_retries += 1
            status = extract_http_status(data)
            if status is not None:
                self._http_status = status
            raw_cat = data.get("retry_category") or data.get("category") or data.get("error")
            if isinstance(raw_cat, str) and raw_cat.strip():
                self._retry_category = raw_cat.strip()[:100]
            elif status == 429 and self._retry_category is None:
                self._retry_category = "rate_limit"

    def _handle_assistant(self, data: Mapping[str, object]) -> Iterable[SessionEvent]:
        raw_msg = data.get("message")
        msg = cast("Mapping[str, object]", raw_msg) if isinstance(raw_msg, Mapping) else data
        model = bounded_model(msg.get("model"))
        if model is not None and data.get("parent_tool_use_id") is None:
            self._model = model
        msg_id = msg.get("id")
        self._usage.record_assistant_usage(
            msg_id if isinstance(msg_id, str) else None,
            msg.get("usage"),
        )
        session_ref = bounded_id(data.get("session_id"))
        if session_ref is not None and self._session_ref is None:
            self._session_ref = session_ref

        content = msg.get("content")
        if not isinstance(content, list):
            return
        for raw_block in cast("list[object]", content):
            if not isinstance(raw_block, Mapping):
                continue
            block = cast("Mapping[str, object]", raw_block)
            btype = block.get("type")
            if btype == "text":
                text = block.get("text")
                if isinstance(text, str) and text:
                    yield TextDelta(
                        seq=self._next_seq(),
                        at=_EPOCH_UTC,
                        channel="assistant",
                        text=self._redact(text),
                    )
            elif btype == "thinking":
                # Normative (Dossier §3.4): thinking blocks remain in transcript only.
                continue
            elif btype == "tool_use":
                self._tool_calls += 1
                tool_name = bounded_id(block.get("name")) or "unknown"
                call_id = bounded_id(block.get("id")) or f"call-{self._tool_calls}"
                tool_input = block.get("input", {})
                self._tool_by_call_id[call_id] = (tool_name, tool_input)
                self._usage.mark_tool(tool_name)
                canonical = json.dumps(
                    tool_input,
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                digest = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
                preview = self._redact(canonical)[:500]
                yield ToolRequested(
                    seq=self._next_seq(),
                    at=_EPOCH_UTC,
                    call_id=call_id,
                    tool=tool_name,
                    args_preview=preview,
                    args_digest=digest,
                )

    def _handle_user(self, data: Mapping[str, object]) -> Iterable[SessionEvent]:
        raw_msg = data.get("message")
        msg = cast("Mapping[str, object]", raw_msg) if isinstance(raw_msg, Mapping) else data
        content = msg.get("content")
        if not isinstance(content, list):
            return
        tool_use_result = data.get("tool_use_result")
        for raw_block in cast("list[object]", content):
            if not isinstance(raw_block, Mapping):
                continue
            block = cast("Mapping[str, object]", raw_block)
            if block.get("type") != "tool_result":
                continue
            call_id = bounded_id(block.get("tool_use_id") or block.get("call_id"))
            if call_id is None or call_id in self._completed_calls:
                continue
            is_err = bool(block.get("is_error"))
            if is_err and _looks_like_permission_denial(block.get("content"), tool_use_result):
                status = ToolCallStatus.DENIED
                if call_id not in self._denied_calls:
                    self._denied_calls.add(call_id)
                    tool_name, tool_input = self._tool_by_call_id.get(call_id, ("unknown", None))
                    self._denials.append(
                        ToolDenial(tool=tool_name, hint=self._denial_hint(tool_name, tool_input))
                    )
            else:
                status = ToolCallStatus.ERROR if is_err else ToolCallStatus.OK
            self._completed_calls.add(call_id)
            yield ToolCompleted(
                seq=self._next_seq(),
                at=_EPOCH_UTC,
                call_id=call_id,
                status=status,
                duration_ms=nonneg_opt(block.get("duration_ms")),
            )

    def _handle_rate_limit(self, data: Mapping[str, object]) -> None:
        raw_info = data.get("rate_limit_info")
        info = cast("Mapping[str, object]", raw_info) if isinstance(raw_info, Mapping) else data
        raw_status = info.get("status") or data.get("limit_status")
        if isinstance(raw_status, str) and raw_status.strip():
            self._limit_status = raw_status.strip()[:100]
        raw_window = (
            info.get("rateLimitType")
            or info.get("limit_window")
            or info.get("window")
            or data.get("limit_window")
        )
        if isinstance(raw_window, str) and raw_window.strip():
            self._limit_window = raw_window.strip()[:100]
        raw_resets = info.get("resetsAt") or info.get("resets_at") or data.get("limit_resets_at")
        if not isinstance(raw_resets, bool) and isinstance(raw_resets, (int, float)) and raw_resets > 0:
            self._limit_resets_at = int(raw_resets)

    def _handle_result(self, data: Mapping[str, object]) -> Iterable[SessionEvent]:
        session_ref = bounded_id(data.get("session_id"))
        if session_ref is not None:
            self._session_ref = session_ref
        model = bounded_model(data.get("model"))
        if model is not None and data.get("parent_tool_use_id") is None:
            self._model = model

        usage_report = self._usage.record_result_usage(data.get("usage"))
        if usage_report is not None:
            yield UsageReported(
                seq=self._next_seq(),
                at=_EPOCH_UTC,
                usage=usage_report,
                cumulative=True,
            )

        raw_stop = data.get("stop_reason")
        if isinstance(raw_stop, str):
            self._stop_reason = _STOP_REASON_MAP.get(raw_stop, StopReason.OTHER)

        if bool(data.get("is_error")):
            self._is_error = True
            self._saw_terminal = False
            err_text = _extract_error_text(data)
            if err_text is not None:
                self._fatal_text = self._redact(err_text)
            status = extract_http_status(data, err_text)
            if status is not None:
                self._http_status = status
            return

        result_text = data.get("result")
        if isinstance(result_text, str) and result_text != "":
            self._result_texts.append(self._redact(result_text))
        payload = _json_value(data.get("structured_output"))
        if payload is not None:
            self._structured = payload
        if not self._is_error:
            self._saw_terminal = True
