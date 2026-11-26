"""Internal scope inventory: bounded UUID paging over the current memory UoW snapshot."""

from dataclasses import FrozenInstanceError
from datetime import timedelta
from typing import cast
from uuid import UUID

import pytest

from fakes.app import build_harness
from fakes.clock import FrozenClock
from skm.adapters.memory.core.scopes import MemoryScopeRegistry
from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.ids import ScopeId, WorkspaceId, uuid7
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRegistry


def scope_id(n: int) -> ScopeId:
    return ScopeId(uuid7(1, 0, n))


INSTANCE = scope_id(60)
WORKSPACE = scope_id(20)
PROJECT = scope_id(50)
PLAN = scope_id(10)
RUN = scope_id(40)
HOST = scope_id(30)
WORKSPACE_ID = WorkspaceId(WORKSPACE)
TREE: tuple[tuple[ScopeId, ScopeKind, ScopeId | None, WorkspaceId | None], ...] = (
    (INSTANCE, ScopeKind.INSTANCE, None, None),
    (WORKSPACE, ScopeKind.WORKSPACE, INSTANCE, WORKSPACE_ID),
    (PROJECT, ScopeKind.PROJECT, WORKSPACE, WORKSPACE_ID),
    (PLAN, ScopeKind.PLAN, PROJECT, WORKSPACE_ID),
    (RUN, ScopeKind.RUN, PLAN, WORKSPACE_ID),
    (HOST, ScopeKind.HOST, INSTANCE, None),
)


@pytest.fixture
def state() -> MemoryBackendState:
    state = MemoryBackendState()
    state.core.clock.clock = FrozenClock()
    return state


@pytest.fixture
def scopes(state: MemoryBackendState) -> ScopeRegistry:
    return MemoryScopeRegistry(state)


def seed_tree(scopes: ScopeRegistry) -> None:
    # Parent order deliberately differs from UUID order, with host last.
    for id_, kind, parent, workspace_id in TREE:
        scopes.create(id_, kind, parent=parent, workspace_id=workspace_id)


def test_empty_inventory_is_a_tuple_without_an_instance(scopes: ScopeRegistry) -> None:
    assert scopes.list_scopes() == ()
    assert scopes.list_scopes(after=ScopeId(UUID(int=0)), limit=1) == ()


def test_all_kinds_without_config_or_module_entities_are_inventoried(
    scopes: ScopeRegistry, state: MemoryBackendState
) -> None:
    seed_tree(scopes)
    assert state.core.config_entries == {}
    assert state.modules == {}
    records = scopes.list_scopes()
    assert isinstance(records, tuple)
    assert tuple(record.id for record in records) == (PLAN, WORKSPACE, HOST, RUN, PROJECT, INSTANCE)
    assert {record.kind for record in records} == set(ScopeKind)
    assert records == tuple(scopes.get(id_) for id_ in sorted(row[0] for row in TREE))
    assert tuple(record.id for record in scopes.ancestors(RUN)) == (
        INSTANCE,
        WORKSPACE,
        PROJECT,
        PLAN,
        RUN,
    )
    assert scopes.instance() == scopes.get(INSTANCE)


def test_old_run_remains_visible_after_another_run_is_created(
    scopes: ScopeRegistry, state: MemoryBackendState
) -> None:
    seed_tree(scopes)
    old_run = scopes.get(RUN)
    clock = state.core.clock.clock
    assert isinstance(clock, FrozenClock)
    clock.advance(timedelta(days=365))
    newer_run = scope_id(45)
    scopes.create(newer_run, ScopeKind.RUN, parent=PLAN, workspace_id=WORKSPACE_ID)
    assert scopes.get(newer_run).created_at > old_run.created_at
    runs = tuple(record for record in scopes.list_scopes() if record.kind is ScopeKind.RUN)
    assert runs == (old_run, scopes.get(newer_run))


@pytest.mark.parametrize("limit", [1, 2, 4, 6, 500])
def test_pages_have_no_gaps_or_duplicates_and_use_an_exclusive_cursor(
    scopes: ScopeRegistry, limit: int
) -> None:
    seed_tree(scopes)
    expected = scopes.list_scopes()
    collected: list[ScopeRecord] = []
    after = None
    for _ in range(len(expected) + 1):
        page = scopes.list_scopes(after=after, limit=limit)
        assert len(page) <= limit
        if not page:
            break
        assert all(after is None or record.id > after for record in page)
        collected.extend(page)
        after = page[-1].id
    else:
        pytest.fail("inventory paging did not terminate")
    assert tuple(collected) == expected
    assert scopes.list_scopes(after=expected[-1].id, limit=limit) == ()


