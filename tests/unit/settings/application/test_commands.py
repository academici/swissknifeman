"""Settings write commands through the bus on the memory backend (settings §A.7.1-A.7.5).

The harness here is the vertical slice of the settings commands: the real bus, the packaged settings registry
with every owner validator, the real ``ConfigLoader``, the memory config store and the memory settings
repositories. ``test_import.py`` and ``test_queries.py`` load it with ``run_path``.

Invariants: a refused command writes nothing (entries, history, generation, events); every write takes one
generation; a value change with a lock change is two history steps and ``row_version + 2``; no-op writes
leave everything untouched; rights the DTO cannot reveal are refused (fail closed).
"""

from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.app import FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as CORE_REPOSITORIES
from skm.adapters.memory.settings import REPOSITORIES as SETTINGS_REPOSITORIES
from skm.adapters.memory.settings.repositories import settings_state
from skm.adapters.memory.uow import InMemoryBackend
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.context import CommandContext
from skm.application_bus.middleware import request_digest
from skm.application_bus.ports import Authorizer, AuthzDecision
from skm.application_bus.registry import BusRegistry
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.kernel.scopes import ScopeRef as KernelScopeRef
from skm.modules.access.permissions import PERMISSIONS as CATALOG
from skm.modules.settings.application.commands import lock_value as lock_value_module
from skm.modules.settings.application.commands import remove_value as remove_value_module
from skm.modules.settings.application.commands import set_value as set_value_module
from skm.modules.settings.application.rights import write_permissions
from skm.modules.settings.application.scopes import resolve_target_scope
from skm.modules.settings.application.write_flow import safe_value
from skm.modules.settings.domain.history import ChangeKind
from skm.modules.settings.generated import commands
from skm.modules.settings.module import MODULE
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.sources.packs import PackFragment
from skm.platform.config.store import ConfigStore, PackConfigSource, ScopeTree
from skm.platform.logging.logger import get_logger
from support.registries import schemas, settings_registry

INSTANCE = ScopeId(UUID("01900000-0000-7000-8000-000000000001"))
WORKSPACE = ScopeId(UUID("01900000-0000-7000-8000-0000000000a1"))
PROJECT = ScopeId(UUID("01900000-0000-7000-8000-0000000000c1"))
PLAN = ScopeId(UUID("01900000-0000-7000-8000-0000000000d1"))
RUN = ScopeId(UUID("01900000-0000-7000-8000-0000000000e1"))
HOST = ScopeId(UUID("01900000-0000-7000-8000-0000000000f1"))
SCOPE_IDS = {
    "instance": INSTANCE,
    "workspace": WORKSPACE,
    "project": PROJECT,
    "plan": PLAN,
    "run": RUN,
    "host": HOST,
}
ACTOR = Actor(PrincipalId(UUID("01900000-0000-7000-8000-0000000000b1")), PrincipalKind.HUMAN, "tester")
EVERYTHING = frozenset(CATALOG)


class Packs:
    """``PackConfigSource`` with fixed fragments."""

    def __init__(self, *fragments: PackFragment) -> None:
        self.fragments_ = fragments

    def generation(self) -> int:
        return len(self.fragments_)

    def fragments(self, scope_chain: object) -> tuple[PackFragment, ...]:
        return self.fragments_


@dataclass
class Harness:
    backend: InMemoryBackend
    bus: Bus
    authorizer: FakeAuthorizer
    clock: FrozenClock
    ids: SequentialIds
    loader: ConfigLoader
    counter: int = 0

    def meta(self, key: str | None = None) -> RequestMeta:
        self.counter += 1
        return RequestMeta(self.request_id, Surface.TEST, key, self.clock.now())

    @property
    def request_id(self) -> str:
        """The request id of the latest ``meta``."""
        return f"req_{self.counter:0>26}"

    def run(self, dto: object, *, key: str | None = None) -> Any:
        return self.bus.dispatch(dto, actor=ACTOR, meta=self.meta(key))

    def ask(self, dto: object) -> Any:
        return self.bus.ask(dto, actor=ACTOR, meta=self.meta())

    def uow(self, *, readonly: bool = False) -> Any:
        return self.backend.uow_factory()(self.meta(), readonly=readonly)

    # ------------------------------------------------------------------ observations
    @property
    def generation(self) -> int:
        return self.backend.committed.core.config_generation

    @property
    def history(self) -> list[Any]:
        return list(settings_state(self.backend.committed).history)

    @property
    def events(self) -> list[Any]:
        return list(self.backend.committed.core.events)

    @property
    def audits(self) -> list[Any]:
        return list(self.backend.committed.core.audit)

    @property
    def receipts(self) -> list[Any]:
        return list(self.backend.committed.core.idempotency.values())

    def entries(self, level: str = "project") -> dict[str, Any]:
        return dict(settings_state(self.backend.committed).entries.get(SCOPE_IDS[level], {}))

    def snapshot(self) -> tuple[object, ...]:
        """Everything a refused command must leave untouched."""
        committed = self.backend.committed
        state = settings_state(committed)
        return (
            committed.core.config_generation,
            {scope: dict(rows) for scope, rows in committed.core.config_entries.items()},
            {scope: dict(rows) for scope, rows in state.entries.items()},
            list(state.history),
            len(committed.core.events),
        )


