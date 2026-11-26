"""``ConfigLoader`` over the memory ``ConfigStore``/``ScopeTree`` of a unit of work (settings §B.10, §B.13).

Invariants: chains come from the scope tree of the caller's transaction; the shared cache holds only committed
configuration (own uncommitted writes are visible, a rollback leaves nothing behind, a generation that moves
while reading is not cached); every cache key component (chain, generation, pack generation, invocation,
frozen digest, process) separates results; restart values are captured once from committed configuration and
applied only to their own instance/host. Ported scenarios: aicore ``test_model`` (layers listed in order,
missing key falls through, unset restores the default), orch ``test_authority_monotonic`` (a nearer level
cannot weaken a floor, current revocation reaches a frozen run).
"""

import threading
from collections.abc import Iterator, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from runpy import run_path
from typing import Any, cast
from uuid import UUID, uuid4

import pytest

from fakes.clock import FrozenClock
from fakes.demo_module import SCHEMA_ROOT
from fakes.ids import SequentialIds
from skm.adapters.memory.config_store import (
    MemoryConfigStore,
    delete_config_entry,
    increment_config_generation,
    write_config_entry,
)
from skm.adapters.memory.core import REPOSITORIES
from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.uow import InMemoryBackend, InMemoryUnitOfWork
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.kernel.scopes import ScopeRef as KernelScopeRef
from skm.platform.config import effective as effective_module
from skm.platform.config.effective import EffectiveConfig
from skm.platform.config.keys import Chain, Level
from skm.platform.config.layers import Contribution, Layer, LayerRef
from skm.platform.config.loader import ConfigLoader, ProcessConfig
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.scopes import ScopeChain, ScopeRef
from skm.platform.config.sources.packs import PackFragment
from skm.platform.config.store import (
    ConfigStore,
    EmptyPackConfigSource,
    ScopeTree,
    StoredContribution,
)
from skm.platform.schema.registry import SchemaRegistry

h = run_path(str(Path(__file__).with_name("test_frozen.py")))
leaf = h["leaf"]

PROPERTIES: dict[str, Any] = {
    **h["PROPERTIES"],
    "tags": leaf({"type": "array", "items": {"type": "string"}}, default=[]),
    "dir": leaf({"type": "string"}, path=True),
    "mode": leaf({"type": "string"}, default="file", override=True),
    "host_size": leaf({"type": "integer"}, default=1, chain="host", levels=["instance", "host"]),
}

INSTANCE = ScopeId(UUID("01900000-0000-7000-8000-000000000001"))
WORKSPACE = ScopeId(UUID("01900000-0000-7000-8000-0000000000a1"))
PROJECT = ScopeId(UUID("01900000-0000-7000-8000-0000000000c1"))
PLAN = ScopeId(UUID("01900000-0000-7000-8000-0000000000d1"))
RUN = ScopeId(UUID("01900000-0000-7000-8000-0000000000e1"))
HOST = ScopeId(UUID("01900000-0000-7000-8000-0000000000f1"))
OTHER_HOST = ScopeId(UUID("01900000-0000-7000-8000-0000000000f2"))
LEVEL_IDS = {
    Level.INSTANCE: INSTANCE,
    Level.WORKSPACE: WORKSPACE,
    Level.PROJECT: PROJECT,
    Level.PLAN: PLAN,
    Level.RUN: RUN,
    Level.HOST: HOST,
}


def ref(level: Level, scope_id: UUID | None = None) -> ScopeRef:
    return ScopeRef(level, scope_id or LEVEL_IDS[level])


# ---------------------------------------------------------------------------------------------------------
# A memory backend with the real config store and a test-only writer port


