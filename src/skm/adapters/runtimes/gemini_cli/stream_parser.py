"""Parse Gemini CLI headless JSONL into the shared supervised session protocol."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from typing import NoReturn, cast

from skm.adapters.runtimes._cli_session.session import FinalOutcome
from skm.adapters.runtimes._cli_session.wire_values import (
    bounded_id,
    bounded_model,
    extract_http_status,
    identity_redact,
)
from skm.modules.runtimes.domain.error_rules import RuntimeSignals
from skm.modules.runtimes.domain.observation import ToolVisibility
from skm.modules.runtimes.domain.session_events import (
    SessionEvent,
    SessionStarted,
    TextDelta,
    ToolCallStatus,
    ToolCompleted,
    ToolRequested,
    UsageReported,
)
from skm.modules.runtimes.domain.usage import unknown_usage

from .usage import parse_usage

__all__: list[str] = []

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class GeminiCliStreamParser:
    def __init__(
        self, *, model: str, version: str | None, redact: Callable[[str], str] = identity_redact
    ) -> None:
        self._model = model
        self._version = version
        self._redact = redact
        self._seq = 0
        self._session_ref: str | None = None
        self._assistant: list[str] = []
        self._tools: set[str] = set()
        self._completed_tools: set[str] = set()
        self._result_status: str | None = None
        self._invalid = False
        self._is_error = False
        self._fatal_text: str | None = None
        self._http_status: int | None = None
        self._usage = unknown_usage()

    def _next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def _reject(self, detail: str) -> NoReturn:
        self._invalid = True
        raise ValueError(detail)

    def feed(self, line: bytes) -> Iterable[SessionEvent]:
        try:
            raw: object = json.loads(line.decode("utf-8"))
        except (ValueError, RecursionError):
            self._invalid = True
            raise ValueError("Invalid Gemini CLI JSONL") from None
        if not isinstance(raw, dict):
            self._reject("Expected a Gemini CLI event object")
        data = cast("dict[str, object]", raw)
        if self._result_status is not None:
            self._reject("Gemini CLI emitted an event after its result")
        kind = data.get("type")
        if kind == "init":
            return self._init(data)
        if kind == "error" and data.get("severity") == "error":
            self._error(data, data)
        if kind == "result":
            return self._result(data)
        if self._session_ref is None:
            return ()
        if kind == "message":
            return self._message(data)
        if kind == "tool_use":
            return self._tool_use(data)
        if kind == "tool_result":
            return self._tool_result(data)
        return ()

    def _init(self, data: Mapping[str, object]) -> tuple[SessionStarted, ...]:
        session_ref = bounded_id(data.get("session_id"))
        if (
            self._session_ref is not None
            or session_ref is None
            or bounded_model(data.get("model")) != self._model
        ):
            self._reject("Invalid Gemini CLI session or model")
        self._session_ref = session_ref
        return (
            SessionStarted(
                seq=self._next_seq(),
                at=_EPOCH,
                session_ref=session_ref,
                model=self._model,
                runtime_version=self._version,
            ),
        )

    def _message(self, data: Mapping[str, object]) -> tuple[TextDelta, ...]:
        content = data.get("content")
        if data.get("role") != "assistant" or not isinstance(content, str) or not content:
            return ()
        self._assistant.append(content)
        return (TextDelta(seq=self._next_seq(), at=_EPOCH, channel="assistant", text=self._redact(content)),)

    def _tool_use(self, data: Mapping[str, object]) -> tuple[ToolRequested, ...]:
        call_id = bounded_id(data.get("tool_id"))
        tool = bounded_id(data.get("tool_name"))
        if call_id is None or tool is None or call_id in self._tools:
            return ()
        self._tools.add(call_id)
        self._assistant.clear()
        args = json.dumps(data.get("parameters", {}), sort_keys=True, separators=(",", ":"))
        return (
            ToolRequested(
                seq=self._next_seq(),
                at=_EPOCH,
                call_id=call_id,
                tool=tool,
                args_preview=self._redact(args)[:500],
                args_digest=f"sha256:{hashlib.sha256(args.encode()).hexdigest()}",
            ),
        )

    def _tool_result(self, data: Mapping[str, object]) -> tuple[ToolCompleted, ...]:
        call_id = bounded_id(data.get("tool_id"))
        if call_id is None or call_id not in self._tools or call_id in self._completed_tools:
            return ()
        self._completed_tools.add(call_id)
        status = ToolCallStatus.OK if data.get("status") == "success" else ToolCallStatus.ERROR
        return (
            ToolCompleted(seq=self._next_seq(), at=_EPOCH, call_id=call_id, status=status, duration_ms=None),
        )

    def _error(self, data: Mapping[str, object], error: Mapping[str, object]) -> None:
        self._is_error = True
        message = error.get("message")
        if isinstance(message, str) and message:
            self._fatal_text = self._redact(message[:4000])
        status = extract_http_status({**error, "error_status": error.get("code")}, self._fatal_text)
        self._http_status = status or extract_http_status(data) or self._http_status

    def _result(self, data: Mapping[str, object]) -> tuple[UsageReported, ...]:
        status = data.get("status")
        if status == "error":
            self._result_status = "error"
            error = data.get("error")
            self._error(data, cast("Mapping[str, object]", error) if isinstance(error, Mapping) else data)
        elif status == "success" and self._session_ref is not None:
            self._result_status = "success"
        else:
            self._reject("Invalid Gemini CLI terminal result")
        self._usage = parse_usage(data.get("stats"))
        if self._usage.is_empty():
            return ()
        return (UsageReported(seq=self._next_seq(), at=_EPOCH, usage=self._usage, cumulative=True),)

    def is_terminal(self, line: bytes) -> bool:
        del line
        return self._result_status is not None

    def saw_terminal(self) -> bool:
        return self._result_status == "success" and not (self._invalid or self._is_error)

    def finish(self, exit_code: int | None) -> FinalOutcome:
        complete = self.saw_terminal()
        tools = ToolVisibility("unavailable", None)
        if self._session_ref is not None:
            tools = ToolVisibility(
                "complete" if complete and self._tools == self._completed_tools else "partial",
                len(self._tools),
            )
        return FinalOutcome(
            final_text=self._redact("".join(self._assistant)) if complete else "",
            session_ref=self._session_ref,
            model=self._model if self._session_ref is not None else None,
            usage=self._usage,
            signals=RuntimeSignals(
                exit_code=exit_code,
                fatal_text=self._fatal_text,
                http_status=self._http_status,
                is_error=self._is_error,
                terminal=complete,
            ),
            is_error=self._is_error,
            tools=tools,
        )