def harness(*, allowed: Iterable[str] | None = None, packs: PackConfigSource | None = None) -> Harness:
    pack_source = packs if packs is not None else Packs()
    bus_registry = BusRegistry.build(
        (MODULE,), schemas=schemas(), permission_catalog=EVERYTHING, disabled_modules=frozenset()
    )
    authorizer = FakeAuthorizer(allowed)
    factories: dict[type, Any] = {
        **CORE_REPOSITORIES,
        **SETTINGS_REPOSITORIES,
        ConfigStore: MemoryConfigStore,
        PackConfigSource: lambda _state: pack_source,
        Authorizer: lambda _state: authorizer,  # the bus's authorizer, confirmed again by the handlers
    }
    clock, ids = FrozenClock(), SequentialIds()
    backend = InMemoryBackend(
        factories=factories,
        schemas=schemas(),
        subscriptions=bus_registry.subscription_index(),
        ids=ids,
        clock=clock,
    )
    loader = ConfigLoader(settings_registry(), pack_source)
    bus = Bus(
        registry=bus_registry,
        schemas=schemas(),
        uow_factory=backend.uow_factory(),
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=loader,
        clock=clock,
        ids=ids,
        entropy=DeterministicEntropy(),
        gateways=GatewayTable({}, "control_plane_gateway"),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )
    made = Harness(backend, bus, authorizer, clock, ids, loader)
    with made.uow() as uow:
        scopes = uow.repo(ScopeRegistry)
        ws = WorkspaceId(WORKSPACE)
        scopes.create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        scopes.create(WORKSPACE, ScopeKind.WORKSPACE, parent=INSTANCE, workspace_id=ws)
        scopes.create(PROJECT, ScopeKind.PROJECT, parent=WORKSPACE, workspace_id=ws)
        scopes.create(PLAN, ScopeKind.PLAN, parent=PROJECT, workspace_id=ws)
        scopes.create(RUN, ScopeKind.RUN, parent=PLAN, workspace_id=ws)
        scopes.create(HOST, ScopeKind.HOST, parent=INSTANCE, workspace_id=None)
        uow.commit()
    return made


def scope(cls: type[Any], level: str, scope_id: UUID | str | None = "default") -> Any:
    chosen = SCOPE_IDS[level] if scope_id == "default" else scope_id
    return cls(level=level, scope_id=chosen)


def set_value(level: str, key: str, value: JsonValue, **fields: Any) -> commands.SetValue:
    return commands.SetValue(
        scope=scope(commands.SetValueDefsScopeRef, level), key=key, value=value, **fields
    )


def unset_value(level: str, key: str, **fields: Any) -> commands.UnsetValue:
    return commands.UnsetValue(scope=scope(commands.UnsetValueDefsScopeRef, level), key=key, **fields)


def remove_value(level: str, key: str, **fields: Any) -> commands.RemoveValue:
    return commands.RemoveValue(scope=scope(commands.RemoveValueDefsScopeRef, level), key=key, **fields)


def lock_value(level: str, key: str, **fields: Any) -> commands.LockValue:
    return commands.LockValue(scope=scope(commands.LockValueScope, level), key=key, **fields)


def unlock_value(level: str, key: str, **fields: Any) -> commands.UnlockValue:
    return commands.UnlockValue(scope=scope(commands.UnlockValueScope, level), key=key, **fields)


def refused(made: Harness, dto: object, code: ErrorCode) -> SkmError:
    """Run ``dto``, expect ``code`` and prove that nothing was written."""
    before = made.snapshot()
    with pytest.raises(SkmError) as caught:
        made.run(dto)
    assert caught.value.code is code, caught.value
    assert made.snapshot() == before
    return caught.value


ROUNDS = "execution.review.max_rounds"
PROFILE = "execution.workflow.profile"
TARGETS = "integrations.targets"


@pytest.mark.parametrize("nested", [False, True])
def test_safe_value_masks_unevaluated_secrets_after_failed_additional_properties(nested: bool) -> None:
    secret = {"type": "integer", "x-skm-secret": True}
    schema = {
        "properties": {"public": {}},
        "additionalProperties": {"type": "integer"},
        "unevaluatedProperties": {"properties": {"secret": secret}} if nested else secret,
    }
    spec = replace(settings_registry().spec(TARGETS), value_schema=cast("Any", schema))
    literal = "synthetic-unevaluated-projection-value"
    extra: JsonValue = {"secret": literal, "public": "ok"} if nested else literal
    masked: JsonValue = {"secret": "<redacted>", "public": "ok"} if nested else "<redacted>"
    value: JsonValue = {"public": "ok", "extra": extra}
    assert safe_value(spec, value) == {"public": "ok", "extra": masked}
    assert value == {"public": "ok", "extra": extra}


# ---------------------------------------------------------------------------------------------------------
# set_value


def test_set_creates_an_entry_with_one_generation_history_and_event() -> None:
    made = harness()
    result = made.run(set_value("project", ROUNDS, 1, reason="tighter"))
    assert result.changed is True
    assert result.generation == made.generation == 1
    assert (result.entry.row_version, result.entry.op, result.entry.value) == (1, "set", 1)
    assert result.entry.scope.label == f"project:{PROJECT}"
    assert result.entry.reason == "tighter"
    assert result.effective.value == 1
    assert result.effective.winner.level == "project"
    assert result.effective.winner.entry_id == result.entry.entry_id
    [record] = made.history
    assert (record.change_kind, record.generation, record.new_value, record.old_op) == (
        ChangeKind.CREATED,
        1,
        1,
        None,
    )
    [event] = made.events
    assert event.type == "urn:skm:settings:event:config-changed:v1"
    assert (event.stream_kind, event.stream_id, event.workspace_id) == ("config", PROJECT, WORKSPACE)
    assert event.payload["changes"] == {ROUNDS: "created"}
    assert event.payload["keys"] == [ROUNDS]
    assert "value" not in str(event.payload)  # names only, never values