class ConfigWrites:
    """Test-only repository port: writes the memory config tables of the current unit of work."""

    def __init__(self, state: MemoryBackendState) -> None:
        self.state = state

    def put(
        self, level: Level, key: str, value: JsonValue = None, *, op: str = "set", locked: bool = False
    ) -> None:
        scope_id = LEVEL_IDS[level]
        rows = self.state.core.config_entries.get(scope_id, {})
        version = cast("int", rows[key]["row_version"]) + 1 if key in rows else 1
        entry = StoredContribution(uuid4(), key, cast("Any", op), value, locked, version)
        write_config_entry(self.state, scope_id, entry)

    def drop(self, level: Level, key: str) -> None:
        delete_config_entry(self.state, LEVEL_IDS[level], key)

    def bump(self) -> int:
        return increment_config_generation(self.state)


def _meta() -> RequestMeta:
    return RequestMeta(
        request_id="req_" + "0" * 26,
        surface=Surface.TEST,
        idempotency_key=None,
        received_at=datetime(2026, 1, 1, tzinfo=UTC),
    )


class Store:
    """One memory backend: committed state, scopes and helpers around units of work."""

    def __init__(self, instance: ScopeId = INSTANCE) -> None:
        factories: dict[type, Any] = {
            **REPOSITORIES,
            ConfigStore: MemoryConfigStore,
            ConfigWrites: ConfigWrites,
        }
        self.backend = InMemoryBackend(
            factories=factories,
            schemas=SchemaRegistry.load(SCHEMA_ROOT),
            subscriptions={},
            ids=SequentialIds(),
            clock=FrozenClock(),
        )
        with self.uow() as uow:
            scopes = uow.repo(ScopeRegistry)
            scopes.create(instance, ScopeKind.INSTANCE, parent=None, workspace_id=None)
            scopes.create(
                WORKSPACE, ScopeKind.WORKSPACE, parent=instance, workspace_id=WorkspaceId(WORKSPACE)
            )
            scopes.create(PROJECT, ScopeKind.PROJECT, parent=WORKSPACE, workspace_id=WorkspaceId(WORKSPACE))
            scopes.create(PLAN, ScopeKind.PLAN, parent=PROJECT, workspace_id=WorkspaceId(WORKSPACE))
            scopes.create(RUN, ScopeKind.RUN, parent=PLAN, workspace_id=WorkspaceId(WORKSPACE))
            scopes.create(HOST, ScopeKind.HOST, parent=instance, workspace_id=None)
            scopes.create(OTHER_HOST, ScopeKind.HOST, parent=instance, workspace_id=None)
            uow.commit()

    @contextmanager
    def uow(self, *, readonly: bool = False) -> Iterator[InMemoryUnitOfWork]:
        with self.backend.uow_factory()(_meta(), readonly=readonly) as uow:
            yield uow

    def commit(self, *writes: tuple[Any, ...]) -> int:
        """Write ``(level, key, value[, op[, locked]])`` rows and increment the generation in one commit."""
        with self.uow() as uow:
            port = uow.repo(ConfigWrites)
            for level, key, value, *rest in writes:
                port.put(level, key, value, op=rest[0] if rest else "set", locked=len(rest) > 1 and rest[1])
            generation = port.bump()
            uow.commit()
        return generation

    def read(
        self,
        loader: ConfigLoader,
        scope: ScopeRef | KernelScopeRef | None = None,
        kind: Chain = Chain.WORK,
        **kwargs: Any,
    ) -> EffectiveConfig:
        with self.uow(readonly=True) as uow:
            return loader.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), scope, kind, **kwargs)


@pytest.fixture(scope="module")
def registry(tmp_path_factory: pytest.TempPathFactory) -> SettingsRegistry:
    return h["build_registry"](tmp_path_factory.mktemp("loader"), PROPERTIES)


@pytest.fixture
def store() -> Store:
    return Store()


def loader_of(registry: SettingsRegistry, **kwargs: Any) -> ConfigLoader:
    return ConfigLoader(registry, kwargs.pop("packs", EmptyPackConfigSource()), **kwargs)


# ---------------------------------------------------------------------------------------------------------
# Chains from the scope tree


