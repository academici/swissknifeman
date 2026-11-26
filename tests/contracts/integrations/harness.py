"""Two-backend harness of the ``integrations`` contract and security suites: memory ∥ PostgreSQL."""

from __future__ import annotations

import itertools
import json
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import datetime, timedelta
from typing import Any, Literal, cast
from uuid import UUID

import psycopg
import pytest

from contracts.extensions.harness import FakeBuiltinPacks, FakeEstimator, pack_payload
from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from skm.adapters.memory.config_store import MemoryConfigStore
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.postgres.access.repositories import PostgresPrincipalRepository, PostgresTokenRepository
from skm.adapters.postgres.config_store import PostgresConfigStore
from skm.adapters.postgres.core.audit import PostgresAuditLog
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.adapters.postgres.integrations import REPOSITORIES as POSTGRES_INTEGRATIONS
from skm.adapters.postgres.policy import REPOSITORIES as POSTGRES_POLICY
from skm.adapters.postgres.uow import PostgresUowFactory
from skm.adapters.postgres.workspace import REPOSITORIES as POSTGRES_WORKSPACE
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import AuditLog, Authorizer, IdempotencyStore
from skm.application_bus.registry import BusRegistry
from skm.bootstrap.adapters import memory_repository_table, postgres_repository_table
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import (
    FileVersionId,
    HostId,
    PrincipalId,
    ProjectId,
    RepositoryId,
    ScopeId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork, UnitOfWorkFactory
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.kernel.tokens import TokenEstimator
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
from skm.modules.artifacts.domain.blob import (
    Blob,
    BlobAvailability,
    BlobId,
    BlobLocation,
    ContentDigest,
    LocationState,
)
from skm.modules.artifacts.domain.classification import Classification
from skm.modules.artifacts.domain.content_safety import SafetyReport
from skm.modules.artifacts.domain.file import File, FileId, FileOrigin, FileState, set_current, trash
from skm.modules.artifacts.domain.file_version import FileVersion, VersionSource, new_version
from skm.modules.artifacts.ports import BlobRepository, FileRepository, FileVersionRepository
from skm.modules.extensions.application.candidate import build_candidate
from skm.modules.extensions.application.install import install_candidate
from skm.modules.extensions.domain.pack import BUILTIN_ORIGIN, PackTrust
from skm.modules.extensions.domain.payload import PackPayload
from skm.modules.extensions.module import MODULE as EXTENSIONS
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.integrations.module import MODULE as INTEGRATIONS
from skm.modules.policy.module import MODULE as POLICY
from skm.modules.runtimes.module import MODULE as RUNTIMES
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.settings.module import MODULE as SETTINGS
from skm.modules.workspace.generated.commands import (
    AttachRepository,
    BindCheckout,
    CreateProject,
    CreateWorkspace,
    HostArch,
    HostOs,
    RegisterHost,
    RegisterHostDefsHostPlatform,
    RegisterRepository,
)
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.public import CheckoutBindingId, normalize_remote
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource, ScopeTree
from support.backend import LockedIds, PostgresTestBackend
from support.pg import TestDatabase
from support.seed import SEED, seed_backend
from unit.policy.application.harness import (
    EVERYTHING,
    NOW,
    FixedPepper,
    Packs,
    schemas,
    settings_registry,
)

__all__ = [
    "HEAD_SHA",
    "INSTANCE",
    "NOW",
    "REMOTE",
    "SeededCheckout",
    "Side",
    "memory_side",
    "pack_payload",
    "pg_side",
    "postgres_side",
    "side",
]

INSTANCE = SEED.instance_id
REMOTE = "https://github.com/acme/skm-demo.git"
HEAD_SHA = "a" * 40
_MODULES = ("access", "workspace", "settings", "policy", "extensions", "runtimes", "integrations")


@dataclass(frozen=True, slots=True)
class SeededCheckout:
    workspace_id: WorkspaceId
    project_id: ProjectId
    host_id: HostId
    repository_id: RepositoryId
    checkout_binding_id: CheckoutBindingId


class _PgBlobRepo:
    """Minimal PostgreSQL reader of ``skm_artifacts`` blobs and locations."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def get(self, blob_id: BlobId) -> Blob:
        row = self._conn.execute(
            "SELECT id, workspace_id, content_digest, size_bytes, detected_media_type, "
            "availability, created_at, verified_at FROM skm_artifacts.blobs WHERE id = %s",
            (UUID(str(blob_id)),),
        ).fetchone()
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "blob not found", details={"kind": "blob"})
        return Blob(
            id=BlobId(cast("UUID", row[0])),
            workspace_id=WorkspaceId(cast("UUID", row[1])),
            digest=ContentDigest(f"sha256:{cast('str', row[2])}"),
            size_bytes=cast("int", row[3]),
            detected_media_type=cast("str", row[4]),
            availability=BlobAvailability(cast("str", row[5])),
            created_at=cast("datetime", row[6]),
            verified_at=cast("datetime | None", row[7]),
        )

    def locations(self, blob_id: BlobId) -> tuple[BlobLocation, ...]:
        rows = self._conn.execute(
            "SELECT blob_id, backend_id, storage_key, storage_version, state, verified_at "
            "FROM skm_artifacts.blob_locations WHERE blob_id = %s",
            (UUID(str(blob_id)),),
        ).fetchall()
        return tuple(
            BlobLocation(
                blob_id=BlobId(cast("UUID", r[0])),
                backend_id=cast("str", r[1]),
                storage_key=cast("str", r[2]),
                storage_version=cast("str | None", r[3]),
                state=LocationState(cast("str", r[4])),
                verified_at=cast("datetime | None", r[5]),
            )
            for r in rows
        )


class _PgFileRepo:
    """Minimal PostgreSQL reader of ``skm_artifacts.files`` for ``require_ready_versions``."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def get(self, file_id: FileId) -> File:
        row = self._conn.execute(
            "SELECT id, workspace_id, project_id, title, origin, classification, "
            "current_version_id, state, row_version, created_at, created_by "
            "FROM skm_artifacts.files WHERE id = %s",
            (UUID(str(file_id)),),
        ).fetchone()
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "file not found", details={"kind": "file"})
        proj_uuid = cast("UUID | None", row[2])
        cur_uuid = cast("UUID | None", row[6])
        return File(
            id=FileId(cast("UUID", row[0])),
            workspace_id=WorkspaceId(cast("UUID", row[1])),
            project_id=None if proj_uuid is None else ProjectId(proj_uuid),
            title=cast("str", row[3]),
            origin=FileOrigin(cast("str", row[4])),
            classification=Classification(cast("str", row[5])),
            current_version_id=None if cur_uuid is None else FileVersionId(cur_uuid),
            state=FileState(cast("str", row[7])),
            row_version=cast("int", row[8]),
            created_at=cast("datetime", row[9]),
            created_by=PrincipalId(cast("UUID", row[10])),
        )


