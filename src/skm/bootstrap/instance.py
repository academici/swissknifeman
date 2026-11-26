"""Instance initialization for ``skm init`` (kernel-platform §5.5, cli §6.1, access §7.7).

``init_instance`` first lays down what an instance needs before any principal exists: the state directory and
its private ``secrets/`` (0700), the token pepper (32 CSPRNG bytes, hex, 0600), the bootstrap file (0600) with
a new ``instance_id``, the migrated schema and the instance scope row. Nothing is overwritten. An existing
bootstrap keeps its instance id, paths and pepper reference; an existing pepper is reused after its metadata
is checked; wrong permissions are refused, never repaired.

Order is chosen for crash safety, not the order the profile is read in. Existing secrets are checked and the
database is asked first: a database that already belongs to another instance is refused before anything is
written. The bootstrap is written last, after the pepper and the migrations, so an interrupted run leaves
either no profile (the rerun reuses the pepper it finds) or a complete profile whose missing instance row the
rerun adds. A pepper is created only while the database has no instance row: once it has one, tokens may
already be hashed with the pepper, and a silent replacement would revoke them all.

Then the identities, over the production composition of the profile just written (``RbacAuthorizer``, the
stored scope chain, the pepper; no test overrides): the canonical ``system`` principal
(``SYSTEM_PRINCIPAL_ID``, service, owner on the instance; access §13) in one unit of work of this bootstrap
layer, because no command can create the actor every internal command needs; then
``access.bootstrap_local_owner`` dispatched as ``SYSTEM_ACTOR``, whose secret goes only to
``<state_dir>/secrets/owner.token`` (0600, written exclusively); then, as the local owner authenticated by
that file, the default workspace through ``workspace.get_workspace`` and ``workspace.create_workspace``.
Every step looks before it acts, so a rerun completes only what is missing. The owner secret exists once: an
owner whose token file is gone is refused (``SECRET_UNAVAILABLE``), never given a second secret, and a token
file without an owner in the database is never overwritten. A workspace of the slug that the local owner is
no member of is refused (``ALREADY_EXISTS``), not taken over.

Built-in packs load under the system actor once that principal exists.
"""

import json
import os
from collections.abc import Callable, Mapping
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Final, cast
from uuid import UUID, uuid4

from skm.adapters.postgres.connection import PgSettings, connect_single
from skm.adapters.postgres.core.scopes import PostgresScopeRegistry
from skm.application_bus.client import new_request_id
from skm.bootstrap.composition import OWNER_TOKEN_FILE, App, build_cli_app, resolve_cli_actor
from skm.bootstrap.instance_secrets import (
    check_private_dir,
    create_exclusive,
    ensure_pepper,
    ensure_private_dir,
    precheck_pepper,
    read_private,
)
from skm.bootstrap.lifecycle import embedded_dsn
from skm.bootstrap.local_postgres import (
    ManagedPostgres,
    database_identity,
    installation_id_from_env,
    local_postgres_state,
    machine_database_refs,
    managed_postgres,
    mark_managed_postgres,
    prepare_machine_storage,
    provision_local_postgres,
)
from skm.bootstrap.machine import open_machine_store, resolve_machine_profile
from skm.bootstrap.platform_module import MigrationState, local_migration_runner
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    CapabilityUnavailable,
    Conflict,
    NotFound,
    PreconditionFailed,
    Unauthenticated,
    ValidationFailed,
)
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.application.events import MembershipGranted, PrincipalCreated
from skm.modules.access.domain.identity import LOCAL_ISSUER, LOCAL_OWNER_SUBJECT
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.generated.commands import BootstrapLocalOwner
from skm.modules.access.generated.results import BootstrapLocalOwnerResult
from skm.modules.access.ports import IdentityRepository, MembershipRepository, PrincipalRepository
from skm.modules.access.public import SYSTEM_ACTOR, ListMemberships, ListMembershipsView, Role
from skm.modules.extensions.public import SyncBuiltinPacks
from skm.modules.workspace.public import (
    CreateWorkspace,
    CreateWorkspaceResult,
    GetWorkspace,
    WorkspaceView,
)
from skm.platform.config.bootstrap import (
    BootstrapConfig,
    configure_bootstrap,
    load_bootstrap,
)
from skm.platform.config.secrets import SecretRef
from skm.platform.config.sources.document import decode_document
from skm.platform.machine import MachineProfile
from skm.platform.schema.registry import SchemaRegistry
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

