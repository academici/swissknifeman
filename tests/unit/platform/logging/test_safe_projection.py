"""Private prose is excluded before redaction, including every public logging entry point.

The canary has no secret/token pattern. Pattern masking or truncation cannot make these tests pass.
Schema source masks and revealed-secret masking are exercised separately on otherwise valid metadata.
"""

import json
from collections.abc import Generator
from contextlib import nullcontext
from dataclasses import dataclass, field
from io import StringIO
from typing import Any, override
from uuid import UUID

import pytest

from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.logging import setup
from skm.platform.logging.envelope import bind, safe_fields, source_fields
from skm.platform.logging.logger import get_logger
from skm.platform.logging.redaction import MASK, Redactor
from skm.platform.logging.setup import configure_logging

PRIVATE = "confidential document orchard marmalade 649fcd no credential pattern"
SENTINEL = "sentinel-value-734921"
ID = "019a0254-fc00-7000-8000-000000000001"
DIGEST = "sha256:" + "a" * 64


@pytest.fixture(autouse=True)
def isolated_logging_settings() -> Generator[None]:
    original = setup._state.settings
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(setup._state, "settings", original)
        yield
    assert setup._state.settings is original


@dataclass(frozen=True)
class Document:
    title: str = PRIVATE
    body: dict[str, object] = field(default_factory=lambda: {"nested": [PRIVATE]})
    secret: str = field(default=SENTINEL, metadata={"x-skm-secret": True})

    def to_json(self) -> object:
        pytest.fail("DTO serialization must never be used by logging")


class SecretValue:
    def reveal(self) -> str:
        pytest.fail("SecretValue must be excluded without revealing")

    @override
    def __str__(self) -> str:
        raise AssertionError("SecretValue must be excluded without conversion")

    @override
    def __repr__(self) -> str:
        pytest.fail("SecretValue must be excluded without repr")


class RecordingRedactor(Redactor):
    def __init__(self) -> None:
        super().__init__()
        self.documents: list[JsonObject] = []

    @override
    def document(self, value: JsonValue) -> JsonValue:
        assert isinstance(value, dict)
        self.documents.append(dict(value))
        return super().document(value)


def private_failure() -> RuntimeError:
    document = Document()
    with pytest.raises(RuntimeError) as raised:
        # Content in exception args, locals, cause and notes must stay in memory, in every mode.
        raise RuntimeError(PRIVATE, document) from ValueError(PRIVATE)
    raised.value.add_note(PRIVATE)
    return raised.value


@pytest.mark.parametrize("fmt", ["json", "text"])
@pytest.mark.parametrize("detail", ["normal", "debug"])
@pytest.mark.parametrize("method", ["debug", "info", "warning", "error"])
@pytest.mark.parametrize(
    ("event", "selectors"),
    [
        ("stage.completed", {}),
        ("bus.command.completed", {"command": "private.unknown_operation"}),
        ("unknown.operation", {}),
    ],
)
def test_no_private_content_in_any_mode_or_public_entry_point(
    fmt: Any,
    detail: Any,
    method: str,
    event: str,
    selectors: dict[str, object],
) -> None:
    stream = StringIO()
    redactor = RecordingRedactor()
    failure = private_failure()
    assert redactor.text(PRIVATE) == PRIVATE
    configure_logging(
        level="debug", detail=detail, fmt=fmt, stream=stream, redactor=redactor, host="test-host"
    )
    fields: dict[str, object] = {
        "run_id": ID,
        "passed": 3,
        "duration_ms": 12,
        "digest": DIGEST,
        "code": "NOT_FOUND",
        "dto": Document(),
        "result": Document(),
        "payload": {"nested": [{"body": PRIVATE}]},
        "fields": {"digest": PRIVATE, "document": Document()},
        "prompt": PRIVATE,
        "payload_preview": PRIVATE,
        "argv": ["tool", PRIVATE],
        "cwd": "/private/worktree/" + PRIVATE,
        "error": failure,
        "exception": failure,
        "traceback": PRIVATE,
        "message": PRIVATE,
        "title": PRIVATE,
        "config_value": PRIVATE,
        "continuation": {"document": PRIVATE},
        "secret": SecretValue(),
        "secret_ref": {"scheme": "file", "path": "/private/" + PRIVATE},
        **selectors,
    }
    if method == "error":
        fields["exc"] = failure
    with bind(request_id="req_" + "A" * 26, correlation_id=ID, causation_id=ID, parent_causation_id=None):
        getattr(get_logger("execution.worker"), method)(event, **fields)
    assert len(stream.getvalue().splitlines()) == 1
    assert len(redactor.documents) == 1
    assert failure.__traceback__ is not None
    assert failure.__cause__ is not None
    assert failure.__notes__ == [PRIVATE]
    before = redactor.documents[0]
    for output in (stream.getvalue(), json.dumps(before)):
        for fragment in (PRIVATE, "orchard", "marmalade", SENTINEL, "payload_preview", "traceback"):
            assert fragment not in output
    assert before["run_id"] == ID
    assert before["correlation_id"] == before["causation_id"] == ID
    if event == "stage.completed":
        assert (
            before.items() >= {"passed": 3, "duration_ms": 12, "digest": DIGEST, "code": "NOT_FOUND"}.items()
        )
    else:
        assert not {"passed", "duration_ms", "digest", "code"} & before.keys()


