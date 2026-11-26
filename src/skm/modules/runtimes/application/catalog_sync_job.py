"""``ModelCatalogSyncJob``: fetch catalog candidates, then stage them.

Network runs in ``fetch`` through the injected transport, before any unit of work exists.
``stage`` only applies the trust policy. It does not write offerings and does not publish a snapshot.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from types import MappingProxyType

from skm.kernel.errors import SkmError
from skm.modules.runtimes.application.catalog_sources import (
    CatalogTransport,
    SourceAdapter,
    default_adapters,
)
from skm.modules.runtimes.domain.catalog_sync import (
    CatalogCandidate,
    CatalogSourceId,
    CatalogSyncReport,
    stage_candidates,
)

__all__ = ["ModelCatalogSyncJob"]


@dataclass(slots=True)
class ModelCatalogSyncJob:
    """One sync. Adapters and transport are injected so tests stay offline."""

    transport: CatalogTransport
    today: date
    adapters: tuple[SourceAdapter, ...] = field(default_factory=default_adapters)
    provider_runtimes: Mapping[str, str] = field(default_factory=lambda: MappingProxyType({}))
    _fetched: tuple[CatalogCandidate, ...] = field(default=(), init=False)
    _errors: tuple[tuple[CatalogSourceId, str], ...] = field(default=(), init=False)

    def fetch(self) -> tuple[CatalogCandidate, ...]:
        """Read every source. A failing source is recorded and does not abort the others."""
        found: list[CatalogCandidate] = []
        errors: list[tuple[CatalogSourceId, str]] = []
        for adapter in self.adapters:
            try:
                found.extend(
                    adapter.fetch(self.transport, today=self.today, provider_runtimes=self.provider_runtimes)
                )
            except SkmError as exc:
                errors.append((adapter.source_id, exc.message))
        self._fetched = tuple(found)
        self._errors = tuple(errors)
        return self._fetched

    def stage(self) -> CatalogSyncReport:
        """Stage the rows already fetched. External rows stay inactive."""
        return CatalogSyncReport(stage_candidates(self._fetched), self._errors)

    def run(self) -> CatalogSyncReport:
        """Fetch outside a unit of work, then stage. No database call happens here."""
        self.fetch()
        return self.stage()
