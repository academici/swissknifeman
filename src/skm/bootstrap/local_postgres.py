"""Manage the packaged PostgreSQL and distinguish it from an external database."""

import json
import os
import shutil
import socket
from collections.abc import Callable, Generator, Mapping
from dataclasses import dataclass, field
from os import defpath
from pathlib import Path
from secrets import token_hex
from typing import Final, Literal, cast
from urllib.parse import urlsplit
from uuid import UUID, uuid4

from skm.adapters.postgres.connection import PgSettings, connect_single, dsn_password
from skm.adapters.postgres.machine import PostgresMachineStore
from skm.adapters.postgres.migrations.runner import MigrationRunner, discover_migrations, package_loader
from skm.adapters.secrets.env import EnvSecretResolver
from skm.adapters.secrets.file import FileSecretResolver
from skm.adapters.secrets.keyring import KeyringSecretResolver
from skm.bootstrap.instance_secrets import create_exclusive, ensure_private_dir, read_private
from skm.bootstrap.lifecycle import ComponentStatus, follow_process_log
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, CapabilityUnavailable, ValidationFailed
from skm.kernel.json_types import JsonObject, JsonValue
from skm.platform.config.bootstrap import BootstrapConfig, configure_bootstrap, read_bootstrap_document
from skm.platform.config.secrets import SecretRef, SecretResolvers
from skm.platform.config.sources.document import decode_document
from skm.platform.fs.atomic_write import atomic_write
from skm.platform.fs.file_lock import FileLock
from skm.platform.process.environment import build_env
from skm.platform.process.runner import ProcessResult, run
from skm.platform.system_clock import SystemClock

__all__ = [
    "SERVICE",
    "InitMachineReport",
    "ManagedPostgres",
    "compose_file",
    "compose_status",
    "compose_stop",
    "compose_up",
    "database_identity",
    "external_status",
    "init_machine_profile",
    "installation_id_from_env",
    "local_postgres_state",
    "machine_database_refs",
    "machine_postgres_status",
    "managed_postgres",
    "manages_postgres",
    "mark_managed_postgres",
    "postgres_logs",
    "postgres_up",
    "prepare_machine_storage",
    "provision_local_postgres",
]


def manages_postgres(marker: Path, instance_id: str) -> bool:
    try:
        return marker.read_text() == instance_id
    except FileNotFoundError:
        return False


SERVICE: Final = "postgres"
_COMPOSE: Final = "compose.local.yaml"
_DOCKER_ENV: Final = (
    "DOCKER_HOST",
    "DOCKER_CONTEXT",
    "DOCKER_CONFIG",
    "DOCKER_CERT_PATH",
    "DOCKER_TLS_VERIFY",
    "XDG_RUNTIME_DIR",
    "SKM_LOCAL_PG_ADMIN_PASSWORD",
    "SKM_LOCAL_PG_MODE",
    "SKM_LOCAL_PG_PORT",
    "SKM_LOCAL_PG_PROJECT_APP",
    "SKM_LOCAL_PG_PROJECT_MIGRATOR",
    "SKM_LOCAL_PG_MACHINE_APP",
    "SKM_LOCAL_PG_MACHINE_MIGRATOR",
)
_COMMAND_SECONDS: Final = 60.0
_STDERR_TAIL: Final = 2000
_ROLES = ("serve", "worker")


_DATABASES: Final = {
    "PROJECT_APP": ("skm_projects", "skm_app_login"),
    "PROJECT_MIGRATOR": ("skm_projects", "skm_migrator_login"),
    "MACHINE_APP": ("skm_host", "skm_host_app_login"),
    "MACHINE_MIGRATOR": ("skm_host", "skm_host_migrator_login"),
}
_METADATA: Final = "postgres-local.json"
type _Mode = Literal["standalone", "client"]


@dataclass(frozen=True, slots=True)
class ManagedPostgres:
    state: Path
    installation_id: UUID
    mode: _Mode
    port: int
    passwords: dict[str, str] = field(repr=False)

    def dsn(self, key: str) -> str:
        database, login = _DATABASES[key]
        return f"postgresql://{login}:{self.passwords[key]}@127.0.0.1:{self.port}/{database}"

    def reference(self, key: str) -> SecretRef:
        return SecretRef(
            "file", str(self.state / "secrets" / f"postgres-{key.lower().replace('_', '-')}.dsn")
        )

    def environment(self, environ: Mapping[str, str], on_secret: Callable[[str], None]) -> dict[str, str]:
        for password in self.passwords.values():
            on_secret(password)
        return {
            **{key: value for key, value in environ.items() if not key.startswith("SKM_LOCAL_PG_")},
            "SKM_LOCAL_PG_PROJECT": f"skm-local-{self.installation_id.hex}",
            "SKM_LOCAL_PG_MODE": self.mode,
            "SKM_LOCAL_PG_PORT": str(self.port),
            **{
                ("SKM_LOCAL_PG_ADMIN_PASSWORD" if key == "ADMIN" else f"SKM_LOCAL_PG_{key}"): value
                for key, value in self.passwords.items()
            },
        }


