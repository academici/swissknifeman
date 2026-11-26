"""Stored host configuration and instance plugin selection for a registered worker."""

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry, scope_not_found
from skm.modules.settings.application.preview import Preview
from skm.modules.settings.application.write_flow import safe_value
from skm.modules.settings.domain.worker_config import PROJECT_WORKER_HOST_KEYS, PROJECT_WORKER_WORK_KEYS
from skm.modules.settings.generated.queries import GetHostConfig
from skm.modules.settings.generated.results import GetHostConfigResult, GetHostConfigResultPlugins
from skm.platform.config.keys import Chain, Level
from skm.platform.config.scopes import ScopeRef as ConfigScopeRef
from skm.platform.config.store import PackConfigSource, ScopeTree
from skm.platform.jsonc.digest import digest

__all__ = ["SPEC", "handle"]


def handle(query: GetHostConfig, ctx: QueryContext, uow: UnitOfWork) -> GetHostConfigResult:
    host = uow.repo(ScopeRegistry).get(ScopeId(query.host_id))
    if host.kind is not ScopeKind.HOST:
        raise scope_not_found()

    registry = ctx.config.registry
    scopes = uow.repo(ScopeTree)
    packs = uow.repo(PackConfigSource)
    host_ref = ConfigScopeRef(Level.HOST, host.id)
    effective = Preview(uow, registry, packs, host_ref).current(Chain.HOST)
    work = Preview(uow, registry, packs, scopes.instance_scope()).current(
        Chain.WORK, (*sorted(PROJECT_WORKER_WORK_KEYS), "plugins.allowed", "plugins.required")
    )
    invalid = (effective.invalid_keys().keys() & PROJECT_WORKER_HOST_KEYS) | (
        work.invalid_keys().keys() & PROJECT_WORKER_WORK_KEYS
    )
    values: JsonObject = {
        key: safe_value(registry.spec(key), config.get(key))
        for config, keys in ((effective, PROJECT_WORKER_HOST_KEYS), (work, PROJECT_WORKER_WORK_KEYS))
        for key in sorted((keys & frozenset(config.resolved_keys())) - invalid)
        if config.present(key)
    }
    return GetHostConfigResult(
        host_id=query.host_id,
        generation=effective.generation,
        pack_generation=effective.pack_generation,
        digest=digest(values),
        values=values,
        invalid=tuple(sorted(invalid)),
        plugins=GetHostConfigResultPlugins.from_json(
            {"allowed": work.get("plugins.allowed"), "required": work.get("plugins.required")}
        ),
    )


SPEC = QuerySpec(
    name="settings.get_host_config",
    dto=GetHostConfig,
    result=GetHostConfigResult,
    permission="config.read",
    scope_of=lambda q: ScopeRef(ScopeKind.HOST, ScopeId(q.host_id)),
    internal=False,
    allowed_kinds=frozenset({PrincipalKind.WORKER}),
    handler=handle,
)
