"""run logs refuse a foreign step, hide a restricted transcript, and decode UTF-8 across chunks."""

from __future__ import annotations

import argparse
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest

from skm.entrypoints.cli._run_logs import logs
from skm.entrypoints.cli.context import CliContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed


def _args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "ref": str(uuid4()),
        "step": None,
        "transcript": False,
        "follow": False,
    }
    values.update(overrides)
    return cast(argparse.Namespace, SimpleNamespace(**values))


def _ctx(open_file: object | None = None) -> CliContext:
    return cast(CliContext, SimpleNamespace(client=SimpleNamespace(open_file_version_content=open_file)))


def test_logs_rejects_a_step_that_is_not_on_the_attempt(monkeypatch: pytest.MonkeyPatch) -> None:
    attempt_id = uuid4()
    attempt = SimpleNamespace(
        attempt_id=str(attempt_id),
        steps=[{"step_id": str(uuid4())}],
        state="completed",
    )
    monkeypatch.setattr("skm.entrypoints.cli._run_logs.ask", lambda ctx, operation, **payload: attempt)
    monkeypatch.setattr("skm.entrypoints.cli._run_logs.show", lambda *args, **kwargs: None)
    with pytest.raises(ValidationFailed, match="step does not belong to this attempt") as caught:
        logs(_args(ref=str(attempt_id), step=str(uuid4())), _ctx())
    assert caught.value.code is ErrorCode.INVALID_REFERENCE


def test_logs_refuses_a_restricted_transcript_without_opening_the_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    step_id = uuid4()
    opened: list[object] = []
    attempt = SimpleNamespace(
        attempt_id=str(uuid4()),
        steps=[{"step_id": str(step_id)}],
        state="completed",
    )
    step = SimpleNamespace(
        step_id=str(step_id),
        payload_visibility="restricted",
        transcript_file_version_id=uuid4(),
    )

    def ask(_ctx: object, operation: object, **payload: object) -> object:
        name = getattr(operation, "__name__", type(operation).__name__)
        return attempt if "GetAttempt" in str(name) or name == "GetAttempt" else step

    def open_file(vid: object) -> None:
        opened.append(vid)

    monkeypatch.setattr("skm.entrypoints.cli._run_logs.ask", ask)
    monkeypatch.setattr("skm.entrypoints.cli._run_logs.show", lambda *args, **kwargs: None)
    with pytest.raises(Forbidden, match=r"file\.read is required for this transcript") as caught:
        logs(_args(step=str(step_id), transcript=True), _ctx(open_file=open_file))
    assert caught.value.code is ErrorCode.FORBIDDEN
    assert opened == []


def test_logs_decodes_one_utf8_character_split_across_chunks_and_skips_a_seen_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first_id, second_id = uuid4(), uuid4()
    version = uuid4()
    attempt = SimpleNamespace(
        attempt_id=str(uuid4()),
        steps=[{"step_id": str(first_id)}, {"step_id": str(second_id)}],
        state="completed",
    )
    steps = {
        str(first_id): SimpleNamespace(
            step_id=str(first_id),
            payload_visibility="public",
            transcript_file_version_id=version,
        ),
        str(second_id): SimpleNamespace(
            step_id=str(second_id),
            payload_visibility="public",
            transcript_file_version_id=version,
        ),
    }
    accent = "é".encode()
    chunks = [b"x" * 65535 + accent[:1], accent[1:] + b"y"]
    reads = 0

    class SplitStream:
        def __enter__(self) -> SplitStream:
            return self

        def __exit__(self, *exc: object) -> None:
            return None

        def read(self, size: int) -> bytes:
            nonlocal reads
            reads += 1
            if not chunks:
                return b""
            assert size == 65536
            return chunks.pop(0)

    def ask(_ctx: object, operation: object, **payload: object) -> object:
        if payload.get("attempt_id") or "step_id" not in payload:
            return attempt
        return steps[str(payload["step_id"])]

    rendered: list[str] = []

    def render(_ctx: object, payload: dict[str, Any], **kwargs: object) -> None:
        rendered.append(str(payload.get("text", "")))

    monkeypatch.setattr("skm.entrypoints.cli._run_logs.ask", ask)
    monkeypatch.setattr("skm.entrypoints.cli._run_logs.show", lambda *args, **kwargs: None)
    monkeypatch.setattr("skm.entrypoints.cli._run_logs.render", render)
    assert logs(_args(transcript=True), _ctx(open_file=lambda vid: SplitStream())) == 0
    assert "".join(rendered) == ("x" * 65535) + "éy"
    assert reads == 3  # two payload chunks, then the empty read that ends the loop
    # The second step shares the version and must not open the file again.
    assert chunks == []  # first open consumed both chunks; a second open would have nothing to pop


def test_logs_follow_returns_the_waiting_hint(monkeypatch: pytest.MonkeyPatch) -> None:
    attempt = SimpleNamespace(attempt_id=str(uuid4()), steps=[], state="waiting")
    monkeypatch.setattr("skm.entrypoints.cli._run_logs.ask", lambda *args, **kwargs: attempt)
    monkeypatch.setattr("skm.entrypoints.cli._run_logs.show", lambda *args, **kwargs: None)
    monkeypatch.setattr("skm.entrypoints.cli._run_logs.render_waiting", lambda *args, **kwargs: 7)
    assert logs(_args(follow=True), _ctx()) == 7
