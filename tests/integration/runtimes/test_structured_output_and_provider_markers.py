"""Codex multi-agent flags, structured stream results, and merged provider error markers."""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path
from typing import override

from contracts.runtimes.conftest import WireParser, build
from integration.runtimes.test_codex_argv import _make_request
from skm.adapters.runtimes.claude_code.runtime import ClaudeCodeRuntime
from skm.adapters.runtimes.claude_code.stream_parser import ClaudeStreamParser
from skm.adapters.runtimes.codex.launch import _render_codex_argv
from skm.adapters.runtimes.codex.permissions import RenderedPermissions
from skm.adapters.runtimes.codex.runtime import CodexRuntime
from skm.kernel.error_codes import ErrorCode
from skm.modules.runtimes import public as rt
from skm.modules.runtimes.domain.error_rules import (
    ErrorClass,
    ErrorScope,
    RuntimeSignals,
    classify,
)

_NOW = 1_790_000_000
_MULTI_AGENT = (
    "-c",
    "features.multi_agent=false",
    "-c",
    "features.multi_agent_v2=false",
)


def _line(payload: object) -> bytes:
    return (json.dumps(payload) + "\n").encode()


def _perms(tmp_path: Path, argv: tuple[str, ...], *, bypass: bool = False) -> RenderedPermissions:
    return RenderedPermissions(
        sandbox_mode="workspace-write",
        argv=argv,
        config_path=tmp_path / "config.toml",
        bypass_approvals_and_sandbox=bypass,
    )


class _StructuredWire(WireParser):
    """Fixture parser that copies an optional structured payload onto the outcome."""

    @override
    def feed(self, line: bytes) -> Iterable[rt.SessionEvent]:
        events = tuple(super().feed(line))
        data = json.loads(line)
        structured = data.get("structured")
        if structured is not None and data.get("type") in {"fake_result", "error"}:
            self.outcome = replace(self.outcome, structured=structured)
        return events


def test_codex_argv_disables_multi_agent_on_the_shared_tail(tmp_path: Path) -> None:
    fresh = _render_codex_argv(
        _make_request(tmp_path / "fresh", effort=None),
        binary_path="codex",
        rendered_perms=_perms(tmp_path, ("--sandbox", "workspace-write")),
    )
    assert fresh[fresh.index("--model") + 2 :] == (*_MULTI_AGENT, "-")
    assert "features.multi_agent=false" not in fresh[: fresh.index("--model")]

    resume_ref = "0199aa00-thread-7"
    resume = _render_codex_argv(
        _make_request(
            tmp_path / "resume",
            effort=None,
            resume_session_ref=resume_ref,
            session_policy="ephemeral",
        ),
        binary_path="codex",
        rendered_perms=_perms(
            tmp_path,
            ("-c", 'sandbox_mode="workspace-write"'),
            bypass=True,
        ),
    )
    assert resume[:6] == ("codex", "-a", "never", "exec", "resume", resume_ref)
    assert resume[1:][4] == resume_ref
    assert "features.multi_agent=false" not in resume[:6]
    model_at = resume.index("--model")
    assert resume[model_at + 2 :] == (
        *_MULTI_AGENT,
        "--ephemeral",
        "--dangerously-bypass-approvals-and-sandbox",
        "-",
    )


def test_stream_json_publishes_structured_output_only_for_a_terminal_success() -> None:
    structured_only = ClaudeStreamParser()
    payload = {"answer": 1, "ok": False, "items": [None, "a"]}
    list(
        structured_only.feed(
            _line({"type": "result", "is_error": False, "result": "", "structured_output": payload})
        )
    )
    assert structured_only.saw_terminal() is True
    only = structured_only.finish(0)
    assert only.final_text == ""
    assert only.structured == payload

    with_text = ClaudeStreamParser()
    list(with_text.feed(_line({"type": "result", "result": "hello", "structured_output": ["x"]})))
    both = with_text.finish(0)
    assert both.final_text == "hello"
    assert both.structured == ["x"]

    errored = ClaudeStreamParser()
    list(
        errored.feed(
            _line(
                {
                    "type": "result",
                    "is_error": True,
                    "result": "authentication failed",
                    "structured_output": payload,
                }
            )
        )
    )
    assert errored.saw_terminal() is False
    failed = errored.finish(1)
    assert failed.final_text == ""
    assert failed.structured is None

    flipped = ClaudeStreamParser()
    list(flipped.feed(_line({"type": "result", "result": "kept", "structured_output": {"n": 1}})))
    list(
        flipped.feed(
            _line({"type": "result", "is_error": True, "result": "boom", "structured_output": {"n": 2}})
        )
    )
    assert flipped.saw_terminal() is False
    dropped = flipped.finish(1)
    assert dropped.final_text == ""
    assert dropped.structured is None

    partial = ClaudeStreamParser()
    list(partial.feed(_line({"type": "system", "subtype": "init", "session_id": "sess-1"})))
    assert partial.saw_terminal() is False
    unfinished = partial.finish(None)
    assert unfinished.final_text == ""
    assert unfinished.structured is None