def test_run_chain_is_built_from_the_scope_tree_with_stored_provenance(registry, store) -> None:
    store.commit(
        (Level.INSTANCE, "demo.rounds", 3),
        (Level.WORKSPACE, "demo.note", "from workspace"),
        (Level.PROJECT, "demo.rounds", None, "unset"),
        (Level.PLAN, "demo.tags", ["a"]),
        (Level.RUN, "demo.tags", ["b"], "append"),
    )
    effective = store.read(loader_of(registry), ref(Level.RUN))
    chain = effective.chain
    assert chain.kind is Chain.WORK
    assert [scope.level for scope in chain.scopes] == [
        Level.INSTANCE,
        Level.WORKSPACE,
        Level.PROJECT,
        Level.PLAN,
        Level.RUN,
    ]
    assert chain.ids() == (INSTANCE, WORKSPACE, PROJECT, PLAN, RUN)
    assert [scope.label for scope in chain.scopes][:2] == ["instance", f"workspace:{WORKSPACE}"]
    assert effective.generation == 1
    assert effective.pack_generation == 0
    assert effective.get("demo.rounds") == 2  # the project unset restores the default (§B.5.2)
    assert effective.get("demo.note") == "from workspace"  # a missing key falls through
    assert effective.get("demo.tags") == ["a", "b"]
    winner = effective.provenance("demo.tags").winner
    assert winner is not None
    assert (winner.level, winner.scope_id, winner.row_version) == (Level.RUN, RUN, 1)
    assert winner.entry_id is not None
    assert winner.label == f"run:{RUN}"
    levels = [item.contribution.layer.level for item in effective.provenance("demo.rounds").trace]
    assert levels == [Level.DEFAULT, Level.INSTANCE, Level.PROJECT]  # layers in order, farthest first


def test_none_and_bus_scope_refs_resolve_the_same_chains(registry, store) -> None:
    loader = loader_of(registry)
    assert store.read(loader, None).chain.ids() == (INSTANCE,)
    kernel = store.read(loader, KernelScopeRef(kind=ScopeKind.PROJECT, id=PROJECT))
    assert kernel is store.read(loader, ref(Level.PROJECT))  # one cache entry for both spellings


def test_host_chain_is_separate_and_misplaced_scopes_are_refused(registry, store) -> None:
    store.commit((Level.HOST, "demo.host_size", 4), (Level.INSTANCE, "demo.host_size", 2))
    loader = loader_of(registry)
    with store.uow(readonly=True) as uow:
        host = loader.effective_host(uow.repo(ConfigStore), uow.repo(ScopeTree), ref(Level.HOST))
    assert host.chain == ScopeChain(Chain.HOST, (ref(Level.INSTANCE), ref(Level.HOST)))
    assert host.get("demo.host_size") == 4
    assert store.read(loader, None, Chain.HOST).get("demo.host_size") == 2  # (instance) host chain
    assert store.read(loader, ref(Level.HOST, OTHER_HOST), Chain.HOST).get("demo.host_size") == 2
    with pytest.raises(ValidationFailed) as host_in_work:
        store.read(loader, ref(Level.HOST))
    assert host_in_work.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    with pytest.raises(ValidationFailed) as work_in_host:
        store.read(loader, ref(Level.WORKSPACE), Chain.HOST)
    assert work_in_host.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    with pytest.raises(ValidationFailed) as wrong_kind:
        store.read(loader, ref(Level.PROJECT, WORKSPACE))
    assert wrong_kind.value.code is ErrorCode.INVALID_REFERENCE


