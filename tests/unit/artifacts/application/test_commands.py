"""Artifact commands over the real bus and the memory backend (artifacts §7, §15).

The bus, the config loader over the packaged sections, the memory repositories of ``access``, ``workspace``
and ``artifacts``, the memory ``BlobStore`` gateway and the production authorizer are real; ids, clock and
entropy are deterministic. People and staged blobs are seeded as domain values, never through a handler under
test, so a failing command cannot be blamed on its own setup. ``record_staged_blob`` (the upload
coordinator) is another leaf: a staged blob here is promoted bytes plus its ``staged_blobs`` row.

This module also owns the harness the grant and content tests import (the write set has no conftest).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.app import FakeScopeChain
from fakes.clock import FrozenClock
from fakes.entropy import DeterministicEntropy
from fakes.ids import SequentialIds
from skm.adapters.memory.access import REPOSITORIES as ACCESS_REPOSITORIES
from skm.adapters.memory.artifacts import REPOSITORIES as ARTIFACT_REPOSITORIES
from skm.adapters.memory.artifacts.state import artifacts_state
from skm.adapters.memory.blob_store import MemoryBlobStore
from skm.adapters.memory.config_store import (
    MemoryConfigStore,
    increment_config_generation,
    write_config_entry,
)
from skm.adapters.memory.core import REPOSITORIES as CORE_REPOSITORIES
from skm.adapters.memory.uow import InMemoryBackend
from skm.adapters.memory.workspace import REPOSITORIES as WORKSPACE_REPOSITORIES
from skm.application_bus.bus import Bus, RetryPolicy
from skm.application_bus.ports import Authorizer
from skm.application_bus.registry import BusRegistry
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.domain.token import ApiToken, TokenId, TokenKind, grant_of
from skm.modules.access.module import MODULE as ACCESS
from skm.modules.access.permissions import PERMISSIONS as CATALOG
from skm.modules.access.ports import (
    MembershipRepository,
    PrincipalRepository,
    TokenPepperSource,
    TokenRepository,
)
from skm.modules.access.public import RbacAuthorizer, Role
from skm.modules.artifacts.domain.blob import ContentDigest
from skm.modules.artifacts.domain.staged_blob import StagedBlob, StagedBlobId
from skm.modules.artifacts.domain.upload_rules import detect_media_type
from skm.modules.artifacts.generated import commands as wire
from skm.modules.artifacts.module import MODULE as ARTIFACTS
from skm.modules.artifacts.ports import BlobStore, StagedBlobRepository
from skm.modules.artifacts.public import (
    AddFile,
    AddFileVersion,
    GetFile,
    RestoreFile,
    TrashFile,
)
from skm.modules.workspace.module import MODULE as WORKSPACE
from skm.modules.workspace.public import ArchiveProject, ArchiveWorkspace, CreateProject, CreateWorkspace
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.store import ConfigStore, PackConfigSource, StoredContribution
from support.registries import schemas, settings_registry

NOW = datetime(2026, 10, 29, 12, 0, tzinfo=UTC)
PEPPER = bytes(range(32))
EVERYTHING = frozenset(CATALOG)
TEXT = b"hello artifacts\n"
SOURCE = wire.AddFileDefsVersionSource(kind="upload")
SOURCE_V = wire.AddFileVersionDefsVersionSource(kind="upload")


class FixedPepper:
    def pepper(self) -> bytes:
        return PEPPER


class Packs:
    def generation(self) -> int:
        return 0

    def fragments(self, scope_chain: object) -> tuple[()]:
        return ()


class _Trickle:
    """A stream that hands out at most ``chunk`` bytes per ``read`` call before its end, like a pipe."""

    def __init__(self, inner: Any, chunk: int) -> None:
        self._inner, self._chunk = inner, chunk

    def read(self, size: int = -1) -> bytes:
        return self._inner.read(self._chunk if size < 0 else min(size, self._chunk))

    def __enter__(self) -> "_Trickle":
        return self

    def __exit__(self, *_exc: object) -> None:
        self._inner.close()


class TrickleStore:
    """``BlobStore`` view of ``store`` whose streams return short reads; everything else is delegated."""

    def __init__(self, store: Any, chunk: int = 3) -> None:
        self._store, self._chunk = store, chunk

    def open(self, location: Any) -> _Trickle:
        return _Trickle(self._store.open(location), self._chunk)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._store, name)


@dataclass(frozen=True)
class Staged:
    """One staged blob: the ids a ref carries, convertible to the ref type of each command."""

    id: StagedBlobId
    workspace_id: WorkspaceId
    digest: str
    size: int
    media_type: str
    storage_key: str

    def _fields(self, **changes: Any) -> dict[str, Any]:
        fields: dict[str, Any] = {
            "staged_blob_id": self.id,
            "workspace_id": self.workspace_id,
            "digest": self.digest,
            "size": self.size,
            "media_type": self.media_type,
        }
        return {**fields, **changes}

    def ref(self, **changes: Any) -> wire.AddFileDefsStagedBlobRef:
        return wire.AddFileDefsStagedBlobRef(**self._fields(**changes))

    def version_ref(self, **changes: Any) -> wire.AddFileVersionDefsStagedBlobRef:
        return wire.AddFileVersionDefsStagedBlobRef(**self._fields(**changes))


@dataclass
class World:
    backend: InMemoryBackend
    bus: Bus
    clock: FrozenClock
    ids: SequentialIds
    blobs: MemoryBlobStore
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

    def refused(self, code: ErrorCode, fn: Callable[[], object]) -> SkmError:
        """``fn`` must fail with ``code`` and leave every table and the event log untouched."""
        before = self.snapshot()
        with pytest.raises(SkmError) as caught:
            fn()
        assert caught.value.code is code
        assert self.snapshot() == before
        return caught.value

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

    def worker(self, name: str, workspace_id: WorkspaceId) -> Actor:
        """A worker principal with the ``worker`` role on the workspace (which holds ``file.read`` and
        ``file.write``: only the artifacts handler keeps a worker from changing a logical file)."""
        return self.person(name, {ScopeId(workspace_id): Role.WORKER}, kind=PrincipalKind.WORKER)

    def token_actor(
        self,
        who: Actor | str,
        *,
        permissions: frozenset[str] | None,
        scope: ScopeId | None = None,
        assignment: UUID | None = None,
        serial: int = 1,
    ) -> Actor:
        """``who`` authenticated by a live token row: personal (human), worker or assignment (worker).

        The row is stored, so the bus admits it like a real credential (access §4.6); an assignment token is
        bound to ``assignment`` and to the run scope ``scope`` (whose ancestors the grant lists).
        """
        base = self.actor(who)
        kind = TokenKind.PERSONAL if base.kind is not PrincipalKind.WORKER else TokenKind.WORKER
        step = None
        if assignment is not None:
            kind, step = TokenKind.ASSIGNMENT, UUID(int=0x5700 + serial)
        token_id = TokenId(UUID(int=0x7000 + serial))
        now = self.clock.now()
        row = ApiToken(
            id=token_id,
            principal_id=base.principal_id,
            kind=kind,
            name=f"token-{serial}",
            prefix=f"tok{serial:05d}".translate(str.maketrans("0189", "abcd")),
            secret_hash=bytes(32),
            scope_id=scope,
            permissions=permissions,
            expires_at=None if kind is TokenKind.PERSONAL else now + timedelta(days=1),
            created_at=now,
            created_by=base.principal_id,
            last_used_at=None,
            revoked_at=None,
            revoked_by=None,
            assignment_id=assignment,
            step_id=step,
            superseded_by=None,
        )
        with self.uow() as uow:
            uow.repo(TokenRepository).add(row)
            if scope is not None:
                chain = uow.repo(ScopeRegistry).ancestors(scope)
                ancestors = tuple(ScopeId(item.id) for item in chain[:-1])
            else:
                ancestors = ()
            uow.commit()
        return Actor(
            base.principal_id, base.kind, base.display_name, grant_of(row, scope_ancestors=ancestors)
        )

    def run_scope(self, workspace_id: WorkspaceId, project_id: ProjectId, serial: int = 1) -> ScopeId:
        """A plan and a run scope below the project: the scope of an assignment token."""
        plan, run = ScopeId(UUID(int=0x9100 + serial)), ScopeId(UUID(int=0x9200 + serial))
        with self.uow() as uow:
            scopes = uow.repo(ScopeRegistry)
            scopes.create(plan, ScopeKind.PLAN, parent=ScopeId(project_id), workspace_id=workspace_id)
            scopes.create(run, ScopeKind.RUN, parent=plan, workspace_id=workspace_id)
            uow.commit()
        return run

    def configure(self, scope_id: UUID, key: str, value: Any) -> None:
        """Write one level entry of ``scope_id`` straight into the committed config tables."""
        state = self.backend.committed
        write_config_entry(
            state,
            scope_id,
            StoredContribution(
                entry_id=UUID(int=0xC000 + state.core.config_generation + 1),
                key=key,
                op="set",
                value=value,
                locked=False,
                row_version=1,
            ),
        )
        increment_config_generation(state)

    def workspace(self, slug: str = "personal", title: str = "Personal") -> WorkspaceId:
        return WorkspaceId(self.run(CreateWorkspace(slug=slug, title=title)).workspace_id)

    def project(self, workspace_id: WorkspaceId, slug: str = "skm", title: str = "SKM") -> ProjectId:
        return ProjectId(
            self.run(CreateProject(workspace_id=workspace_id, slug=slug, title=title)).project_id
        )

    def stage(
        self,
        workspace_id: WorkspaceId,
        data: bytes = TEXT,
        *,
        media_type: str = "text/plain",
        ttl: timedelta = timedelta(hours=24),
    ) -> Staged:
        """Bytes promoted into the memory store plus the ``staged_blobs`` row of ``record_staged_blob``."""
        handle = self.blobs.stage(workspace_id, [data])
        location = self.blobs.promote(handle, expected_digest=handle.digest)
        now = self.clock.now()
        staged = StagedBlob(
            id=StagedBlobId(self.ids.new_id()),
            workspace_id=workspace_id,
            digest=ContentDigest(handle.digest),
            size_bytes=handle.size_bytes,
            media_type=media_type,
            detected_media_type=detect_media_type(data[:4096]),
            backend_id=cast("str", location["backend_id"]),
            storage_key=cast("str", location["storage_key"]),
            created_by=self.people["owner"].principal_id,
            created_at=now,
            expires_at=now + ttl,
            consumed_at=None,
            consumed_request_id=None,
        )
        with self.uow() as uow:
            uow.repo(StagedBlobRepository).add(staged)
            uow.commit()
        return Staged(
            staged.id, workspace_id, handle.digest, handle.size_bytes, media_type, staged.storage_key
        )

    def add_file(
        self,
        workspace_id: WorkspaceId,
        staged: Staged,
        *,
        project_id: ProjectId | None = None,
        title: str = "notes",
        filename: str = "notes.txt",
        actor: Actor | str = "owner",
        key: str | None = None,
        **changes: Any,
    ) -> Any:
        fields: dict[str, Any] = {
            "workspace_id": workspace_id,
            "project_id": project_id,
            "title": title,
            "origin": wire.FileOrigin.UPLOAD,
            "blob": staged.ref(),
            "original_filename": filename,
            "source": SOURCE,
        }
        return self.run(AddFile(**{**fields, **changes}), actor, key=key)

    def add_version(
        self,
        file_id: UUID,
        staged: Staged,
        *,
        version: int,
        filename: str = "notes.txt",
        actor: Actor | str = "owner",
        **changes: Any,
    ) -> Any:
        fields: dict[str, Any] = {
            "file_id": file_id,
            "expected_row_version": version,
            "blob": staged.version_ref(),
            "original_filename": filename,
            "declared_media_type": None,
            "source": SOURCE_V,
        }
        return self.run(AddFileVersion(**{**fields, **changes}), actor)

    # ------------------------------------------------------------------ observations
    def events(self, name: str | None = None) -> list[Any]:
        found = list(self.backend.committed.core.events)
        if name is None:
            return found
        return [e for e in found if e.type == f"urn:skm:artifacts:event:{name}:v1"]

    def tables(self) -> Any:
        return artifacts_state(self.backend.committed)

    def snapshot(self) -> tuple[object, ...]:
        """Everything a refused command must leave untouched."""
        tables = self.tables()
        return (
            dict(tables.staged),
            dict(tables.blobs),
            dict(tables.locations),
            dict(tables.files),
            dict(tables.versions),
            dict(tables.grants),
            len(self.backend.committed.core.events),
        )

    def staged_row(self, staged: Staged) -> StagedBlob:
        return self.tables().staged[staged.id]


def build_world(*, scan_chunk: int | None = None) -> World:
    """``scan_chunk`` gives the streams of the handlers' ``BlobStore`` gateway short reads of that size."""
    bus_registry = BusRegistry.build(
        (ACCESS, WORKSPACE, ARTIFACTS),
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
        **ARTIFACT_REPOSITORIES,
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
    blobs = MemoryBlobStore(clock, max_bytes=1 << 20)
    gateway_store = blobs if scan_chunk is None else TrickleStore(blobs, scan_chunk)
    artifacts_state(backend.committed).store.bind(blobs)  # the host injects the store into the unit of work
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
        gateways=GatewayTable(
            {TokenPepperSource: FixedPepper(), BlobStore: cast("BlobStore", gateway_store)},
            "control_plane_gateway",
        ),
        retry=RetryPolicy(max_attempts=1, base_delay_seconds=0.0, max_delay_seconds=0.0),
        idempotency_ttl=timedelta(hours=1),
    )
    instance = ScopeId(UUID("01900000-0000-7000-8000-000000000001"))
    made = World(backend, bus, clock, ids, blobs, instance)
    with made.uow() as uow:
        uow.repo(ScopeRegistry).create(instance, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        uow.commit()
    made.person("owner", {instance: Role.OWNER})
    return made


@pytest.fixture
def world() -> World:
    return build_world()


@dataclass
class Setup:
    """Two workspaces, a project in the first, a viewer and an outsider."""

    world: World
    ws: WorkspaceId = field(init=False)
    other_ws: WorkspaceId = field(init=False)
    project: ProjectId = field(init=False)

    def __post_init__(self) -> None:
        world = self.world
        self.ws = world.workspace("personal")
        self.other_ws = world.workspace("other")
        self.project = world.project(self.ws)
        world.person("viewer", {ScopeId(self.ws): Role.VIEWER})
        world.person("outsider")


@pytest.fixture
def setup(world: World) -> Setup:
    return Setup(world)


# ---------------------------------------------------------------------------------------------- add_file
def test_add_file_creates_file_version_one_blob_and_events(world: World, setup: Setup) -> None:
    staged = world.stage(setup.ws)
    result = world.add_file(setup.ws, staged, project_id=setup.project, classification="internal")
    assert (result.version_no, result.classification.value, result.safety.verdict) == (1, "internal", "ok")
    tables = world.tables()
    [file] = tables.files.values()
    [version] = tables.versions.values()
    assert (file.id, file.current_version_id, file.row_version) == (result.file_id, version.id, 2)
    assert (file.project_id, file.workspace_id, version.version_no) == (setup.project, setup.ws, 1)
    assert version.original_filename == "notes.txt"
    [blob] = tables.blobs.values()
    [location] = tables.locations[blob.id]
    assert (blob.digest.value, blob.size_bytes) == (staged.digest, len(TEXT))
    assert location.storage_key == staged.storage_key
    consumed = world.staged_row(staged)
    assert consumed.consumed_at == NOW
    assert consumed.consumed_request_id is not None
    [added] = world.events("file-added")
    assert added.payload["file_id"] == str(file.id)
    assert added.payload["project_id"] == str(setup.project)
    [version_added] = world.events("file-version-added")
    assert version_added.payload["digest"] == staged.digest
    assert version_added.payload["version_no"] == 1
    assert "storage_key" not in version_added.payload
    assert "blob_id" not in version_added.payload


def test_add_file_without_project_makes_a_workspace_level_file(world: World, setup: Setup) -> None:
    result = world.add_file(setup.ws, world.stage(setup.ws))
    assert world.tables().files[result.file_id].project_id is None


def test_a_repeated_request_with_the_same_key_answers_from_the_receipt(world: World, setup: Setup) -> None:
    staged = world.stage(setup.ws)
    first = world.add_file(setup.ws, staged, key="k1")
    again = world.add_file(setup.ws, staged, key="k1")
    assert again == first
    assert len(world.tables().files) == 1
    assert len(world.events("file-added")) == 1


def test_equal_bytes_share_a_blob_inside_one_workspace_only(world: World, setup: Setup) -> None:
    a = world.add_file(setup.ws, world.stage(setup.ws), title="a")
    b = world.add_file(setup.ws, world.stage(setup.ws), title="b")
    c = world.add_file(setup.other_ws, world.stage(setup.other_ws), title="c")
    tables = world.tables()
    assert len({a.file_id, b.file_id, c.file_id}) == 3
    assert len(tables.files) == 3
    assert len(tables.versions) == 3
    assert len(tables.blobs) == 2  # one per workspace: the same digest in another workspace is another blob
    in_ws = [blob for blob in tables.blobs.values() if blob.workspace_id == setup.ws]
    assert len(in_ws) == 1
    assert {v.blob_id for v in tables.versions.values() if v.file_id in {a.file_id, b.file_id}} == {
        in_ws[0].id
    }


def test_a_filename_that_is_not_valid_is_refused_before_any_side_effect(world: World, setup: Setup) -> None:
    staged = world.stage(setup.ws)
    long_name = "я" * 128  # 128 code points pass the schema, 256 bytes do not pass validate_filename
    error = world.refused(
        ErrorCode.SCHEMA_INVALID, lambda: world.add_file(setup.ws, staged, filename=long_name)
    )
    assert error.details["field"] == "original_filename"
    assert world.staged_row(staged).consumed_at is None
    world.add_file(setup.ws, staged)  # the same staged blob is still usable


def test_the_filename_is_checked_before_the_staged_blob_and_the_admission_are_looked_at(
    world: World, setup: Setup
) -> None:
    """Order, not just rollback: a bad name wins over a consumed blob, a gone object and a closed project."""
    long_name = "я" * 128
    used = world.stage(setup.ws)
    world.add_file(setup.ws, used, title="used")
    world.refused(ErrorCode.SCHEMA_INVALID, lambda: world.add_file(setup.ws, used, filename=long_name))
    gone = world.stage(setup.ws, b"gone\n")
    world.blobs.delete_unreferenced({"backend_id": "local-primary", "storage_key": gone.storage_key})
    world.refused(ErrorCode.SCHEMA_INVALID, lambda: world.add_file(setup.ws, gone, filename=long_name))
    world.run(ArchiveProject(project_id=setup.project, expected_row_version=1, reason="done"))
    fresh = world.stage(setup.ws, b"fresh\n")
    world.refused(
        ErrorCode.SCHEMA_INVALID,
        lambda: world.add_file(setup.ws, fresh, project_id=setup.project, filename=long_name),
    )


def test_a_worker_cannot_create_a_file_even_with_file_write(world: World, setup: Setup) -> None:
    worker = world.worker("w1", setup.ws)
    staged = world.stage(setup.ws)
    error = world.refused(ErrorCode.FORBIDDEN, lambda: world.add_file(setup.ws, staged, actor=worker))
    assert world.staged_row(staged).consumed_at is None
    assert error.code is ErrorCode.FORBIDDEN


def test_a_viewer_and_an_outsider_cannot_write(world: World, setup: Setup) -> None:
    for who in ("viewer", "outsider"):
        staged = world.stage(setup.ws)
        world.refused(
            ErrorCode.FORBIDDEN, lambda staged=staged, who=who: world.add_file(setup.ws, staged, actor=who)
        )


def test_a_project_of_another_workspace_is_refused(world: World, setup: Setup) -> None:
    staged = world.stage(setup.other_ws)
    error = world.refused(
        ErrorCode.FORBIDDEN, lambda: world.add_file(setup.other_ws, staged, project_id=setup.project)
    )
    assert error.details["reason"] == "other_workspace"


def test_an_archived_project_or_workspace_admits_no_new_file(world: World, setup: Setup) -> None:
    world.run(ArchiveProject(project_id=setup.project, expected_row_version=1, reason="done"))
    staged = world.stage(setup.ws)
    world.refused(
        ErrorCode.PROJECT_ARCHIVED, lambda: world.add_file(setup.ws, staged, project_id=setup.project)
    )
    world.run(ArchiveWorkspace(workspace_id=setup.ws, expected_row_version=1, reason="closed"))
    world.refused(ErrorCode.PROJECT_ARCHIVED, lambda: world.add_file(setup.ws, staged))


# ---------------------------------------------------------------------------------------------- staged
def test_a_staged_blob_is_consumed_once_by_one_request(world: World, setup: Setup) -> None:
    staged = world.stage(setup.ws)
    world.add_file(setup.ws, staged, title="first")
    world.refused(ErrorCode.STAGED_BLOB_CONSUMED, lambda: world.add_file(setup.ws, staged, title="second"))
    assert len(world.tables().files) == 1


def test_a_staged_blob_of_another_workspace_is_forbidden(world: World, setup: Setup) -> None:
    staged = world.stage(setup.other_ws)
    ref = staged.ref(workspace_id=setup.ws)  # the ref lies about the workspace; the row knows better
    error = world.refused(ErrorCode.FORBIDDEN, lambda: world.add_file(setup.ws, staged, blob=ref))
    assert error.details["reason"] == "other_workspace"
    assert world.staged_row(staged).consumed_at is None


def test_a_ref_that_does_not_match_the_staged_bytes_is_refused(world: World, setup: Setup) -> None:
    staged = world.stage(setup.ws)
    other = world.stage(setup.ws, b"other bytes\n")
    world.refused(
        ErrorCode.BLOB_DIGEST_MISMATCH,
        lambda: world.add_file(setup.ws, staged, blob=staged.ref(digest=other.digest)),
    )
    world.refused(
        ErrorCode.BLOB_DIGEST_MISMATCH,
        lambda: world.add_file(setup.ws, staged, blob=staged.ref(size=staged.size + 1)),
    )


def test_an_expired_staged_blob_is_refused(world: World, setup: Setup) -> None:
    staged = world.stage(setup.ws, ttl=timedelta(hours=1))
    world.clock.advance(timedelta(hours=1))
    world.refused(ErrorCode.STAGED_BLOB_EXPIRED, lambda: world.add_file(setup.ws, staged))


def test_an_unknown_staged_blob_is_not_found(world: World, setup: Setup) -> None:
    staged = world.stage(setup.ws)
    unknown = staged.ref(staged_blob_id=UUID(int=7))
    world.refused(ErrorCode.NOT_FOUND, lambda: world.add_file(setup.ws, staged, blob=unknown))


def test_a_forged_ref_whose_object_is_gone_is_not_ready(world: World, setup: Setup) -> None:
    staged = world.stage(setup.ws)
    world.blobs.delete_unreferenced({"backend_id": "local-primary", "storage_key": staged.storage_key})
    world.refused(ErrorCode.FILE_VERSION_NOT_READY, lambda: world.add_file(setup.ws, staged))
    assert world.staged_row(staged).consumed_at is None  # the rollback leaves it staged


# ---------------------------------------------------------------------------------------------- safety
def test_a_secret_named_file_needs_an_acknowledgement_and_a_high_classification(
    world: World, setup: Setup
) -> None:
    staged = world.stage(setup.ws, b"DEBUG=1\n")  # secret only by its name
    error = world.refused(ErrorCode.CONTENT_UNSAFE, lambda: world.add_file(setup.ws, staged, filename=".env"))
    assert error.details["reason"] == "not_acknowledged"
    assert world.staged_row(staged).consumed_at is None
    low = world.refused(
        ErrorCode.CONTENT_UNSAFE,
        lambda: world.add_file(setup.ws, staged, filename=".env", acknowledge=("CS-SECRET-NAME",)),
    )
    assert low.details["reason"] == "classification_below_acknowledge_minimum"
    result = world.add_file(
        setup.ws,
        staged,
        filename=".env",
        acknowledge=("CS-SECRET-NAME",),
        classification=wire.Classification.CONFIDENTIAL,
    )
    assert result.safety.acknowledged == ("CS-SECRET-NAME",)
    assert result.classification.value == "confidential"


def test_a_secret_in_the_content_is_found_through_the_gateway(world: World, setup: Setup) -> None:
    secret = b"key = ghp_" + b"a1B2" * 9 + b"\n"
    staged = world.stage(setup.ws, secret)
    error = world.refused(ErrorCode.CONTENT_UNSAFE, lambda: world.add_file(setup.ws, staged))
    assert "ghp_" not in str(error.details)  # a finding never carries the matched value


def test_evidence_with_a_block_finding_is_kept_as_restricted(world: World, setup: Setup) -> None:
    staged = world.stage(setup.ws, b"TOKEN=placeholder\n")
    result = world.add_file(setup.ws, staged, filename=".env", origin=wire.FileOrigin.EVIDENCE)
    assert result.classification.value == "restricted"
    assert result.safety.verdict == "block"


def test_a_media_mismatch_warns_and_raises_public_to_internal(world: World, setup: Setup) -> None:
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    staged = world.stage(setup.ws, png, media_type="image/png")
    result = world.add_file(
        setup.ws, staged, filename="p.png", declared_media_type="text/plain", classification="public"
    )
    assert result.classification.value == "internal"
    assert [f.rule for f in result.safety.findings if f.level == "warn"] == ["CS-MEDIA-MISMATCH"]


# ---------------------------------------------------------------------------------------------- versions
def test_versions_are_sequential_immutable_and_move_the_current_pointer(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws), project_id=setup.project)
    before = dict(world.tables().versions)
    second = world.add_version(first.file_id, world.stage(setup.ws, b"v2\n"), version=2)
    third = world.add_version(first.file_id, world.stage(setup.ws, b"v3\n"), version=3, filename="n3.txt")
    assert (second.version_no, third.version_no) == (2, 3)
    tables = world.tables()
    for version_id, row in before.items():
        assert tables.versions[version_id] == row  # an older version is never rewritten
    assert tables.files[first.file_id].current_version_id == third.file_version_id
    numbers = sorted(v.version_no for v in tables.versions.values() if v.file_id == first.file_id)
    assert numbers == [1, 2, 3]
    assert len(world.events("file-version-added")) == 3


