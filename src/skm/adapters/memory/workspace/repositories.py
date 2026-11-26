"""Memory implementations of the workspace ports and of ``access.WorkerHostLookup`` (workspace §6, §11).

Rows are the immutable domain values themselves. The checks PostgreSQL gets from constraints are made here
too: unique workspace and host names, unique project slug per workspace, unique ``(workspace, canonical
remote)`` and remote per workspace, unique mount name per project and one primary mount, one live binding
per ``(host, repository)``, one worker per principal, and optimistic ``row_version`` updates. Composite FKs
and triggers are not imitated (adapters §2.2): their contract cases run on PostgreSQL only.

Cursors are opaque base64 JSON arrays of text: ``[slug, id]`` for workspaces and projects, ``[name, id]``
for hosts, ``[created_at, id]`` for repositories, ``[registered_at, id]`` for workers (keyset, ascending).
"""

import base64
import binascii
import json
from collections.abc import Callable, Sequence
from dataclasses import replace
from datetime import datetime
from typing import cast

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.workspace.state import MemoryWorkspaceState, workspace_state
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import HostId, PrincipalId, ProjectId, RepositoryId, ScopeId, WorkerId, WorkspaceId
from skm.kernel.pagination import Cursor, Page, validate_cursor, validate_page_limit
from skm.modules.workspace.domain import worker as worker_rules
from skm.modules.workspace.domain.attach import RepositoryMatchView
from skm.modules.workspace.domain.checkout_binding import BindingState, CheckoutBinding, CheckoutBindingId
from skm.modules.workspace.domain.host import Host, HostState
from skm.modules.workspace.domain.mount import MountName, MountRole
from skm.modules.workspace.domain.mount import ProjectRepository as ProjectMount
from skm.modules.workspace.domain.project import Project, ProjectState
from skm.modules.workspace.domain.remote_url import NormalizedRemote
from skm.modules.workspace.domain.repository import Repository, RepositoryRemote
from skm.modules.workspace.domain.slug import Slug
from skm.modules.workspace.domain.worker import Worker, WorkerCapabilities, WorkerState
from skm.modules.workspace.domain.workspace import Workspace, WorkspaceState

__all__ = [
    "MemoryCheckoutBindingRepository",
    "MemoryHostRepository",
    "MemoryMountRepository",
    "MemoryProjectRepository",
    "MemoryRepositoryRepository",
    "MemoryWorkerHostLookup",
    "MemoryWorkerRepository",
    "MemoryWorkspaceRepository",
]


def _encode_cursor(parts: Sequence[str]) -> Cursor:
    raw = json.dumps(list(parts), separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return validate_cursor(base64.urlsafe_b64encode(raw).decode("ascii"))


def _decode_cursor(cursor: str | None, size: int) -> tuple[str, ...] | None:
    if cursor is None:
        return None
    try:
        parts = json.loads(base64.urlsafe_b64decode(validate_cursor(cursor).encode("ascii")))
        items = cast("list[object]", parts) if isinstance(parts, list) else []
        if len(items) != size or not all(isinstance(item, str) for item in items):
            raise ValueError("cursor shape")
        return tuple(cast("list[str]", items))
    except (ValueError, TypeError, binascii.Error, UnicodeError):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "invalid page cursor", details={"field": "after"}
        ) from None


def _page[T](rows: list[T], after: str | None, limit: int, key_of: Callable[[T], tuple[str, str]]) -> Page[T]:
    """Keyset page over rows already sorted by ``key_of``."""
    limit = validate_page_limit(limit)
    start = _decode_cursor(after, 2)
    if start is not None:
        rows = [row for row in rows if key_of(row) > start]
    items = rows[:limit]
    following = _encode_cursor(key_of(items[-1])) if len(rows) > limit else None
    return Page(items=tuple(items), next=following)


def _not_found(kind: str, ref: object) -> NotFound:
    return NotFound(ErrorCode.NOT_FOUND, f"{kind} not found", details={"kind": kind, "ref": str(ref)})


def _stamp(moment: datetime) -> str:
    return moment.isoformat()


def _check_version(kind: str, actual: int, expected: int) -> None:
    if actual != expected:
        raise Conflict(
            ErrorCode.VERSION_CONFLICT,
            f"version conflict: expected {expected}, actual {actual}",
            details={"kind": kind, "expected": expected, "actual": actual},
        )


class _Tables:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._tables: MemoryWorkspaceState = workspace_state(state)

    def _writable(self) -> MemoryWorkspaceState:
        self._state.core.require_writable()
        return self._tables