def test_a_bus_host_scope_ref_selects_the_host_chain(registry, store) -> None:
    """``scope_of(cmd)`` of a host-scoped operation is a kernel host ref passed without a chain kind."""
    store.commit((Level.HOST, "demo.host_size", 4), (Level.INSTANCE, "demo.host_size", 2))
    loader = loader_of(registry)
    bus_host = store.read(loader, KernelScopeRef(kind=ScopeKind.HOST, id=HOST))
    assert bus_host.chain == ScopeChain(Chain.HOST, (ref(Level.INSTANCE), ref(Level.HOST)))
    assert bus_host.get("demo.host_size") == 4
    with store.uow(readonly=True) as uow:
        direct = loader.effective_host(uow.repo(ConfigStore), uow.repo(ScopeTree), ref(Level.HOST))
    assert direct is bus_host  # one host cache entry for both spellings
    other = store.read(loader, KernelScopeRef(kind=ScopeKind.HOST, id=OTHER_HOST))
    assert other.chain.ids() == (INSTANCE, OTHER_HOST)
    assert other.get("demo.host_size") == 2  # the target host's own values, not another host's
    work = store.read(loader, None)
    assert work.chain.kind is Chain.WORK
    assert work is not bus_host
    # The config spelling keeps its explicit chain: host in the work chain stays refused.
    with pytest.raises(ValidationFailed) as host_in_work:
        store.read(loader, ref(Level.HOST))
    assert host_in_work.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    # A kernel work scope still follows the requested kind: workspace in the host chain stays refused.
    with pytest.raises(ValidationFailed) as work_in_host:
        store.read(loader, KernelScopeRef(kind=ScopeKind.WORKSPACE, id=WORKSPACE), Chain.HOST)
    assert work_in_host.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    # A host ref naming a work scope is an invalid reference, not a host chain of that scope.
    with pytest.raises(ValidationFailed) as not_a_host:
        store.read(loader, KernelScopeRef(kind=ScopeKind.HOST, id=WORKSPACE))
    assert not_a_host.value.code is ErrorCode.INVALID_REFERENCE


def test_process_values_reach_the_bus_host_chain_of_the_captured_host_only(registry, store) -> None:
    store.commit((Level.HOST, "demo.host_restart", "h1"))
    loader = loader_of(registry)
    with store.uow(readonly=True) as uow:
        loader.start_process(
            uow.repo(ConfigStore), uow.repo(ScopeTree), KernelScopeRef(kind=ScopeKind.HOST, id=HOST)
        )
    store.commit((Level.HOST, "demo.host_restart", "h2"))
    host = store.read(loader, KernelScopeRef(kind=ScopeKind.HOST, id=HOST))
    assert host.get("demo.host_restart") == "h1"
    assert host.provenance("demo.host_restart").winner == LayerRef(Level.PROCESS)
    other = store.read(loader, KernelScopeRef(kind=ScopeKind.HOST, id=OTHER_HOST))
    assert other.get("demo.host_restart") == "host-original"
    assert not other.diagnostics


def test_a_scope_tree_that_answers_another_chain_fails_closed(registry, store) -> None:
    class Lying:
        def __init__(self, tree: ScopeTree) -> None:
            self.tree = tree

        def instance_scope(self) -> ScopeRef:
            return self.tree.instance_scope()

        def chain_for(self, scope: ScopeRef, kind: Chain) -> ScopeChain:
            return self.tree.chain_for(ref(Level.WORKSPACE), kind)

        def label(self, scope: ScopeRef) -> str:
            return ""

    with store.uow(readonly=True) as uow, pytest.raises(InternalError):
        loader_of(registry).effective(uow.repo(ConfigStore), Lying(uow.repo(ScopeTree)), ref(Level.PROJECT))


# ---------------------------------------------------------------------------------------------------------
# Generation cache


def test_cache_hits_within_a_generation_and_misses_after_a_commit(registry, store) -> None:
    store.commit((Level.WORKSPACE, "demo.rounds", 4))
    loader = loader_of(registry)
    first = store.read(loader, ref(Level.WORKSPACE))
    assert store.read(loader, ref(Level.WORKSPACE)) is first
    store.commit((Level.WORKSPACE, "demo.rounds", 5))
    second = store.read(loader, ref(Level.WORKSPACE))
    assert second is not first
    assert (second.generation, second.get("demo.rounds")) == (2, 5)
    assert first.get("demo.rounds") == 4  # a published snapshot never changes


