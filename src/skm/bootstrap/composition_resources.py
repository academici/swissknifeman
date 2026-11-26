"""Storage, credentials and PostgreSQL resources owned by the composition root."""

import errno
import os
import re
import shutil
import stat
import threading
from collections.abc import Callable, Generator, Iterator, Mapping, Sequence
from contextlib import contextmanager
from hashlib import file_digest
from pathlib import Path
from time import monotonic, sleep
from types import TracebackType
from typing import Any, Self, cast, override
from uuid import UUID

from skm.adapters.blobs.local.store import LocalBlobStore
from skm.adapters.postgres.config_store import PostgresConfigStore
from skm.adapters.postgres.connection import PgSettings, connect_single
from skm.adapters.postgres.core.events_store import PostgresEventWriter
from skm.adapters.postgres.core.schema_version import SchemaCompatibility, SchemaVersionReader
from skm.adapters.postgres.core.scopes import PostgresScopeTree
from skm.adapters.postgres.extensions.pack_config_source import PackConnectionSlot
from skm.adapters.postgres.pool import PoolHandle
from skm.adapters.postgres.uow import PostgresUnitOfWork, PostgresUowFactory
from skm.adapters.secrets.env import EnvSecretResolver
from skm.adapters.secrets.file import FileSecretResolver
from skm.application_bus.client import new_request_id
from skm.application_bus.platform.storage import StorageObjects
from skm.bootstrap.api_startup import restricted_api_process
from skm.bootstrap.platform_module import bind_storage_gateways, local_known_version
from skm.bootstrap.plugins import ProcessPlugins
from skm.kernel.actor import Actor
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    NotFound,
    PreconditionFailed,
    Unauthenticated,
    ValidationFailed,
)
from skm.kernel.id_generator import IdGenerator
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Isolation, RequestMeta, Surface, UnitOfWorkFactory
from skm.modules.access.public import authenticate_token
from skm.modules.artifacts.generated.settings import ArtifactsSettings
from skm.modules.artifacts.ports import BlobStore
from skm.platform.config.bootstrap import BootstrapConfig, apply_process_config, validate_worker_host
from skm.platform.config.keys import Level
from skm.platform.config.layers import Layer
from skm.platform.config.loader import ConfigLoader
from skm.platform.config.scopes import ScopeRef as ConfigScopeRef
from skm.platform.config.secrets import SecretRef, SecretResolvers
from skm.platform.config.sources.cli_overrides import InvocationOverrides
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.fs.atomic_write import UnsafePathError
from skm.platform.fs.safe_paths import safe_join
from skm.platform.fs.storage_budget import StorageBudget, StorageOwnerIdentity
from skm.platform.process.identity import ProcessIdentity, identity_of, is_same_process
from skm.platform.storage.verify import Location

__all__ = [
    "LazyBlobStore",
    "TokenPepper",
    "TrackedUow",
    "TrackedUowFactory",
    "database_dsn",
    "free_bytes",
    "invocation_from_json",
    "owner_alive",
    "owner_id",
    "owner_token",
    "permissions",
    "pg_blob_store",
    "private_secrets_dir",
    "process_host",
    "serve_pool_shutdown",
    "start_process",
    "token_authenticator",
    "token_pepper",
    "unauthenticated",
]

type PgFactories = Mapping[type, Callable[[Any], object]]
KNOWN_SCHEMA_VERSION = local_known_version()
OWNER_TOKEN_FILE = Path("secrets") / "owner.token"
_PEPPER_MIN_BYTES = 32


@contextmanager
def serve_pool_shutdown() -> Generator[Callable[[float], None]]:
    """Share the signal deadline across the UoW pool and the blob-coordination pool."""
    timer: threading.Timer | None = None
    with PoolHandle.collect() as pools:

        def interrupt() -> None:
            # A checked-out connection may be between statements when the first cancel arrives.
            while True:
                active = [pool.cancel_active() for pool in pools]
                if not any(active):
                    return
                sleep(0.05)

        def drain(deadline: float) -> None:
            nonlocal timer
            if timer is None:
                for pool in pools:
                    pool.deadline = deadline
                timer = threading.Timer(max(0.0, deadline - monotonic()), interrupt)
                timer.daemon = True
                timer.start()

        try:
            yield drain
        finally:
            if timer is not None and not any(pool.has_active_connections() for pool in pools):
                timer.cancel()


