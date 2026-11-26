"""Bootstrap v1 selection and process-start checks (settings §B.11.1, kernel §5.3)."""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Collection, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast
from uuid import UUID

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.generated._codec import SecretRef
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import Surface
from skm.platform.config._bootstrap_schema import BOOTSTRAP_URN, validate_bootstrap_document

if TYPE_CHECKING:
    from skm.platform.config.effective import EffectiveConfig, ProcessConfig

__all__ = [
    "BOOTSTRAP_SEARCH",
    "BOOTSTRAP_URN",
    "BootstrapConfig",
    "WebAuthConfig",
    "apply_process_config",
    "configure_bootstrap",
    "load_bootstrap",
    "pool_capacity",
    "read_bootstrap_document",
    "validate_profile_roots",
    "validate_worker_host",
]

BOOTSTRAP_SEARCH = (
    "--bootstrap",
    "$SKM_BOOTSTRAP",
    "$XDG_CONFIG_HOME/skm/bootstrap.toml",
    "~/.config/skm/bootstrap.toml",
    "/etc/skm/bootstrap.toml",
)
_URN = BOOTSTRAP_URN


@dataclass(frozen=True, slots=True)
class WebAuthConfig:
    mode: Literal["admin_login", "none"] = "admin_login"
    forwarded_allow_ips: tuple[str, ...] = ()
    session_ttl_seconds: int = 43_200
    cookie_samesite: Literal["lax", "strict"] = "lax"
    login_rate_limit_max: int = 10
    login_rate_limit_window_seconds: int = 60


@dataclass(frozen=True, slots=True)
class BootstrapConfig:
    source: str
    instance_id: UUID | None
    access_mode: Literal["embedded", "http"]
    database_url: SecretRef | str | None = field(repr=False)
    database_migrate_on_start: bool
    database_application_name: str
    database_migrator_url: SecretRef | None = field(repr=False)
    database_pool_min_size: int
    database_pool_max_size: int | None
    database_pool_timeout_seconds: int
    api_endpoint: str | None
    api_credential: SecretRef | str | None = field(repr=False)
    api_ca_bundle: Path | None
    api_timeout_seconds: float
    token_pepper: SecretRef | None = field(repr=False)
    instance_profile: str | None
    profiles: tuple[str, ...]
    state_dir: Path
    blobs_root: Path
    worktrees_root: Path
    materialized_root: Path
    backups_root: Path
    host_id: UUID | Literal["auto"]
    host_name: str
    web_auth: WebAuthConfig = field(default_factory=WebAuthConfig)
    installation_id: UUID | None = None
    machine_database_url: SecretRef | None = field(default=None, repr=False)
    machine_database_migrator_url: SecretRef | None = field(default=None, repr=False)


def _invalid(field_name: str, reason: str) -> ValidationFailed:
    return ValidationFailed(
        ErrorCode.CONFIG_INVALID,
        "Invalid bootstrap configuration",
        details={"field": field_name, "reason": reason},
    )


def _validate(document: Mapping[str, JsonValue]) -> None:
    validate_bootstrap_document(document)


def _table(document: Mapping[str, JsonValue], name: str) -> dict[str, JsonValue]:
    return dict(cast("Mapping[str, JsonValue]", document.get(name, {})))


def _expand(value: str, home: Path, state_dir: Path | None = None) -> Path:
    if state_dir is not None:
        value = value.replace("${state_dir}", str(state_dir))
    if value == "~":
        return home.absolute()
    if value.startswith("~/"):
        return (home / value[2:]).absolute()
    return Path(value).expanduser().absolute()


