"""Memory adapters of the context repository ports (context §§6, 11; DDL ``0019``)."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Final

from skm.adapters.memory.context.research import MemoryResearchRepository as MemoryResearchRepository
from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.planning.state import planning_state
from skm.adapters.memory.workspace.state import workspace_state
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, PreconditionFailed, ValidationFailed
from skm.modules.context.domain.finalize import sha256_text
from skm.modules.context.domain.manifest import ContextManifest, ManifestBlock, ManifestState
from skm.modules.context.domain.request import validate_owner_ref
from skm.modules.planning.domain.specification import from_document

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from skm.kernel.ids import ContextManifestId
    from skm.modules.context.domain.contracts import Digest

__all__ = ["MemoryContextRepository", "MemoryResearchRepository", "MemoryTextStore"]

_STATE_KEY: Final = "context"


@dataclass
class _MemoryContextState:
    manifests: dict[ContextManifestId, ContextManifest] = field(
        default_factory=dict["ContextManifestId", ContextManifest]
    )
    step_refs: dict[str, ContextManifestId] = field(default_factory=dict[str, "ContextManifestId"])
    texts: dict[Digest, str] = field(default_factory=dict["Digest", str])


def _context_state(state: MemoryBackendState) -> _MemoryContextState:
    found = state.modules.get(_STATE_KEY)
    if found is None:
        found = _MemoryContextState()
        state.modules[_STATE_KEY] = found
    if not isinstance(found, _MemoryContextState):
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "context memory state is malformed", details={"module": _STATE_KEY}
        )
    return found


def _validate_block_invariants(blocks: Sequence[ManifestBlock], *, final: bool) -> None:
    seen_ordinals: set[int] = set()
    seen_refs: set[str] = set()
    seen_positions: set[int] = set()
    for b in blocks:
        if b.ordinal < 0 or b.ordinal in seen_ordinals:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "invalid or duplicate context block ordinal",
                details={"ordinal": b.ordinal},
            )
        seen_ordinals.add(b.ordinal)
        if b.block_ref in seen_refs:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "duplicate block_ref in manifest",
                details={"constraint": "uq_context_blocks__ref", "block_ref": b.block_ref},
            )
        seen_refs.add(b.block_ref)
        if (b.included is True) != (b.position is not None):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "included=True iff position is not None",
                details={"block_ref": b.block_ref},
            )
        if b.position is not None:
            if b.position < 0 or b.position in seen_positions:
                raise Conflict(
                    ErrorCode.ALREADY_EXISTS,
                    "duplicate or negative block position",
                    details={"constraint": "uq_context_blocks__position", "position": b.position},
                )
            seen_positions.add(b.position)
        if final and b.included is None:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "finalized manifest cannot contain undecided blocks",
                details={"block_ref": b.block_ref},
            )


def _draft_header_signature(m: ContextManifest) -> tuple[object, ...]:
    return (
        m.workspace_id,
        m.project_id,
        m.plan_id,
        m.revision_id,
        m.entity_id,
        m.owner_ref,
        m.purpose,
        m.agent_profile_version_id,
        m.runtime_id,
        m.model,
        m.draft_digest,
        m.total_limit,
        m.estimator_id,
        m.assembler_version,
        m.created_at,
    )


class MemoryContextRepository:
    """In-memory implementation of ``ContextRepository`` enforcing ``draft -> final`` immutability."""

    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state

    def _tables(self) -> _MemoryContextState:
        return _context_state(self._state)

    def _writable(self) -> _MemoryContextState:
        self._state.core.require_writable()
        return self._tables()

    def add_draft(self, manifest: ContextManifest) -> None:
        tables = self._writable()
        if manifest.state is not ManifestState.DRAFT:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "add_draft requires state='draft'",
                details={"state": manifest.state.value},
            )
        if (
            manifest.mode is not None
            or manifest.task_digest is not None
            or manifest.prompt_digest is not None
            or manifest.prompt_file_version_id is not None
            or manifest.total_tokens_estimate is not None
            or manifest.finalized_at is not None
        ):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "draft manifest must leave final fields unset",
                details={"manifest_id": str(manifest.id)},
            )
        if manifest.purpose.attempt_no < 1 or manifest.purpose.round_no < 1 or manifest.total_limit < 1000:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "context manifest counters violate ck_context_manifests__numbers",
                details={"manifest_id": str(manifest.id)},
            )
        step_ref = manifest.purpose.step_ref
        owner_ref = manifest.owner_ref or f"step:{step_ref}"
        if validate_owner_ref(owner_ref, step_ref) is not None:
            self._check_standalone_refs(manifest)
        elif (manifest.plan_id is None) != (manifest.revision_id is None) or (
            manifest.revision_id is None and manifest.entity_id is not None
        ):
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "invalid step manifest revision binding")
        _validate_block_invariants(manifest.blocks, final=False)
        if manifest.id in tables.manifests:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "context manifest already exists",
                details={"constraint": "context_manifests_pkey", "id": str(manifest.id)},
            )
        if step_ref is not None and step_ref in tables.step_refs:
            raise Conflict(
                ErrorCode.ALREADY_EXISTS,
                "context manifest for step_ref already exists",
                details={
                    "constraint": "uq_context_manifests__step_ref",
                    "step_ref": manifest.purpose.step_ref,
                },
            )
        stored = deepcopy(replace(manifest, owner_ref=owner_ref))
        tables.manifests[stored.id] = stored
        if step_ref is not None:
            tables.step_refs[step_ref] = stored.id

    def _check_standalone_refs(self, manifest: ContextManifest) -> None:
        project = workspace_state(self._state).projects.get(manifest.project_id)
        if project is None or project.workspace_id != manifest.workspace_id:
            raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "invalid standalone manifest project")
        planning = planning_state(self._state)
        if manifest.plan_id is not None:
            plan = planning.plans.get(manifest.plan_id)
            if plan is None or (plan.workspace_id, plan.project_id) != (
                manifest.workspace_id,
                manifest.project_id,
            ):
                raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "invalid standalone manifest plan")
        if manifest.revision_id is None:
            if manifest.entity_id is not None:
                raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "a standalone entity requires a revision")
            return
        if manifest.plan_id is None:
            raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "a standalone revision requires a plan")
        revision = planning.revisions.get(manifest.revision_id)
        if revision is None or (revision.meta.workspace_id, revision.meta.plan_id) != (
            manifest.workspace_id,
            manifest.plan_id,
        ):
            raise ValidationFailed(ErrorCode.INVALID_REFERENCE, "invalid standalone manifest revision")
        if manifest.entity_id is not None:
            spec, _ = from_document(revision.document)
            try:
                spec.entity(manifest.entity_id)
            except NotFound as exc:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID, "invalid standalone manifest entity"
                ) from exc

    def get(self, manifest_id: ContextManifestId, *, for_update: bool = False) -> ContextManifest:
        if for_update:
            self._state.core.require_writable()
        found = self._tables().manifests.get(manifest_id)
        if found is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "context manifest not found",
                details={"kind": "context_manifest", "ref": str(manifest_id)},
            )
        return deepcopy(found)

    def for_step(self, step_ref: str) -> ContextManifest:
        manifest_id = self._tables().step_refs.get(step_ref)
        if manifest_id is None:
            raise NotFound(ErrorCode.NOT_FOUND, "context manifest not found")
        return self.get(manifest_id)

    def finalize(self, manifest: ContextManifest, host_rows: Sequence[ManifestBlock]) -> None:
        tables = self._writable()
        current = tables.manifests.get(manifest.id)
        if current is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "context manifest not found",
                details={"kind": "context_manifest", "ref": str(manifest.id)},
            )
        if current.state is not ManifestState.DRAFT:
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "context manifest is already finalized",
                details={"from": current.state.value, "to": manifest.state.value},
            )
        if manifest.state is not ManifestState.FINAL:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "finalize requires target state='final'",
                details={"state": manifest.state.value},
            )
        if (
            manifest.mode is None
            or manifest.task_digest is None
            or manifest.prompt_digest is None
            or manifest.prompt_file_version_id is None
            or manifest.total_tokens_estimate is None
            or manifest.finalized_at is None
        ):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "finalized manifest must populate all final fields",
                details={"manifest_id": str(manifest.id)},
            )
        normalized = replace(manifest, owner_ref=manifest.owner_ref or current.owner_ref)
        if _draft_header_signature(normalized) != _draft_header_signature(current):
            raise ValidationFailed(
                ErrorCode.CONTEXT_MANIFEST_TAMPERED,
                "draft columns of context_manifests are immutable during finalize",
                details={"manifest_id": str(manifest.id)},
            )

        host_ordinals = {r.ordinal for r in host_rows}
        non_host = [b for b in normalized.blocks if b.ordinal not in host_ordinals]
        merged_blocks = tuple(sorted((*non_host, *host_rows), key=lambda b: b.ordinal))

        orig_by_ord = {b.ordinal: b for b in current.blocks}
        for b in non_host:
            orig = orig_by_ord.get(b.ordinal)
            if orig is None or (
                orig.block_ref,
                orig.block_type,
                orig.budget_class,
                orig.mandatory,
                orig.source_kind,
                orig.source_ref,
                orig.source_version,
                orig.trust,
                orig.tokens_estimate,
                orig.content_digest,
                orig.atomic_group,
                orig.content_stored,
            ) != (
                b.block_ref,
                b.block_type,
                b.budget_class,
                b.mandatory,
                b.source_kind,
                b.source_ref,
                b.source_version,
                b.trust,
                b.tokens_estimate,
                b.content_digest,
                b.atomic_group,
                b.content_stored,
            ):
                raise ValidationFailed(
                    ErrorCode.CONTEXT_MANIFEST_TAMPERED,
                    "draft block metadata cannot be mutated on finalize",
                    details={"ordinal": b.ordinal},
                )
        for hr in host_rows:
            if hr.ordinal in orig_by_ord or not hr.block_ref.startswith("h:hi:"):
                raise ValidationFailed(
                    ErrorCode.CONTEXT_MANIFEST_TAMPERED,
                    "host_rows must be new 'h:hi:<n>' blocks",
                    details={"block_ref": hr.block_ref, "ordinal": hr.ordinal},
                )
        _validate_block_invariants(merged_blocks, final=True)
        tables.manifests[manifest.id] = deepcopy(replace(normalized, blocks=merged_blocks))


class MemoryTextStore:
    """Append-only content-addressed store for ``skm_context.texts``."""

    def __init__(self, state: MemoryBackendState) -> None:
        self._state = state

    def put_many(self, texts: Mapping[Digest, str]) -> None:
        self._state.core.require_writable()
        tables = _context_state(self._state)
        for digest, content in texts.items():
            actual = sha256_text(content)
            if digest != actual:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID,
                    "text digest does not match sha256(content)",
                    details={"expected": digest, "actual": actual},
                )
            if digest not in tables.texts:
                tables.texts[digest] = content

    def get_many(self, digests: Sequence[Digest]) -> Mapping[Digest, str]:
        tables = _context_state(self._state)
        return {d: tables.texts[d] for d in digests if d in tables.texts}