def managed_postgres(state: Path) -> ManagedPostgres | None:
    path = state / "secrets" / _METADATA
    if not os.path.lexists(path):
        return None
    ensure_private_dir(path.parent)
    try:
        data = json.loads(read_private(path, 4096))
        if (
            data["mode"] not in ("standalone", "client")
            or type(data["port"]) is not int
            or not 1 <= data["port"] <= 65535
        ):
            raise ValueError
        keys = {
            "ADMIN",
            *(key for key in _DATABASES if data["mode"] == "standalone" or key.startswith("MACHINE")),
        }
        if set(data["passwords"]) != keys or any(
            len(value) != 64 or len(bytes.fromhex(value)) != 32 for value in data["passwords"].values()
        ):
            raise ValueError
        return ManagedPostgres(
            state, UUID(data["installation_id"]), data["mode"], data["port"], data["passwords"]
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Invalid local PostgreSQL installation metadata"
        ) from None


def local_postgres_state(environ: Mapping[str, str], home: Path) -> Path:
    if state := environ.get("SKM_STATE_DIR"):
        if state == "~":
            return home.absolute()
        if state.startswith("~/"):
            return (home / state[2:]).absolute()
        return Path(state).absolute()
    return (Path(environ.get("XDG_STATE_HOME") or home / ".local/state") / "skm").absolute()


def installation_id_from_env(environ: Mapping[str, str]) -> UUID | None:
    try:
        return UUID(environ["SKM_INSTALLATION_ID"]) if "SKM_INSTALLATION_ID" in environ else None
    except ValueError:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "SKM_INSTALLATION_ID must be a UUID") from None


def provision_local_postgres(
    state: Path,
    mode: _Mode,
    installation_id: UUID | None,
    environ: Mapping[str, str],
    *,
    on_secret: Callable[[str], None],
    wait: int = 60,
) -> ManagedPostgres:
    docker_command(environ, "version")  # detect an unavailable executable before creating private files
    secrets = state / "secrets"
    ensure_private_dir(secrets)
    with FileLock(secrets / "postgres.lock").hold(timeout_seconds=60):
        managed = managed_postgres(state)
        if managed is None:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.bind(("127.0.0.1", 0))
                port = int(sock.getsockname()[1])
            passwords = {
                key: token_hex(32)
                for key in (
                    "ADMIN",
                    *(_DATABASES if mode == "standalone" else ("MACHINE_APP", "MACHINE_MIGRATOR")),
                )
            }
            managed = ManagedPostgres(state, installation_id or uuid4(), mode, port, passwords)
            if not create_exclusive(
                secrets / _METADATA,
                json.dumps(
                    {
                        "installation_id": str(managed.installation_id),
                        "mode": mode,
                        "port": port,
                        "passwords": passwords,
                    }
                ).encode(),
            ):
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID, "Local PostgreSQL metadata was written concurrently"
                )
        if managed.mode != mode or (
            installation_id is not None and managed.installation_id != installation_id
        ):
            raise ValidationFailed(
                ErrorCode.CONFIG_INVALID, "Local PostgreSQL belongs to another installation or mode"
            )
        for key in managed.passwords.keys() - {"ADMIN"}:
            dsn = managed.dsn(key)
            on_secret(dsn)
            path = Path(managed.reference(key).path)
            content = dsn.encode()
            if not create_exclusive(path, content) and read_private(path, 4096) != content:
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID, "Local PostgreSQL DSN file disagrees with its installation"
                )
        compose_up(managed.environment(environ, on_secret), wait)
        return managed