def read_bootstrap_document(
    cli_path: str | None, environ: Mapping[str, str], home: Path
) -> tuple[str, dict[str, JsonValue]]:
    candidates = [cli_path, environ.get("SKM_BOOTSTRAP")]
    xdg = environ.get("XDG_CONFIG_HOME")
    candidates.extend(
        (
            str(Path(xdg) / "skm/bootstrap.toml") if xdg else None,
            str(home / ".config/skm/bootstrap.toml"),
            "/etc/skm/bootstrap.toml",
        )
    )
    for candidate in candidates:
        if candidate is None:
            continue
        path = _expand(candidate, home)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            continue
        except (OSError, UnicodeError):
            raise _invalid("bootstrap", "unreadable") from None
        from skm.platform.config.sources.document import decode_document

        try:
            document = decode_document(text, "toml")
        except (ValueError, TypeError, RecursionError):
            raise _invalid("bootstrap", "toml") from None
        _validate(document)
        validate_profile_roots(document, home)
        return str(path), document
    if "SKM_DATABASE_URL" in environ:
        return "env", {"schema": _URN, "access": {"mode": "embedded"}}
    if "SKM_API_ENDPOINT" in environ:
        return "env", {"schema": _URN, "access": {"mode": "http"}}
    raise PreconditionFailed(
        ErrorCode.BOOTSTRAP_MISSING, "Bootstrap missing; run skm init", details={"hint": "skm init"}
    )


def _select(
    document: dict[str, JsonValue],
    instance: str | None,
    environ: Mapping[str, str],
    cwd_profile: str | None,
) -> tuple[dict[str, JsonValue], str | None, tuple[str, ...]]:
    profiles = _table(document, "instances")
    if not profiles:
        if instance is not None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "Instance profile not found",
                details={"kind": "instance_profile", "name": instance, "known": []},
            )
        if "SKM_INSTANCE" in environ:
            import logging

            logging.getLogger(__name__).warning("SKM_INSTANCE ignored for single-instance bootstrap")
        return dict(document), None, ()
    selected = next(
        value
        for value in (
            instance,
            environ.get("SKM_INSTANCE"),
            cwd_profile,
            cast("str", document["default_instance"]),
        )
        if value is not None
    )
    names = tuple(sorted(profiles))
    if selected not in profiles:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "Instance profile not found",
            details={
                "kind": "instance_profile",
                "name": selected,
                "known": list(names),
            },
        )
    profile = dict(cast("Mapping[str, JsonValue]", profiles[selected]))
    paths = _profile_paths(document, profile, selected)
    host = _table(document, "host")
    host.update(_table(profile, "host"))
    web_auth = _table(document, "web_auth")
    web_auth.update(_table(profile, "web_auth"))
    profile.update({"schema": _URN, "paths": paths, "host": host})
    for key in ("installation_id", "machine_database"):
        if key in document:
            profile[key] = document[key]
    if web_auth:
        profile["web_auth"] = web_auth
    return profile, selected, names


def _profile_paths(
    document: Mapping[str, JsonValue], profile: Mapping[str, JsonValue], name: str
) -> dict[str, JsonValue]:
    paths = _table(document, "paths")
    profile_paths = _table(profile, "paths")
    if "state_dir" not in profile_paths:
        paths["state_dir"] = str(paths.get("state_dir", "~/.local/state/skm")) + f"/instances/{name}"
    if "blobs_root" not in profile_paths:
        paths["blobs_root"] = str(paths.get("blobs_root", "~/.local/share/skm/blobs")) + f"/{name}"
    paths.update(profile_paths)
    return paths


def validate_profile_roots(
    document: Mapping[str, JsonValue],
    home: Path,
    *,
    selected: str | None = None,
    state_override: str | None = None,
) -> None:
    seen: list[Path] = []
    for name, profile in _table(document, "instances").items():
        paths = _profile_paths(document, cast("Mapping[str, JsonValue]", profile), name)
        state_path = str(paths["state_dir"])
        if name == selected and state_override is not None:
            state_path = state_override
        try:
            state = _expand(state_path, home)
            blobs = _expand(str(paths["blobs_root"]), home, state)
            roots = (state.resolve(), blobs.resolve())
        except (OSError, RuntimeError):
            raise _invalid("paths", "unresolvable_profile_root") from None
        if roots[0] == roots[1] or any(
            root.is_relative_to(other) or other.is_relative_to(root) for root in roots for other in seen
        ):
            raise _invalid(f"instances.{name}.paths", "overlapping_profile_roots")
        seen.extend(roots)


