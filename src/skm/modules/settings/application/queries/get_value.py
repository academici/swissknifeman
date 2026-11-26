"""``settings.get_value`` (settings §A.8): the effective value of one key in the chain of a scope.

The resolution is independent of the serving process: stored levels, packs and defaults, never the
invocation layer. An invalid effective value fails closed (``CONFIG_INVALID``); a key of the other chain is
``CONFIG_SCOPE_NOT_ALLOWED``. Secret keys show their reference, never a value.
"""

from typing import cast

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.settings.application.preview import Preview, chain_kind
from skm.modules.settings.application.project_keys import require_project_key
from skm.modules.settings.application.scopes import bus_scope_of, resolve_target_scope
from skm.modules.settings.application.write_flow import layer_view, safe_value
from skm.modules.settings.generated.queries import GetValue
from skm.modules.settings.generated.views import GetValueView, GetValueViewDefsLayerRef
from skm.platform.config.store import PackConfigSource

__all__ = ["SPEC", "handle"]


def handle(query: GetValue, ctx: QueryContext, uow: UnitOfWork) -> GetValueView:
    target = resolve_target_scope(uow, query.scope, ctx.scope_chain)
    require_project_key(query.key)
    registry = ctx.config.registry
    spec = registry.spec(query.key)  # CONFIG_UNKNOWN_KEY
    preview = Preview(uow, registry, uow.repo(PackConfigSource), target.ref)
    effective = preview.candidate(chain_kind(target.ref.level, spec), {}, keys=(query.key,))
    present = effective.present(query.key)  # CONFIG_INVALID / CONFIG_SCOPE_NOT_ALLOWED
    resolution = effective.resolution(query.key)
    return GetValueView(
        key=query.key,
        present=present,
        value=safe_value(spec, cast("JsonValue", resolution.value)) if present else None,
        winner=layer_view(GetValueViewDefsLayerRef, resolution.winner),
        locked_by=layer_view(GetValueViewDefsLayerRef, resolution.locked_by),
    )


SPEC = QuerySpec(
    name="settings.get_value",
    dto=GetValue,
    result=GetValueView,
    permission="config.read",
    scope_of=bus_scope_of(lambda query: query.scope),
    handler=handle,
)
