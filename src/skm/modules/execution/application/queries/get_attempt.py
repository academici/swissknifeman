"""``execution.get_attempt`` query handler (execution §8)."""

from __future__ import annotations

from copy import deepcopy
from typing import TYPE_CHECKING
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.errors import NotFound
from skm.kernel.ids import AttemptId, ScopeId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access.public import effective_permissions
from skm.modules.execution.domain.contracts import EvidenceOwnerKind
from skm.modules.execution.generated.queries import GetAttempt
from skm.modules.execution.generated.views import AttemptView
from skm.modules.execution.ports import AttemptRepository, EvidenceBindingRepository, ExecutionQueries

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["SPEC", "handle"]


def _resolve_scope(query: GetAttempt, uow: UnitOfWork) -> ScopeRef | None:
    try:
        attempt = uow.repo(AttemptRepository).get(AttemptId(query.attempt_id))
    except NotFound:
        return None
    return ScopeRef(ScopeKind.RUN, ScopeId(attempt.run_id))


def handle(query: GetAttempt, ctx: QueryContext, uow: UnitOfWork) -> AttemptView:
    aid = AttemptId(query.attempt_id)
    attempt = uow.repo(AttemptRepository).get(aid)
    doc = deepcopy(dict(uow.repo(ExecutionQueries).attempt_view(aid)))
    perms = effective_permissions(uow, ctx.actor, ScopeId(attempt.run_id))
    if "checkout.read_locator" not in perms and isinstance(stages := doc.get("stages"), list):
        for stg in stages:
            if isinstance(stg, dict) and isinstance(env := stg.get("environment"), dict):
                env.pop("local_locator", None)
    bindings = uow.repo(EvidenceBindingRepository)
    groups: tuple[tuple[str, str, EvidenceOwnerKind], ...] = (
        ("checks", "check_execution_id", "check_execution"),
        ("reviews", "review_id", "review"),
    )
    for rows, id_key, kind in groups:
        entries = doc.get(rows)
        if isinstance(entries, list):
            for row in entries:
                if isinstance(row, dict) and isinstance(owner_id := row.get(id_key), str):
                    row["evidence_refs"] = [
                        {"file_version_id": str(version_id), "role": str(role)}
                        for version_id, role in bindings.for_owner(kind, UUID(owner_id))
                    ]
    return AttemptView.from_json(doc)


SPEC = QuerySpec(
    name="execution.get_attempt",
    dto=GetAttempt,
    result=AttemptView,
    permission="run.read",
    scope_of=None,
    handler=handle,
    scope_resolver=_resolve_scope,
)
