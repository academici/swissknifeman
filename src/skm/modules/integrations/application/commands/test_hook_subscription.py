"""Handler for ``integrations.test_hook_subscription`` (integrations §7.7)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import CommandSpec, IdempotencyMode
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.integrations.application.subscribers import (
    default_hookable_event_types,
    read_hook_subscriptions,
    registered_sink_ids,
)
from skm.modules.integrations.domain.events import HookTestRequested
from skm.modules.integrations.domain.hook_subscriptions import ExecutionLocation
from skm.modules.integrations.generated.commands import TestHookSubscription
from skm.modules.integrations.generated.results import TestHookSubscriptionResult
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import CommandContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def _scope_of(cmd: TestHookSubscription) -> ScopeRef:
    if cmd.project_id is not None:
        return ScopeRef(ScopeKind.PROJECT, ScopeId(cmd.project_id))
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(cmd.workspace_id))


def handle(
    cmd: TestHookSubscription,
    ctx: CommandContext,
    uow: UnitOfWork,
) -> TestHookSubscriptionResult:
    workspace_id = WorkspaceId(cmd.workspace_id)
    workspace.require_active_workspace(uow, workspace_id)
    if cmd.project_id is not None:
        project_id = ProjectId(cmd.project_id)
        if workspace.workspace_of_project(uow, project_id) != workspace_id:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "project not found in workspace",
                details={"kind": "project", "ref": str(project_id)},
            )
        workspace.require_active_project(uow, project_id)

    entries, _ = read_hook_subscriptions(
        ctx.config,
        hookable_types=default_hookable_event_types(),
        sink_ids=registered_sink_ids(ctx.config),
    )
    found = next(((sub, violations) for sub, violations in entries if sub.id == cmd.subscription_id), None)
    if found is None:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            f"hook subscription {cmd.subscription_id!r} not found",
            details={"kind": "hook_subscription", "ref": cmd.subscription_id},
        )
    sub, violations = found
    if sub.execution_location is ExecutionLocation.HOST:
        raise PreconditionFailed(
            ErrorCode.HOOK_SUBSCRIPTION_LOCATION,
            f"hook subscription {cmd.subscription_id!r} runs on host; use test_host_subscription",
            details={"subscription_id": cmd.subscription_id, "execution_location": "host"},
        )
    if violations:
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            f"hook subscription {cmd.subscription_id!r} is invalid",
            details={
                "subscription_id": cmd.subscription_id,
                "violations": [{"key": v.key, "reason": v.reason, "message": v.message} for v in violations],
            },
        )

    test_id = ctx.ids.new_id()
    uow.record(
        HookTestRequested(
            test_id=test_id,
            workspace_id=workspace_id,
            subscription_id=cmd.subscription_id,
            requested_by=ctx.actor.principal_id,
            project_id=None if cmd.project_id is None else ProjectId(cmd.project_id),
        )
    )
    return TestHookSubscriptionResult(test_id=test_id)


SPEC = CommandSpec(
    name="integrations.test_hook_subscription",
    dto=TestHookSubscription,
    result=TestHookSubscriptionResult,
    permission="hook.manage",
    scope_of=_scope_of,
    handler=handle,
    idempotency=IdempotencyMode.OPTIONAL,
)
