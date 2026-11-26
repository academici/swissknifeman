"""Model catalog data, merging, overrides and staleness (runtimes §4.2, ``runtime_catalog:*``).

Prices are decimal strings in the resource (``"3.00"``) parsed into ``Decimal``; a float never enters a price,
a digest or a cost. A model without verified pricing has ``pricing = None`` and its cost stays unknown.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Final, Literal, Protocol, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.ids import ResourceVersionId

from .classes import EFFORT_ORDER, MODEL_CLASS_ORDER, Effort, ModelClass, RoleId
from .ids import Digest, ModelId, RuntimeId, is_runtime_id

if TYPE_CHECKING:
    from skm.kernel.json_types import JsonObject, JsonValue

__all__ = [
    "CatalogResourceLike",
    "ModelCatalog",
    "ModelEntry",
    "ModelStatus",
    "Pricing",
    "RuntimeCatalogEntry",
    "catalog_digest",
    "is_catalog_stale",
    "load_catalog",
    "merge_catalogs",
    "parse_catalog_document",
    "parse_price",
    "parse_pricing",
]

_PRICE: Final = re.compile(r"[0-9]+(\.[0-9]+)?")


class CatalogResourceLike(Protocol):
    """Structural contract matching ``extensions.public.RuntimeCatalogEntry``."""

    @property
    def key(self) -> str: ...

    @property
    def resource_version_id(self) -> ResourceVersionId: ...

    @property
    def manifest(self) -> Mapping[str, JsonValue]: ...


def parse_price(value: object, name: str) -> Decimal:
    """A non-negative decimal string such as ``"3.00"``; numbers are refused so no float reaches a price."""
    if not isinstance(value, str) or _PRICE.fullmatch(value) is None:
        raise ValueError(f"{name} must be a decimal string like '3.00', got {value!r}")
    try:
        return Decimal(value)
    except InvalidOperation as exc:  # pragma: no cover - the pattern admits only valid decimals
        raise ValueError(f"{name}: {value!r} is not a decimal") from exc


@dataclass(frozen=True, slots=True)
class Pricing:
    input_per_mtok_usd: Decimal
    output_per_mtok_usd: Decimal
    cache_read_per_mtok_usd: Decimal | None
    cache_write_per_mtok_usd: Decimal | None
    currency: Literal["USD"]
    verified_at: date
    source: str

    def __post_init__(self) -> None:
        for name in ("input_per_mtok_usd", "output_per_mtok_usd"):
            _check_price(getattr(self, name), name, optional=False)
        for name in ("cache_read_per_mtok_usd", "cache_write_per_mtok_usd"):
            _check_price(getattr(self, name), name, optional=True)
        if self.currency != "USD":
            raise ValueError("currency must be USD")
        if not isinstance(self.verified_at, date):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise TypeError("verified_at must be a date")


def _check_price(value: object, name: str, *, optional: bool) -> None:
    if value is None and optional:
        return
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise TypeError(f"{name} must be a finite non-negative Decimal")


def parse_pricing(data: Mapping[str, JsonValue] | None) -> Pricing | None:
    """``pricing`` of a ``model-catalog`` model entry; absent/null stays None (cost unknown)."""
    if data is None:
        return None
    cache_read = data.get("cache_read_per_mtok_usd")
    cache_write = data.get("cache_write_per_mtok_usd")
    verified_at = data["verified_at"]
    source = data["source"]
    if not isinstance(verified_at, str) or not isinstance(source, str):
        raise TypeError("pricing.verified_at and pricing.source must be strings")
    if data["currency"] != "USD":
        raise ValueError("pricing.currency must be USD")
    return Pricing(
        input_per_mtok_usd=parse_price(data["input_per_mtok_usd"], "input_per_mtok_usd"),
        output_per_mtok_usd=parse_price(data["output_per_mtok_usd"], "output_per_mtok_usd"),
        cache_read_per_mtok_usd=None
        if cache_read is None
        else parse_price(cache_read, "cache_read_per_mtok_usd"),
        cache_write_per_mtok_usd=None
        if cache_write is None
        else parse_price(cache_write, "cache_write_per_mtok_usd"),
        currency="USD",
        verified_at=date.fromisoformat(verified_at),
        source=source,
    )


class ModelStatus(StrEnum):
    CONFIRMED = "confirmed"
    UNVERIFIED = "unverified"
    DEPRECATED = "deprecated"


@dataclass(frozen=True, slots=True)
class ModelEntry:
    id: ModelId  # string passed to the runtime, e.g. "opus"
    runtime_id: RuntimeId
    display_name: str
    classes: frozenset[ModelClass]
    suited_roles: frozenset[RoleId]  # a hint, not a restriction
    context_window_tokens: int  # >= 1000
    max_output_tokens: int | None
    pricing: Pricing | None  # None: usage.cost_usd_micros stays None
    patterns: tuple[str, ...]  # regexes recognizing variants of the model
    status: ModelStatus
    verified_at: date
    source: str
    notes: str

    def matches(self, model: ModelId) -> bool:
        return model == self.id or any(re.fullmatch(pattern, model) for pattern in self.patterns)


@dataclass(frozen=True, slots=True)
class RuntimeCatalogEntry:
    runtime_id: RuntimeId
    class_selectors: Mapping[ModelClass, tuple[ModelId, ...]]  # preference order
    effort_selectors: Mapping[Effort, str]  # runtime effort flag value ("" = do not pass)
    models: tuple[ModelEntry, ...]


@dataclass(frozen=True, slots=True)
class ModelCatalog:
    catalog_version: str
    resource_version_ids: tuple[ResourceVersionId, ...]
    digest: Digest
    runtimes: Mapping[RuntimeId, RuntimeCatalogEntry]

    def __post_init__(self) -> None:
        object.__setattr__(self, "runtimes", MappingProxyType(dict(self.runtimes)))

    def model(self, runtime_id: RuntimeId, model: ModelId) -> ModelEntry | None:
        """Exact id first, then the first entry whose pattern matches the whole model string."""
        entry = self.runtimes.get(runtime_id)
        if entry is None:
            return None
        for candidate in entry.models:
            if candidate.id == model:
                return candidate
        for candidate in entry.models:
            if candidate.matches(model):
                return candidate
        return None

    def pick(self, runtime_id: RuntimeId, model_class: ModelClass) -> ModelEntry | None:
        """First non-deprecated model of the class selector, in preference order."""
        entry = self.runtimes.get(runtime_id)
        if entry is None:
            return None
        by_id = {candidate.id: candidate for candidate in entry.models}
        for model_id in entry.class_selectors.get(model_class, ()):
            candidate = by_id.get(model_id)
            if candidate is not None and candidate.status is not ModelStatus.DEPRECATED:
                return candidate
        return None


def _normalize_toml(value: object) -> JsonValue:
    if isinstance(value, float):
        raise ValidationFailed(
            ErrorCode.CONFIG_INVALID,
            "floating-point numbers are forbidden in model catalogs; use decimal strings for prices",
            details={"reason": "float_in_catalog"},
        )
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, Mapping):
        return {
            str(key): _normalize_toml(item) for key, item in cast("Mapping[object, object]", value).items()
        }
    if isinstance(value, list | tuple):
        return [_normalize_toml(item) for item in cast("Iterable[object]", value)]
    raise ValidationFailed(
        ErrorCode.CONFIG_INVALID,
        f"unsupported value in model catalog: {type(value).__name__}",
        details={"reason": "catalog_invalid"},
    )


def _invalid_catalog(message: str) -> ValidationFailed:
    return ValidationFailed(ErrorCode.CONFIG_INVALID, message, details={"reason": "catalog_invalid"})


def _parse_model(runtime_id: RuntimeId, raw: Mapping[str, JsonValue]) -> ModelEntry:
    try:
        model_id = raw["id"]
        display_name = raw["display_name"]
        context_window = raw["context_window_tokens"]
        max_output = raw.get("max_output_tokens")
        classes_raw = raw["classes"]
        roles_raw = raw.get("suited_roles", [])
        patterns_raw = raw.get("patterns", [])
        status_raw = raw["status"]
        verified_raw = raw["verified_at"]
        source = raw["source"]
        notes = raw.get("notes", "")
        pricing_raw = raw.get("pricing")
        if (
            not isinstance(model_id, str)
            or not model_id
            or not isinstance(display_name, str)
            or type(context_window) is not int
            or context_window < 1000
            or (max_output is not None and (type(max_output) is not int or max_output < 1))
            or not isinstance(classes_raw, list)
            or not isinstance(roles_raw, list)
            or not isinstance(patterns_raw, list)
            or not isinstance(status_raw, str)
            or not isinstance(verified_raw, str)
            or not isinstance(source, str)
            or not isinstance(notes, str)
            or (pricing_raw is not None and not isinstance(pricing_raw, Mapping))
        ):
            raise _invalid_catalog(f"malformed model entry in runtime {runtime_id!r}")
        for pattern in patterns_raw:
            if not isinstance(pattern, str):
                raise _invalid_catalog(f"pattern in model {model_id!r} must be a string")
            re.compile(pattern)
        return ModelEntry(
            id=model_id,
            runtime_id=runtime_id,
            display_name=display_name,
            classes=frozenset(ModelClass(cast("str", item)) for item in classes_raw),
            suited_roles=frozenset(RoleId(cast("str", item)) for item in roles_raw),
            context_window_tokens=context_window,
            max_output_tokens=max_output,
            pricing=parse_pricing(cast("Mapping[str, JsonValue] | None", pricing_raw)),
            patterns=tuple(cast("list[str]", patterns_raw)),
            status=ModelStatus(status_raw),
            verified_at=date.fromisoformat(verified_raw),
            source=source,
            notes=notes,
        )
    except ValidationFailed:
        raise
    except (KeyError, TypeError, ValueError, re.error) as exc:
        raise _invalid_catalog(f"invalid model entry in runtime {runtime_id!r}: {exc}") from exc


def _parse_runtime_entry(runtime_id: str, entry_raw: Mapping[str, JsonValue]) -> RuntimeCatalogEntry:
    class_sel_raw = entry_raw.get("class_selectors")
    effort_sel_raw = entry_raw.get("effort_selectors")
    models_raw = entry_raw.get("models")
    if (
        not isinstance(class_sel_raw, Mapping)
        or not isinstance(effort_sel_raw, Mapping)
        or not isinstance(models_raw, list)
    ):
        raise _invalid_catalog(f"malformed runtime section {runtime_id!r}")

    class_selectors: dict[ModelClass, tuple[ModelId, ...]] = {}
    for cls_name, ids in class_sel_raw.items():
        if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
            raise _invalid_catalog(f"invalid class_selectors.{cls_name} in {runtime_id!r}")
        try:
            cls = ModelClass(cls_name)
        except ValueError as exc:
            raise _invalid_catalog(f"unknown model class {cls_name!r} in {runtime_id!r}") from exc
        class_selectors[cls] = tuple(cast("list[str]", ids))

    effort_selectors: dict[Effort, str] = {}
    for effort_name, flag in effort_sel_raw.items():
        if not isinstance(flag, str):
            raise _invalid_catalog(f"invalid effort_selectors.{effort_name} in {runtime_id!r}")
        try:
            eff = Effort(effort_name)
        except ValueError as exc:
            raise _invalid_catalog(f"unknown effort {effort_name!r} in {runtime_id!r}") from exc
        effort_selectors[eff] = flag

    models: list[ModelEntry] = []
    seen_ids: set[ModelId] = set()
    for item in models_raw:
        if not isinstance(item, Mapping):
            raise _invalid_catalog(f"model entry in {runtime_id!r} must be a table")
        model = _parse_model(runtime_id, cast("Mapping[str, JsonValue]", item))
        if model.id in seen_ids:
            raise _invalid_catalog(f"duplicate model id {model.id!r} in {runtime_id!r}")
        seen_ids.add(model.id)
        models.append(model)

    return RuntimeCatalogEntry(
        runtime_id=runtime_id,
        class_selectors=MappingProxyType(class_selectors),
        effort_selectors=MappingProxyType(effort_selectors),
        models=tuple(models),
    )


def parse_catalog_document(body: Mapping[str, object]) -> tuple[str, dict[RuntimeId, RuntimeCatalogEntry]]:
    """Parse one ``urn:skm:runtimes:model-catalog:v1`` manifest mapping."""
    if not isinstance(body, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise _invalid_catalog("model catalog document must be a mapping")
    doc = cast("JsonObject", _normalize_toml(body))

    schema = doc.get("schema")
    if schema != "urn:skm:runtimes:model-catalog:v1":
        raise _invalid_catalog(f"unexpected model catalog schema {schema!r}")
    catalog_version = doc.get("catalog_version")
    if not isinstance(catalog_version, str) or not catalog_version:
        raise _invalid_catalog("catalog_version must be a non-empty string")
    runtimes_raw = doc.get("runtimes")
    if not isinstance(runtimes_raw, Mapping):
        raise _invalid_catalog("runtimes must be a mapping")

    parsed: dict[RuntimeId, RuntimeCatalogEntry] = {}
    for runtime_id, entry_raw in sorted(runtimes_raw.items()):
        if not is_runtime_id(runtime_id) or not isinstance(entry_raw, Mapping):
            raise _invalid_catalog(f"invalid runtime catalog entry {runtime_id!r}")
        parsed[runtime_id] = _parse_runtime_entry(runtime_id, cast("Mapping[str, JsonValue]", entry_raw))
    return catalog_version, parsed


def _pricing_canonical(pricing: Pricing | None) -> JsonObject | None:
    if pricing is None:
        return None
    return {
        "cache_read_per_mtok_usd": None
        if pricing.cache_read_per_mtok_usd is None
        else str(pricing.cache_read_per_mtok_usd),
        "cache_write_per_mtok_usd": None
        if pricing.cache_write_per_mtok_usd is None
        else str(pricing.cache_write_per_mtok_usd),
        "currency": pricing.currency,
        "input_per_mtok_usd": str(pricing.input_per_mtok_usd),
        "output_per_mtok_usd": str(pricing.output_per_mtok_usd),
        "source": pricing.source,
        "verified_at": pricing.verified_at.isoformat(),
    }


def catalog_digest(
    catalog_version: str,
    resource_version_ids: Sequence[ResourceVersionId],
    runtimes: Mapping[RuntimeId, RuntimeCatalogEntry],
) -> Digest:
    """Canonical SHA-256 digest of a resolved (and overridden) ``ModelCatalog`` (no floats)."""
    payload: dict[str, object] = {
        "catalog_version": catalog_version,
        "resource_version_ids": [str(item) for item in resource_version_ids],
        "runtimes": {
            runtime_id: {
                "class_selectors": {
                    cls.value: list(entry.class_selectors.get(cls, ()))
                    for cls in MODEL_CLASS_ORDER
                    if cls in entry.class_selectors
                },
                "effort_selectors": {
                    eff.value: entry.effort_selectors[eff]
                    for eff in EFFORT_ORDER
                    if eff in entry.effort_selectors
                },
                "models": [
                    {
                        "classes": [cls.value for cls in MODEL_CLASS_ORDER if cls in model.classes],
                        "context_window_tokens": model.context_window_tokens,
                        "display_name": model.display_name,
                        "id": model.id,
                        "max_output_tokens": model.max_output_tokens,
                        "notes": model.notes,
                        "patterns": list(model.patterns),
                        "pricing": _pricing_canonical(model.pricing),
                        "source": model.source,
                        "status": model.status.value,
                        "suited_roles": sorted(role.value for role in model.suited_roles),
                        "verified_at": model.verified_at.isoformat(),
                    }
                    for model in entry.models
                ],
            }
            for runtime_id, entry in sorted(runtimes.items())
        },
    }
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return f"sha256:{hashlib.sha256(raw).hexdigest()}"


def merge_catalogs(
    resources: Sequence[CatalogResourceLike], *, snapshot: CatalogResourceLike | None = None
) -> ModelCatalog:
    """Merge base resources by key, then apply an optional operator snapshot of model rows."""
    ordered = sorted(resources, key=lambda item: item.key)
    merged: dict[RuntimeId, RuntimeCatalogEntry] = {}
    owners: dict[RuntimeId, str] = {}
    version_ids: list[ResourceVersionId] = []
    catalog_version = "0.0.0"

    for index, resource in enumerate(ordered):
        doc_version, runtimes = parse_catalog_document(resource.manifest)
        if index == 0 or resource.key == "models":
            catalog_version = doc_version
        version_ids.append(resource.resource_version_id)
        for runtime_id, entry in sorted(runtimes.items()):
            first_key = owners.get(runtime_id)
            if first_key is not None:
                raise Conflict(
                    ErrorCode.EXTENSION_OVERRIDE_NOT_DECLARED,
                    f"runtime {runtime_id!r} is declared by multiple runtime_catalog resources",
                    details={
                        "reason": "CONFIG_CONFLICT",
                        "runtime_id": runtime_id,
                        "resources": [first_key, resource.key],
                    },
                )
            owners[runtime_id] = resource.key
            merged[runtime_id] = entry

    if snapshot is not None:
        doc_version, runtimes = parse_catalog_document(snapshot.manifest)
        if not ordered:
            catalog_version = doc_version
        version_ids.append(snapshot.resource_version_id)
        for runtime_id, entry in runtimes.items():
            base = merged.get(runtime_id)
            if base is None:
                merged[runtime_id] = entry
                continue
            models = {model.id: model for model in base.models}
            models.update((model.id, model) for model in entry.models)
            merged[runtime_id] = replace(base, models=tuple(models.values()))

    digest = catalog_digest(catalog_version, version_ids, merged)
    return ModelCatalog(
        catalog_version=catalog_version,
        resource_version_ids=tuple(version_ids),
        digest=digest,
        runtimes=merged,
    )


def _price_override_text(value: object, field_name: str) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Decimal):
        return format(value, "f")
    if type(value) is int:
        return str(value)
    if isinstance(value, float):
        return repr(value)
    raise _invalid_catalog(f"invalid override price for {field_name}: {value!r}")


def _apply_model_override(model: ModelEntry, override: Mapping[str, object]) -> ModelEntry:
    window = model.context_window_tokens
    for key in ("context_window_tokens", "context_window"):
        if key in override and override[key] is not None:
            raw_window = override[key]
            if type(raw_window) is not int or raw_window < 1000:
                raise _invalid_catalog(f"invalid {key} override on {model.runtime_id}:{model.id}")
            window = raw_window

    classes = model.classes
    if "classes" in override and override["classes"] is not None:
        raw_classes = override["classes"]
        if not isinstance(raw_classes, Sequence) or isinstance(raw_classes, str):
            raise _invalid_catalog(f"invalid classes override on {model.runtime_id}:{model.id}")
        seq_classes = cast("Sequence[object]", raw_classes)
        classes = frozenset(ModelClass(str(item)) for item in seq_classes)
    elif "tier" in override and override["tier"] is not None:
        classes = frozenset({ModelClass(str(override["tier"]))})

    status = model.status
    if override.get("disabled") is True:
        status = ModelStatus.DEPRECATED
    elif "status" in override and override["status"] is not None:
        status = ModelStatus(str(override["status"]))

    pricing = model.pricing
    if "pricing" in override:
        raw_pricing = override["pricing"]
        if raw_pricing is None:
            pricing = None
        elif isinstance(raw_pricing, Mapping):
            pricing = parse_pricing(cast("Mapping[str, JsonValue]", raw_pricing))
        else:
            raise _invalid_catalog(f"invalid pricing override on {model.runtime_id}:{model.id}")
    elif any(
        key in override and override[key] is not None
        for key in ("input_usd_per_mtok", "output_usd_per_mtok", "cache_read_usd_per_mtok")
    ):
        inp_raw = override.get("input_usd_per_mtok")
        out_raw = override.get("output_usd_per_mtok")
        cache_read_raw = override.get("cache_read_usd_per_mtok")
        inp = (
            parse_price(_price_override_text(inp_raw, "input_usd_per_mtok"), "input_usd_per_mtok")
            if inp_raw is not None
            else (pricing.input_per_mtok_usd if pricing is not None else None)
        )
        out = (
            parse_price(_price_override_text(out_raw, "output_usd_per_mtok"), "output_usd_per_mtok")
            if out_raw is not None
            else (pricing.output_per_mtok_usd if pricing is not None else None)
        )
        if inp is None or out is None:
            raise _invalid_catalog(
                f"pricing override on {model.runtime_id}:{model.id} requires input and output prices"
            )
        cache_read = (
            parse_price(
                _price_override_text(cache_read_raw, "cache_read_usd_per_mtok"), "cache_read_usd_per_mtok"
            )
            if cache_read_raw is not None
            else (pricing.cache_read_per_mtok_usd if pricing is not None else None)
        )
        pricing = Pricing(
            input_per_mtok_usd=inp,
            output_per_mtok_usd=out,
            cache_read_per_mtok_usd=cache_read,
            cache_write_per_mtok_usd=pricing.cache_write_per_mtok_usd if pricing is not None else None,
            currency="USD",
            verified_at=pricing.verified_at if pricing is not None else model.verified_at,
            source="config:runtimes.models.overrides",
        )

    return replace(
        model,
        context_window_tokens=window,
        classes=classes,
        status=status,
        pricing=pricing,
    )


def load_catalog(
    resources: Sequence[CatalogResourceLike],
    overrides: Mapping[str, Mapping[str, object]] | None = None,
    *,
    snapshot: CatalogResourceLike | None = None,
) -> ModelCatalog:
    """Merge ``runtime_catalog:*`` resources and apply ``runtimes.models.overrides`` (§4.2).

    ``ModelCatalog.digest`` is recomputed after applying overrides.
    """
    base = merge_catalogs(resources, snapshot=snapshot)
    if not overrides:
        return base

    updated_runtimes: dict[RuntimeId, RuntimeCatalogEntry] = dict(base.runtimes)
    for target_key, spec in sorted(overrides.items()):
        if not isinstance(spec, Mapping):  # pyright: ignore[reportUnnecessaryIsInstance]
            raise _invalid_catalog(f"override {target_key!r} must be a mapping")
        if ":" in target_key:
            runtime_id, _, model_id = target_key.partition(":")
            candidates = (runtime_id,) if runtime_id in updated_runtimes else ()
        else:
            model_id = target_key
            candidates = tuple(sorted(updated_runtimes))
        for runtime_id in candidates:
            entry = updated_runtimes[runtime_id]
            models = tuple(
                _apply_model_override(model, spec) if model.id == model_id else model
                for model in entry.models
            )
            if models != entry.models:
                updated_runtimes[runtime_id] = replace(entry, models=models)

    digest = catalog_digest(base.catalog_version, base.resource_version_ids, updated_runtimes)
    return ModelCatalog(
        catalog_version=base.catalog_version,
        resource_version_ids=base.resource_version_ids,
        digest=digest,
        runtimes=updated_runtimes,
    )


def is_catalog_stale(catalog: ModelCatalog, *, today: date, max_age_days: int) -> bool:
    """True when any catalog model (or pricing) ``verified_at`` is older than ``max_age_days``."""
    if max_age_days < 1:
        raise ValueError("max_age_days must be >= 1")
    for entry in catalog.runtimes.values():
        for model in entry.models:
            if (today - model.verified_at).days > max_age_days:
                return True
            if model.pricing is not None and (today - model.pricing.verified_at).days > max_age_days:
                return True
    return False
