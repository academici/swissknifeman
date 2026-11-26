"""Validate explicit model offers and resolve current worker and host routes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, cast

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import HostId, ScopeId, WorkerId
from skm.kernel.scopes import ScopeKind, ScopeRef
from skm.modules.access import public as access
from skm.modules.runtimes.application.queries.list_models import resolve_catalog
from skm.modules.runtimes.domain.capability import Capability
from skm.modules.runtimes.domain.catalog import ModelStatus
from skm.modules.runtimes.domain.catalog_records import (
    WORKER_OFFER_TTL,
    HostModelAvailability,
    WorkerModelSnapshot,
)
from skm.modules.runtimes.domain.classes import Effort
from skm.modules.runtimes.domain.installation import AuthState
from skm.modules.runtimes.domain.routing import HostRouting, RouteKey
from skm.modules.runtimes.ports import (
    CapabilityCatalog,
    HostModelAvailabilityRepository,
    ModelCatalogRepository,
)
from skm.platform.config import ConfigLoader, ConfigStore, PackConfigSource, ScopeTree

if TYPE_CHECKING:
    from datetime import datetime
    from uuid import UUID

    from skm.application_bus.context import CommandContext
    from skm.kernel.ports_uow import UnitOfWork
    from skm.modules.runtimes.domain.installation import RuntimeInstallation
    from skm.modules.runtimes.generated.commands import RecordHostRuntimes
    from skm.platform.config import EffectiveConfig

_MAX_OBSERVATION_AGE = timedelta(minutes=2)


@dataclass(frozen=True, slots=True)
class _HostPolicy:
    runtimes: frozenset[str] | None
    models: dict[str, list[str]]
    substitutions: tuple[tuple[RouteKey, RouteKey], ...]

    def enables(self, runtime_id: str, model_id: str) -> bool:
        return (self.runtimes is None or runtime_id in self.runtimes) and (
            runtime_id not in self.models or model_id in self.models[runtime_id]
        )


def _policy(config: EffectiveConfig) -> _HostPolicy:
    def key(raw: dict[str, str]) -> RouteKey:
        return RouteKey(raw["runtime_id"], raw["model_id"], Effort(raw["effort"]))

    runtimes = cast("list[str] | None", config.get("runtimes.host.enabled_runtimes"))
    return _HostPolicy(
        None if runtimes is None else frozenset(runtimes),
        cast("dict[str, list[str]]", config.get("runtimes.host.enabled_models")),
        tuple(
            (key(item["requested"]), key(item["selected"]))
            for item in cast(
                "list[dict[str, dict[str, str]]]", config.get("runtimes.host.route_substitutions")
            )
        ),
    )


def current_worker_snapshot(
    uow: UnitOfWork, worker_id: WorkerId, *, as_of: datetime
) -> WorkerModelSnapshot | None:
    snapshot = uow.repo(HostModelAvailabilityRepository).worker_snapshot(worker_id)
    if snapshot is None or not snapshot.fresh_at(as_of):
        return None
    if not access.worker_credential_current(uow, snapshot.publisher_token_id, worker_id, now=as_of):
        return None
    return snapshot


def host_routing(
    uow: UnitOfWork,
    config: EffectiveConfig,
    host_id: HostId,
    *,
    as_of: datetime,
    worker_runtimes: frozenset[str] | None,
    worker_snapshot: WorkerModelSnapshot | None = None,
    worker_id: WorkerId | None = None,
) -> HostRouting:
    host_config = ConfigLoader(config.registry, uow.repo(PackConfigSource)).effective_host(
        uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.HOST, ScopeId(host_id))
    )
    policy = _policy(host_config)
    if worker_id is None:
        observations = uow.repo(HostModelAvailabilityRepository).list_fresh(host_id, as_of=as_of)
    else:
        observations = () if worker_snapshot is None else worker_snapshot.offers
    return HostRouting(
        frozenset(
            RouteKey(offer.runtime_id, offer.model_id, offer.effort)
            for offer in observations
            if offer.host_id == host_id
            and offer.observed_at <= as_of < offer.expires_at
            and (worker_runtimes is None or offer.runtime_id in worker_runtimes)
            and policy.enables(offer.runtime_id, offer.model_id)
        ),
        policy.substitutions,
    )


def _offer_rows(
    cmd: RecordHostRuntimes, *, now: datetime, observed_at: datetime | None = None
) -> dict[RouteKey, HostModelAvailability]:
    by_route: dict[RouteKey, HostModelAvailability] = {}
    for item in cmd.model_offers or ():
        route = RouteKey(item.runtime_id, item.model_id, Effort(item.effort))
        try:
            offer = HostModelAvailability(
                HostId(cmd.host_id),
                route.runtime_id,
                route.model_id,
                route.effort,
                item.observed_at,
                item.expires_at,
            )
        except ValueError as exc:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Model offer times must be UTC") from exc
        if (
            route in by_route
            or not now - _MAX_OBSERVATION_AGE <= offer.observed_at <= now
            or not now < offer.expires_at <= offer.observed_at + WORKER_OFFER_TTL
            or (observed_at is not None and offer.observed_at != observed_at)
        ):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid time or duplicate model offer")
        by_route[route] = offer
    return by_route


def record_host_offers(
    uow: UnitOfWork,
    cmd: RecordHostRuntimes,
    config: EffectiveConfig,
    installations: list[RuntimeInstallation],
    now: datetime,
) -> None:
    """Retain explicit host observations for non-worker route previews."""
    rows = _offer_rows(cmd, now=now)
    if not rows:
        return
    policy = _policy(config)
    installed = {
        item.runtime_id
        for item in installations
        if item.auth_state not in {AuthState.MISSING, AuthState.EXPIRED}
    }
    catalog = uow.repo(ModelCatalogRepository)
    allowed = {
        (runtime_id, item.model_id)
        for runtime_id in installed
        for item in catalog.list_offerings(runtime_id)
        if item.status is not ModelStatus.DEPRECATED and policy.enables(runtime_id, item.model_id)
    }
    repository = uow.repo(HostModelAvailabilityRepository)
    for key, row in rows.items():
        if (key.runtime_id, key.model_id) not in allowed:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID, "Host offer has no enabled installed catalog model"
            )
        repository.upsert(row)


def record_worker_snapshot(
    uow: UnitOfWork,
    ctx: CommandContext,
    cmd: RecordHostRuntimes,
    installations: list[RuntimeInstallation],
    *,
    worker_id: WorkerId,
    worker_runtimes: frozenset[str],
    publisher_id: UUID,
    now: datetime,
) -> None:
    observed_at = cmd.model_offers_observed_at
    if observed_at is None or cmd.model_offers is None or not cmd.refresh_model_offers:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "Worker publication requires a complete model snapshot"
        )
    if observed_at.utcoffset() != timedelta(0) or not now - _MAX_OBSERVATION_AGE <= observed_at <= now:
        raise ValidationFailed(
            ErrorCode.SCHEMA_INVALID, "Worker snapshot observation is stale or in the future"
        )
    if not access.worker_credential_current(uow, publisher_id, worker_id, now=now, lock=True):
        raise Forbidden(ErrorCode.FORBIDDEN, "Worker credential cannot publish current offers")

    rows = _offer_rows(cmd, now=now, observed_at=observed_at)
    eligible = _eligible_worker_offers(uow, ctx, rows, installations, worker_runtimes, now)
    snapshot = WorkerModelSnapshot(
        worker_id,
        publisher_id,
        observed_at,
        observed_at + WORKER_OFFER_TTL,
        tuple(item for item in installations if item.runtime_id in worker_runtimes),
        tuple(eligible),
    )
    if not uow.repo(HostModelAvailabilityRepository).replace_worker_snapshot(snapshot):
        raise PreconditionFailed(ErrorCode.INVALID_TRANSITION, "Worker model snapshot is out of order")


def _eligible_worker_offers(
    uow: UnitOfWork,
    ctx: CommandContext,
    rows: dict[RouteKey, HostModelAvailability],
    installations: list[RuntimeInstallation],
    worker_runtimes: frozenset[str],
    now: datetime,
) -> list[HostModelAvailability]:
    if not rows:
        return []
    config = ConfigLoader(ctx.config.registry, uow.repo(PackConfigSource)).effective(
        uow.repo(ConfigStore), uow.repo(ScopeTree), None
    )
    catalog = resolve_catalog(uow, config=config)
    policy = _policy(ctx.config)
    caps = ctx.gateways.get(CapabilityCatalog)
    installed = {
        item.runtime_id
        for item in installations
        if item.runtime_id in worker_runtimes
        and item.version is not None
        and item.auth_state is AuthState.OK
        and now - _MAX_OBSERVATION_AGE <= item.detected_at <= now
        and all(
            caps.static(item.runtime_id).supports(capability)
            for capability in (Capability.HEADLESS_EXECUTION, Capability.EFFORT_CONTROL)
        )
    }
    accepted: list[HostModelAvailability] = []
    allowed_runtimes = frozenset(cast("list[str]", config.get("runtimes.allowed")))
    for key, observation in rows.items():
        model = catalog.model(key.runtime_id, key.model_id)
        entry = catalog.runtimes.get(key.runtime_id)
        if (
            key.runtime_id in installed
            and key.runtime_id in allowed_runtimes
            and policy.enables(key.runtime_id, key.model_id)
            and model is not None
            and model.status is not ModelStatus.DEPRECATED
            and entry is not None
            and key.effort in entry.effort_selectors
        ):
            accepted.append(observation)
    return accepted