__all__ = [
    "DEFAULT_WORKSPACE",
    "OWNER_TOKEN_NAME",
    "InitMigrations",
    "InitOwner",
    "InitReport",
    "InitWorkspace",
    "find_bootstrap",
    "init_instance",
]

DEFAULT_WORKSPACE: Final = "personal"  # access §7.7 (G38)
OWNER_TOKEN_NAME: Final = "local-owner-cli"  # cli §6.1 step 5; the DTO default is "local-owner"
_SYSTEM_NAME: Final = "system"
_URN: Final = "urn:skm:config:bootstrap:v1"
# The DSN carries a password: the profile holds only the reference (examples/config/bootstrap.local.toml).
_DATABASE_REF: Final = "secret://env/SKM_DATABASE_URL"
_SECRETS: Final = "secrets"
_PEPPER: Final = "token-pepper"
_APPLICATION: Final = "skm-cli"
_HEADER: Final = (
    "# Written by `skm init` (embedded mode). Only what is needed before the database is reachable;\n"
    "# every other setting lives in the settings levels (skm config ...). The database URL is not stored\n"
    "# here: SKM_DATABASE_URL in the environment supplies it.\n"
)


@dataclass(frozen=True, slots=True)
class InitMigrations:
    applied: tuple[int, ...]
    current: int


@dataclass(frozen=True, slots=True)
class InitOwner:
    """The local owner; ``token_path`` names the file of its secret, never the secret itself."""

    principal_id: UUID
    created: bool
    token_path: Path


@dataclass(frozen=True, slots=True)
class InitWorkspace:
    workspace_id: UUID
    slug: str
    created: bool


@dataclass(frozen=True, slots=True)
class InitReport:
    """What ``skm init`` found or created; host and packs join later (cli §6.1 steps 6-7)."""

    instance_id: UUID
    already_initialized: bool
    bootstrap_path: Path
    state_dir: Path
    token_pepper_path: Path | None
    token_pepper_created: bool
    migrations: InitMigrations
    instance_scope_created: bool
    system_principal_created: bool
    owner_principal_id: UUID
    owner: InitOwner
    workspace: InitWorkspace | None  # None with --no-workspace


# ----------------------------------------------------------------------------------------------- paths


def _expand(value: str, home: Path) -> Path:
    if value == "~":
        return home.absolute()
    if value.startswith("~/"):
        return (home / value[2:]).absolute()
    return Path(value).absolute()


def find_bootstrap(cli_path: str | None, environ: Mapping[str, str], home: Path) -> tuple[Path, bool]:
    """The profile ``skm init`` reads or writes, and whether it exists.

    The order is the loader's (``BOOTSTRAP_SEARCH``) without the system-wide ``/etc/skm/bootstrap.toml``,
    which a user's ``init`` never writes: the first existing file wins, so a rerun never shadows a profile
    the loader would read; with none, the first applicable location is the one to create.
    """
    xdg = environ.get("XDG_CONFIG_HOME")
    candidates = [
        _expand(value, home)
        for value in (
            cli_path,
            environ.get("SKM_BOOTSTRAP"),
            str(Path(xdg) / "skm/bootstrap.toml") if xdg else None,
            str(home / ".config/skm/bootstrap.toml"),
        )
        if value
    ]
    if cli_path or environ.get("SKM_BOOTSTRAP"):
        return candidates[0], candidates[0].exists()  # an explicit file is never replaced by a search
    for candidate in candidates:
        if candidate.exists():
            return candidate, True
    return candidates[0], False


