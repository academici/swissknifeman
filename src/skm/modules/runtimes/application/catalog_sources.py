"""Pluggable catalog source adapters.

Each adapter normalizes one public inventory into ``CatalogCandidate`` rows. Transport is an
injected protocol, so a unit test supplies bytes and never opens a socket. A missing tariff stays
``None``; a present zero is a real price and is kept.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from typing import Protocol, cast
from urllib.parse import urlsplit

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, ValidationFailed
from skm.modules.runtimes.domain.catalog import ModelStatus
from skm.modules.runtimes.domain.catalog_sync import (
    SOURCE_IDS,
    CandidateTrust,
    CatalogCandidate,
    CatalogSourceId,
    PriceQuote,
)
from skm.modules.runtimes.domain.classes import ModelClass, RoleId

__all__ = [
    "DEFAULT_SOURCE_URLS",
    "CatalogTransport",
    "FallbackGeneralizationsSource",
    "ModelsDevSource",
    "OpenRouterSource",
    "SourceAdapter",
    "V1ModelsSource",
    "default_adapters",
]

DEFAULT_SOURCE_URLS: Mapping[CatalogSourceId, tuple[str, ...]] = {
    CatalogSourceId.MODELS_DEV: ("https://models.dev/api.json",),
    CatalogSourceId.OPENROUTER: (
        "https://openrouter.ai/api/v1/models",
        "https://openrouter.ai/api/v1/models/{id}/endpoints",
    ),
    CatalogSourceId.V1_MODELS: ("https://api.openai.com/v1/models",),
    CatalogSourceId.FALLBACK_GENERALIZATIONS: (),
}


class CatalogTransport(Protocol):
    """Bytes of one HTTPS document. Implementations live in adapters; tests pass a dict."""

    def get_text(self, url: str) -> str: ...


class SourceAdapter(Protocol):
    @property
    def source_id(self) -> CatalogSourceId: ...

    def fetch(
        self,
        transport: CatalogTransport,
        *,
        today: date,
        provider_runtimes: Mapping[str, str] = MappingProxyType({}),
    ) -> tuple[CatalogCandidate, ...]: ...


def _price(value: object) -> Decimal | None:
    """Parse a finite non-negative tariff. ``None`` and blank stay unknown; zero is kept."""
    if value is None or value is False:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite() or number < 0:
        return None
    return number


def _quote(
    raw_input: object,
    raw_output: object,
    *,
    today: date,
    source: str,
    cache_read: object = None,
    cache_write: object = None,
) -> PriceQuote | None:
    inp = _price(raw_input)
    out = _price(raw_output)
    if inp is None or out is None:
        return None
    return PriceQuote(
        input_per_mtok_usd=inp,
        output_per_mtok_usd=out,
        cache_read_per_mtok_usd=_price(cache_read),
        cache_write_per_mtok_usd=_price(cache_write),
        verified_at=today,
        source=source,
    )


def _as_int(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _window(value: object, *, default: int = 128000) -> int:
    number = _as_int(value)
    if number is None or number < 1000:
        return default
    return number


def _output_limit(value: object) -> int | None:
    number = _as_int(value)
    if number is None or number < 0:
        return None
    return number


def _classes(model_id: str) -> frozenset[ModelClass]:
    lowered = model_id.lower()
    if any(token in lowered for token in ("opus", "frontier", "astra", "large")):
        return frozenset({ModelClass.FRONTIER})
    if any(token in lowered for token in ("haiku", "mini", "flash", "luna", "economy")):
        return frozenset({ModelClass.ECONOMY})
    return frozenset({ModelClass.IMPLEMENTATION})


def _roles(classes: frozenset[ModelClass]) -> frozenset[RoleId]:
    if ModelClass.ECONOMY in classes:
        return frozenset({RoleId.SCOUT, RoleId.RESEARCHER, RoleId.REGISTRAR})
    if ModelClass.FRONTIER in classes:
        return frozenset({RoleId.EXECUTOR, RoleId.REVIEWER, RoleId.ADVISOR})
    return frozenset({RoleId.EXECUTOR, RoleId.REVIEWER, RoleId.TRIAGER})


def _loads(text: str, url: str) -> object:
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE,
            "catalog source returned invalid JSON",
            details={"url": url, "reason": "invalid_json"},
        ) from exc


def _mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return cast("Mapping[str, object]", value)
    return None


def _runtime_for(provider: str, mapping: Mapping[str, str]) -> str | None:
    return mapping.get(provider.strip().lower().replace(" ", ""))


def _candidate(  # noqa: PLR0913 -- one normalized row; each field is a catalog column
    *,
    source_id: CatalogSourceId,
    runtime_id: str,
    model_id: str,
    display_name: str,
    window: int,
    today: date,
    source: str,
    pricing: PriceQuote | None,
    provider_model_id: str | None = None,
    max_output: int | None = None,
    trust: CandidateTrust = CandidateTrust.EXTERNAL,
    notes: str = "",
    provider_runtimes: Mapping[str, str] = MappingProxyType({}),
) -> CatalogCandidate | None:
    resolved = _runtime_for(runtime_id, provider_runtimes) or (
        runtime_id if runtime_id in provider_runtimes.values() else None
    )
    if resolved is None or not model_id or "\x00" in model_id:
        return None
    classes = _classes(model_id)
    return CatalogCandidate(
        source_id=source_id,
        runtime_id=resolved,
        model_id=model_id,
        provider_model_id=provider_model_id or model_id,
        display_name=display_name or model_id,
        context_window_tokens=window,
        max_output_tokens=max_output,
        classes=classes,
        suited_roles=_roles(classes),
        status=ModelStatus.UNVERIFIED,
        verified_at=today,
        source=source,
        pricing=pricing,
        notes=notes,
        trust=trust,
    )


@dataclass(frozen=True, slots=True)
class ModelsDevSource:
    """``models.dev`` api.json: ``{provider: {models: {id: {...}}}}``."""

    source_id: CatalogSourceId = CatalogSourceId.MODELS_DEV
    url: str = "https://models.dev/api.json"

    def fetch(
        self,
        transport: CatalogTransport,
        *,
        today: date,
        provider_runtimes: Mapping[str, str] = MappingProxyType({}),
    ) -> tuple[CatalogCandidate, ...]:
        document = _mapping(_loads(transport.get_text(self.url), self.url))
        if document is None:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "models.dev document must be an object")
        found: list[CatalogCandidate] = []
        for provider, body in document.items():
            runtime = _runtime_for(str(provider), provider_runtimes)
            section = _mapping(body)
            if runtime is None or section is None:
                continue
            models = _mapping(section.get("models")) or {}
            for model_id, raw in models.items():
                row = _mapping(raw) or {}
                cost = _mapping(row.get("cost")) or {}
                quote = _quote(
                    cost.get("input"),
                    cost.get("output"),
                    today=today,
                    source=self.url,
                    cache_read=cost.get("cache_read"),
                    cache_write=cost.get("cache_write"),
                )
                limit = _mapping(row.get("limit")) or {}
                candidate = _candidate(
                    source_id=self.source_id,
                    runtime_id=runtime,
                    model_id=str(model_id),
                    display_name=str(row.get("name") or model_id),
                    window=_window(limit.get("context")),
                    max_output=_output_limit(limit.get("output")),
                    today=today,
                    source=self.url,
                    pricing=quote,
                    provider_runtimes=provider_runtimes,
                )
                if candidate is not None:
                    found.append(candidate)
        return tuple(found)


def _openrouter_price(model: Mapping[str, object], key: str) -> object:
    pricing = _mapping(model.get("pricing")) or {}
    # OpenRouter quotes per-token USD. Catalog tariffs are USD per million tokens.
    raw = pricing.get(key)
    number = _price(raw)
    if number is None:
        return None
    return number * Decimal(1_000_000)


@dataclass(frozen=True, slots=True)
class OpenRouterSource:
    """OpenRouter ``/models`` plus ``/models/{id}/endpoints``.

    The model list supplies identity and context. Endpoint pricing overrides the list price when
    the endpoint document names the same model. A model with no numeric tariff stays unpriced.
    """

    source_id: CatalogSourceId = CatalogSourceId.OPENROUTER
    models_url: str = "https://openrouter.ai/api/v1/models"
    endpoints_template: str = "https://openrouter.ai/api/v1/models/{id}/endpoints"

    def fetch(
        self,
        transport: CatalogTransport,
        *,
        today: date,
        provider_runtimes: Mapping[str, str] = MappingProxyType({}),
    ) -> tuple[CatalogCandidate, ...]:
        document = _mapping(_loads(transport.get_text(self.models_url), self.models_url))
        if document is None:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "OpenRouter models document must be an object")
        rows = document.get("data")
        if not isinstance(rows, list):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "OpenRouter models data must be an array")
        found: list[CatalogCandidate] = []
        for item in cast("list[object]", rows):
            model = _mapping(item)
            if model is None:
                continue
            model_id = str(model.get("id") or "")
            provider, _, name = model_id.partition("/")
            runtime = _runtime_for(provider, provider_runtimes)
            if runtime is None or not name:
                continue
            quote = self._endpoint_quote(transport, model_id, today) or _quote(
                _openrouter_price(model, "prompt"),
                _openrouter_price(model, "completion"),
                today=today,
                source=self.models_url,
            )
            top = _mapping(model.get("top_provider")) or {}
            candidate = _candidate(
                source_id=self.source_id,
                runtime_id=runtime,
                model_id=name,
                provider_model_id=model_id,
                display_name=str(model.get("name") or name),
                window=_window(model.get("context_length") or top.get("context_length")),
                max_output=_output_limit(top.get("max_completion_tokens")),
                today=today,
                source=self.models_url,
                pricing=quote,
                provider_runtimes=provider_runtimes,
            )
            if candidate is not None:
                found.append(candidate)
        return tuple(found)

    def _endpoint_quote(self, transport: CatalogTransport, model_id: str, today: date) -> PriceQuote | None:
        url = self.endpoints_template.format(id=model_id)
        try:
            payload = _mapping(_loads(transport.get_text(url), url))
        except BackendUnavailable:
            return None
        if payload is None:
            return None
        data = _mapping(payload.get("data")) or payload
        endpoints = data.get("endpoints")
        if not isinstance(endpoints, list) or not endpoints:
            return None
        first = _mapping(cast("list[object]", endpoints)[0]) or {}
        pricing = _mapping(first.get("pricing")) or {}
        prompt = _price(pricing.get("prompt"))
        completion = _price(pricing.get("completion"))
        if prompt is None or completion is None:
            return None
        return PriceQuote(
            input_per_mtok_usd=prompt * Decimal(1_000_000),
            output_per_mtok_usd=completion * Decimal(1_000_000),
            verified_at=today,
            source=url,
        )


@dataclass(frozen=True, slots=True)
class V1ModelsSource:
    """OpenAI-compatible model list. Its host supplies the provider slug unless a runtime is configured."""

    source_id: CatalogSourceId = CatalogSourceId.V1_MODELS
    url: str = "https://api.openai.com/v1/models"
    runtime_id: str | None = None

    def fetch(
        self,
        transport: CatalogTransport,
        *,
        today: date,
        provider_runtimes: Mapping[str, str] = MappingProxyType({}),
    ) -> tuple[CatalogCandidate, ...]:
        document = _mapping(_loads(transport.get_text(self.url), self.url))
        if document is None:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "/v1/models document must be an object")
        rows = document.get("data")
        if not isinstance(rows, list):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "/v1/models data must be an array")
        hostname = urlsplit(self.url).hostname or ""
        runtime_id = self.runtime_id or hostname.removeprefix("api.").partition(".")[0]
        found: list[CatalogCandidate] = []
        for item in cast("list[object]", rows):
            model = _mapping(item)
            if model is None:
                continue
            model_id = str(model.get("id") or "")
            if not model_id:
                continue
            candidate = _candidate(
                source_id=self.source_id,
                runtime_id=runtime_id,
                model_id=model_id,
                display_name=model_id,
                window=_window(model.get("context_window")),
                today=today,
                source=self.url,
                pricing=None,
                notes="Listed by /v1/models; no tariff in the document.",
                provider_runtimes=provider_runtimes,
            )
            if candidate is not None:
                found.append(candidate)
        return tuple(found)


@dataclass(frozen=True, slots=True)
class FallbackGeneralizationsSource:
    """Offline generalizations used when a provider inventory is unreachable.

    The rows are explicit external proposals with no tariff. They never count as operator-trusted.
    """

    source_id: CatalogSourceId = CatalogSourceId.FALLBACK_GENERALIZATIONS

    def fetch(
        self,
        transport: CatalogTransport,
        *,
        today: date,
        provider_runtimes: Mapping[str, str] = MappingProxyType({}),
    ) -> tuple[CatalogCandidate, ...]:
        del transport
        specs = tuple(
            (runtime_id, f"{runtime_id}-general", f"{runtime_id} (generalized)", ModelClass.ECONOMY)
            for runtime_id in sorted(set(provider_runtimes.values()))
        )
        rows: list[CatalogCandidate] = []
        for runtime_id, model_id, display_name, model_class in specs:
            rows.append(
                CatalogCandidate(
                    source_id=self.source_id,
                    runtime_id=runtime_id,
                    model_id=model_id,
                    provider_model_id=model_id,
                    display_name=display_name,
                    context_window_tokens=128000,
                    classes=frozenset({model_class}),
                    suited_roles=_roles(frozenset({model_class})),
                    status=ModelStatus.UNVERIFIED,
                    verified_at=today,
                    source="fallback_generalizations",
                    pricing=None,
                    notes="Generalized fallback. Tariff unknown; not activated.",
                    trust=CandidateTrust.EXTERNAL,
                )
            )
        return tuple(rows)


def default_adapters() -> tuple[SourceAdapter, ...]:
    """One adapter per source id, in fetch order."""
    adapters: tuple[SourceAdapter, ...] = (
        ModelsDevSource(),
        OpenRouterSource(),
        V1ModelsSource(),
        FallbackGeneralizationsSource(),
    )
    if tuple(item.source_id for item in adapters) != SOURCE_IDS:
        raise RuntimeError("catalog source adapters drifted from SOURCE_IDS")
    return adapters
