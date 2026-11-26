"""PostgreSQL adapters for ``CheckRepository`` and ``ReviewRepository`` (execution §6; DDL ``0015``)."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import (
    check_from_row,
    finding_from_row,
    fix_brief_from_row,
    review_from_row,
    verdict_from_row,
)
from skm.adapters.postgres.execution.codecs_core import as_uuid
from skm.adapters.postgres.execution.mapping import (
    FIX_BRIEF_URN,
    opt_aware,
    opt_jsonb,
    require_unchanged,
    run,
    schema_registry,
)
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.kernel.json_types import JsonObject
from skm.modules.execution.domain.fix_brief import fix_brief_to_json
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.review import ReviewerKind
from skm.modules.execution.domain.stored_payloads import (
    canonical_bytes,
    invalid_ref,
    not_found,
    schema_invalid,
)

if TYPE_CHECKING:
    from skm.kernel.ids import EntityId, ProjectId, TaskId, WorkspaceId
    from skm.modules.execution.domain.check_execution import CheckExecution
    from skm.modules.execution.domain.finding import Finding
    from skm.modules.execution.domain.finding_resolution import FindingResolution
    from skm.modules.execution.domain.fix_brief import FixBrief
    from skm.modules.execution.domain.ids import CheckExecutionId, FixBriefId, OutputId
    from skm.modules.execution.domain.manual_verdict import ManualVerdict
    from skm.modules.execution.domain.review import Review

__all__ = [
    "PostgresCheckRepository",
    "PostgresReviewRepository",
]

_FIX_BRIEF_MAX_BYTES: Final = 1_048_576
_CHECK_OWNED: Final = (
    "workspace_id",
    "run_id",
    "task_id",
    "attempt_id",
    "output_id",
    "check_spec_id",
    "check_key",
    "kind",
    "required",
    "fingerprint",
    "round_no",
)
_REVIEW_OWNED: Final = (
    "workspace_id",
    "run_id",
    "task_id",
    "attempt_id",
    "output_id",
    "round_no",
    "reviewer_kind",
    "profile_key",
    "profile_version_id",
    "audit_scope",
    "base_output_id",
)
_FINDING_OWNED: Final = ("review_id", "local_id", "finding_key", "first_seen_review_id")

_RUN_META: Final = "SELECT revision_id FROM skm_execution.runs WHERE id = %s"
_INSERT_CHECK: Final = """
INSERT INTO skm_execution.check_executions (
    id, workspace_id, run_id, task_id, attempt_id, output_id, revision_id,
    check_spec_id, check_key, kind, required, state, exit_code, summary,
    error_code, reused_from_id, fingerprint, round_no, started_at, finished_at, created_at
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    COALESCE(%s, clock_timestamp())
)
"""
_LOCK_CHECK: Final = "SELECT * FROM skm_execution.check_executions WHERE id = %s FOR UPDATE"
_UPDATE_CHECK: Final = """
UPDATE skm_execution.check_executions
   SET state = %s, exit_code = %s, summary = %s, error_code = %s,
       reused_from_id = %s, started_at = %s, finished_at = %s
 WHERE id = %s
"""
_CHECKS_FOR_OUTPUT: Final = """
SELECT * FROM skm_execution.check_executions
 WHERE output_id = %s
 ORDER BY round_no ASC, check_key ASC, id ASC
"""
_REUSABLE_CHECK: Final = """
SELECT ce.*
  FROM skm_execution.check_executions ce
  JOIN skm_execution.runs r ON r.id = ce.run_id
 WHERE ce.workspace_id = %s
   AND r.project_id = %s
   AND ce.fingerprint = %s
   AND ce.check_spec_id = %s
   AND ce.state = 'passed'
   AND ce.reused_from_id IS NULL
 ORDER BY COALESCE(ce.finished_at, ce.started_at, ce.created_at) DESC, ce.id DESC
 LIMIT 1
