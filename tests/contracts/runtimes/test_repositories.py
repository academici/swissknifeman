"""Dual-backend contract suite (memory ∥ PostgreSQL) for ``runtimes`` repositories (DDL 0017)."""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast

import psycopg
import pytest

from contracts.extensions.harness import CATALOG_TOML, FakeEstimator, pack_payload
from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from skm.adapters.memory.access import REPOSITORIES as MEMORY_ACCESS
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.core import REPOSITORIES as MEMORY_CORE
from skm.adapters.memory.extensions import REPOSITORIES as MEMORY_EXTENSIONS
from skm.adapters.memory.runtimes import REPOSITORIES as MEMORY_RUNTIMES
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.memory.workspace import REPOSITORIES as MEMORY_WORKSPACE
from skm.adapters.postgres.access.repositories import PostgresPrincipalRepository, PostgresTokenRepository
from skm.adapters.postgres.config_store import PostgresConfigStore
from skm.adapters.postgres.core.audit import PostgresAuditLog
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.adapters.postgres.runtimes import REPOSITORIES as POSTGRES_RUNTIMES
from skm.adapters.postgres.uow import PostgresUowFactory
from skm.adapters.postgres.workspace import REPOSITORIES as POSTGRES_WORKSPACE
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import AuditLog, Authorizer, IdempotencyStore
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.adapters import postgres_repository_table
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import HostId, PrincipalId, ResourceVersionId
from skm.kernel.isolation import IsolationProfile
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.ports import (
    MembershipRepository,
    PrincipalRepository,
    TokenPepperSource,
    TokenRepository,
)
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.extensions import public as extensions
from skm.modules.runtimes.domain.capability import (
    Capability,
    CapabilityRecord,
    CapabilityStatus,
    VerificationContext,
    verification_context_key,
)
from skm.modules.runtimes.domain.catalog import ModelStatus, Pricing
from skm.modules.runtimes.domain.catalog_records import (
    CanonicalModel,
    HostModelAvailability,
    ModelGuideline,
    ProviderModelOffering,
)
from skm.modules.runtimes.domain.classes import Effort, ModelClass, RoleId
from skm.modules.runtimes.domain.detection import VerificationRecord
from skm.modules.runtimes.domain.installation import AuthState, RuntimeInstallation
from skm.modules.runtimes.ports import (
    CapabilityVerificationRepository,
    HostModelAvailabilityRepository,
    HostRuntimeRepository,
    ModelCatalogRepository,
)
from skm.modules.workspace.generated.commands import HostArch, HostOs
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.public import RegisterHost, RegisterHostDefsHostPlatform
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource, ScopeTree
from support.backend import LockedIds, PostgresTestBackend
from support.pg import TestDatabase, clean_test_database, pg_session, test_database  # noqa: F401
from support.seed import SEED, seed_backend
from support.sides import BACKEND_PARAMS, iter_pg_side, iter_side
from unit.policy.application.harness import (
    EVERYTHING,
    NOW,
    FixedPepper,
    Packs,
    schemas,
    settings_registry,
)

INSTANCE = SEED.instance_id
BINARY_SHA = "sha256:" + "e" * 64
LAUNCH_SHA = "sha256:" + "f" * 64


@dataclass
class Side:
    kind: str
    uow_factory: UnitOfWorkFactory
    clock: FrozenClock
    ids: LockedIds
    bus: Bus
    owner: Actor
    host_a: HostId
    host_b: HostId
    pg: PostgresTestBackend | None = None
    memory: InMemoryBackend | None = None
    requests: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    def meta(self, key: str | None = None) -> RequestMeta:
        return RequestMeta(f"req_{next(self.requests):0>26}", Surface.TEST, key, self.clock.now())

    def uow(self, *, readonly: bool = False) -> UnitOfWork:
        return self.uow_factory(self.meta(), readonly=readonly)

    def tick(self, seconds: float = 1.0) -> None:
        self.clock.advance(timedelta(seconds=seconds))

    def close(self) -> None:
        if self.pg is not None:
            self.pg.close()


def _bus(uow_factory: UnitOfWorkFactory, registry: BusRegistry, clock: FrozenClock, ids: LockedIds) -> Bus:
    packs = Packs()
    return Bus(
        registry=registry,
        schemas=schemas(),
        uow_factory=uow_factory,
        authorizer=RbacAuthorizer(clock),
        scopes=FakeScopeChain(),
        config=ConfigLoader(settings_registry(), packs),
        clock=clock,
        ids=ids,
        entropy=DeterministicEntropy(),
        gateways=GatewayTable({TokenPepperSource: FixedPepper()}, "control_plane_gateway"),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )


