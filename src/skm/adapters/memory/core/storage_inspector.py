"""Inspect memory tables without creating or modifying rows in the snapshot."""

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from skm.adapters.memory.artifacts.state import MemoryArtifactsState
from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.execution.state import MemoryExecutionState
from skm.adapters.memory.knowledge.mapping import MemoryKnowledgeState
from skm.adapters.memory.planning.repositories import MemoryRevisionRepository
from skm.adapters.memory.planning.state import MemoryPlanningState
from skm.adapters.memory.workspace.state import MemoryWorkspaceState
from skm.application_bus.ports import OutboxState
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import FileVersionId
from skm.kernel.scopes import ScopeKind
from skm.modules.artifacts.domain.blob import BlobLocation, LocationState
from skm.modules.execution.domain.assignment import TERMINAL_ASSIGNMENT_STATES, AssignmentState
from skm.modules.execution.domain.attempt import TERMINAL_ATTEMPT_STATES, AttemptEndReason
from skm.modules.execution.domain.external_effect import EffectState
from skm.modules.execution.domain.output import manifest_digest
from skm.modules.execution.domain.run import RunKind
from skm.modules.planning.domain.canonical import specification_digest
from skm.modules.planning.domain.compile_graph import compile_execution_graph
from skm.modules.planning.domain.material import MaterialKind
from skm.modules.planning.domain.specification import from_document
from skm.platform.storage.verify import (
    EvidenceCheck,
    ExpiredStage,
    Finding,
    Level,
    Location,
    ObjectCheck,
    ObjectInventory,
    Reference,
    Target,
    check_scopes,
    checked_digest,
    finding,
)

__all__ = ["MemoryStorageInspector"]