_ENV_FIELDS = {
    "SKM_ACCESS_MODE": ("access", "mode"),
    "SKM_INSTANCE_ID": ("", "instance_id"),
    "SKM_INSTALLATION_ID": ("", "installation_id"),
    "SKM_DATABASE_URL": ("database", "url"),
    "SKM_API_ENDPOINT": ("api", "endpoint"),
    "SKM_API_TOKEN": ("api", "credential"),
    "SKM_STATE_DIR": ("paths", "state_dir"),
    "SKM_HOST_ID": ("host", "id"),
    "SKM_WEB_AUTH_MODE": ("web_auth", "mode"),
}


def _clone_json(value: JsonValue) -> JsonValue:
    if isinstance(value, Mapping):
        return {str(key): _clone_json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_clone_json(item) for item in value]
    return value


def _environment(document: dict[str, JsonValue], environ: Mapping[str, str], source: str) -> None:
    for name, (section, key) in _ENV_FIELDS.items():
        if name not in environ:
            continue
        if section:
            table = _table(document, section)
            table[key] = environ[name]
            document[section] = table
        else:
            document[key] = environ[name]
    machine_database = _table(document, "machine_database")
    for variable, key in (
        ("SKM_MACHINE_DATABASE_URL", "url"),
        ("SKM_MACHINE_DATABASE_MIGRATOR_URL", "migrator_url"),
    ):
        if variable in environ:
            if not environ[variable]:
                raise _invalid(f"machine_database.{key}", "empty_credential")
            machine_database[key] = f"secret://env/{variable}"
    if machine_database:
        document["machine_database"] = machine_database
    checked = cast("dict[str, JsonValue]", _clone_json(document))
    for variable, section, key in (
        ("SKM_DATABASE_URL", "database", "url"),
        ("SKM_API_TOKEN", "api", "credential"),
    ):
        if variable in environ:
            if not environ[variable]:
                raise _invalid(f"{section}.{key}", "empty_credential")
            table = _table(checked, section)
            table[key] = "secret://env/BOOTSTRAP_LITERAL"
            checked[section] = table
    if source == "env" and "instance_id" not in checked:
        checked["instance_id"] = "00000000-0000-0000-0000-000000000000"
    _validate(checked)


def _reference(table: Mapping[str, JsonValue], key: str) -> SecretRef | None:
    value = table.get(key)
    return None if value is None else SecretRef.parse(cast("str", value))


def load_bootstrap(
    cli_path: str | None,
    environ: Mapping[str, str],
    home: Path,
    *,
    instance: str | None = None,
    cwd_profile: str | None = None,
) -> BootstrapConfig:
    source, document = read_bootstrap_document(cli_path, environ, home)
    return configure_bootstrap(source, document, environ, home, instance=instance, cwd_profile=cwd_profile)