def test_update_checks_the_expected_version_and_a_stale_one_writes_nothing() -> None:
    made = harness()
    made.run(set_value("project", ROUNDS, 2))
    updated = made.run(set_value("project", ROUNDS, 1, expected_row_version=1))
    assert (updated.entry.row_version, updated.generation) == (2, 2)
    assert [item.change_kind for item in made.history] == [ChangeKind.CREATED, ChangeKind.UPDATED]
    error = refused(made, set_value("project", ROUNDS, 2, expected_row_version=1), ErrorCode.VERSION_CONFLICT)
    assert error.details == {"expected": 1, "actual": 2}
    refused(made, set_value("plan", ROUNDS, 1, expected_row_version=3), ErrorCode.VERSION_CONFLICT)
    assert made.run(set_value("plan", ROUNDS, 1, expected_row_version=0)).entry.row_version == 1


def test_same_content_is_a_no_op_without_history_event_or_generation() -> None:
    made = harness()
    first = made.run(set_value("project", ROUNDS, 1))
    before = made.snapshot()
    again = made.run(set_value("project", ROUNDS, 1))
    assert again.changed is False
    assert again.generation == first.generation
    assert again.entry == first.entry
    assert again.effective.value == 1
    assert made.snapshot() == before


def test_value_and_lock_change_together_are_two_steps_and_version_plus_two() -> None:
    made = harness()
    created = made.run(set_value("instance", ROUNDS, 4, locked=True))
    assert created.entry.locked is True
    assert created.entry.row_version == 1
    assert [event.type.split(":")[-2] for event in made.events] == ["config-changed", "config-locked"]
    changed = made.run(set_value("instance", ROUNDS, 3, locked=False, expected_row_version=1))
    assert (changed.entry.row_version, changed.entry.locked, changed.generation) == (3, False, 2)
    steps = [(item.change_kind, item.generation, item.old_locked, item.new_locked) for item in made.history]
    assert steps == [
        (ChangeKind.CREATED, 1, None, True),
        (ChangeKind.UPDATED, 2, True, True),
        (ChangeKind.UNLOCKED, 2, True, False),
    ]
    assert [event.type.split(":")[-2] for event in made.events][2:] == ["config-changed", "config-unlocked"]
    assert made.events[2].payload["changes"] == {ROUNDS: "updated"}
    only_lock = made.run(set_value("instance", ROUNDS, 3, locked=True))
    assert only_lock.entry.row_version == 4
    assert made.events[-2].payload["changes"] == {ROUNDS: "lock_changed"}


def test_narrow_write_wider_than_the_ceiling_is_refused_at_project_but_opens_at_workspace() -> None:
    made = harness()
    error = refused(made, set_value("project", ROUNDS, 5), ErrorCode.CONFIG_NARROWING_VIOLATION)
    assert error.details["ceiling"] == 2  # the base value: default, no farther explicit level
    assert made.run(set_value("workspace", ROUNDS, 5)).effective.value == 5  # shared level opens the chain
    assert made.run(set_value("project", ROUNDS, 4)).effective.value == 4
    refused(made, set_value("plan", ROUNDS, 5), ErrorCode.CONFIG_NARROWING_VIOLATION)


def test_lock_above_refuses_nearer_writes() -> None:
    made = harness()
    made.run(set_value("workspace", ROUNDS, 3, locked=True))
    error = refused(made, set_value("project", ROUNDS, 1), ErrorCode.CONFIG_LOCKED)
    assert cast("dict[str, Any]", error.details["locked_by"])["level"] == "workspace"


def test_confirm_keys_need_confirmed() -> None:
    made = harness()
    command = "execution.generation.command"
    refused(made, set_value("project", command, ["make", "gen"]), ErrorCode.CONFIRMATION_REQUIRED)
    assert made.run(set_value("project", command, ["make", "gen"], confirmed=True)).changed is True


def test_section_validator_on_the_candidate_refuses_the_write() -> None:
    made = harness()
    made.run(set_value("project", "budgets.run.max_usd", 10))
    error = refused(made, set_value("project", "budgets.task.max_usd", 15), ErrorCode.CONFIG_INVALID)
    assert error.details["validator"] == "budgets.task_le_run"
    assert "budgets.run.max_usd" in cast("list[str]", error.details["keys"])
    assert made.run(set_value("project", "budgets.task.max_usd", 5)).changed is True


def test_append_and_invalid_values() -> None:
    made = harness()
    made.run(set_value("instance", TARGETS, ["codex"]))
    appended = made.run(set_value("project", TARGETS, ["cursor"], mode="append"))
    assert appended.entry.op == "append"
    assert appended.effective.value == ["codex", "cursor"]
    error = refused(made, set_value("project", TARGETS, ["nope"]), ErrorCode.CONFIG_INVALID)
    assert error.details["issues"]
    refused(made, set_value("project", ROUNDS, None), ErrorCode.CONFIG_INVALID)  # SET null is not unset
    refused(made, set_value("project", ROUNDS, [1], mode="append"), ErrorCode.CONFIG_OP_NOT_ALLOWED)
    refused(made, set_value("project", "nope.key", 1), ErrorCode.CONFIG_UNKNOWN_KEY)
    refused(made, set_value("project", "storage.statement_timeout_ms", 1), ErrorCode.CONFIG_SCOPE_NOT_ALLOWED)