def database_identity(dsn: str, *, require_machine_app: bool = False) -> tuple[object, ...]:
    with connect_single(PgSettings(dsn, "skm-local-storage-check", pool_timeout_seconds=3)) as conn:
        row = conn.execute(
            """
            SELECT oid, datname, pg_catalog.pg_postmaster_start_time()
            FROM pg_catalog.pg_database WHERE datname = current_database()
            """
        ).fetchone()
        if require_machine_app:
            eligible = conn.execute(
                """
                SELECT NOT rolsuper
                  AND EXISTS (
                      SELECT FROM pg_catalog.pg_roles AS app
                      WHERE app.rolname = 'skm_host_app'
                        AND pg_catalog.pg_has_role(current_user, app.oid, 'USAGE')
                  )
                  AND NOT EXISTS (
                      SELECT FROM pg_catalog.pg_roles AS migrator
                      WHERE migrator.rolname = 'skm_host_migrator'
                        AND pg_catalog.pg_has_role(current_user, migrator.oid, 'USAGE')
                  )
                FROM pg_catalog.pg_roles WHERE rolname = current_user
                """
            ).fetchone()
            if eligible != (True,):
                raise ValidationFailed(
                    ErrorCode.CONFIG_INVALID, "Machine runtime DSN needs the machine app role"
                )
    if row is None:
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Could not identify the PostgreSQL database")
    return row


def _machine_connections(
    config: BootstrapConfig,
    environ: Mapping[str, str],
    on_secret: Callable[[str], None],
    project_dsn: str | None,
) -> tuple[MigrationRunner, PostgresMachineStore, UUID]:
    if (
        config.installation_id is None
        or config.machine_database_url is None
        or config.machine_database_migrator_url is None
    ):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Machine storage needs an installation ID and separate DSN references"
        )
    resolvers = SecretResolvers(
        (EnvSecretResolver(environ), FileSecretResolver(), KeyringSecretResolver()), on_reveal=on_secret
    )
    app_dsn = resolvers.resolve(config.machine_database_url).reveal()
    migrator_dsn = resolvers.resolve(config.machine_database_migrator_url).reveal()
    for dsn in (app_dsn, migrator_dsn):
        if password := dsn_password(dsn):
            on_secret(password)
    machine = database_identity(app_dsn, require_machine_app=True)
    if machine != database_identity(migrator_dsn):
        raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Machine DSNs select different databases")
    if project_dsn is not None and machine == database_identity(project_dsn):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Machine and project DSNs must select separate databases"
        )
    runner = MigrationRunner(
        migrator_dsn,
        discover_migrations(database="machine"),
        package_loader(database="machine"),
        SystemClock(),
        "skm machine",
        database="machine",
    )
    return runner, PostgresMachineStore(app_dsn), config.installation_id


def prepare_machine_storage(
    config: BootstrapConfig,
    environ: Mapping[str, str],
    *,
    on_secret: Callable[[str], None],
    dry_run: bool = False,
    project_dsn: str | None = None,
) -> tuple[int, ...]:
    runner, app, installation_id = _machine_connections(config, environ, on_secret, project_dsn)
    applied = runner.migrate(dry_run=dry_run)
    if not applied:
        recorded = app.get_installation_id()
        if recorded is not None and recorded != installation_id:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Machine installation differs from bootstrap")
    if not dry_run:
        app.initialize_installation(installation_id)
    return applied


@dataclass(frozen=True, slots=True)
class InitMachineReport:
    installation_id: UUID
    instance_id: UUID
    migrations: tuple[int, ...]


def machine_database_refs(managed: ManagedPostgres | None, env: Mapping[str, str]) -> JsonObject:
    if managed is not None:
        return {
            "url": str(managed.reference("MACHINE_APP")),
            "migrator_url": str(managed.reference("MACHINE_MIGRATOR")),
        }
    app, migrator = "SKM_MACHINE_DATABASE_URL", "SKM_MACHINE_DATABASE_MIGRATOR_URL"
    if bool(env.get(app)) != bool(env.get(migrator)):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "Separate machine app and migrator DSNs are required"
        )
    return {"url": f"secret://env/{app}", "migrator_url": f"secret://env/{migrator}"} if env.get(app) else {}


def mark_managed_postgres(state: Path, managed: ManagedPostgres) -> None:
    atomic_write(state / "pids" / "postgres.compose", str(managed.installation_id).encode(), mode=0o600)


