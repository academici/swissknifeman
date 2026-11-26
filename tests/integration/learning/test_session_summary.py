"""Bounded Claude Code JSONL intake preserves unknown metrics and excludes raw content."""

import argparse
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from io import StringIO
from json import dumps
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from fixtures.hooks.subprocess.harness import cached_invocation
from integration.integrations.test_hooks import env, hook_env, set_modes
from skm.adapters.integrations.claude_code.session_summary import MAX_TRANSCRIPT_BYTES, summarize_session
from skm.application_bus.host import HostContext
from skm.bootstrap import hook
from skm.bootstrap.composition_resources import TokenPepper
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork
from skm.modules.access.ports import TokenPepperSource
from skm.modules.access.public import CreateToken, WhoAmI, authenticate_token
from skm.modules.learning.application.commands.extract_candidates import ActivityStorage
from skm.modules.learning.domain.activity import ActivitySummary, Outcome
from skm.modules.learning.ports import ActivityRecordRepository
from skm.modules.settings.generated.commands import SetValue
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "env", "hook_env", "pg_session", "test_database"]

_NOW = datetime(2026, 11, 1, tzinfo=UTC)


def _message(kind: str, blocks: list[dict[str, Any]], *, stop_reason: str | None = None) -> str:
    return dumps(
        {
            "type": kind,
            "sessionId": "session-1",
            "message": {
                "id": "m1" if stop_reason is None else "m2",
                "content": blocks,
                "usage": {"input_tokens": 4},
                "stop_reason": stop_reason,
            },
        }
    )


