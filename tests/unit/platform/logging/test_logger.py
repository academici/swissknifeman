"""Public logger entry points, safe error metadata and concurrent correlation."""

import json
import logging
import re
from collections.abc import Generator
from concurrent.futures import ThreadPoolExecutor
from contextvars import copy_context
from io import StringIO
from threading import Barrier
from typing import override

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.platform.logging import setup
from skm.platform.logging.envelope import LOG_FIELDS, bind, context_fields
from skm.platform.logging.logger import StructLogger, get_logger
from skm.platform.logging.redaction import Redactor
from skm.platform.logging.setup import configure_logging

ID = "019a0254-fc00-7000-8000-000000000001"
PARENT = "019a0254-fc00-7000-8000-000000000002"
REQUEST = "req_" + "A" * 26


@pytest.fixture(autouse=True)
def isolated_logging_settings() -> Generator[None]:
    original = setup._state.settings
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(setup._state, "settings", original)
        yield
    assert setup._state.settings is original


def configured() -> tuple[StructLogger, StringIO]:
    stream = StringIO()
    configure_logging(
        level="debug", detail="debug", fmt="json", stream=stream, redactor=Redactor(), host="test-host"
    )
    return get_logger("execution.worker"), stream


def test_jsonl_envelope_has_observed_utc_and_protected_identity() -> None:
    logger, stream = configured()
    logger.info(
        "stage.completed",
        duration_ms=12,
        passed=3,
        ts="private",
        level="error",
        component="private",
        event="private",
        pid=0,
        host="private",
    )
    (line,) = stream.getvalue().splitlines()
    record = json.loads(line)
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z", record["ts"])
    assert record["level"] == "info"
    assert record["event"] == "stage.completed"
    assert record["component"] == "execution.worker"
    assert record["host"] == "test-host"
    assert record["pid"] > 0
    assert record["duration_ms"] == 12
    assert list(record) == [name for name in LOG_FIELDS if name in record] + ["duration_ms", "passed"]
    assert "type" not in record
    assert "fields" not in record


@pytest.mark.parametrize("method", ["debug", "info", "warning", "error"])
def test_all_public_levels(method: str) -> None:
    logger, stream = configured()
    getattr(logger, method)("stage.completed", passed=2)
    assert json.loads(stream.getvalue())["level"] == method


def test_exception_retains_cause_but_no_text_trace_or_notes_are_emitted() -> None:
    logger, stream = configured()
    cause = ValueError("private cause")
    with pytest.raises(ValidationFailed) as raised:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "private message", details={"private": "document"}
        ) from cause
    exc = raised.value
    exc.add_note("private note")
    traceback = exc.__traceback__
    logger.error("bus.command.failed", command="workspace.create_project", exc=exc)
    assert exc.__cause__ is cause
    assert exc.__traceback__ is traceback
    assert exc.message == "private message"
    assert exc.__notes__ == ["private note"]
    record = json.loads(stream.getvalue())
    assert record["code"] == record["reason_code"] == "SCHEMA_INVALID"
    assert record["error.type"] == "SkmError"
    assert "private" not in stream.getvalue()
    assert "Traceback" not in stream.getvalue()


def test_arbitrary_exception_class_names_and_stringifiers_never_reach_sink() -> None:
    class PrivateDocumentClass(Exception):
        @override
        def __str__(self) -> str:
            raise AssertionError("raw exception text was requested")

    logger, stream = configured()
    logger.error("worker.stage.failed", exc=PrivateDocumentClass("private"))
    assert json.loads(stream.getvalue())["error.type"] == "Exception"
    assert "PrivateDocumentClass" not in stream.getvalue()


def test_explicit_thread_context_copy_preserves_the_entire_causal_chain() -> None:
    logger, stream = configured()
    with bind(
        request_id=REQUEST,
        correlation_id=REQUEST,
        causation_id=ID,
        parent_causation_id=PARENT,
        run_id=ID,
        step_id=ID,
        parent_step_id=PARENT,
    ):
        context = copy_context()
        with ThreadPoolExecutor(max_workers=1) as executor:
            executor.submit(context.run, logger.info, "stage.completed", passed=1).result()
            executor.submit(logger.info, "stage.completed", passed=2).result()
    copied, empty = map(json.loads, stream.getvalue().splitlines())
    for name in ("request_id", "correlation_id", "causation_id", "parent_causation_id", "parent_step_id"):
        assert (
            copied[name]
            == {
                "request_id": REQUEST,
                "correlation_id": REQUEST,
                "causation_id": ID,
                "parent_causation_id": PARENT,
                "parent_step_id": PARENT,
            }[name]
        )
        assert name not in empty
    assert context_fields() == {}


def test_simultaneous_threads_do_not_mix_jsonl_or_context() -> None:
    logger, stream = configured()
    barrier = Barrier(4)

    def worker(number: int) -> None:
        run = f"019a0254-fc00-7000-8000-{number:012d}"
        with bind(run_id=run, request_id=REQUEST, correlation_id=ID, causation_id=PARENT):
            barrier.wait(timeout=5)
            for _ in range(4):
                logger.info("stage.completed", passed=number)

    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(worker, range(4)))
    records = [json.loads(line) for line in stream.getvalue().splitlines()]
    assert len(records) == 16
    assert all(record["run_id"].endswith(f"{record['passed']:012d}") for record in records)
    assert all(record["correlation_id"] == ID and record["causation_id"] == PARENT for record in records)


def test_configuration_does_not_install_audit_domain_or_stdlib_handlers() -> None:
    handlers = list(logging.getLogger().handlers)
    logger, stream = configured()
    logger.info("unknown.event", payload={"domain": "event"}, audit={"record": "private"})
    assert list(logging.getLogger().handlers) == handlers
    assert "payload" not in stream.getvalue()
    assert "audit" not in stream.getvalue()


@pytest.mark.parametrize("value", ["free text", "single", "upper.Case", "bad\nname", "x." + "a" * 128])
def test_invalid_component_and_event_cannot_inject_log_lines(value: str) -> None:
    with pytest.raises(ValueError, match="component"):
        get_logger(value)
    logger, stream = configured()
    with pytest.raises(ValueError, match="event"):
        logger.info(value)
    assert stream.getvalue() == ""