def _default_dir(environ: Mapping[str, str], home: Path, xdg: str, fallback: str) -> Path:
    base = environ.get(xdg)
    return Path(base).absolute() / "skm" if base else (home / fallback / "skm").absolute()


# ----------------------------------------------------------------------------------------------- errors


def _foreign(recorded: UUID, expected: UUID | None) -> Conflict:
    return Conflict(
        ErrorCode.ALREADY_EXISTS,
        "the database already belongs to another instance",
        details={
            "kind": "instance",
            "instance_id": str(recorded),
            "bootstrap_instance_id": None if expected is None else str(expected),
            "hint": "use the bootstrap of that instance (--bootstrap) or an empty database",
        },
    )


def _foreign_token(path: Path, reason: str) -> Conflict:
    return Conflict(
        ErrorCode.ALREADY_EXISTS,
        "the owner token file does not belong to this instance's local owner",
        details={
            "kind": "owner_token",
            "path": str(path),
            "reason": reason,
            "hint": "skm init never overwrites a token file; move it away if it is not needed",
        },
    )


def _invalid(field: str, reason: str, **extra: JsonValue) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.CONFIG_INVALID,
        "skm init cannot use this bootstrap configuration",
        details={"field": field, "reason": reason, **extra},
    )


# ----------------------------------------------------------------------------------------------- files


def _state_dir(path: Path) -> None:
    """Create the state directory (0700) when missing; only ``secrets/`` below it must be private."""
    try:
        path.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError:
        raise _invalid("paths.state_dir", "not_a_directory", path=str(path)) from None


# ----------------------------------------------------------------------------------------------- bootstrap


def _toml_string(value: str) -> str:
    # JSON string escapes are TOML basic-string escapes; TOML also forbids a raw DEL.
    return json.dumps(value, ensure_ascii=False).replace("\x7f", "\\u007f")


def _toml_value(value: JsonValue) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return _toml_string(value)
    raise TypeError("the bootstrap writer renders strings and booleans only")


def _render(document: JsonObject) -> str:
    lines = [_HEADER.rstrip("\n")]
    tables: list[tuple[str, JsonObject]] = []
    for key, value in document.items():
        if isinstance(value, dict):
            tables.append((key, value))
        else:
            lines.append(f"{key} = {_toml_value(value)}")
    for name, table in tables:
        lines.extend(["", f"[{name}]", *(f"{key} = {_toml_value(value)}" for key, value in table.items())])
    return "\n".join(lines) + "\n"


def _document(
    instance_id: UUID, state_dir: Path, blobs_root: Path, pepper: Path, host_name: str | None
) -> JsonObject:
    host: JsonObject = {"id": "auto"}
    if host_name is not None:
        host["name"] = host_name
    return {
        "schema": _URN,
        "instance_id": str(instance_id),
        "access": {"mode": "embedded"},
        "database": {"url": _DATABASE_REF, "migrate_on_start": True, "application_name": "skm"},
        "secrets": {"token_pepper": str(SecretRef("file", str(pepper)))},
        "paths": {"state_dir": str(state_dir), "blobs_root": str(blobs_root)},
        "host": host,
    }


def _bootstrap_text(document: JsonObject) -> str:
    """The rendered profile, refused unless it is schema-valid and reads back as exactly ``document``."""
    issues = SchemaRegistry.load_default().validate(_URN, document)
    if issues:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "the bootstrap skm init would write is invalid",
            details={"issues": [{"pointer": issue.pointer, "code": issue.code} for issue in issues]},
        )
    text = _render(document)
    if decode_document(text, "toml") != document:
        raise _invalid("bootstrap", "render")
    return text


# ----------------------------------------------------------------------------------------------- database


def _settings(dsn: str) -> PgSettings:
    return PgSettings(dsn=dsn, application_name=_APPLICATION)