class _PgFileVersionRepo:
    """Minimal PostgreSQL reader of ``skm_artifacts.file_versions`` for ``require_ready_versions``."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def _from_row(self, row: tuple[Any, ...]) -> FileVersion:
        return FileVersion(
            id=FileVersionId(cast("UUID", row[0])),
            workspace_id=WorkspaceId(cast("UUID", row[1])),
            file_id=FileId(cast("UUID", row[2])),
            version_no=cast("int", row[3]),
            blob_id=BlobId(cast("UUID", row[4])),
            original_filename=cast("str", row[5]),
            declared_media_type=cast("str | None", row[6]),
            description=cast("str", row[7]),
            source=VersionSource(kind="capture", ref=None, captured_at=None),
            safety=SafetyReport(findings=(), acknowledged=(), binary=False),
            created_by=PrincipalId(cast("UUID", row[10])),
            created_at=cast("datetime", row[11]),
        )

    def get(self, version_id: FileVersionId) -> FileVersion:
        rows = self.many((version_id,))
        if not rows:
            raise NotFound(ErrorCode.NOT_FOUND, "file_version not found", details={"kind": "file_version"})
        return rows[0]

    def many(self, ids: Sequence[FileVersionId]) -> tuple[FileVersion, ...]:
        if not ids:
            return ()
        uuids = [UUID(str(item)) for item in ids]
        rows = self._conn.execute(
            "SELECT id, workspace_id, file_id, version_no, blob_id, original_filename, "
            "declared_media_type, description, source, safety, created_by, created_at "
            "FROM skm_artifacts.file_versions WHERE id = ANY(%s)",
            (uuids,),
        ).fetchall()
        return tuple(self._from_row(r) for r in rows)


@dataclass
class Side:
    """One backend (memory or PostgreSQL) with the real bus, repositories, and seeding helpers."""

    kind: Literal["memory", "postgres"]
    uow_factory: UnitOfWorkFactory
    clock: FrozenClock
    ids: LockedIds
    bus: Bus
    loader: ConfigLoader
    builtin: FakeBuiltinPacks
    pg: PostgresTestBackend | None = None
    memory: InMemoryBackend | None = None
    people: dict[str, Actor] = field(default_factory=dict[str, Actor])
    requests: Iterator[int] = field(default_factory=lambda: itertools.count(1))
    blob_counter: Iterator[int] = field(default_factory=lambda: itertools.count(1))

    def meta(self, key: str | None = None) -> RequestMeta:
        return RequestMeta(f"req_{next(self.requests):0>26}", Surface.TEST, key, self.clock.now())

    def uow(self, *, readonly: bool = False) -> UnitOfWork:
        return self.uow_factory(self.meta(), readonly=readonly)

    def actor(self, who: Actor | str) -> Actor:
        return self.people[who] if isinstance(who, str) else who

    def run(self, dto: object, actor: Actor | str = "owner", *, key: str | None = None) -> Any:
        return self.bus.dispatch(dto, actor=self.actor(actor), meta=self.meta(key))

    def ask(self, dto: object, actor: Actor | str = "owner") -> Any:
        return self.bus.ask(dto, actor=self.actor(actor), meta=self.meta())

    def tick(self, seconds: float = 1.0) -> None:
        self.clock.advance(timedelta(seconds=seconds))

    def person(
        self,
        name: str,
        roles: Mapping[ScopeId, Role] | None = None,
        *,
        kind: PrincipalKind = PrincipalKind.HUMAN,
    ) -> Actor:
        principal = new_principal(
            principal_id=PrincipalId(self.ids.new_id()),
            kind=kind,
            display_name=name,
            created_by=None,
            now=self.clock.now(),
        )
        with self.uow() as uow:
            uow.repo(PrincipalRepository).add(principal)
            for scope_id, role in (roles or {}).items():
                uow.repo(MembershipRepository).upsert(
                    Membership(scope_id, principal.id, role, None, self.clock.now())
                )
            uow.commit()
        actor = Actor(principal_id=principal.id, kind=kind, display_name=name)
        self.people[name] = actor
        return actor

    def workspace(self, slug: str = "ws-a", title: str = "Workspace A") -> WorkspaceId:
        return WorkspaceId(self.run(CreateWorkspace(slug=slug, title=title)).workspace_id)

    def project(self, workspace_id: WorkspaceId, slug: str = "proj-a", title: str = "Project A") -> ProjectId:
        return ProjectId(
            self.run(CreateProject(workspace_id=workspace_id, slug=slug, title=title)).project_id
        )

    def host(self, name: str = "laptop") -> HostId:
        platform = RegisterHostDefsHostPlatform(os=HostOs.LINUX, arch=HostArch.X86_64)
        return HostId(self.run(RegisterHost(name=name, platform=platform)).host_id)

    def repository(
        self, workspace_id: WorkspaceId, title: str = "repo-a", remote: str = REMOTE
    ) -> RepositoryId:
        return RepositoryId(
            self.run(
                RegisterRepository(
                    workspace_id=workspace_id, title=title, remote_url=remote, external_id=None
                )
            ).repository_id
        )

    def attach(self, project_id: ProjectId, repository_id: RepositoryId, mount_name: str = "main") -> None:
        self.run(
            AttachRepository(
                project_id=UUID(str(project_id)),
                repository_id=UUID(str(repository_id)),
                mount_name=mount_name,
            )
        )

    def bind_checkout(
        self,
        repository_id: RepositoryId,
        host_id: HostId,
        *,
        local_locator: str = "/work/skm-demo",
        remote: str = REMOTE,
    ) -> CheckoutBindingId:
        norm_remote = normalize_remote(remote)
        assert norm_remote is not None
        res = self.run(
            BindCheckout(
                repository_id=UUID(str(repository_id)),
                host_id=UUID(str(host_id)),
                local_locator=local_locator,
                observed_toplevel=local_locator,
                observed_remotes=(norm_remote.value,),
                observed_head=HEAD_SHA,
                observed_dirty=False,
                observed_at=self.clock.now(),
            )
        )
        return CheckoutBindingId(res.binding_id)

    def seed_checkout(self, suffix: str = "a") -> SeededCheckout:
        remote = f"https://github.com/acme/repo-{suffix}.git"
        ws_id = self.workspace(slug=f"ws-{suffix}", title=f"Workspace {suffix}")
        proj_id = self.project(ws_id, slug=f"proj-{suffix}", title=f"Project {suffix}")
        host_id = self.host(name=f"host-{suffix}")
        repo_id = self.repository(ws_id, title=f"repo-{suffix}", remote=remote)
        self.attach(proj_id, repo_id, mount_name="main")
        binding_id = self.bind_checkout(repo_id, host_id, local_locator=f"/work/repo-{suffix}", remote=remote)
        return SeededCheckout(
            workspace_id=ws_id,
            project_id=proj_id,
            host_id=host_id,
            repository_id=repo_id,
            checkout_binding_id=binding_id,
        )

    def set_setting(
        self,
        scope_kind: Literal["instance", "workspace", "project", "host"],
        scope_id: UUID | ScopeId | WorkspaceId | ProjectId | HostId,
        key: str,
        value: JsonValue,
        *,
        actor: Actor | str = "owner",
    ) -> None:
        ref = SetValueDefsScopeRef(
            level=scope_kind,
            scope_id=None if scope_kind == "instance" else UUID(str(scope_id)),
        )
        self.run(
            SetValue(
                scope=ref,
                key=key,
                value=value,
                confirmed=True,
            ),
            actor=actor,
        )

    def install_pack(self, payload: PackPayload) -> None:
        candidate = build_candidate(payload, estimator=FakeEstimator())
        owner = self.actor("owner")
        with self.uow() as uow:
            cfg = self.loader.effective(
                uow.repo(ConfigStore),
                uow.repo(ScopeTree),
                ScopeRef(ScopeKind.INSTANCE, INSTANCE),
            )
            install_candidate(
                candidate,
                origin=BUILTIN_ORIGIN,
                trust=PackTrust.BUILTIN,
                installed_by=owner.principal_id,
                clock=self.clock,
                ids=self.ids,
                config=cfg,
                uow=uow,
                dry_run=False,
            )
            uow.commit()

    def seed_file_version(
        self,
        workspace_id: WorkspaceId,
        project_id: ProjectId | None = None,
        *,
        trashed: bool = False,
        blob_missing: bool = False,
    ) -> FileVersionId:
        idx = next(self.blob_counter)
        hex_digest = f"{idx:064x}"
        now = self.clock.now()
        owner_id = self.actor("owner").principal_id
        blob_id = BlobId(self.ids.new_id())
        file_id = FileId(self.ids.new_id())
        version_id = FileVersionId(self.ids.new_id())
        storage_key = f"objects/{workspace_id}/{hex_digest}"
        availability = BlobAvailability.MISSING if blob_missing else BlobAvailability.AVAILABLE
        loc_state = LocationState.MISSING if blob_missing else LocationState.PRESENT

        if self.kind == "memory":
            blob = Blob(
                id=blob_id,
                workspace_id=workspace_id,
                digest=ContentDigest(f"sha256:{hex_digest}"),
                size_bytes=16,
                detected_media_type="text/plain",
                availability=availability,
                created_at=now,
                verified_at=now,
            )
            location = BlobLocation(
                blob_id=blob_id,
                backend_id="local-primary",
                storage_key=storage_key,
                storage_version=None,
                state=loc_state,
                verified_at=now,
            )
            file_obj = File(
                id=file_id,
                workspace_id=workspace_id,
                project_id=project_id,
                title=f"pre-image-{idx}.txt",
                origin=FileOrigin.CAPTURE,
                classification=Classification.INTERNAL,
                current_version_id=None,
                state=FileState.ACTIVE,
                row_version=1,
                created_at=now,
                created_by=owner_id,
            )
            version_obj = new_version(
                version_id=version_id,
                file=file_obj,
                previous_no=0,
                blob=replace(blob, availability=BlobAvailability.AVAILABLE),
                original_filename=f"pre-image-{idx}.txt",
                declared_media_type="text/plain",
                description="pre-image capture",
                source=VersionSource(kind="capture", ref=None, captured_at=now),
                safety=SafetyReport(findings=(), acknowledged=(), binary=False),
                created_by=owner_id,
                now=now,
            )
            updated_file = set_current(file_obj, version_obj)
            if trashed:
                updated_file = trash(updated_file)
            with self.uow() as uow:
                uow.repo(BlobRepository).add(blob, location)
                uow.repo(FileRepository).add(updated_file)
                uow.repo(FileVersionRepository).add(version_obj)
                uow.commit()
            return version_id

        assert self.pg is not None
        with psycopg.connect(self.pg.database.dsn) as conn, conn.transaction():
            conn.execute(
                "INSERT INTO skm_artifacts.blobs "
                "(id, workspace_id, hash_algorithm, content_digest, size_bytes, detected_media_type, "
                "availability, created_at, verified_at) VALUES (%s, %s, 'sha256', %s, %s, %s, %s, %s, %s)",
                (
                    UUID(str(blob_id)),
                    UUID(str(workspace_id)),
                    hex_digest,
                    16,
                    "text/plain",
                    availability.value,
                    now,
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO skm_artifacts.blob_locations "
                "(workspace_id, blob_id, backend_id, storage_key, storage_version, state, verified_at) "
                "VALUES (%s, %s, 'local-primary', %s, NULL, %s, %s)",
                (UUID(str(workspace_id)), UUID(str(blob_id)), storage_key, loc_state.value, now),
            )
            conn.execute(
                "INSERT INTO skm_artifacts.files "
                "(id, workspace_id, project_id, title, origin, classification, current_version_id, "
                "state, row_version, created_at, created_by, updated_at) "
                "VALUES (%s, %s, %s, %s, 'capture', 'internal', %s, %s, 1, %s, %s, %s)",
                (
                    UUID(str(file_id)),
                    UUID(str(workspace_id)),
                    None if project_id is None else UUID(str(project_id)),
                    f"pre-image-{idx}.txt",
                    UUID(str(version_id)),
                    "trashed" if trashed else "active",
                    now,
                    UUID(str(owner_id)),
                    now,
                ),
            )
            conn.execute(
                "INSERT INTO skm_artifacts.file_versions "
                "(id, workspace_id, file_id, version_no, blob_id, original_filename, "
                "declared_media_type, description, source, safety, created_by, created_at) "
                "VALUES (%s, %s, %s, 1, %s, %s, 'text/plain', 'pre-image capture', "
                "%s::jsonb, %s::jsonb, %s, %s)",
                (
                    UUID(str(version_id)),
                    UUID(str(workspace_id)),
                    UUID(str(file_id)),
                    UUID(str(blob_id)),
                    f"pre-image-{idx}.txt",
                    json.dumps({"kind": "capture", "ref": None, "captured_at": now.isoformat()}),
                    json.dumps({"findings": [], "acknowledged": [], "binary": False}),
                    UUID(str(owner_id)),
                    now,
                ),
            )
        return version_id

    def events(self, event_urn: str | None = None) -> list[tuple[str, dict[str, Any]]]:
        if self.memory is not None:
            found = [(e.type, dict(e.payload)) for e in self.memory.committed.core.events]
        else:
            assert self.pg is not None
            rows = self.pg.execute(
                "SELECT event_type, payload FROM skm_core.domain_events "
                "ORDER BY recorded_at, stream_kind, stream_id, stream_seq"
            )
            found = [(cast("str", row[0]), cast("dict[str, Any]", row[1])) for row in rows]
        if event_urn is None:
            return found
        return [item for item in found if item[0] == event_urn]

    def close(self) -> None:
        if self.pg is not None:
            self.pg.close()


def _registry() -> BusRegistry:
    return BusRegistry.build(
        (ACCESS, WORKSPACE, SETTINGS, POLICY, EXTENSIONS, RUNTIMES, INTEGRATIONS),
        schemas=schemas(),
        permission_catalog=EVERYTHING,
        disabled_modules=frozenset(),
    )


def _bus(
    uow_factory: UnitOfWorkFactory,
    registry: BusRegistry,
    clock: FrozenClock,
    ids: LockedIds,
    packs: Packs,
    builtin: FakeBuiltinPacks,
) -> tuple[Bus, ConfigLoader]:
    loader = ConfigLoader(settings_registry(), packs)
    bus = Bus(
        registry=registry,
        schemas=schemas(),
        uow_factory=uow_factory,
        authorizer=RbacAuthorizer(clock),
        scopes=FakeScopeChain(),
        config=loader,
        clock=clock,
        ids=ids,
        entropy=DeterministicEntropy(),
        gateways=GatewayTable(
            {
                TokenPepperSource: FixedPepper(),
                TokenEstimator: FakeEstimator(),
                BuiltinPacks: builtin,
            },
            "control_plane_gateway",
        ),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )
    return bus, loader


def memory_side() -> Side:
    registry, clock, ids = _registry(), FrozenClock(NOW), LockedIds()
    packs, authorizer, builtin = Packs(), RbacAuthorizer(clock), FakeBuiltinPacks()
    mem_modules = (*_MODULES, "artifacts")
    factories: dict[type, Callable[[Any], object]] = {
        **cast("Mapping[type, Callable[[Any], object]]", memory_repository_table(mem_modules)),
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
    bus, loader = _bus(uow_factory, registry, clock, ids, packs, builtin)
    made = Side("memory", uow_factory, clock, ids, bus, loader, builtin, memory=backend)
    made.person("owner", {INSTANCE: Role.OWNER})
    return made


def postgres_side(database: TestDatabase) -> Side:
    registry, clock, ids = _registry(), FrozenClock(NOW), LockedIds()
    packs, authorizer, builtin = Packs(), RbacAuthorizer(clock), FakeBuiltinPacks()
    pg = PostgresTestBackend(database, pool_max_size=8)
    clocked_ws = {
        port: (lambda conn, adapter=adapter: adapter(conn, clock=clock))
        for port, adapter in cast("Mapping[type, Any]", POSTGRES_WORKSPACE).items()
    }
    clocked_int = {
        port: (lambda conn, adapter=adapter: adapter(conn, clock=clock))
        for port, adapter in cast("Mapping[type, Any]", POSTGRES_INTEGRATIONS).items()
    }
    clocked_policy = {
        port: (lambda conn, adapter=adapter: adapter(conn, clock=clock))
        for port, adapter in cast("Mapping[type, Any]", POSTGRES_POLICY).items()
        if port.__name__ == "ToolIntentRepository"
    }
    factories: dict[type, Callable[[psycopg.Connection], object]] = {
        **cast(
            "Mapping[type, Callable[[psycopg.Connection], object]]",
            postgres_repository_table(_MODULES),
        ),
        **clocked_ws,
        **clocked_int,
        **clocked_policy,
        PrincipalRepository: lambda conn: PostgresPrincipalRepository(conn, clock=clock),
        TokenRepository: lambda conn: PostgresTokenRepository(conn, clock=clock),
        BlobRepository: _PgBlobRepo,
        FileRepository: _PgFileRepo,
        FileVersionRepository: _PgFileVersionRepo,
        IdempotencyStore: PostgresIdempotencyStore,
        AuditLog: PostgresAuditLog,
        ConfigStore: PostgresConfigStore,
        PackConfigSource: lambda _conn: packs,
        Authorizer: lambda _conn: authorizer,
    }
    writer = PostgresEventWriter(schemas=schemas(), subscriptions=registry.subscription_index(), ids=ids)
    uow_factory = PostgresUowFactory(pg.pool, factories, writer, clock)
    bus, loader = _bus(uow_factory, registry, clock, ids, packs, builtin)
    made = Side("postgres", uow_factory, clock, ids, bus, loader, builtin, pg=pg)
    made.person("owner", {INSTANCE: Role.OWNER})
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


@pytest.fixture
def pg_side(clean_test_database: TestDatabase) -> Iterator[Side]:
    made = postgres_side(clean_test_database)
    try:
        yield made
    finally:
        made.close()
