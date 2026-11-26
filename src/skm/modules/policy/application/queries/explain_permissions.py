"""``policy.explain_permissions`` (policy §8): which layer narrowed which field of the effective permissions.

The composition of §5.1 replayed layer by layer: the profile gives the start, then the ceiling, every
restriction, the role layer and the task layer in order. A layer is listed for a field when applying it
changed the value of that field, so a layer that narrows nothing is absent. The result is read-only
information; it grants nothing.
"""

from __future__ import annotations

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.isolation import IsolationProfile
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.policy.application.commands import allow_unconfined, layer_of
from skm.modules.policy.application.composition import ceiling_layer, resolve_profile, restriction_layers
from skm.modules.policy.domain.permission_set import PermissionLayer, PermissionSet, narrow
from skm.modules.policy.domain.render import view_document
from skm.modules.policy.generated.queries import ExplainPermissions
from skm.modules.policy.generated.results import ExplainPermissionsResult, ExplainPermissionsResultItemsItem

__all__ = ["FIELDS", "SPEC", "handle"]

FIELDS = (
    "fs_read",
    "fs_write",
    "commands",
    "network",
    "tools",
    "operations",
    "external_effects",
    "effects_need_approval",
    "allowed_isolation",
)


def _start(ctx: QueryContext, query: ExplainPermissions) -> tuple[PermissionSet, str]:
    key = "policy.interactive.profile" if query.interactive else "policy.default_profile"
    chosen = query.profile_id or ctx.config.get(key)
    if not isinstance(chosen, str):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "no policy profile is configured",
            details={"profile_id": None, "reason": "unknown_profile"},
        )
    profile = resolve_profile(ctx.config, chosen)
    unconfined = allow_unconfined(ctx.config)
    if profile.requires_host_flag and not unconfined:
        raise Forbidden(
            ErrorCode.FORBIDDEN,
            f"profile {profile.id} needs policy.host.allow_unconfined on this host",
            details={"reason": "unconfined_not_allowed_on_host", "profile_id": profile.id},
        )
    base = profile.permissions
    if not unconfined:
        base = PermissionSet(
            fs_read=base.fs_read,
            fs_write=base.fs_write,
            commands=base.commands,
            network=base.network,
            tools=base.tools,
            operations=base.operations,
            external_effects=base.external_effects,
            effects_need_approval=base.effects_need_approval,
            allowed_isolation=base.allowed_isolation - {IsolationProfile.NONE.value},
            sources=base.sources,
        )
    return base, base.sources[0] if base.sources else f"profile:{profile.id}"


def handle(query: ExplainPermissions, ctx: QueryContext, uow: UnitOfWork) -> ExplainPermissionsResult:
    del uow  # the replay reads no repository
    current, origin = _start(ctx, query)
    layers: tuple[PermissionLayer | None, ...] = (
        ceiling_layer(ctx.config),
        *restriction_layers(ctx.config),
        layer_of(query.role_layer, "role"),
        layer_of(query.task_layer, "task"),
    )
    contributors: dict[str, list[str]] = {name: [origin] for name in FIELDS}
    before = view_document(current)
    for layer in layers:
        if layer is None:
            continue
        current = narrow(current, layer)
        after = view_document(current)
        for name in FIELDS:
            if after[name] != before[name]:
                contributors[name].append(layer.source)
        before = after
    return ExplainPermissionsResult(
        items=tuple(
            ExplainPermissionsResultItemsItem(
                field=name, value=before[name], contributed_by=tuple(contributors[name])
            )
            for name in FIELDS
        )
    )


SPEC = QuerySpec(
    name="policy.explain_permissions",
    dto=ExplainPermissions,
    result=ExplainPermissionsResult,
    permission="policy.read",
    scope_of=lambda query: ScopeRef(ScopeKind.RUN, ScopeId(query.scope_id)),
    handler=handle,
)