def _registry() -> BusRegistry:
    return BusRegistry.build(
        (ACCESS, WORKSPACE),
        schemas=schemas(),
        permission_catalog=EVERYTHING,
        disabled_modules=frozenset(),
    )


def _seed_owner_and_hosts(
    kind: str,
    uow_factory: UnitOfWorkFactory,
    clock: FrozenClock,
    ids: LockedIds,
    bus: Bus,
    *,
    pg: PostgresTestBackend | None = None,
    memory: InMemoryBackend | None = None,
) -> Side:
    meta0 = RequestMeta("req_" + "0" * 26, Surface.TEST, None, clock.now())
    principal = new_principal(
        principal_id=PrincipalId(ids.new_id()),
        kind=PrincipalKind.HUMAN,
        display_name="owner",
        created_by=None,
        now=clock.now(),
    )
    with uow_factory(meta0, readonly=False) as uow:
        uow.repo(PrincipalRepository).add(principal)
        uow.repo(MembershipRepository).upsert(
            Membership(INSTANCE, principal.id, Role.OWNER, None, clock.now())
        )
        uow.commit()
    owner = Actor(principal_id=principal.id, kind=PrincipalKind.HUMAN, display_name="owner")
    platform = RegisterHostDefsHostPlatform(os=HostOs.LINUX, arch=HostArch.X86_64)
    meta1 = RequestMeta("req_" + "1" * 26, Surface.TEST, None, clock.now())
    meta2 = RequestMeta("req_" + "2" * 26, Surface.TEST, None, clock.now())
    res_a = cast("Any", bus.dispatch(RegisterHost(name="host-a", platform=platform), actor=owner, meta=meta1))
    res_b = cast("Any", bus.dispatch(RegisterHost(name="host-b", platform=platform), actor=owner, meta=meta2))
    host_a = HostId(res_a.host_id)
    host_b = HostId(res_b.host_id)
    return Side(
        kind=kind,
        uow_factory=uow_factory,
        clock=clock,
        ids=ids,
        bus=bus,
        owner=owner,
        host_a=host_a,
        host_b=host_b,
        pg=pg,
        memory=memory,
    )


