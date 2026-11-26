"""Promote staged catalog candidates and publish one immutable runtime catalog snapshot.

The caller opens the unit of work. This module does not fetch the network. Only rows the trust
policy marked active are written and published. Pending external rows stay out of the snapshot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed, ValidationFailed
from skm.kernel.ids import ResourceVersionId
from skm.modules.extensions import public as extensions
from skm.modules.runtimes.domain.catalog_records import CanonicalModel, ModelGuideline, ProviderModelOffering
from skm.modules.runtimes.domain.catalog_sync import (
    ACTIVATION_PACK_SLUG,
    CATALOG_RESOURCE_KEY,
    CatalogSyncReport,
    pricing_of,
    render_catalog_toml,
)
from skm.modules.runtimes.ports import ModelCatalogRepository

if TYPE_CHECKING:
    from datetime import date

    from skm.kernel.clock import Clock
    from skm.kernel.id_generator import IdGenerator
    from skm.kernel.ids import PrincipalId
    from skm.kernel.ports_uow import UnitOfWork
    from skm.kernel.tokens import TokenEstimator
    from skm.modules.extensions.public import InstallPackResult
    from skm.platform.config import EffectiveConfig

__all__ = ["CATALOG_RESOURCE_KEY", "activate_staged_catalog"]


def _manifest(version: str) -> str:
    return (
        'schema = "urn:skm:extensions:pack:v1"\n'
        f'slug = "{ACTIVATION_PACK_SLUG}"\n'
        f'version = "{version}"\n'
        'title = "Activated model catalog"\n'
        'description = "Operator snapshot of staged catalog candidates."\n'
        'publisher = "skm"\n'
        'trust = "operator"\n'
        'license = "Apache-2.0"\n'
        'requires_skm = ">=0.1.0,<1"\n'
        "priority = 100\n"
    )


def activate_staged_catalog(  # noqa: PLR0913 -- caller UoW plus the publication dependencies travel together
    uow: UnitOfWork,
    report: CatalogSyncReport,
    *,
    catalog_version: str,
    installed_by: PrincipalId,
    clock: Clock,
    ids: IdGenerator,
    config: EffectiveConfig,
    estimator: TokenEstimator,
    verified_at: date | None = None,
) -> InstallPackResult:
    """Write active offerings and publish ``runtime_catalog`` through the extensions facade.

    Use ``report.approve(*candidates)`` to select pending external rows before calling this function.
    Existing ``PackPins`` keep their recorded versions through the regular pack install path.
    """
    active = report.active
    if not active:
        raise PreconditionFailed(
            ErrorCode.PRECONDITION_REQUIRED,
            "no trusted catalog candidate is staged for activation",
            details={"reason": "nothing_to_activate", "pending": len(report.pending)},
        )
    if len({(row.candidate.runtime_id, row.candidate.model_id) for row in active}) != len(active):
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID,
            "select one catalog candidate per runtime and model for activation",
            details={"reason": "duplicate_offering"},
        )
    day = verified_at or clock.now().date()
    catalog_toml = render_catalog_toml(active, catalog_version=catalog_version, verified_at=day)
    published = extensions.publish_runtime_catalog_snapshot(
        uow,
        pack_manifest=_manifest(catalog_version),
        catalog_toml=catalog_toml,
        installed_by=installed_by,
        clock=clock,
        ids=ids,
        config=config,
        estimator=estimator,
        resource_key=CATALOG_RESOURCE_KEY,
    )
    view = extensions.resolve_resource(
        uow,
        extensions.ResourceKind.RUNTIME_CATALOG,
        CATALOG_RESOURCE_KEY,
        config=config,
        pins={ACTIVATION_PACK_SLUG: extensions.PackVersionId(published.pack_version_id)},
    )
    version_id = ResourceVersionId(view.resource_version_id)
    repo = uow.repo(ModelCatalogRepository)
    for row in active:
        model = row.candidate
        repo.add_model(CanonicalModel(model.model_id))
        repo.upsert_offering(
            ProviderModelOffering(
                runtime_id=model.runtime_id,
                model_id=model.model_id,
                provider_model_id=model.provider_model_id,
                display_name=model.display_name,
                context_window_tokens=model.context_window_tokens,
                max_output_tokens=model.max_output_tokens,
                patterns=model.patterns,
                status=model.status,
                verified_at=model.verified_at,
                source=model.source,
                pricing=pricing_of(model.pricing, fallback_date=model.verified_at),
            )
        )
        repo.add_guideline(
            ModelGuideline(
                version_id,
                model.runtime_id,
                model.model_id,
                model.classes,
                model.suited_roles,
                model.notes,
            )
        )
    return published