def init_machine_profile(
    path: Path,
    config: BootstrapConfig,
    environ: Mapping[str, str],
    home: Path,
    *,
    on_secret: Callable[[str], None],
) -> InitMachineReport:
    """Initialize local storage for an existing HTTPS profile."""
    endpoint = urlsplit(config.api_endpoint or "")
    if (
        config.access_mode != "http"
        or config.instance_id is None
        or endpoint.scheme != "https"
        or endpoint.hostname is None
        or endpoint.username is not None
        or endpoint.query
        or endpoint.fragment
        or endpoint.path != "/api/v1"
    ):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID, "A configured HTTPS profile is required for client storage"
        )
    path_source, document = read_bootstrap_document(str(path), environ, home)
    root = config.state_dir
    if config.profiles:
        paths = document.get("paths", {})
        configured = paths.get("state_dir") if isinstance(paths, dict) else None
        root = Path(environ.get("XDG_STATE_HOME") or home / ".local/state") / "skm"
        if isinstance(configured, str):
            root = home / configured[2:] if configured.startswith("~/") else Path(configured).absolute()
    managed = managed_postgres(root)
    reference = config.machine_database_url
    if managed is None and reference is not None and reference.scheme == "file":
        managed = managed_postgres(Path(reference.path).parent.parent)
        if managed is not None:
            root = managed.state
    if config.machine_database_url is None or managed is not None:
        managed = provision_local_postgres(
            root, managed.mode if managed else "client", config.installation_id, environ, on_secret=on_secret
        )
    installation = managed.installation_id if managed is not None else config.installation_id or uuid4()
    section = machine_database_refs(managed, environ)
    additions: list[str] = []
    if "installation_id" not in document:
        additions.append(f'installation_id = "{installation}"\n')
        document["installation_id"] = str(installation)
    if "machine_database" not in document and section:
        additions.append(
            "\n[machine_database]\n"
            + "".join(f"{key} = {json.dumps(value)}\n" for key, value in section.items())
        )
        document["machine_database"] = section
    setup = configure_bootstrap(path_source, document, environ, home, instance=config.instance_profile)
    applied = prepare_machine_storage(setup, environ, on_secret=on_secret)
    if additions:
        original = path.read_text(encoding="utf-8")
        prefix = next((entry for entry in additions if entry.startswith("installation_id = ")), "")
        suffix = next((entry for entry in additions if entry.startswith("\n[machine_database]")), "")
        updated = prefix + original.rstrip() + "\n" + suffix
        if decode_document(updated, "toml") != document:
            raise ValidationFailed(ErrorCode.CONFIG_INVALID, "Bootstrap changed during client initialization")
        atomic_write(path, updated.encode(), mode=0o600)
    if managed is not None:
        mark_managed_postgres(config.state_dir, managed)
    return InitMachineReport(installation, config.instance_id, applied)


def machine_postgres_status(
    config: BootstrapConfig, environ: Mapping[str, str], on_secret: Callable[[str], None]
) -> ComponentStatus:
    ref = config.machine_database_url
    if ref is None or config.installation_id is None:
        return ComponentStatus(SERVICE, "absent", "machine storage is not configured")
    resolver = SecretResolvers(
        (EnvSecretResolver(environ), FileSecretResolver(), KeyringSecretResolver()), on_reveal=on_secret
    )
    dsn = resolver.resolve(ref).reveal()
    if password := dsn_password(dsn):
        on_secret(password)
    try:
        installation = PostgresMachineStore(dsn).get_installation_id()
    except BackendUnavailable:
        return ComponentStatus(SERVICE, "unavailable", "machine database")
    state = "running" if installation == config.installation_id else "invalid"
    return ComponentStatus(SERVICE, state, "machine database")


def compose_file() -> Path:
    """The packaged compose file: wheel data ``skm/_deploy`` first, then the source checkout's ``deploy/``."""
    here = Path(__file__).resolve()
    for candidate in (here.parents[1] / "_deploy" / _COMPOSE, here.parents[3] / "deploy" / _COMPOSE):
        if candidate.is_file():
            return candidate
    raise CapabilityUnavailable(
        ErrorCode.CAPABILITY_UNAVAILABLE,
        "the packaged compose file for the local PostgreSQL is missing from this installation",
        details={
            "file": _COMPOSE,
            "hint": "reinstall skm, or run your own PostgreSQL and use skm init --database-url",
        },
    )


def docker_command(
    environ: Mapping[str, str], *arguments: str
) -> tuple[tuple[str, ...], Path, dict[str, str]]:
    docker = shutil.which("docker", path=environ.get("PATH", defpath))
    if docker is None:
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE,
            "Docker is not available: skm local runs PostgreSQL with docker compose; no docker on PATH",
            details={
                "component": SERVICE,
                "hint": "install Docker Engine or Desktop with compose v2, "
                "or run your own PostgreSQL and use skm init --database-url",
            },
        )
    file = compose_file()
    project = environ.get("SKM_LOCAL_PG_PROJECT")
    project_args = ("--project-name", project) if project else ()
    argv = (docker, "compose", *project_args, "-f", str(file), *arguments)
    return argv, file.parent, build_env(environ, allow=_DOCKER_ENV)


