"""PostgreSQL adapters of the context repository ports (context §§6, 11; DDL ``0019``)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import datetime
from typing import Final, Literal, cast
from uuid import UUID

import psycopg

from skm.adapters.postgres.context.research import PostgresResearchRepository as PostgresResearchRepository
from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import InternalError, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import (
    ContextManifestId,
    EntityId,
    FileVersionId,
    PlanId,
    ProjectId,
    ResourceVersionId,
    RevisionId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonObject, JsonValue
from skm.modules.context.domain.blocks import BlockType, BudgetClass, TrustLevel
from skm.modules.context.domain.contracts import Digest
from skm.modules.context.domain.draft import host_input_from_json, host_input_to_json
from skm.modules.context.domain.finalize import sha256_text
from skm.modules.context.domain.manifest import ClassUsage, ContextManifest, ManifestBlock, ManifestState
from skm.modules.context.domain.request import StepPurpose, validate_owner_ref

__all__ = ["PostgresContextRepository", "PostgresResearchRepository", "PostgresTextStore"]

_NIL_UUID: Final = UUID(int=0)

_SQL_INSERT_MANIFEST: Final = """
INSERT INTO skm_context.context_manifests (
    id, workspace_id, project_id, plan_id, revision_id, entity_id,
    owner_ref, step_ref, role, stage_id, attempt_no, round_no,
    agent_profile_version_id, runtime_id, model, route, state, draft_digest,
    mode, task_digest, prompt_digest, prompt_file_version_id, total_tokens_estimate,
    total_limit, budgets, host_inputs, host_facts, skills_trace, diagnostics,
    estimator_id, assembler_version, created_at, finalized_at
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
)
"""

_SQL_INSERT_BLOCK: Final = """
INSERT INTO skm_context.context_blocks (
    manifest_id, ordinal, block_ref, position, block_type, budget_class, mandatory,
    source_kind, source_ref, source_version, trust, tokens_estimate, content_digest,
    included, reason, detail, atomic_group, content_stored, research_query_ids
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

_SQL_SELECT_MANIFEST: Final = """
SELECT
    id, workspace_id, project_id, plan_id, revision_id, entity_id,
    owner_ref, step_ref, role, stage_id, attempt_no, round_no,
    agent_profile_version_id, runtime_id, model, route, state, draft_digest,
    mode, task_digest, prompt_digest, prompt_file_version_id, total_tokens_estimate,
    total_limit, budgets, host_inputs, host_facts, skills_trace, diagnostics,
    estimator_id, assembler_version, created_at, finalized_at
FROM skm_context.context_manifests
WHERE id = %s
"""

_SQL_SELECT_MANIFEST_FOR_UPDATE: Final = """
SELECT
    id, workspace_id, project_id, plan_id, revision_id, entity_id,
    owner_ref, step_ref, role, stage_id, attempt_no, round_no,
    agent_profile_version_id, runtime_id, model, route, state, draft_digest,
    mode, task_digest, prompt_digest, prompt_file_version_id, total_tokens_estimate,
    total_limit, budgets, host_inputs, host_facts, skills_trace, diagnostics,
    estimator_id, assembler_version, created_at, finalized_at
FROM skm_context.context_manifests
WHERE id = %s
FOR UPDATE
"""

_SQL_SELECT_BLOCKS: Final = """
SELECT
    ordinal, block_ref, position, block_type, budget_class, mandatory,
    source_kind, source_ref, source_version, trust, tokens_estimate, content_digest,
    included, reason, detail, atomic_group, content_stored, research_query_ids
FROM skm_context.context_blocks
WHERE manifest_id = %s
ORDER BY ordinal ASC
"""

_SQL_UPDATE_DRAFT_BLOCK: Final = """
UPDATE skm_context.context_blocks
SET position = %s, included = %s, reason = %s, detail = %s
WHERE manifest_id = %s AND ordinal = %s AND included IS NULL
"""

_SQL_FINALIZE_MANIFEST: Final = """
UPDATE skm_context.context_manifests
SET
    state = 'final', route = %s, mode = %s, task_digest = %s,
    prompt_digest = %s, prompt_file_version_id = %s, total_tokens_estimate = %s,
    budgets = %s, host_facts = %s, diagnostics = %s, finalized_at = %s
WHERE id = %s AND state = 'draft'
RETURNING id
"""

_SQL_INSERT_TEXT: Final = """
INSERT INTO skm_context.texts (digest, text, size_bytes, created_at)
VALUES (%s, %s, %s, transaction_timestamp())
ON CONFLICT (digest) DO NOTHING
"""

_SQL_SELECT_TEXTS: Final = """
SELECT digest, text FROM skm_context.texts WHERE digest = ANY(%s)
"""


def _run[T](call: Callable[[], T]) -> T:
    try:
        return call()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def _budgets_to_json(budgets: Mapping[BudgetClass, ClassUsage]) -> JsonObject:
    out: JsonObject = {}
    for cls in BudgetClass:
        entry: JsonObject = {
            "tokens": budgets[cls].tokens if cls in budgets else None,
            "limit": budgets[cls].limit if cls in budgets else None,
        }
        out[cls.value] = entry
    return out


def _budgets_from_json(raw: object) -> Mapping[BudgetClass, ClassUsage]:
    data: Mapping[str, object] = cast("Mapping[str, object]", raw) if isinstance(raw, Mapping) else {}
    out: dict[BudgetClass, ClassUsage] = {}
    for cls in BudgetClass:
        entry_raw = data.get(cls.value)
        if isinstance(entry_raw, Mapping):
            entry = cast("Mapping[str, object]", entry_raw)
            tok, lim = entry.get("tokens"), entry.get("limit")
            out[cls] = ClassUsage(
                tokens=None if tok is None else int(cast("int", tok)),
                limit=None if lim is None else int(cast("int", lim)),
            )
        else:
            out[cls] = ClassUsage(tokens=None, limit=None)
    return out


def _block_params(manifest_id: ContextManifestId, b: ManifestBlock) -> tuple[object, ...]:
    return (
        manifest_id,
        b.ordinal,
        b.block_ref,
        b.position,
        b.block_type.value,
        b.budget_class.value,
        b.mandatory,
        b.source_kind,
        b.source_ref,
        b.source_version,
        b.trust.value,
        b.tokens_estimate,
        b.content_digest,
        b.included,
        b.reason,
        b.detail,
        b.atomic_group,
        b.content_stored,
        list(b.research_query_ids) if b.research_query_ids else None,
    )


def _block_from_row(row: tuple[object, ...]) -> ManifestBlock:
    rq_raw = row[17]
    rq_ids = (
        tuple(str(x) for x in cast("Sequence[object]", rq_raw))
        if isinstance(rq_raw, Sequence) and not isinstance(rq_raw, str | bytes)
        else ()
    )
    return ManifestBlock(
        ordinal=int(cast("int", row[0])),
        block_ref=str(row[1]),
        position=None if row[2] is None else int(cast("int", row[2])),
        block_type=BlockType(str(row[3])),
        budget_class=BudgetClass(str(row[4])),
        mandatory=bool(row[5]),
        source_kind=str(row[6]),
        source_ref=str(row[7]),
        source_version=None if row[8] is None else str(row[8]),
        trust=TrustLevel(str(row[9])),
        tokens_estimate=None if row[10] is None else int(cast("int", row[10])),
        content_digest=None if row[11] is None else str(row[11]),
        included=None if row[12] is None else bool(row[12]),
        reason=str(row[13]),
        detail=None if row[14] is None else str(row[14]),
        atomic_group=None if row[15] is None else str(row[15]),
        content_stored=bool(row[16]),
        research_query_ids=rq_ids,
    )


def _manifest_from_row(row: tuple[object, ...], blocks: tuple[ManifestBlock, ...]) -> ContextManifest:
    try:
        raw_entity = cast("UUID | None", row[5])
        entity_id = (
            None
            if raw_entity is None or (row[7] is not None and raw_entity == _NIL_UUID)
            else EntityId(raw_entity)
        )
        raw_hi = row[25]
        host_inputs = (
            tuple(
                host_input_from_json(cast("Mapping[str, JsonValue]", item))
                for item in cast("Sequence[object]", raw_hi)
                if isinstance(item, Mapping)
            )
            if isinstance(raw_hi, Sequence) and not isinstance(raw_hi, str | bytes)
            else ()
        )
        raw_trace = dict(cast("Mapping[str, JsonValue]", row[27])) if isinstance(row[27], Mapping) else {}
        raw_diags = row[28]
        diagnostics = (
            tuple(
                dict(cast("Mapping[str, JsonValue]", d))
                for d in cast("Sequence[object]", raw_diags)
                if isinstance(d, Mapping)
            )
            if isinstance(raw_diags, Sequence) and not isinstance(raw_diags, str | bytes)
            else ()
        )
        return ContextManifest(
            id=ContextManifestId(cast("UUID", row[0])),
            workspace_id=WorkspaceId(cast("UUID", row[1])),
            project_id=ProjectId(cast("UUID", row[2])),
            plan_id=None if row[3] is None else PlanId(cast("UUID", row[3])),
            revision_id=None if row[4] is None else RevisionId(cast("UUID", row[4])),
            entity_id=entity_id,
            owner_ref=str(row[6]),
            purpose=StepPurpose(
                step_ref=None if row[7] is None else str(row[7]),
                role=str(row[8]),
                stage_id=str(row[9]),
                attempt_no=int(cast("int", row[10])),
                round_no=int(cast("int", row[11])),
            ),
            agent_profile_version_id=ResourceVersionId(cast("UUID", row[12])),
            runtime_id=str(row[13]),
            model=str(row[14]),
            route=dict(cast("Mapping[str, JsonValue]", row[15])) if isinstance(row[15], Mapping) else {},
            state=ManifestState(str(row[16])),
            draft_digest=str(row[17]),
            mode=None if row[18] is None else cast("Literal['full', 'delta']", str(row[18])),
            task_digest=None if row[19] is None else str(row[19]),
            prompt_digest=None if row[20] is None else str(row[20]),
            prompt_file_version_id=None if row[21] is None else FileVersionId(cast("UUID", row[21])),
            total_tokens_estimate=None if row[22] is None else int(cast("int", row[22])),
            total_limit=int(cast("int", row[23])),
            budgets=_budgets_from_json(row[24]),
            blocks=blocks,
            host_facts=dict(cast("Mapping[str, JsonValue]", row[26]))
            if isinstance(row[26], Mapping)
            else None,
            skills_trace=raw_trace,
            diagnostics=diagnostics,
            estimator_id=str(row[29]),
            assembler_version=int(cast("int", row[30])),
            created_at=cast("datetime", row[31]),
            finalized_at=cast("datetime | None", row[32]),
            host_inputs=host_inputs,
        )
    except Exception as exc:
        raise InternalError(
            ErrorCode.INTERNAL_ERROR,
            "stored context_manifests row is damaged",
            details={"id": str(row[0])},
        ) from exc


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
    )