@pytest.mark.parametrize("after", [ScopeId(UUID(int=0)), scope_id(25), scope_id(70)])
def test_cursor_is_a_uuid_boundary_even_when_no_row_has_that_id(
    scopes: ScopeRegistry, after: ScopeId
) -> None:
    seed_tree(scopes)
    assert after not in {row[0] for row in TREE}
    expected = tuple(record for record in scopes.list_scopes() if record.id > after)
    assert scopes.list_scopes(after=after) == expected


def test_default_and_maximum_limits_bound_large_inventories(scopes: ScopeRegistry) -> None:
    scopes.create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
    for n in reversed(range(100, 605)):
        scopes.create(scope_id(n), ScopeKind.HOST, parent=INSTANCE, workspace_id=None)
    expected_ids = (INSTANCE, *(scope_id(n) for n in range(100, 605)))
    assert tuple(record.id for record in scopes.list_scopes()) == expected_ids[:100]
    first = scopes.list_scopes(limit=500)
    rest = scopes.list_scopes(after=first[-1].id, limit=500)
    assert len(first) == 500
    assert len(rest) == 6
    assert tuple(record.id for record in (*first, *rest)) == expected_ids


@pytest.mark.parametrize("populated", [False, True])
@pytest.mark.parametrize("limit", [-1, 0, 501])
def test_out_of_range_limits_are_rejected_even_when_empty(
    scopes: ScopeRegistry, populated: bool, limit: int
) -> None:
    if populated:
        seed_tree(scopes)
    with pytest.raises(ValueError, match="page limit"):
        scopes.list_scopes(limit=limit)


@pytest.mark.parametrize("limit", [True, False, 1.0, "100", None, [], {}])
def test_limits_require_an_integer_excluding_bool(scopes: ScopeRegistry, limit: object) -> None:
    with pytest.raises(TypeError, match="page limit"):
        scopes.list_scopes(limit=cast(int, limit))


@pytest.mark.parametrize("populated", [False, True])
@pytest.mark.parametrize("after", ["", str(WORKSPACE), WORKSPACE.bytes, 0, True, [], {}])
def test_cursors_require_uuid_objects_even_when_empty(
    scopes: ScopeRegistry, populated: bool, after: object
) -> None:
    if populated:
        seed_tree(scopes)
    with pytest.raises(TypeError, match="UUID"):
        scopes.list_scopes(after=cast(ScopeId, after))


def test_returned_pages_are_immutable_and_later_reads_see_current_writes(scopes: ScopeRegistry) -> None:
    seed_tree(scopes)
    before = scopes.list_scopes()
    with pytest.raises(FrozenInstanceError):
        before[0].kind = ScopeKind.HOST  # type: ignore[misc]
    added = scope_id(35)
    scopes.create(added, ScopeKind.HOST, parent=INSTANCE, workspace_id=None)
    assert len(before) == 6
    assert added not in {record.id for record in before}
    assert tuple(record.id for record in scopes.list_scopes(after=HOST, limit=2)) == (added, RUN)


@pytest.mark.parametrize("commit", [False, True])
def test_inventory_uses_the_current_uow_and_respects_commit_or_rollback(commit: bool) -> None:
    h = build_harness()
    added = scope_id(100)
    with h.uow_factory(h.meta()) as uow:
        scopes = uow.repo(ScopeRegistry)
        before = scopes.list_scopes()
        scopes.create(
            added, ScopeKind.PROJECT, parent=ScopeId(h.seed.workspace_id), workspace_id=h.seed.workspace_id
        )
        added_record = scopes.get(added)
        assert added_record in scopes.list_scopes()
        assert added not in h.backend.committed.core.scopes
        if commit:
            uow.commit()
    committed = h.backend.committed
    with h.uow_factory(h.meta(), readonly=True) as uow:
        records = uow.repo(ScopeRegistry).list_scopes()
        expected = tuple(sorted((*before, added_record), key=lambda record: record.id)) if commit else before
        assert records == expected
        assert (added in {record.id for record in records}) is commit
        uow.commit()
    assert h.backend.committed is committed


def test_readonly_inventory_keeps_the_uow_snapshot_when_backing_state_changes() -> None:
    h = build_harness()
    added = scope_id(100)
    with h.uow_factory(h.meta(), readonly=True) as uow:
        scopes = uow.repo(ScopeRegistry)
        before = scopes.list_scopes()
        # Change only the backing state to distinguish it from the UoW's already-open snapshot.
        MemoryScopeRegistry(h.backend.committed).create(
            added, ScopeKind.PROJECT, parent=ScopeId(h.seed.workspace_id), workspace_id=h.seed.workspace_id
        )
        assert scopes.list_scopes() == before
    with h.uow_factory(h.meta(), readonly=True) as uow:
        assert added in {record.id for record in uow.repo(ScopeRegistry).list_scopes()}
