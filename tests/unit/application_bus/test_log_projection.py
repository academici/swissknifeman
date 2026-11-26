"""The bus emits typed safe metadata only (kernel-platform §3.4), in normal and debug detail.

The canaries below match no token pattern of the ``Redactor``, so only the code-owned projection can keep them
out of the log: truncation or pattern redaction would not.
"""

import io
import json
import sys
from collections.abc import Iterator
from dataclasses import replace
from typing import Any

import pytest

from fakes.app import Harness, build_harness, request_id
from fakes.demo_module import ECHO, ECHO_SECRET, GET_ECHO, Echo, EchoSecret, GetEcho, handle_echo, manifest
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, SkmError, ValidationFailed
from skm.platform.logging.redaction import Redactor
from skm.platform.logging.setup import configure_logging

CANARY = "zebra-lantern-quartz-4417"
SECRET = "hunter2-marmalade-9031"
ARGV_CANARY = "--private-flag=walrus-pinecone-2290"


@pytest.fixture(params=["normal", "debug"])
def stream(request: pytest.FixtureRequest) -> Iterator[io.StringIO]:
    sink = io.StringIO()
    configure_logging(
        level="debug", detail=request.param, fmt="json", stream=sink, redactor=Redactor(), host="test-host"
    )
    yield sink
    configure_logging(
        level="info", detail="normal", fmt="json", stream=sys.stderr, redactor=Redactor(), host="localhost"
    )


def records(sink: io.StringIO) -> list[dict[str, Any]]:
    lines = [line for line in sink.getvalue().splitlines() if line]
    return [json.loads(line) for line in lines]  # every line is one JSON object


def echo(h: Harness, text: str) -> Echo:
    return Echo(workspace_id=h.seed.workspace_id, text=text)


def assert_clean(sink: io.StringIO) -> None:
    text = sink.getvalue()
    for private in (CANARY, SECRET, ARGV_CANARY):
        assert private not in text


def failed(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in entries if e["event"] == "bus.command.failed"]


def test_successful_command_logs_ids_and_correlation_but_no_content(stream: io.StringIO) -> None:
    h = build_harness()
    h.bus.dispatch(echo(h, CANARY), actor=h.actor, meta=h.meta())
    entries = records(stream)
    assert_clean(stream)
    started = next(e for e in entries if e["event"] == "bus.command.started")
    completed = next(e for e in entries if e["event"] == "bus.command.completed")
    for entry in (started, completed):
        assert entry["request_id"] == request_id()
        assert entry["correlation_id"] == request_id()  # bound before processing
        assert entry["surface"] == "test"
        assert entry["actor_id"] == str(h.seed.principal_id)
    # ``demo.echo`` is not a registered log operation, so only the common envelope survives the projection.
    envelope = {
        "ts",
        "level",
        "component",
        "event",
        "message",
        "request_id",
        "correlation_id",
        "causation_id",
    }
    envelope |= {"parent_causation_id", "surface", "actor_id", "pid", "host", "reason_code"}
    assert {key for e in entries for key in e} <= envelope


def test_causal_ids_of_the_request_are_logged_as_given(stream: io.StringIO) -> None:
    h = build_harness()
    h.bus.dispatch(
        echo(h, CANARY), actor=h.actor, meta=h.meta(correlation_id=request_id(5), causation_id=request_id(6))
    )
    started = next(e for e in records(stream) if e["event"] == "bus.command.started")
    assert (started["correlation_id"], started["causation_id"]) == (request_id(5), request_id(6))
    assert_clean(stream)


def test_invalid_dto_failure_logs_a_code_not_the_document(stream: io.StringIO) -> None:
    h = build_harness()
    with pytest.raises(ValidationFailed):
        h.bus.dispatch(echo(h, ""), actor=h.actor, meta=h.meta())
    (entry,) = failed(records(stream))
    assert entry["reason_code"]
    assert entry["request_id"] == request_id()
    assert_clean(stream)


def test_secret_field_never_reaches_the_log_even_on_failure(stream: io.StringIO) -> None:
    h = build_harness(manifests=(manifest(commands=(ECHO_SECRET,)),))
    h.bus.dispatch(
        EchoSecret(workspace_id=h.seed.workspace_id, text=CANARY, secret=SECRET),
        actor=h.actor,
        meta=h.meta("k1"),
    )
    with pytest.raises(Conflict):
        h.bus.dispatch(
            EchoSecret(workspace_id=h.seed.workspace_id, text=CANARY, secret=SECRET + "x"),
            actor=h.actor,
            meta=h.meta("k1", request=request_id(2)),
        )
    assert failed(records(stream))
    assert_clean(stream)


