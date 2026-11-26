"""Project-scoped context explanation with visible totals and explicit read boundaries."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, cast
from uuid import UUID

from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import ContextManifestId, ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.context.application.query_dtos import ContextExplainResponse, ExplainContextRequest
from skm.modules.context.domain.explain import explain_rows
from skm.modules.context.domain.host_inputs import selector_ref
from skm.modules.context.domain.reasons import HIDDEN_REASONS
from skm.modules.context.domain.request import validate_owner_ref
from skm.modules.context.generated.views import ContextExplainView, context_explain_view_from_json
from skm.modules.context.ports import ContextRepository

if TYPE_CHECKING:
    from skm.application_bus.context import QueryContext
    from skm.kernel.ids import PrincipalId
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.context.domain.manifest import ContextManifest, ManifestBlock


def scope_of(query: ExplainContextRequest) -> ScopeRef:
    return ScopeRef(ScopeKind.PROJECT, ScopeId(UUID(cast("str", query["project_id"]))))


def load_manifest(
    uow: UnitOfWork,
    principal_id: PrincipalId,
    project_id: str,
    manifest_id: str | None,
    *,
    step_id: str | None = None,
) -> ContextManifest:
    if (step_id is None) == (manifest_id is None):
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "select exactly one context manifest or step")
    repo = uow.repo(ContextRepository)
    manifest = (
        repo.get(ContextManifestId(UUID(manifest_id)))
        if manifest_id is not None
        else repo.for_step(str(UUID(cast("str", step_id))))
    )
    owner = validate_owner_ref(manifest.owner_ref, manifest.purpose.step_ref)
    if manifest.project_id != UUID(project_id) or (owner is not None and owner != principal_id):
        raise NotFound(ErrorCode.NOT_FOUND, "context manifest not found")
    return manifest


def _visible(manifest: ContextManifest, block: ManifestBlock) -> bool:
    # A planned checkout path is already known to the caller; absent private CP sources stay hidden.
    planned_missing = (
        block.reason == "not_found"
        and block.source_kind == "repository_path"
        and any(
            block.block_ref == f"h:{req.request_id}" and block.source_ref == req.source_ref
            for req in manifest.host_inputs
        )
    )
    return block.reason not in HIDDEN_REASONS or planned_missing


def _rows(manifest: ContextManifest, visible: tuple[ManifestBlock, ...]) -> list[JsonObject]:
    requests = {f"h:{req.request_id}": req for req in manifest.host_inputs}
    result: list[JsonObject] = []
    for block in sorted(visible, key=lambda b: (b.position is None, b.position or 0, b.ordinal)):
        rows = explain_rows(replace(manifest, blocks=(block,)))
        row: JsonObject = (
            rows[0]
            if rows
            else {
                "pos": block.position,
                "block_type": block.block_type.value,
                "source": block.source_ref,
                "tokens": None,
                "digest": "",
                "trust": block.trust.value,
                "reason": block.reason,
                "included": block.included,
                "selector": None,
                "detail": None,
            }
        )
        req = requests.get(block.block_ref)
        if req is not None:
            row["selector"] = selector_ref(req.selector)
        row["backlinks"] = "unknown"
        row["dependencies"] = "unknown"
        result.append(row)
    return result


def _public_trace(manifest: ContextManifest) -> JsonObject:
    hidden = tuple(b for b in manifest.blocks if not _visible(manifest, b))
    hidden_refs = {b.source_ref for b in hidden}

    def skill_key(ref: str) -> str | None:
        for prefix in ("resource:skill:", "skill:"):
            if ref.startswith(prefix):
                return ref.removeprefix(prefix).partition("@")[0]
        return ref.partition("@")[0] if ":" not in ref else None

    hidden_keys = {skill_key(b.source_ref) for b in hidden if b.block_type.value == "skills"}
    hidden_keys.discard(None)

    def contains_hidden_ref(value: JsonValue) -> bool:
        return isinstance(value, str) and any(ref and ref in value for ref in hidden_refs)

    def inaccessible(value: JsonValue) -> bool:
        return isinstance(value, str) and (contains_hidden_ref(value) or skill_key(value) in hidden_keys)

    def clean(value: JsonValue, *, identity: bool = False) -> JsonValue:
        if contains_hidden_ref(value) or (identity and inaccessible(value)):
            return None
        if isinstance(value, list):
            # Dictionaries in trace sequences are records; their field names are structural.
            return [
                result
                for item in value
                if (result := clean(item, identity=identity and not isinstance(item, dict))) is not None
            ]
        if isinstance(value, dict):
            if identity:
                # A trace mapping indexes skills even when an ID is literally "key" or "reason".
                return {key: clean(item) for key, item in value.items() if not inaccessible(key)}
            if any(
                inaccessible(value.get(key)) for key in ("key", "skill_key", "source_ref", "source", "ref")
            ) or any(contains_hidden_ref(item) for item in value.values()):
                return None
            # Aggregate counts cannot be copied after inaccessible entries were removed.
            return {
                key: clean(item)
                for key, item in value.items()
                if key not in {"count", "counts", "total"} and not key.endswith(("_count", "_counts"))
            }
        return value

    # Internal render snapshots and host request plans are not an explain view.
    keys = ("mode", "budget", "included", "conditional", "excluded", "discoverable")
    trace: JsonObject = {
        key: clean(manifest.skills_trace[key], identity=key not in {"mode", "budget"})
        for key in keys
        if key in manifest.skills_trace
    }
    trace["used"] = sum(
        b.tokens_estimate or 0
        for b in manifest.blocks
        if b.included and b.block_type.value == "skills" and b.reason not in HIDDEN_REASONS
    )
    return trace


def handle(query: ExplainContextRequest, ctx: QueryContext, uow: UnitOfWork) -> ContextExplainView:
    manifest = load_manifest(
        uow,
        ctx.actor.principal_id,
        cast("str", query["project_id"]),
        cast("str | None", query.get("manifest_id")),
        step_id=cast("str | None", query.get("step_id")),
    )
    visible = tuple(b for b in manifest.blocks if _visible(manifest, b))
    rows = _rows(manifest, visible)
    budgets: JsonObject = {
        cls.value: {
            "tokens": sum(b.tokens_estimate or 0 for b in visible if b.included and b.budget_class is cls)
            if manifest.total_tokens_estimate is not None
            else None,
            "limit": usage.limit,
        }
        for cls, usage in manifest.budgets.items()
    }
    route = manifest.route
    self_loads = route.get("self_loads_observed")
    if self_loads is None:
        self_loads = route.get("self_loads", [])
    diagnostics = list(manifest.diagnostics)
    if manifest.host_facts and manifest.host_facts.get("work_paths_truncated"):
        diagnostics.append(
            {"code": "WORK_PATHS_TRUNCATED", "severity": "warning", "detail": "work paths are incomplete"}
        )
    return context_explain_view_from_json(
        {
            "state": manifest.state.value,
            "route": {
                "runtime_id": manifest.runtime_id,
                "model": manifest.model,
                "source": route.get("route_source", route.get("source")),
                "operation": route.get("operation"),
                "config_mode": route.get("config_mode"),
                "degraded": route.get("degraded", []),
            },
            "runtime_self_loads": self_loads,
            "rows": rows,
            "excluded": [
                {
                    "block_type": b.block_type.value,
                    "source_ref": b.source_ref,
                    "reason": b.reason,
                    "detail": b.detail,
                }
                for b in visible
                if b.included is False
            ],
            "budgets": budgets,
            "totals": {
                "tokens": sum(b.tokens_estimate or 0 for b in visible if b.included)
                if manifest.total_tokens_estimate is not None
                else None,
                "limit": manifest.total_limit,
                "included": sum(b.included is True for b in visible),
                "excluded": sum(b.included is False for b in visible),
            },
            "mode": manifest.mode,
            "skills_trace": _public_trace(manifest),
            "host_facts": manifest.host_facts,
            "diagnostics": diagnostics,
        }
    )


SPEC = QuerySpec(
    name="context.explain_context",
    dto=ExplainContextRequest,
    result=ContextExplainResponse,
    permission="context.read",
    scope_of=scope_of,
    handler=handle,
)
