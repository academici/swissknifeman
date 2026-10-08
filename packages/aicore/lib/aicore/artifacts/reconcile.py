"""Provider-neutral observe → diff → apply → readback orchestration.

The shared layer owns ordering and refusal rules only.  Package adapters retain
their renderer, artifact-lock and target-write semantics; therefore a provider
can never infer canonical intent from another provider's rendered output.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Callable, Protocol

from .values import ProviderId


class ReconcileState(str, Enum):
    CLEAN = "clean"
    DRIFTED = "drifted"
    REFUSED = "refused"
    APPLIED = "applied"
    READBACK_FAILED = "readback-failed"


@dataclass(frozen=True, order=True)
class ReconcileDiagnostic:
    code: str
    provider_id: ProviderId
    target_id: str


@dataclass(frozen=True)
class Observation:
    """A redacted, value-free provider-owned observation."""

    provider_id: ProviderId
    target_id: str
    identity: str
    state: ReconcileState
    diagnostics: tuple[ReconcileDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise TypeError("provider_id must be ProviderId")
        if not isinstance(self.target_id, str) or not self.target_id:
            raise ValueError("target_id is required")
        if not isinstance(self.identity, str) or not self.identity:
            raise ValueError("identity is required")
        if not isinstance(self.state, ReconcileState):
            raise TypeError("state must be ReconcileState")
        if not isinstance(self.diagnostics, tuple) or not all(
            isinstance(item, ReconcileDiagnostic) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be tuple[ReconcileDiagnostic, ...]")
        if any(item.provider_id is not self.provider_id or item.target_id != self.target_id
               for item in self.diagnostics):
            raise ValueError("diagnostics must belong to the observed target")
        object.__setattr__(self, "diagnostics", tuple(sorted(set(self.diagnostics))))


@dataclass(frozen=True)
class ReconcilePlan:
    """An immutable no-write plan bound to one desired snapshot identity."""

    provider_id: ProviderId
    target_id: str
    desired_identity: str
    observed_identity: str
    state: ReconcileState
    diagnostics: tuple[ReconcileDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.provider_id, ProviderId):
            raise TypeError("provider_id must be ProviderId")
        if not all(isinstance(value, str) and value for value in (
            self.target_id, self.desired_identity, self.observed_identity
        )):
            raise ValueError("target and identities are required")
        if self.state not in (ReconcileState.CLEAN, ReconcileState.DRIFTED,
                              ReconcileState.REFUSED):
            raise ValueError("plan state must be clean, drifted, or refused")
        if not isinstance(self.diagnostics, tuple) or not all(
            isinstance(item, ReconcileDiagnostic) for item in self.diagnostics
        ):
            raise TypeError("diagnostics must be tuple[ReconcileDiagnostic, ...]")
        if any(item.provider_id is not self.provider_id or item.target_id != self.target_id
               for item in self.diagnostics):
            raise ValueError("diagnostics must belong to the planned target")
        object.__setattr__(self, "diagnostics", tuple(sorted(set(self.diagnostics))))

    @property
    def can_apply(self) -> bool:
        return self.state is ReconcileState.DRIFTED and not self.diagnostics


@dataclass(frozen=True)
class ReconcileResult:
    plan: ReconcilePlan
    state: ReconcileState
    readback: Observation | None


class ProviderReconciler(Protocol):
    """A package-owned adapter for exactly one provider and target set."""

    provider_id: ProviderId

    def observe(self, target_id: str) -> Observation: ...

    def apply(self, plan: ReconcilePlan) -> None: ...


def plan_reconciliation(*, provider_id: ProviderId, target_id: str,
                        desired_identity: str, observe: Callable[[str], Observation]) -> ReconcilePlan:
    """Observe and classify without writing a provider target."""
    if not isinstance(provider_id, ProviderId):
        raise TypeError("provider_id must be ProviderId")
    if not isinstance(target_id, str) or not target_id or not isinstance(desired_identity, str) or not desired_identity:
        raise ValueError("target_id and desired_identity are required")
    observed = observe(target_id)
    if not isinstance(observed, Observation):
        raise TypeError("observe must return Observation")
    if observed.provider_id is not provider_id or observed.target_id != target_id:
        return ReconcilePlan(provider_id, target_id, desired_identity, "unavailable", ReconcileState.REFUSED,
                             (ReconcileDiagnostic("RECONCILE_CROSS_PROVIDER_OBSERVATION", provider_id, target_id),))
    if observed.diagnostics or observed.state is ReconcileState.REFUSED:
        return ReconcilePlan(provider_id, target_id, desired_identity, observed.identity, ReconcileState.REFUSED,
                             observed.diagnostics or (ReconcileDiagnostic("RECONCILE_OBSERVATION_REFUSED", provider_id, target_id),))
    state = ReconcileState.CLEAN if observed.identity == desired_identity else ReconcileState.DRIFTED
    return ReconcilePlan(provider_id, target_id, desired_identity, observed.identity, state)


def apply_reconciliation(plan: ReconcilePlan, *, reconciler: ProviderReconciler) -> ReconcileResult:
    """Apply a preflighted plan and require a fresh provider-owned readback."""
    if not isinstance(plan, ReconcilePlan):
        raise TypeError("plan must be ReconcilePlan")
    if reconciler.provider_id is not plan.provider_id:
        raise ValueError("RECONCILE_CROSS_PROVIDER_APPLY")
    if not plan.can_apply:
        return ReconcileResult(plan, plan.state, None)
    reconciler.apply(plan)
    readback = reconciler.observe(plan.target_id)
    if readback.provider_id is not plan.provider_id or readback.target_id != plan.target_id:
        return ReconcileResult(plan, ReconcileState.READBACK_FAILED, None)
    if readback.diagnostics or readback.identity != plan.desired_identity:
        return ReconcileResult(plan, ReconcileState.READBACK_FAILED, readback)
    return ReconcileResult(plan, ReconcileState.APPLIED, readback)
