"""``runtimes.get_capabilities`` (runtimes §8) and effective capability resolution (§13)."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Literal

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.runtimes.domain.capability import (
    ENFORCING_CAPABILITIES,
    Capability,
    CapabilityRecord,
    RuntimeCapabilities,
    VerificationContext,
    effective_capabilities,
    verification_context_key,
)
from skm.modules.runtimes.domain.ids import RuntimeId
from skm.modules.runtimes.generated.queries import GetCapabilities
from skm.modules.runtimes.generated.views import Capability as ViewCapability
from skm.modules.runtimes.generated.views import (
    RuntimeCapabilitiesView,
    RuntimeCapabilitiesViewRecordsItem,
    RuntimeCapabilitiesViewRecordsItemVerificationContextVariant1,
)
from skm.modules.runtimes.ports import CapabilityCatalog, CapabilityVerificationRepository

if TYPE_CHECKING:
    from skm.kernel.gateways import Gateways
    from skm.platform.config import EffectiveConfig

__all__ = ["SPEC", "handle", "resolve_capabilities"]


def resolve_capabilities(
    uow: UnitOfWork,
    gateways: Gateways,
    runtime_id: RuntimeId,
    runtime_version: str | None = None,
    *,
    verification_context: VerificationContext | None = None,
    config: EffectiveConfig | None = None,
    today: date,
) -> RuntimeCapabilities:
    """Merge static adapter capabilities with latest recorded verifications (§4.3, §13)."""
    static = gateways.get(CapabilityCatalog).static(runtime_id)
    vkey = None if verification_context is None else verification_context_key(verification_context)
    verified = uow.repo(CapabilityVerificationRepository).latest(runtime_id, runtime_version, vkey)

    raw_days = None if config is None else config.get("runtimes.capabilities.stale_after_days")
    stale_after_days = raw_days if type(raw_days) is int and raw_days >= 1 else 30
    stale_policy: Literal["warn", "refuse"] = (
        "refuse"
        if config is not None and config.get("runtimes.capabilities.stale_policy") == "refuse"
        else "warn"
    )
    return effective_capabilities(
        static,
        verified,
        host_version=runtime_version,
        verification_context=verification_context,
        now=today,
        stale_after_days=stale_after_days,
        stale_policy=stale_policy,
    )


def _context_view(
    ctx: VerificationContext | None,
) -> RuntimeCapabilitiesViewRecordsItemVerificationContextVariant1 | None:
    if ctx is None:
        return None
    return RuntimeCapabilitiesViewRecordsItemVerificationContextVariant1(
        host_id=ctx.host_id,
        binary_sha256=ctx.binary_sha256,
        os=ctx.os,
        kernel=ctx.kernel,
        adapter_version=ctx.adapter_version,
        isolation_profile=str(ctx.isolation_profile),
        launch_config_digest=ctx.launch_config_digest,
    )


def handle(query: GetCapabilities, ctx: QueryContext, uow: UnitOfWork) -> RuntimeCapabilitiesView:
    static = ctx.gateways.get(CapabilityCatalog).static(query.runtime_id)
    verified = uow.repo(CapabilityVerificationRepository).latest(
        query.runtime_id, query.runtime_version, None
    )
    verified_by_cap: dict[Capability, CapabilityRecord] = {rec.capability: rec for rec in verified}

    raw_days = ctx.config.get("runtimes.capabilities.stale_after_days")
    stale_after_days = raw_days if type(raw_days) is int and raw_days >= 1 else 30
    stale_policy: Literal["warn", "refuse"] = (
        "refuse" if ctx.config.get("runtimes.capabilities.stale_policy") == "refuse" else "warn"
    )
    today = ctx.clock.now().date()

    records: list[RuntimeCapabilitiesViewRecordsItem] = []
    for cap in Capability:
        ver_rec = verified_by_cap.get(cap)
        static_rec = static.records.get(cap)
        if cap not in ENFORCING_CAPABILITIES and ver_rec is None and static_rec is None:
            continue

        eval_ctx = ver_rec.verification_context if ver_rec is not None else None
        if query.runtime_version is not None:
            eval_version: str | None = query.runtime_version
        elif cap in ENFORCING_CAPABILITIES and ver_rec is not None:
            eval_version = ver_rec.tested_runtime_version
        else:
            eval_version = None
        eff = effective_capabilities(
            static,
            (ver_rec,) if ver_rec is not None else (),
            host_version=eval_version,
            verification_context=eval_ctx,
            now=today,
            stale_after_days=stale_after_days,
            stale_policy=stale_policy,
        )
        eff_rec = eff.records[cap]

        is_verified_source = False
        if ver_rec is not None:
            if cap in ENFORCING_CAPABILITIES:
                is_verified_source = ver_rec.verification_context is not None
            else:
                is_verified_source = (
                    static_rec is None
                    or static_rec.last_verified_at is None
                    or (
                        ver_rec.last_verified_at is not None
                        and ver_rec.last_verified_at >= static_rec.last_verified_at
                    )
                )

        records.append(
            RuntimeCapabilitiesViewRecordsItem(
                capability=ViewCapability(cap.value),
                status=eff_rec.status.value,
                evidence=eff_rec.evidence,
                tested_runtime_version=eff_rec.tested_runtime_version,
                limitations=eff_rec.limitations,
                last_verified_at=eff_rec.last_verified_at,
                source="verified" if is_verified_source else "static",
                verification_context=_context_view(eff_rec.verification_context),
            )
        )

    return RuntimeCapabilitiesView(
        runtime_id=static.runtime_id,
        adapter_version=static.adapter_version,
        records=tuple(records),
    )


SPEC = QuerySpec(
    name="runtimes.get_capabilities",
    dto=GetCapabilities,
    result=RuntimeCapabilitiesView,
    permission="runtime.read",
    scope_of=None,
    handler=handle,
)