def test_two_independent_loaders_see_the_new_generation_after_commit(registry, store) -> None:
    one, two = loader_of(registry), loader_of(registry)
    assert store.read(one).get("demo.rounds") == store.read(two).get("demo.rounds") == 2
    with store.uow() as uow:
        uow.repo(ConfigWrites).put(Level.INSTANCE, "demo.rounds", 8)
        uow.repo(ConfigWrites).bump()
        uow.commit()
    for loader in (one, two):
        current = store.read(loader)
        assert (current.generation, current.get("demo.rounds")) == (1, 8)


def test_pack_generation_and_fragments_are_part_of_the_key(registry, store) -> None:
    class Packs:
        def __init__(self) -> None:
            self.gen = 0
            self.items: tuple[PackFragment, ...] = ()
            self.chains: list[ScopeChain] = []

        def generation(self) -> int:
            return self.gen

        def fragments(self, scope_chain: ScopeChain) -> tuple[PackFragment, ...]:
            self.chains.append(scope_chain)
            return self.items

    packs = Packs()
    loader = loader_of(registry, packs=packs)
    assert store.read(loader, ref(Level.PROJECT)).get("demo.rounds") == 2
    packs.gen, packs.items = 1, (PackFragment("core", 10, {"demo.rounds": 6}),)
    effective = store.read(loader, ref(Level.PROJECT))
    assert (effective.pack_generation, effective.get("demo.rounds")) == (1, 6)
    assert effective.provenance("demo.rounds").winner == LayerRef(
        Level.PACK, pack_id="core", pack_priority=10
    )
    assert packs.chains[-1].ids() == (INSTANCE, WORKSPACE, PROJECT)


def test_empty_pack_source_is_explicit() -> None:
    packs = EmptyPackConfigSource()
    chain = ScopeChain(Chain.WORK, (ref(Level.INSTANCE),))
    assert (packs.generation(), packs.fragments(chain)) == (0, ())


def test_invocation_layers_and_path_expansion_apply(registry, store) -> None:
    store.commit((Level.INSTANCE, "demo.dir", "~/state"))
    at = LayerRef(Level.INVOCATION, label="--set", source="cli")
    loader = loader_of(
        registry,
        invocation=(
            Layer(
                at, {"demo.mode": Contribution(at, "set", "cli"), "demo.note": Contribution(at, "set", "x")}
            ),
        ),
        expand_path=lambda value: value.replace("~", "/home/u"),
    )
    effective = store.read(loader)
    assert effective.get("demo.mode") == "cli"
    assert effective.get("demo.note") is None  # override = false: invocation does not apply
    assert effective.get("demo.dir") == "/home/u/state"
    with pytest.raises(ValueError, match="invocation"):
        ConfigLoader(registry, EmptyPackConfigSource(), [Layer(LayerRef(Level.DEFAULT), {})])


def test_cache_is_a_bounded_lru(registry, store) -> None:
    loader = loader_of(registry, cache_size=1)
    workspace = store.read(loader, ref(Level.WORKSPACE))
    assert store.read(loader, ref(Level.WORKSPACE)) is workspace
    store.read(loader, ref(Level.RUN))
    assert store.read(loader, ref(Level.WORKSPACE)) is not workspace
    uncached = loader_of(registry, cache_size=0)
    assert store.read(uncached) is not store.read(uncached)
    with pytest.raises(ValueError, match="cache_size"):
        loader_of(registry, cache_size=-1)


def test_a_generation_that_moves_while_reading_is_not_cached(registry, store) -> None:
    class Moving:
        """A concurrent commit between the reads of one ``effective`` call."""

        def __init__(self, inner: ConfigStore) -> None:
            self.inner = inner
            self.calls = 0

        def generation(self) -> int:
            self.calls += 1
            return self.inner.generation() + self.calls

        def pending_writes(self) -> bool:
            return False

        def entries_for(self, scope_ids: Sequence[UUID]) -> Mapping[UUID, Mapping[str, StoredContribution]]:
            return self.inner.entries_for(scope_ids)

    loader = loader_of(registry)
    with store.uow(readonly=True) as uow:
        moving = Moving(uow.repo(ConfigStore))
        first = loader.effective(moving, uow.repo(ScopeTree), None)
        moving.calls = 0
        assert loader.effective(moving, uow.repo(ScopeTree), None) is not first