def _recorded_instance(dsn: str) -> UUID | None:
    """The instance row of the database, or ``None`` (no row, or a database not migrated yet)."""
    with closing(connect_single(_settings(dsn))) as conn:
        row = conn.execute("SELECT to_regclass('skm_core.scopes') IS NOT NULL").fetchone()
        if row is None or not row[0]:
            return None
        try:
            return PostgresScopeRegistry(conn).instance().id
        except NotFound:
            return None


def _ensure_instance_scope(dsn: str, instance_id: UUID) -> bool:
    with closing(connect_single(_settings(dsn))) as conn:
        registry = PostgresScopeRegistry(conn)
        try:
            recorded = registry.instance().id
        except NotFound:
            try:
                registry.create(ScopeId(instance_id), ScopeKind.INSTANCE, parent=None, workspace_id=None)
            except Conflict:  # a concurrent init committed its instance row first
                conn.rollback()
                recorded = registry.instance().id
            else:
                conn.commit()
                return True
        if recorded != instance_id:
            raise _foreign(recorded, instance_id)
        return False


def _migrate(dsn: str) -> InitMigrations:
    runner = local_migration_runner(dsn)
    applied = runner.migrate()
    current = max(
        (version for _, version, state in runner.status() if state is not MigrationState.PENDING), default=0
    )
    return InitMigrations(applied=applied, current=current)


# ----------------------------------------------------------------------------------------------- identities


def _open_app(
    bootstrap_path: Path, dsn: str, environ: Mapping[str, str], home: Path, instance: str | None
) -> tuple[App, BootstrapConfig]:
    """The production CLI composition of the profile, over the DSN ``skm init`` was given (never stored)."""
    env = {**environ, "SKM_DATABASE_URL": dsn}
    bootstrap = load_bootstrap(str(bootstrap_path), env, home, instance=instance)
    return build_cli_app(bootstrap, environ=env, invocation={"set": [], "config": []}), bootstrap


def _meta(ids: Uuid7Generator, clock: SystemClock) -> RequestMeta:
    return RequestMeta(new_request_id(ids), Surface.CLI, None, clock.now(), client="skm-cli/init")


def _ensure_system_principal(app: App, ids: Uuid7Generator, clock: SystemClock) -> bool:
    """The canonical ``system`` principal and its owner membership on the instance (access §13).

    Created here, in the bootstrap layer, because every internal command (``bootstrap_local_owner`` first)
    needs this actor. It gets no token. Returns whether the principal row was created by this call.
    """
    now = clock.now()
    with app.uow_factory(_meta(ids, clock)) as uow:
        principals = uow.repo(PrincipalRepository)
        created = False
        try:
            found = principals.get(SYSTEM_PRINCIPAL_ID)
        except NotFound:
            principal = new_principal(
                principal_id=SYSTEM_PRINCIPAL_ID,
                kind=PrincipalKind.SERVICE,
                display_name=_SYSTEM_NAME,
                created_by=None,
                now=now,
            )
            try:
                principals.add(principal)
            except Conflict:  # a concurrent init committed it first
                found = principals.get(SYSTEM_PRINCIPAL_ID)
            else:
                uow.record(
                    PrincipalCreated(
                        principal_id=principal.id, kind=principal.kind, display_name=principal.display_name
                    )
                )
                found, created = principal, True
        if found.kind is not PrincipalKind.SERVICE:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "the id of the system principal belongs to another kind of principal",
                details={"kind": "principal", "principal_id": str(SYSTEM_PRINCIPAL_ID)},
            )
        instance = uow.repo(ScopeRegistry).instance()
        memberships = uow.repo(MembershipRepository)
        current = memberships.get(instance.id, SYSTEM_PRINCIPAL_ID)
        if current is None or current.role is not Role.OWNER:
            memberships.upsert(
                Membership(
                    scope_id=instance.id,
                    principal_id=SYSTEM_PRINCIPAL_ID,
                    role=Role.OWNER,
                    granted_by=None,
                    granted_at=now,
                )
            )
            uow.record(
                MembershipGranted(
                    scope_id=instance.id,
                    principal_id=SYSTEM_PRINCIPAL_ID,
                    role=Role.OWNER,
                    previous_role=None if current is None else current.role,
                    workspace_id=None,
                )
            )
        uow.commit()
    return created