class MemoryStorageInspector:
    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state
        self._artifacts = self._table("artifacts", MemoryArtifactsState)
        self._execution = self._table("execution", MemoryExecutionState)
        self._planning = self._table("planning", MemoryPlanningState)
        self._workspace = self._table("workspace", MemoryWorkspaceState)

    def _table[T](self, key: str, factory: type[T]) -> T:
        value = self._state.modules.get(key)
        return value if isinstance(value, factory) else factory()

    def _scopes(self) -> Iterable[Finding]:
        scopes = self._state.core.scopes.values()
        instance = next((str(s.id) for s in scopes if s.kind is ScopeKind.INSTANCE), None)
        owners = [
            *(
                (Target("workspace", str(row.id), row.id), instance)
                for row in self._workspace.workspaces.values()
            ),
            *((Target("host", str(row.id)), instance) for row in self._workspace.hosts.values()),
            *(
                (Target("project", str(row.id), row.workspace_id), str(row.workspace_id))
                for row in self._workspace.projects.values()
            ),
            *(
                (Target("plan", str(row.id), row.workspace_id), str(row.project_id))
                for row in self._planning.plans.values()
            ),
            *(
                (
                    Target("run", str(row.id), row.workspace_id),
                    str(row.project_id if row.kind is RunKind.ADHOC else row.plan_id),
                )
                for row in self._execution.runs.values()
            ),
        ]
        return check_scopes(scopes, owners)

    def _provenance(self, *, cross_workspace: bool) -> Iterator[Finding]:
        knowledge = self._table("knowledge", MemoryKnowledgeState)
        candidates = getattr(self._state.modules.get("learning"), "candidates", {})
        for row in knowledge.lessons.values():
            candidate = candidates.get(row.candidate_id)
            if cross_workspace:
                if candidate is None or candidate.workspace_id == row.workspace_id:
                    continue
                code = "CROSS_WORKSPACE_LINK"
            else:
                if candidate is not None:
                    continue
                code = "DANGLING_REFERENCE"
            yield finding(
                code, "lesson", row.id, row.workspace_id, Reference("candidate", str(row.candidate_id))
            )

    def _revisions(self, *, cryptographic: bool) -> Iterator[Finding]:
        if not self._planning.revisions:
            return
        repo = MemoryRevisionRepository(self._state)
        for ident, row in self._planning.revisions.items():
            workspace = row.meta.workspace_id
            digest = checked_digest(specification_digest, row.document)
            if cryptographic:
                if digest != row.meta.content_digest:
                    yield finding("PAYLOAD_DIGEST_MISMATCH", "revision", ident, workspace)
                continue

            try:
                typed = repo.load_typed_document(ident)
                spec, _ = from_document(typed)
            except (AttributeError, KeyError, TypeError, ValueError, ValidationFailed):
                yield finding("TYPED_SPEC_MISMATCH", "revision", ident, workspace)
                continue
            material_ids = {
                material.id for material in spec.materials if material.kind is MaterialKind.FILE_VERSION
            }
            # The typed document overlays pins onto the payload. A missing pin leaves the digest intact.
            if (
                digest is None
                or checked_digest(specification_digest, typed) != digest
                or len(row.pins) != len(material_ids)
                or {pin.material_id for pin in row.pins} != material_ids
            ):
                yield finding("TYPED_SPEC_MISMATCH", "revision", ident, workspace)
            try:
                compile_execution_graph(spec, ident)
            except ValidationFailed as error:
                if error.code == ErrorCode.DEPENDENCY_CYCLE:
                    yield finding("DEPENDENCY_CYCLE", "revision", ident, workspace)

    def _leases(self, now: datetime) -> Iterator[Finding]:
        for ident, lease in self._execution.leases.items():
            assignment = self._execution.assignments.get(ident)
            if lease.expires_at <= now or assignment is None:
                continue
            attempt = self._execution.attempts.get(assignment.attempt_id)
            if assignment.state in TERMINAL_ASSIGNMENT_STATES or (
                attempt is not None and attempt.state in TERMINAL_ATTEMPT_STATES
            ):
                yield finding(
                    "LEASE_INCONSISTENT",
                    "assignment",
                    ident,
                    assignment.workspace_id,
                    Reference("attempt", str(assignment.attempt_id)),
                )

    def expired_staging(self, now: datetime) -> Iterator[ExpiredStage]:
        blobs = {(blob.workspace_id, blob.digest) for blob in self._artifacts.blobs.values()}
        refs = {_location(loc).key for group in self._artifacts.locations.values() for loc in group}
        refs.update(
            (row.backend_id, row.storage_key)
            for row in self._artifacts.staged.values()
            if row.consumed_at is None and row.expires_at > now
        )
        for row in self._artifacts.staged.values():
            if (
                row.consumed_at is None
                and row.expires_at <= now
                and (row.backend_id, row.storage_key) not in refs
                and (row.workspace_id, row.digest) not in blobs
            ):
                yield ExpiredStage(
                    row.id, row.workspace_id, row.digest.value, Location(row.backend_id, row.storage_key)
                )

    def has_blob(self, workspace_id: UUID, digest: str) -> bool:
        return any(
            blob.workspace_id == workspace_id and blob.digest.value == digest
            for blob in self._artifacts.blobs.values()
        )

    def _cross_links(self) -> Iterator[Finding]:
        yield from self._provenance(cross_workspace=True)
        a, e, p, w = self._artifacts, self._execution, self._planning, self._workspace
        for rows, kind, columns in (
            (
                a.files,
                "files",
                (("project_id", "projects", w.projects), ("current_version_id", "file_versions", a.versions)),
            ),
            (a.versions, "file_versions", (("file_id", "files", a.files), ("blob_id", "blobs", a.blobs))),
            (p.plans, "plans", (("project_id", "projects", w.projects),)),
            (e.runs, "runs", (("project_id", "projects", w.projects), ("plan_id", "plans", p.plans))),
            (e.tasks, "run_tasks", (("run_id", "runs", e.runs),)),
            (e.attempts, "attempts", (("run_id", "runs", e.runs), ("task_id", "run_tasks", e.tasks))),
            (
                e.assignments,
                "assignments",
                (("run_id", "runs", e.runs), ("attempt_id", "attempts", e.attempts)),
            ),
            (
                w.bindings,
                "checkout_bindings",
                (("repository_id", "repositories", w.repositories),),
            ),
        ):
            for ident, row in rows.items():
                for field, parent_kind, table in columns:
                    parent = _related(table, getattr(row, field, None))
                    if parent is not None and parent.workspace_id != row.workspace_id:
                        yield finding(
                            "CROSS_WORKSPACE_LINK",
                            kind,
                            ident,
                            row.workspace_id,
                            Reference(parent_kind, str(parent.id)),
                        )
        for scope in self._state.core.scopes.values():
            parent_scope = self._state.core.scopes.get(scope.parent_id) if scope.parent_id else None
            if (
                parent_scope is not None
                and parent_scope.workspace_id is not None
                and scope.workspace_id is not None
                and parent_scope.workspace_id != scope.workspace_id
            ):
                yield finding(
                    "CROSS_WORKSPACE_LINK",
                    "scope",
                    scope.id,
                    scope.workspace_id,
                    Reference("scope", str(parent_scope.id)),
                )
        for run in e.runs.values():
            revision = p.revisions.get(run.revision_id) if run.revision_id is not None else None
            if revision is not None and revision.meta.workspace_id != run.workspace_id:
                yield finding(
                    "CROSS_WORKSPACE_LINK",
                    "runs",
                    run.id,
                    run.workspace_id,
                    Reference("plan_revisions", str(run.revision_id)),
                )
        for row in p.revisions.values():
            for pin in row.pins:
                version = a.versions.get(FileVersionId(pin.file_version_id))
                if version is not None and version.workspace_id != row.meta.workspace_id:
                    yield finding(
                        "CROSS_WORKSPACE_LINK",
                        "revision",
                        row.meta.id,
                        row.meta.workspace_id,
                        Reference("file_version", str(pin.file_version_id)),
                    )
            plan = p.plans.get(row.meta.plan_id)
            if plan is not None and plan.workspace_id != row.meta.workspace_id:
                yield finding(
                    "CROSS_WORKSPACE_LINK",
                    "plan_revisions",
                    row.meta.id,
                    row.meta.workspace_id,
                    Reference("plans", str(plan.id)),
                )
        yield from self._cross_evidence_links()

    def _cross_evidence_links(self) -> Iterator[Finding]:
        e = self._execution
        owners = {"attempt": e.attempts, "check_execution": e.checks, "review": e.reviews}
        for (kind, ident), bindings in e.evidence_bindings.items():
            if kind == "output":
                output = _related(e.outputs, ident)
                owner = e.attempts.get(output.attempt_id) if output is not None else None
                target_kind = "attempt_output"
            else:
                owner = _related(owners[kind], ident)
                target_kind = kind
            if owner is None:
                continue
            for version_id, _ in bindings:
                version = self._artifacts.versions.get(version_id)
                if version is not None and version.workspace_id != owner.workspace_id:
                    yield finding(
                        "CROSS_WORKSPACE_LINK",
                        target_kind,
                        ident,
                        owner.workspace_id,
                        Reference("file_version", str(version_id)),
                    )

    def _recovery(self, now: datetime, before: datetime) -> Iterator[Finding]:
        e = self._execution
        events = {event.id: event for event in self._state.core.events}
        for row in self._state.core.outbox.values():
            if row.state is OutboxState.DEAD:
                event = events.get(row.event_id)
                workspace = None if event is None else event.workspace_id
                yield finding(
                    "OUTBOX_DEAD", "outbox", row.id, workspace, Reference("event", str(row.event_id))
                )

        live = {
            (a.workspace_id, a.attempt_id)
            for ident, lease in e.leases.items()
            if lease.expires_at > now
            and (a := e.assignments.get(ident)) is not None
            and a.state is AssignmentState.LEASED
            and a.last_fencing_token == lease.fencing_token
            and (attempt := e.attempts.get(a.attempt_id)) is not None
            and attempt.state not in TERMINAL_ATTEMPT_STATES
        }
        for effect in e.effects.values():
            if effect.state is EffectState.OUTCOME_UNKNOWN or (
                effect.state is EffectState.EXECUTING and (effect.workspace_id, effect.attempt_id) not in live
            ):
                yield finding("EFFECT_OUTCOME_UNKNOWN", "external_effect", effect.id, effect.workspace_id)
        for row in e.recoveries.values():
            if row.outcome is None and row.at < before:
                run = e.runs.get(row.run_id)
                workspace = None if run is None else run.workspace_id
                yield finding("RECOVERY_STALLED", "run_recovery", row.id, workspace)

    def inspect(self, level: Level, *, now: datetime, recovery_before: datetime) -> Iterator[Finding]:
        match level:
            case "relational":
                yield from self._scopes()
                yield from self._provenance(cross_workspace=False)
            case "specification":
                yield from self._revisions(cryptographic=False)
            case "execution":
                yield from self._leases(now)
            case "files":
                for stage in self.expired_staging(now):
                    yield finding("STAGED_EXPIRED", "staged_blob", stage.id, stage.workspace_id)
            case "cryptographic":
                yield from self._revisions(cryptographic=True)
                yield from self._manifest_digests()
            case "authorization":
                yield from self._cross_links()
            case "recovery":
                yield from self._recovery(now, recovery_before)

    def _manifest_digests(self) -> Iterator[Finding]:
        for row in self._execution.outputs.values():
            if manifest_digest(row.manifest) != row.manifest_digest:
                run = self._execution.runs.get(row.run_id)
                workspace = None if run is None else run.workspace_id
                yield finding("PAYLOAD_DIGEST_MISMATCH", "attempt_output", row.id, workspace)
        manifests = getattr(self._state.modules.get("context"), "manifests", {})
        for row in manifests.values():
            if row.state != "final":
                continue
            version = self._artifacts.versions.get(row.prompt_file_version_id)
            blob = (
                None
                if version is None or version.workspace_id != row.workspace_id
                else (self._artifacts.blobs.get(version.blob_id))
            )
            if (
                blob is None
                or blob.workspace_id != row.workspace_id
                or blob.digest.value != row.prompt_digest
            ):
                yield finding(
                    "PAYLOAD_DIGEST_MISMATCH",
                    "context_manifest",
                    row.id,
                    row.workspace_id,
                    Reference("file_version", str(row.prompt_file_version_id)),
                )

    def inventory(self) -> ObjectInventory:
        a = self._artifacts
        refs: dict[UUID, list[Reference]] = defaultdict(list)
        for version in a.versions.values():
            refs[version.blob_id].append(Reference("file_version", str(version.id)))
        objects: list[ObjectCheck] = []
        for ident, locations in a.locations.items():
            blob = a.blobs.get(ident)
            workspace = None if blob is None else blob.workspace_id
            digest = None if blob is None else blob.digest.value
            references = tuple(sorted(refs[ident], key=lambda ref: ref.id))
            objects.extend(
                ObjectCheck(Target("blob", str(ident), workspace), _location(loc), digest, references)
                for loc in locations
            )
        objects.extend(
            ObjectCheck(
                Target("staged_blob", str(row.id), row.workspace_id),
                Location(row.backend_id, row.storage_key),
                row.digest.value,
            )
            for row in a.staged.values()
            if row.consumed_at is None
        )
        return ObjectInventory(tuple(self._workspace.workspaces), tuple(objects))

    def evidence(self) -> Iterator[EvidenceCheck]:
        e = self._execution
        owners: dict[tuple[UUID, UUID], set[tuple[str, UUID]]] = defaultdict(set)
        for row in e.attempts.values():
            if row.end_reason == AttemptEndReason.ACCEPTED:
                owners[row.workspace_id, row.id].add(("attempt", row.id))
                if row.current_output_id is not None:
                    owners[row.workspace_id, row.id].add(("output", row.current_output_id))
        for task in e.tasks.values():
            if task.accepted_attempt_id is not None:
                refs = owners[task.workspace_id, task.accepted_attempt_id]
                refs.add(("attempt", task.accepted_attempt_id))
                if task.accepted_output_id is not None:
                    refs.add(("output", task.accepted_output_id))
        for decision in e.acceptance_decisions.values():
            if decision.decision != "accepted":
                continue
            refs = owners[decision.workspace_id, decision.attempt_id]
            refs.add(("attempt", decision.attempt_id))
            if decision.output_id is not None:
                refs.add(("output", decision.output_id))
            if decision.basis.review_id is not None:
                refs.add(("review", decision.basis.review_id))
            refs.update(("check_execution", ident) for ident in decision.basis.check_execution_ids)

        for (workspace, attempt), refs in owners.items():
            target = Target("attempt", str(attempt), workspace)
            outputs = {ident for kind, ident in refs if kind == "output"}
            refs.update(
                ("check_execution", row.id)
                for row in e.checks.values()
                if row.attempt_id == attempt and row.output_id in outputs
            )
            refs.update(
                ("review", row.id)
                for row in e.reviews.values()
                if row.attempt_id == attempt and row.output_id in outputs
            )
            for kind, ident in refs:
                yield from self._evidence_for(target, kind, ident)

    def _evidence_for(self, target: Target, kind: str, ident: UUID) -> Iterator[EvidenceCheck]:
        e, a = self._execution, self._artifacts
        row = _related(
            {"attempt": e.attempts, "output": e.outputs, "review": e.reviews, "check_execution": e.checks}[
                kind
            ],
            ident,
        )
        if row is None:
            yield EvidenceCheck(target, Reference("attempt_output" if kind == "output" else kind, str(ident)))
            return
        versions = {file for file, _ in e.evidence_bindings.get((kind, ident), ())}
        if kind == "output" and row.manifest.patch_file_version_id is not None:
            versions.add(row.manifest.patch_file_version_id)
        for version in versions:
            stored = a.versions.get(version)
            blob = (
                a.blobs.get(stored.blob_id) if stored and stored.workspace_id == target.workspace_id else None
            )
            locations = (
                ()
                if blob is None or blob.workspace_id != target.workspace_id
                else tuple(
                    _location(loc)
                    for loc in a.locations.get(blob.id, ())
                    if loc.state is LocationState.PRESENT
                )
            )
            yield EvidenceCheck(target, Reference("file_version", str(version)), locations)


def _related(table: Mapping[Any, Any], ident: UUID | None) -> Any:
    return table.get(ident)


def _location(loc: BlobLocation) -> Location:
    return Location(loc.backend_id, loc.storage_key, loc.storage_version)