"""
_CHECK_WS: Final = "SELECT workspace_id FROM skm_execution.check_executions WHERE id = %s"
_INSERT_VERDICT: Final = """
INSERT INTO skm_execution.manual_check_verdicts (
    id, check_execution_id, workspace_id, principal_id, verdict, comment, supersedes_id, recorded_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""
_VERDICTS_FOR_CHECK: Final = """
SELECT * FROM skm_execution.manual_check_verdicts
 WHERE check_execution_id = %s
 ORDER BY recorded_at ASC, id ASC
"""

_INSERT_REVIEW: Final = """
INSERT INTO skm_execution.reviews (
    id, workspace_id, run_id, task_id, attempt_id, output_id, round_no,
    reviewer_kind, reviewer_ref, step_id, profile_key, profile_version_id,
    audit_scope, state, verdict, freshness, base_output_id, residual_risk,
    created_at, completed_at
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
    COALESCE(%s, clock_timestamp()), %s
)
"""
_LOCK_REVIEW: Final = "SELECT * FROM skm_execution.reviews WHERE id = %s FOR UPDATE"
_UPDATE_REVIEW: Final = """
UPDATE skm_execution.reviews
   SET reviewer_ref = %s, state = %s, verdict = %s, freshness = %s,
       residual_risk = %s, completed_at = %s
 WHERE id = %s
"""
_REVIEWS_FOR_TASK: Final = "SELECT * FROM skm_execution.reviews WHERE task_id = %s ORDER BY round_no ASC"
_REVIEW_TASK_WS: Final = "SELECT task_id, workspace_id FROM skm_execution.reviews WHERE id = %s"
_INSERT_FINDING: Final = """
INSERT INTO skm_execution.review_findings (
    id, review_id, task_id, workspace_id, local_id, finding_key, first_seen_review_id,
    severity, confidence, basis, category, message, failure_scenario, location,
    reproduction, state, row_version, created_at, updated_at
) VALUES (
    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 1,
    clock_timestamp(), clock_timestamp()
)
"""
_LOCK_FINDING: Final = "SELECT * FROM skm_execution.review_findings WHERE id = %s FOR UPDATE"
_UPDATE_FINDING: Final = """
UPDATE skm_execution.review_findings
   SET severity = %s, confidence = %s, basis = %s, category = %s,
       message = %s, failure_scenario = %s, location = %s, reproduction = %s,
       state = %s, row_version = row_version + 1, updated_at = clock_timestamp()
 WHERE id = %s
"""
_FINDINGS_FOR_TASK: Final = """
SELECT f.*
  FROM skm_execution.review_findings f
  JOIN skm_execution.reviews r ON r.id = f.review_id
 WHERE f.task_id = %s
 ORDER BY r.round_no ASC, f.local_id ASC, f.id ASC
"""
_FINDING_TASK: Final = "SELECT task_id FROM skm_execution.review_findings WHERE id = %s"
_STEP_EXISTS: Final = "SELECT 1 FROM skm_execution.attempt_steps WHERE id = %s"
_INSERT_RESOLUTION: Final = """
INSERT INTO skm_execution.finding_resolutions (
    id, finding_id, task_id, resolution_kind, target_output_id, comment, resolved_by, at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
"""
_ATTEMPT_RUN_WS: Final = "SELECT run_id, workspace_id FROM skm_execution.attempts WHERE id = %s"
_INSERT_FIX_BRIEF: Final = """
INSERT INTO skm_execution.fix_briefs (
    id, run_id, task_id, attempt_id, workspace_id, source_review_id, source_check_round,
    document, digest, truncated, full_report_file_version_id, created_at
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, clock_timestamp())
"""
_GET_FIX_BRIEF: Final = "SELECT * FROM skm_execution.fix_briefs WHERE id = %s"


class PostgresCheckRepository:
    def get(self, check_id: CheckExecutionId) -> CheckExecution:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM skm_execution.check_executions WHERE id = %s", (check_id,))
            row = cur.fetchone()
        if row is None:
            raise not_found("check_execution", check_id)
        return check_from_row(row)

    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def add_many(self, executions: Sequence[CheckExecution]) -> None:
        if not executions:
            return

        def _op() -> None:
            rev_cache: dict[UUID, UUID] = {}
            with self._conn.cursor(row_factory=dict_row) as cur:
                for ex in executions:
                    rid = UUID(str(ex.run_id))
                    rev_id = rev_cache.get(rid)
                    if rev_id is None:
                        cur.execute(_RUN_META, (rid,))
                        rm = cur.fetchone()
                        if rm is None:
                            raise invalid_ref("fk_check_executions__runs_revision", run_id=str(ex.run_id))
                        rev_id = as_uuid(rm["revision_id"])
                        rev_cache[rid] = rev_id
                    started, finished = opt_aware(ex.started_at), opt_aware(ex.finished_at)
                    cur.execute(
                        _INSERT_CHECK,
                        (
                            ex.id,
                            ex.workspace_id,
                            ex.run_id,
                            ex.task_id,
                            ex.attempt_id,
                            ex.output_id,
                            rev_id,
                            ex.check_spec_id,
                            ex.check_key,
                            ex.kind.value,
                            ex.required,
                            ex.state.value,
                            ex.exit_code,
                            ex.summary,
                            ex.error_code,
                            ex.reused_from_id,
                            ex.fingerprint,
                            ex.round_no,
                            started,
                            finished,
                            started or finished,
                        ),
                    )

        run(_op)

    def save(self, execution: CheckExecution) -> None:
        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LOCK_CHECK, (execution.id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("check_execution", execution.id)
                require_unchanged("check_execution", check_from_row(row), execution, _CHECK_OWNED)
                cur.execute(
                    _UPDATE_CHECK,
                    (
                        execution.state.value,
                        execution.exit_code,
                        execution.summary,
                        execution.error_code,
                        execution.reused_from_id,
                        opt_aware(execution.started_at),
                        opt_aware(execution.finished_at),
                        execution.id,
                    ),
                )

        run(_op)

    def for_output(self, output_id: OutputId) -> tuple[CheckExecution, ...]:
        def _op() -> tuple[CheckExecution, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_CHECKS_FOR_OUTPUT, (output_id,))
                return tuple(check_from_row(r) for r in cur.fetchall())

        return run(_op)

    def reusable(
        self,
        workspace_id: WorkspaceId,
        project_id: ProjectId,
        fingerprint: str,
        check_spec_id: EntityId,
    ) -> CheckExecution | None:
        def _op() -> CheckExecution | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_REUSABLE_CHECK, (workspace_id, project_id, fingerprint, check_spec_id))
                row = cur.fetchone()
                return None if row is None else check_from_row(row)

        return run(_op)

    def add_verdict(self, verdict: ManualVerdict) -> None:
        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_CHECK_WS, (verdict.check_execution_id,))
                ce = cur.fetchone()
                if ce is None:
                    raise invalid_ref(
                        "fk_manual_check_verdicts__check_executions",
                        check_execution_id=str(verdict.check_execution_id),
                    )
                cur.execute(
                    _INSERT_VERDICT,
                    (
                        verdict.id,
                        verdict.check_execution_id,
                        as_uuid(ce["workspace_id"]),
                        verdict.principal_id,
                        verdict.verdict,
                        verdict.comment,
                        verdict.supersedes_id,
                        require_aware(verdict.recorded_at),
                    ),
                )

        run(_op)

    def verdicts(self, check_execution_id: CheckExecutionId) -> tuple[ManualVerdict, ...]:
        def _op() -> tuple[ManualVerdict, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_VERDICTS_FOR_CHECK, (check_execution_id,))
                return tuple(verdict_from_row(r) for r in cur.fetchall())

        return run(_op)


