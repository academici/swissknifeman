"""Harness of the extensions tests: pack fixtures, the real bus over memory, one contract on two backends.

The bus, the config loader, the memory repositories and the production authorizer are real; ids, clock and
entropy are deterministic. The repositories come from the ``REPOSITORIES`` of each backend package, as in the
composition. The token estimator is a fake: the built-in heuristic arrives with its own leaf (P09.04.a).
"""

from collections.abc import Callable, Iterator, Mapping
from datetime import timedelta
from typing import Any, cast
from uuid import UUID

import psycopg
import pytest

from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.access import REPOSITORIES as MEMORY_ACCESS
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as MEMORY_CORE
from skm.adapters.memory.extensions import REPOSITORIES as MEMORY_EXTENSIONS
from skm.adapters.memory.extensions.mapping import extensions_state
from skm.adapters.memory.settings import REPOSITORIES as MEMORY_SETTINGS
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.memory.workspace import REPOSITORIES as MEMORY_WORKSPACE
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.uow import PostgresUowFactory
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import Authorizer
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.adapters import postgres_repository_table
from skm.kernel.actor import PrincipalKind
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.ports import PrincipalRepository, TokenPepperSource
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.extensions.domain.payload import PackPayload, PayloadFile
from skm.modules.extensions.module import MODULE as EXTENSIONS
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.policy.module import MODULE as POLICY
from skm.modules.settings.module import MODULE as SETTINGS
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource, ScopeTree
from skm.platform.schema.registry import SchemaRegistry
from support.backend import LockedIds, PostgresTestBackend
from support.pg import TestDatabase
from support.seed import SEED, seed_backend
from unit.policy.application.harness import (
    EVERYTHING,
    INSTANCE,
    NOW,
    FixedPepper,
    Packs,
    World,
    schemas,
    settings_registry,
)

__all__ = [
    "CATALOG_TOML",
    "NOW",
    "ExtensionsWorld",
    "FakeBuiltinPacks",
    "FakeEstimator",
    "Side",
    "build_world",
    "memory_side",
    "pack_payload",
    "postgres_side",
    "profile_toml",
    "side",
]

PROMPT_BLOCKS = {
    "prompts/shared/system.md": "system rules",
    "prompts/executor/role.md": "role text",
    "prompts/executor/result.md": "result text",
}
CATALOG_TOML = 'schema = "urn:skm:runtimes:model-catalog:v1"\ncatalog_version = "{version}"\n[runtimes]\n'


def profile_toml(
    key: str = "executor",
    *,
    role: str = "executor",
    policy_profile: str = "workspace-contained",
    layer: str = "",
    inherit: str = "false",
) -> str:
    """A file of ``urn:skm:extensions:agent-profile:v1``; ``layer`` is TOML of ``[permissions.layer.*]``."""
    return f"""
schema = "urn:skm:extensions:agent-profile:v1"
key = "{key}"
version = "1.0.0"
role = "{role}"
title = "Executor"
description = "Implements one task."
result_schema = "urn:skm:execution:role-result:{role}:v1"
llm = true

[routing]
model_class = "implementation"
effort = "high"
required_capabilities = []
optional_capabilities = []

[isolation]
profile = "worktree"

[permissions]
policy_profile = "{policy_profile}"
{layer}

[prompt]
system_constraints = ["shared/system"]
role_contract = ["executor/role"]
result_contract = ["executor/result"]

[context]
include = []
inherit_user_global = {inherit}
repo_instructions = "full"
repo_instruction_sections = []
skills_mode = "auto"
skills_include = []
skills_exclude = []
history_max_steps = 3
memory_top_k = 0
include_optional_materials = true

[limits]
timeout_seconds = 3600
idle_timeout_seconds = 600
max_result_retries = 2
"""


def pack_payload(
    slug: str = "core",
    version: str = "1.0.0",
    *,
    trust: str = "builtin",
    files: Mapping[str, str] | None = None,
    binary: Mapping[str, bytes] | None = None,
    extra_manifest: str = "",
    requires_skm: str = ">=0.1.0,<1",
    priority: int | None = None,
) -> PackPayload:
    manifest = f"""
schema = "urn:skm:extensions:pack:v1"
slug = "{slug}"
version = "{version}"
title = "Pack {slug}"
description = "A pack of the tests."
publisher = "skm"
trust = "{trust}"
license = "Apache-2.0"
requires_skm = "{requires_skm}"
{"" if priority is None else f"priority = {priority}"}
{extra_manifest}
"""
    bodies = {path: text.encode() for path, text in (files or {}).items()} | dict(binary or {})
    return PackPayload(manifest, tuple(PayloadFile(path, body) for path, body in bodies.items()))


def core_files(*, version: str = "1.0.0", **profile: Any) -> dict[str, str]:
    """A loadable pack: prompts, one executor profile, one runtime catalog of the given version."""
    return {
        **PROMPT_BLOCKS,
        "agent-profiles/executor.toml": profile_toml(**profile),
        "runtimes/models.toml": CATALOG_TOML.format(version=version),
    }


class FakeBuiltinPacks:
    def __init__(self, *payloads: PackPayload) -> None:
        self.current = tuple(payloads)

    def payloads(self) -> tuple[PackPayload, ...]:
        return self.current


class FakeEstimator:
    estimator_id = "fake"

    def estimate(self, text: str) -> int:
        return len(text)


