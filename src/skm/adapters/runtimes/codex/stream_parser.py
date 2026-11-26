"""Codex JSONL wire parser implementing ``_cli_session.session.StreamParser``."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import Final, cast

from skm.adapters.runtimes._cli_session.session import FinalOutcome
from skm.adapters.runtimes._cli_session.wire_values import (
    bounded_id,
    bounded_model,
    bounded_version,
    extract_http_status,
    identity_redact,
    nonneg_opt,
)
from skm.modules.runtimes.domain.classes import Effort
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

from .permissions import denial_hint
from .usage import UsageAccumulator

__all__: list[str] = []

_EPOCH_UTC: Final = datetime(1970, 1, 1, tzinfo=UTC)
_RECONNECT_RE: Final = re.compile(r"reconnecting\.\.\.\s*(\d+)/\d+", re.IGNORECASE)

_TOOL_ITEM_TYPES: Final = frozenset(
    {
        "command_execution",
        "file_change",
        "mcp_tool_call",
        "web_search",
        "patch_apply",
        "local_shell_call",
    }
)

_MESSAGE_ITEM_TYPES: Final = frozenset(
    {
        "agent_message",
        "assistant_message",
    }
)


def _extract_error_text(data: Mapping[str, object]) -> str | None:
    parts: list[str] = []
    err_obj = data.get("error")
    if isinstance(err_obj, str) and err_obj.strip():
        parts.append(err_obj.strip())
    elif isinstance(err_obj, Mapping):
        err_map = cast("Mapping[str, object]", err_obj)
        msg = err_map.get("message")
        if isinstance(msg, str) and msg.strip():
            parts.append(msg.strip())
        code = err_map.get("code")
        if isinstance(code, str) and code.strip() and code.strip() not in parts:
            parts.append(code.strip())
    msg_top = data.get("message")
    if isinstance(msg_top, str) and msg_top.strip():
        parts.append(msg_top.strip())
    if not parts:
        return None
    return "; ".join(dict.fromkeys(parts))[:4000]


def _extract_tool_args(item: Mapping[str, object], item_type: str) -> dict[str, object]:
    if item_type == "command_execution":
        args: dict[str, object] = {}
        if "command" in item:
            args["command"] = item["command"]
        if "cwd" in item:
            args["cwd"] = item["cwd"]
        return args
    if item_type == "file_change":
        if "changes" in item:
            return {"changes": item["changes"]}
        if "path" in item:
            return {"path": item["path"]}
        return {}
    if item_type == "mcp_tool_call":
        args = {}
        for key in ("server", "tool", "arguments"):
            if key in item:
                args[key] = item[key]
        return args
    if item_type == "web_search":
        if "query" in item:
            return {"query": item["query"]}
        return {}
    excluded = {"id", "type", "status", "exit_code", "aggregated_output", "output", "duration_ms"}
    return {k: v for k, v in item.items() if k not in excluded}


def _looks_like_sandbox_denial(item: Mapping[str, object]) -> bool:
    status_raw = item.get("status")
    if isinstance(status_raw, str) and status_raw.casefold() in ("denied", "declined", "blocked"):
        return True
    candidates: list[str] = []
    for key in ("aggregated_output", "output", "error", "stderr", "reason"):
        val = item.get(key)
        if isinstance(val, str) and val:
            candidates.append(val)
        elif isinstance(val, Mapping):
            msg = cast("Mapping[str, object]", val).get("message")
            if isinstance(msg, str) and msg:
                candidates.append(msg)
    if not candidates:
        return False
    folded = " ".join(candidates).casefold()
    exit_code = item.get("exit_code")
    failed = (isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0) or (
        isinstance(status_raw, str) and status_raw.casefold() in ("failed", "error")
    )
    if not failed and "sandbox" not in folded and "permission denied" not in folded:
        return False
    return any(
        marker in folded
        for marker in (
            "permission denied",
            "operation not permitted",
            "read-only file system",
            "blocked by sandbox",
            "sandbox policy",
            "sandbox denied",
            "seccomp",
            "landlock",
        )
    )


def _extract_message_text(item: Mapping[str, object]) -> str | None:
    text = item.get("text")
    if isinstance(text, str) and text:
        return text
    content = item.get("content")
    if isinstance(content, list):
        parts: list[str] = []
        for entry in cast("list[object]", content):
            if isinstance(entry, Mapping):
                bmap = cast("Mapping[str, object]", entry)
                btext = bmap.get("text")
                if isinstance(btext, str) and btext:
                    parts.append(btext)
        if parts:
            return "".join(parts)
    return None


class CodexStreamParser:
    """Stateful line-by-line parser for Codex ``exec --json`` JSONL output."""

    def __init__(
        self,
        *,
        default_model: str | None = None,
        runtime_version: str | None = None,
        redact: Callable[[str], str] = identity_redact,
    ) -> None:
        self._default_model = bounded_model(default_model)
        self._runtime_version = bounded_version(runtime_version)
        self._redact = redact
        self._usage = UsageAccumulator()
        self._seq = 0
        self._saw_init = False
        self._saw_terminal = False
        self._is_error = False
        self._session_ref: str | None = None
        self._provider_model: str | None = None
        self._observed_effort: Effort | None = None
        self._stop_reason: StopReason = StopReason.END_TURN
        self._current_turn_texts: list[str] = []
        self._accepted_turn_texts: list[str] = []
        self._fatal_text: str | None = None
        self._last_notification_error: str | None = None
        self._last_notification_http_status: int | None = None
        self._http_status: int | None = None
        self._retry_category: str | None = None
        self._api_retries = 0
        self._limit_status: str | None = None
        self._limit_window: str | None = None
        self._limit_resets_at: int | None = None
        self._tool_calls = 0
        self._tool_by_call_id: dict[str, tuple[str, object]] = {}
        self._requested_calls: set[str] = set()
        self._completed_calls: set[str] = set()
        self._denied_calls: set[str] = set()
        self._denials: list[ToolDenial] = []

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
        if kind == "thread.started":
            events = tuple(self._handle_thread_started(data))
        elif kind == "turn.started":
            self._handle_turn_started(data)
        elif kind == "item.started":
            events = tuple(self._handle_item_started(data))
        elif kind == "item.completed":
            events = tuple(self._handle_item_completed(data))
        elif kind == "turn.completed":
            events = tuple(self._handle_turn_completed(data))
        elif kind == "turn.failed":
            self._handle_turn_failed(data)
        elif kind == "error":
            self._handle_error_notification(data)
        return events

    def is_terminal(self, line: bytes) -> bool:
        if not line.strip():
            return False
        try:
            parsed: object = json.loads(line.decode("utf-8", "strict"))
        except (UnicodeError, ValueError, RecursionError):
            return False
        if not isinstance(parsed, dict):
            return False
        kind = cast("dict[str, object]", parsed).get("type")
        return kind in ("turn.completed", "turn.failed")

    def saw_terminal(self) -> bool:
        return self._saw_terminal and not self._is_error

    def finish(self, exit_code: int | None) -> FinalOutcome:
        terminal_ok = self.saw_terminal()
        fatal_text = self._fatal_text
        http_status = self._http_status
        if fatal_text is None and (self._is_error or exit_code not in (None, 0)):
            fatal_text = self._last_notification_error
            if http_status is None:
                http_status = self._last_notification_http_status
        if http_status is None and fatal_text is not None:
            http_status = extract_http_status({}, fatal_text)

        signals = RuntimeSignals(
            exit_code=exit_code,
            fatal_text=fatal_text,
            is_error=True if self._is_error else (False if self._saw_terminal else None),
            http_status=http_status,
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
            final_text="\n\n".join(self._accepted_turn_texts) if terminal_ok else "",
            session_ref=self._session_ref,
            model=self._provider_model,
            observed_effort=self._observed_effort,
            usage=self._usage.final_usage(completed=terminal_ok),
            signals=signals,
            is_error=self._is_error,
            stop_reason=self._stop_reason,
            tools=tools,
            denials=tuple(self._denials),
        )

    def _handle_thread_started(self, data: Mapping[str, object]) -> Iterable[SessionEvent]:
        self._saw_init = True
        thread_id = bounded_id(data.get("thread_id") or data.get("session_id"))
        if thread_id is not None:
            self._session_ref = thread_id
        provider_model = bounded_model(data.get("model"))
        if provider_model is not None:
            self._provider_model = provider_model
        version = bounded_version(data.get("version") or data.get("codex_version")) or self._runtime_version
        yield SessionStarted(
            seq=self._next_seq(),
            at=_EPOCH_UTC,
            session_ref=thread_id,
            model=provider_model or self._default_model,
            runtime_version=version,
        )

    def _handle_turn_started(self, data: Mapping[str, object]) -> None:
        self._saw_terminal = False
        self._is_error = False
        self._fatal_text = None
        self._http_status = None
        self._last_notification_error = None
        self._last_notification_http_status = None
        self._limit_resets_at = None
        self._current_turn_texts.clear()
        self._usage.start_turn()
        provider_model = bounded_model(data.get("model"))
        if provider_model is not None:
            self._provider_model = provider_model

    def _emit_tool_requested(
        self,
        item: Mapping[str, object],
        item_type: str,
    ) -> tuple[str, ToolRequested | None]:
        raw_id = item.get("id") or item.get("call_id")
        call_id = bounded_id(raw_id) or f"call-{self._tool_calls + 1}"
        if call_id in self._requested_calls:
            return call_id, None
        self._tool_calls += 1
        self._requested_calls.add(call_id)
        tool_args = _extract_tool_args(item, item_type)
        self._tool_by_call_id[call_id] = (item_type, tool_args)
        canonical = json.dumps(
            tool_args,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )
        digest = f"sha256:{hashlib.sha256(canonical.encode('utf-8')).hexdigest()}"
        preview = self._redact(canonical)[:500]
        return (
            call_id,
            ToolRequested(
                seq=self._next_seq(),
                at=_EPOCH_UTC,
                call_id=call_id,
                tool=item_type,
                args_preview=preview,
                args_digest=digest,
            ),
        )

    def _handle_item_started(self, data: Mapping[str, object]) -> Iterable[SessionEvent]:
        if "usage" in data:
            self._usage.record_delta_usage(data.get("usage"))
        raw_item = data.get("item")
        if not isinstance(raw_item, Mapping):
            return
        item = cast("Mapping[str, object]", raw_item)
        if "usage" in item:
            self._usage.record_delta_usage(item.get("usage"))
        item_type = bounded_id(item.get("type"))
        if item_type is None or item_type not in _TOOL_ITEM_TYPES:
            return
        _, req_event = self._emit_tool_requested(item, item_type)
        if req_event is not None:
            yield req_event

    def _handle_item_completed(self, data: Mapping[str, object]) -> Iterable[SessionEvent]:
        if "usage" in data:
            self._usage.record_delta_usage(data.get("usage"))
        raw_item = data.get("item")
        if not isinstance(raw_item, Mapping):
            return
        item = cast("Mapping[str, object]", raw_item)
        if "usage" in item:
            self._usage.record_delta_usage(item.get("usage"))
        item_type = bounded_id(item.get("type"))
        if item_type is None:
            return

        if item_type == "reasoning":
            # Normative (Dossier §3.4): reasoning items are omitted from public events (transcript only).
            return

        if item_type in _MESSAGE_ITEM_TYPES:
            raw_text = _extract_message_text(item)
            if raw_text is not None:
                safe_text = self._redact(raw_text)
                self._current_turn_texts.append(safe_text)
                yield TextDelta(
                    seq=self._next_seq(),
                    at=_EPOCH_UTC,
                    channel="assistant",
                    text=safe_text,
                )
            return

        if item_type in _TOOL_ITEM_TYPES:
            call_id, req_event = self._emit_tool_requested(item, item_type)
            if req_event is not None:
                yield req_event
            if call_id in self._completed_calls:
                return
            self._completed_calls.add(call_id)

            exit_code = item.get("exit_code")
            status_raw = item.get("status")
            status_failed = isinstance(status_raw, str) and status_raw.casefold() in (
                "failed",
                "error",
                "declined",
                "denied",
            )
            is_failed = (
                isinstance(exit_code, int) and not isinstance(exit_code, bool) and exit_code != 0
            ) or status_failed
            if _looks_like_sandbox_denial(item):
                status = ToolCallStatus.DENIED
                if call_id not in self._denied_calls:
                    self._denied_calls.add(call_id)
                    tool_name, tool_input = self._tool_by_call_id.get(call_id, (item_type, item))
                    self._denials.append(ToolDenial(tool=tool_name, hint=denial_hint(tool_name, tool_input)))
            elif is_failed:
                status = ToolCallStatus.ERROR
            else:
                status = ToolCallStatus.OK

            yield ToolCompleted(
                seq=self._next_seq(),
                at=_EPOCH_UTC,
                call_id=call_id,
                status=status,
                duration_ms=nonneg_opt(item.get("duration_ms")),
            )

    def _handle_turn_completed(self, data: Mapping[str, object]) -> Iterable[SessionEvent]:
        provider_model = bounded_model(data.get("model"))
        if provider_model is not None:
            self._provider_model = provider_model
        effort = data.get("reasoning_effort")
        if isinstance(effort, str) and effort in tuple(Effort):
            self._observed_effort = Effort(effort)
        usage_report = self._usage.record_turn_usage(data.get("usage"))
        if usage_report is not None:
            yield UsageReported(
                seq=self._next_seq(),
                at=_EPOCH_UTC,
                usage=usage_report,
                cumulative=True,
            )
        self._accepted_turn_texts = list(self._current_turn_texts)
        self._current_turn_texts.clear()
        self._fatal_text = None
        self._http_status = None
        self._last_notification_error = None
        self._last_notification_http_status = None
        self._limit_resets_at = None
        self._is_error = False
        self._saw_terminal = True

    def _handle_turn_failed(self, data: Mapping[str, object]) -> None:
        self._usage.fail_turn()
        self._current_turn_texts.clear()
        self._is_error = True
        self._saw_terminal = True
        err_text = _extract_error_text(data)
        self._fatal_text = self._redact(err_text) if err_text is not None else None
        self._http_status = extract_http_status(data, err_text)
        raw_resets = data.get("limit_resets_at")
        err_obj = data.get("error")
        if raw_resets is None and isinstance(err_obj, Mapping):
            err_map = cast("Mapping[str, object]", err_obj)
            raw_resets = err_map.get("resets_at") or err_map.get("limit_resets_at")
        if not isinstance(raw_resets, bool) and isinstance(raw_resets, (int, float)) and raw_resets > 0:
            self._limit_resets_at = int(raw_resets)

    def _handle_error_notification(self, data: Mapping[str, object]) -> None:
        """Non-fatal diagnostic notification (e.g. 'Reconnecting... 1/5'). Does NOT set is_error."""
        err_text = _extract_error_text(data)
        if err_text is not None:
            self._last_notification_error = self._redact(err_text)
            match = _RECONNECT_RE.search(err_text)
            if match is not None:
                attempt = int(match.group(1))
                self._api_retries = max(self._api_retries, attempt)
        status = extract_http_status(data, err_text)
        if status is not None:
            self._last_notification_http_status = status