def _owner_token_lost(path: Path, reason: str, message: str) -> PreconditionFailed:
    return PreconditionFailed(
        ErrorCode.SECRET_UNAVAILABLE,
        message,
        details={
            "ref": str(SecretRef("file", str(path))),
            "reason": reason,
            "hint": "the owner secret is issued once and skm init never issues another: restore owner.token "
            "from a backup, or let another instance owner save a token for the local owner there",
        },
    )


def _save_owner_token(path: Path, secret: str) -> None:
    """The only plaintext copy of the owner secret: ``owner.token`` (0600), created, never replaced."""
    ensure_private_dir(path.parent)
    if not create_exclusive(path, secret.encode("utf-8") + b"\n"):
        raise _foreign_token(path, "exists")


def _owner_actor(
    app: App, bootstrap: BootstrapConfig, owner_id: UUID, on_secret: Callable[[str], None]
) -> Actor:
    """The local owner as authenticated by its token file (permissions checked before it is read)."""
    path = bootstrap.state_dir / OWNER_TOKEN_FILE
    if not os.path.lexists(path):
        raise _owner_token_lost(path, "missing", "the local owner exists but its token file is missing")
    # Refused as SECRET_PERMISSIONS here, never repaired, before the resolver reads the secret.
    check_private_dir(path.parent)
    read_private(path, 0)
    try:
        actor = resolve_cli_actor(app, bootstrap, as_token=None, on_secret=on_secret)
    except Unauthenticated:
        raise _owner_token_lost(path, "rejected", "the owner token file holds no usable credential") from None
    if actor.principal_id != owner_id:
        raise _foreign_token(path, "other_principal")
    return actor


def _ensure_owner(
    app: App,
    bootstrap: BootstrapConfig,
    *,
    display_name: str,
    owner_password: str | None,
    on_secret: Callable[[str], None],
    ids: Uuid7Generator,
    clock: SystemClock,
) -> tuple[InitOwner, Actor]:
    """``access.bootstrap_local_owner`` as ``SYSTEM_ACTOR`` (access §7.7), then the token file's owner."""
    path = bootstrap.state_dir / OWNER_TOKEN_FILE
    with app.uow_factory(_meta(ids, clock), readonly=True) as uow:
        known = uow.repo(IdentityRepository).find(LOCAL_ISSUER, LOCAL_OWNER_SUBJECT)
    created = False
    if known is not None and owner_password is None:
        owner_id: UUID = known.principal_id
    else:
        if known is None and os.path.lexists(path):  # never adopted for a new owner
            raise _foreign_token(path, "no_local_owner")
        system = app.client(actor=SYSTEM_ACTOR, surface=Surface.CLI)
        result = cast(
            "BootstrapLocalOwnerResult",
            system.dispatch(
                BootstrapLocalOwner(
                    display_name=display_name, token_name=OWNER_TOKEN_NAME, password=owner_password
                )
            ),
        )
        owner_id = result.principal_id
        if result.token_secret is not None:
            on_secret(result.token_secret)  # before anything can be printed
            _save_owner_token(path, result.token_secret)
            created = True
    actor = _owner_actor(app, bootstrap, owner_id, on_secret)
    return InitOwner(principal_id=owner_id, created=created, token_path=path), actor


