"""Bind authorized project callers and local session handles to one machine installation."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable, Generator, Mapping
from contextlib import AbstractContextManager, closing, contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Literal
from uuid import UUID

from skm.application_bus.client import SkmClient
from skm.bootstrap.machine import (
    machine_socket_path,
    open_machine_store,
    pin_machine_config,
    resolve_machine_profile,
)
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError, error_for
from skm.kernel.ids import HostId, ProjectId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.access.public import WhoAmI, WhoAmIView
from skm.modules.workspace.public import GetProject, GetWorkspace, ProjectView, WorkspaceView
from skm.platform.config.bootstrap import BootstrapConfig
from skm.platform.config.generated.settings import UiLocale, UiTheme
from skm.platform.machine import MachinePrincipal, MachineProfile, MachineSession, MachineStore
from skm.platform.system_clock import SystemClock

if TYPE_CHECKING:
    from skm.platform.config.sources.bootstrap import ProfileCatalog

__all__ = [
    "SELECTION_KEY",
    "MachineAuthority",
    "MachineCaller",
    "MachineOperation",
    "MachineOperationHandler",
    "MachineProject",
    "MachineServerConfig",
    "build_machine_server",
    "machine_project_opener",
    "machine_user_scope",
    "require_human_identity",
    "require_user_setting",
    "run_machine_operation",
    "validate_user_setting",
]

SELECTION_KEY = "context.selection"
_PREFERENCES = {"ui.locale": frozenset(UiLocale), "ui.theme": frozenset(UiTheme)}
_SESSION_TTL = timedelta(minutes=10)
type MachineOperation = Literal[
    "repo.bind",
    "repo.verify",
    "integrations.plan",
    "integrations.apply",
    "integrations.doctor",
    "integrations.list",
    "workspace.sync-projections",
]


@dataclass(frozen=True, slots=True)
class MachineProject:
    client: SkmClient
    host_id: HostId | None
    config: BootstrapConfig | None = None
    environ: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class MachineCaller:
    scope: MachinePrincipal
    profile: MachineProfile
    project: MachineProject
    store: MachineStore

    @property
    def client(self) -> SkmClient:
        return self.project.client

    @property
    def host_id(self) -> HostId:
        host = self.project.host_id
        if host is None:
            raise error_for(ErrorCode.CONFIG_INVALID, "A registered local host is required")
        return host


type MachineOperationHandler = Callable[[MachineOperation, MachineCaller, JsonObject, UUID | None], JsonValue]
type _ProjectOpener = Callable[[MachineProfile, str], AbstractContextManager[MachineProject]]


def machine_project_opener(catalog_loader: Callable[[], ProfileCatalog]) -> _ProjectOpener:
    """Open a pinned client with the explicitly presented token for every incoming request."""
    from skm.bootstrap.composition import build_app
    from skm.bootstrap.host_services import read_recorded_host_id
    from skm.bootstrap.instance_secrets import open_http_client
    from skm.kernel.ports_uow import Surface

    @contextmanager
    def project(profile: MachineProfile, token: str) -> Generator[MachineProject]:
        catalog = catalog_loader()
        config = pin_machine_config(catalog.config(profile.name), profile)
        host = (
            HostId(config.host_id)
            if isinstance(config.host_id, UUID)
            else read_recorded_host_id(config.state_dir)
        )
        if config.access_mode == "http":
            with closing(open_http_client(config, catalog.environ, as_token=token)) as client:
                if host is not None:
                    client.bind_host(host)
                yield MachineProject(client, host, config, catalog.environ)
        else:
            with closing(
                build_app(
                    config,
                    surface=Surface.CLI,
                    environ=catalog.environ,
                    invocation={},
                    load_project_plugins=False,
                )
            ) as app:
                if app.instance_id != profile.instance_id:
                    raise error_for(ErrorCode.CONFIG_INVALID, "Embedded database identity changed")
                actor = app.authenticate(token)
                yield MachineProject(
                    app.client(actor=actor, surface=Surface.CLI), host, config, catalog.environ
                )

    return project


def _handle_hash(handle: str) -> str:
    return hashlib.sha256(handle.encode("ascii")).hexdigest()


class MachineAuthority:
    """Verify project identity online and resolve user scope from a stored handle offline."""

    def __init__(
        self,
        store: MachineStore,
        installation_id: UUID,
        open_project: _ProjectOpener,
        *,
        clock: Clock | None = None,
    ) -> None:
        self.store = store
        self.installation_id = installation_id
        self._open_project = open_project
        self._clock = clock if clock is not None else SystemClock()

    def profile(self, name: str) -> MachineProfile:
        return resolve_machine_profile(self.store, self.installation_id, name)

    @contextmanager
    def caller(self, name: str, token: str) -> Generator[tuple[MachineCaller, datetime | None]]:
        profile = self.profile(name)
        with self._open_project(profile, token) as project:
            identity = project.client.ask(WhoAmI())
            principal_id, expires_at = require_human_identity(identity)
            if self.profile(name) != profile:
                raise error_for(ErrorCode.VERSION_CONFLICT, "Machine profile changed during authentication")
            scope = MachinePrincipal(self.installation_id, profile.instance_id, principal_id)
            yield MachineCaller(scope, profile, project, self.store), expires_at

    def scope(self, handle: str) -> MachinePrincipal:
        scope = self.store.get_session(self.installation_id, _handle_hash(handle), self._clock.now())
        if scope is None:
            raise error_for(ErrorCode.UNAUTHENTICATED, "An active machine session handle is required")
        return scope

    def logout(self, handle: str) -> None:
        self.store.delete_session(self.installation_id, _handle_hash(handle))

    def login(self, name: str, token: str, previous_handle: str | None = None) -> JsonObject:
        try:
            with self.caller(name, token) as (caller, token_expires):
                if previous_handle is not None and self.scope(previous_handle) != caller.scope:
                    raise error_for(ErrorCode.FORBIDDEN, "Machine session is outside the caller's scope")
                now = self._clock.now()
                expires = min(now + _SESSION_TTL, token_expires) if token_expires else now + _SESSION_TTL
                if expires <= now:
                    raise error_for(ErrorCode.UNAUTHENTICATED, "Project token has expired")
                handle = secrets.token_urlsafe(32)
                record = MachineSession(
                    caller.profile, caller.scope.principal_id, _handle_hash(handle), expires
                )
                if not self.store.put_session(record):
                    raise error_for(
                        ErrorCode.VERSION_CONFLICT, "Machine profile changed during authentication"
                    )
        except SkmError as error:
            if previous_handle is not None and error.code is ErrorCode.UNAUTHENTICATED:
                self.logout(previous_handle)
            raise
        if previous_handle is not None:
            self.logout(previous_handle)
        return {
            "handle": handle,
            "expires_at": expires.isoformat(),
            "instance_id": str(caller.scope.instance_id),
        }


def require_human_identity(identity: object) -> tuple[UUID, datetime | None]:
    if (
        not isinstance(identity, WhoAmIView)
        or identity.principal.kind != "human"
        or identity.token is None
        or identity.token.kind != "personal"
    ):
        raise error_for(ErrorCode.UNAUTHENTICATED, "A personal token for a human principal is required")
    return identity.principal.principal_id, identity.token.expires_at


def machine_user_scope(
    configuration: BootstrapConfig, identity: Callable[[], object]
) -> Callable[[], MachinePrincipal] | None:
    """Resolve a personal CLI session to its machine settings namespace on first use."""
    installation, instance = configuration.installation_id, configuration.instance_id
    if installation is None or instance is None:
        return None

    @cache
    def scope() -> MachinePrincipal:
        principal, _ = require_human_identity(identity())
        return MachinePrincipal(installation, instance, principal)

    return scope


def require_user_setting(key: str) -> None:
    if key != SELECTION_KEY and key not in _PREFERENCES:
        raise error_for(ErrorCode.NOT_FOUND, "Unknown machine user setting")


def _selection_id(selection: Mapping[str, JsonValue], key: str) -> UUID | None:
    value = selection.get(key)
    if value is None:
        return None
    try:
        if isinstance(value, str):
            return UUID(value)
    except ValueError:
        pass
    raise error_for(ErrorCode.SCHEMA_INVALID, f"Invalid {key}")


def validate_user_setting(key: str, value: JsonValue, client: SkmClient) -> JsonValue:
    """Validate the closed setting list and resolve new context under the same project caller."""
    require_user_setting(key)
    if key in _PREFERENCES:
        if not isinstance(value, str) or value not in _PREFERENCES[key]:
            raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid machine preference value")
        return value
    if not isinstance(value, dict) or set(value) - {"workspace_id", "project_id"}:
        raise error_for(ErrorCode.SCHEMA_INVALID, "Invalid context selection")
    workspace_id, project_id = _selection_id(value, "workspace_id"), _selection_id(value, "project_id")
    if project_id is not None:
        project = client.ask(GetProject(project_id=ProjectId(project_id)))
        if (
            not isinstance(project, ProjectView)
            or project.workspace_id != workspace_id
            or project.state != "active"
        ):
            raise error_for(ErrorCode.INVALID_REFERENCE, "Project is outside the selected active workspace")
    if workspace_id is not None:
        workspace = client.ask(GetWorkspace(workspace_id=WorkspaceId(workspace_id)))
        if not isinstance(workspace, WorkspaceView) or workspace.state != "active":
            raise error_for(ErrorCode.INVALID_REFERENCE, "Selected workspace is unavailable or inactive")
    return {
        "workspace_id": str(workspace_id) if workspace_id is not None else None,
        "project_id": str(project_id) if project_id is not None else None,
    }


def run_machine_operation(
    operation: MachineOperation, caller: MachineCaller, payload: JsonObject, request_id: UUID | None
) -> JsonValue:
    """Production binding for the scoped host operation endpoints."""
    if operation in ("repo.bind", "repo.verify"):
        from skm.adapters.git.repo_inspect import GitRepositoryInspector
        from skm.bootstrap.checkout_operations import LocalCheckoutResolver, run_checkout_operation

        if request_id is None:
            raise error_for(ErrorCode.PRECONDITION_REQUIRED, "A UUID Idempotency-Key is required")
        resolver = LocalCheckoutResolver(
            caller.scope, caller.host_id, caller.store, caller.client, GitRepositoryInspector()
        )
        return run_checkout_operation(
            "bind" if operation == "repo.bind" else "verify", resolver, payload, request_id
        )
    from skm.bootstrap.projection_wiring import run_machine_projection_operation

    return run_machine_projection_operation(operation, caller, payload)


@dataclass(frozen=True, slots=True)
class MachineServerConfig:
    authority: MachineAuthority
    profile: str
    socket: Path


def build_machine_server(
    catalog_loader: Callable[[], ProfileCatalog], profile: str, *, on_secret: Callable[[str], None]
) -> MachineServerConfig:
    """Compose the configured installation without opening a project connection at startup."""

    catalog = catalog_loader()
    config = catalog.config(profile)
    store = open_machine_store(config, catalog.environ, on_secret=on_secret)
    installation = config.installation_id
    assert installation is not None  # noqa: S101 -- checked by open_machine_store
    authority = MachineAuthority(store, installation, machine_project_opener(catalog_loader))
    path = machine_socket_path(catalog.environ, catalog.home, installation)
    return MachineServerConfig(authority, profile, path)
