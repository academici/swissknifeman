"""Test applications: ``memory_app``, ``BackendTestApp`` and ``pg_app`` over a ``TestBackend``.

``TestApp``/``TestHost`` stay test-only protocols. Both apps run the real bus with the test doubles of
``fakes.app`` for the authorizer, the config loader and the gateways; the demo module is the only registered
module. ``memory_app`` owns its own memory backend; ``BackendTestApp`` runs over the backend of the
``backend`` fixture (memory or PostgreSQL) and may take a replaced unit-of-work factory, which is how fault
wrappers reach the bus (testing spec §8). Behaviour that needs later cards (relay, host, roles, settings)
raises ``NotImplementedError`` naming the card instead of pretending to work.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import TYPE_CHECKING, Any, ClassVar, Final, Protocol

from fakes.app import FakeConfigLoader, FakeGateways, FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from fakes.entropy import DeterministicEntropy
from skm.application_bus.bus import Bus, RetryPolicy

if TYPE_CHECKING:
    from fakes.app import Harness
    from skm.application_bus.registry import BusRegistry
    from skm.kernel.events import EventEnvelope
    from skm.kernel.ports_uow import UnitOfWorkFactory
    from support.backend import TestBackend

IDEMPOTENCY_TTL: Final = timedelta(hours=24)
RETRY_ATTEMPTS: Final = 3


class TestHost(Protocol):
    __test__: ClassVar[bool] = False
    gateways: Mapping[type, object]
    calls: list[tuple[str, object]]

    # Surface.CLI becomes the typed default when the kernel Surface exists.
    def run(self, name: str, request: object, *, surface: object = "cli") -> object: ...


class TestApp(Protocol):
    __test__: ClassVar[bool] = False

    @property
    def clock(self) -> object: ...
    @property
    def ids(self) -> object: ...
    @property
    def seed(self) -> object: ...
    @property
    def state(self) -> object: ...

    def dispatch(
        self, cmd: object, *, idempotency_key: str | None = None, actor: object | None = None
    ) -> object: ...

    def ask(self, query: object, *, actor: object | None = None) -> object: ...
    def as_role(self, role: str, *, scope: object | None = None) -> TestApp: ...
    def committed_events[E](self, event_type: type[E] | None = None) -> list[E]: ...
    def envelopes(self, *, workspace_id: object | None = None) -> list[object]: ...
    def outbox(self, *, consumer_id: str | None = None, state: str | None = None) -> list[object]: ...
    def run_relay(self, *, max_rounds: int = 10) -> int: ...
    def set_config(self, key: str, value: object, *, scope: object) -> None: ...
    def host(self, *, gateways: Mapping[type, object]) -> TestHost: ...


class MemoryTestApp:
    """``TestApp`` over a ``fakes.app.Harness``: dispatch/ask go through the real bus."""

    __test__: ClassVar[bool] = False

    def __init__(self, harness: Harness, *, actor_role: str) -> None:
        self._harness = harness
        self._role = actor_role
        self.clock = harness.clock
        self.ids = harness.ids
        self.seed = harness.seed

    @property
    def state(self) -> object:
        return self._harness.backend.committed  # replaced on every commit, so read it each time

    @property
    def harness(self) -> Harness:
        return self._harness

    def dispatch(
        self, cmd: object, *, idempotency_key: str | None = None, actor: object | None = None
    ) -> object:
        if actor is None:
            return self._harness.client.dispatch(cmd, idempotency_key=idempotency_key)
        meta = self._harness.meta(idempotency_key)
        return self._harness.bus.dispatch(cmd, actor=actor, meta=meta)  # type: ignore[arg-type]

    def ask(self, query: object, *, actor: object | None = None) -> object:
        if actor is None:
            return self._harness.client.ask(query)
        return self._harness.bus.ask(query, actor=actor, meta=self._harness.meta())  # type: ignore[arg-type]

    def as_role(self, role: str, *, scope: object | None = None) -> TestApp:
        raise NotImplementedError("the bus test apps authorize through FakeAuthorizer and have no roles")

    def committed_events[E](self, event_type: type[E] | None = None) -> list[E]:
        raise NotImplementedError("the bus test apps expose raw envelopes only; use envelopes()")

    def envelopes(self, *, workspace_id: object | None = None) -> list[object]:
        events = self._harness.backend.committed.core.events
        return [e for e in events if workspace_id is None or e.workspace_id == workspace_id]

    def outbox(self, *, consumer_id: str | None = None, state: str | None = None) -> list[object]:
        rows = self._harness.backend.committed.core.outbox.values()
        return [
            row
            for row in rows
            if (consumer_id is None or row.destination == consumer_id)
            and (state is None or row.state.value == state)
        ]

    def run_relay(self, *, max_rounds: int = 10) -> int:
        raise NotImplementedError("the bus test apps do not run the outbox relay; read outbox() rows instead")

    def set_config(self, key: str, value: object, *, scope: object) -> None:
        self._harness.config.values[key] = value  # type: ignore[assignment]

    def host(self, *, gateways: Mapping[type, object]) -> TestHost:
        raise NotImplementedError("the bus test apps have no host side")


def memory_app(
    *,
    actor_role: str = "owner",
    config: Mapping[str, object] | None = None,
    disabled_modules: frozenset[str] = frozenset(),
    clock: object | None = None,
    ids: object | None = None,
) -> TestApp:
    from fakes.app import build_harness

    options: dict[str, Any] = {}
    if clock is not None:
        options["clock"] = clock
    if ids is not None:
        options["ids"] = ids
    harness = build_harness(config=config, disabled_modules=disabled_modules, **options)  # type: ignore[arg-type]
    return MemoryTestApp(harness, actor_role=actor_role)


class BackendTestApp:
    """``TestApp`` over a ``TestBackend``: the real bus, its units of work from ``uow_factory``."""

    __test__: ClassVar[bool] = False

    def __init__(
        self,
        backend: TestBackend,
        *,
        actor_role: str,
        uow_factory: UnitOfWorkFactory,
        registry: BusRegistry,
    ) -> None:
        if actor_role != "owner":
            raise NotImplementedError("the bus test apps authorize through FakeAuthorizer and have no roles")
        self.backend = backend
        self.clock = backend.clock
        self.ids = backend.ids
        self.seed = backend.seed
        self.actor = backend.seed.actor()
        self.authorizer = FakeAuthorizer(None)
        self.config = FakeConfigLoader()
        self.bus = Bus(
            registry=registry,
            schemas=backend.schemas,
            uow_factory=uow_factory,
            authorizer=self.authorizer,
            scopes=FakeScopeChain(),
            config=self.config,  # type: ignore[arg-type] - the fake implements the part of ConfigLoader the bus calls
            clock=backend.clock,
            ids=backend.ids,
            entropy=DeterministicEntropy(),
            gateways=FakeGateways(),  # type: ignore[arg-type]
            retry=RetryPolicy(max_attempts=RETRY_ATTEMPTS, base_delay_seconds=0.0, max_delay_seconds=0.0),
            idempotency_ttl=IDEMPOTENCY_TTL,
        )

    @property
    def state(self) -> object:
        memory = getattr(self.backend, "memory", None)
        if memory is None:
            raise TypeError("TestApp.state is a read-only view of the memory backend only")
        return memory.committed

    def dispatch(
        self, cmd: object, *, idempotency_key: str | None = None, actor: object | None = None
    ) -> object:
        meta = self.backend.meta(idempotency_key)
        return self.bus.dispatch(cmd, actor=actor or self.actor, meta=meta)  # type: ignore[arg-type]

    def ask(self, query: object, *, actor: object | None = None) -> object:
        return self.bus.ask(query, actor=actor or self.actor, meta=self.backend.meta())  # type: ignore[arg-type]

    def as_role(self, role: str, *, scope: object | None = None) -> TestApp:
        raise NotImplementedError("the bus test apps authorize through FakeAuthorizer and have no roles")

    def committed_events[E](self, event_type: type[E] | None = None) -> list[E]:
        raise NotImplementedError("the bus test apps expose raw envelopes only; use envelopes()")

    def envelopes(self, *, workspace_id: object | None = None) -> list[object]:
        events: list[EventEnvelope] = self.backend.envelopes(workspace_id=workspace_id)  # type: ignore[arg-type]
        return list[object](events)

    def outbox(self, *, consumer_id: str | None = None, state: str | None = None) -> list[object]:
        return [
            row
            for row in self.backend.outbox_rows()
            if (consumer_id is None or row.destination == consumer_id)
            and (state is None or row.state == state)
        ]

    def run_relay(self, *, max_rounds: int = 10) -> int:
        raise NotImplementedError("the bus test apps do not run the outbox relay; read outbox() rows instead")

    def set_config(self, key: str, value: object, *, scope: object) -> None:
        self.config.values[key] = value  # type: ignore[assignment]

    def host(self, *, gateways: Mapping[type, object]) -> TestHost:
        raise NotImplementedError("TestHost (testing spec §6.1) arrives with the first host-operation suite")


def pg_app(backend: TestBackend, *, actor_role: str = "owner") -> TestApp:
    """The bus over the PostgreSQL ``TestBackend`` (the ``backend[postgres]`` or ``pg_backend`` fixture)."""
    if getattr(backend, "kind", None) != "postgres":
        raise TypeError("pg_app needs the PostgreSQL TestBackend of tests/support/backend.py")
    return backend.app(actor_role=actor_role)