def _ensure_workspace(app: App, owner: Actor, slug: str) -> InitWorkspace:
    """The default workspace through the workspace commands, as the local owner (access §7.7, G38).

    Missing: ``workspace.create_workspace`` (its handler makes the creator the workspace owner). Present with
    the local owner as a member: kept. Present without it: ``ALREADY_EXISTS``; another principal's workspace
    is never taken over.
    """
    client = app.client(actor=owner, surface=Surface.CLI)
    try:
        view = cast("WorkspaceView", client.ask(GetWorkspace(slug=slug)))
    except NotFound:
        title = "Personal" if slug == DEFAULT_WORKSPACE else slug
        try:
            made = cast("CreateWorkspaceResult", client.dispatch(CreateWorkspace(slug=slug, title=title)))
        except Conflict as error:
            if error.code is not ErrorCode.ALREADY_EXISTS:
                raise
            view = cast("WorkspaceView", client.ask(GetWorkspace(slug=slug)))  # a concurrent init
        else:
            return InitWorkspace(workspace_id=made.workspace_id, slug=made.slug, created=True)
    members = cast(
        "ListMembershipsView",
        client.ask(ListMemberships(scope_id=view.workspace_id, principal_id=owner.principal_id)),
    )
    if not any(item.principal_id == owner.principal_id for item in members.items):
        raise Conflict(
            ErrorCode.ALREADY_EXISTS,
            f'workspace "{slug}" already exists and the local owner is not its member',
            details={
                "kind": "workspace",
                "slug": slug,
                "hint": "choose another slug (skm init --workspace OTHER) or skip it (--no-workspace)",
            },
        )
    return InitWorkspace(workspace_id=view.workspace_id, slug=view.slug, created=False)


def _identities(  # noqa: PLR0913 -- database bootstrap and local owner inputs
    bootstrap_path: Path,
    *,
    dsn: str,
    environ: Mapping[str, str],
    home: Path,
    instance: str | None,
    owner_name: str,
    owner_password: str | None,
    workspace: str | None,
    on_secret: Callable[[str], None],
) -> tuple[bool, InitOwner, InitWorkspace | None]:
    clock = SystemClock()
    ids = Uuid7Generator(clock)
    app, bootstrap = _open_app(bootstrap_path, dsn, environ, home, instance)
    try:
        system_created = _ensure_system_principal(app, ids, clock)
        app.client(actor=SYSTEM_ACTOR, surface=Surface.CLI).dispatch(SyncBuiltinPacks())
        owner, actor = _ensure_owner(
            app,
            bootstrap,
            display_name=owner_name,
            owner_password=owner_password,
            on_secret=on_secret,
            ids=ids,
            clock=clock,
        )
        made = None if workspace is None else _ensure_workspace(app, actor, workspace)
    finally:
        app.close()
    return system_created, owner, made


# ----------------------------------------------------------------------------------------------- init


def _existing(
    path: Path, environ: Mapping[str, str], home: Path, instance: str | None
) -> tuple[BootstrapConfig, UUID]:
    bootstrap = load_bootstrap(str(path), environ, home, instance=instance)
    if bootstrap.access_mode != "embedded":
        raise CapabilityUnavailable(
            ErrorCode.CAPABILITY_UNAVAILABLE,
            "skm init prepares an embedded profile; an http profile is initialized on its server",
            details={"bootstrap": str(path)},
        )
    if bootstrap.instance_id is None:
        raise _invalid("instance_id", "missing", bootstrap=str(path))
    return bootstrap, bootstrap.instance_id


def _pepper_path(bootstrap: BootstrapConfig, home: Path) -> Path | None:
    """The managed pepper file of an existing profile; an env/keyring pepper is not init's to create."""
    ref = bootstrap.token_pepper
    if ref is None:
        raise _invalid(
            "secrets.token_pepper",
            "missing",
            hint=f'add [secrets] token_pepper = "secret://file/{bootstrap.state_dir / _SECRETS / _PEPPER}"',
        )
    if ref.scheme != "file":
        return None
    return _expand(ref.path, home)