RUN_USD = "budgets.run.max_usd"


def allowed_audit(made: Harness, action: str = "settings.set_value") -> Any:
    """The allowed audit record of the latest request (exactly one)."""
    [record] = [item for item in made.audits if item.request_id == made.request_id]
    assert (record.action, record.decision, record.actor_id) == (action, "allowed", ACTOR.principal_id)
    return record


def test_a_float_value_is_set_through_the_bus_and_an_equal_float_is_a_no_op() -> None:
    made = harness()
    result = made.run(set_value("project", RUN_USD, 15.0))  # canonical JSON refuses floats: the bus digest
    assert result.changed is True
    assert (result.entry.value, result.effective.value) == (15.0, 15.0)
    assert type(made.entries()[RUN_USD].value) is float
    assert allowed_audit(made).workspace_id == WORKSPACE
    before = made.snapshot()
    again = made.run(set_value("project", RUN_USD, 15.0))
    assert (again.changed, again.generation, again.entry) == (False, result.generation, result.entry)
    assert made.snapshot() == before
    updated = made.run(set_value("project", RUN_USD, 12.5, expected_row_version=1))
    assert (updated.entry.row_version, updated.effective.value, updated.generation) == (2, 12.5, 2)
    error = refused(made, set_value("project", RUN_USD, 25.5), ErrorCode.CONFIG_NARROWING_VIOLATION)
    assert error.details["ceiling"] == 20.0
    refused(made, set_value("project", RUN_USD, 12.25, expected_row_version=1), ErrorCode.VERSION_CONFLICT)
    assert made.entries()[RUN_USD].value == 12.5


def test_a_float_request_replays_by_its_idempotency_key() -> None:
    made = harness()
    dto = set_value("project", RUN_USD, 15.0)
    first = made.run(dto, key="budget-1")
    audits = len(made.audits)
    before = made.snapshot()
    replay = made.run(set_value("project", RUN_USD, 15.0), key="budget-1")
    assert replay == first  # the stored result, not a second write
    assert made.snapshot() == before
    assert len(made.audits) == audits
    [receipt] = made.receipts
    assert receipt.request_digest == request_digest(set_value_module.SPEC, dto)
    for value in (15, 15.5, "15.0"):  # the integer of the same value, another float, the string
        with pytest.raises(SkmError) as caught:
            made.run(set_value("project", RUN_USD, value), key="budget-1")
        assert caught.value.code is ErrorCode.IDEMPOTENCY_KEY_REUSED
        assert made.snapshot() == before
    assert len(made.receipts) == 1
    other = made.run(set_value("project", RUN_USD, 12.5, expected_row_version=1), key="budget-2")
    assert (other.changed, other.effective.value) == (True, 12.5)
    assert len(made.receipts) == 2


# ---------------------------------------------------------------------------------------------------------
# unset_value / remove_value


def test_unset_resets_to_the_default_and_remove_restores_the_farther_level() -> None:
    made = harness()
    made.run(set_value("instance", PROFILE, "quick-fix"))
    unset = made.run(unset_value("project", PROFILE))
    assert unset.entry.op == "unset"
    assert "value" not in unset.entry.to_json()
    assert unset.effective.value == "reviewed-development"
    assert unset.effective.winner.level == "project"
    removed = made.run(remove_value("project", PROFILE, expected_row_version=1))
    assert removed.removed_entry_id == unset.entry.entry_id
    assert removed.generation == 3
    assert removed.effective.value == "quick-fix"
    assert removed.effective.winner.level == "instance"
    assert made.history[-1].change_kind is ChangeKind.REMOVED
    assert made.history[-1].new_op is None
    assert made.events[-1].payload["changes"] == {PROFILE: "removed"}
    assert made.entries() == {}


def test_unset_is_refused_for_monotonic_keys() -> None:
    made = harness()
    refused(made, unset_value("project", ROUNDS), ErrorCode.CONFIG_OP_NOT_ALLOWED)
    refused(made, unset_value("project", "execution.advisor.human_gate"), ErrorCode.CONFIG_OP_NOT_ALLOWED)


def test_remove_needs_an_entry_and_may_drop_a_narrow_override() -> None:
    made = harness()
    error = refused(made, remove_value("project", ROUNDS), ErrorCode.NOT_FOUND)
    assert error.details["kind"] == "config_entry"
    made.run(set_value("project", ROUNDS, 1))
    assert made.run(remove_value("project", ROUNDS)).effective.value == 2
    made.run(set_value("project", ROUNDS, 1))
    refused(made, remove_value("project", ROUNDS, expected_row_version=7), ErrorCode.VERSION_CONFLICT)


# ---------------------------------------------------------------------------------------------------------
# lock_value / unlock_value


