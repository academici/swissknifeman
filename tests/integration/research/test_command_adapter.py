"""Command protocols, bounded pipes and mandatory process-group cleanup."""

from time import monotonic

import pytest

from skm.adapters.research.command import CommandResearchSource, ProcessSession
from skm.adapters.research.retry import SourceBusy, SourceFailed, with_retry
from skm.kernel.cancel import Cancelled, CancelSource
from skm.platform.process.identity import group_alive

from ._support import command, json_script, query


@pytest.mark.parametrize(
    ("protocol", "reply"),
    [
        ("text-v0", {"text": "evidence", "sources": ["repo:repo/docs.md"]}),
        (
            "json-v1",
            {
                "documents": [{"origin": "repo:repo/docs.md", "title": "Docs", "text": "evidence"}],
                "claims": [{"text": "claim", "origins": ["repo:repo/docs.md"]}],
                "usage": {"requests": 1},
            },
        ),
    ],
)
def test_command_protocols(protocol, reply):
    cfg = command(json_script(reply), protocol=protocol)
    result = CommandResearchSource().search(cfg, query(), cancel=CancelSource().token)
    assert result.documents[0].origin == "mcp:docs/repo:repo/docs.md"
    assert result.raw_digest.startswith("sha256:")
    if protocol == "json-v1":
        assert result.claims[0][1] == ("mcp:docs/repo:repo/docs.md",)
        assert result.usage == {"requests": 1}
    else:
        assert result.answer_text == "evidence"
        assert result.documents[0].text is None


@pytest.mark.parametrize(
    "script",
    [
        "print('not json')",
        "print('[]')",
        "print('{\"documents\": [0]}')",
        "import sys; print('secret-value', file=sys.stderr); sys.exit(3)",
    ],
)
def test_malformed_or_failed_command_never_discloses_output(script):
    with pytest.raises(SourceFailed) as error:
        CommandResearchSource().search(command(script), query(), cancel=CancelSource().token)
    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize("stream", ["stdout", "stderr"])
def test_capture_is_bounded_even_for_valid_prefix_and_no_newlines(stream):
    script = f"import sys; sys.{stream}.write('x'*2100000); sys.{stream}.flush()"
    started = monotonic()
    with pytest.raises(SourceFailed):
        CommandResearchSource().search(command(script), query(), cancel=CancelSource().token)
    assert monotonic() - started < 10


def test_timeout_terminates_ignoring_group_including_child_after_leader_exit():
    script = (
        "import os,signal; signal.signal(signal.SIGTERM,signal.SIG_IGN); "
        "child=os.fork(); os._exit(0) if child else signal.pause()"
    )
    cfg = command(script)
    session = ProcessSession(cfg.argv, {}, CancelSource().token, 0.2)
    pgid = session.process.pid
    try:
        with pytest.raises(SourceBusy):
            session.exchange(b"")
    finally:
        session.close()
    assert not group_alive(pgid)


def test_cancel_interrupts_process_and_preserves_cancellation():
    source = CancelSource()
    cfg = command("import signal; signal.pause()")
    session = ProcessSession(cfg.argv, {}, source.token, 10)
    source.cancel("lease_lost")
    try:
        with pytest.raises(Cancelled, match="lease_lost"):
            session.exchange(b"query")
    finally:
        session.close()
    assert not group_alive(session.process.pid)


def test_retry_only_transient_failure_bounded_and_cancellable():
    class Token:
        cancelled = False
        reason: str | None = None

        def __init__(self):
            self.waits = []

        def raise_if_cancelled(self):
            return None

        def wait(self, timeout_seconds: float) -> bool:
            self.waits.append(timeout_seconds)
            return False

    calls = []
    token = Token()

    def busy():
        calls.append(1)
        raise SourceBusy("busy")

    with pytest.raises(SourceBusy):
        with_retry(busy, cancel=token)
    assert len(calls) == 3
    assert token.waits == [5, 10]
    with pytest.raises(ValueError, match="between one and three"):
        with_retry(busy, cancel=token, attempts=4)
    with pytest.raises(SourceFailed):
        with_retry(lambda: (_ for _ in ()).throw(SourceFailed()), cancel=token)
    cancelled = CancelSource()
    cancelled.cancel("shutdown")
    with pytest.raises(Cancelled):
        with_retry(busy, cancel=cancelled.token)
