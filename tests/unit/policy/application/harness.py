"""Harness of the policy application and security tests: the real bus over the memory backend (policy §15).

The bus, the config loader over the packaged sections, the memory repositories of ``access``, ``workspace``,
``settings`` and ``policy`` and the production authorizer (``RbacAuthorizer``) are real; only ids, clock and
entropy are deterministic. People are seeded as domain values (principal plus membership), never through a
handler under test. The scope tree is ``instance > workspace > project > plan > run``; intents live in the
run scope, so the configuration of every level applies to them.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.access import REPOSITORIES as ACCESS_REPOSITORIES
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as CORE_REPOSITORIES
from skm.adapters.memory.policy import REPOSITORIES as POLICY_REPOSITORIES
from skm.adapters.memory.policy.state import policy_state
from skm.adapters.memory.settings import REPOSITORIES as SETTINGS_REPOSITORIES
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.memory.workspace import REPOSITORIES as WORKSPACE_REPOSITORIES
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.context import CommandContext
from skm.application_bus.ports import Authorizer
from skm.application_bus.registry import BusRegistry
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.permissions import PERMISSIONS as CATALOG
from skm.modules.access.ports import MembershipRepository, PrincipalRepository, TokenPepperSource
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.policy.module import MODULE as POLICY
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.settings.module import MODULE as SETTINGS
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource, ScopeTree
from skm.platform.logging.logger import get_logger
from support.registries import schemas, settings_registry

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
PEPPER = bytes(range(32))
EVERYTHING = frozenset(CATALOG)
ALL_EFFECTS = ["git_commit", "git_push", "pr_create", "message", "publish"]
INSTANCE = ScopeId(UUID("01900000-0000-7000-8000-000000000001"))
DIGEST = "sha256:" + "a" * 64
SHA = "b" * 40
REPOSITORY = "01900000-0000-7000-8000-0000000000aa"


class FixedPepper:
    def pepper(self) -> bytes:
        return PEPPER


class Packs:
    def generation(self) -> int:
        return 0

    def fragments(self, scope_chain: object) -> tuple[()]:
        return ()


def push_args(**changes: Any) -> dict[str, Any]:
    """A valid ``git_push`` argument document; ``changes`` replace members."""
    document: dict[str, Any] = {
        "repository_id": REPOSITORY,
        "remote": "github.com/acme/app",
        "endpoint": {
            "transport": "https",
            "hostname": "github.com",
            "effective_port": 443,
            "repository_path": "acme/app.git",
        },
        "binding_identity": {
            "binding_id": "01900000-0000-7000-8000-0000000000b1",
            "host_id": "01900000-0000-7000-8000-0000000000b2",
            "repository_id": REPOSITORY,
            "locator_digest": DIGEST,
        },
        "target_ref": "refs/heads/main",
        "before_sha": SHA,
        "after_sha": "c" * 40,
        "refspecs": ["refs/heads/main:refs/heads/main"],
        "force": False,
    }
    document.update(changes)
    return document


def commit_args(**changes: Any) -> dict[str, Any]:
    document: dict[str, Any] = {
        "repository_id": REPOSITORY,
        "branch": "refs/heads/work",
        "parent_commit": SHA,
        "tree_digest": DIGEST,
    }
    document.update(changes)
    return document


@dataclass
class World:
    backend: InMemoryBackend
    bus: Bus
    clock: FrozenClock
    ids: SequentialIds
    loader: ConfigLoader
    counter: int = 0
    people: dict[str, Actor] = field(default_factory=dict[str, Actor])
    workspace_id: WorkspaceId = field(default_factory=lambda: WorkspaceId(UUID(int=0)))
    project_id: ProjectId = field(default_factory=lambda: ProjectId(UUID(int=0)))
    scope_id: ScopeId = field(
        default_factory=lambda: ScopeId(UUID(int=0))
    )  # the run scope: intents live here

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

    def context(
        self, uow: Any, who: Actor | str = "owner", *, entropy: DeterministicEntropy | None = None
    ) -> CommandContext:
        """The context a handler of the run scope gets, for the facade called in ``uow`` (execution's way)."""
        scope = ScopeRef(ScopeKind.RUN, self.scope_id)
        chain = FakeScopeChain().chain(uow, scope)
        return CommandContext(
            actor=self.actor(who),
            meta=self.meta(),
            scope=scope,
            scope_chain=chain,
            clock=self.clock,
            ids=self.ids,
            entropy=entropy or DeterministicEntropy(),
            config=self.loader.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), scope),
            log=get_logger("modules.policy"),
            gateways=GatewayTable({}, "control_plane_gateway"),
        )

    def tick(self, seconds: float) -> None:
        self.clock.advance(timedelta(seconds=seconds))

    # ------------------------------------------------------------------ seeding (domain values, no handler)
    def person(
        self,
        name: str,
        roles: Mapping[Any, Role] | None = None,
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

    def set_config(self, key: str, value: JsonValue, level: str = "instance") -> None:
        scope = SetValueDefsScopeRef(level=cast("Any", level))
        self.run(SetValue(scope=scope, key=key, value=value))

    def allow_effects(self, *kinds: str) -> None:
        allowed: list[JsonValue] = list(kinds)
        self.set_config("policy.ceiling.external_effects", allowed)

    # ------------------------------------------------------------------ observations
    def events(self, name: str | None = None) -> list[Any]:
        found = [e for e in self.backend.committed.core.events if e.type.startswith("urn:skm:policy:event:")]
        return found if name is None else [e for e in found if e.type == f"urn:skm:policy:event:{name}:v1"]

    def intents(self) -> dict[Any, Any]:
        return dict(policy_state(self.backend.committed).intents)

    def approvals(self) -> dict[Any, Any]:
        return dict(policy_state(self.backend.committed).approvals)

    def audit(self) -> list[Any]:
        return list(policy_state(self.backend.committed).audit)

    def snapshot(self) -> tuple[object, ...]:
        """Everything a refused command must leave untouched."""
        committed = self.backend.committed
        tables = policy_state(committed)
        return (
            dict(tables.intents),
            dict(tables.approvals),
            list(tables.audit),
            len(committed.core.events),
        )


def build_world() -> World:
    bus_registry = BusRegistry.build(
        (ACCESS, WORKSPACE, SETTINGS, POLICY),
        schemas=schemas(),
        permission_catalog=EVERYTHING,
        disabled_modules=frozenset(),
    )
    clock, ids, entropy = FrozenClock(NOW), SequentialIds(), DeterministicEntropy()
    packs = Packs()
    authorizer = RbacAuthorizer(clock)
    factories: dict[type, Callable[[Any], object]] = {
        **CORE_REPOSITORIES,
        **ACCESS_REPOSITORIES,
        **WORKSPACE_REPOSITORIES,
        **SETTINGS_REPOSITORIES,
        **POLICY_REPOSITORIES,
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
    loader = ConfigLoader(settings_registry(), packs)
    bus = Bus(
        registry=bus_registry,
        schemas=schemas(),
        uow_factory=backend.uow_factory(),
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=loader,
        clock=clock,
        ids=ids,
        entropy=entropy,
        gateways=GatewayTable({TokenPepperSource: FixedPepper()}, "control_plane_gateway"),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )
    world = World(backend, bus, clock, ids, loader)
    with world.uow() as uow:
        uow.repo(ScopeRegistry).create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        uow.commit()
    world.person("owner", {INSTANCE: Role.OWNER})
    world.workspace_id = WorkspaceId(
        world.run(CreateWorkspace(slug="personal", title="Personal")).workspace_id
    )
    world.project_id = ProjectId(
        world.run(CreateProject(workspace_id=world.workspace_id, slug="skm", title="SKM")).project_id
    )
    plan, run = ScopeId(world.ids.new_id()), ScopeId(world.ids.new_id())
    with world.uow() as uow:
        scopes = uow.repo(ScopeRegistry)
        scopes.create(plan, ScopeKind.PLAN, parent=ScopeId(world.project_id), workspace_id=world.workspace_id)
        scopes.create(run, ScopeKind.RUN, parent=plan, workspace_id=world.workspace_id)
        uow.commit()
    world.scope_id = run
    world.allow_effects(*ALL_EFFECTS)
    return world