def test_a_stale_expected_version_is_a_conflict_that_burns_nothing(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    staged = world.stage(setup.ws, b"v2\n")
    world.refused(ErrorCode.VERSION_CONFLICT, lambda: world.add_version(first.file_id, staged, version=1))
    assert world.staged_row(staged).consumed_at is None
    assert world.add_version(first.file_id, staged, version=2).version_no == 2  # the number was not burnt


def test_a_rejected_version_does_not_consume_a_number(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    unsafe = world.stage(setup.ws, b"DEBUG=1\n")
    world.refused(
        ErrorCode.CONTENT_UNSAFE, lambda: world.add_version(first.file_id, unsafe, version=2, filename=".env")
    )
    assert world.add_version(first.file_id, world.stage(setup.ws, b"v2\n"), version=2).version_no == 2


def test_classification_of_a_file_only_rises(world: World, setup: Setup) -> None:
    secret = world.add_file(
        setup.ws, world.stage(setup.ws), classification=wire.Classification.CONFIDENTIAL, title="secret"
    )
    world.add_version(secret.file_id, world.stage(setup.ws, b"v2\n"), version=2)
    assert world.tables().files[secret.file_id].classification.value == "confidential"  # never lowered
    public = world.add_file(setup.ws, world.stage(setup.ws, b"p1\n"), classification="public", title="p")
    assert world.tables().files[public.file_id].classification.value == "public"
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16  # a declared/detected mismatch is a G21 warning: floor internal
    world.add_version(
        public.file_id,
        world.stage(setup.ws, png, media_type="image/png"),
        version=2,
        filename="p.png",
        declared_media_type="text/plain",
    )
    assert world.tables().files[public.file_id].classification.value == "internal"


def test_an_evidence_version_with_a_block_finding_raises_the_file_to_restricted(
    world: World, setup: Setup
) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws), origin=wire.FileOrigin.EVIDENCE, title="ev")
    world.add_version(first.file_id, world.stage(setup.ws, b"TOKEN=x\n"), version=2, filename=".env")
    assert world.tables().files[first.file_id].classification.value == "restricted"