def compose(environ: Mapping[str, str], *arguments: str, timeout: float = _COMMAND_SECONDS) -> ProcessResult:
    argv, cwd, env = docker_command(environ, *arguments)
    return run(argv, cwd=cwd, env=env, timeout_seconds=timeout)


def compose_failed(result: ProcessResult, message: str) -> BackendUnavailable:
    tail = result.stderr.decode("utf-8", "replace").strip()[-_STDERR_TAIL:]
    return BackendUnavailable(
        ErrorCode.BACKEND_UNAVAILABLE,
        message,
        details={
            "component": SERVICE,
            "exit_code": result.exit_code,
            "timed_out": result.timed_out,
            "stderr": tail,
            "hint": "check the Docker daemon and the assigned loopback PostgreSQL port",
        },
    )


def _containers(stdout: bytes) -> list[dict[str, JsonValue]]:
    """``docker compose ps --format json``: a JSON array (compose < 2.21) or one object per line."""
    text = stdout.decode("utf-8", "replace").strip()
    if not text:
        return []
    try:
        if text.startswith("["):
            items = cast("list[JsonValue]", json.loads(text))
        else:
            items = [cast("JsonValue", json.loads(line)) for line in text.splitlines() if line.strip()]
    except ValueError:
        return []
    return [cast("dict[str, JsonValue]", item) for item in items if isinstance(item, dict)]


def _published(container: dict[str, JsonValue]) -> str:
    publishers = container.get("Publishers")
    for item in publishers if isinstance(publishers, list) else []:
        if isinstance(item, dict) and item.get("PublishedPort"):
            return f"{item.get('URL') or '127.0.0.1'}:{item['PublishedPort']}"
    return ""


def compose_status(environ: Mapping[str, str]) -> ComponentStatus:
    result = compose(environ, "ps", "--all", "--format", "json", SERVICE)
    if result.exit_code != 0:
        raise compose_failed(result, "docker compose could not report the local PostgreSQL")
    found = [item for item in _containers(result.stdout) if item.get("Service", SERVICE) == SERVICE]
    if not found:
        return ComponentStatus(SERVICE, "absent", "not created (skm local up)")
    container = found[0]
    state = str(container.get("State") or "unknown")
    health = str(container.get("Health") or "")
    shown = "running" if state == "running" and health in {"", "healthy"} else state
    detail = ", ".join(part for part in (_published(container), health) if part)
    return ComponentStatus(SERVICE, shown, detail)


def _postgres_ready(dsn: str) -> bool:
    try:
        with connect_single(PgSettings(dsn, "skm-local-status", pool_timeout_seconds=2)):
            return True
    except BackendUnavailable:
        return False


def compose_up(environ: Mapping[str, str], wait: int) -> ComponentStatus:
    started = compose(
        environ,
        "up",
        "--detach",
        "--wait",
        "--wait-timeout",
        str(wait),
        SERVICE,
        timeout=wait + _COMMAND_SECONDS,
    )
    if started.exit_code:
        raise compose_failed(started, "docker compose could not start a healthy local PostgreSQL")
    return compose_status(environ)


def compose_stop(environ: Mapping[str, str]) -> ComponentStatus:
    stopped = compose(environ, "stop", SERVICE)
    if stopped.exit_code:
        raise compose_failed(stopped, "docker compose could not stop the local PostgreSQL")
    return compose_status(environ)


def external_status(dsn: str) -> ComponentStatus:
    return ComponentStatus(SERVICE, "running" if _postgres_ready(dsn) else "unavailable", "external")


def postgres_up(
    dsn: str, environ: Mapping[str, str], marker: Path, instance_id: str, wait: int
) -> ComponentStatus:
    if manages_postgres(marker, instance_id):
        return compose_up(environ, wait)
    if _postgres_ready(dsn):
        return ComponentStatus(SERVICE, "running", "external")
    raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "The configured PostgreSQL is unavailable")


def postgres_logs(environ: Mapping[str, str], lines: int, *, follow: bool) -> Generator[str]:
    flags = ("logs", "--no-color", "--tail", str(lines))
    if follow:
        argv, cwd, env = docker_command(environ, *flags, "--follow", SERVICE)
        yield from follow_process_log(argv, cwd, env)
        return
    result = compose(environ, *flags, SERVICE)
    if result.exit_code:
        raise compose_failed(result, "docker compose could not read PostgreSQL logs")
    yield from result.stdout.decode("utf-8", "replace").splitlines()