class MemoryWorkspaceRepository(_Tables):
    def get(self, workspace_id: WorkspaceId) -> Workspace:
        found = self._tables.workspaces.get(workspace_id)
        if found is None:
            raise _not_found("workspace", workspace_id)
        return found

    def find_by_slug(self, slug: Slug) -> Workspace | None:
        return next((item for item in self._tables.workspaces.values() if item.slug == slug), None)

    def add(self, workspace: Workspace) -> None:
        tables = self._writable()
        if workspace.id in tables.workspaces or self.find_by_slug(workspace.slug) is not None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "workspace already exists",
                details={"kind": "workspace", "slug": workspace.slug.value},
            )
        tables.workspaces[workspace.id] = workspace

    def save(self, workspace: Workspace, *, expected_version: int) -> None:
        tables = self._writable()
        _check_version("workspace", self.get(workspace.id).row_version, expected_version)
        tables.workspaces[workspace.id] = workspace

    def list(self, *, state: WorkspaceState | None, after: str | None, limit: int) -> Page[Workspace]:
        rows = sorted(
            (item for item in self._tables.workspaces.values() if state is None or item.state is state),
            key=lambda item: (item.slug.value, str(item.id)),
        )
        return _page(rows, after, limit, lambda item: (item.slug.value, str(item.id)))


class MemoryProjectRepository(_Tables):
    def get(self, project_id: ProjectId) -> Project:
        found = self._tables.projects.get(project_id)
        if found is None:
            raise _not_found("project", project_id)
        return found

    def find_by_slug(self, workspace_id: WorkspaceId, slug: Slug) -> Project | None:
        return next(
            (
                item
                for item in self._tables.projects.values()
                if item.workspace_id == workspace_id and item.slug == slug
            ),
            None,
        )

    def add(self, project: Project) -> None:
        tables = self._writable()
        if project.id in tables.projects or self.find_by_slug(project.workspace_id, project.slug) is not None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "project already exists",
                details={"kind": "project", "slug": project.slug.value},
            )
        tables.projects[project.id] = project

    def save(self, project: Project, *, expected_version: int) -> None:
        tables = self._writable()
        _check_version("project", self.get(project.id).row_version, expected_version)
        tables.projects[project.id] = project

    def list(
        self, workspace_id: WorkspaceId, *, state: ProjectState | None, after: str | None, limit: int
    ) -> Page[Project]:
        rows = sorted(
            (
                item
                for item in self._tables.projects.values()
                if item.workspace_id == workspace_id and (state is None or item.state is state)
            ),
            key=lambda item: (item.slug.value, str(item.id)),
        )
        return _page(rows, after, limit, lambda item: (item.slug.value, str(item.id)))

    def count(self, workspace_id: WorkspaceId) -> int:
        return sum(1 for item in self._tables.projects.values() if item.workspace_id == workspace_id)


class MemoryRepositoryRepository(_Tables):
    def get(self, repository_id: RepositoryId) -> Repository:
        found = self._tables.repositories.get(repository_id)
        if found is None:
            raise _not_found("repository", repository_id)
        return found

    def add(self, repository: Repository) -> None:
        tables = self._writable()
        clash = repository.id in tables.repositories or (
            repository.canonical_remote is not None
            and any(
                item.workspace_id == repository.workspace_id
                and item.canonical_remote == repository.canonical_remote
                for item in tables.repositories.values()
            )
        )
        if clash:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "repository already exists",
                details={"kind": "repository", "repository_id": str(repository.id)},
            )
        tables.repositories[repository.id] = repository
        tables.remotes.setdefault(repository.id, ())

    def save(self, repository: Repository, *, expected_version: int) -> None:
        tables = self._writable()
        _check_version("repository", self.get(repository.id).row_version, expected_version)
        tables.repositories[repository.id] = repository

    def remotes(self, repository_id: RepositoryId) -> tuple[RepositoryRemote, ...]:
        self.get(repository_id)
        return self._tables.remotes.get(repository_id, ())

    def replace_remotes(self, repository_id: RepositoryId, remotes: Sequence[RepositoryRemote]) -> None:
        tables = self._writable()
        repository = self.get(repository_id)
        mine = {item.normalized for item in remotes}
        if len(mine) != len(remotes) or sum(1 for item in remotes if item.is_primary) > 1:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID, "duplicate or several primary remotes", details={"field": "remotes"}
            )
        for other_id, others in tables.remotes.items():
            other = tables.repositories[other_id]
            if other_id != repository_id and other.workspace_id == repository.workspace_id:
                for item in others:
                    if item.normalized in mine:
                        raise Conflict(
                            ErrorCode.ALREADY_EXISTS,
                            "the remote belongs to another repository of the workspace",
                            details={"kind": "remote", "repository_id": str(other_id)},
                        )
        tables.remotes[repository_id] = tuple(remotes)

    def match_remotes(
        self, workspace_id: WorkspaceId, remotes: Sequence[NormalizedRemote]
    ) -> tuple[RepositoryMatchView, ...]:
        wanted = set(remotes)
        found: list[RepositoryMatchView] = []
        for repository in self._tables.repositories.values():
            if repository.workspace_id != workspace_id:
                continue
            matched = tuple(
                item.normalized
                for item in self._tables.remotes.get(repository.id, ())
                if item.normalized in wanted
            )
            if matched:
                projects = tuple(
                    sorted(
                        {
                            m.project_id
                            for m in self._tables.mounts.values()
                            if m.repository_id == repository.id
                        },
                        key=str,
                    )
                )
                found.append(RepositoryMatchView(repository.id, repository.title, matched, projects))
        return tuple(sorted(found, key=lambda view: str(view.repository_id)))

    def list(
        self, workspace_id: WorkspaceId, *, id_prefix: str | None, after: str | None, limit: int
    ) -> Page[Repository]:
        rows = sorted(
            (
                item
                for item in self._tables.repositories.values()
                if item.workspace_id == workspace_id
                and (id_prefix is None or item.id.hex.startswith(id_prefix))
            ),
            key=lambda item: (_stamp(item.created_at), str(item.id)),
        )
        return _page(rows, after, limit, lambda item: (_stamp(item.created_at), str(item.id)))