def invocation_from_json(invocation: JsonObject) -> InvocationOverrides:
    sets = cast("list[str]", invocation.get("set") or [])
    config = invocation.get("config") or []
    files = [config] if isinstance(config, str) else cast("list[str]", config)
    return InvocationOverrides(config_files=tuple(Path(name) for name in files), sets=tuple(sets))


class TokenPepper:
    def __init__(self, pepper: bytes) -> None:
        self._pepper = pepper

    def pepper(self) -> bytes:
        return self._pepper


def token_authenticator(
    uow_factory: UnitOfWorkFactory, pepper: bytes, surface: Surface, ids: IdGenerator, clock: Clock
) -> Callable[[str], Actor]:
    def authenticate(secret_text: str) -> Actor:
        meta = RequestMeta(new_request_id(ids), surface, None, clock.now())
        with uow_factory(meta, readonly=True) as uow:
            return authenticate_token(uow, secret_text, pepper=pepper, now=clock.now())

    return authenticate


def token_pepper(bootstrap: BootstrapConfig, environ: Mapping[str, str]) -> bytes:
    ref = bootstrap.token_pepper
    if ref is None:
        raise PreconditionFailed(
            ErrorCode.SECRET_UNAVAILABLE,
            "the bootstrap names no token pepper",
            details={"field": "secrets.token_pepper", "hint": "run skm init"},
        )
    value = (
        SecretResolvers((EnvSecretResolver(environ), FileSecretResolver()), on_reveal=lambda _value: None)
        .resolve(ref)
        .reveal()
        .encode("utf-8")
    )
    if len(value) < _PEPPER_MIN_BYTES:
        raise PreconditionFailed(
            ErrorCode.SECRET_UNAVAILABLE,
            "the token pepper is shorter than 32 bytes",
            details={"ref": str(ref), "reason": "too_short"},
        )
    return value


class LazyBlobStore:
    def __init__(self, build: Callable[[], BlobStore], inspection: StorageObjects) -> None:
        self._lock, self._build, self._store = threading.Lock(), build, cast("BlobStore | None", None)
        self.inspection = inspection

    def __getattr__(self, name: str) -> Any:
        with self._lock:
            if self._store is None:
                self._store = self._build()
            store = self._store
        return getattr(store, name)


class _LocalBlobInspection:
    """Inspect final objects without opening the local writer or claiming a staging directory."""

    _key = re.compile(
        r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}/objects/(?P<shard>[0-9a-f]{2})/(?P<digest>[0-9a-f]{64})"
    )

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, location: Location) -> Path | None:
        match = self._key.fullmatch(location.storage_key)
        if location.backend_id != LocalBlobStore.BACKEND_ID or match is None:
            return None
        if match["shard"] != match["digest"][:2]:
            return None
        try:
            return safe_join(self._root, location.storage_key)
        except (UnsafePathError, NotADirectoryError):
            return None

    def exists(self, location: Location) -> bool:
        path = self._path(location)
        try:
            return path is not None and stat.S_ISREG(path.lstat().st_mode)
        except (FileNotFoundError, NotADirectoryError):
            return False

    def verify(self, location: Location, digest: str) -> bool:
        path = self._path(location)
        if path is None:
            return False
        try:
            fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        except OSError as error:
            if error.errno in (errno.ENOENT, errno.ENOTDIR, errno.ELOOP):
                return False
            raise
        with os.fdopen(fd, "rb") as stream:
            return (
                stat.S_ISREG(os.fstat(fd).st_mode)
                and f"sha256:{file_digest(stream, 'sha256').hexdigest()}" == digest
            )

    def objects(self, workspace_id: UUID) -> Iterator[Location]:
        try:
            objects = safe_join(self._root, f"{workspace_id}/objects")
            with os.scandir(objects) as shards:
                for shard in shards:
                    if not re.fullmatch(r"[0-9a-f]{2}", shard.name) or not shard.is_dir(
                        follow_symlinks=False
                    ):
                        continue
                    with os.scandir(shard.path) as paths:
                        for path in paths:
                            key = f"{workspace_id}/objects/{shard.name}/{path.name}"
                            if (
                                self._key.fullmatch(key)
                                and path.name.startswith(shard.name)
                                and path.is_file(follow_symlinks=False)
                            ):
                                yield Location(LocalBlobStore.BACKEND_ID, key)
        except (FileNotFoundError, NotADirectoryError, UnsafePathError):
            return


