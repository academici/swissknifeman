"""Checks shared by the workspace handlers and the facade (workspace §5.3, §5.4, §13).

``require_active_*`` are the admission points of §5.4: they read the *current* stored states of the project
and of its workspace, so a closed area refuses a new plan, attach or bind even when the archive event has not
been delivered yet. Cleanup and recording handlers do not call them.

``require`` and ``holds`` decide a permission on a scope inside the caller's unit of work for operations whose
DTO names an entity that is not a scope (a repository, a binding, a worker): the bus authorises the self
right,
the handler loads the entity and decides the real permission on its workspace with the same
``RbacAuthorizer`` decision (reason code included) the bus would have used.
"""

from collections.abc import Sequence
from uuid import UUID

from skm.application_bus.context import CommandContext, QueryContext
from skm.kernel.actor import Actor
from skm.kernel.clock import Clock
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRecord, ScopeRef, ScopeRegistry
from skm.modules.access.public import RbacAuthorizer
from skm.modules.workspace.domain import project as project_rules
from skm.modules.workspace.domain import workspace as workspace_rules
from skm.modules.workspace.domain.project import Project
from skm.modules.workspace.domain.workspace import Workspace
from skm.modules.workspace.generated.settings import WorkspaceSettings
from skm.modules.workspace.ports import ProjectRepository, WorkspaceRepository

__all__ = [
    "SELF_PERMISSION",
    "allow_unconfined",
    "chain_of",
    "holds",
    "require",
    "require_active_project",
    "require_active_workspace",
    "scope_ref",
    "stale_after_days",
]

SELF_PERMISSION = (
    "token.own"  # bus right of operations that authorise on a loaded entity (access §4.4 row 5c)
)
_UNCONFINED_KEY = "policy.host.allow_unconfined"
_CONFIG_NOT_VISIBLE = frozenset({ErrorCode.CONFIG_SCOPE_NOT_ALLOWED, ErrorCode.CONFIG_UNKNOWN_KEY})


def chain_of(uow: UnitOfWork, scope_id: ScopeId | WorkspaceId | ProjectId) -> tuple[ScopeRecord, ...]:
    return uow.repo(ScopeRegistry).ancestors(ScopeId(scope_id))


def _decision(
    uow: UnitOfWork, clock: Clock, actor: Actor, permission: str, chain: Sequence[ScopeRecord]
) -> tuple[bool, str | None]:
    verdict = RbacAuthorizer(clock).authorize(uow, actor, permission, tuple(chain))
    return verdict.allowed, verdict.reason_code


def holds(
    uow: UnitOfWork, clock: Clock, actor: Actor, permission: str, scope_id: ScopeId | WorkspaceId | ProjectId
) -> bool:
    return _decision(uow, clock, actor, permission, chain_of(uow, scope_id))[0]


def require(
    uow: UnitOfWork, clock: Clock, actor: Actor, permission: str, scope_id: ScopeId | WorkspaceId | ProjectId
) -> None:
    """``FORBIDDEN`` unless ``actor`` holds ``permission`` on ``scope_id`` now."""
    allowed, reason = _decision(uow, clock, actor, permission, chain_of(uow, scope_id))
    if not allowed:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            f"{permission} is not granted here",
            details={"permission": permission, "scope_id": str(scope_id), "reason_code": reason or ""},
        )


def require_active_workspace(uow: UnitOfWork, workspace_id: WorkspaceId) -> Workspace:
    workspace = uow.repo(WorkspaceRepository).get(workspace_id)
    workspace_rules.require_active(workspace)
    return workspace


def require_active_project(uow: UnitOfWork, project_id: ProjectId) -> Project:
    """The project is active **and** so is its workspace (``PROJECT_ARCHIVED``, ``details.kind``)."""
    project = uow.repo(ProjectRepository).get(project_id)
    project_rules.require_active(project)
    workspace_rules.require_active(uow.repo(WorkspaceRepository).get(project.workspace_id))
    return project


def stale_after_days(ctx: CommandContext | QueryContext) -> int:
    return ctx.config.section(WorkspaceSettings).checkout.stale_after_days


def allow_unconfined(ctx: CommandContext) -> bool:
    """``policy.host.allow_unconfined`` is a host-chain key: a workspace-scoped command cannot see it.

    Not visible means not allowed (fail closed): ``none`` is declared only where the key resolves to true.
    """
    try:
        return ctx.config.get(_UNCONFINED_KEY) is True
    except ValidationFailed as error:
        if error.code in _CONFIG_NOT_VISIBLE:
            return False
        raise


def scope_ref(kind: ScopeKind, scope_id: UUID | None) -> ScopeRef | None:
    """Bus scope of an optional entity id; ``None`` is the instance scope (the resolver reads ids only)."""
    return None if scope_id is None else ScopeRef(kind, ScopeId(scope_id))
