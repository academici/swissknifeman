"""Project-authorized hook policy snapshot (integrations §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ProjectId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.integrations.application.projection_views import applied_preset_subscriptions
from skm.modules.integrations.application.subscribers import (
    default_hookable_event_types,
    read_hook_subscriptions,
    registered_sink_ids,
)
from skm.modules.integrations.domain.hook_subscriptions import (
    CommandTarget,
    ExecutionLocation,
    subscription_json,
)
from skm.modules.integrations.domain.target import TargetId
from skm.modules.integrations.generated.queries import get_hook_policy_from_json
from skm.modules.integrations.generated.settings import IntegrationsSettings
from skm.modules.integrations.generated.views import hook_policy_view_from_json
from skm.modules.integrations.ports import ProjectionRepository
from skm.modules.policy.public import effective_permissions, permission_set_to_view
from skm.modules.workspace import public as workspace

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "GetHookPolicy", "HookPolicyView", "handle"]


class GetHookPolicy(dict[str, Any]):
    """Bus identity for the generated JSON-mode request codec."""

    SCHEMA_URN = "urn:skm:integrations:query:get-hook-policy:v1"

    @classmethod
    def from_json(cls, data: Any) -> GetHookPolicy:
        return cls(get_hook_policy_from_json(data))

    def to_json(self) -> dict[str, Any]:
        return dict(self)


class HookPolicyView(dict[str, Any]):
    SCHEMA_URN = "urn:skm:integrations:view:hook-policy:v1"

    @classmethod
    def from_json(cls, data: Any) -> HookPolicyView:
        return cls(hook_policy_view_from_json(data))

    def to_json(self) -> dict[str, Any]:
        return dict(self)


def scope_of(query: GetHookPolicy) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(query["project_id"])))


def handle(query: GetHookPolicy, ctx: QueryContext, uow: UnitOfWork) -> HookPolicyView:
    project = ProjectId(UUID(query["project_id"]))
    workspace.require_active_project(uow, project)
    settings = ctx.config.section(IntegrationsSettings)
    perms = effective_permissions(
        uow,
        scope_chain=workspace.scope_chain(uow, ScopeId(project)),
        config=ctx.config,
        profile_id="read-only" if settings.permission_profile.value == "observe" else "workspace-contained",
        role_layer=None,
        task_layer=None,
        allow_unconfined=False,
    )
    repo = uow.repo(ProjectionRepository)
    target = TargetId(query["target"])
    builtins, version = applied_preset_subscriptions(repo, project, target)
    entries, _ = read_hook_subscriptions(
        ctx.config, hookable_types=default_hookable_event_types(), sink_ids=registered_sink_ids(ctx.config)
    )
    subscriptions: list[dict[str, Any]] = []
    builtin_ids = {sub.id for sub in builtins}
    configured = (sub for sub, violations in entries if not violations and sub.id not in builtin_ids)
    for sub in (*builtins, *configured):
        if not sub.enabled or sub.execution_location is not ExecutionLocation.HOST:
            continue
        if isinstance(sub.target, CommandTarget):
            normalized = subscription_json(sub)
            subscriptions.append(
                {
                    "id": sub.id,
                    "digest": sub.digest,
                    **cast("dict[str, Any]", normalized["target"]),
                    **{
                        key: normalized[key]
                        for key in ("class", "event_types", "timeout_ms", "retry", "failure_policy")
                    },
                }
            )
    # Pair both independent counters: neither can hide a change in the other.
    generation = ctx.config.generation
    paired = (generation + version) * (generation + version + 1) // 2 + version
    suffixes = cast("list[str]", ctx.config.get("planning.validation.code_suffixes"))
    return HookPolicyView.from_json(
        {
            "hook_modes": {key: value.value for key, value in settings.hooks.mode.items()},
            "permissions": permission_set_to_view(perms),
            "reserved_paths": [".skm/**"],
            "managed_file_paths": sorted(repo.managed_file_paths(project, target)),
            "changelog": {
                "code_globs": ["src/**", "web/**", *(f"*{suffix}" for suffix in suffixes)],
                "changelog_path": settings.hooks.changelog_files[0]
                if settings.hooks.changelog_files
                else "CHANGELOG.md",
                "skip_marker": "[changelog-skip]",
                "changelog_paths": list(settings.hooks.changelog_files),
            },
            "subscriptions": subscriptions,
            "generation": paired,
            "ttl_seconds": 30,
        }
    )


SPEC = QuerySpec(
    name="integrations.get_hook_policy",
    dto=GetHookPolicy,
    result=HookPolicyView,
    permission="integration.read",
    scope_of=scope_of,
    handler=handle,
)
