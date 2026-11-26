"""Occurrence-based differences between two manifests in the authorized project."""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.context.application.queries.explain_context import load_manifest
from skm.modules.context.application.query_dtos import ContextDiffResponse, DiffContextsRequest
from skm.modules.context.domain.explain import diff_manifests
from skm.modules.context.domain.reasons import HIDDEN_REASONS
from skm.modules.context.generated.views import ContextDiffView, context_diff_view_from_json

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.context.domain.manifest import ContextManifest


def scope_of(query: DiffContextsRequest) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(cast("str", query["project_id"]))))


def _digests(manifest: ContextManifest) -> dict[tuple[str, str, int], str | None]:
    occurrences: dict[tuple[str, str], int] = defaultdict(int)
    result: dict[tuple[str, str, int], str | None] = {}
    for block in sorted(manifest.blocks, key=lambda b: b.ordinal):
        if not block.included or block.reason in HIDDEN_REASONS:
            continue
        key = block.block_type.value, block.source_ref
        result[(*key, occurrences[key])] = block.content_digest
        occurrences[key] += 1
    return result


def handle(query: DiffContextsRequest, ctx: QueryContext, uow: UnitOfWork) -> ContextDiffView:
    base = load_manifest(
        uow, ctx.actor.principal_id, cast("str", query["project_id"]), cast("str", query["base_manifest_id"])
    )
    target = load_manifest(
        uow,
        ctx.actor.principal_id,
        cast("str", query["project_id"]),
        cast("str | None", query.get("target_manifest_id")),
        step_id=cast("str | None", query.get("step_id")),
    )
    diff = diff_manifests(base, target)
    before, after = _digests(base), _digests(target)
    rows: list[JsonObject] = []
    counts: JsonObject = dict.fromkeys(("added", "removed", "changed", "same"), 0)
    for raw in cast("list[JsonObject]", diff["blocks"]):
        change = str(raw["status"])
        left, right = cast("int | None", raw["base_tokens"]), cast("int | None", raw["target_tokens"])
        key = str(raw["block_type"]), str(raw["source"]), int(cast("int", raw["occurrence"]))
        rows.append(
            {
                "block_type": key[0],
                "source_ref": key[1],
                "occurrence": key[2],
                "change": change,
                "tokens": {"from": left, "to": right, "delta": (right or 0) - (left or 0)},
                "digest": {"from": before.get(key), "to": after.get(key)},
            }
        )
        counts[change] = int(cast("int", counts[change])) + 1
    return context_diff_view_from_json(
        {"blocks": cast("list[JsonValue]", rows), "tokens": diff["tokens"], "counts": counts}
    )


SPEC = QuerySpec(
    name="context.diff_contexts",
    dto=DiffContextsRequest,
    result=ContextDiffResponse,
    permission="context.read",
    scope_of=scope_of,
    handler=handle,
)
