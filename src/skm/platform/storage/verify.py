"""Storage finding catalog and checks shared by the storage adapters."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from graphlib import CycleError, TopologicalSorter
from hashlib import sha256
from types import MappingProxyType
from typing import Final, Literal
from uuid import UUID

from skm.kernel.errors import ValidationFailed
from skm.kernel.scopes import ScopeRecord, check_scope_parent, check_scope_workspace
from skm.platform.generated.results import (
    VerifyStorageResult,
    VerifyStorageResultCounts,
)
from skm.platform.generated.results import (
    VerifyStorageResultFindingsItem as Finding,
)
from skm.platform.generated.results import (
    VerifyStorageResultFindingsItemReferencedByItem as Reference,
)
from skm.platform.generated.results import (
    VerifyStorageResultFindingsItemTarget as Target,
)

type Level = Literal[
    "relational", "specification", "execution", "files", "cryptographic", "authorization", "recovery"
]
type Severity = Literal["error", "warning", "info"]
type Repairability = Literal["none", "safe"]

LEVELS: Final[tuple[Level, ...]] = (
    "relational",
    "specification",
    "execution",
    "files",
    "cryptographic",
    "authorization",
    "recovery",
)
CATALOG: Final = MappingProxyType[str, tuple[Level, Severity, Repairability, str]](
    {
        "SCOPE_LINEAGE_BROKEN": ("relational", "error", "none", "Scope disagrees with its parent or owner."),
        "DANGLING_REFERENCE": ("relational", "warning", "none", "Provenance points to a missing record."),
        "TYPED_SPEC_MISMATCH": (
            "specification",
            "error",
            "none",
            "Revision payload disagrees with typed storage.",
        ),
        "DEPENDENCY_CYCLE": (
            "specification",
            "error",
            "none",
            "Published revision contains a dependency cycle.",
        ),
        "ACCEPTED_EVIDENCE_MISSING": ("execution", "error", "none", "Accepted evidence is unavailable."),
        "LEASE_INCONSISTENT": (
            "execution",
            "error",
            "none",
            "A terminal assignment or attempt has a live lease.",
        ),
        "MISSING_OBJECT": ("files", "error", "none", "Blob location has no stored object."),
        "ORPHAN_OBJECT": ("files", "warning", "none", "Final object has no metadata reference."),
        "STAGED_EXPIRED": ("files", "info", "safe", "Unreferenced staged blob has expired."),
        "PAYLOAD_DIGEST_MISMATCH": (
            "cryptographic",
            "error",
            "none",
            "Stored content disagrees with its digest.",
        ),
        "CROSS_WORKSPACE_LINK": ("authorization", "error", "none", "Link crosses workspace ownership."),
        "OUTBOX_DEAD": ("recovery", "warning", "safe", "Delivery is in the dead outbox."),
        "EFFECT_OUTCOME_UNKNOWN": ("recovery", "warning", "none", "External effect requires reconciliation."),
        "RECOVERY_STALLED": ("recovery", "warning", "none", "Recovery exceeded the supervisor window."),
    }
)


@dataclass(frozen=True, slots=True)
class Location:
    backend_id: str
    storage_key: str
    storage_version: str | None = None

    @property
    def key(self) -> tuple[str, str]:
        return self.backend_id, self.storage_key


@dataclass(frozen=True, slots=True)
class ExpiredStage:
    id: UUID
    workspace_id: UUID
    digest: str
    location: Location


@dataclass(frozen=True, slots=True)
class ObjectCheck:
    target: Target
    location: Location
    digest: str | None
    referenced_by: tuple[Reference, ...] = ()


@dataclass(frozen=True, slots=True)
class EvidenceCheck:
    attempt: Target
    reference: Reference
    locations: tuple[Location, ...] = ()


@dataclass(frozen=True, slots=True)
class ObjectInventory:
    workspaces: tuple[UUID, ...]
    objects: tuple[ObjectCheck, ...]


def finding(
    code: str,
    kind: str,
    identifier: object,
    workspace: UUID | None = None,
    *references: Reference,
) -> Finding:
    level, severity, repairability, detail = CATALOG[code]
    return Finding(
        code, severity, level, Target(kind, str(identifier), workspace), references, repairability, detail
    )


def report(levels: tuple[Level, ...], findings: Iterable[Finding]) -> VerifyStorageResult:
    order = {level: index for index, level in enumerate(levels)}
    ordered = tuple(
        sorted(
            set(findings),
            key=lambda item: (
                order[item.level],
                item.code,
                item.target.kind,
                item.target.id,
                str(item.target.workspace_id),
                tuple((ref.kind, ref.id) for ref in item.referenced_by),
            ),
        )
    )
    return VerifyStorageResult(
        levels,
        ordered,
        VerifyStorageResultCounts(
            error=sum(item.severity == "error" for item in ordered),
            warning=sum(item.severity == "warning" for item in ordered),
            info=sum(item.severity == "info" for item in ordered),
        ),
    )


def check_scopes(
    scopes: Iterable[ScopeRecord],
    owners: Iterable[tuple[Target, str | None]],
) -> Iterable[Finding]:
    records = {str(scope.id): scope for scope in scopes}
    for scope in records.values():
        parent = records.get(str(scope.parent_id))
        try:
            check_scope_parent(scope.kind, parent)
            check_scope_workspace(scope.id, scope.kind, parent, scope.workspace_id)
        except ValidationFailed:
            yield finding("SCOPE_LINEAGE_BROKEN", "scope", scope.id, scope.workspace_id)
    for target, parent_id in owners:
        current = records.get(target.id)
        expected = (target.kind, parent_id, target.workspace_id)
        if (
            current is None
            or (current.kind, str(current.parent_id) if current.parent_id else None, current.workspace_id)
            != expected
        ):
            yield finding("SCOPE_LINEAGE_BROKEN", target.kind, target.id, target.workspace_id)


def has_cycle(edges: Iterable[tuple[str, str]]) -> bool:
    graph = TopologicalSorter[str]()
    for dependent, prerequisite in edges:
        graph.add(dependent, prerequisite)
    try:
        graph.prepare()
    except CycleError:
        return True
    return False


def checked_digest[T](compute: Callable[[T], str], document: T) -> str | None:
    """A damaged stored document may have no canonical representation."""
    try:
        return compute(document)
    except (AttributeError, KeyError, ValueError, TypeError, RecursionError):
        return None


def check_evidence(
    records: Iterable[EvidenceCheck],
    exists: Callable[[Location], bool] | None,
) -> Iterable[Finding]:
    for record in records:
        if not record.locations or (exists is not None and not any(map(exists, record.locations))):
            yield finding(
                "ACCEPTED_EVIDENCE_MISSING",
                record.attempt.kind,
                record.attempt.id,
                record.attempt.workspace_id,
                record.reference,
            )


def check_objects(
    inventory: ObjectInventory,
    levels: tuple[Level, ...],
    exists: Callable[[Location], bool],
    verify: Callable[[Location, str], bool],
    objects: Callable[[UUID], Iterable[Location]],
) -> Iterable[Finding]:
    for item in inventory.objects:
        target = item.target
        if target.kind == "staged_blob" and "cryptographic" not in levels:
            continue
        if not exists(item.location):
            if "files" in levels and target.kind == "blob":
                yield finding(
                    "MISSING_OBJECT", target.kind, target.id, target.workspace_id, *item.referenced_by
                )
        elif "cryptographic" in levels and item.digest is not None and not verify(item.location, item.digest):
            yield finding(
                "PAYLOAD_DIGEST_MISMATCH", target.kind, target.id, target.workspace_id, *item.referenced_by
            )
    if "files" in levels:
        known = {item.location.key for item in inventory.objects}
        for workspace in inventory.workspaces:
            for location in objects(workspace):
                if location.key not in known:
                    # Storage keys can contain identifiers or filesystem details. Report an opaque identity.
                    identifier = sha256(repr(location.key).encode()).hexdigest()
                    yield finding("ORPHAN_OBJECT", "blob_object", identifier, workspace)
