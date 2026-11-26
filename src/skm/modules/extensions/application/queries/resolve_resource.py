"""``extensions.resolve_resource`` (extensions §8, §4.12): the explanation of a choice.

It answers with the candidates and the diagnostics even when nothing can be chosen (``chosen = null``); the
facade of the same name raises the normative error instead.
"""

from typing import cast

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.extensions.application.resolving import decide, resource_version_view
from skm.modules.extensions.domain.keys import parse_resource_key
from skm.modules.extensions.domain.kinds import ResourceKind
from skm.modules.extensions.generated.queries import ResolveResource
from skm.modules.extensions.generated.views import ResolutionView, ResolutionViewCandidatesItem

__all__ = ["SPEC", "handle"]


def handle(query: ResolveResource, ctx: QueryContext, uow: UnitOfWork) -> ResolutionView:
    kind = ResourceKind(query.kind.value)
    key = parse_resource_key(query.key, prompt_block=kind is ResourceKind.PROMPT_BLOCK)
    decision, diagnostics, _missing = decide(uow, kind, key, config=ctx.config, pins=None)
    return ResolutionView(
        chosen=None if decision.chosen is None else resource_version_view(uow, decision.chosen.id),
        candidates=tuple(
            ResolutionViewCandidatesItem(
                pack=row.pack, version=row.version, digest=row.digest, verdict=row.verdict, reason=row.reason
            )
            for row in decision.candidates
        ),
        diagnostics=tuple(
            cast(
                "dict[str, JsonValue]",
                {
                    "code": item.code,
                    "message": item.message,
                    "severity": item.severity.value,
                    "target": item.target,
                },
            )
            for item in diagnostics
        ),
    )


SPEC = QuerySpec(
    name="extensions.resolve_resource",
    dto=ResolveResource,
    result=ResolutionView,
    permission="ext.read",
    scope_of=lambda query: ScopeRef(ScopeKind(query.scope.kind), ScopeId(query.scope.id)),
    handler=handle,
)
