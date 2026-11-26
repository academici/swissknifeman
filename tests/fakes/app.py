"""Test-only wiring of the application bus over the memory backend.

Everything here is a test double: the config loader and its store answer from a dict (the real ones live in
``platform.config``), the authorizer is ``fakes.authorizer.FakeAuthorizer`` and the gateway table is empty.
Nothing in ``src/skm`` imports this module, and no production registry contains the ``demo`` module.
"""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any
from uuid import UUID

from fakes.authorizer import FakeAuthorizer
from fakes.clock import FrozenClock
from fakes.demo_module import MANIFEST, PERMISSIONS, SCHEMA_ROOT
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.core import REPOSITORIES as CORE_REPOSITORIES
from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.uow import InMemoryBackend, InMemoryUowFactory
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.client import EmbeddedClient, EventReaderSession
from skm.application_bus.ports import EventReader
from skm.application_bus.registry import BusRegistry
from skm.kernel.actor import Actor
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.module_manifest import ModuleManifest
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeRecord, ScopeRef, ScopeRegistry
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.schema.registry import SchemaRegistry
from support.seed import Seed, seed_backend

__all__ = [
    "FakeConfig",
    "FakeConfigLoader",
    "FakeConfigStore",
    "FakeGateways",
    "FakeScopeChain",
    "Harness",
    "build_harness",
    "request_id",
]


class FakeConfig:
    """``EffectiveConfig`` subset the bus reads: ``get`` over a flat dict."""

    def __init__(self, values: Mapping[str, JsonValue]) -> None:
        self._values = dict(values)
        self.chain: tuple[ScopeRef, ...] = ()
        self.generation = 1
        self.pack_generation = 0
        self.digest = "sha256:" + "0" * 64

    def get(self, key: str) -> JsonValue | None:
        return self._values.get(key)

    def present(self, key: str) -> bool:
        return key in self._values

    def resolution(self, key: str) -> JsonObject:
        return {}

    def provenance(self, key: str) -> JsonObject:
        return {}


class FakeConfigStore:
    """``ConfigStore`` without levels; the fake loader below never reads it."""

    def generation(self) -> int:
        return 1

    def entries_for(self, scope_ids: Any) -> Mapping[UUID, Mapping[str, JsonObject]]:
        return {}


class FakeConfigLoader:
    """``ConfigLoader.effective`` over a mutable dict; counts calls."""

    def __init__(self, values: Mapping[str, JsonValue] | None = None) -> None:
        self.values: dict[str, JsonValue] = dict(values or {})
        self.calls = 0

    def effective(
        self,
        store: ConfigStore,
        scopes: ScopeTree,
        scope: ScopeRef | None,
        kind: str = "work",
        *,
        frozen: JsonObject | None = None,
    ) -> FakeConfig:
        self.calls += 1
        return FakeConfig(self.values)


class FakeGateways:
    """Empty gateway table: a handler that asks for a gateway fails loudly."""

    def get(self, port: type[Any]) -> Any:
        raise LookupError(f"no gateway for {port.__name__} in this test")

    def has(self, port: type[object]) -> bool:
        return False


class FakeScopeChain:
    """``ScopeChainResolver`` over ``uow.repo(ScopeRegistry)``."""

    def chain(self, uow: Any, scope: ScopeRef | None) -> tuple[ScopeRecord, ...]:
        registry = uow.repo(ScopeRegistry)
        if scope is None:
            return (registry.instance(),)
        return registry.ancestors(scope.id)  # NotFound for an unknown scope


@dataclass
class Harness:
    """A bus, its memory backend and the test doubles around them."""

    backend: InMemoryBackend
    uow_factory: InMemoryUowFactory
    bus: Bus
    registry: BusRegistry
    schemas: SchemaRegistry
    clock: FrozenClock
    ids: SequentialIds
    authorizer: FakeAuthorizer
    config: FakeConfigLoader
    seed: Seed
    actor: Actor
    client: EmbeddedClient
    extra: dict[str, object] = field(default_factory=dict[str, object])

    @property
    def state(self) -> MemoryBackendState:
        return self.backend.committed

    def meta(
        self,
        key: str | None = None,
        *,
        request: str | None = None,
        correlation_id: str | None = None,
        causation_id: str | None = None,
    ) -> RequestMeta:
        return RequestMeta(
            request_id=request or request_id(),
            surface=Surface.TEST,
            idempotency_key=key,
            received_at=self.clock.now(),
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def events(self) -> list[Any]:
        return list(self.backend.committed.core.events)

    def audit(self) -> list[Any]:
        return list(self.backend.committed.core.audit)

    def reader_session(self) -> EventReaderSession:
        @contextmanager
        def session() -> Iterator[EventReader]:
            with self.uow_factory(self.meta(), readonly=True) as uow:
                yield uow.repo(EventReader)

        return session()


def build_harness(
    *,
    manifests: tuple[ModuleManifest, ...] = (MANIFEST,),
    allowed: frozenset[str] | None = None,
    config: Mapping[str, JsonValue] | None = None,
    ttl: timedelta = timedelta(hours=24),
    disabled_modules: frozenset[str] = frozenset(),
    clock: FrozenClock | None = None,
    ids: SequentialIds | None = None,
) -> Harness:
    """Registry, memory backend (seeded), bus and an embedded client for the human seed actor."""
    schemas = SchemaRegistry.load(SCHEMA_ROOT)
    registry = BusRegistry.build(
        manifests, schemas=schemas, permission_catalog=PERMISSIONS, disabled_modules=disabled_modules
    )
    clock = clock if clock is not None else FrozenClock()
    ids = ids if ids is not None else SequentialIds()
    factories: dict[type, Any] = {
        **CORE_REPOSITORIES,
        ConfigStore: lambda state: FakeConfigStore(),
    }
    backend = InMemoryBackend(
        factories=factories,
        schemas=schemas,
        subscriptions=registry.subscription_index(),
        ids=ids,
        clock=clock,
    )
    uow_factory = backend.uow_factory()
    seed = seed_backend(uow_factory)
    authorizer = FakeAuthorizer(allowed)
    loader = FakeConfigLoader(config)
    bus = Bus(
        registry=registry,
        schemas=schemas,
        uow_factory=uow_factory,
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=loader,  # type: ignore[arg-type] - the fake implements the part of ConfigLoader the bus calls
        clock=clock,
        ids=ids,
        entropy=DeterministicEntropy(),
        gateways=FakeGateways(),  # type: ignore[arg-type]
        retry=RetryPolicy(max_attempts=3, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=ttl,
    )
    actor = seed.actor()
    harness = Harness(
        backend=backend,
        uow_factory=uow_factory,
        bus=bus,
        registry=registry,
        schemas=schemas,
        clock=clock,
        ids=ids,
        authorizer=authorizer,
        config=loader,
        seed=seed,
        actor=actor,
        client=None,  # type: ignore[arg-type] - set below, the client needs the harness reader session
    )
    harness.client = EmbeddedClient(
        bus,
        actor=actor,
        surface=Surface.TEST,
        events=harness.reader_session,
        clock=clock,
        ids=ids,
        client_label="test/0",
    )
    return harness


def request_id(n: int = 1) -> str:
    """A well-formed request id (``req_`` + 26 characters) that is easy to read in assertions."""
    return f"req_{n:0>26}"