# ---------------------------------------------------------------------------------------------------------
# Uncommitted writes: own writes visible, rollback leaves the cache clean


def _in_transaction_then_rollback(
    store: Store, loader: ConfigLoader, *, store_first: bool
) -> EffectiveConfig:
    with store.uow() as uow:
        if store_first:  # the bus creates the store in load_config, before the handler writes
            uow.repo(ConfigStore)
        writes = uow.repo(ConfigWrites)
        writes.put(Level.WORKSPACE, "demo.rounds", 7)
        writes.bump()
        config_store = uow.repo(ConfigStore)
        assert config_store.pending_writes()
        own = loader.effective(config_store, uow.repo(ScopeTree), ref(Level.WORKSPACE))
        uow.rollback()
    return own


@pytest.mark.parametrize("store_first", [True, False])
def test_own_writes_are_visible_and_a_rollback_does_not_poison_the_cache(
    registry, store, store_first
) -> None:
    loader = loader_of(registry)
    before = store.read(loader, ref(Level.WORKSPACE))
    own = _in_transaction_then_rollback(store, loader, store_first=store_first)
    assert (own.generation, own.get("demo.rounds")) == (1, 7)  # settings preview sees its own write
    assert store.read(loader, ref(Level.WORKSPACE)) is before  # rolled back: generation 0 again
    store.commit((Level.WORKSPACE, "demo.rounds", 9))  # the same generation number, other content
    after = store.read(loader, ref(Level.WORKSPACE))
    assert (after.generation, after.get("demo.rounds")) == (1, 9)


def test_without_pending_detection_the_rollback_would_poison_the_cache(registry, store) -> None:
    """Negative example: the guard above is what protects the shared cache."""

    class Blind:
        def __init__(self, inner: ConfigStore) -> None:
            self.inner = inner

        def generation(self) -> int:
            return self.inner.generation()

        def pending_writes(self) -> bool:
            return False

        def entries_for(self, scope_ids: Sequence[UUID]) -> Mapping[UUID, Mapping[str, StoredContribution]]:
            return self.inner.entries_for(scope_ids)

    loader = loader_of(registry)
    with store.uow() as uow:
        uow.repo(ConfigWrites).put(Level.WORKSPACE, "demo.rounds", 7)
        uow.repo(ConfigWrites).bump()
        loader.effective(Blind(uow.repo(ConfigStore)), uow.repo(ScopeTree), ref(Level.WORKSPACE))
        uow.rollback()
    store.commit((Level.WORKSPACE, "demo.rounds", 9))
    assert store.read(loader, ref(Level.WORKSPACE)).get("demo.rounds") == 7  # poisoned


def test_memory_store_reports_pending_writes_of_its_unit_of_work(store) -> None:
    with store.uow(readonly=True) as uow:
        assert not uow.repo(ConfigStore).pending_writes()
    with store.uow() as uow:
        config_store = uow.repo(ConfigStore)
        assert not config_store.pending_writes()
        uow.repo(ConfigWrites).drop(Level.WORKSPACE, "demo.absent")  # a writer marks even a no-op
        assert config_store.pending_writes()
        uow.commit()
    with store.uow() as uow:
        config_store = uow.repo(ConfigStore)
        assert not config_store.pending_writes()  # the mark of a committed copy does not carry over
        state = cast("Any", uow)._working
        state.core.config_entries[WORKSPACE] = {}  # a raw write after the store was created
        assert config_store.pending_writes()
    with store.uow(readonly=True) as uow, pytest.raises(RuntimeError, match="readonly"):
        uow.repo(ConfigWrites).bump()


# ---------------------------------------------------------------------------------------------------------
# Stored rows


