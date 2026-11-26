"""Project the core pack's model inventory during built-in pack sync."""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.modules.runtimes.domain.catalog import parse_catalog_document
from skm.modules.runtimes.domain.catalog_records import CanonicalModel, ModelGuideline, ProviderModelOffering
from skm.modules.runtimes.ports import ModelCatalogRepository

if TYPE_CHECKING:
    from collections.abc import Mapping

    from skm.kernel.ids import ResourceVersionId
    from skm.kernel.json_types import JsonValue
    from skm.kernel.ports_uow import UnitOfWork

__all__ = ["seed_builtin_model_catalog"]


def seed_builtin_model_catalog(
    uow: UnitOfWork, resource_version_id: ResourceVersionId, manifest: Mapping[str, JsonValue]
) -> None:
    """Seed offerings and versioned guidelines once per core catalog resource."""
    repo = uow.repo(ModelCatalogRepository)
    projected = {(row.runtime_id, row.model_id) for row in repo.list_guidelines(resource_version_id)}
    _, runtimes = parse_catalog_document(manifest)
    for runtime_id, runtime in runtimes.items():
        for model in runtime.models:
            if (runtime_id, model.id) in projected:
                continue
            repo.add_model(CanonicalModel(model.id))
            repo.upsert_offering(
                ProviderModelOffering(
                    runtime_id=runtime_id,
                    model_id=model.id,
                    provider_model_id=model.id,
                    display_name=model.display_name,
                    context_window_tokens=model.context_window_tokens,
                    max_output_tokens=model.max_output_tokens,
                    patterns=model.patterns,
                    status=model.status,
                    verified_at=model.verified_at,
                    source=model.source,
                    pricing=model.pricing,
                )
            )
            repo.add_guideline(
                ModelGuideline(
                    resource_version_id, runtime_id, model.id, model.classes, model.suited_roles, model.notes
                )
            )
