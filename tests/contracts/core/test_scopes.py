"""Scope lineage contract of ``ScopeRegistry`` / ``ScopeTree`` (kernel-platform §2.10, adapters §1.1).

Runs against the memory adapter; ``tests/integration/postgres/test_core_constraints.py`` repeats the
same table of rejected shapes against ``skm_core.scopes`` itself, so both backends refuse the same lineages.
"""

from itertools import product

import pytest

from fakes.clock import FrozenClock
from skm.adapters.memory.core.scopes import MemoryScopeRegistry, MemoryScopeTree
from skm.adapters.memory.core.state import MemoryBackendState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import ScopeId, WorkspaceId, uuid7
from skm.kernel.scopes import ALLOWED_PARENTS, ScopeKind
from skm.platform.config.keys import Chain, Level
from skm.platform.config.scopes import ScopeRef


def sid(n: int) -> ScopeId:
    return ScopeId(uuid7(1, 0, n))


INSTANCE, WS_A, WS_B, PROJECT_A, PLAN_A, RUN_A, HOST = (sid(n) for n in (1, 2, 3, 4, 5, 6, 7))
WSID_A, WSID_B = WorkspaceId(WS_A), WorkspaceId(WS_B)


@pytest.fixture
def registry() -> MemoryScopeRegistry:
    state = MemoryBackendState()
    state.core.clock.clock = FrozenClock()
    return MemoryScopeRegistry(state)


@pytest.fixture
def seeded(registry: MemoryScopeRegistry) -> MemoryScopeRegistry:
    registry.create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
    registry.create(WS_A, ScopeKind.WORKSPACE, parent=INSTANCE, workspace_id=WSID_A)
    registry.create(WS_B, ScopeKind.WORKSPACE, parent=INSTANCE, workspace_id=WSID_B)
    registry.create(PROJECT_A, ScopeKind.PROJECT, parent=WS_A, workspace_id=WSID_A)
    registry.create(PLAN_A, ScopeKind.PLAN, parent=PROJECT_A, workspace_id=WSID_A)
    registry.create(RUN_A, ScopeKind.RUN, parent=PLAN_A, workspace_id=WSID_A)
    registry.create(HOST, ScopeKind.HOST, parent=INSTANCE, workspace_id=None)
    return registry


PARENT_OF_KIND: dict[ScopeKind, ScopeId] = {
    ScopeKind.INSTANCE: INSTANCE,
    ScopeKind.WORKSPACE: WS_A,
    ScopeKind.PROJECT: PROJECT_A,
    ScopeKind.PLAN: PLAN_A,
    ScopeKind.RUN: RUN_A,
    ScopeKind.HOST: HOST,
}


_IN_WORKSPACE = {ScopeKind.PROJECT, ScopeKind.PLAN, ScopeKind.RUN}


def _workspace_for(kind: ScopeKind, scope_id: ScopeId) -> WorkspaceId | None:
    if kind is ScopeKind.WORKSPACE:
        return WorkspaceId(scope_id)
    return WSID_A if kind in _IN_WORKSPACE else None


def test_instance_id_is_chosen_by_the_caller(registry: MemoryScopeRegistry) -> None:
    # Single-instance is a property of the table, not a hard-coded id (init supplies the id from bootstrap).
    chosen = sid(900)
    registry.create(chosen, ScopeKind.INSTANCE, parent=None, workspace_id=None)
    assert registry.instance().id == chosen


def test_every_kind_accepts_exactly_its_parent_kind(seeded: MemoryScopeRegistry) -> None:
    for n, kind in enumerate(k for k in ScopeKind if k is not ScopeKind.INSTANCE):
        for i, parent_kind in enumerate(ALLOWED_PARENTS[kind]):
            assert parent_kind is not None
            parent = PARENT_OF_KIND[parent_kind]
            new = sid(100 + 2 * n + i)
            seeded.create(new, kind, parent=parent, workspace_id=_workspace_for(kind, new))
            assert seeded.get(new).parent_id == parent


