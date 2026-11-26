"""``execution.list_execution_environments`` query handler (execution §8)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.application_bus.registry import QuerySpec
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden
from skm.kernel.ids import HostId, ScopeId
from skm.kernel.json_types import JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.public import effective_permissions
from skm.modules.execution.application.queries import bad_cursor, check_limit, decode_token, encode_token
from skm.modules.execution.generated.queries import ListExecutionEnvironments
from skm.modules.execution.generated.views import ExecutionEnvironmentsView
from skm.modules.execution.ports import ExecutionQueries
from skm.modules.workspace.public import get_host

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def handle(query: ListExecutionEnvironments, ctx: QueryContext, uow: UnitOfWork) -> ExecutionEnvironmentsView:
    host_id = HostId(query.host_id)
    get_host(uow, host_id)
    perms = effective_permissions(uow, ctx.actor, ScopeId(host_id))
    if ctx.actor.kind is PrincipalKind.WORKER:
        if "worker.claim" not in perms:
            raise Forbidden(ErrorCode.FORBIDDEN, "worker lacks worker.claim on host")
    elif not {"run.read", "checkout.read_locator"} <= perms:
        raise Forbidden(ErrorCode.FORBIDDEN, "actor lacks run.read and checkout.read_locator on host")
    limit = check_limit(query.limit, default=50)
    rem_only = bool(query.removable_only)
    sig: dict[str, JsonValue] = {"h": str(host_id), "a": str(ctx.actor.principal_id), "r": rem_only}
    raw_cur: str | None = None
    if query.after is not None:
        tok = decode_token(query.after)
        if {k: tok.get(k) for k in sig} != sig or not isinstance(tok.get("c"), str):
            raise bad_cursor()
        raw_cur = str(tok["c"])
    page = uow.repo(ExecutionQueries).environments_page(host_id, rem_only, raw_cur, limit)
    nxt = page.get("next_after")
    return ExecutionEnvironmentsView.from_json(
        {
            "items": page.get("items", ()),
            "next_after": None if nxt is None else encode_token({**sig, "c": str(nxt)}),
        }
    )


SPEC = QuerySpec(
    name="execution.list_execution_environments",
    dto=ListExecutionEnvironments,
    result=ExecutionEnvironmentsView,
    permission="workspace.read",
    scope_of=lambda q: ScopeRef(ScopeKind.HOST, ScopeId(q.host_id)),
    handler=handle,
)