def memory_side() -> Side:
    registry, clock, ids = _registry(), FrozenClock(NOW), LockedIds()
    packs, authorizer = Packs(), RbacAuthorizer(clock)
    clocked_runtimes = {
        port: (lambda state, adapter=adapter: adapter(state, clock=clock))
        for port, adapter in (
            (port, cast("Any", MEMORY_RUNTIMES[port]))
            for port in (HostRuntimeRepository, CapabilityVerificationRepository)
        )
    }
    factories: dict[type, Callable[[Any], object]] = {
        **MEMORY_CORE,
        **MEMORY_ACCESS,
        **MEMORY_EXTENSIONS,
        **MEMORY_WORKSPACE,
        **MEMORY_RUNTIMES,
        **clocked_runtimes,
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
    uow_factory = backend.uow_factory()
    seed_backend(uow_factory)
    bus = _bus(uow_factory, registry, clock, ids)
    return _seed_owner_and_hosts("memory", uow_factory, clock, ids, bus, memory=backend)


def postgres_side(database: TestDatabase) -> Side:
    registry, clock, ids = _registry(), FrozenClock(NOW), LockedIds()
    packs, authorizer = Packs(), RbacAuthorizer(clock)
    pg = PostgresTestBackend(database, pool_max_size=8)
    clocked = {
        port: (lambda conn, adapter=adapter: adapter(conn, clock=clock))
        for port, adapter in (
            *cast("Mapping[type, Any]", POSTGRES_WORKSPACE).items(),
            *(
                (port, cast("Any", POSTGRES_RUNTIMES[port]))
                for port in (HostRuntimeRepository, CapabilityVerificationRepository)
            ),
        )
    }
    factories: dict[type, Callable[[psycopg.Connection], object]] = {
        **cast(
            "dict[type, Callable[[psycopg.Connection], object]]",
            postgres_repository_table(("access", "workspace", "extensions", "runtimes")),
        ),
        **clocked,
        PrincipalRepository: lambda conn: PostgresPrincipalRepository(conn, clock=clock),
        TokenRepository: lambda conn: PostgresTokenRepository(conn, clock=clock),
        IdempotencyStore: PostgresIdempotencyStore,
        AuditLog: PostgresAuditLog,
        ConfigStore: PostgresConfigStore,
        PackConfigSource: lambda _conn: packs,
        Authorizer: lambda _conn: authorizer,
    }
    writer = PostgresEventWriter(schemas=schemas(), subscriptions=registry.subscription_index(), ids=ids)
    uow_factory = PostgresUowFactory(pg.pool, factories, writer, clock)
    bus = _bus(uow_factory, registry, clock, ids)
    return _seed_owner_and_hosts("postgres", uow_factory, clock, ids, bus, pg=pg)


@pytest.fixture(params=BACKEND_PARAMS)
def side(request: pytest.FixtureRequest) -> Iterator[Side]:
    yield from iter_side(request, memory_side, postgres_side)


@pytest.fixture
def pg_side(clean_test_database: TestDatabase) -> Iterator[Side]:  # noqa: F811 - imported pytest fixture
    yield from iter_pg_side(clean_test_database, postgres_side)


def _install(
    host_id: HostId,
    runtime_id: str,
    *,
    version: str | None = "1.0.0",
    auth_state: AuthState = AuthState.OK,
    details: Mapping[str, str] | None = None,
) -> RuntimeInstallation:
    return RuntimeInstallation(
        host_id=host_id,
        runtime_id=runtime_id,
        version=version,
        binary_locator=f"/usr/local/bin/{runtime_id}",
        auth_state=auth_state,
        detected_at=NOW,
        details=dict(details or {}),
    )


def test_host_runtimes_upsert_ordering_isolation_and_remove_missing(side: Side) -> None:
    with side.uow() as uow:
        repo = uow.repo(HostRuntimeRepository)
        repo.upsert(_install(side.host_a, "grok", details={"tier": "beta"}))
        repo.upsert(_install(side.host_a, "codex", version="0.42.0"))
        repo.upsert(_install(side.host_a, "claude_code", version="2.1.0"))
        repo.upsert(_install(side.host_b, "cursor", version="2026.09"))
        uow.commit()

    with side.uow(readonly=True) as uow:
        host_a_list = uow.repo(HostRuntimeRepository).list_for_host(side.host_a)
        assert [item.runtime_id for item in host_a_list] == ["claude_code", "codex", "grok"]
        assert host_a_list[2].details == {"tier": "beta"}

    side.tick(10.0)
    updated_codex = replace(
        _install(
            side.host_a, "codex", version="0.43.0", auth_state=AuthState.MISSING, details={"err": "exp"}
        ),
        detected_at=side.clock.now(),
    )
    with side.uow() as uow:
        repo = uow.repo(HostRuntimeRepository)
        repo.upsert(updated_codex)
        repo.remove_missing(side.host_a, frozenset({"codex"}))
        uow.commit()

    with side.uow(readonly=True) as uow:
        repo = uow.repo(HostRuntimeRepository)
        after_partial = repo.list_for_host(side.host_a)
        assert len(after_partial) == 1
        assert after_partial[0] == updated_codex
        assert [item.runtime_id for item in repo.list_for_host(side.host_b)] == ["cursor"]

    with side.uow() as uow:
        uow.repo(HostRuntimeRepository).remove_missing(side.host_a, frozenset())
        uow.commit()

    with side.uow(readonly=True) as uow:
        repo = uow.repo(HostRuntimeRepository)
        assert repo.list_for_host(side.host_a) == ()
        assert [item.runtime_id for item in repo.list_for_host(side.host_b)] == ["cursor"]


def test_host_runtimes_rejects_unknown_host_fk(side: Side) -> None:
    missing_host = HostId(side.ids.new_id())
    with pytest.raises(SkmError) as exc_info, side.uow() as uow:
        uow.repo(HostRuntimeRepository).upsert(_install(missing_host, "codex"))
    assert exc_info.value.code is ErrorCode.INVALID_REFERENCE


def test_capability_verifications_append_dedup_and_latest_scoping(side: Side) -> None:
    vctx_a = VerificationContext(
        host_id=side.host_a,
        binary_sha256=BINARY_SHA,
        os="linux",
        kernel="6.8",
        adapter_version="1.0.0",
        isolation_profile=IsolationProfile.WORKTREE,
        launch_config_digest=LAUNCH_SHA,
    )
    vctx_b = replace(vctx_a, host_id=side.host_b)
    key_a = verification_context_key(vctx_a)
    key_b = verification_context_key(vctx_b)

    functional = VerificationRecord(
        runtime_id="codex",
        runtime_version="0.42.0",
        record=CapabilityRecord(
            Capability.HEADLESS_EXECUTION,
            CapabilityStatus.NATIVE,
            "codex exec",
            "0.42.0",
            "",
            NOW.date(),
            None,
        ),
        verification_context=None,
        verification_key=None,
        recorded_by=side.owner.principal_id,
    )
    enforcing_old = VerificationRecord(
        runtime_id="codex",
        runtime_version="0.42.0",
        record=CapabilityRecord(
            Capability.CONFIG_ISOLATION,
            CapabilityStatus.ADAPTED,
            "isolated HOME v1",
            "0.42.0",
            "",
            NOW.date(),
            vctx_a,
        ),
        verification_context=vctx_a,
        verification_key=key_a,
        recorded_by=side.owner.principal_id,
    )
    with side.uow() as uow:
        repo = uow.repo(CapabilityVerificationRepository)
        repo.add(functional)
        repo.add(functional)  # idempotent duplicate
        repo.add(enforcing_old)
        uow.commit()

    side.tick(60.0)
    enforcing_new = VerificationRecord(
        runtime_id="codex",
        runtime_version="0.42.0",
        record=CapabilityRecord(
            Capability.CONFIG_ISOLATION,
            CapabilityStatus.NATIVE,
            "isolated HOME v2",
            "0.42.0",
            "",
            NOW.date() + timedelta(days=1),
            vctx_a,
        ),
        verification_context=vctx_a,
        verification_key=key_a,
        recorded_by=side.owner.principal_id,
    )
    with side.uow() as uow:
        uow.repo(CapabilityVerificationRepository).add(enforcing_new)
        uow.commit()

    with side.uow(readonly=True) as uow:
        repo = uow.repo(CapabilityVerificationRepository)
        for_a = {rec.capability: rec for rec in repo.latest("codex", "0.42.0", key_a)}
        assert set(for_a) == {Capability.HEADLESS_EXECUTION, Capability.CONFIG_ISOLATION}
        assert for_a[Capability.CONFIG_ISOLATION].status is CapabilityStatus.NATIVE
        assert for_a[Capability.CONFIG_ISOLATION].verification_context == vctx_a

        for_b = {rec.capability: rec for rec in repo.latest("codex", "0.42.0", key_b)}
        assert set(for_b) == {Capability.HEADLESS_EXECUTION}

        other_version = repo.latest("codex", "0.41.0", key_a)
        assert other_version == ()


def test_capability_verifications_rejects_mismatched_context_and_unknown_principal(side: Side) -> None:
    vctx = VerificationContext(
        host_id=side.host_a,
        binary_sha256=BINARY_SHA,
        os="linux",
        kernel="6.8",
        adapter_version="1.0.0",
        isolation_profile=IsolationProfile.WORKTREE,
        launch_config_digest=LAUNCH_SHA,
    )
    cap_rec = CapabilityRecord(
        Capability.CONFIG_ISOLATION,
        CapabilityStatus.NATIVE,
        "probe",
        "0.42.0",
        "",
        NOW.date(),
        vctx,
    )
    half_null = VerificationRecord(
        runtime_id="codex",
        runtime_version="0.42.0",
        record=cap_rec,
        verification_context=vctx,
        verification_key=None,
        recorded_by=side.owner.principal_id,
    )
    with pytest.raises(ValidationFailed) as half_err, side.uow() as uow:
        uow.repo(CapabilityVerificationRepository).add(half_null)
    assert half_err.value.code is ErrorCode.SCHEMA_INVALID

    wrong_key = replace(half_null, verification_key="sha256:" + "0" * 64)
    with pytest.raises(ValidationFailed) as key_err, side.uow() as uow:
        uow.repo(CapabilityVerificationRepository).add(wrong_key)
    assert key_err.value.code is ErrorCode.SCHEMA_INVALID

    unknown_actor = VerificationRecord(
        runtime_id="codex",
        runtime_version="0.42.0",
        record=replace(cap_rec, capability=Capability.HEADLESS_EXECUTION, verification_context=None),
        verification_context=None,
        verification_key=None,
        recorded_by=PrincipalId(side.ids.new_id()),
    )
    with pytest.raises(SkmError) as fk_err, side.uow() as uow:
        uow.repo(CapabilityVerificationRepository).add(unknown_actor)
    assert fk_err.value.code is ErrorCode.INVALID_REFERENCE


@pytest.mark.pg
def test_postgres_capability_verifications_append_only_trigger(pg_side: Side) -> None:
    record = VerificationRecord(
        runtime_id="codex",
        runtime_version="0.42.0",
        record=CapabilityRecord(
            Capability.HEADLESS_EXECUTION,
            CapabilityStatus.NATIVE,
            "codex exec",
            "0.42.0",
            "",
            NOW.date(),
            None,
        ),
        verification_context=None,
        verification_key=None,
        recorded_by=pg_side.owner.principal_id,
    )
    with pg_side.uow() as uow:
        uow.repo(CapabilityVerificationRepository).add(record)
        uow.commit()

    assert pg_side.pg is not None
    with pytest.raises(psycopg.Error):
        pg_side.pg.execute("UPDATE skm_runtimes.capability_verifications SET status = 'unsupported'")
    with pytest.raises(psycopg.Error):
        pg_side.pg.execute("DELETE FROM skm_runtimes.capability_verifications")


def _catalog_resource(side: Side, uow: UnitOfWork) -> ResourceVersionId:
    scope = ScopeRef(ScopeKind.INSTANCE, INSTANCE)
    config = ConfigLoader(settings_registry(), Packs()).effective(
        uow.repo(ConfigStore), uow.repo(ScopeTree), scope
    )
    pack = extensions.publish_runtime_catalog_snapshot(
        uow,
        pack_manifest=pack_payload("catalog", "1.0.0", trust="operator").manifest_text,
        catalog_toml=CATALOG_TOML.format(version="1.0.0"),
        installed_by=side.owner.principal_id,
        clock=side.clock,
        ids=side.ids,
        config=config,
        estimator=FakeEstimator(),
    )
    ref = extensions.resolve_resource(
        uow,
        extensions.ResourceKind.RUNTIME_CATALOG,
        "models",
        config=config,
        pins={"catalog": extensions.PackVersionId(pack.pack_version_id)},
    )
    return ResourceVersionId(ref.resource_version_id)


def test_model_catalog_repository_preserves_null_prices_and_versioned_guidelines(side: Side) -> None:
    model = CanonicalModel("shared-model")
    offering = ProviderModelOffering(
        "grok",
        model.model_id,
        "grok-provider-selector",
        "Shared model",
        128000,
        None,
        ("shared-.*",),
        ModelStatus.CONFIRMED,
        NOW.date(),
        "inventory",
        None,
    )
    priced = replace(
        offering,
        runtime_id="cursor",
        pricing=Pricing(Decimal("0"), Decimal("1.125"), None, Decimal("0"), "USD", NOW.date(), "tariff"),
    )
    with side.uow() as uow:
        version_id = _catalog_resource(side, uow)
        repo = uow.repo(ModelCatalogRepository)
        repo.add_model(model)
        repo.add_model(model)
        repo.upsert_offering(offering)
        repo.upsert_offering(priced)
        guideline = ModelGuideline(
            version_id,
            "grok",
            model.model_id,
            frozenset({ModelClass.FRONTIER}),
            frozenset({RoleId.REVIEWER}),
            "Use for review",
        )
        repo.add_guideline(guideline)
        repo.add_guideline(guideline)
        uow.commit()

    with side.uow(readonly=True) as uow:
        repo = uow.repo(ModelCatalogRepository)
        assert repo.list_models() == (model,)
        assert repo.list_offerings("grok") == (offering,)
        assert repo.list_offerings("cursor") == (priced,)
        assert repo.list_guidelines(version_id) == (guideline,)
        assert repo.list_guidelines(ResourceVersionId(side.ids.new_id())) == ()


def test_host_model_availability_is_host_scoped_fresh_and_monotonic(side: Side) -> None:
    model = CanonicalModel("shared-model")
    observed = HostModelAvailability(
        side.host_a, "grok", model.model_id, Effort.HIGH, NOW, NOW + timedelta(hours=1)
    )
    refreshed = replace(
        observed, observed_at=NOW + timedelta(minutes=10), expires_at=NOW + timedelta(hours=2)
    )
    low = replace(observed, effort=Effort.LOW)
    other = replace(observed, host_id=side.host_b)
    with side.uow() as uow:
        catalog = uow.repo(ModelCatalogRepository)
        catalog.add_model(model)
        catalog.upsert_offering(
            ProviderModelOffering(
                "grok",
                model.model_id,
                model.model_id,
                "Shared model",
                128000,
                None,
                (),
                ModelStatus.CONFIRMED,
                NOW.date(),
                "inventory",
                None,
            )
        )
        offers = uow.repo(HostModelAvailabilityRepository)
        for row in (observed, refreshed, observed, low, other):
            offers.upsert(row)
        uow.commit()

    with side.uow(readonly=True) as uow:
        offers = uow.repo(HostModelAvailabilityRepository)
        assert offers.list_fresh(side.host_a, as_of=NOW) == (low,)
        assert offers.list_fresh(side.host_b, as_of=NOW) == (other,)
        assert offers.list_fresh(side.host_a, as_of=refreshed.observed_at) == (refreshed, low)
        assert offers.list_fresh(side.host_a, as_of=observed.expires_at) == (refreshed,)
        assert offers.list_fresh(side.host_a, as_of=refreshed.expires_at) == ()