def configure_bootstrap(
    source: str,
    document: dict[str, JsonValue],
    environ: Mapping[str, str],
    home: Path,
    *,
    instance: str | None = None,
    cwd_profile: str | None = None,
) -> BootstrapConfig:
    """Resolve one profile from an already read bootstrap snapshot."""
    effective, profile, profiles = _select(document, instance, environ, cwd_profile)
    if "SKM_STATE_DIR" in environ:
        validate_profile_roots(document, home, selected=profile, state_override=environ["SKM_STATE_DIR"])
    _environment(effective, environ, source)
    database, api = _table(effective, "database"), _table(effective, "api")
    paths, host = (_table(effective, name) for name in ("paths", "host"))
    state = _expand(cast("str", paths.get("state_dir", "~/.local/state/skm")), home)
    db_url = environ["SKM_DATABASE_URL"] if "SKM_DATABASE_URL" in environ else _reference(database, "url")
    credential = environ["SKM_API_TOKEN"] if "SKM_API_TOKEN" in environ else _reference(api, "credential")
    host_id = host.get("id", "auto")
    raw_host_name = host.get("name")
    if raw_host_name is None:
        if "socket" not in sys.modules and hasattr(os, "uname"):
            host_name = os.uname().nodename.lower()
        else:
            import socket

            host_name = socket.gethostname().lower()
    else:
        host_name = cast("str", raw_host_name)
    web_auth_table = _table(effective, "web_auth")
    web_auth = WebAuthConfig(
        mode=cast('Literal["admin_login", "none"]', web_auth_table.get("mode", "admin_login")),
        forwarded_allow_ips=tuple(
            str(item) for item in cast("list[str]", web_auth_table.get("forwarded_allow_ips", []))
        ),
        session_ttl_seconds=cast("int", web_auth_table.get("session_ttl_seconds", 43_200)),
        cookie_samesite=cast('Literal["lax", "strict"]', web_auth_table.get("cookie_samesite", "lax")),
        login_rate_limit_max=cast("int", web_auth_table.get("login_rate_limit_max", 10)),
        login_rate_limit_window_seconds=cast(
            "int", web_auth_table.get("login_rate_limit_window_seconds", 60)
        ),
    )
    return BootstrapConfig(
        source=source,
        instance_id=UUID(str(effective["instance_id"])) if "instance_id" in effective else None,
        access_mode=cast('Literal["embedded", "http"]', _table(effective, "access")["mode"]),
        database_url=db_url,
        database_migrate_on_start=cast("bool", database.get("migrate_on_start", False)),
        database_application_name=cast("str", database.get("application_name", "skm")),
        database_migrator_url=_reference(database, "migrator_url"),
        database_pool_min_size=cast("int", database.get("pool_min_size", 1)),
        database_pool_max_size=cast("int | None", database.get("pool_max_size")),
        database_pool_timeout_seconds=cast("int", database.get("pool_timeout_seconds", 10)),
        api_endpoint=cast("str | None", api.get("endpoint")),
        api_credential=credential,
        api_ca_bundle=_expand(str(api["ca_bundle"]), home, state) if "ca_bundle" in api else None,
        api_timeout_seconds=float(cast("float", api.get("timeout_seconds", 30))),
        token_pepper=_reference(_table(effective, "secrets"), "token_pepper"),
        instance_profile=profile,
        profiles=profiles,
        state_dir=state,
        blobs_root=_expand(cast("str", paths.get("blobs_root", "~/.local/share/skm/blobs")), home, state),
        worktrees_root=_expand(
            cast("str", paths.get("worktrees_root", "${state_dir}/worktrees")), home, state
        ),
        materialized_root=_expand(
            cast("str", paths.get("materialized_root", "${state_dir}/materialized")), home, state
        ),
        backups_root=_expand(cast("str", paths.get("backups_root", "${state_dir}/backups")), home, state),
        host_id="auto" if host_id == "auto" else UUID(str(host_id)),
        host_name=host_name,
        web_auth=web_auth,
        installation_id=UUID(str(effective["installation_id"])) if "installation_id" in effective else None,
        machine_database_url=_reference(_table(effective, "machine_database"), "url"),
        machine_database_migrator_url=_reference(_table(effective, "machine_database"), "migrator_url"),
    )


def _resolve_snapshot_host(
    bootstrap: BootstrapConfig, process: ProcessConfig, surface: Surface
) -> BootstrapConfig:
    from skm.platform.config.keys import Level

    target = process.host_target
    if (
        bootstrap.host_id == "auto"
        and target is not None
        and target.level is Level.HOST
        and surface in (Surface.CLI, Surface.WORKER, Surface.HOOK)
    ):
        return _resolve_recorded_host(bootstrap, surface=surface)
    return bootstrap


def _process_identity(bootstrap: BootstrapConfig, process: ProcessConfig) -> UUID:
    from skm.platform.config.keys import Level

    instance_id = process.instance_scope_id
    if instance_id is None or (bootstrap.instance_id is not None and bootstrap.instance_id != instance_id):
        raise _invalid("instance_id", "process_identity_mismatch")
    target = process.host_target
    if target is not None and target.level is Level.HOST and target.scope_id != bootstrap.host_id:
        raise _invalid("host.id", "process_identity_mismatch")
    return instance_id