def add_storage_gateways(entries: dict[type[object], object]) -> None:
    store = entries.get(BlobStore)
    bind_storage_gateways(entries, store.inspection if isinstance(store, LazyBlobStore) else None)


def owner_id() -> StorageOwnerIdentity:
    ident = identity_of(os.getpid())
    if ident is not None and ident.boot_id and ident.start_ticks is not None:
        return StorageOwnerIdentity(ident.boot_id, ident.pid, str(ident.start_ticks))
    return StorageOwnerIdentity("local-boot", os.getpid(), "0")


def owner_alive(owner: StorageOwnerIdentity) -> bool | None:
    if owner.boot_id == "local-boot":
        return owner.pid == os.getpid()
    try:
        return is_same_process(ProcessIdentity(owner.pid, int(owner.start_identity), owner.boot_id))
    except (OSError, ValueError):
        return None


class TrackedUow(PostgresUnitOfWork):
    def __init__(
        self,
        tracker: PackConnectionSlot,
        pool: PoolHandle,
        factories: PgFactories,
        events: PostgresEventWriter,
        meta: RequestMeta,
        clock: Clock,
        *,
        readonly: bool,
        isolation: Isolation,
    ) -> None:
        super().__init__(pool, factories, events, meta, clock, readonly=readonly, isolation=isolation)
        self._tracker = tracker
        self._counted = False

    def _open_conn(self) -> Any:
        try:
            return self.connection
        except RuntimeError:
            return None

    @override
    def __enter__(self) -> Self:
        super().__enter__()
        self._tracker.push(self._open_conn)
        self._counted = True
        return self

    @override
    def __exit__(
        self, exc_type: type[BaseException] | None, exc: BaseException | None, tb: TracebackType | None
    ) -> None:
        try:
            super().__exit__(exc_type, exc, tb)
        finally:
            if self._counted:
                self._counted = False
                self._tracker.pop()


class TrackedUowFactory(PostgresUowFactory):
    def __init__(
        self,
        pool: PoolHandle,
        factories: PgFactories,
        events: PostgresEventWriter,
        clock: Clock,
        *,
        tracker: PackConnectionSlot,
    ) -> None:
        super().__init__(pool, factories, events, clock)
        self._tracker = tracker
        self._shared = (pool, factories, events, clock)

    @override
    def __call__(
        self, meta: RequestMeta, *, readonly: bool = False, isolation: Isolation = Isolation.READ_COMMITTED
    ) -> PostgresUnitOfWork:
        pool, factories, events, clock = self._shared
        return TrackedUow(
            self._tracker, pool, factories, events, meta, clock, readonly=readonly, isolation=isolation
        )


def database_dsn(bootstrap: BootstrapConfig, environ: Mapping[str, str]) -> str:
    configured = bootstrap.database_url
    if configured is None:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "the PostgreSQL backend needs a database DSN",
            details={"field": "database.url"},
        )
    dsn = (
        configured
        if isinstance(configured, str)
        else SecretResolvers(
            (EnvSecretResolver(environ), FileSecretResolver()), on_reveal=lambda _value: None
        )
        .resolve(configured)
        .reveal()
    )
    if not dsn.strip():
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "the database DSN is empty", details={"field": "database.url"}
        )
    return dsn


def process_host(
    bootstrap: BootstrapConfig, surface: Surface
) -> tuple[BootstrapConfig, ConfigScopeRef | None]:
    if surface in (Surface.WORKER, Surface.HOOK):
        bootstrap = validate_worker_host(bootstrap, surface=surface)
    host_id = bootstrap.host_id
    if isinstance(host_id, UUID):
        return bootstrap, ConfigScopeRef(Level.HOST, host_id)
    return bootstrap, None


