"""``runtimes.list_models`` (runtimes §8) and catalog resolution helpers (§13)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING, Any, cast

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, ValidationFailed
from skm.kernel.ids import ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.extensions import public as extensions
from skm.modules.runtimes.domain.catalog import (
    ModelCatalog,
    ModelEntry,
    is_catalog_stale,
    load_catalog,
)
from skm.modules.runtimes.domain.catalog_sync import CATALOG_RESOURCE_KEY
from skm.modules.runtimes.domain.classes import MODEL_CLASS_ORDER, ModelClass
from skm.modules.runtimes.domain.ids import ModelId, RuntimeId
from skm.modules.runtimes.domain.usage import UsageReport, cost
from skm.modules.runtimes.generated.queries import ListModels
from skm.modules.runtimes.generated.views import ModelsView
from skm.platform.config import ConfigLoader, ConfigStore, PackConfigSource, ScopeTree

if TYPE_CHECKING:
    from skm.platform.config import EffectiveConfig

__all__ = [
    "SPEC",
    "handle",
    "resolve_catalog",
    "resolve_model_entry",
    "resolve_model_guideline",
    "resolve_usage_cost",
]


def resolve_catalog(
    uow: UnitOfWork,
    *,
    config: EffectiveConfig,
    pins: extensions.PackPins | None = None,
) -> ModelCatalog:
    """Resolve ``runtime_catalog:*`` resources within ``pins`` and apply ``runtimes.models.overrides``."""
    view = extensions.runtime_catalog(uow, (), config, pins=pins)
    entries = () if view is None else view.entries
    snapshot = next(
        (entry for entry in entries if entry.key == CATALOG_RESOURCE_KEY and entry.is_operator_snapshot),
        None,
    )
    raw_overrides = config.get("runtimes.models.overrides")
    if raw_overrides is not None and not isinstance(raw_overrides, Mapping):
        raise TypeError("runtimes.models.overrides must be a mapping")
    overrides = cast("Mapping[str, Mapping[str, object]] | None", raw_overrides)
    base = tuple(entry for entry in entries if entry is not snapshot)
    return load_catalog(base, overrides, snapshot=snapshot)


def resolve_model_entry(
    uow: UnitOfWork,
    runtime_id: RuntimeId,
    model: ModelId,
    *,
    config: EffectiveConfig,
    pins: extensions.PackPins | None = None,
) -> ModelEntry | None:
    return resolve_catalog(uow, config=config, pins=pins).model(runtime_id, model)


def resolve_model_guideline(
    uow: UnitOfWork,
    runtime_id: str | None,
    model: str,
    *,
    catalog: ModelCatalog,
    config: EffectiveConfig,
    pins: extensions.PackPins | None = None,
) -> Mapping[str, Any] | None:
    """Match the admitted selector first, then its catalog entry or a known catalog alias."""
    matches: dict[tuple[bool, bool], list[extensions.ResourceVersionView]] = {}
    entries = tuple(
        entry
        for rid in ((runtime_id,) if runtime_id else catalog.runtimes)
        if (entry := catalog.model(rid, model)) is not None
    )
    for view in extensions.list_resolved(
        uow, extensions.ResourceKind.MODEL_GUIDELINE, config=config, pins=pins
    ):
        profile = view.manifest
        allowed = profile.get("runtime_ids", [])
        if runtime_id is not None and allowed and runtime_id not in allowed:
            continue
        target = profile["model_id"]
        exact = target == model
        if not exact and not any(
            (not allowed or entry.runtime_id in allowed)
            and (target == entry.id or (model == entry.id and entry.matches(target)))
            for entry in entries
        ):
            continue
        matches.setdefault((exact, runtime_id is not None and bool(allowed)), []).append(view)
    if not matches:
        return None
    winners = matches[max(matches)]
    if len(winners) != 1:
        raise ValidationFailed(
            ErrorCode.EXTENSION_INCOMPATIBLE,
            "multiple model guidelines match the target",
            details={"model": model, "guidelines": list[JsonValue](sorted(p.key for p in winners))},
        )
    return winners[0].manifest


def resolve_usage_cost(
    uow: UnitOfWork,
    usage: UsageReport,
    runtime_id: RuntimeId,
    model: ModelId,
    *,
    config: EffectiveConfig,
    pins: extensions.PackPins | None = None,
) -> UsageReport:
    entry = resolve_model_entry(uow, runtime_id, model, config=config, pins=pins)
    computed = cost(usage, None if entry is None else entry.pricing)
    return replace(usage, cost_usd_micros=computed)


def _model_view(model: ModelEntry) -> JsonObject:
    pricing: JsonObject | None = None
    if model.pricing is not None:
        pricing = {
            "input_per_mtok_usd": str(model.pricing.input_per_mtok_usd),
            "output_per_mtok_usd": str(model.pricing.output_per_mtok_usd),
            "cache_read_per_mtok_usd": None
            if model.pricing.cache_read_per_mtok_usd is None
            else str(model.pricing.cache_read_per_mtok_usd),
            "cache_write_per_mtok_usd": None
            if model.pricing.cache_write_per_mtok_usd is None
            else str(model.pricing.cache_write_per_mtok_usd),
            "currency": model.pricing.currency,
            "verified_at": model.pricing.verified_at.isoformat(),
            "source": model.pricing.source,
        }
    return {
        "id": model.id,
        "runtime_id": model.runtime_id,
        "display_name": model.display_name,
        "classes": list[JsonValue]([cls.value for cls in MODEL_CLASS_ORDER if cls in model.classes]),
        "suited_roles": list[JsonValue](sorted(role.value for role in model.suited_roles)),
        "context_window_tokens": model.context_window_tokens,
        "max_output_tokens": model.max_output_tokens,
        "pricing": pricing,
        "patterns": list(model.patterns),
        "status": model.status.value,
        "verified_at": model.verified_at.isoformat(),
        "source": model.source,
        "notes": model.notes,
    }


def handle(query: ListModels, ctx: QueryContext, uow: UnitOfWork) -> ModelsView:
    config = ctx.config
    if query.host_id is not None:
        config = ConfigLoader(config.registry, uow.repo(PackConfigSource)).effective(
            uow.repo(ConfigStore), uow.repo(ScopeTree), None
        )
    catalog = resolve_catalog(uow, config=config)
    raw_max_age = config.get("runtimes.catalog.max_age_days")
    max_age_days = raw_max_age if type(raw_max_age) is int and raw_max_age >= 1 else 60
    stale = is_catalog_stale(catalog, today=ctx.clock.now().date(), max_age_days=max_age_days)

    if query.prepare_for is not None:
        guideline = resolve_model_guideline(
            uow,
            query.runtime_id,
            query.prepare_for,
            catalog=catalog,
            config=config,
        )
        if guideline is None:
            raise NotFound(
                ErrorCode.NOT_FOUND, "no guideline for target model", details={"model": query.prepare_for}
            )
        entry = catalog.model(query.runtime_id, query.prepare_for) if query.runtime_id else None
        row: JsonObject = _model_view(entry) if entry else {"id": query.prepare_for}
        row["guideline"] = dict(guideline)
        return ModelsView(catalog.catalog_version, catalog.digest, stale, (row,))

    want_class = ModelClass(query.model_class.value) if query.model_class is not None else None
    models: list[JsonObject] = []
    for runtime_id, entry in sorted(catalog.runtimes.items()):
        if query.runtime_id is not None and runtime_id != query.runtime_id:
            continue
        for model in entry.models:
            if want_class is not None and want_class not in model.classes:
                continue
            view = _model_view(model)
            if query.host_id is not None:
                view["efforts"] = list[JsonValue](effort.value for effort in entry.effort_selectors)
            models.append(view)

    return ModelsView(
        catalog_version=catalog.catalog_version,
        catalog_digest=catalog.digest,
        stale=stale,
        models=tuple(models),
    )


SPEC = QuerySpec(
    name="runtimes.list_models",
    dto=ListModels,
    result=ModelsView,
    permission="runtime.read",
    scope_of=lambda q: None if q.host_id is None else ScopeRef(ScopeKind.HOST, ScopeId(q.host_id)),
    handler=handle,
)