def test_unexpected_handler_exception_logs_type_only(stream: io.StringIO) -> None:
    def broken(cmd: Echo, ctx: Any, uow: Any) -> Any:
        raise RuntimeError(f"cannot process {cmd.text} with {ARGV_CANARY} in /home/{SECRET}")

    h = build_harness(manifests=(manifest(commands=(replace(ECHO, handler=broken),)),))
    with pytest.raises(SkmError):
        h.bus.dispatch(echo(h, CANARY), actor=h.actor, meta=h.meta())
    (entry,) = failed(records(stream))
    assert entry["level"] == "error"
    assert entry["reason_code"] == "INTERNAL_ERROR"
    assert_clean(stream)


def test_domain_error_with_private_message_logs_only_its_code(stream: io.StringIO) -> None:
    def refuse(cmd: Echo, ctx: Any, uow: Any) -> Any:
        raise Conflict(
            ErrorCode.ALREADY_EXISTS, f"{cmd.text} exists", details={"cwd": ARGV_CANARY, "text": cmd.text}
        )

    h = build_harness(manifests=(manifest(commands=(replace(ECHO, handler=refuse),)),))
    with pytest.raises(Conflict):
        h.bus.dispatch(echo(h, CANARY), actor=h.actor, meta=h.meta())
    assert failed(records(stream))
    assert_clean(stream)


def test_denied_command_logs_a_code_and_no_content(stream: io.StringIO) -> None:
    h = build_harness()
    h.authorizer.deny_all()
    with pytest.raises(Forbidden):
        h.bus.dispatch(echo(h, CANARY), actor=h.actor, meta=h.meta())
    (entry,) = failed(records(stream))
    assert entry["reason_code"]
    assert_clean(stream)


def test_handler_logger_drops_unregistered_content_fields(stream: io.StringIO) -> None:
    def chatty(cmd: Echo, ctx: Any, uow: Any) -> Any:
        ctx.log.info(
            "modules.demo.echoed", argv=[ARGV_CANARY], cwd=ARGV_CANARY, payload={"x": CANARY}, text=cmd.text
        )
        ctx.log.warning(
            "modules.demo.echoed", message=f"echoing {cmd.text}", prompt=CANARY, config={"k": SECRET}
        )
        return handle_echo(cmd, ctx, uow)

    h = build_harness(manifests=(manifest(commands=(replace(ECHO, handler=chatty),)),))
    h.bus.dispatch(echo(h, CANARY), actor=h.actor, meta=h.meta())
    chatter = [e for e in records(stream) if e["event"] == "modules.demo.echoed"]
    assert chatter
    assert all(e["request_id"] == request_id() for e in chatter)
    assert_clean(stream)


def test_unexpected_query_exception_is_logged_with_its_type_only(stream: io.StringIO) -> None:
    def broken(query: GetEcho, ctx: Any, uow: Any) -> Any:
        raise RuntimeError(f"cannot read {ARGV_CANARY} in /home/{SECRET}")

    h = build_harness(manifests=(manifest(queries=(replace(GET_ECHO, handler=broken),)),))
    with pytest.raises(SkmError) as exc:
        h.bus.ask(GetEcho(workspace_id=h.seed.workspace_id), actor=h.actor, meta=h.meta())
    assert exc.value.code is ErrorCode.INTERNAL_ERROR
    (entry,) = [e for e in records(stream) if e["event"] == "bus.query.failed"]
    assert (entry["level"], entry["reason_code"], entry["error.type"]) == (
        "error",
        "INTERNAL_ERROR",
        "RuntimeError",
    )
    assert entry["request_id"] == exc.value.details["request_id"]
    assert_clean(stream)


def test_query_failures_log_no_query_content(stream: io.StringIO) -> None:
    h = build_harness()
    h.authorizer.deny_all()
    with pytest.raises(Forbidden):
        h.client.ask(GetEcho(workspace_id=h.seed.workspace_id))
    assert_clean(stream)