def test_structured_only_success_is_completed_and_blank_text_stays_empty(tmp_path: Path) -> None:
    payload = {"answer": 1}
    completed = build(
        tmp_path / "structured",
        stdout=_line({"type": "fake_result", "final_text": "", "structured": payload}),
        parser=_StructuredWire(),
    ).session.result()
    assert completed.outcome == "completed"
    assert completed.failure is None
    assert completed.final_text == ""
    assert completed.structured == payload

    blank = build(
        tmp_path / "blank",
        stdout=_line({"type": "fake_result", "final_text": "   "}),
    ).session.result()
    assert blank.outcome == "failed"
    assert blank.final_text == ""
    assert blank.structured is None
    failure = blank.failure
    assert failure is not None
    assert failure.code is ErrorCode.RESULT_INVALID
    assert failure.details.get("reason") == "empty_output"

    leaked = build(
        tmp_path / "error",
        stdout=_line({"type": "error", "error": "nope", "http_status": 500, "structured": payload}),
        exit_code=1,
        parser=_StructuredWire(),
    ).session.result()
    assert leaked.outcome == "failed"
    assert leaked.final_text == ""
    assert leaked.structured is None
    assert leaked.failure is not None


def test_provider_error_markers_classify_without_stealing_rate_limits() -> None:
    codex_rules = CodexRuntime()._error_rules
    codex_cases = (
        (
            "authentication failed",
            ErrorClass.AUTHENTICATION,
            ErrorCode.RUNTIME_AUTH_EXPIRED,
            ErrorScope.ACCOUNT,
        ),
        (
            "The model does not exist or you do not have access to it",
            ErrorClass.MODEL_UNAVAILABLE,
            ErrorCode.MODEL_UNAVAILABLE,
            ErrorScope.REQUEST,
        ),
        (
            "Usage limit exceeded",
            ErrorClass.QUOTA,
            ErrorCode.QUOTA_EXHAUSTED,
            ErrorScope.ACCOUNT,
        ),
        ("quota exhausted", ErrorClass.QUOTA, ErrorCode.QUOTA_EXHAUSTED, ErrorScope.ACCOUNT),
        (
            "Usage limit exceeded; quota exhausted",
            ErrorClass.QUOTA,
            ErrorCode.QUOTA_EXHAUSTED,
            ErrorScope.ACCOUNT,
        ),
    )
    for text, error_class, code, scope in codex_cases:
        failure = classify("codex", RuntimeSignals(fatal_text=text, exit_code=1), codex_rules, now_unix=_NOW)
        assert failure.error_class is error_class
        assert failure.code is code
        assert failure.scope is scope

    claude_rules = ClaudeCodeRuntime()._error_rules
    limited = classify(
        "claude_code",
        RuntimeSignals(
            http_status=429,
            is_error=True,
            retry_category="rate_limit",
            limit_status="rejected",
            fatal_text="API Error: 429 rate_limit_error: Too many requests",
            exit_code=1,
            limit_resets_at=_NOW + 7200,
        ),
        claude_rules,
        now_unix=_NOW,
    )
    assert limited.code is ErrorCode.RATE_LIMITED
    assert limited.error_class is ErrorClass.RATE_LIMIT
    assert limited.retryable is True
    assert limited.retry_after_seconds == 7200

    claude_signals = (
        ("authentication_failed", ErrorClass.AUTHENTICATION, ErrorCode.RUNTIME_AUTH_EXPIRED),
        ("cloud_credential_error", ErrorClass.AUTHENTICATION, ErrorCode.RUNTIME_AUTH_EXPIRED),
        ("oauth_org_not_allowed", ErrorClass.AUTHORIZATION, ErrorCode.RUNTIME_FORBIDDEN),
        ("account_on_hold", ErrorClass.AUTHORIZATION, ErrorCode.RUNTIME_FORBIDDEN),
        ("billing_error", ErrorClass.AUTHORIZATION, ErrorCode.RUNTIME_FORBIDDEN),
        ("overloaded", ErrorClass.PROVIDER_INTERNAL, ErrorCode.RUNTIME_OVERLOADED),
        ("server_error", ErrorClass.PROVIDER_INTERNAL, ErrorCode.RUNTIME_OVERLOADED),
        ("model_not_found", ErrorClass.MODEL_UNAVAILABLE, ErrorCode.MODEL_UNAVAILABLE),
        ("invalid_request", ErrorClass.INVALID_REQUEST, ErrorCode.RUNTIME_INVALID_REQUEST),
    )
    for category, error_class, code in claude_signals:
        failure = classify(
            "claude_code",
            RuntimeSignals(retry_category=category, is_error=True, exit_code=1),
            claude_rules,
            now_unix=_NOW,
        )
        assert failure.error_class is error_class
        assert failure.code is code

    bare = classify(
        "claude_code",
        RuntimeSignals(retry_category="authentication_failed", is_error=False, exit_code=1),
        claude_rules,
        now_unix=_NOW,
    )
    assert bare.code is ErrorCode.RUNTIME_CRASHED

    for marker in ("session limit", "weekly limit"):
        failure = classify(
            "claude_code",
            RuntimeSignals(fatal_text=f"provider {marker} reached", exit_code=1),
            claude_rules,
            now_unix=_NOW,
        )
        assert failure.code is ErrorCode.QUOTA_EXHAUSTED
        assert failure.error_class is ErrorClass.QUOTA
        assert failure.scope is ErrorScope.ACCOUNT

    # Codex classifies HTTP 429 ahead of these text markers.
    for text in ("Usage limit exceeded", "authentication failed", "quota exhausted"):
        limited_codex = classify(
            "codex",
            RuntimeSignals(
                http_status=429,
                fatal_text=text,
                exit_code=1,
                limit_resets_at=_NOW + 45,
            ),
            codex_rules,
            now_unix=_NOW,
        )
        assert limited_codex.code is ErrorCode.RATE_LIMITED
        assert limited_codex.error_class is ErrorClass.RATE_LIMIT
        assert limited_codex.retryable is True
        assert limited_codex.retry_after_seconds == 45

    for marker in ("session limit", "weekly limit"):
        limited_claude = classify(
            "claude_code",
            RuntimeSignals(
                http_status=429,
                fatal_text=f"HTTP 429 {marker} reached",
                exit_code=1,
                limit_resets_at=_NOW + 30,
            ),
            claude_rules,
            now_unix=_NOW,
        )
        assert limited_claude.code is ErrorCode.QUOTA_EXHAUSTED
        assert limited_claude.error_class is ErrorClass.QUOTA
        assert limited_claude.scope is ErrorScope.ACCOUNT
        assert limited_claude.retryable is False
        assert limited_claude.retry_after_seconds == 30


def test_nested_non_finite_structured_output_is_dropped() -> None:
    rejected = ClaudeStreamParser()
    raw = (
        '{"type":"result","is_error":false,"result":"ok",'
        '"structured_output":{"answer":1,"nested":{"too_big":1e999},'
        '"items":[0,{"inner":-1e999},NaN,Infinity]}}\n'
    )
    list(rejected.feed(raw.encode()))
    outcome = rejected.finish(0)
    assert rejected.saw_terminal() is True
    assert outcome.final_text == "ok"
    assert outcome.structured is None

    finite = ClaudeStreamParser()
    list(
        finite.feed(
            _line(
                {
                    "type": "result",
                    "result": "ok",
                    "structured_output": {"nested": {"n": 1.5}, "items": [None, 0, False]},
                }
            )
        )
    )
    kept = finite.finish(0)
    assert kept.structured == {"nested": {"n": 1.5}, "items": [None, 0, False]}