def start_process(
    config: ConfigLoader,
    bootstrap: BootstrapConfig,
    dsn: str,
    *,
    surface: Surface,
    plugins: ProcessPlugins,
    slot: PackConnectionSlot | None = None,
    api_layers: Sequence[Layer] = (),
) -> tuple[BootstrapConfig, ConfigLoader, bool]:
    bootstrap, host = process_host(bootstrap, surface)
    timeout = bootstrap.database_pool_timeout_seconds
    startup = PgSettings(dsn, bootstrap.database_application_name, 0, 1, timeout)
    conn = connect_single(startup)
    if slot is not None:
        slot.push(lambda: conn)
    try:
        reader = SchemaVersionReader(KNOWN_SCHEMA_VERSION)
        if surface is Surface.API and reader.compatibility(conn) is not SchemaCompatibility.COMPATIBLE:
            restricted_bs, restricted_cfg = restricted_api_process(bootstrap, config.registry, api_layers)
            return restricted_bs, restricted_cfg, True
        reader.require(conn)
        store, scopes = PostgresConfigStore(conn), PostgresScopeTree(conn)
        if host is None and surface in (Surface.API, Surface.BACKGROUND):
            host = scopes.instance_scope()
        process, config = plugins.start(config, store, scopes, host)
        startup_host = (
            config.effective_host(store, scopes, host)
            if surface is Surface.WORKER and host is not None
            else None
        )
    finally:
        if slot is not None:
            slot.pop()
        conn.close()
    return apply_process_config(bootstrap, process, surface=surface, startup_host=startup_host), config, False


def free_bytes(path: Path) -> int:
    return shutil.disk_usage(path if path.exists() else path.parent).free


def pg_blob_store(bs: BootstrapConfig, ctx: tuple[Any, ...]) -> BlobStore:
    uow_ref, cfg, tracker, surf, clock, ids = ctx

    def build() -> BlobStore:
        max_bytes, min_free = 104_857_600, 5_368_709_120
        if uow_ref and not tracker.holds():
            meta = RequestMeta(new_request_id(ids), surf, None, clock.now())
            try:
                with uow_ref[0](meta, readonly=True) as uow:
                    sec = cfg.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), None).section(
                        ArtifactsSettings
                    )
                    max_bytes, min_free = sec.upload.max_bytes, sec.storage.min_free_bytes
                    uow.rollback()
            except NotFound:
                pass
        locks = bs.state_dir / "locks"
        locks.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(locks, 0o700)
        budget = StorageBudget(
            locks.resolve(strict=True), free_bytes=free_bytes, identity=owner_id, owner_alive=owner_alive
        )
        return LocalBlobStore(
            bs.blobs_root, max_bytes=max_bytes, min_free_bytes=min_free, storage_budget=budget
        )

    return cast("BlobStore", LazyBlobStore(build, _LocalBlobInspection(bs.blobs_root)))


def unauthenticated(reason: str, **details: str) -> Unauthenticated:
    return Unauthenticated(
        ErrorCode.UNAUTHENTICATED,
        "no usable credential for the CLI",
        details={
            "reason": reason,
            "hint": "skm init creates the owner token; --as-token acts as another one",
            **details,
        },
    )


def private_secrets_dir(path: Path) -> None:
    try:
        info = path.lstat()
    except FileNotFoundError:
        raise unauthenticated("owner_token_missing") from None
    except OSError:
        raise permissions(path, "unusable_directory") from None
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise permissions(path, "not_a_directory")
    if info.st_uid != os.geteuid():
        raise permissions(path, "owner")
    if stat.S_IMODE(info.st_mode) & 0o077:
        raise permissions(path, "mode")


def permissions(path: Path, reason: str) -> PreconditionFailed:
    return PreconditionFailed(
        ErrorCode.SECRET_PERMISSIONS,
        "secret storage must be private to the process user",
        details={"path": str(path), "reason": reason},
    )


def owner_token(state_dir: Path, on_secret: Callable[[str], None]) -> str:
    directory = state_dir / OWNER_TOKEN_FILE.parent
    private_secrets_dir(directory)
    path = state_dir / OWNER_TOKEN_FILE
    if not os.path.lexists(path):
        raise unauthenticated("owner_token_missing")
    resolvers = SecretResolvers((FileSecretResolver(),), on_reveal=on_secret)
    return resolvers.resolve(SecretRef("file", str(path))).reveal()