def test_reads_only_bound_structured_metrics(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
    transcript.write_text(
        "\n".join(
            [
                _message(
                    "assistant",
                    [
                        {"type": "text", "text": secret},
                        *(
                            {
                                "type": "tool_use",
                                "id": str(i),
                                "name": "Read",
                                "input": {"file_path": str(tmp_path / "a")},
                            }
                            for i in range(2)
                        ),
                    ],
                ),
                _message(
                    "user",
                    [{"type": "tool_result", "tool_use_id": str(i), "content": secret} for i in range(2)],
                ),
                _message("assistant", [{"type": "text", "text": secret}], stop_reason="end_turn"),
                dumps({"type": "future_metadata", "sessionId": "session-1", "value": []}),
            ]
        )
    )
    result = summarize_session(transcript, session_id="session-1", checkout=tmp_path, observed_at=_NOW)
    assert result is not None
    assert secret not in dumps(result)
    assert str(tmp_path) not in dumps(result)
    summary = ActivitySummary.from_json(result)
    assert summary.tools_total == summary.reads_total == 2
    assert summary.reads_unique == 1
    assert summary.usage_input == 8
    assert summary.files_changed == ()
    assert summary.error_loops == ()
    assert summary.checks is None
    assert summary.usage_cache_read is None
    assert summary.outcome is Outcome.UNKNOWN
    assert summary.exposure_coverage == "unknown"
    assert result["adapter_id"] == "claude_code"
    assert result["adapter_version"] == result["parser_version"] == "1"
    assert result["source_format"] == "claude_code_jsonl"
    assert summary.metric_coverage is not None
    assert summary.metric_coverage["tools_total"] == summary.metric_coverage["files_changed"] == "complete"
    assert summary.metric_coverage["usage_input"] == "complete"
    assert summary.metric_coverage["usage_cache_read"] == summary.metric_coverage["checks"] == "unknown"
    assert summary.metric_coverage["outcome"] == "unknown"
    serialized = summary.to_json()
    for field in ("adapter_id", "adapter_version", "parser_version", "source_format", "metric_coverage"):
        assert serialized[field] == result[field]
    assert summarize_session(transcript, session_id="foreign", checkout=tmp_path, observed_at=_NOW) is None


@pytest.mark.parametrize(
    "rows",
    [
        [_message("assistant", [])],
        [_message("assistant", [], stop_reason="end_turn"), _message("user", [])],
        [_message("assistant", [], stop_reason="end_turn"), "{malformed"],
        [_message("assistant", [], stop_reason="end_turn"), dumps({"type": [], "sessionId": "session-1"})],
        [_message("assistant", [{"type": []}], stop_reason="end_turn")],
    ],
    ids=["prefix", "missing-tail", "invalid-json", "invalid-row-type", "invalid-block-type"],
)
def test_partial_or_malformed_does_not_claim_complete_metrics(tmp_path: Path, rows: list[str]) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text("\n".join(rows))
    result = summarize_session(transcript, session_id="session-1", checkout=tmp_path, observed_at=_NOW)
    assert result is not None
    summary = ActivitySummary.from_json(result)
    assert summary.tools_total is summary.reads_total is summary.files_changed is None
    assert summary.outcome is Outcome.UNKNOWN
    assert summary.exposure_coverage == "unknown"
    assert summary.metric_coverage is not None
    assert summary.metric_coverage["tools_total"] == "partial"
    assert summary.metric_coverage["reads_total"] == summary.metric_coverage["files_changed"] == "partial"
    assert summary.metric_coverage["checks"] == summary.metric_coverage["outcome"] == "unknown"


def test_completed_session_can_establish_zero_metrics(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    transcript.write_text(_message("assistant", [], stop_reason="end_turn"))
    result = summarize_session(transcript, session_id="session-1", checkout=tmp_path, observed_at=_NOW)
    assert result is not None
    assert result["tools_total"] == result["reads_total"] == 0
    assert result["files_changed"] == []


def test_oversized_and_non_regular_inputs_are_ignored(tmp_path: Path) -> None:
    transcript = tmp_path / "session.jsonl"
    with transcript.open("wb") as stream:
        stream.truncate(MAX_TRANSCRIPT_BYTES + 1)
    assert summarize_session(transcript, session_id="session-1", checkout=tmp_path, observed_at=_NOW) is None
    assert summarize_session(tmp_path, session_id="session-1", checkout=tmp_path, observed_at=_NOW) is None


def test_spool_defers_read_and_drops_disabled_observation(tmp_path: Path) -> None:
    from skm.adapters.integrations.claude_code.session_summary import SessionSummarySpool
    from skm.kernel.json_types import JsonObject

    wakes: list[bool] = []
    seen: list[tuple[str, JsonObject]] = []
    folder = tmp_path / "spool"
    source = tmp_path / "session-1.jsonl"
    key = str(UUID(int=1))
    spool = SessionSummarySpool(folder, tmp_path, wake=lambda: wakes.append(True), now=lambda: _NOW)
    spool.enqueue(key, str(tmp_path), "session-1", str(source))
    assert wakes == [True]
    assert len(list(folder.glob("*.json"))) == 1
    assert seen == []
    source.write_text(_message("assistant", []))
    assert (
        spool.drain(enabled=lambda _: False, dispatch=lambda project, doc: seen.append((project, doc))) == 0
    )
    assert seen == []
    spool.enqueue(key, str(tmp_path), "session-1", str(source))
    assert spool.drain(enabled=lambda _: True, dispatch=lambda project, doc: seen.append((project, doc))) == 1
    assert seen[0][0] == key
    assert seen[0][1]["outcome"] == "unknown"
    assert list(folder.glob("*.json")) == []


@pytest.mark.parametrize("client_sessions_enabled", [True, False])
def test_cached_native_session_end_spools_and_drains(
    hook_env: Any, client_sessions_enabled: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_modes(hook_env, run_report="warn")
    env_vars = cached_invocation(hook_env, "claude_code").environ
    if not client_sessions_enabled:
        hook_env.client.dispatch(
            SetValue.from_json(
                {
                    "scope": {"level": "project", "scope_id": str(hook_env.project_id)},
                    "key": "learning.sources.client_sessions",
                    "value": False,
                }
            ),
            idempotency_key=hook_env.client.new_idempotency_key(),
        )

    pepper = b"learning-hook-test-pepper".ljust(32, b"0")
    entries = cast("dict[type[object], object]", hook_env.app.gateways.entries)
    monkeypatch.setitem(entries, TokenPepperSource, TokenPepper(pepper))
    token = hook_env.client.dispatch(
        CreateToken("learning-hook", scope_id=hook_env.project_id, permissions=("lesson.read",))
    )
    clock = hook_env.app.bus._clock
    meta = RequestMeta("req_" + "2" * 26, Surface.HOOK, None, clock.now())
    with cast("UnitOfWork", hook_env.app.uow_factory(meta, readonly=True)) as uow:
        actor = authenticate_token(uow, token.secret, pepper=pepper, now=clock.now())
    client = hook_env.app.client(actor=actor, surface=Surface.HOOK)
    assert client.ask(WhoAmI(scope_id=hook_env.project_id)).effective_permissions == ("lesson.read",)

    @contextmanager
    def live_context(
        environ: Mapping[str, str], bootstrap: str | None, *, session_drain: bool, **_options: Any
    ) -> Iterator[HostContext]:
        assert environ == env_vars
        assert bootstrap is None
        assert session_drain
        yield replace(cast("HostContext", hook_env.ctx), client=client)

    # Route the live availability check and the drain to the same authenticated test backend.
    monkeypatch.setattr(hook, "hook_context", live_context)

    transcript = Path(env_vars["HOME"]) / ".claude" / "projects" / "checkout" / "session-1.jsonl"
    transcript.parent.mkdir(parents=True)
    queued = hook_env.state_dir / "hooks" / "learning"
    out, err = StringIO(), StringIO()
    flushed: list[bool] = []
    monkeypatch.setattr(out, "flush", lambda: flushed.append(True))
    wakeups: list[bool] = []

    def start_drain(environ: Mapping[str, str], bootstrap: str | None) -> None:
        assert environ == env_vars
        assert bootstrap is None
        assert flushed == [True]
        assert len(list(queued.glob("*.json"))) == 1
        assert not transcript.exists()
        wakeups.append(True)

    monkeypatch.setattr(hook, "_start_session_drain", start_drain)
    args = argparse.Namespace(
        target="claude_code",
        surface="lifecycle.run_report",
        event_name="SessionEnd",
        project=str(hook_env.project_id),
    )
    payload = {
        "cwd": str(hook_env.checkout_dir),
        "session_id": "session-1",
        "reason": "logout",
        "transcript_path": str(transcript),
    }
    assert hook.invoke(args, StringIO(dumps(payload)), out, err, env_vars) == 0
    assert out.getvalue() == err.getvalue() == ""
    assert wakeups == [True]

    transcript.write_text(_message("assistant", []))
    hook._drain_sessions(env_vars, None)
    transcript.unlink()
    assert list(queued.glob("*.json")) == []
    with cast("UnitOfWork", hook_env.app.uow_factory(meta, readonly=True)) as uow:
        records = cast("ActivityStorage", uow.repo(ActivityRecordRepository))
        assert records.count_for_project(hook_env.project_id) == int(client_sessions_enabled)
        if client_sessions_enabled:
            (activity,) = records.recent_for_project(hook_env.project_id, window=1)
            (source_metadata,) = [
                ref["source_metadata"]
                for bundle in activity.detector_evidence
                for ref in bundle.source_refs
                if "source_metadata" in ref
            ]
            assert isinstance(source_metadata, dict)
            assert source_metadata["adapter_id"] == "claude_code"
            assert source_metadata["adapter_version"] == source_metadata["parser_version"] == "1"
            assert source_metadata["source_format"] == "claude_code_jsonl"
            coverage = source_metadata["metric_coverage"]
            assert isinstance(coverage, dict)
            assert (
                coverage["tools_total"] == coverage["files_changed"] == coverage["usage_input"] == "partial"
            )
            assert coverage["checks"] == coverage["outcome"] == "unknown"
            assert activity.outcome is Outcome.UNKNOWN
            assert activity.evidence_dependency == "unknown"
