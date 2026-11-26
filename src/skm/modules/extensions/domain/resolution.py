"""Which version of a resource a scope or a run reads (extensions §4.12).

``choose_pack_versions`` picks the newest allowed active version of each enabled pack; ``choices_from_pins``
replaces that step by exactly the versions a run has pinned (K19): a newer installed version or a pack
disabled later change nothing, a retired or unknown pinned version is ``NOT_FOUND`` (``pinned_pack_missing``).
``resolve`` is the common rest: order candidates, skip quarantined ones, apply the resource pin. It explains
every candidate instead of raising, so ``extensions.resolve_resource`` can show a refusal; ``require_chosen``
turns the decision into the normative error.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed
from skm.kernel.outcomes import Diagnostic, Severity
from skm.modules.extensions.domain.keys import LATEST, SemVer
from skm.modules.extensions.domain.pack import TRUST_RANK, PackState, PackTrust

if TYPE_CHECKING:
    from collections.abc import Collection, Iterable, Mapping, Sequence

    from skm.kernel.ids import ResourceVersionId
    from skm.modules.extensions.domain.keys import (
        PackId,
        PackSlug,
        PackVersionId,
        ResourceKey,
        VersionConstraint,
    )
    from skm.modules.extensions.domain.kinds import ResourceKind
    from skm.modules.extensions.domain.pack import PackPins, PackVersionSummary
    from skm.modules.extensions.domain.resource import ResourceVersionSummary

__all__ = [
    "CandidateRow",
    "PackChoice",
    "ResolutionDecision",
    "ResolutionOutcome",
    "ResourcePin",
    "choices_from_pins",
    "choose_pack_versions",
    "config_choices",
    "parse_resource_pin",
    "require_chosen",
    "resolve",
]


@dataclass(frozen=True, slots=True)
class PackChoice:
    pack_id: PackId
    slug: PackSlug
    version_id: PackVersionId
    version: SemVer
    trust: PackTrust
    priority: int


@dataclass(frozen=True, slots=True)
class CandidateRow:
    pack: PackSlug
    version: str
    digest: str
    verdict: str
    reason: str  # chosen | lower_priority | quarantined | pin_mismatch


class ResolutionOutcome(StrEnum):
    CHOSEN = "chosen"
    NO_CANDIDATES = "no_candidates"
    QUARANTINED = "quarantined"
    PIN_UNSATISFIED = "pin_unsatisfied"


@dataclass(frozen=True, slots=True)
class ResolutionDecision:
    chosen: ResourceVersionSummary | None
    candidates: tuple[CandidateRow, ...]
    outcome: ResolutionOutcome = ResolutionOutcome.CHOSEN
    kind: str = ""
    key: str = ""


@dataclass(frozen=True, slots=True)
class ResourcePin:
    """``extensions.resources.pinned["<kind>:<key>"]``: a digest or an exact version. A digest names one
    content of its pair because ``install_candidate`` refuses other files under a digest the pair holds."""

    digest: str | None = None
    version: str | None = None

    def matches(self, row: ResourceVersionSummary) -> bool:
        if self.digest is not None:
            return row.digest == self.digest
        return str(row.version) == self.version


def parse_resource_pin(text: str) -> ResourcePin:
    return ResourcePin(digest=text) if text.startswith("sha256:") else ResourcePin(version=text)


def _choice(row: PackVersionSummary, priorities: Mapping[PackSlug, int]) -> PackChoice:
    return PackChoice(
        pack_id=row.pack_id,
        slug=row.slug,
        version_id=row.version_id,
        version=row.version,
        trust=row.trust,
        priority=priorities.get(row.slug, row.priority),
    )


def choose_pack_versions(
    enabled: Sequence[PackSlug],
    constraints: Mapping[PackSlug, VersionConstraint],
    installed: Sequence[PackVersionSummary],
    *,
    priorities: Mapping[PackSlug, int] | None = None,
) -> tuple[tuple[PackChoice, ...], tuple[Diagnostic, ...]]:
    """§4.12 steps 1-2; a slug without a fitting active version is ``PACK_NOT_INSTALLED``."""
    choices: list[PackChoice] = []
    diagnostics: list[Diagnostic] = []
    for slug in sorted(set(enabled)):
        constraint = constraints.get(slug, LATEST)
        fitting = [
            row
            for row in installed
            if row.slug == slug and row.state is PackState.ACTIVE and constraint.matches(row.version)
        ]
        if fitting:
            newest = max(fitting, key=lambda row: _VersionOrder(row.version))
            choices.append(_choice(newest, priorities or {}))
        else:
            diagnostics.append(
                Diagnostic(
                    "PACK_NOT_INSTALLED",
                    f"no active version of pack {slug} satisfies {constraint}",
                    Severity.ERROR,
                    target=slug,
                    details={"pack": slug, "constraint": str(constraint)},
                )
            )
    return tuple(choices), tuple(diagnostics)


@dataclass(frozen=True, slots=True)
class _VersionOrder:
    version: SemVer

    def __lt__(self, other: _VersionOrder) -> bool:
        return self.version < other.version


def choices_from_pins(
    pins: PackPins,
    installed: Iterable[PackVersionSummary],
    *,
    priorities: Mapping[PackSlug, int] | None = None,
) -> tuple[PackChoice, ...]:
    """§4.12 step 8: exactly the pinned versions, whatever is newer or disabled now."""
    by_id = {row.version_id: row for row in installed}
    choices: list[PackChoice] = []
    for slug in sorted(pins):
        row = by_id.get(pins[slug])
        if row is None or row.slug != slug or row.state is not PackState.ACTIVE:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                f"pinned version of pack {slug} is not available",
                details={"reason": "pinned_pack_missing", "pack": slug, "pack_version_id": str(pins[slug])},
            )
        choices.append(_choice(row, priorities or {}))
    return tuple(choices)


def _rank(choice: PackChoice) -> tuple[int, int, str]:
    return (-choice.priority, -TRUST_RANK[choice.trust], choice.slug)


def config_choices(choices: Iterable[PackChoice]) -> tuple[PackChoice, ...]:
    """§11.3, S26: ``builtin`` and ``operator`` choices ordered by ``(priority, slug)``."""
    allowed = (choice for choice in choices if choice.trust in (PackTrust.BUILTIN, PackTrust.OPERATOR))
    return tuple(sorted(allowed, key=lambda choice: (choice.priority, choice.slug)))


def resolve(
    kind: ResourceKind,
    key: ResourceKey,
    choices: Sequence[PackChoice],
    versions: Sequence[ResourceVersionSummary],
    quarantine: frozenset[ResourceVersionId] | Collection[ResourceVersionId],
    pin: ResourcePin | None,
) -> ResolutionDecision:
    """§4.12 steps 3-7 over the versions of ``(kind, key)`` in the chosen pack versions."""
    by_version = {choice.version_id: choice for choice in choices}
    ordered = sorted(
        (
            (by_version[row.pack_version_id], row)
            for row in versions
            if row.kind == kind and row.key == key and row.pack_version_id in by_version
        ),
        key=lambda pair: _rank(pair[0]),
    )
    chosen: ResourceVersionSummary | None = None
    rows: list[CandidateRow] = []
    any_pinned = False
    for choice, row in ordered:
        if pin is not None and not pin.matches(row):
            reason = "pin_mismatch"
        elif row.id in quarantine:
            any_pinned = True
            reason = "quarantined"
        elif chosen is None:
            any_pinned = True
            chosen, reason = row, "chosen"
        else:
            reason = "lower_priority"
        rows.append(CandidateRow(choice.slug, str(row.version), row.digest, row.verdict.value, reason))
    if chosen is not None:
        outcome = ResolutionOutcome.CHOSEN
    elif not ordered:
        outcome = ResolutionOutcome.NO_CANDIDATES
    elif pin is not None and not any_pinned:
        outcome = ResolutionOutcome.PIN_UNSATISFIED
    else:
        outcome = ResolutionOutcome.QUARANTINED
    return ResolutionDecision(chosen, tuple(rows), outcome, str(kind), key)


def require_chosen(
    decision: ResolutionDecision, *, missing_packs: Sequence[PackSlug] = ()
) -> ResourceVersionSummary:
    """The chosen version or the normative error of §4.12 steps 2, 5, 6 and 7."""
    if decision.chosen is not None:
        return decision.chosen
    details = {"kind": decision.kind, "key": decision.key}
    if decision.outcome is ResolutionOutcome.QUARANTINED:
        raise PreconditionFailed(
            ErrorCode.RESOURCE_QUARANTINED, "every candidate is quarantined", details=details
        )
    if decision.outcome is ResolutionOutcome.PIN_UNSATISFIED:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "no candidate satisfies the pin",
            details={**details, "reason": "pin_unsatisfied"},
        )
    if missing_packs:
        raise NotFound(
            ErrorCode.NOT_FOUND,
            "no version of the pack can supply the resource",
            details={"kind": "pack_version", "pack": sorted(missing_packs)[0], "key": decision.key},
        )
    raise NotFound(ErrorCode.NOT_FOUND, "resource not found", details=details)
