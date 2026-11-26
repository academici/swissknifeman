"""Closed projection rules and context lifetime, without touching sinks."""

import asyncio
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.ports_uow import Surface
from skm.platform.logging.envelope import LOG_FIELDS, bind, context_fields, safe_fields, source_fields

ID = "019a0254-fc00-7000-8000-000000000001"
REQUEST = "req_" + "A" * 26
DIGEST = "sha256:" + "a" * 64


def test_common_envelope_checks_ids_and_converts_only_declared_types() -> None:
    fields: dict[str, object] = {name: UUID(ID) for name in LOG_FIELDS[11:20]}
    fields.update(
        request_id=REQUEST,
        correlation_id=ID,
        causation_id=ID,
        parent_causation_id=None,
        surface=Surface.WORKER,
    )
    assert safe_fields("unregistered.event", fields) == {
        **dict.fromkeys(LOG_FIELDS[11:20], ID),
        "request_id": REQUEST,
        "correlation_id": ID,
        "causation_id": ID,
        "parent_causation_id": None,
        "surface": "worker",
    }


def test_unknown_event_and_unknown_operation_default_to_empty_extra_projection() -> None:
    fields = {"run_id": ID, "duration_ms": 42, "code": "NOT_FOUND", "payload": {"private": "text"}}
    assert safe_fields("unknown.event", fields) == {"run_id": ID}
    for selector in ("command", "operation"):
        assert safe_fields("bus.command.completed", {**fields, selector: "unknown.operation"}) == {
            "run_id": ID
        }
    assert safe_fields(
        "bus.command.completed",
        {
            **fields,
            "command": "workspace.create_project",
            "operation": "execution.begin_stage",
        },
    ) == {"run_id": ID}


def test_known_metadata_and_canonical_order() -> None:
    fields = {
        "passed": 3,
        "digest": DIGEST,
        "run_id": ID,
        "duration_ms": 42.5,
        "stage": "run_checks",
        "code": ErrorCode.NOT_FOUND,
        "dto": "private",
        "z": 1,
    }
    result = safe_fields("stage.completed", fields)
    assert result == {
        "run_id": ID,
        "code": "NOT_FOUND",
        "digest": DIGEST,
        "duration_ms": 42.5,
        "passed": 3,
        "stage": "run_checks",
    }
    assert list(result) == ["run_id", "code", "digest", "duration_ms", "passed", "stage"]
    assert "event" in LOG_FIELDS
    assert "type" not in LOG_FIELDS


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("run_id", "private-document"),
        ("actor_id", "operator name"),
        ("surface", "private"),
        ("request_id", ""),
        ("request_id", "a" * 129),
        ("request_id", "request private"),
        ("request_id", "request/private"),
        ("request_id", "request\nprivate"),
        ("request_id", "request\x00private"),
        ("host", "/private/worktree"),
        ("host", "bad\nhost"),
        ("pid", True),
        ("pid", -1),
        ("ts", "2026-02-30T12:00:00.000Z"),
        ("ts", "2026-10-27T12:00:00Z"),
        ("level", "trace"),
        ("message", "private prose"),
        ("reason_code", "private prose"),
    ],
)
def test_invalid_common_values_are_excluded(name: str, value: object) -> None:
    assert safe_fields("unknown.event", {name: value}) == {}


@pytest.mark.parametrize("request_id", ["req-" + ID, "api:test-42", "a" * 128, REQUEST])
def test_api_request_ids_survive_projection_and_context(request_id: str) -> None:
    assert safe_fields("unknown.event", {"request_id": request_id}) == {"request_id": request_id}
    with bind(request_id=request_id):
        assert context_fields()["request_id"] == request_id
    assert context_fields() == {}


@pytest.mark.parametrize(
    ("name", "value"),
    [
        ("passed", True),
        ("passed", -1),
        ("passed", 1 << 53),
        ("duration_ms", True),
        ("duration_ms", -0.1),
        ("duration_ms", float("nan")),
        ("duration_ms", float("inf")),
        ("duration_ms", 10**1000),
        ("digest", "private text"),
        ("stage", "custom private stage"),
        ("code", "ARBITRARY_PRIVATE_CODE"),
        ("passed", {"value": 3}),
    ],
)
def test_wrong_types_and_bounds_are_excluded(name: str, value: object) -> None:
    assert safe_fields("stage.completed", {name: value}) == {}