def test_lock_and_unlock_count_shadowed_entries_and_record_events() -> None:
    made = harness()
    made.run(set_value("workspace", ROUNDS, 3))
    made.run(set_value("project", ROUNDS, 2))
    made.run(set_value("plan", ROUNDS, 1))
    locked = made.run(lock_value("workspace", ROUNDS))
    assert (locked.changed, locked.shadowed_below, locked.entry.locked, locked.entry.row_version) == (
        True,
        2,
        True,
        2,
    )
    assert made.history[-1].change_kind is ChangeKind.LOCKED
    assert made.events[-1].type == "urn:skm:settings:event:config-locked:v1"
    before = made.snapshot()
    again = made.run(lock_value("workspace", ROUNDS))
    assert again.changed is False
    assert made.snapshot() == before
    refused(made, set_value("plan", ROUNDS, 1, expected_row_version=1), ErrorCode.CONFIG_LOCKED)
    unlocked = made.run(unlock_value("workspace", ROUNDS))
    assert unlocked.changed is True
    assert unlocked.shadowed_below == 2
    assert unlocked.entry.locked is False
    assert made.events[-1].type == "urn:skm:settings:event:config-unlocked:v1"


def test_lock_rules() -> None:
    made = harness()
    made.run(set_value("project", ROUNDS, 1))
    refused(
        made, lock_value("project", ROUNDS), ErrorCode.SCHEMA_INVALID
    )  # the DTO admits instance/workspace
    refused(made, lock_value("workspace", ROUNDS), ErrorCode.NOT_FOUND)
    error = refused(made, set_value("project", ROUNDS, 1, locked=True), ErrorCode.CONFIG_SCOPE_NOT_ALLOWED)
    assert error.details["reason"] == "lock_level"


# ---------------------------------------------------------------------------------------------------------
# rights, scopes and chains


def test_permission_sets_follow_level_lock_and_key_rights() -> None:
    assert write_permissions("project", [ROUNDS], lock_change=False) == ("config.write",)
    assert write_permissions("instance", [ROUNDS], lock_change=True) == ("config.lock", "config.write_shared")
    assert write_permissions("workspace", ["hooks.subscriptions"], lock_change=False) == (
        "config.write_shared",
        "hook.manage",
    )
    made = harness(allowed={"config.write"})
    refused(made, set_value("instance", ROUNDS, 4), ErrorCode.FORBIDDEN)
    refused(made, set_value("project", ROUNDS, 1, locked=False), ErrorCode.FORBIDDEN)  # config.lock
    assert made.run(set_value("project", ROUNDS, 1)).changed is True
    assert {call.permission for call in made.authorizer.calls} == {
        "config.write",
        "config.write_shared",
        "config.lock",
    }


def test_rights_the_dto_does_not_reveal_are_confirmed_by_the_handler() -> None:
    made = harness()
    made.run(set_value("instance", ROUNDS, 4, locked=True))
    made.run(set_value("instance", PROFILE, "quick-fix"))
    made.authorizer.allowed = {"config.write", "config.write_shared"}
    # Removing a locked entry needs config.lock; the bus could not see that from the DTO, the handler asks.
    error = refused(made, remove_value("instance", ROUNDS), ErrorCode.FORBIDDEN)
    assert error.details == {"permission": "config.lock", "reason_code": "ROLE_LACKS_PERMISSION"}
    assert made.authorizer.calls[-1].permission == "config.lock"
    assert made.run(remove_value("instance", PROFILE)).effective.value is not None  # unlocked: no config.lock
    made.authorizer.allow_all()
    assert made.run(remove_value("instance", ROUNDS)).effective.value == 2  # an authorized actor removes it
    assert made.history[-1].change_kind is ChangeKind.REMOVED


def request_audits(made: Harness) -> list[Any]:
    """Audit records of the latest request."""
    return [item for item in made.audits if item.request_id == made.request_id]


def test_removing_a_locked_entry_without_config_lock_is_audited_as_denied() -> None:
    made = harness()
    made.run(set_value("instance", ROUNDS, 4, locked=True))
    made.authorizer.allowed = {"config.write", "config.write_shared"}  # all the DTO reveals
    error = refused(made, remove_value("instance", ROUNDS), ErrorCode.FORBIDDEN)
    assert error.details == {"permission": "config.lock", "reason_code": "ROLE_LACKS_PERMISSION"}
    [denied] = request_audits(made)
    assert (denied.action, denied.decision, denied.reason_code) == (
        "settings.remove_value",
        "denied",
        "ROLE_LACKS_PERMISSION",
    )
    assert denied.workspace_id is None
    assert denied.target == {"scope": {"kind": "instance", "id": str(INSTANCE)}, "permission": "config.lock"}
    assert made.entries("instance")[ROUNDS].locked is True
    assert made.backend.active == 0
    # a write the DTO reveals is still refused by the bus itself, audited once, before the handler
    error = refused(made, unlock_value("instance", ROUNDS), ErrorCode.FORBIDDEN)
    [bus_denied] = request_audits(made)
    assert (bus_denied.decision, bus_denied.target["permission"]) == ("denied", "config.lock")
    # a refusal that is no denial writes no audit
    refused(made, remove_value("project", PROFILE), ErrorCode.NOT_FOUND)
    assert request_audits(made) == []
    made.authorizer.allow_all()
    assert made.run(remove_value("instance", ROUNDS)).generation == made.generation
    assert [item.decision for item in request_audits(made)] == ["allowed"]


def script(made: Harness, scripted: str, decisions: list[AuthzDecision]) -> list[AuthzDecision]:
    """Answer ``scripted`` with ``decisions`` in turn (the state changing between them, e.g. a membership
    removed and committed meanwhile); other permissions keep the fake's answers. Returns those given."""
    decide = made.authorizer.authorize
    given: list[AuthzDecision] = []

    def authorize(uow: Any, actor: Any, permission: str, chain: Any) -> Any:
        if permission != scripted:
            return decide(uow, actor, permission, chain)
        given.append(decisions[len(given)])
        return given[-1]

    made.authorizer.authorize = authorize
    return given


