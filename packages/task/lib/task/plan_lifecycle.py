"""Advisory impact selection, not an execution engine or admission gate.

Mechanical operations and their evidence remain owned by the existing modules.
"""
from __future__ import annotations

from dataclasses import dataclass


HARD_RISKS = frozenset((
    "security-auth", "destructive-migration", "irreversible-external",
    "payment-accounting", "concurrency-shared-state", "public-api-schema",
    "low-confidence-impact",
))


@dataclass(frozen=True)
class LifecycleInput:
    risks: frozenset[str] = frozenset()
    bounded_integration: bool = False
    foreign_baseline_intersects: bool = False
    route_changed: bool = False
    changed_projections: tuple[str, ...] = ()
    audit: bool = False
    audit_product_finding: bool = False
    ownership_boundary: bool = False
    session_boundary: bool = False
    release_or_authority: bool = False


@dataclass(frozen=True)
class LifecycleSelection:
    validation: tuple[str, ...]
    review: str
    audit_action: str
    route_evidence: str
    projections: tuple[str, ...]
    commits: int
    context: str
    semantic_next: str
    foreign_baseline: str


def select(data: LifecycleInput) -> LifecycleSelection:
    """Select the cheapest safe normal path from declared, typed impact facts."""
    if not isinstance(data, LifecycleInput):
        raise ValueError("нужен LifecycleInput с явно оценённым воздействием")
    if not isinstance(data.risks, frozenset) or not all(isinstance(risk, str) for risk in data.risks):
        raise ValueError("risks: нужен frozenset имён рисков")
    unknown = data.risks - HARD_RISKS
    if unknown:
        raise ValueError(f"неизвестный риск: {sorted(unknown)}; уточните воздействие")
    for name in ("bounded_integration", "foreign_baseline_intersects", "route_changed",
                 "audit", "audit_product_finding", "ownership_boundary", "session_boundary",
                 "release_or_authority"):
        if not isinstance(getattr(data, name), bool):
            raise ValueError(f"{name}: нужна явная boolean оценка")
    if data.audit_product_finding and not data.audit:
        raise ValueError("audit_product_finding требует audit=True")
    hard = bool(data.risks & HARD_RISKS) or data.release_or_authority
    if hard:
        validation = ("focused", "affected-package", "integration")
        review = "independent"
    elif data.bounded_integration:
        validation = ("focused", "affected-package")
        review = "light"
    else:
        validation = ("focused",)
        review = "none"

    if data.audit:
        audit_action = "return-owning-continuation" if data.audit_product_finding else "read-only"
    else:
        audit_action = "not-requested"
    return LifecycleSelection(
        validation=validation,
        review=review,
        audit_action=audit_action,
        route_evidence="recapture" if data.route_changed else "reuse",
        projections=tuple(dict.fromkeys(data.changed_projections)),
        commits=2 if data.ownership_boundary or data.session_boundary else 1,
        context="cold-start-root" if data.session_boundary else "continue-root",
        semantic_next="waiting" if data.release_or_authority else "exec-items",
        foreign_baseline=("gating" if data.foreign_baseline_intersects else "visible-non-gating"),
    )
