"""``policy.record_tool_decisions`` (policy §7, §11): the append-only audit of hook and worker decisions."""

from datetime import timedelta
from typing import Any

import pytest

from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.modules.access.public import Role
from skm.modules.policy.generated.commands import RecordToolDecisions, RecordToolDecisionsRecordsItem
from skm.modules.policy.ports import DecisionAuditRepository
from unit.policy.application.harness import World
from unit.policy.application.test_lifecycle import refused


def record(world: World, **changes: Any) -> RecordToolDecisionsRecordsItem:
    values: dict[str, Any] = {
        "at": world.clock.now() - timedelta(seconds=3),
        "tool": "fs.write",
        "call_summary": "write /work/main/a.py",
        "outcome": "allow",
        "code": None,
        "rule": None,
        "operation": "modify_write_set",
        "source": "hook",
    }
    values.update(changes)
    return RecordToolDecisionsRecordsItem(**values)


def send(world: World, *records: RecordToolDecisionsRecordsItem, who: str = "owner") -> Any:
    return world.run(RecordToolDecisions(scope_id=world.scope_id, records=records), who)


def test_decisions_are_stored_with_the_principal_scope_and_workspace_and_raise_no_events(
    world: World,
) -> None:
    before = len(world.backend.committed.core.events)
    result = send(
        world,
        record(world),
        record(world, outcome="deny", code="path_outside_scope", operation=None, tool="fs.edit"),
        record(world, outcome="warn", operation="modify_outside_write_set", rule="outside"),
    )
    assert result.recorded == 3
    rows = world.audit()
    assert [row.outcome for row in rows] == ["allow", "deny", "warn"]
    owner = world.actor("owner")
    assert {(row.principal_id, row.scope_id, row.workspace_id) for row in rows} == {
        (owner.principal_id, world.scope_id, world.workspace_id)
    }
    assert {row.recorded_at for row in rows} == {world.clock.now()}
    assert len(world.backend.committed.core.events) == before  # high-frequency records raise no events


def test_the_risk_signal_reads_back_by_operation(world: World) -> None:
    send(world, record(world), record(world, outcome="warn", operation="modify_outside_write_set"))
    with world.uow(readonly=True) as uow:
        warned = uow.repo(DecisionAuditRepository).for_scope(
            world.scope_id, operation="modify_outside_write_set"
        )
        everything = uow.repo(DecisionAuditRepository).for_scope(world.scope_id)
    assert [row.outcome for row in warned] == ["warn"]
    assert len(everything) == 2


@pytest.mark.parametrize(
    "bad",
    [
        pytest.param({"outcome": "deny", "code": None}, id="deny-without-code"),
        pytest.param({"outcome": "allow", "code": "path_denied"}, id="code-without-deny"),
        pytest.param({"outcome": "deny", "code": "made_up"}, id="unknown-code"),
        pytest.param({"operation": "format_disk"}, id="unknown-operation"),
        pytest.param({"tool": ""}, id="empty-tool"),
        pytest.param({"tool": "t" * 201}, id="long-tool"),
    ],
)
def test_a_record_breaking_the_vocabulary_is_refused_whole(world: World, bad: dict[str, Any]) -> None:
    refused(world, lambda: send(world, record(world), record(world, **bad)), ErrorCode.SCHEMA_INVALID)
    assert world.audit() == []


def test_only_a_worker_records_worker_decisions(world: World) -> None:
    refused(
        world,
        lambda: send(world, record(world, source="worker")),
        ErrorCode.FORBIDDEN,
        reason="source_not_worker",
    )
    world.person("w1", {world.workspace_id: Role.WORKER}, kind=PrincipalKind.WORKER)
    assert send(world, record(world, source="worker"), who="w1").recorded == 1
    assert world.audit()[0].source.value == "worker"


def test_a_reader_of_the_scope_records_hook_decisions_and_a_stranger_cannot(world: World) -> None:
    world.person("watcher", {world.workspace_id: Role.VIEWER})
    world.person("stranger", {})
    assert send(world, record(world), who="watcher").recorded == 1
    refused(world, lambda: send(world, record(world), who="stranger"), ErrorCode.FORBIDDEN)


def test_the_most_a_batch_may_hold_is_two_hundred(world: World) -> None:
    assert send(world, *[record(world) for _ in range(200)]).recorded == 200
    refused(world, lambda: send(world, *[record(world) for _ in range(201)]), ErrorCode.SCHEMA_INVALID)
    assert len(world.audit()) == 200


def test_a_repeated_batch_with_the_same_key_is_stored_once(world: World) -> None:
    dto = RecordToolDecisions(scope_id=world.scope_id, records=(record(world),))
    assert world.run(dto, key="batch-1") == world.run(dto, key="batch-1")
    assert len(world.audit()) == 1