@pytest.mark.parametrize("value", [Document(), {"nested": PRIVATE}, [PRIVATE], SecretValue()])
@pytest.mark.parametrize("slot", ["run_id", "request_id", "duration_ms", "passed", "digest", "stage", "code"])
def test_generic_values_cannot_launder_content_through_an_allowed_field(slot: str, value: object) -> None:
    assert slot not in safe_fields("stage.completed", {slot: value})


def test_custom_scalar_subclasses_are_not_safe_metadata() -> None:
    class SecretString(str):
        @override
        def __str__(self) -> str:
            raise AssertionError("custom scalar conversion")

    assert (
        safe_fields("stage.completed", {"run_id": SecretString(ID), "stage": SecretString("run_checks")})
        == {}
    )


@pytest.mark.parametrize("fmt", ["json", "text"])
@pytest.mark.parametrize("detail", ["normal", "debug"])
def test_source_masks_remove_even_valid_allowed_metadata_before_redactor(fmt: Any, detail: Any) -> None:
    schema: JsonObject = {
        "properties": {
            "run_id": {"type": "string", "x-skm-secret": True},
            "duration_ms": {"type": "number", "x-skm-secret": True},
            "passed": {"type": "integer", "x-skm-secret": False},
            "digest": {"type": "string"},
            "private_content": {"type": "string"},
        }
    }
    fields = source_fields(
        {"run_id": ID, "duration_ms": 123456789, "passed": 3, "digest": DIGEST, "private_content": PRIVATE},
        schema=schema,
    )
    redactor = RecordingRedactor()
    stream = StringIO()
    configure_logging(
        level="debug", detail=detail, fmt=fmt, stream=stream, redactor=redactor, host="test-host"
    )
    get_logger("execution.worker").info("stage.completed", **fields)
    assert "run_id" not in redactor.documents[0]
    assert "duration_ms" not in redactor.documents[0]
    assert redactor.documents[0]["passed"] == 3
    assert redactor.documents[0]["digest"] == DIGEST
    assert ID not in stream.getvalue()
    assert "123456789" not in stream.getvalue()
    assert PRIVATE not in stream.getvalue()


@pytest.mark.parametrize("fmt", ["json", "text"])
@pytest.mark.parametrize("detail", ["normal", "debug"])
@pytest.mark.parametrize("secret_host", [SENTINEL, "sk-" + "a" * 24])
def test_final_redactor_masks_registered_values_and_token_patterns_in_selected_metadata(
    fmt: Any, detail: Any, secret_host: str
) -> None:
    redactor = RecordingRedactor()
    on_reveal = redactor.register_secret
    on_reveal(ID)
    on_reveal("123456789")
    on_reveal(SENTINEL)
    stream = StringIO()
    configure_logging(
        level="debug", detail=detail, fmt=fmt, stream=stream, redactor=redactor, host=secret_host
    )
    get_logger("execution.worker").info(
        "stage.completed", run_id=ID, duration_ms=123456789, passed=3, digest=DIGEST, secret=SENTINEL
    )
    assert redactor.documents[0]["run_id"] == ID
    assert redactor.documents[0]["duration_ms"] == 123456789
    assert "secret" not in redactor.documents[0]
    assert MASK in stream.getvalue()
    assert all(value not in stream.getvalue() for value in (ID, "123456789", secret_host, SENTINEL))
    if fmt == "json":
        record = json.loads(stream.getvalue())
        assert record["run_id"] == record["duration_ms"] == record["host"] == MASK
        assert record["passed"] == 3
        assert record["digest"] == DIGEST


