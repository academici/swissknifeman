"""Staged catalog candidates and the trust rule that keeps them inactive.

External inventory is a proposal. A missing tariff stays ``None`` (unknown), never zero.
Activation is a separate operator decision; this module has no IO, clock or environment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Final

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed

from .catalog import ModelStatus, Pricing
from .classes import ModelClass, RoleId
from .ids import ModelId, RuntimeId, is_runtime_id

__all__ = [
    "ACTIVATION_PACK_SLUG",
    "CATALOG_RESOURCE_KEY",
    "SOURCE_IDS",
    "CandidateTrust",
    "CatalogCandidate",
    "CatalogSourceId",
    "CatalogSyncReport",
    "PriceQuote",
    "StagedCandidate",
    "pricing_of",
    "render_catalog_toml",
    "stage_candidates",
]

ACTIVATION_PACK_SLUG: Final = "catalog-sync"
CATALOG_RESOURCE_KEY: Final = "synced-models"


class CatalogSourceId(StrEnum):
    """The four pluggable inventory sources. Order is the fetch order of the job."""

    MODELS_DEV = "models_dev"
    OPENROUTER = "openrouter"
    V1_MODELS = "v1_models"
    FALLBACK_GENERALIZATIONS = "fallback_generalizations"


SOURCE_IDS: Final = tuple(CatalogSourceId)


class CandidateTrust(StrEnum):
    """How a staged row may be promoted. External rows wait for explicit operator approval."""

    OPERATOR = "operator"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class PriceQuote:
    """A verified USD tariff. Absent quotes stay ``None`` on the candidate; zero is a real price."""

    input_per_mtok_usd: Decimal
    output_per_mtok_usd: Decimal
    cache_read_per_mtok_usd: Decimal | None = None
    cache_write_per_mtok_usd: Decimal | None = None
    verified_at: date | None = None
    source: str = ""

    def __post_init__(self) -> None:
        for name in ("input_per_mtok_usd", "output_per_mtok_usd"):
            _check_price(getattr(self, name), name, optional=False)
        for name in ("cache_read_per_mtok_usd", "cache_write_per_mtok_usd"):
            _check_price(getattr(self, name), name, optional=True)


def _check_price(value: object, name: str, *, optional: bool) -> None:
    if value is None and optional:
        return
    if not isinstance(value, Decimal) or not value.is_finite() or value < 0:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            f"{name} must be a finite non-negative Decimal",
            details={"field": name},
        )


@dataclass(frozen=True, slots=True)
class CatalogCandidate:
    """One normalized model row from a source adapter. ``pricing is None`` means the tariff is unknown."""

    source_id: CatalogSourceId
    runtime_id: RuntimeId
    model_id: ModelId
    provider_model_id: ModelId
    display_name: str
    context_window_tokens: int
    classes: frozenset[ModelClass]
    verified_at: date
    source: str
    max_output_tokens: int | None = None
    patterns: tuple[str, ...] = ()
    suited_roles: frozenset[RoleId] = frozenset()
    status: ModelStatus = ModelStatus.UNVERIFIED
    pricing: PriceQuote | None = None
    notes: str = ""
    trust: CandidateTrust = CandidateTrust.EXTERNAL

    def __post_init__(self) -> None:
        if not is_runtime_id(self.runtime_id):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid runtime identifier")
        if not self.model_id or "\x00" in self.model_id or not self.provider_model_id:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid model identifier")
        if self.context_window_tokens < 1000:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid offering token limits")
        if self.max_output_tokens is not None and self.max_output_tokens < 0:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid offering token limits")
        if not self.classes:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "a catalog candidate names at least one class")


@dataclass(frozen=True, slots=True)
class StagedCandidate:
    """A candidate held for review. ``active`` is true only for an operator-trusted row."""

    candidate: CatalogCandidate
    active: bool

    def __post_init__(self) -> None:
        if self.active and self.candidate.trust is not CandidateTrust.OPERATOR:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "an external catalog candidate is not activated automatically",
                details={"reason": "untrusted_external_candidate", "model_id": self.candidate.model_id},
            )


def stage_candidates(candidates: tuple[CatalogCandidate, ...]) -> tuple[StagedCandidate, ...]:
    """Apply the trust policy: operator rows may be active; every external row stays staged."""
    return tuple(
        StagedCandidate(candidate, active=candidate.trust is CandidateTrust.OPERATOR)
        for candidate in candidates
    )


@dataclass(frozen=True, slots=True)
class CatalogSyncReport:
    """What one sync observed. Staging never publishes a snapshot."""

    staged: tuple[StagedCandidate, ...]
    source_errors: tuple[tuple[CatalogSourceId, str], ...] = ()

    @property
    def active(self) -> tuple[StagedCandidate, ...]:
        return tuple(row for row in self.staged if row.active)

    @property
    def pending(self) -> tuple[StagedCandidate, ...]:
        return tuple(row for row in self.staged if not row.active)

    def approve(self, *candidates: CatalogCandidate) -> CatalogSyncReport:
        """Approve the selected pending candidates from this report for explicit activation."""
        selected = set(candidates)
        if not selected <= {row.candidate for row in self.pending}:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "approval must select pending candidates from the catalog sync report",
                details={"reason": "candidate_not_pending"},
            )
        return replace(
            self,
            staged=tuple(
                StagedCandidate(replace(row.candidate, trust=CandidateTrust.OPERATOR), active=True)
                if row.candidate in selected
                else row
                for row in self.staged
            ),
        )


def _decimal_literal(value: Decimal) -> str:
    return format(value, "f")


def _toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False).replace("\x7f", r"\u007f")


def render_catalog_toml(rows: tuple[StagedCandidate, ...], *, catalog_version: str, verified_at: date) -> str:
    """Render the active rows as one ``runtime_catalog`` document. Pending rows are omitted."""
    by_runtime: dict[RuntimeId, list[StagedCandidate]] = {}
    for row in rows:
        if row.active:
            by_runtime.setdefault(row.candidate.runtime_id, []).append(row)
    lines = [
        f"schema = {_toml_string('urn:skm:runtimes:model-catalog:v1')}",
        f"catalog_version = {_toml_string(catalog_version)}",
        "",
    ]
    for runtime_id in sorted(by_runtime):
        group = by_runtime[runtime_id]
        lines.append(f"[runtimes.{runtime_id}]")
        lines.append("class_selectors = {}")
        lines.append("effort_selectors = {}")
        lines.append(f"inventory_verified_at = {_toml_string(verified_at.isoformat())}")
        lines.append('inventory_source = "catalog-sync"')
        lines.append("")
        for row in group:
            model = row.candidate
            lines.append(f"[[runtimes.{runtime_id}.models]]")
            lines.append(f"id = {_toml_string(model.model_id)}")
            lines.append(f"display_name = {_toml_string(model.display_name)}")
            classes = ", ".join(
                _toml_string(item.value) for item in sorted(model.classes, key=lambda c: c.value)
            )
            lines.append(f"classes = [{classes}]")
            if model.suited_roles:
                roles = ", ".join(
                    _toml_string(item.value) for item in sorted(model.suited_roles, key=lambda c: c.value)
                )
                lines.append(f"suited_roles = [{roles}]")
            lines.append(f"context_window_tokens = {model.context_window_tokens}")
            if model.max_output_tokens is not None:
                lines.append(f"max_output_tokens = {model.max_output_tokens}")
            if model.patterns:
                patterns = ", ".join(_toml_string(item) for item in model.patterns)
                lines.append(f"patterns = [{patterns}]")
            lines.append(f"status = {_toml_string(model.status.value)}")
            lines.append(f"verified_at = {_toml_string(model.verified_at.isoformat())}")
            lines.append(f"source = {_toml_string(model.source)}")
            lines.append(f"notes = {_toml_string(model.notes)}")
            if model.pricing is not None:
                lines.extend(_pricing_lines(model.pricing, fallback_date=model.verified_at))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _pricing_lines(pricing: PriceQuote, *, fallback_date: date) -> list[str]:
    verified = pricing.verified_at or fallback_date
    source = pricing.source or "catalog-sync"
    parts = [
        f"input_per_mtok_usd = {_toml_string(_decimal_literal(pricing.input_per_mtok_usd))}",
        f"output_per_mtok_usd = {_toml_string(_decimal_literal(pricing.output_per_mtok_usd))}",
        'currency = "USD"',
        f"verified_at = {_toml_string(verified.isoformat())}",
        f"source = {_toml_string(source)}",
    ]
    if pricing.cache_read_per_mtok_usd is not None:
        parts.append(
            f"cache_read_per_mtok_usd = {_toml_string(_decimal_literal(pricing.cache_read_per_mtok_usd))}"
        )
    if pricing.cache_write_per_mtok_usd is not None:
        parts.append(
            f"cache_write_per_mtok_usd = {_toml_string(_decimal_literal(pricing.cache_write_per_mtok_usd))}"
        )
    return ["pricing = { " + ", ".join(parts) + " }"]


def pricing_of(quote: PriceQuote | None, *, fallback_date: date) -> Pricing | None:
    """Domain ``Pricing`` for a quote. ``None`` stays ``None`` so a missing tariff is never zero."""
    if quote is None:
        return None
    return Pricing(
        input_per_mtok_usd=quote.input_per_mtok_usd,
        output_per_mtok_usd=quote.output_per_mtok_usd,
        cache_read_per_mtok_usd=quote.cache_read_per_mtok_usd,
        cache_write_per_mtok_usd=quote.cache_write_per_mtok_usd,
        currency="USD",
        verified_at=quote.verified_at or fallback_date,
        source=quote.source or "catalog-sync",
    )