@pytest.mark.parametrize(
    ("event", "expected"),
    [
        ("bus.command.failed", "INTERNAL_ERROR"),
        ("worker.stage.failed", "INTERNAL_ERROR"),
        ("policy.denied", "FORBIDDEN"),
    ],
)
def test_failures_always_have_a_closed_reason(event: str, expected: str) -> None:
    assert safe_fields(event, {"reason_code": "private prose"})["reason_code"] == expected
    assert safe_fields(event, {"reason_code": ErrorCode.NOT_FOUND})["reason_code"] == "NOT_FOUND"
    assert safe_fields(event, {"code": ErrorCode.NOT_FOUND})["reason_code"] == "NOT_FOUND"


CONFIG_COMMANDS = (
    "settings.set_value",
    "settings.unset_value",
    "settings.remove_value",
    "settings.lock_value",
    "settings.unlock_value",
    "settings.import_config",
)
CONFIG_QUERIES = (
    "settings.get_value",
    "settings.get_schema",
    "settings.get_generation",
    "settings.explain_config",
    "settings.list_entries",
    "settings.export_config",
    "settings.get_history",
)


@pytest.mark.parametrize("command", [*CONFIG_COMMANDS, *CONFIG_QUERIES])
@pytest.mark.parametrize("code", ["CONFIG_INVALID", "SCHEMA_INVALID", "VERSION_CONFLICT", "FORBIDDEN"])
def test_config_operations_log_the_user_facing_failure_code(command: str, code: str) -> None:
    fields = {"command": command, "code": code, "duration_ms": 3, "error.type": "SkmError"}
    projected = safe_fields("bus.command.failed", fields)
    assert projected["reason_code"] == code
    assert projected["code"] == code
    assert projected["command"] == command


def test_unlisted_operation_still_reports_the_internal_default() -> None:
    fields = {"command": "settings.unknown_op", "code": "CONFIG_INVALID"}
    assert safe_fields("bus.command.failed", fields)["reason_code"] == "INTERNAL_ERROR"


def test_config_operation_schema_urn_is_bound_to_its_operation() -> None:
    urn = "urn:skm:settings:command:set-value:v1"
    fields = {"command": "settings.set_value", "schema_urn": urn}
    assert safe_fields("bus.command.started", fields)["schema_urn"] == urn
    other = {"command": "settings.set_value", "schema_urn": "urn:skm:settings:command:lock-value:v1"}
    assert "schema_urn" not in safe_fields("bus.command.started", other)


def test_static_message_and_schema_match_the_registered_operation() -> None:
    result = safe_fields(
        "bus.command.started",
        {
            "command": "workspace.create_project",
            "schema_urn": "urn:skm:workspace:command:create-project:v1",
            "message": "Command started",
        },
    )
    assert result["message"] == "Command started"
    assert result["schema_urn"] == "urn:skm:workspace:command:create-project:v1"
    assert "schema_urn" not in safe_fields(
        "bus.command.started",
        {
            "command": "workspace.create_project",
            "schema_urn": "urn:skm:execution:command:begin-stage:v1",
        },
    )


def test_nested_binding_restores_all_context_even_on_exception() -> None:
    assert context_fields() == {}
    with bind(
        request_id=REQUEST,
        correlation_id=REQUEST,
        causation_id=ID,
        parent_causation_id=None,
        actor_id=ID,
        workspace_id=ID,
    ):
        original = context_fields()

        def nested_failure() -> None:
            with bind(request_id=ID, causation_id=None, parent_causation_id=ID):
                assert context_fields()["request_id"] == ID
                assert context_fields()["parent_causation_id"] == ID
                raise RuntimeError("private")

        with pytest.raises(RuntimeError):
            nested_failure()
        assert context_fields() == original
        copied = context_fields()
        copied["workspace_id"] = "cannot mutate original"
        assert context_fields() == original
        with bind(request_id="invalid/value", payload="private"):
            assert context_fields()["request_id"] is None
            assert "payload" not in context_fields()
    assert context_fields() == {}


def test_async_tasks_have_isolated_context() -> None:
    async def task(request: str) -> str:
        with bind(request_id=request):
            await asyncio.sleep(0)
            assert context_fields()["request_id"] == request
            return request

    async def run() -> list[str]:
        return list(await asyncio.gather(task(REQUEST), task(ID)))

    assert asyncio.run(run()) == [REQUEST, ID]
    assert context_fields() == {}


def test_schema_source_masks_root_compositions_and_properties_fail_closed() -> None:
    assert source_fields({"run_id": ID}, schema={"x-skm-secret": True}) == {}
    assert source_fields({"run_id": ID}, schema={"$ref": "urn:unresolved"}) == {}
    assert source_fields({"run_id": ID}, schema={"properties": {"run_id": {"anyOf": [{}]}}}) == {}