def _block_draft_signature(b: ManifestBlock) -> tuple[object, ...]:
    return (
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
    )


class PostgresContextRepository:
    """PostgreSQL implementation of ``ContextRepository`` over ``skm_context`` (DDL ``0019``)."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add_draft(self, manifest: ContextManifest) -> None:
        if manifest.state is not ManifestState.DRAFT:
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "add_draft requires state='draft'",
                details={"state": manifest.state.value},
            )
        owner = manifest.owner_ref or f"step:{manifest.purpose.step_ref}"
        hi_j: list[JsonValue] = [host_input_to_json(hi) for hi in manifest.host_inputs]
        diags_j: list[JsonValue] = [dict(d) for d in manifest.diagnostics]
        standalone = validate_owner_ref(owner, manifest.purpose.step_ref) is not None
        entity_uuid = (
            _NIL_UUID
            if manifest.entity_id is None and not standalone and manifest.revision_id is not None
            else manifest.entity_id
        )

        def _insert() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    _SQL_INSERT_MANIFEST,
                    (
                        manifest.id,
                        manifest.workspace_id,
                        manifest.project_id,
                        manifest.plan_id,
                        manifest.revision_id,
                        entity_uuid,
                        owner,
                        manifest.purpose.step_ref,
                        manifest.purpose.role,
                        manifest.purpose.stage_id,
                        manifest.purpose.attempt_no,
                        manifest.purpose.round_no,
                        manifest.agent_profile_version_id,
                        manifest.runtime_id,
                        manifest.model,
                        to_jsonb(manifest.route),
                        manifest.state.value,
                        manifest.draft_digest,
                        None,
                        None,
                        None,
                        None,
                        None,
                        manifest.total_limit,
                        to_jsonb(_budgets_to_json(manifest.budgets)),
                        to_jsonb(hi_j),
                        None,
                        to_jsonb(manifest.skills_trace),
                        to_jsonb(diags_j),
                        manifest.estimator_id,
                        manifest.assembler_version,
                        require_aware(manifest.created_at),
                        None,
                    ),
                )
                for b in manifest.blocks:
                    cur.execute(_SQL_INSERT_BLOCK, _block_params(manifest.id, b))

        _run(_insert)

    def get(self, manifest_id: ContextManifestId, *, for_update: bool = False) -> ContextManifest:
        def _fetch() -> tuple[tuple[object, ...] | None, list[tuple[object, ...]]]:
            with self._conn.cursor() as cur:
                if for_update:
                    cur.execute(_SQL_SELECT_MANIFEST_FOR_UPDATE, (manifest_id,))
                else:
                    cur.execute(_SQL_SELECT_MANIFEST, (manifest_id,))
                header = cur.fetchone()
                if header is None:
                    return None, []
                cur.execute(_SQL_SELECT_BLOCKS, (manifest_id,))
                return header, cur.fetchall()

        header_row, block_rows = _run(_fetch)
        if header_row is None:
            raise NotFound(
                ErrorCode.NOT_FOUND,
                "context manifest not found",
                details={"kind": "context_manifest", "ref": str(manifest_id)},
            )
        return _manifest_from_row(header_row, tuple(_block_from_row(r) for r in block_rows))

    def for_step(self, step_ref: str) -> ContextManifest:
        # step_ref is unique and immutable, so the lookup and read need no row lock.
        row = _run(
            lambda: self._conn.execute(
                "SELECT id FROM skm_context.context_manifests WHERE step_ref = %s", (step_ref,)
            ).fetchone()
        )
        if row is None:
            raise NotFound(ErrorCode.NOT_FOUND, "context manifest not found")
        return self.get(ContextManifestId(cast("UUID", row[0])))

    def finalize(self, manifest: ContextManifest, host_rows: Sequence[ManifestBlock]) -> None:
        current = self.get(manifest.id, for_update=True)
        if current.state is not ManifestState.DRAFT:
            raise PreconditionFailed(
                ErrorCode.INVALID_TRANSITION,
                "context manifest is already finalized",
                details={"from": current.state.value, "to": manifest.state.value},
            )
        if manifest.state is not ManifestState.FINAL or (
            manifest.mode is None
            or manifest.task_digest is None
            or manifest.prompt_digest is None
            or manifest.prompt_file_version_id is None
            or manifest.total_tokens_estimate is None
            or manifest.finalized_at is None
        ):
            raise ValidationFailed(
                ErrorCode.SCHEMA_INVALID,
                "finalized manifest must have state='final' and all final fields populated",
                details={"manifest_id": str(manifest.id)},
            )
        normalized = replace(
            manifest,
            owner_ref=manifest.owner_ref or current.owner_ref,
            host_inputs=manifest.host_inputs or current.host_inputs,
        )
        if _draft_header_signature(normalized) != _draft_header_signature(current):
            raise ValidationFailed(
                ErrorCode.CONTEXT_MANIFEST_TAMPERED,
                "draft columns of context_manifests are immutable during finalize",
                details={"manifest_id": str(manifest.id)},
            )

        host_ordinals = {r.ordinal for r in host_rows}
        orig_by_ord = {b.ordinal: b for b in current.blocks}
        draft_updates: list[ManifestBlock] = []
        for b in normalized.blocks:
            if b.ordinal in host_ordinals:
                continue
            orig = orig_by_ord.get(b.ordinal)
            if orig is None or _block_draft_signature(orig) != _block_draft_signature(b):
                raise ValidationFailed(
                    ErrorCode.CONTEXT_MANIFEST_TAMPERED,
                    "draft block metadata cannot be mutated on finalize",
                    details={"ordinal": b.ordinal},
                )
            if b.included is None:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID,
                    "finalized manifest cannot contain undecided blocks",
                    details={"block_ref": b.block_ref},
                )
            draft_updates.append(b)
        for hr in host_rows:
            if hr.ordinal in orig_by_ord or not hr.block_ref.startswith("h:hi:") or hr.included is None:
                raise ValidationFailed(
                    ErrorCode.CONTEXT_MANIFEST_TAMPERED,
                    "host_rows must be decided 'h:hi:<n>' blocks",
                    details={"block_ref": hr.block_ref, "ordinal": hr.ordinal},
                )

        def _apply() -> None:
            with self._conn.cursor() as cur:
                for b in draft_updates:
                    if not b.block_ref.startswith("x:"):
                        cur.execute(
                            _SQL_UPDATE_DRAFT_BLOCK,
                            (b.position, b.included, b.reason, b.detail, normalized.id, b.ordinal),
                        )
                        if cur.rowcount != 1:
                            raise PreconditionFailed(
                                ErrorCode.INVALID_TRANSITION,
                                "draft block was already decided or missing",
                                details={"manifest_id": str(normalized.id), "ordinal": b.ordinal},
                            )
                for hr in host_rows:
                    cur.execute(_SQL_INSERT_BLOCK, _block_params(normalized.id, hr))
                fin_diags: list[JsonValue] = [dict(d) for d in normalized.diagnostics]
                cur.execute(
                    _SQL_FINALIZE_MANIFEST,
                    (
                        to_jsonb(normalized.route),
                        normalized.mode,
                        normalized.task_digest,
                        normalized.prompt_digest,
                        normalized.prompt_file_version_id,
                        normalized.total_tokens_estimate,
                        to_jsonb(_budgets_to_json(normalized.budgets)),
                        None if normalized.host_facts is None else to_jsonb(normalized.host_facts),
                        to_jsonb(fin_diags),
                        require_aware(cast("datetime", normalized.finalized_at)),
                        normalized.id,
                    ),
                )
                if cur.fetchone() is None:
                    raise PreconditionFailed(
                        ErrorCode.INVALID_TRANSITION,
                        "context manifest is no longer in draft state",
                        details={"manifest_id": str(normalized.id)},
                    )

        _run(_apply)


class PostgresTextStore:
    """Append-only content-addressed store over ``skm_context.texts``."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def put_many(self, texts: Mapping[Digest, str]) -> None:
        if not texts:
            return
        rows: list[tuple[str, int, str]] = []
        for digest, content in texts.items():
            actual = sha256_text(content)
            if digest != actual:
                raise ValidationFailed(
                    ErrorCode.SCHEMA_INVALID,
                    "text digest does not match sha256(content)",
                    details={"expected": digest, "actual": actual},
                )
            rows.append((digest, len(content.encode("utf-8")), content))

        def _insert() -> None:
            with self._conn.cursor() as cur:
                for digest, size_bytes, content in rows:
                    cur.execute(_SQL_INSERT_TEXT, (digest, content, size_bytes))

        _run(_insert)

    def get_many(self, digests: Sequence[Digest]) -> Mapping[Digest, str]:
        if not digests:
            return {}
        wanted = list(dict.fromkeys(digests))

        def _select() -> list[tuple[object, ...]]:
            with self._conn.cursor() as cur:
                cur.execute(_SQL_SELECT_TEXTS, (wanted,))
                return cur.fetchall()

        return {str(r[0]): str(r[1]) for r in _run(_select)}
