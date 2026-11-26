"""Independent threshold/detail controls and both sink formats."""

import errno
import json
from collections.abc import Generator
from dataclasses import replace
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from typing import Any, override

import pytest

from skm.platform.logging import setup
from skm.platform.logging.logger import get_logger
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.logging.setup import configure_logging, detail_enabled, reconfigure_logging

DIGEST = "sha256:" + "a" * 64


@pytest.fixture(scope="module", autouse=True)
def original_logging_settings() -> Generator[setup._Settings]:
    # Seed an open INFO sink for the cross-test regression, restoring the session snapshot afterward.
    settings = replace(
        setup._state.settings,
        level="info",
        detail="normal",
        fmt="json",
        stream=StringIO(),
        redactor=Redactor(),
    )
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(setup._state, "settings", settings)
        yield settings


@pytest.fixture(autouse=True)
def isolated_logging_settings(original_logging_settings: setup._Settings) -> Generator[None]:
    assert setup._state.settings is original_logging_settings
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(setup._state, "settings", original_logging_settings)
        yield
    assert setup._state.settings is original_logging_settings


def test_live_reconfiguration_keeps_sink_format_host_and_secret_registry() -> None:
    stream = StringIO()
    redactor = Redactor()
    redactor.register_secret("test-host")
    configure_logging(
        level="error", detail="normal", fmt="json", stream=stream, redactor=redactor, host="test-host"
    )
    logger = get_logger("application.bus")
    logger.info("bus.command.completed", command="workspace.create_project")
    assert stream.getvalue() == ""
    assert not detail_enabled()
    reconfigure_logging(level="debug", detail="debug")
    assert detail_enabled()
    logger.debug("bus.command.completed", command="workspace.create_project", result_digest=DIGEST)
    record = json.loads(stream.getvalue())
    assert record["result_digest"] == DIGEST
    assert record["host"] == MASK


PRIMARY = "P" * 40


@pytest.mark.parametrize("fmt", ["json", "text"])
@pytest.mark.parametrize(
    ("secondary", "host"),
    [
        (MASK[3:] + "SECONDARY_0123456789", PRIMARY + "SECONDARY_0123456789"),
        ("SECONDARY_0123456789" + MASK[:4], "SECONDARY_0123456789" + PRIMARY),
        ("LEFT_FIXTURE" + MASK + "RIGHT_FIXTURE", "LEFT_FIXTURE" + PRIMARY + "RIGHT_FIXTURE"),
    ],
    ids=["mask-and-suffix", "prefix-and-mask", "both-sides"],
)
def test_sink_never_emits_a_registered_value_assembled_by_a_mask(secondary: str, host: str, fmt: Any) -> None:
    stream = StringIO()
    redactor = Redactor()
    for secret in (PRIMARY, secondary):
        redactor.register_secret(secret)
    configure_logging(level="info", detail="normal", fmt=fmt, stream=stream, redactor=redactor, host=host)
    get_logger("application.bus").info("bus.command.started", command="workspace.create_project")
    line = stream.getvalue()
    assert secondary not in line
    assert PRIMARY not in line
    assert "workspace.create_project" in line
    if fmt == "json":
        assert json.loads(line)["host"] == MASK
    else:
        assert MASK in line


@pytest.mark.parametrize("detail", ["normal", "debug"])
def test_detail_does_not_change_the_level_threshold(detail: Any) -> None:
    stream = StringIO()
    configure_logging(
        level="info", detail=detail, fmt="json", stream=stream, redactor=Redactor(), host="test-host"
    )
    logger = get_logger("application.bus")
    logger.debug("bus.command.started", command="workspace.create_project")
    logger.info("bus.command.completed", command="workspace.create_project", result_digest=DIGEST)
    (record,) = map(json.loads, stream.getvalue().splitlines())
    assert ("result_digest" in record) == (detail == "debug")
    assert record["command"] == "workspace.create_project"


@pytest.mark.parametrize(
    ("event", "fields"),
    [
        ("config.resolved", {"generation": 1, "digest": DIGEST, "keys_count": 4}),
        ("adapters.postgres.sql", {"statement": "get", "rows": 2, "duration_ms": 3}),
        (
            "platform.process.run",
            {
                "operation": "runtimes.host.detect_runtimes",
                "exit_code": 0,
                "timed_out": False,
                "duration_ms": 7,
            },
        ),
    ],
)
def test_detail_events_are_suppressed_in_normal_even_at_debug_level(
    event: str, fields: dict[str, object]
) -> None:
    stream = StringIO()
    configure_logging(
        level="debug", detail="normal", fmt="json", stream=stream, redactor=Redactor(), host="test-host"
    )
    logger = get_logger("platform.worker")
    logger.info(event, **fields)
    assert stream.getvalue() == ""
    reconfigure_logging(level="debug", detail="debug")
    logger.info(event, **fields)
    assert json.loads(stream.getvalue()).items() >= fields.items()