class PostgresReviewRepository:
    def __init__(self, conn: psycopg.Connection[Any]) -> None:
        self._conn = conn

    def add(self, review: Review) -> None:
        step_id: UUID | None = None
        pv_uuid = UUID(str(review.profile_version_id))
        profile_vid: UUID | None = None if pv_uuid == UUID(int=0) else pv_uuid
        if review.reviewer_kind is ReviewerKind.AGENT:
            raw_step = review.reviewer_ref.get("step_id")
            if not isinstance(raw_step, str):
                raise schema_invalid("agent review requires reviewer_ref.step_id", field="reviewer_ref")
            try:
                step_id = UUID(raw_step)
            except ValueError:
                raise schema_invalid("reviewer_ref.step_id must be a UUID", field="reviewer_ref") from None
            if profile_vid is None:
                raise schema_invalid("agent review requires profile_version_id", field="profile_version_id")
        completed = opt_aware(review.completed_at)

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    _INSERT_REVIEW,
                    (
                        review.id,
                        review.workspace_id,
                        review.run_id,
                        review.task_id,
                        review.attempt_id,
                        review.output_id,
                        review.round_no,
                        review.reviewer_kind.value,
                        to_jsonb(thaw_json(review.reviewer_ref)),
                        step_id,
                        review.profile_key,
                        profile_vid,
                        review.audit_scope,
                        review.state.value,
                        None if review.verdict is None else review.verdict.value,
                        review.freshness.value,
                        review.base_output_id,
                        review.residual_risk,
                        completed,
                        completed,
                    ),
                )

        run(_op)

    def save(self, review: Review) -> None:
        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LOCK_REVIEW, (review.id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("review", review.id)
                require_unchanged("review", review_from_row(row), review, _REVIEW_OWNED)
                cur.execute(
                    _UPDATE_REVIEW,
                    (
                        to_jsonb(thaw_json(review.reviewer_ref)),
                        review.state.value,
                        None if review.verdict is None else review.verdict.value,
                        review.freshness.value,
                        review.residual_risk,
                        opt_aware(review.completed_at),
                        review.id,
                    ),
                )

        run(_op)

    def for_task(self, task_id: TaskId) -> tuple[Review, ...]:
        def _op() -> tuple[Review, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_REVIEWS_FOR_TASK, (task_id,))
                return tuple(review_from_row(r) for r in cur.fetchall())

        return run(_op)

    def add_findings(self, findings: Sequence[Finding]) -> None:
        if not findings:
            return

        def _op() -> None:
            rev_meta: dict[UUID, tuple[UUID, UUID]] = {}
            with self._conn.cursor(row_factory=dict_row) as cur:
                for f in findings:
                    r_uuid = UUID(str(f.review_id))
                    pair = rev_meta.get(r_uuid)
                    if pair is None:
                        cur.execute(_REVIEW_TASK_WS, (r_uuid,))
                        rm = cur.fetchone()
                        if rm is None:
                            raise invalid_ref("fk_review_findings__reviews", review_id=str(f.review_id))
                        pair = (as_uuid(rm["task_id"]), as_uuid(rm["workspace_id"]))
                        rev_meta[r_uuid] = pair
                    cur.execute(
                        _INSERT_FINDING,
                        (
                            f.id,
                            f.review_id,
                            pair[0],
                            pair[1],
                            f.local_id,
                            f.finding_key,
                            f.first_seen_review_id,
                            f.severity.value,
                            f.confidence,
                            f.basis,
                            f.category,
                            f.message,
                            f.failure_scenario,
                            to_jsonb(thaw_json(f.location)),
                            opt_jsonb(f.reproduction),
                            f.state.value,
                        ),
                    )

        run(_op)

    def save_finding(self, finding: Finding) -> None:
        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_LOCK_FINDING, (finding.id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("finding", finding.id)
                require_unchanged("finding", finding_from_row(row), finding, _FINDING_OWNED)
                cur.execute(
                    _UPDATE_FINDING,
                    (
                        finding.severity.value,
                        finding.confidence,
                        finding.basis,
                        finding.category,
                        finding.message,
                        finding.failure_scenario,
                        to_jsonb(thaw_json(finding.location)),
                        opt_jsonb(finding.reproduction),
                        finding.state.value,
                        finding.id,
                    ),
                )

        run(_op)

    def findings_for_task(self, task_id: TaskId) -> tuple[Finding, ...]:
        def _op() -> tuple[Finding, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_FINDINGS_FOR_TASK, (task_id,))
                return tuple(finding_from_row(r) for r in cur.fetchall())

        return run(_op)

    def add_resolution(self, resolution: FindingResolution) -> None:
        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_FINDING_TASK, (resolution.finding_id,))
                frow = cur.fetchone()
                if frow is None:
                    raise invalid_ref(
                        "fk_finding_resolutions__review_findings", finding_id=str(resolution.finding_id)
                    )
                cur.execute(_STEP_EXISTS, (resolution.resolved_by,))
                rb: JsonObject = (
                    {"step_id": str(resolution.resolved_by)}
                    if cur.fetchone() is not None
                    else {"principal_id": str(resolution.resolved_by)}
                )
                cur.execute(
                    _INSERT_RESOLUTION,
                    (
                        resolution.id,
                        resolution.finding_id,
                        as_uuid(frow["task_id"]),
                        resolution.resolution_kind.value,
                        resolution.target_output_id,
                        resolution.comment,
                        to_jsonb(rb),
                        require_aware(resolution.at),
                    ),
                )

        run(_op)

    def add_fix_brief(self, brief: FixBrief) -> None:
        doc = fix_brief_to_json(brief)
        if len(canonical_bytes(doc)) > _FIX_BRIEF_MAX_BYTES:
            raise schema_invalid("fix_brief exceeds 1048576 canonical bytes", field="document")
        schema_registry().require_valid(FIX_BRIEF_URN, doc)

        def _op() -> None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_ATTEMPT_RUN_WS, (brief.attempt_id,))
                arow = cur.fetchone()
                if arow is None:
                    raise invalid_ref("fk_fix_briefs__attempts", attempt_id=str(brief.attempt_id))
                cur.execute(
                    _INSERT_FIX_BRIEF,
                    (
                        brief.id,
                        as_uuid(arow["run_id"]),
                        brief.task_id,
                        brief.attempt_id,
                        as_uuid(arow["workspace_id"]),
                        brief.source_review_id,
                        brief.source_check_round,
                        to_jsonb(doc),
                        brief.digest,
                        brief.truncated,
                        brief.full_report_file_version_id,
                    ),
                )

        run(_op)

    def get_fix_brief(self, brief_id: FixBriefId) -> FixBrief:
        def _op() -> FixBrief:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(_GET_FIX_BRIEF, (brief_id,))
                row = cur.fetchone()
                if row is None:
                    raise not_found("fix_brief", brief_id)
                return fix_brief_from_row(row)

        return run(_op)
