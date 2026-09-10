"""Transient, change-impact selection for the normal plan execution loop.

This module deliberately owns no plan carrier, status or new enum.  It only
composes decisions already owned by Task runtime modules into a small result a
command can execute and test without copying the control algorithm into prose.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import monotonic


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


def execute(data: LifecycleInput, *, executed: tuple[str, ...] = (), started_at: float | None = None) -> dict:
    """Return bounded end-to-end evidence; callers execute commands themselves."""
    selection = select(data)
    return {
        "selection": selection,
        "executed": tuple(executed),
        "reused": ("route-evidence",) if selection.route_evidence == "reuse" else (),
        "wall_time_ms": round((monotonic() - started_at) * 1000, 3) if started_at is not None else None,
    }
