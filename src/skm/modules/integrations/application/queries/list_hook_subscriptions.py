"""Handler for ``integrations.list_hook_subscriptions`` (integrations §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING, cast
from urllib.parse import urlsplit

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.integrations.application.subscribers import (
    default_hookable_event_types,
    read_hook_subscriptions,
    registered_sink_ids,
)
from skm.modules.integrations.domain.hook_subscriptions import (
    CommandTarget,
    HookSubscription,
    Violation,
    WebhookTarget,
)
from skm.modules.integrations.generated.queries import ListHookSubscriptions
from skm.modules.integrations.generated.results import ListHookSubscriptionsResult
from skm.modules.integrations.generated.views import (
    HookSubscriptionView,
    HookSubscriptionViewDefsJsonValue,
)
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def _scope_of(query: ListHookSubscriptions) -> ScopeRef:
    if query.project_id is not None:
        return ScopeRef(ScopeKind.PROJECT, ScopeId(query.project_id))
    return ScopeRef(ScopeKind.WORKSPACE, ScopeId(query.workspace_id))


def _target_summary(sub: HookSubscription) -> str:
    """Safe summary (host URL | argv[0] | sink_id); never exposes userinfo, query or secret values."""
    target = sub.target
    if isinstance(target, WebhookTarget):
        try:
            parsed = urlsplit(target.url)
            host = parsed.hostname or ""
            port = parsed.port
        except ValueError:
            return "webhook"
        if not host:
            return "webhook"
        authority = f"[{host}]" if ":" in host else host
        if port is not None:
            authority = f"{authority}:{port}"
        scheme = parsed.scheme or "https"
        return f"{scheme}://{authority}"
    if isinstance(target, CommandTarget):
        return target.argv[0] if target.argv else "<command>"
    return target.sink_id or "<sink>"


def _violation_item(violation: Violation) -> Mapping[str, HookSubscriptionViewDefsJsonValue]:
    return cast(
        "Mapping[str, HookSubscriptionViewDefsJsonValue]",
        {
            "key": violation.key,
            "reason": violation.reason,
            "message": violation.message,
        },
    )


def handle(
    query: ListHookSubscriptions,
    ctx: QueryContext,
    uow: UnitOfWork,
) -> ListHookSubscriptionsResult:
    workspace_id = WorkspaceId(query.workspace_id)
    workspace.require_active_workspace(uow, workspace_id)
    if query.project_id is not None:
        project_id = ProjectId(query.project_id)
        if workspace.workspace_of_project(uow, project_id) != workspace_id:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "project not found in workspace",
                details={"kind": "project", "ref": str(project_id)},
            )
        workspace.require_active_project(uow, project_id)

    entries, parse_violations = read_hook_subscriptions(
        ctx.config,
        hookable_types=default_hookable_event_types(),
        sink_ids=registered_sink_ids(ctx.config),
    )
    for violation in (*parse_violations, *(v for _, problems in entries for v in problems)):
        ctx.log.warning(
            "integrations.hook_subscription_invalid",
            code="HOOK_SUBSCRIPTION_INVALID",
            key=violation.key,
            reason=violation.reason,
        )
    items = tuple(
        HookSubscriptionView(
            id=sub.id,
            class_=sub.hook_class.value,
            kind=sub.kind.value,
            execution_location=sub.execution_location.value,
            event_types=sub.event_types,
            target_summary=_target_summary(sub),
            enabled=sub.enabled,
            valid=not violations,
            violations=tuple(_violation_item(v) for v in violations),
            defined_at=sub.defined_at,
            digest=sub.digest,
        )
        for sub, violations in entries
    )
    return ListHookSubscriptionsResult(items=items)


SPEC = QuerySpec(
    name="integrations.list_hook_subscriptions",
    dto=ListHookSubscriptions,
    result=ListHookSubscriptionsResult,
    permission="integration.read",
    scope_of=_scope_of,
    handler=handle,
)