ALLOW = AuthzDecision(allowed=True)


def refusal(reason: str) -> AuthzDecision:
    return AuthzDecision(allowed=False, reason_code=reason)


@pytest.mark.parametrize(
    ("original", "later"),
    [
        ("ROLE_LACKS_PERMISSION", refusal("NO_MEMBERSHIP")),
        ("NO_MEMBERSHIP", refusal("ROLE_LACKS_PERMISSION")),
        ("NO_MEMBERSHIP", ALLOW),
        ("TOKEN_NARROWED", refusal("TOKEN_SCOPE")),
    ],
)
def test_a_refused_lock_right_is_audited_with_the_reason_of_the_decision_that_refused_it(
    original: str, later: AuthzDecision
) -> None:
    made = harness()
    made.run(set_value("instance", ROUNDS, 4, locked=True))
    given = script(made, "config.lock", [refusal(original), later])
    error = refused(made, remove_value("instance", ROUNDS), ErrorCode.FORBIDDEN)
    assert error.details == {"permission": "config.lock", "reason_code": original}
    assert given == [refusal(original)]  # only the handler's own decision; never asked again
    [denied] = request_audits(made)
    assert (denied.action, denied.decision, denied.reason_code) == (
        "settings.remove_value",
        "denied",
        original,
    )
    assert denied.actor_id == ACTOR.principal_id
    assert denied.target == {"scope": {"kind": "instance", "id": str(INSTANCE)}, "permission": "config.lock"}
    assert made.entries("instance")[ROUNDS].locked is True
    assert (made.receipts, made.backend.active) == ([], 0)


def test_a_refusal_without_a_reason_is_reported_without_one_and_audited_with_the_bus_fallback() -> None:
    made = harness()
    made.run(set_value("instance", ROUNDS, 4, locked=True))
    script(made, "config.lock", [AuthzDecision(allowed=False), refusal("NO_MEMBERSHIP")])
    error = refused(made, remove_value("instance", ROUNDS), ErrorCode.FORBIDDEN)
    assert error.details == {"permission": "config.lock"}  # no reason is made up
    [denied] = request_audits(made)
    # the bus default of a denial without a reason (open gap: no agreed "unknown"), never the later one
    assert (denied.decision, denied.reason_code) == ("denied", "ROLE_LACKS_PERMISSION")


def test_a_replace_import_audits_the_original_reason_of_a_refused_key_right() -> None:
    made = harness()
    made.run(set_value("project", HOOKS, {"audit": SUBSCRIPTION}, confirmed=True))
    given = script(made, "hook.manage", [refusal("TOKEN_NARROWED"), refusal("NO_MEMBERSHIP")])
    document = {"execution": {"review": {"max_rounds": 1}}}  # replace mode removes the hooks entry
    dto = commands.ImportConfig(
        scope=commands.ImportConfigDefsScopeRef(level="project", scope_id=PROJECT),
        document=document,
        format="json",
        mode="replace",
        confirmed=True,
    )
    error = refused(made, dto, ErrorCode.CONFIG_INVALID)
    cause = error.__cause__
    assert isinstance(cause, SkmError)
    assert (cause.code, cause.details) == (
        ErrorCode.FORBIDDEN,
        {"permission": "hook.manage", "reason_code": "TOKEN_NARROWED"},
    )
    assert given == [refusal("TOKEN_NARROWED")]
    [denied] = request_audits(made)
    assert (denied.action, denied.decision, denied.reason_code) == (
        "settings.import_config",
        "denied",
        "TOKEN_NARROWED",
    )
    assert denied.target["permission"] == "hook.manage"
    assert HOOKS in made.entries("project")


@pytest.mark.parametrize(
    "value", [float("nan"), float("inf"), float("-inf"), [1.5, float("nan")], {"a": float("inf")}]
)
def test_a_non_finite_number_is_schema_invalid_through_the_bus(value: Any) -> None:
    made = harness()
    for dto in (set_value("project", "budgets.run.max_usd", value), set_value("project", HOOKS, value)):
        error = refused(made, dto, ErrorCode.SCHEMA_INVALID)
        assert error.details["reason"] == "not_json"
    assert (made.audits, made.receipts, made.authorizer.calls) == ([], [], [])


def refused_direct(
    made: Harness, spec: Any, dto: object, code: ErrorCode, *, resolved: KernelScopeRef | None = None
) -> SkmError:
    """``refused`` for a handler called around the bus (``direct``)."""
    before = made.snapshot()
    with pytest.raises(SkmError) as caught:
        direct(made, spec, dto, resolved=resolved)
    assert caught.value.code is code, caught.value
    assert made.snapshot() == before
    return caught.value


HOOKS = "hooks.subscriptions"
SUBSCRIPTION: dict[str, JsonValue] = {
    "class": "observation",
    "kind": "webhook",
    "execution_location": "control_plane",
    "event_types": ["urn:skm:planning:event:plan-created:v1"],
    "target": {"url": "https://a.example/hook", "secret": "secret://env/HOOK_SECRET"},
}