def _new_profile(
    bootstrap_path: Path,
    document: JsonObject,
    database_url: str | None,
    env: Mapping[str, str],
    user_home: Path,
    on_secret: Callable[[str], None],
) -> tuple[BootstrapConfig, str, ManagedPostgres | None]:
    managed: ManagedPostgres | None = None
    if database_url is None:
        managed = provision_local_postgres(
            Path(cast("str", cast("JsonObject", document["paths"])["state_dir"])),
            "standalone",
            installation_id_from_env(env),
            env,
            on_secret=on_secret,
        )
        database_url = managed.dsn("PROJECT_MIGRATOR")
        document["database"] = {
            "url": str(managed.reference("PROJECT_APP")),
            "migrator_url": str(managed.reference("PROJECT_MIGRATOR")),
            "migrate_on_start": False,
            "application_name": "skm",
        }
    elif env.get("SKM_DATABASE_MIGRATOR_URL"):
        document["database"] = {
            "url": _DATABASE_REF,
            "migrator_url": "secret://env/SKM_DATABASE_MIGRATOR_URL",
            "migrate_on_start": False,
            "application_name": "skm",
        }
    if machine := machine_database_refs(managed, env):
        document["installation_id"] = str(
            managed.installation_id if managed is not None else installation_id_from_env(env) or uuid4()
        )
        document["machine_database"] = machine
    text = _bootstrap_text(document)
    if managed is None:
        env = {**env, "SKM_DATABASE_URL": env.get("SKM_DATABASE_URL") or database_url}
    config = configure_bootstrap(str(bootstrap_path), document, env, user_home)
    return config, text, managed


def _preflight_init(
    config: BootstrapConfig,
    database_url: str,
    pepper: Path | None,
    env: Mapping[str, str],
    on_secret: Callable[[str], None],
    already: bool,
) -> UUID | None:
    instance_id, state = config.instance_id, config.state_dir
    if pepper is not None:
        precheck_pepper(pepper)
    # 1. The database: refuse a foreign one before anything is written.
    local_migration_runner(database_url).migrate(dry_run=True)
    if config.machine_database_url is not None:
        prepare_machine_storage(config, env, on_secret=on_secret, dry_run=True, project_dsn=database_url)
    recorded = _recorded_instance(database_url)
    if recorded is not None and (not already or recorded != instance_id):
        raise _foreign(recorded, instance_id if already else None)
    owner_token = state / OWNER_TOKEN_FILE
    if recorded is None and os.path.lexists(owner_token):  # no owner can exist yet: the file is foreign
        raise _foreign_token(owner_token, "no_local_owner")
    return recorded


def _activate_embedded(
    config: BootstrapConfig,
    instance_id: UUID,
    environ: Mapping[str, str],
    on_secret: Callable[[str], None],
) -> None:
    installation = config.installation_id
    if installation is None:
        return
    store = open_machine_store(config, environ, on_secret=on_secret)
    profile = MachineProfile(
        installation, config.instance_profile or "default", instance_id, f"embedded:{instance_id}", None
    )
    if not store.put_profile(profile):
        stored = resolve_machine_profile(store, installation, profile.name)
        if replace(stored, revision=None) != profile:
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Embedded database conflicts with the machine pin"
            )


