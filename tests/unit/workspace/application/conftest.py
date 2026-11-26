"""Harness of the workspace application tests: the real bus over the memory backend (workspace §15).

The bus, the config loader over the packaged sections, the memory repositories of ``access`` and
``workspace`` and the production authorizer (``RbacAuthorizer``) are real; only ids, clock and entropy are
deterministic. People are seeded as domain values (principal plus membership), never through a handler under
test, so a failing command cannot be blamed on its own setup.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import pytest

from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.access import REPOSITORIES as ACCESS_REPOSITORIES
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as CORE_REPOSITORIES
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.memory.workspace import REPOSITORIES as WORKSPACE_REPOSITORIES
from skm.adapters.memory.workspace.state import workspace_state
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import Authorizer
from skm.application_bus.registry import BusRegistry
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, PrincipalId, ProjectId, ScopeId, WorkerId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.permissions import PERMISSIONS as CATALOG
from skm.modules.access.ports import MembershipRepository, PrincipalRepository, TokenPepperSource
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.workspace.domain.host import HostArch as DomainArch
from skm.modules.workspace.domain.host import HostOs as DomainOs
from skm.modules.workspace.domain.host import HostPlatform
from skm.modules.workspace.domain.worker import Worker, WorkerCapabilities, WorkerState
from skm.modules.workspace.generated.commands import HostArch, HostOs
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.ports import WorkerRepository
from skm.modules.workspace.public import (
    CreateProject,
    CreateWorkspace,
    RegisterHost,
    RegisterHostDefsHostPlatform,
    RegisterRepository,
)
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource
from support.registries import schemas, settings_registry

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
PEPPER = bytes(range(32))
REMOTE = "https://github.com/acme/app.git"
EVERYTHING = frozenset(CATALOG)


class FixedPepper:
    def pepper(self) -> bytes:
        return PEPPER


class Packs:
    def generation(self) -> int:
        return 0

    def fragments(self, scope_chain: object) -> tuple[()]:
        return ()


def make_capabilities(*, profiles: tuple[str, ...] = ("worktree",)) -> WorkerCapabilities:
    return WorkerCapabilities(
        runtimes=("claude_code",),
        isolation_profiles=profiles,
        max_concurrency=2,
        labels=("gpu",),
        platform=HostPlatform(DomainOs.LINUX, DomainArch.X86_64),
        skm_version="2.0.0",
    )


@dataclass
class World:
    backend: InMemoryBackend
    bus: Bus
    clock: FrozenClock
    ids: SequentialIds
    instance: ScopeId
    counter: int = 0
    people: dict[str, Actor] = field(default_factory=dict[str, Actor])

    # ------------------------------------------------------------------ requests
    def meta(self, key: str | None = None) -> RequestMeta:
        self.counter += 1
        return RequestMeta(f"req_{self.counter:0>26}", Surface.TEST, key, self.clock.now())

    def run(self, dto: object, actor: Actor | str = "owner", *, key: str | None = None) -> Any:
        return self.bus.dispatch(dto, actor=self.actor(actor), meta=self.meta(key))

    def ask(self, dto: object, actor: Actor | str = "owner") -> Any:
        return self.bus.ask(dto, actor=self.actor(actor), meta=self.meta())

    def uow(self, *, readonly: bool = False) -> Any:
        return self.backend.uow_factory()(self.meta(), readonly=readonly)

    def actor(self, who: Actor | str) -> Actor:
        return self.people[who] if isinstance(who, str) else who

    # ------------------------------------------------------------------ seeding (domain values, no handler)
    def person(
        self,
        name: str,
        roles: Mapping[ScopeId, Role] | None = None,
        *,
        kind: PrincipalKind = PrincipalKind.HUMAN,
    ) -> Actor:

        with self.uow() as uow:
            principal = new_principal(
                principal_id=PrincipalId(self.ids.new_id()),
                kind=kind,
                display_name=name,
                created_by=None,
                now=self.clock.now(),
            )
            uow.repo(PrincipalRepository).add(principal)
            for scope_id, role in (roles or {}).items():
                uow.repo(MembershipRepository).upsert(Membership(scope_id, principal.id, role, None, NOW))
            uow.commit()
        actor = Actor(principal_id=principal.id, kind=kind, display_name=name)
        self.people[name] = actor
        return actor

    def workspace(self, slug: str = "personal", title: str = "Personal") -> WorkspaceId:
        return WorkspaceId(self.run(CreateWorkspace(slug=slug, title=title)).workspace_id)

    def project(self, workspace_id: WorkspaceId, slug: str = "skm", title: str = "SKM") -> ProjectId:
        return ProjectId(
            self.run(CreateProject(workspace_id=workspace_id, slug=slug, title=title)).project_id
        )

    def host(self, name: str = "laptop") -> HostId:
        platform = RegisterHostDefsHostPlatform(os=HostOs.LINUX, arch=HostArch.X86_64)
        return HostId(self.run(RegisterHost(name=name, platform=platform)).host_id)

    def repository(self, workspace_id: WorkspaceId, title: str = "app", remote: str | None = REMOTE) -> UUID:
        return self.run(
            RegisterRepository(workspace_id=workspace_id, title=title, remote_url=remote, external_id=None)
        ).repository_id

    def worker(
        self,
        workspace_id: WorkspaceId,
        host_id: HostId,
        name: str = "w1",
        *,
        state: str = "offline",
    ) -> tuple[Actor, WorkerId]:
        """A worker principal, its ``worker`` membership and a ``Worker`` row (seeded as domain values)."""

        worker_id = WorkerId(self.ids.new_id())
        with self.uow() as uow:
            principal = new_principal(
                principal_id=PrincipalId(self.ids.new_id()),
                kind=PrincipalKind.WORKER,
                display_name=name,
                created_by=None,
                now=self.clock.now(),
            )
            uow.repo(PrincipalRepository).add(principal)
            uow.repo(MembershipRepository).upsert(
                Membership(ScopeId(workspace_id), principal.id, Role.WORKER, None, NOW)
            )
            uow.repo(WorkerRepository).add(
                Worker(
                    id=worker_id,
                    workspace_id=workspace_id,
                    host_id=host_id,
                    principal_id=principal.id,
                    display_name=name,
                    capabilities=make_capabilities(),
                    state=WorkerState(state),
                    last_heartbeat_at=None,
                    registered_at=self.clock.now(),
                    row_version=1,
                )
            )
            uow.commit()
        actor = Actor(principal_id=principal.id, kind=PrincipalKind.WORKER, display_name=name)
        self.people[name] = actor
        return actor, worker_id

    capabilities = staticmethod(make_capabilities)

    # ------------------------------------------------------------------ observations
    def events(self, name: str | None = None) -> list[Any]:
        found = list(self.backend.committed.core.events)
        return found if name is None else [e for e in found if e.type == f"urn:skm:workspace:event:{name}:v1"]

    def audits(self) -> list[Any]:
        return list(self.backend.committed.core.audit)

    def snapshot(self) -> tuple[object, ...]:
        """Everything a refused command must leave untouched."""
        committed = self.backend.committed
        tables = workspace_state(committed)
        return (
            dict(tables.workspaces),
            dict(tables.projects),
            dict(tables.repositories),
            dict(tables.remotes),
            dict(tables.mounts),
            dict(tables.hosts),
            dict(tables.bindings),
            dict(tables.workers),
            len(committed.core.events),
        )

    def tables(self) -> Any:
        return workspace_state(self.backend.committed)


def build_world() -> World:
    bus_registry = BusRegistry.build(
        (ACCESS, WORKSPACE), schemas=schemas(), permission_catalog=EVERYTHING, disabled_modules=frozenset()
    )
    clock, ids, entropy = FrozenClock(NOW), SequentialIds(), DeterministicEntropy()
    packs = Packs()
    authorizer = RbacAuthorizer(clock)
    factories: dict[type, Callable[[Any], object]] = {
        **CORE_REPOSITORIES,
        **ACCESS_REPOSITORIES,
        **WORKSPACE_REPOSITORIES,
        ConfigStore: MemoryConfigStore,
        PackConfigSource: lambda _state: packs,
        Authorizer: lambda _state: authorizer,
    }
    backend = InMemoryBackend(
        factories=factories,
        schemas=schemas(),
        subscriptions=bus_registry.subscription_index(),
        ids=ids,
        clock=clock,
    )
    bus = Bus(
        registry=bus_registry,
        schemas=schemas(),
        uow_factory=backend.uow_factory(),
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=ConfigLoader(settings_registry(), packs),
        clock=clock,
        ids=ids,
        entropy=entropy,
        gateways=GatewayTable({TokenPepperSource: FixedPepper()}, "control_plane_gateway"),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )
    instance = ScopeId(UUID("01900000-0000-7000-8000-000000000001"))
    made = World(backend, bus, clock, ids, instance)
    with made.uow() as uow:
        uow.repo(ScopeRegistry).create(instance, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        uow.commit()
    made.person("owner", {instance: Role.OWNER})
    return made


@pytest.fixture
def world() -> World:
    return build_world()
