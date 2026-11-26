"""Acceptance rules: criteria, their checks and requirements (planning §5.7, module ``acceptance``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from skm.modules.planning.domain.check_spec import CheckKind
from skm.modules.planning.domain.criterion import VerificationMode
from skm.modules.planning.domain.phase import DesignState
from skm.modules.planning.domain.requirement import Priority
from skm.modules.planning.domain.review_requirement import WaivedReview
from skm.modules.planning.domain.validation.context import Locator, ValidationSettings
from skm.modules.planning.domain.validation.findings import FindingCode, Severity, finding

if TYPE_CHECKING:
    from collections.abc import Iterator

    from skm.modules.planning.domain.check_spec import CheckSpec
    from skm.modules.planning.domain.criterion import Criterion
    from skm.modules.planning.domain.validation.context import ValidationContext
    from skm.modules.planning.domain.validation.findings import Finding


def _check_key(criterion: Criterion, ref: str) -> str:
    """The full key of a check a criterion lists: ``V<n>`` belongs to the item of the criterion's owner."""
    return ref if ":" in ref else f"{criterion.owner.split('/', 1)[0]}:{ref}"


def _checks_of(ctx: ValidationContext, criterion: Criterion) -> tuple[list[CheckSpec], bool]:
    """The checks of ``criterion`` that exist, and whether some listed check does not (``ref_unknown``)."""
    by_key = {f"{check.owner}:{check.key}": check for check in ctx.spec.checks}
    found = [by_key[key] for ref in criterion.checks if (key := _check_key(criterion, ref)) in by_key]
    return found, len(found) < len(criterion.checks)


def criterion_check_mismatch(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    for criterion in ctx.spec.criteria:
        owner = criterion.owner
        item = owner.split("/", 1)[0]
        allowed = {
            owner,
            item,
            item.split(".", 1)[0],
        }  # the owner, the item of a unit, the phase of the owner
        for n, ref in enumerate(criterion.checks):
            check = next(
                (c for c in ctx.spec.checks if f"{c.owner}:{c.key}" == _check_key(criterion, ref)), None
            )
            if check is None:
                continue
            if check.owner not in allowed:
                reason = "owner"
            elif criterion.verification_mode is VerificationMode.CHECK and check.kind is CheckKind.MANUAL:
                reason = "manual_check_in_check_mode"
            elif (
                criterion.verification_mode is VerificationMode.MANUAL and check.kind is not CheckKind.MANUAL
            ):
                reason = "automatic_check_in_manual_mode"
            else:
                continue
            yield finding(
                FindingCode.CRITERION_CHECK_MISMATCH,
                f"{criterion.key} lists {check.owner}:{check.key}, which does not fit it ({reason})",
                key=criterion.key,
                entity_id=criterion.id,
                pointer=loc.pointer(criterion.key, "checks", n),
                details={"check": f"{check.owner}:{check.key}", "reason": reason},
            )


def criterion_missing(ctx: ValidationContext) -> Iterator[Finding]:
    spec, loc = ctx.spec, Locator(ctx.document)
    detailed = {phase.key for phase in spec.phases if phase.design_state is DesignState.DETAILED}
    for item in spec.items:
        owners = {item.key, *(unit.key for unit in spec.units_of(item.key))}
        if item.phase in detailed and not any(c.owner in owners for c in spec.criteria):
            yield finding(
                FindingCode.CRITERION_MISSING,
                f"{item.key} has no acceptance criteria; acceptance relies on its checks only",
                key=item.key,
                entity_id=item.id,
                pointer=loc.pointer(item.key),
            )


def criterion_unlinked(ctx: ValidationContext) -> Iterator[Finding]:
    loc = Locator(ctx.document)
    severity = None if ValidationSettings.of(ctx.settings).require_acceptance_links else Severity.WARNING
    owners = {entity.key: entity for entity in (*ctx.spec.items, *ctx.spec.units)}
    for criterion in ctx.spec.criteria:
        checks, dangling = _checks_of(ctx, criterion)
        reason: str | None = None
        where = "checks"
        match criterion.verification_mode:
            case VerificationMode.CHECK if not criterion.checks:
                reason = "check mode without checks"
            case VerificationMode.MANUAL if not dangling and not any(
                c.kind is CheckKind.MANUAL for c in checks
            ):
                reason = "manual mode without a manual check"
            case VerificationMode.REVIEW:
                owner = owners.get(criterion.owner)
                review = None if owner is None else ctx.spec.review_requirement_for(owner.id)
                if isinstance(review, WaivedReview):
                    reason, where = "review mode while the review of the item is waived", "verification_mode"
            case _:
                pass
        if reason is not None:
            yield finding(
                FindingCode.CRITERION_UNLINKED,
                f"{criterion.key} cannot be verified: {reason}",
                key=criterion.key,
                entity_id=criterion.id,
                pointer=loc.pointer(criterion.key, where),
                severity=severity,
                details={"mode": criterion.verification_mode.value, "reason": reason},
            )


def requirement_unimplemented(ctx: ValidationContext) -> Iterator[Finding]:
    spec, loc = ctx.spec, Locator(ctx.document)
    implemented = {key for entity in (*spec.items, *spec.units) for key in entity.implements}
    implemented.update(key for criterion in spec.criteria for key in criterion.requirements)
    for requirement in spec.requirements:
        if (
            requirement.priority is Priority.MUST
            and not requirement.owners
            and requirement.key not in implemented
        ):
            yield finding(
                FindingCode.REQUIREMENT_UNIMPLEMENTED,
                f"must-requirement {requirement.key} is implemented by nothing and owned by nobody",
                key=requirement.key,
                entity_id=requirement.id,
                pointer=loc.pointer(requirement.key),
            )


RULES: Final = (criterion_check_mismatch, criterion_missing, criterion_unlinked, requirement_unimplemented)