def test_json_and_text_have_identical_projection() -> None:
    captures: list[JsonObject] = []
    for fmt in ("json", "text"):
        redactor = RecordingRedactor()
        configure_logging(
            level="info", detail="normal", fmt=fmt, stream=StringIO(), redactor=redactor, host="test-host"
        )
        get_logger("execution.worker").info(
            "stage.completed", passed=2, digest=DIGEST, payload={"nested": PRIVATE}, argv=[PRIVATE]
        )
        captures.append({key: value for key, value in redactor.documents[0].items() if key != "ts"})
    assert captures[0] == captures[1]


@pytest.mark.parametrize("fmt", ["json", "text"])
@pytest.mark.parametrize("detail", ["normal", "debug"])
@pytest.mark.parametrize("secret", [ID.upper(), "019A0254-fC00-7000-8000-000000000001"])
@pytest.mark.parametrize("as_uuid", [False, True])
@pytest.mark.parametrize(
    ("slot", "via_bind"),
    [
        (name, bound)
        for name in (
            "actor_id",
            "workspace_id",
            "project_id",
            "plan_id",
            "run_id",
            "task_id",
            "attempt_id",
            "step_id",
            "parent_step_id",
            "request_id",
            "correlation_id",
            "causation_id",
            "parent_causation_id",
        )
        for bound in (False, True)
    ]
    + [("event_id", False)],
)
def test_registered_uuid_stays_masked_after_every_id_projection(
    fmt: Any,
    detail: Any,
    secret: str,
    as_uuid: bool,
    slot: str,
    via_bind: bool,
) -> None:
    redactor = Redactor(patterns=())
    redactor.register_secret(secret)
    stream = StringIO()
    configure_logging(
        level="info", detail=detail, fmt=fmt, stream=stream, redactor=redactor, host="test-host"
    )
    value = UUID(secret) if as_uuid else secret
    fields: dict[str, Any] = {slot: value}
    context = bind(**fields) if via_bind else nullcontext()
    other = "019a0254-fc00-7000-8000-000000000002"
    # Use a separate, unregistered envelope ID as a positive control in the same record.
    control_slot = "task_id" if slot == "run_id" else "run_id"
    event = "relay.delivery.failed" if slot == "event_id" else "stage.completed"
    with context:
        get_logger("execution.worker").info(event, **{control_slot: other}, **({} if via_bind else fields))
    output = stream.getvalue()
    assert secret not in output
    assert ID not in output
    assert MASK in output
    assert other in output
    if fmt == "json":
        record = json.loads(output)
        assert record[slot] == MASK
        assert record[control_slot] == other
    else:
        assert f'{slot}="{MASK}"' in output


@pytest.mark.parametrize("fmt", ["json", "text"])
@pytest.mark.parametrize("detail", ["normal", "debug"])
def test_request_id_registration_remains_exact_through_bind(fmt: Any, detail: Any) -> None:
    request = "req_" + "A" * 26
    other = "req_" + "B" * 26
    redactor = Redactor(patterns=())
    redactor.register_secret(request)
    stream = StringIO()
    configure_logging(
        level="info", detail=detail, fmt=fmt, stream=stream, redactor=redactor, host="test-host"
    )
    with bind(request_id=request, correlation_id=other):
        get_logger("execution.worker").info("stage.completed", passed=1)
    assert request not in stream.getvalue()
    assert other in stream.getvalue()
    assert MASK in stream.getvalue()