def test_a_worker_cannot_add_a_version(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    worker = world.worker("w1", setup.ws)
    staged = world.stage(setup.ws, b"v2\n")
    world.refused(
        ErrorCode.FORBIDDEN, lambda: world.add_version(first.file_id, staged, version=2, actor=worker)
    )


def test_a_viewer_cannot_add_a_version(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws), project_id=setup.project)
    staged = world.stage(setup.ws, b"v2\n")
    world.refused(
        ErrorCode.FORBIDDEN, lambda: world.add_version(first.file_id, staged, version=2, actor="viewer")
    )


def test_a_version_filename_is_validated_before_the_staged_blob_is_consumed(
    world: World, setup: Setup
) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    long_name = "я" * 128
    staged = world.stage(setup.ws, b"v2\n")
    world.refused(
        ErrorCode.SCHEMA_INVALID,
        lambda: world.add_version(first.file_id, staged, version=2, filename=long_name),
    )
    assert world.staged_row(staged).consumed_at is None
    used = world.stage(setup.ws, b"v2 used\n")
    world.add_version(first.file_id, used, version=2)
    world.refused(  # a consumed blob and a stale version still lose against the bad name
        ErrorCode.SCHEMA_INVALID,
        lambda: world.add_version(first.file_id, used, version=2, filename=long_name),
    )