def test_a_handler_called_around_the_bus_confirms_every_right_itself() -> None:
    made = harness(allowed={"config.write"})
    hooks = set_value("project", HOOKS, {}, confirmed=True)
    error = refused_direct(made, set_value_module.SPEC, hooks, ErrorCode.FORBIDDEN)
    assert error.details == {"permission": "hook.manage", "reason_code": "ROLE_LACKS_PERMISSION"}
    assert ("hook.manage", PROJECT) in {(call.permission, call.scope_id) for call in made.authorizer.calls}
    error = refused_direct(
        made, set_value_module.SPEC, set_value("workspace", ROUNDS, 3), ErrorCode.FORBIDDEN
    )
    assert error.details == {"permission": "config.write_shared", "reason_code": "ROLE_LACKS_PERMISSION"}
    assert direct(made, set_value_module.SPEC, set_value("project", ROUNDS, 1)).changed is True
    made.authorizer.allowed = {"config.write_shared"}
    made.authorizer.reason_code = "NO_MEMBERSHIP"  # each refusal names the reason of its own decision
    error = refused_direct(made, set_value_module.SPEC, set_value("project", ROUNDS, 2), ErrorCode.FORBIDDEN)
    assert error.details == {"permission": "config.write", "reason_code": "NO_MEMBERSHIP"}
    made.authorizer.allowed = {"config.write_shared", "config.write"}
    locked = set_value("workspace", ROUNDS, 3, locked=True)
    error = refused_direct(made, set_value_module.SPEC, locked, ErrorCode.FORBIDDEN)
    assert error.details == {"permission": "config.lock", "reason_code": "NO_MEMBERSHIP"}
    assert direct(made, set_value_module.SPEC, set_value("workspace", ROUNDS, 3)).changed is True
    error = refused_direct(made, lock_value_module.SPEC, lock_value("workspace", ROUNDS), ErrorCode.FORBIDDEN)
    assert error.details == {"permission": "config.lock", "reason_code": "NO_MEMBERSHIP"}
    made.authorizer.allowed = {"config.write", "config.write_shared", "config.lock", "hook.manage"}
    assert direct(made, set_value_module.SPEC, hooks).changed is True
    assert direct(made, lock_value_module.SPEC, lock_value("workspace", ROUNDS)).changed is True
    assert (
        direct(made, remove_value_module.SPEC, remove_value("workspace", ROUNDS)).generation
        == made.generation
    )


def test_a_partial_deep_merge_contribution_is_checked_without_required() -> None:
    made = harness()
    made.run(set_value("workspace", HOOKS, {"audit": SUBSCRIPTION}, confirmed=True))
    partial: JsonValue = {"audit": {"kind": "webhook", "target": {"headers": {"X": "new"}}}}
    result = made.run(set_value("project", HOOKS, partial, confirmed=True))
    target = cast("dict[str, Any]", SUBSCRIPTION["target"])
    assert result.effective.value["audit"]["target"] == {**target, "headers": {"X": "new"}}
    bad_type: JsonValue = {"audit": {"target": {"headers": {"X": 1}}}}
    error = refused(made, set_value("project", HOOKS, bad_type, confirmed=True), ErrorCode.CONFIG_INVALID)
    assert "required" not in str(error.details)  # the type of the header, not the absent members
    # every partial member is valid, the merged target (webhook url plus a command argv) is not
    mixed: JsonValue = {"audit": {"target": {"argv": ["notify"]}}}
    refused(made, set_value("project", HOOKS, mixed, confirmed=True), ErrorCode.CONFIG_INVALID)
    alone = refused(made, set_value("instance", HOOKS, partial, confirmed=True), ErrorCode.CONFIG_INVALID)
    assert "required" in str(alone.details)  # nothing farther: the merged value lacks the required members


def test_scope_references_are_checked() -> None:
    made = harness()
    wrong_kind = commands.SetValue(
        scope=commands.SetValueDefsScopeRef(level="project", scope_id=WORKSPACE), key=ROUNDS, value=1
    )
    refused(made, wrong_kind, ErrorCode.INVALID_REFERENCE)
    no_id = commands.SetValue(scope=commands.SetValueDefsScopeRef(level="project"), key=ROUNDS, value=1)
    refused(made, no_id, ErrorCode.INVALID_REFERENCE)
    unknown = commands.SetValue(
        scope=commands.SetValueDefsScopeRef(level="project", scope_id=UUID(int=99)), key=ROUNDS, value=1
    )
    refused(made, unknown, ErrorCode.NOT_FOUND)
    instance = commands.SetValue(scope=commands.SetValueDefsScopeRef(level="instance"), key=ROUNDS, value=4)
    assert made.run(instance).entry.scope.scope_id == INSTANCE


def test_a_handler_called_around_the_bus_needs_an_explicit_scope_id() -> None:
    made = harness()
    for level in ("workspace", "project", "plan", "run", "host"):
        no_id = commands.SetValue(
            scope=commands.SetValueDefsScopeRef(level=level), key=LOG_LEVEL, value="debug"
        )
        resolved = KernelScopeRef(ScopeKind(level), SCOPE_IDS[level])  # a context of exactly that level
        error = refused_direct(
            made, set_value_module.SPEC, no_id, ErrorCode.INVALID_REFERENCE, resolved=resolved
        )
        assert error.details == {"kind": "scope", "level": level, "reason": "scope_id_required"}
        with made.uow(readonly=True) as uow, pytest.raises(SkmError) as caught:
            resolve_target_scope(uow, no_id.scope, FakeScopeChain().chain(uow, resolved))
        assert caught.value.code is ErrorCode.INVALID_REFERENCE
    instance = commands.SetValue(scope=commands.SetValueDefsScopeRef(level="instance"), key=ROUNDS, value=4)
    assert direct(made, set_value_module.SPEC, instance).entry.scope.scope_id == INSTANCE  # optional here
    with made.uow(readonly=True) as uow:
        assert resolve_target_scope(uow, None, FakeScopeChain().chain(uow, None)).scope.id == INSTANCE