def test_malformed_or_misfiled_rows_fail_closed(registry, store) -> None:
    loader = loader_of(registry)
    with store.uow() as uow:
        cast("Any", uow)._working.core.config_entries[INSTANCE] = {"demo.rounds": {"op": "set", "value": 3}}
        with pytest.raises(InternalError):
            loader.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None)

    class Misfiled:
        def __init__(self, inner: ConfigStore) -> None:
            self.inner = inner

        def generation(self) -> int:
            return 0

        def pending_writes(self) -> bool:
            return False

        def entries_for(self, scope_ids: Sequence[UUID]) -> Mapping[UUID, Mapping[str, StoredContribution]]:
            return {INSTANCE: {"demo.note": StoredContribution(uuid4(), "demo.rounds", "set", 9, False, 1)}}

    with store.uow(readonly=True) as uow, pytest.raises(InternalError):
        loader.effective(Misfiled(uow.repo(ConfigStore)), uow.repo(ScopeTree), None)
    with pytest.raises(ValueError, match="unset"):
        StoredContribution(uuid4(), "demo.note", "unset", "x", False, 1)
    with pytest.raises(ValueError, match="row_version"):
        StoredContribution(uuid4(), "demo.note", "set", "x", False, 0)


def test_locks_apply_at_lock_levels_and_are_ignored_elsewhere(registry, store) -> None:
    store.commit(
        (Level.INSTANCE, "demo.note", "pinned", "set", True),
        (Level.RUN, "demo.note", "run"),
        (Level.PROJECT, "demo.tags", ["p"], "set", True),
        (Level.RUN, "demo.tags", ["r"]),
    )
    effective = store.read(loader_of(registry), ref(Level.RUN))
    assert effective.get("demo.note") == "pinned"
    assert effective.provenance("demo.note").locked_by == effective.provenance("demo.note").winner
    assert effective.get("demo.tags") == ["r"]  # a project lock is not trusted
    ignored = [d for d in effective.diagnostics if d.details.get("reason") == "lock_level"]
    assert [d.target for d in ignored] == ["demo.tags"]
    assert ignored[0].code == "CONFIG_SCOPE_NOT_ALLOWED"


def test_a_nearer_level_cannot_weaken_a_floor_and_revocation_reaches_frozen_runs(registry, store) -> None:
    store.commit((Level.INSTANCE, "demo.ceiling", 3), (Level.PROJECT, "demo.ceiling", 9))
    loader = loader_of(registry)
    run = store.read(loader, ref(Level.RUN))
    assert run.get("demo.ceiling") == 3
    statuses = [(t.contribution.layer.level, t.status) for t in run.provenance("demo.ceiling").trace]
    assert (Level.PROJECT, "ignored") in statuses
    frozen = run.freeze(registry)
    store.commit((Level.INSTANCE, "demo.ceiling", 1), (Level.INSTANCE, "demo.rounds", 5))
    selected = store.read(loader, ref(Level.RUN), frozen=frozen)
    assert selected.get("demo.rounds") == 2  # run_frozen from the bundle
    assert selected.get("demo.ceiling") == 1  # live revocation applies at once
    assert store.read(loader, ref(Level.RUN)).get("demo.rounds") == 5  # the frozen digest is part of the key
    assert store.read(loader, ref(Level.RUN), frozen=frozen) is selected
    with pytest.raises(ValidationFailed):
        store.read(loader, ref(Level.PLAN), frozen=frozen)
    # Same values and digest, another run: the cached result of this run must not admit it.
    foreign = replace(frozen, run_scope_id=uuid4())
    assert foreign.digest == frozen.digest
    with pytest.raises(ValidationFailed):
        store.read(loader, ref(Level.RUN), frozen=foreign)


# ---------------------------------------------------------------------------------------------------------
# Process restart values


def test_loader_reexports_the_identity_bearing_process_config() -> None:
    assert ProcessConfig is effective_module.ProcessConfig