def init_instance(  # noqa: PLR0913 -- database bootstrap and local workspace inputs
    bootstrap_path: Path,
    *,
    database_url: str | None,
    state_dir: Path | None,
    blobs_root: Path | None = None,
    host_name: str | None = None,
    instance: str | None = None,
    environ: Mapping[str, str] | None = None,
    home: Path | None = None,
    owner_name: str = "local-owner",
    owner_password: str | None = None,
    workspace: str | None = DEFAULT_WORKSPACE,
    on_secret: Callable[[str], None] = lambda _value: None,
) -> InitReport:
    """Run ``skm init``; idempotent, and never overwrites a profile or a secret.

    ``database_url`` is the resolved DSN of the migrator role (never written anywhere). ``state_dir`` and
    ``blobs_root`` apply to a new profile only (``None``: ``SKM_STATE_DIR``/XDG/home defaults); an existing
    profile keeps its own paths, and a different explicit ``state_dir`` is refused rather than ignored.
    ``owner_name`` is the display name of a new local owner; ``workspace`` the slug of the default workspace
    (``None``: none). ``on_secret`` receives the owner secret before anything else sees it (redaction).
    """
    env: Mapping[str, str] = {} if environ is None else environ
    user_home = Path.home() if home is None else home
    if database_url is not None and not database_url.strip():
        raise _invalid("database.url", "empty")
    already = os.path.lexists(bootstrap_path)
    text: str | None = None
    managed: ManagedPostgres | None = None
    if already:
        config, instance_id = _existing(bootstrap_path, env, user_home, instance)
        state = config.state_dir
        if state_dir is not None and state_dir.absolute() != state:
            raise _invalid("paths.state_dir", "differs_from_bootstrap", bootstrap=str(bootstrap_path))
        pepper = _pepper_path(config, user_home)
        if managed_postgres(state) is not None:
            managed = provision_local_postgres(
                state, "standalone", config.installation_id, env, on_secret=on_secret
            )
    else:
        instance_id = Uuid7Generator(SystemClock()).new_id()
        state = state_dir.absolute() if state_dir is not None else local_postgres_state(env, user_home)
        blobs = (
            blobs_root.absolute()
            if blobs_root is not None
            else _default_dir(env, user_home, "XDG_DATA_HOME", ".local/share") / "blobs"
        )
        pepper = state / _SECRETS / _PEPPER
        document = _document(instance_id, state, blobs, pepper, host_name)
        config, text, managed = _new_profile(
            bootstrap_path, document, database_url, env, user_home, on_secret
        )

    if managed is not None:
        database_url = managed.dsn("PROJECT_MIGRATOR")
        config = replace(
            config,
            machine_database_url=managed.reference("MACHINE_APP"),
            machine_database_migrator_url=managed.reference("MACHINE_MIGRATOR"),
        )
    if database_url is None:
        raise _invalid("database.migrator_url", "missing")
    if config.database_migrator_url is None and str(config.database_url) == _DATABASE_REF:
        # A legacy single-DSN invocation may supply --database-url without its saved environment variable.
        runtime_dsn = database_url
    else:
        runtime_dsn = embedded_dsn(config, env, on_secret)
    if database_url != runtime_dsn and database_identity(database_url) != database_identity(runtime_dsn):
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Project DSNs select different databases")

    recorded = _preflight_init(config, database_url, pepper, env, on_secret, already)
    # 2. Local state and the pepper (reused when an interrupted run already created it).
    _state_dir(state)
    pepper_created = False if pepper is None else ensure_pepper(pepper, may_create=recorded is None)
    # 3. The schema (the code of `skm db migrate`).
    migrations = _migrate(database_url)
    if config.machine_database_url is not None:
        prepare_machine_storage(config, env, on_secret=on_secret, project_dsn=database_url)
    if managed is not None:
        mark_managed_postgres(state, managed)
    # 4. The profile, last: only a complete preparation is ever described by a bootstrap.
    if text is not None:
        bootstrap_path.parent.mkdir(parents=True, exist_ok=True)
        if not create_exclusive(bootstrap_path, text.encode("utf-8")):
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "another skm init wrote the bootstrap meanwhile; run skm init again to verify it",
                details={"kind": "bootstrap", "path": str(bootstrap_path)},
            )
    # 5. The instance scope with the profile's id.
    scope_created = _ensure_instance_scope(runtime_dsn, instance_id)
    # 6. The system principal, the local owner and its token file, the default workspace.
    system_created, owner, made = _identities(
        bootstrap_path,
        dsn=runtime_dsn,
        environ=env,
        home=user_home,
        instance=instance,
        owner_name=owner_name,
        owner_password=owner_password,
        workspace=workspace,
        on_secret=on_secret,
    )
    _activate_embedded(config, instance_id, env, on_secret)
    return InitReport(
        instance_id=instance_id,
        already_initialized=already,
        bootstrap_path=bootstrap_path,
        state_dir=state,
        token_pepper_path=pepper,
        token_pepper_created=pepper_created,
        migrations=migrations,
        instance_scope_created=scope_created,
        system_principal_created=system_created,
        owner_principal_id=owner.principal_id,
        owner=owner,
        workspace=made,
    )