def test_started_detail_fields_are_filtered_without_hiding_command() -> None:
    stream = StringIO()
    configure_logging(
        level="debug", detail="normal", fmt="json", stream=stream, redactor=Redactor(), host="test-host"
    )
    logger = get_logger("application.bus")
    fields = {
        "command": "workspace.create_project",
        "operation": "workspace.create_project",
        "schema_urn": "urn:skm:workspace:command:create-project:v1",
    }
    logger.info("bus.command.started", **fields)
    reconfigure_logging(level="debug", detail="debug")
    logger.info("bus.command.started", **fields)
    normal, debug = map(json.loads, stream.getvalue().splitlines())
    assert normal["command"] == debug["command"] == "workspace.create_project"
    assert "operation" not in normal
    assert "schema_urn" not in normal
    assert debug.items() >= fields.items()


@pytest.mark.parametrize(
    ("field", "value"), [("level", "trace"), ("detail", "full"), ("fmt", "xml"), ("host", "bad\nhost")]
)
def test_invalid_configuration_is_atomic(field: str, value: str) -> None:
    stream = StringIO()
    kwargs: dict[str, Any] = {
        "level": "info",
        "detail": "normal",
        "fmt": "json",
        "stream": stream,
        "redactor": Redactor(),
        "host": "test-host",
    }
    configure_logging(**kwargs)
    kwargs[field] = value
    with pytest.raises(ValueError, match="invalid logging"):
        configure_logging(**kwargs)
    get_logger("platform.worker").info("stage.completed", passed=1)
    assert json.loads(stream.getvalue())["host"] == "test-host"
    if field in {"level", "detail"}:
        live_kwargs: dict[str, Any] = {"level": "info", "detail": "normal", field: value}
        with pytest.raises(ValueError, match="invalid logging"):
            reconfigure_logging(**live_kwargs)
        assert not detail_enabled()


def test_text_has_utc_hhmmss_prefix_and_safe_json_literal_values(monkeypatch: pytest.MonkeyPatch) -> None:
    class Clock:
        def now(self) -> datetime:
            return datetime(2026, 10, 27, 12, 34, 56, 123456, UTC)

    monkeypatch.setattr(setup, "_CLOCK", Clock())
    stream = StringIO()
    configure_logging(
        level="info", detail="normal", fmt="text", stream=stream, redactor=Redactor(), host="test-host"
    )
    get_logger("application.bus").info(
        "bus.command.started",
        command="workspace.create_project",
        message="Command started",
        payload="private\nnext line",
    )
    (line,) = stream.getvalue().splitlines()
    assert line.startswith("12:34:56 info application.bus bus.command.started ")
    assert 'message="Command started"' in line
    assert "payload" not in line


def test_file_sink_uses_the_same_writer_and_remains_owned_by_caller(tmp_path: Path) -> None:
    path = tmp_path / "worker.jsonl"
    with path.open("a", encoding="utf-8") as stream:
        configure_logging(
            level="info", detail="normal", fmt="json", stream=stream, redactor=Redactor(), host="test-host"
        )
        get_logger("platform.worker").info("stage.completed", passed=1)
        assert not stream.closed
        assert json.loads(path.read_text())["passed"] == 1


def test_logging_after_file_sink_uses_the_original_open_sink(
    original_logging_settings: setup._Settings,
) -> None:
    stream = original_logging_settings.stream
    assert isinstance(stream, StringIO)
    assert not stream.closed
    get_logger("logging.regression").info("stage.completed", passed=2)
    assert setup._state.settings is original_logging_settings
    assert json.loads(stream.getvalue().splitlines()[-1])["passed"] == 2


class _FailingSink(StringIO):
    def __init__(self, error: Exception) -> None:
        super().__init__()
        self.error = error

    @override
    def write(self, s: str, /) -> int:
        raise self.error


@pytest.mark.parametrize(
    "error",
    [
        OSError(errno.ENOSPC, "No space left on device"),
        BrokenPipeError(errno.EPIPE, "Broken pipe"),
        OSError(errno.EIO, "Input/output error"),
        ValueError("I/O operation on closed file."),
    ],
)
def test_a_sink_that_cannot_take_the_line_never_fails_the_caller(error: Exception) -> None:
    configure_logging(
        level="info", detail="normal", fmt="json", stream=_FailingSink(error), redactor=Redactor(), host="h"
    )
    logger = get_logger("application.bus")
    logger.info("bus.command.completed", command="workspace.create_project")
    logger.error("background.tick.failed", exc=RuntimeError("boom"), service="outbox")


def test_a_closed_file_sink_drops_lines_and_a_new_sink_receives_the_next(tmp_path: Path) -> None:
    path = tmp_path / "worker.jsonl"
    with path.open("a", encoding="utf-8") as stream:
        configure_logging(
            level="info", detail="normal", fmt="json", stream=stream, redactor=Redactor(), host="h"
        )
    get_logger("platform.worker").info("stage.completed", passed=1)
    replacement = StringIO()
    configure_logging(
        level="info", detail="normal", fmt="json", stream=replacement, redactor=Redactor(), host="h"
    )
    get_logger("platform.worker").info("stage.completed", passed=2)
    assert path.read_text() == ""
    assert json.loads(replacement.getvalue())["passed"] == 2