def _startup_worker_capacity(process: ProcessConfig, startup_host: EffectiveConfig | None) -> JsonValue:
    """Capacity is live: read the validated startup host slice, never the restart-only snapshot."""
    from skm.platform.config.keys import Chain, Level

    if startup_host is None or startup_host.chain.kind is not Chain.HOST:
        raise _invalid("worker.capacity", "startup_host_required")
    chain = startup_host.chain
    if chain.scopes[0].scope_id != process.instance_scope_id:
        raise _invalid("instance_id", "startup_identity_mismatch")
    if chain.target.level is not Level.HOST or chain.target != process.host_target:
        raise _invalid("host.id", "startup_identity_mismatch")
    if startup_host.generation != process.generation:
        raise _invalid("worker.capacity", "startup_generation_mismatch")
    return startup_host.get("worker.capacity")


def pool_capacity(
    bootstrap: BootstrapConfig,
    process: ProcessConfig,
    *,
    surface: Surface,
    enabled_background_services: Collection[str] = (),
    startup_host: EffectiveConfig | None = None,
) -> int:
    """bootstrap.pool_capacity: run after ProcessConfig and before constructing the process pool."""
    bootstrap = _resolve_snapshot_host(bootstrap, process, surface)
    _process_identity(bootstrap, process)
    minimum = 2
    if surface in (Surface.API, Surface.BACKGROUND, Surface.WORKER):
        key = "worker.capacity" if surface is Surface.WORKER else "api.threadpool.size"
        value = (
            _startup_worker_capacity(process, startup_host)
            if surface is Surface.WORKER
            else process.host.get(key)
        )
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise _invalid(key, "process_value_required")
        minimum = (
            2 * value + 2 if surface is Surface.WORKER else value + len(set(enabled_background_services)) + 3
        )
    maximum = bootstrap.database_pool_max_size
    if maximum is not None and maximum < minimum:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "Database pool is below the surface minimum",
            details={"field": "database.pool_max_size", "minimum": minimum},
        )
    maximum = minimum if maximum is None else maximum
    if maximum < bootstrap.database_pool_min_size or maximum > 256:
        raise _invalid("database.pool_max_size", "pool_bounds")
    return maximum


def apply_process_config(
    bootstrap: BootstrapConfig,
    process: ProcessConfig,
    *,
    surface: Surface,
    enabled_background_services: Collection[str] = (),
    startup_host: EffectiveConfig | None = None,
) -> BootstrapConfig:
    """Materialize pool defaults from the same instance/host startup snapshot; preserve its identity."""
    bootstrap = _resolve_snapshot_host(bootstrap, process, surface)
    instance_id = _process_identity(bootstrap, process)
    if bootstrap.access_mode == "http":
        return replace(bootstrap, instance_id=instance_id)
    maximum = pool_capacity(
        bootstrap,
        process,
        surface=surface,
        enabled_background_services=enabled_background_services,
        startup_host=startup_host,
    )
    return replace(bootstrap, instance_id=instance_id, database_pool_max_size=maximum)


def validate_worker_host(bootstrap: BootstrapConfig, *, surface: Surface = Surface.WORKER) -> BootstrapConfig:
    """Resolve a previously registered local host; workers/hooks never register or contact the server here."""
    if surface not in (Surface.WORKER, Surface.HOOK) or bootstrap.host_id != "auto":
        return bootstrap
    return _resolve_recorded_host(bootstrap, surface=surface)


def _resolve_recorded_host(bootstrap: BootstrapConfig, *, surface: Surface) -> BootstrapConfig:
    try:
        document = json.loads((bootstrap.state_dir / "host.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        document = None
    except (OSError, ValueError, UnicodeError):
        raise _invalid("host.id", "host_state_invalid") from None
    if document is not None:
        try:
            host_id = UUID(document["host_id"])
        except (TypeError, ValueError, KeyError, AttributeError):
            raise _invalid("host.id", "host_state_invalid") from None
        return replace(bootstrap, host_id=host_id)
    if surface is Surface.WORKER and bootstrap.access_mode == "http":
        raise _invalid("host.id", "auto_forbidden_in_http")
    raise PreconditionFailed(
        ErrorCode.INVALID_TRANSITION,
        "Host is not registered; run skm host register",
        details={"reason": "host_not_registered", "hint": "skm host register"},
    )