class MemoryMountRepository(_Tables):
    def for_project(self, project_id: ProjectId) -> tuple[ProjectMount, ...]:
        return tuple(
            sorted(
                (item for item in self._tables.mounts.values() if item.project_id == project_id),
                key=lambda item: (item.attached_at, item.mount_name.value),
            )
        )

    def projects_of(self, repository_id: RepositoryId) -> tuple[ProjectId, ...]:
        return tuple(
            sorted(
                {
                    item.project_id
                    for item in self._tables.mounts.values()
                    if item.repository_id == repository_id
                },
                key=str,
            )
        )

    def add(self, mount: ProjectMount) -> None:
        tables = self._writable()
        taken = (mount.project_id, mount.mount_name.value) in tables.mounts
        second_primary = mount.role is MountRole.PRIMARY and any(
            item.project_id == mount.project_id and item.role is MountRole.PRIMARY
            for item in tables.mounts.values()
        )
        if taken or second_primary:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "the mount name or the primary mount is already used in the project",
                details={"kind": "mount", "mount_name": mount.mount_name.value},
            )
        tables.mounts[(mount.project_id, mount.mount_name.value)] = mount

    def remove(self, project_id: ProjectId, mount_name: MountName) -> ProjectMount | None:
        return self._writable().mounts.pop((project_id, mount_name.value), None)


class MemoryHostRepository(_Tables):
    def get(self, host_id: HostId) -> Host:
        found = self._tables.hosts.get(host_id)
        if found is None:
            raise _not_found("host", host_id)
        return found

    def find_by_name(self, name: str) -> Host | None:
        return next((item for item in self._tables.hosts.values() if item.name == name), None)

    def add(self, host: Host) -> None:
        tables = self._writable()
        if host.id in tables.hosts or self.find_by_name(host.name) is not None:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS, "host already exists", details={"kind": "host", "name": host.name}
            )
        tables.hosts[host.id] = host

    def save(self, host: Host, *, expected_version: int) -> None:
        tables = self._writable()
        _check_version("host", self.get(host.id).row_version, expected_version)
        tables.hosts[host.id] = host

    def touch(self, host_id: HostId, at: datetime) -> None:
        """Liveness only: ``last_seen_at`` moves forward, ``row_version`` stays."""
        tables = self._writable()
        host = self.get(host_id)
        if host.last_seen_at is None or at > host.last_seen_at:
            tables.hosts[host_id] = replace(host, last_seen_at=at)

    def list(self, *, state: HostState | None, after: str | None, limit: int) -> Page[Host]:
        rows = sorted(
            (item for item in self._tables.hosts.values() if state is None or item.state is state),
            key=lambda item: (item.name, str(item.id)),
        )
        return _page(rows, after, limit, lambda item: (item.name, str(item.id)))


