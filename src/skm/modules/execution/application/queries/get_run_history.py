"""``execution.get_run_history`` query handler (execution §8.1)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import RunId, ScopeId, TaskId
from skm.kernel.json_types import JsonObject
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.public import effective_permissions
from skm.modules.execution.application.queries import (
    RunHistoryResult,
    bad_cursor,
    check_limit,
    decode_token,
    encode_token,
)
from skm.modules.execution.domain.history import BUILDER_VERSION, MAX_PAGE_EVENTS, build_history
from skm.modules.execution.generated.queries import GetRunHistory
from skm.modules.execution.ports import ExecutionQueries, RunRepository, TaskRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def _resolve_foreign_tasks(
    uow: UnitOfWork, ctx: QueryContext, run_id: RunId, events_slice: Sequence[JsonObject]
) -> tuple[frozenset[tuple[str, str]], frozenset[tuple[str, str]]]:
    task_repo = uow.repo(TaskRepository)
    auth_foreign: set[tuple[str, str]] = set()
    exp_foreign: set[tuple[str, str]] = set()

    def _inspect_task(raw_tid: object) -> None:
        if not isinstance(raw_tid, str):
            return
        try:
            uid = UUID(raw_tid)
            ftask = task_repo.get(TaskId(uid))
        except (ValueError, NotFound):
            return
        norm = str(uid)
        if ftask.run_id != run_id:
            exp_foreign.add(("task", norm))
            if "run.read" in effective_permissions(uow, ctx.actor, ScopeId(ftask.run_id)):
                auth_foreign.add(("task", norm))

    for ev in events_slice:
        pl = ev.get("payload")
        if not isinstance(pl, dict):
            continue
        if pl.get("carried_forward"):
            _inspect_task(pl.get("source_task_id"))
            if isinstance(cl := pl.get("clearance"), dict):
                _inspect_task(cl.get("source_task_id"))
        if isinstance(orig := pl.get("origin"), dict) and "source_task_id" in orig:
            _inspect_task(orig.get("source_task_id"))
        cause = pl.get("cause")
        if isinstance(cause, dict) and isinstance(refs := cause.get("refs"), list):
            for ref in refs:
                if isinstance(ref, dict) and ref.get("kind") == "task":
                    _inspect_task(ref.get("id"))
    return frozenset(auth_foreign), frozenset(exp_foreign)


def handle(query: GetRunHistory, ctx: QueryContext, uow: UnitOfWork) -> RunHistoryResult:
    run_id = RunId(query.run_id)
    uow.repo(RunRepository).get(run_id)
    limit = check_limit(query.limit, default=100, maximum=MAX_PAGE_EVENTS)
    queries = uow.repo(ExecutionQueries)
    head_seq = queries.head_run_seq(run_id)

    if query.after is None:
        if query.through_seq is not None:
            if isinstance(query.through_seq, bool) or query.through_seq < 0 or query.through_seq > head_seq:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID,
                    "through_seq out of range",
                    details={"through_seq": query.through_seq, "head_seq": head_seq},
                )
            through = query.through_seq
        else:
            through = head_seq
        after_seq = 0
    else:
        tok = decode_token(query.after)
        t_val, s_val, v_val = tok.get("t"), tok.get("s"), tok.get("v")
        if (
            v_val != BUILDER_VERSION
            or tok.get("r") != str(run_id)
            or tok.get("a") != str(ctx.actor.principal_id)
            or tok.get("sc") != str(ctx.scope.id)
            or not isinstance(t_val, int)
            or isinstance(t_val, bool)
            or not isinstance(s_val, int)
            or isinstance(s_val, bool)
            or not (0 <= s_val <= t_val <= head_seq)
            or (query.through_seq is not None and query.through_seq != t_val)
        ):
            raise bad_cursor("history cursor is incompatible with request or actor")
        through, after_seq = t_val, s_val

    events_slice = queries.run_events(run_id, after_seq, through, limit)
    auth_foreign, exp_foreign = _resolve_foreign_tasks(uow, ctx, run_id, events_slice)

    def cursor(scanned: int) -> str:
        return encode_token(
            {
                "v": BUILDER_VERSION,
                "r": str(run_id),
                "t": through,
                "s": scanned,
                "a": str(ctx.actor.principal_id),
                "sc": str(ctx.scope.id),
            }
        )

    raw_page = build_history(
        events_slice,
        through,
        run_id=str(run_id),
        after_seq=after_seq,
        limit=limit,
        authorized_foreign_ids=auth_foreign,
        explicit_foreign_ids=exp_foreign,
        encode_cursor=cursor,
    )
    return RunHistoryResult.from_json(raw_page)


SPEC = QuerySpec(
    name="execution.get_run_history",
    dto=GetRunHistory,
    result=RunHistoryResult,
    permission="run.read",
    scope_of=lambda q: ScopeRef(ScopeKind.RUN, ScopeId(q.run_id)),
    handler=handle,
)