@pytest.mark.parametrize(
    ("kind", "parent_kind"),
    [
        (kind, parent_kind)
        for kind, parent_kind in product((k for k in ScopeKind if k is not ScopeKind.INSTANCE), ScopeKind)
        if parent_kind not in ALLOWED_PARENTS[kind]
    ],
)
def test_a_parent_of_another_kind_is_rejected(
    seeded: MemoryScopeRegistry, kind: ScopeKind, parent_kind: ScopeKind
) -> None:
    new = sid(200)
    with pytest.raises(ValidationFailed) as caught:
        seeded.create(new, kind, parent=PARENT_OF_KIND[parent_kind], workspace_id=_workspace_for(kind, new))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    with pytest.raises(NotFound):
        seeded.get(new)


@pytest.mark.parametrize("kind", [k for k in ScopeKind if k is not ScopeKind.INSTANCE])
def test_a_scope_without_a_parent_is_rejected(seeded: MemoryScopeRegistry, kind: ScopeKind) -> None:
    new = sid(201)
    with pytest.raises(ValidationFailed) as caught:
        seeded.create(new, kind, parent=None, workspace_id=_workspace_for(kind, new))
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_the_instance_cannot_have_a_parent(seeded: MemoryScopeRegistry) -> None:
    with pytest.raises(ValidationFailed) as caught:
        seeded.create(sid(202), ScopeKind.INSTANCE, parent=INSTANCE, workspace_id=None)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_an_unknown_parent_is_not_found(seeded: MemoryScopeRegistry) -> None:
    with pytest.raises(NotFound):
        seeded.create(sid(203), ScopeKind.PROJECT, parent=sid(999), workspace_id=WSID_A)


@pytest.mark.parametrize(
    ("kind", "parent", "workspace_id"),
    [
        pytest.param(ScopeKind.PROJECT, WS_A, WSID_B, id="project-in-a-foreign-workspace"),
        pytest.param(ScopeKind.PLAN, PROJECT_A, WSID_B, id="plan-in-a-foreign-workspace"),
        pytest.param(ScopeKind.RUN, PLAN_A, WSID_B, id="run-in-a-foreign-workspace"),
        pytest.param(ScopeKind.PROJECT, WS_A, None, id="project-without-workspace"),
        pytest.param(ScopeKind.RUN, PLAN_A, None, id="run-without-workspace"),
        pytest.param(ScopeKind.WORKSPACE, INSTANCE, None, id="workspace-without-itself"),
        pytest.param(ScopeKind.WORKSPACE, INSTANCE, WSID_A, id="workspace-pointing-at-another-workspace"),
        pytest.param(ScopeKind.HOST, INSTANCE, WSID_A, id="host-with-workspace"),
    ],
)
def test_the_workspace_must_match_the_lineage(
    seeded: MemoryScopeRegistry, kind: ScopeKind, parent: ScopeId, workspace_id: WorkspaceId | None
) -> None:
    new = sid(204)
    with pytest.raises(ValidationFailed) as caught:
        seeded.create(new, kind, parent=parent, workspace_id=workspace_id)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert dict(caught.value.details)["field"] == "workspace_id"
    with pytest.raises(NotFound):
        seeded.get(new)


def test_the_instance_row_cannot_carry_a_workspace(registry: MemoryScopeRegistry) -> None:
    with pytest.raises(ValidationFailed) as caught:
        registry.create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=WSID_A)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID


def test_a_second_instance_is_rejected(seeded: MemoryScopeRegistry) -> None:
    with pytest.raises(Conflict) as caught:
        seeded.create(sid(300), ScopeKind.INSTANCE, parent=None, workspace_id=None)
    assert caught.value.code is ErrorCode.ALREADY_EXISTS
    assert seeded.instance().id == INSTANCE