def direct(made: Harness, spec: Any, dto: object, *, resolved: KernelScopeRef | None = None) -> Any:
    """The handler of ``spec`` in a unit of work with the context the bus builds (``ctx.config`` included);
    ``resolved`` replaces the scope the bus would take from the DTO."""
    with made.uow() as uow:
        chain = FakeScopeChain().chain(uow, resolved if resolved is not None else spec.scope_of(dto))
        target = KernelScopeRef(chain[-1].kind, chain[-1].id)
        ctx = CommandContext(
            actor=ACTOR,
            meta=made.meta(),
            scope=target,
            scope_chain=chain,
            clock=made.clock,
            ids=made.ids,
            entropy=DeterministicEntropy(),
            config=made.loader.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), target),
            log=get_logger("modules.settings"),
            gateways=GatewayTable({}, "control_plane_gateway"),
        )
        result = spec.handler(dto, ctx, uow)
        uow.commit()
    return result


LOG_LEVEL = "logging.level"
RECORD_ALLOWED = "access.audit.record_allowed"
HOST_TARGET = {"scope": {"kind": "host", "id": str(HOST)}, "permission": "config.write"}


def test_host_keys_resolve_in_the_host_chain() -> None:
    made = harness()
    made.run(set_value("instance", LOG_LEVEL, "debug"))
    host = made.run(set_value("host", LOG_LEVEL, "warning"))  # the bus audit step reads the instance policy
    assert host.effective.value == "warning"
    assert host.effective.winner.level == "host"
    assert made.history[-1].scope_id == HOST
    assert made.events[-1].workspace_id is None
    audit = allowed_audit(made)
    assert (audit.workspace_id, audit.target) == (None, HOST_TARGET)
    refused(made, set_value("project", LOG_LEVEL, "debug"), ErrorCode.CONFIG_SCOPE_NOT_ALLOWED)
    audits = made.audits
    refused(made, set_value("host", ROUNDS, 1), ErrorCode.CONFIG_SCOPE_NOT_ALLOWED)  # a work key: rolled back
    assert made.audits == audits  # no allowed record of a rolled back command
    updated = made.run(set_value("host", LOG_LEVEL, "error", expected_row_version=1))
    assert (updated.entry.row_version, updated.effective.value) == (2, "error")
    assert allowed_audit(made).target == HOST_TARGET
    refused(made, set_value("host", LOG_LEVEL, "info", expected_row_version=1), ErrorCode.VERSION_CONFLICT)


def test_a_host_write_without_its_right_is_refused_and_audited_as_denied() -> None:
    made = harness(allowed={"config.write"})  # a host write needs config.write_shared
    error = refused(made, set_value("host", LOG_LEVEL, "warning"), ErrorCode.FORBIDDEN)
    assert error.details["permission"] == "config.write_shared"
    [denied] = made.audits
    assert (denied.action, denied.decision, denied.request_id) == (
        "settings.set_value",
        "denied",
        made.request_id,
    )
    assert denied.workspace_id is None
    assert cast("dict[str, Any]", denied.target["scope"]) == {"kind": "host", "id": str(HOST)}
    made.authorizer.allowed = {"config.write", "config.write_shared"}
    assert made.run(set_value("host", LOG_LEVEL, "warning")).changed is True
    assert allowed_audit(made).target == HOST_TARGET


def test_the_allowed_audit_of_a_host_write_follows_the_instance_work_chain_policy() -> None:
    made = harness()
    made.run(set_value("workspace", RECORD_ALLOWED, False))  # a host has no workspace: not its policy
    assert made.run(set_value("project", ROUNDS, 1)).changed is True
    assert [item for item in made.audits if item.request_id == made.request_id] == []
    made.run(set_value("host", LOG_LEVEL, "warning"))
    assert allowed_audit(made).target == HOST_TARGET

    made.run(set_value("instance", RECORD_ALLOWED, False))
    audits = made.audits
    generation = made.generation
    changed = made.run(set_value("host", LOG_LEVEL, "error", expected_row_version=1))
    assert (changed.changed, changed.generation, made.generation) == (True, generation + 1, generation + 1)
    assert made.history[-1].scope_id == HOST
    assert made.audits == audits  # the instance policy turns the allowed record off

    made.run(set_value("instance", RECORD_ALLOWED, True, expected_row_version=1))
    made.run(set_value("host", LOG_LEVEL, "info", expected_row_version=2))
    assert allowed_audit(made).target == HOST_TARGET


def test_pack_values_are_the_narrow_base() -> None:
    made = harness(packs=Packs(PackFragment("overlay", 10, {ROUNDS: 3}, frozenset())))
    assert made.run(set_value("project", ROUNDS, 3)).effective.value == 3
    error = refused(made, set_value("plan", ROUNDS, 4), ErrorCode.CONFIG_NARROWING_VIOLATION)
    assert error.details["ceiling"] == 3