def test_restart_values_are_captured_once_and_bound_to_their_instance_and_host(registry, store) -> None:
    store.commit((Level.INSTANCE, "demo.restart", "v1"), (Level.HOST, "demo.host_restart", "h1"))
    loader = loader_of(registry)
    assert loader.process is None
    with store.uow(readonly=True) as uow:
        process = loader.start_process(
            uow.repo(ConfigStore), uow.repo(ScopeTree), KernelScopeRef(kind=ScopeKind.HOST, id=HOST)
        )
    assert loader.process is process
    assert (process.instance_scope_id, process.host_target) == (INSTANCE, ref(Level.HOST))
    assert dict(process.work) == {"demo.restart": "v1"}
    assert dict(process.host) == {"demo.host_restart": "h1"}
    store.commit((Level.INSTANCE, "demo.restart", "v2"), (Level.HOST, "demo.host_restart", "h2"))
    current = store.read(loader, ref(Level.PROJECT))
    assert current.get("demo.restart") == "v1"
    assert current.provenance("demo.restart").winner == LayerRef(Level.PROCESS)
    assert [d.code for d in current.diagnostics] == ["CONFIG_RESTART_PENDING"]
    with store.uow(readonly=True) as uow:
        host = loader.effective_host(uow.repo(ConfigStore), uow.repo(ScopeTree), ref(Level.HOST))
        other = loader.effective_host(uow.repo(ConfigStore), uow.repo(ScopeTree), ref(Level.HOST, OTHER_HOST))
        with pytest.raises(InternalError):
            loader.start_process(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
    assert host.get("demo.host_restart") == "h1"
    assert other.get("demo.host_restart") == "host-original"  # another host: current values, no process
    assert not other.diagnostics
    with store.uow(readonly=True) as uow:
        current_host = loader_of(registry).effective_host(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ref(Level.HOST)
        )
    assert current_host.get("demo.host_restart") == "h2"


def test_process_capture_refuses_uncommitted_configuration(registry, store) -> None:
    loader = loader_of(registry)
    with store.uow() as uow:
        uow.repo(ConfigWrites).put(Level.INSTANCE, "demo.restart", "uncommitted")
        with pytest.raises(InternalError):
            loader.start_process(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
    assert loader.process is None


def test_process_values_are_never_applied_to_another_instance(registry, store) -> None:
    loader = loader_of(registry)
    with store.uow(readonly=True) as uow:
        loader.start_process(uow.repo(ConfigStore), uow.repo(ScopeTree), None)
    other = Store(ScopeId(UUID("01900000-0000-7000-8000-000000000099")))
    with pytest.raises(ValidationFailed) as refused:
        other.read(loader)
    assert refused.value.code is ErrorCode.CONFIG_INVALID


# ---------------------------------------------------------------------------------------------------------
# Concurrency


def test_concurrent_readers_and_a_writer_always_see_a_consistent_generation(registry, store) -> None:
    """Instance ``demo.rounds`` equals the generation of every commit; a cached result never mixes them."""
    store.commit((Level.INSTANCE, "demo.rounds", 1))
    loader = loader_of(registry, cache_size=4)
    stop = threading.Event()

    def writer() -> None:
        for _ in range(30):
            with store.uow() as uow:
                writes = uow.repo(ConfigWrites)
                generation = writes.state.core.config_generation + 1
                writes.put(Level.INSTANCE, "demo.rounds", generation)
                writes.bump()
                uow.commit()
        stop.set()

    def reader(scope: ScopeRef) -> list[tuple[int, JsonValue]]:
        seen: list[tuple[int, JsonValue]] = []
        while not stop.is_set() or len(seen) < 5:
            effective = store.read(loader, scope)
            seen.append((effective.generation, effective.get("demo.rounds")))
        return seen

    scopes = [ref(level) for level in (Level.INSTANCE, Level.WORKSPACE, Level.RUN)] * 2
    with ThreadPoolExecutor(max_workers=len(scopes) + 1) as pool:
        readers = [pool.submit(reader, scope) for scope in scopes]
        pool.submit(writer).result()
        observations = [item for future in readers for item in future.result()]
    assert observations
    assert all(generation == rounds for generation, rounds in observations)
    assert store.read(loader).generation == 31