def test_a_staged_blob_of_another_workspace_cannot_become_a_version(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    foreign = world.stage(setup.other_ws, b"v2\n")
    world.refused(ErrorCode.FORBIDDEN, lambda: world.add_version(first.file_id, foreign, version=2))


# ---------------------------------------------------------------------------------------------- trash
def test_trash_and_restore_are_logical_and_touch_no_bytes(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws), project_id=setup.project)
    tables = world.tables()
    kept = (dict(tables.versions), dict(tables.blobs), dict(tables.locations), dict(tables.staged))
    objects = list(world.blobs.iter_objects(setup.ws))
    trashed = world.run(TrashFile(file_id=first.file_id, expected_row_version=2, reason="obsolete"))
    assert (trashed.state, trashed.row_version) == ("trashed", 3)
    restored = world.run(RestoreFile(file_id=first.file_id, expected_row_version=3))
    assert (restored.state, restored.row_version) == ("active", 4)
    after = world.tables()
    assert (dict(after.versions), dict(after.blobs), dict(after.locations), dict(after.staged)) == kept
    assert list(world.blobs.iter_objects(setup.ws)) == objects
    [event] = world.events("file-trashed")
    assert event.payload == {"file_id": str(first.file_id), "reason": "obsolete"}
    assert len(world.events("file-restored")) == 1


