"""Normalize one AGY turn while keeping native diagnostics in the redacted transcript."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from datetime import UTC, datetime
from typing import cast

from skm.adapters.runtimes._cli_session.session import FinalOutcome
from skm.adapters.runtimes._cli_session.wire_values import bounded_id, bounded_model, nonneg_opt
from skm.modules.runtimes.domain.error_rules import RuntimeSignals
from skm.modules.runtimes.domain.session_events import SessionEvent, SessionStarted, TextDelta
from skm.modules.runtimes.domain.usage import UsageReport, UsageStatus, unknown_usage

__all__: list[str] = []

_EPOCH = datetime(1970, 1, 1, tzinfo=UTC)
_ERROR_STATUS = re.compile(r"^[A-Z_]+ \(code ([1-5][0-9]{2})\):")
_COUNTER_MAX = 2**63 - 1


def _record(value: object) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ValueError("expected an Antigravity event object")
    return cast("dict[str, object]", value)


def _usage(value: object) -> UsageReport:
    data: Mapping[str, object] = cast("Mapping[str, object]", value) if isinstance(value, dict) else {}
    report = unknown_usage("stream:agy_result")

    def counter(name: str) -> int | None:
        result = nonneg_opt(data.get(name))
        return result if result is not None and result <= _COUNTER_MAX else None

    cache = counter("cache_read_tokens")
    # AGY has no stable fresh-input contract when cache is used.
    fresh = counter("input_tokens") if cache == 0 else None
    output, reasoning = counter("output_tokens"), counter("thinking_tokens")
    if all(value is None for value in (fresh, output, cache, reasoning)):
        return report
    return replace(
        report,
        status=UsageStatus.REPORTED,
        input_tokens=fresh,
        output_tokens=output,
        cache_read_tokens=cache,
        reasoning_tokens=reasoning,
    )


class AntigravityStreamParser:
    def __init__(
        self, *, models: frozenset[str], version: str | None, workdir: str, redact: Callable[[str], str]
    ) -> None:
        self._models = models
        self._version = version
        self._workdir = workdir
        self._redact = redact
        self._started: SessionStarted | None = None
        self._reported_model: str | None = None
        self._session: str | None = None
        self._emitted_steps: set[int] = set()
        self._terminal: FinalOutcome | None = None
        self._clean_success = False
        self._invalid = False
        self._error_steps: set[int] = set()
        self._completed_response = False

    def feed(self, line: bytes) -> Iterable[SessionEvent]:
        try:
            return self._consume(_record(json.loads(line)))
        except (ValueError, TypeError, UnicodeError, RecursionError):
            self._invalid = True
            raise

    def _consume(self, doc: Mapping[str, object]) -> tuple[SessionEvent, ...]:
        kind = doc.get("event")
        if self._terminal is not None:
            raise ValueError("Antigravity emitted an event after its result")
        if kind == "init":
            return (self._init(doc),)
        if kind == "step_update":
            step = _record(doc.get("step_update"))
            self._require_session(step)
            return self._observe_step(step)
        if kind == "result":
            self._result(_record(doc.get("result")))
        else:
            raise ValueError("unknown Antigravity event")
        return ()

    def _init(self, doc: Mapping[str, object]) -> SessionStarted:
        session = bounded_id(doc.get("conversation_id"))
        init = _record(doc.get("init"))
        model = bounded_model(init.get("model"))
        if self._reported_model is not None or session is None or model is None:
            raise ValueError("unexpected Antigravity session or model")
        if init.get("cwd") != self._workdir:
            raise ValueError("Antigravity reported a different workspace")
        self._reported_model = model
        if model not in self._models:
            raise ValueError("unexpected Antigravity session or model")
        self._session = session
        self._started = SessionStarted(1, _EPOCH, self._redact(session), model, self._version)
        return self._started

    def _require_session(self, doc: Mapping[str, object]) -> None:
        session = bounded_id(doc.get("conversation_id"))
        if session is None or session != self._session:
            raise ValueError("Antigravity event belongs to another conversation")

    def _observe_step(self, doc: Mapping[str, object]) -> tuple[SessionEvent, ...]:
        kind, state = doc.get("step_type"), doc.get("state")
        index = nonneg_opt(doc.get("step_index"))
        if kind == "error_message" and state == "DONE" and index is not None:
            self._error_steps.add(index)
        elif kind not in ("user_input", "error_message"):
            self._error_steps.clear()
            if kind != "agent_response" or state == "DONE":
                self._completed_response = kind == "agent_response"
        text = doc.get("text_delta")
        if (
            kind == "agent_response"
            and state == "DONE"
            and index is not None
            and index not in self._emitted_steps
            and isinstance(text, str)
            and text
        ):
            self._emitted_steps.add(index)
            return (TextDelta(1, _EPOCH, "assistant", self._redact(text)),)
        return ()

    def _result(self, doc: Mapping[str, object]) -> None:
        status, response = doc.get("status"), doc.get("response")
        error = doc.get("error")
        if status not in ("SUCCESS", "ERROR") or not isinstance(response, str):
            raise ValueError("invalid Antigravity result")
        if self._started is not None or status != "ERROR" or doc.get("conversation_id") != "":
            self._require_session(doc)
        # AGY reports partial responses as SUCCESS on print-timeout, including exit zero.
        timeout = doc.get("finished_reason") == "print_timeout"
        fatal = (error if isinstance(error, str) and error else response) if status == "ERROR" else ""
        match = _ERROR_STATUS.match(fatal)
        is_error = status == "ERROR" or timeout
        self._terminal = FinalOutcome(
            final_text="" if is_error else self._redact(response),
            usage=_usage(doc.get("usage")),
            is_error=is_error,
            signals=RuntimeSignals(
                is_error=is_error,
                terminal=True,
                fatal_text=self._redact(fatal) if fatal else None,
                http_status=int(match[1]) if match else None,
                retry_category="print_timeout" if timeout else None,
            ),
        )

    def is_terminal(self, line: bytes) -> bool:
        del line
        return self._terminal is not None or self._repeated_errors()

    def saw_terminal(self) -> bool:
        return self._clean_success

    def _repeated_errors(self) -> bool:
        return len(self._error_steps) >= 3 and not self._completed_response

    def finish(self, exit_code: int | None) -> FinalOutcome:
        outcome = self._terminal if not self._invalid else None
        self._clean_success = outcome is not None and exit_code == 0 and not outcome.is_error
        if outcome is None:
            repeated = not self._invalid and self._repeated_errors()
            outcome = FinalOutcome(
                is_error=repeated,
                signals=RuntimeSignals(retry_category="repeated_error_steps" if repeated else None),
            )
        if self._started is not None:
            outcome = replace(outcome, session_ref=self._started.session_ref)
        return replace(outcome, model=self._reported_model)