class MemoryCheckoutBindingRepository(_Tables):
    def get(self, binding_id: CheckoutBindingId) -> CheckoutBinding:
        found = self._tables.bindings.get(binding_id)
        if found is None:
            raise _not_found("binding", binding_id)
        return found

    def find(self, host_id: HostId, repository_id: RepositoryId) -> CheckoutBinding | None:
        return next(
            (
                item
                for item in self._tables.bindings.values()
                if item.host_id == host_id
                and item.repository_id == repository_id
                and item.state is not BindingState.REMOVED
            ),
            None,
        )

    def add(self, binding: CheckoutBinding) -> None:
        tables = self._writable()
        live = self.find(binding.host_id, binding.repository_id)
        if binding.id in tables.bindings or (live is not None and binding.state is not BindingState.REMOVED):
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "the repository is already bound on this host",
                details={"kind": "binding", "binding_id": str(binding.id if live is None else live.id)},
            )
        tables.bindings[binding.id] = binding

    def save(self, binding: CheckoutBinding, *, expected_version: int) -> None:
        tables = self._writable()
        _check_version("binding", self.get(binding.id).row_version, expected_version)
        tables.bindings[binding.id] = binding


class MemoryWorkerRepository(_Tables):
    def get(self, worker_id: WorkerId) -> Worker:
        found = self._tables.workers.get(worker_id)
        if found is None:
            raise _not_found("worker", worker_id)
        return found

    def add(self, worker: Worker) -> None:
        tables = self._writable()
        if worker.id in tables.workers or self.for_principal(worker.principal_id) is not None:
            raise Conflict(ErrorCode.ALREADY_EXISTS, "worker already exists", details={"kind": "worker"})
        tables.workers[worker.id] = worker

    def save(self, worker: Worker, *, expected_version: int) -> None:
        tables = self._writable()
        _check_version("worker", self.get(worker.id).row_version, expected_version)
        tables.workers[worker.id] = worker

    def heartbeat(self, worker_id: WorkerId, at: datetime, capabilities: WorkerCapabilities | None) -> Worker:
        """Last writer wins: no version check; a retired worker is refused by the domain rule."""
        tables = self._writable()
        beaten = worker_rules.heartbeat(self.get(worker_id), capabilities, at)
        tables.workers[worker_id] = beaten
        return beaten

    def list(
        self, workspace_id: WorkspaceId, *, state: WorkerState | None, after: str | None, limit: int
    ) -> Page[Worker]:
        rows = sorted(
            (
                item
                for item in self._tables.workers.values()
                if item.workspace_id == workspace_id and (state is None or item.state is state)
            ),
            key=lambda item: (_stamp(item.registered_at), str(item.id)),
        )
        return _page(rows, after, limit, lambda item: (_stamp(item.registered_at), str(item.id)))

    def for_principal(self, principal_id: PrincipalId) -> Worker | None:
        return next(
            (item for item in self._tables.workers.values() if item.principal_id == principal_id), None
        )

    def online(self, workspace_ids: Sequence[WorkspaceId]) -> tuple[Worker, ...]:
        wanted = set(workspace_ids)
        return tuple(
            sorted(
                (
                    item
                    for item in self._tables.workers.values()
                    if item.workspace_id in wanted and item.state is WorkerState.ONLINE
                ),
                key=lambda item: (str(item.host_id), str(item.id)),
            )
        )

    def overdue(self, cutoff: datetime) -> tuple[Worker, ...]:
        """Live workers (online or draining) whose last heartbeat, or registration, is before ``cutoff``."""
        return tuple(
            sorted(
                (
                    item
                    for item in self._tables.workers.values()
                    if item.state in (WorkerState.ONLINE, WorkerState.DRAINING)
                    and (item.last_heartbeat_at or item.registered_at) < cutoff
                ),
                key=lambda item: str(item.id),
            )
        )

    def mark_offline_older_than(self, cutoff: datetime) -> tuple[WorkerId, ...]:
        tables = self._writable()
        stale = self.overdue(cutoff)
        for item in stale:
            tables.workers[item.id] = worker_rules.mark_offline(item)
        return tuple(item.id for item in stale)


class MemoryWorkerHostLookup(_Tables):
    """Host and workspace scopes of non-retired workers (access §4.4, §6)."""

    def host_ids(self, principal_id: PrincipalId) -> frozenset[ScopeId]:
        return frozenset(
            ScopeId(item.host_id)
            for item in self._tables.workers.values()
            if item.principal_id == principal_id and item.state is not WorkerState.RETIRED
        )

    def workspace_scope_id(self, principal_id: PrincipalId) -> ScopeId | None:
        return next(
            (
                ScopeId(worker.workspace_id)
                for worker in self._tables.workers.values()
                if worker.principal_id == principal_id and worker.state is not WorkerState.RETIRED
            ),
            None,
        )