def test_a_repeated_trash_or_restore_is_a_no_op_without_an_event(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    world.run(RestoreFile(file_id=first.file_id, expected_row_version=2))  # already active
    assert world.events("file-restored") == []
    world.run(TrashFile(file_id=first.file_id, expected_row_version=2, reason="x"))
    again = world.run(TrashFile(file_id=first.file_id, expected_row_version=3, reason="x"))
    assert (again.state, again.row_version) == ("trashed", 3)
    assert len(world.events("file-trashed")) == 1
    world.refused(
        ErrorCode.VERSION_CONFLICT,
        lambda: world.run(TrashFile(file_id=first.file_id, expected_row_version=2, reason="x")),
    )


def test_a_trashed_file_takes_no_version_until_restored(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    world.run(TrashFile(file_id=first.file_id, expected_row_version=2, reason="x"))
    staged = world.stage(setup.ws, b"v2\n")
    world.refused(ErrorCode.FILE_TRASHED, lambda: world.add_version(first.file_id, staged, version=3))
    world.run(RestoreFile(file_id=first.file_id, expected_row_version=3))
    assert world.add_version(first.file_id, staged, version=4).version_no == 2


def test_a_trashed_file_keeps_its_version_readable(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    world.run(TrashFile(file_id=first.file_id, expected_row_version=2, reason="x"))
    view = world.ask(GetFile(file_id=first.file_id))
    assert view.state == "trashed"
    assert view.current_version.file_version_id == first.file_version_id


@pytest.mark.parametrize("name", ["trash", "restore"])
def test_a_worker_cannot_trash_or_restore(world: World, setup: Setup, name: str) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws))
    worker = world.worker("w1", setup.ws)
    dto = (
        TrashFile(file_id=first.file_id, expected_row_version=2, reason="x")
        if name == "trash"
        else RestoreFile(file_id=first.file_id, expected_row_version=2)
    )
    world.refused(ErrorCode.FORBIDDEN, lambda: world.run(dto, worker))


def test_a_viewer_cannot_trash(world: World, setup: Setup) -> None:
    first = world.add_file(setup.ws, world.stage(setup.ws), project_id=setup.project)
    world.refused(
        ErrorCode.FORBIDDEN,
        lambda: world.run(TrashFile(file_id=first.file_id, expected_row_version=2, reason="x"), "viewer"),
    )


# ----------------------------------------------------------------------------------- classification default
def test_an_omitted_classification_is_not_an_explicit_internal_on_the_wire() -> None:
    omitted = AddFile(
        workspace_id=UUID(int=1),
        title="t",
        origin=wire.FileOrigin.UPLOAD,
        blob=wire.AddFileDefsStagedBlobRef(UUID(int=2), UUID(int=1), "sha256:" + "0" * 64, 1, "text/plain"),
        original_filename="a.txt",
        source=SOURCE,
    )
    explicit = replace(omitted, classification=wire.Classification.INTERNAL)
    assert omitted.classification is None
    assert "classification" not in omitted.to_json()
    assert explicit.to_json()["classification"] == "internal"
    assert AddFile.from_json(omitted.to_json()).classification is None  # absence survives the round trip
    assert AddFile.from_json(explicit.to_json()).classification == "internal"
    assert omitted.to_json() != explicit.to_json()  # two requests: the idempotency digest tells them apart


def test_an_omitted_classification_takes_the_scoped_default_and_an_explicit_one_never_does(
    world: World, setup: Setup
) -> None:
    world.configure(setup.ws, "artifacts.default_classification", "confidential")
    workspace_wide = world.add_file(setup.ws, world.stage(setup.ws), title="w")
    explicit = world.add_file(setup.ws, world.stage(setup.ws, b"b\n"), title="e", classification="internal")
    public_one = world.add_file(setup.ws, world.stage(setup.ws, b"c\n"), title="p", classification="public")
    assert workspace_wide.classification.value == "confidential"  # the workspace default
    assert explicit.classification.value == "internal"  # the caller's own word, equal to the old default
    assert public_one.classification.value == "public"  # and never raised by the default
    world.configure(setup.project, "artifacts.default_classification", "restricted")
    in_project = world.add_file(setup.ws, world.stage(setup.ws, b"d\n"), project_id=setup.project, title="x")
    elsewhere = world.add_file(setup.ws, world.stage(setup.ws, b"e\n"), title="y")
    assert in_project.classification.value == "restricted"  # the project overrides the workspace
    assert elsewhere.classification.value == "confidential"  # and only for its own files
    stored = world.tables().files
    assert stored[in_project.file_id].classification.value == "restricted"
    assert stored[explicit.file_id].classification.value == "internal"


def test_an_explicit_null_classification_never_reaches_the_bus_or_becomes_an_omission(
    world: World, setup: Setup
) -> None:
    """``classification`` is optional but not nullable: null is not "omitted", so no default replaces it."""
    world.configure(setup.ws, "artifacts.default_classification", "confidential")
    staged = world.stage(setup.ws)
    base = AddFile(
        workspace_id=setup.ws,
        title="t",
        origin=wire.FileOrigin.UPLOAD,
        blob=staged.ref(),
        original_filename="a.txt",
        source=SOURCE,
    )
    payload = {**base.to_json(), "classification": None}
    before = world.snapshot()
    with pytest.raises(ValueError, match="not a valid Classification"):
        AddFile.from_json(payload)  # the codec refuses it: no DTO exists to dispatch
    with pytest.raises(SkmError) as invalid:
        schemas().require_valid(AddFile.SCHEMA_URN, payload)  # and the source schema says the same
    assert invalid.value.code is ErrorCode.SCHEMA_INVALID
    assert world.snapshot() == before  # nothing was written, the staged blob is still unused
    assert world.staged_row(staged).consumed_at is None
    omitted = AddFile.from_json(base.to_json())  # the same request without the member is an omission
    assert omitted.classification is None
    assert world.run(omitted).classification.value == "confidential"  # the scoped default applies
    explicit = AddFile.from_json({**base.to_json(), "classification": "internal"})
    assert explicit.classification == wire.Classification.INTERNAL
    other = world.stage(setup.ws, b"x\n")
    kept = world.run(replace(explicit, blob=other.ref()))
    assert kept.classification.value == "internal"  # an explicit enum is kept, not replaced by the default


def test_without_any_entry_the_default_classification_is_internal(world: World, setup: Setup) -> None:
    assert world.add_file(setup.ws, world.stage(setup.ws)).classification.value == "internal"


def test_the_scoped_default_is_still_raised_by_the_admission_floor(world: World, setup: Setup) -> None:
    world.configure(setup.ws, "artifacts.default_classification", "public")
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16
    result = world.add_file(
        setup.ws,
        world.stage(setup.ws, png, media_type="image/png"),
        filename="p.png",
        declared_media_type="text/plain",
    )
    assert result.classification.value == "internal"  # a media mismatch keeps its floor (G21)


# --------------------------------------------------------------------------------------- file scope settings
def test_a_version_is_admitted_under_the_settings_of_the_files_workspace(world: World, setup: Setup) -> None:
    """``add_file_version`` has no scope of its own on the bus; the workspace override must still apply."""
    secret = world.add_file(
        setup.ws, world.stage(setup.ws), classification=wire.Classification.CONFIDENTIAL, title="s"
    )
    acknowledged = {"filename": ".env", "acknowledge": ("CS-SECRET-NAME",)}
    ok = world.add_version(secret.file_id, world.stage(setup.ws, b"A=1\n"), version=2, **acknowledged)
    assert ok.version_no == 2  # the instance floor (confidential) is met by a confidential file
    world.configure(setup.ws, "artifacts.safety.acknowledge_min_classification", "restricted")
    staged = world.stage(setup.ws, b"A=2\n")
    error = world.refused(
        ErrorCode.CONTENT_UNSAFE,
        lambda: world.add_version(secret.file_id, staged, version=3, **acknowledged),
    )
    assert error.details["reason"] == "classification_below_acknowledge_minimum"
    assert world.staged_row(staged).consumed_at is None  # refused before the blob was consumed for good
    other = world.add_file(
        setup.other_ws,
        world.stage(setup.other_ws),
        classification=wire.Classification.CONFIDENTIAL,
        title="o",
    )
    fine = world.add_version(  # another workspace keeps the instance floor
        other.file_id, world.stage(setup.other_ws, b"A=3\n"), version=2, **acknowledged
    )
    assert fine.version_no == 2


def test_a_staged_reference_naming_another_workspace_never_selects_its_settings(
    world: World, setup: Setup
) -> None:
    secret = world.add_file(
        setup.ws, world.stage(setup.ws), classification=wire.Classification.CONFIDENTIAL, title="s"
    )
    world.configure(setup.ws, "artifacts.safety.acknowledge_min_classification", "restricted")
    foreign = world.stage(setup.other_ws, b"A=4\n")  # the other workspace has the lax instance floor
    error = world.refused(
        ErrorCode.FORBIDDEN,
        lambda: world.add_version(
            secret.file_id, foreign, version=2, filename=".env", acknowledge=("CS-SECRET-NAME",)
        ),
    )
    assert error.details["reason"] == "other_workspace"
    assert world.staged_row(foreign).consumed_at is None
    assert world.tables().files[secret.file_id].row_version == 2  # nothing about the file changed


# ---------------------------------------------------------------------------------------------- short reads
def test_the_scan_sees_the_whole_object_when_the_store_returns_short_reads() -> None:
    """One ``read(n)`` is not "everything": a secret past the first chunk must still be found."""
    world = build_world(scan_chunk=3)
    setup = Setup(world)
    secret = b"# notes\n" + b"filler line\n" * 20 + b"key = ghp_" + b"a1B2" * 9 + b"\n"
    staged = world.stage(setup.ws, secret)
    error = world.refused(ErrorCode.CONTENT_UNSAFE, lambda: world.add_file(setup.ws, staged))
    assert "ghp_" not in str(error.details)
    assert world.staged_row(staged).consumed_at is None


def test_the_binary_probe_sees_a_nul_byte_when_the_store_returns_short_reads() -> None:
    world = build_world(scan_chunk=2)
    setup = Setup(world)
    staged = world.stage(setup.ws, b"abcdefgh\x00ijkl", media_type="application/octet-stream")
    result = world.add_file(setup.ws, staged, filename="blob.bin")
    assert "CS-BINARY" in {finding.rule for finding in result.safety.findings}