class ExtensionsWorld(World):
    builtin: FakeBuiltinPacks

    def tables(self) -> Any:
        return extensions_state(self.backend.committed)

    def extension_events(self, name: str) -> list[Any]:
        urn = f"urn:skm:extensions:event:{name}:v1"
        return [event for event in self.backend.committed.core.events if event.type == urn]

    def config(self, uow: Any) -> Any:
        return self.loader.effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.RUN, self.scope_id)
        )


def build_world(*builtin: PackPayload) -> ExtensionsWorld:
    registry = BusRegistry.build(
        (ACCESS, WORKSPACE, SETTINGS, POLICY, EXTENSIONS),
        schemas=schemas(),
        permission_catalog=EVERYTHING,
        disabled_modules=frozenset(),
    )
    clock, ids, entropy = FrozenClock(NOW), SequentialIds(), DeterministicEntropy()
    packs, authorizer = Packs(), RbacAuthorizer(clock)
    factories: dict[type, Callable[[Any], object]] = {
        **MEMORY_CORE,
        **MEMORY_ACCESS,
        **MEMORY_WORKSPACE,
        **MEMORY_SETTINGS,
        **MEMORY_EXTENSIONS,
        ConfigStore: MemoryConfigStore,
        PackConfigSource: lambda _state: packs,
        Authorizer: lambda _state: authorizer,
    }
    backend = InMemoryBackend(
        factories=factories,
        schemas=schemas(),
        subscriptions=registry.subscription_index(),
        ids=ids,
        clock=clock,
    )
    gateway = FakeBuiltinPacks(*builtin)
    loader = ConfigLoader(settings_registry(), packs)
    bus = Bus(
        registry=registry,
        schemas=schemas(),
        uow_factory=backend.uow_factory(),
        authorizer=authorizer,
        scopes=FakeScopeChain(),
        config=loader,
        clock=clock,
        ids=ids,
        entropy=entropy,
        gateways=GatewayTable(
            {TokenPepperSource: FixedPepper(), TokenEstimator: FakeEstimator(), BuiltinPacks: gateway},
            "control_plane_gateway",
        ),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )
    world = ExtensionsWorld(backend, bus, clock, ids, loader)
    world.builtin = gateway
    with world.uow() as uow:
        uow.repo(ScopeRegistry).create(INSTANCE, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        uow.commit()
    world.person("owner", {INSTANCE: Role.OWNER})
    world.person("admin", {INSTANCE: Role.MAINTAINER})
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
    return world


# ------------------------------------------------------------------------------- repository contract
ACTOR = SEED.principal_id
OTHER_ACTOR = PrincipalId(UUID(int=1))


class Side:
    """One backend with the extension repositories and two principals."""

    def __init__(
        self,
        kind: str,
        uow_factory: UnitOfWorkFactory,
        ids: Any,
        pg: PostgresTestBackend | None = None,
        memory: InMemoryBackend | None = None,
    ) -> None:
        self.kind, self.uow_factory, self.ids, self.pg, self.memory = kind, uow_factory, ids, pg, memory
        self.requests = 0

    def uow(self, *, readonly: bool = False) -> UnitOfWork:
        self.requests += 1
        meta = RequestMeta(f"req_{self.requests:0>26}", Surface.TEST, None, NOW)
        return self.uow_factory(meta, readonly=readonly)

    def close(self) -> None:
        if self.pg is not None:
            self.pg.close()


def _principals(made: Side) -> None:
    with made.uow() as uow:
        for principal_id in (ACTOR, OTHER_ACTOR):
            uow.repo(PrincipalRepository).add(
                new_principal(
                    principal_id=principal_id,
                    kind=PrincipalKind.HUMAN,
                    display_name=f"p-{str(principal_id)[-4:]}",
                    created_by=None,
                    now=NOW,
                )
            )
        uow.commit()


def _schemas() -> SchemaRegistry:
    return schemas()


def memory_side() -> Side:
    clock, ids = FrozenClock(NOW), LockedIds()
    factories: dict[type, Callable[[Any], object]] = {
        **MEMORY_CORE,
        **MEMORY_ACCESS,
        **MEMORY_WORKSPACE,
        **MEMORY_EXTENSIONS,
    }
    backend = InMemoryBackend(factories=factories, schemas=_schemas(), subscriptions={}, ids=ids, clock=clock)
    factory = backend.uow_factory()
    seed_backend(factory)
    made = Side("memory", factory, ids, memory=backend)
    _principals(made)
    return made


def postgres_side(database: TestDatabase) -> Side:
    clock, ids = FrozenClock(NOW), LockedIds()
    pg = PostgresTestBackend(database, pool_max_size=4)
    factories = cast(
        "Mapping[type, Callable[[psycopg.Connection], object]]",
        postgres_repository_table(("access", "workspace", "extensions")),
    )
    writer = PostgresEventWriter(schemas=_schemas(), subscriptions={}, ids=ids)
    made = Side("postgres", PostgresUowFactory(pg.pool, factories, writer, clock), ids, pg)
    _principals(made)
    return made


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def side(request: pytest.FixtureRequest) -> Iterator[Side]:
    made = (
        memory_side()
        if request.param == "memory"
        else postgres_side(request.getfixturevalue("clean_test_database"))
    )
    try:
        yield made
    finally:
        made.close()