def test_a_duplicate_id_is_rejected_and_keeps_the_stored_row(seeded: MemoryScopeRegistry) -> None:
    before = seeded.get(PROJECT_A)
    with pytest.raises(Conflict) as caught:
        seeded.create(PROJECT_A, ScopeKind.PROJECT, parent=WS_B, workspace_id=WSID_B)
    assert caught.value.code is ErrorCode.ALREADY_EXISTS
    assert seeded.get(PROJECT_A) == before


def test_instance_is_not_found_before_init(registry: MemoryScopeRegistry) -> None:
    with pytest.raises(NotFound):
        registry.instance()


def test_ancestors_are_ordered_from_the_instance(seeded: MemoryScopeRegistry) -> None:
    assert [r.id for r in seeded.ancestors(RUN_A)] == [INSTANCE, WS_A, PROJECT_A, PLAN_A, RUN_A]
    assert [r.id for r in seeded.ancestors(HOST)] == [INSTANCE, HOST]
    assert [r.id for r in seeded.ancestors(INSTANCE)] == [INSTANCE]
    with pytest.raises(NotFound):
        seeded.ancestors(sid(999))


# --- ScopeTree ----------------------------------------------------------------------------------------------


def _ref(level: Level, scope_id: ScopeId) -> ScopeRef:
    return ScopeRef(level, scope_id)


@pytest.fixture
def tree() -> MemoryScopeTree:
    state = MemoryBackendState()
    state.core.clock.clock = FrozenClock()
    registry = MemoryScopeRegistry(state)
    registry.create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
    registry.create(WS_A, ScopeKind.WORKSPACE, parent=INSTANCE, workspace_id=WSID_A)
    registry.create(PROJECT_A, ScopeKind.PROJECT, parent=WS_A, workspace_id=WSID_A)
    registry.create(RUN_A, ScopeKind.RUN, parent=PROJECT_A, workspace_id=WSID_A)
    registry.create(HOST, ScopeKind.HOST, parent=INSTANCE, workspace_id=None)
    return MemoryScopeTree(state)


def test_tree_work_chain_and_host_chain(tree: MemoryScopeTree) -> None:
    assert tree.instance_scope().scope_id == INSTANCE
    work = tree.chain_for(_ref(Level.PROJECT, PROJECT_A), Chain.WORK)
    assert [s.scope_id for s in work.scopes] == [INSTANCE, WS_A, PROJECT_A]
    host = tree.chain_for(_ref(Level.HOST, HOST), Chain.HOST)
    assert [s.scope_id for s in host.scopes] == [INSTANCE, HOST]
    assert [s.scope_id for s in tree.chain_for(_ref(Level.INSTANCE, INSTANCE), Chain.HOST).scopes] == [
        INSTANCE
    ]


def test_project_owned_run_has_no_plan_config_layer(tree: MemoryScopeTree) -> None:
    work = tree.chain_for(_ref(Level.RUN, RUN_A), Chain.WORK)
    assert [s.scope_id for s in work.scopes] == [INSTANCE, WS_A, PROJECT_A, RUN_A]


def test_tree_rejects_a_host_in_the_work_chain_and_a_project_in_the_host_chain(tree: MemoryScopeTree) -> None:
    with pytest.raises(ValidationFailed) as caught:
        tree.chain_for(_ref(Level.HOST, HOST), Chain.WORK)
    assert caught.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    with pytest.raises(ValidationFailed) as caught:
        tree.chain_for(_ref(Level.PROJECT, PROJECT_A), Chain.HOST)
    assert caught.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED


def test_tree_rejects_a_level_that_is_not_the_stored_kind(tree: MemoryScopeTree) -> None:
    with pytest.raises(ValidationFailed) as caught:
        tree.chain_for(_ref(Level.WORKSPACE, PROJECT_A), Chain.WORK)
    assert caught.value.code is ErrorCode.INVALID_REFERENCE
