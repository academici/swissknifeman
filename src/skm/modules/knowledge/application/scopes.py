"""Resolve the caller's project and keep memory writes within its authorized scopes."""

from uuid import UUID

from skm.application_bus.context import CommandContext
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import ProjectId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.public import RbacAuthorizer
from skm.modules.knowledge.domain.memory_scope import MemoryScope, MemoryScopeKind
from skm.modules.workspace.public import require_active_project, workspace_of_project


def project_ref(project_id: str | None) -> ScopeRef | None:
    return None if project_id is None else ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(project_id)))


def workspace_ref(workspace_id: str) -> ScopeRef:
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(UUID(workspace_id)))


def project_memory_scope(uow: UnitOfWork, project_id: str | None) -> MemoryScope:
    if project_id is None:
        raise PreconditionFailed(ErrorCode.MEMORY_SCOPE_REQUIRED, "Memory requires a project scope")
    project = ProjectId(UUID(project_id))
    require_active_project(uow, project)
    return MemoryScope(MemoryScopeKind.PROJECT, ScopeId(project), None, workspace_of_project(uow, project))


def requested_scope(
    kind: str,
    namespace: str | None,
    project: MemoryScope | None,
) -> MemoryScope:
    scope_kind = MemoryScopeKind(kind)
    if namespace is not None and scope_kind is not MemoryScopeKind.NAMESPACE:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Namespace requires a namespace scope")
    if scope_kind is MemoryScopeKind.GLOBAL:
        return MemoryScope(scope_kind, None, None, None)
    if project is None:
        raise PreconditionFailed(ErrorCode.MEMORY_SCOPE_REQUIRED, "Memory requires a project scope")
    if scope_kind is MemoryScopeKind.PROJECT:
        return project
    return MemoryScope(scope_kind, None, namespace, project.workspace_id)


def require_instance_write(
    scope: MemoryScope, project: MemoryScope | None, ctx: CommandContext, uow: UnitOfWork
) -> None:
    if project is not None and scope.kind is MemoryScopeKind.GLOBAL:
        verdict = RbacAuthorizer(ctx.clock).authorize(uow, ctx.actor, "memory.write", ctx.scope_chain[:1])
        if not verdict.allowed:
            raise Forbidden(ErrorCode.FORBIDDEN, "Global memory requires instance memory.write")
