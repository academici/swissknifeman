"""``runtimes.list_runtimes`` (runtimes §8): registered runtimes and their host installations."""

from __future__ import annotations

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import InternalError, ValidationFailed
from skm.kernel.ids import HostId, ScopeId
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.runtimes.domain.installation import RuntimeInstallation
from skm.modules.runtimes.generated.queries import ListRuntimes
from skm.modules.runtimes.generated.results import ListRuntimesResult
from skm.modules.runtimes.generated.views import (
    RuntimesViewItem,
    RuntimesViewItemInstallationsItem,
)
from skm.modules.runtimes.ports import CapabilityCatalog, HostRuntimeRepository
from skm.modules.workspace import public as workspace

__all__ = ["SPEC", "ListRuntimesResult", "handle"]


def _all_host_ids(uow: UnitOfWork) -> tuple[HostId, ...]:
    try:
        scopes = uow.repo(ScopeRegistry)
    except InternalError:
        return ()
    hosts: list[HostId] = []
    after: ScopeId | None = None
    while True:
        batch = scopes.list_scopes(after=after, limit=500)
        if not batch:
            break
        hosts.extend(HostId(record.id) for record in batch if record.kind is ScopeKind.HOST)
        after = batch[-1].id
    return tuple(hosts)


def handle(query: ListRuntimes, ctx: QueryContext, uow: UnitOfWork) -> ListRuntimesResult:
    cap_catalog = ctx.gateways.get(CapabilityCatalog)
    registered = cap_catalog.registered()

    try:
        raw_allowed = ctx.config.get("runtimes.allowed")
    except ValidationFailed:
        raw_allowed = None
    allowed = (
        frozenset(item for item in raw_allowed if isinstance(item, str))
        if isinstance(raw_allowed, list | tuple)
        else frozenset[str]()
    )

    if query.host_id is not None:
        host_id = HostId(query.host_id)
        workspace.get_host(uow, host_id)
        host_ids: tuple[HostId, ...] = (host_id,)
    else:
        host_ids = _all_host_ids(uow)

    repo = uow.repo(HostRuntimeRepository)
    by_runtime: dict[str, list[RuntimeInstallation]] = {}
    for hid in host_ids:
        for inst in repo.list_for_host(hid):
            by_runtime.setdefault(inst.runtime_id, []).append(inst)

    all_ids = sorted(registered | set(by_runtime))
    items: list[RuntimesViewItem] = []
    for runtime_id in all_ids:
        is_reg = runtime_id in registered
        adapter_version = cap_catalog.static(runtime_id).adapter_version if is_reg else "unknown"
        installs = sorted(by_runtime.get(runtime_id, ()), key=lambda item: str(item.host_id))
        items.append(
            RuntimesViewItem(
                runtime_id=runtime_id,
                registered=is_reg,
                adapter_version=adapter_version,
                installations=tuple(
                    RuntimesViewItemInstallationsItem(
                        host_id=inst.host_id,
                        version=inst.version,
                        auth_state=inst.auth_state.value,
                        detected_at=inst.detected_at,
                    )
                    for inst in installs
                ),
                allowed_in_scope=runtime_id in allowed,
            )
        )
    return ListRuntimesResult(items=tuple(items))


SPEC = QuerySpec(
    name="runtimes.list_runtimes",
    dto=ListRuntimes,
    result=ListRuntimesResult,
    permission="runtime.read",
    scope_of=None,
    handler=handle,
)
