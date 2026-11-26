"""PostgreSQL repositories for runs, bundles, and readiness reports (DDL ``0013``, ``0029``)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final
from uuid import UUID

import psycopg
from psycopg.rows import dict_row

from skm.adapters.postgres.execution.codecs import (
    bundle_from_row,
    readiness_from_row,
    reconfiguration_from_row,
    review_grouping_to_json,
    run_from_row,
)
from skm.adapters.postgres.execution.mapping import (
    opt_aware,
    opt_jsonb,
    require_unchanged,
    validate_readiness_report,
)
from skm.adapters.postgres.execution.mapping import (
    run as run_op,
)
from skm.adapters.postgres.jsonb import require_aware, to_jsonb
from skm.kernel.ids import PlanId, PrincipalId, RevisionId, RunId, WorkspaceId
from skm.modules.execution.domain.execution_bundle import ExecutionBundle, run_selection_to_json
from skm.modules.execution.domain.frozen_json import thaw_json
from skm.modules.execution.domain.health import active_stage_seconds
from skm.modules.execution.domain.ids import ReadinessReportId, StageRecordId
from skm.modules.execution.domain.readiness import ReadinessReport, RevisionVisa
from skm.modules.execution.domain.run import Run
from skm.modules.execution.domain.stored_payloads import (
    config_snapshot_document,
    invalid_ref,
    not_found,
    schema_invalid,
    version_conflict,
    work_policies_document,
)

if TYPE_CHECKING:
    from collections.abc import Sequence
    from datetime import datetime

    from skm.kernel.ids import AttemptId, ProjectId, TaskId
    from skm.modules.execution.ports import ReconfigurationRecord

__all__ = [
    "PostgresBundleRepository",
    "PostgresReadinessRepository",
    "PostgresRunRepository",
]

_RUN_OWNED: Final = (
    "workspace_id",
    "project_id",
    "kind",
    "plan_id",
    "revision_id",
    "revision_no",
    "inline_spec_file_version_id",
    "requested_by",
    "readiness_report_id",
    "audited_report_id",
    "review_request_id",
    "compiler_version",
    "workflow_resource_version_id",
    "review_grouping",
    "created_at",
)

# attempt_stages has no run_id index; the attempts of the run reach the stages through their attempt_id
# index, so the timeout sweep reads the stages of one run instead of scanning those of every run.
_STAGE_INTERVALS: Final = """
SELECT started_at, finished_at FROM skm_execution.attempt_stages
 WHERE attempt_id IN (SELECT a.id FROM skm_execution.attempts a WHERE a.run_id = %s)
   AND run_id = %s AND (%s::uuid IS NULL OR task_id = %s)
   AND (%s::uuid IS NULL OR attempt_id = %s)
   AND (%s::uuid IS NULL OR id = %s)
"""


class PostgresRunRepository:
    def lock_revision_start(self, revision_id: RevisionId, *, audit: bool = False) -> None:
        # Plan starts can share the key. An audit holds it exclusively through publication.
        with self._conn.cursor() as cur:
            if audit:
                cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 1103))", (str(revision_id),))
            else:
                cur.execute(
                    "SELECT pg_advisory_xact_lock_shared(hashtextextended(%s, 1103))", (str(revision_id),)
                )

    def has_active_readiness_audit(self, revision_id: RevisionId) -> bool:
        with self._conn.cursor() as cur:
            cur.execute(
                """SELECT 1 FROM skm_execution.runs
                   WHERE revision_id = %s AND kind = 'readiness_audit'
                   AND status NOT IN ('succeeded', 'failed', 'cancelled') LIMIT 1""",
                (revision_id,),
            )
            return cur.fetchone() is not None

    def now(self) -> datetime:
        with self._conn.cursor() as cur:
            cur.execute("SELECT clock_timestamp()")
            row = cur.fetchone()
            if row is None:
                raise RuntimeError("database clock unavailable")
            return row[0]

    def lock_active(self, run_ids: Sequence[RunId]) -> tuple[Run, ...]:
        with self._conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                """SELECT * FROM skm_execution.runs WHERE id = ANY(%s)
                AND status NOT IN ('succeeded', 'failed', 'cancelled')
                ORDER BY id FOR UPDATE SKIP LOCKED""",
                (list(run_ids),),
            )
            return tuple(run_from_row(row) for row in cur.fetchall())

    def project_has_slot(self, project_id: ProjectId, maximum: int) -> bool:
        with self._conn.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_xact_lock(hashtextextended(%s, 706))", (str(project_id),))
            locked = cur.fetchone()
            if locked is None or not locked[0]:
                return False
            cur.execute(
                "SELECT count(*) FROM skm_execution.runs WHERE project_id=%s AND status='running'",
                (project_id,),
            )
            row = cur.fetchone()
            return row is not None and row[0] < maximum

    def active_seconds(
        self,
        run_id: RunId,
        now: datetime,
        *,
        task_id: TaskId | None = None,
        attempt_id: AttemptId | None = None,
        stage_id: StageRecordId | None = None,
    ) -> float:
        with self._conn.cursor() as cur:
            cur.execute(
                _STAGE_INTERVALS,
                (run_id, run_id, task_id, task_id, attempt_id, attempt_id, stage_id, stage_id),
            )
            intervals = tuple((row[0], row[1]) for row in cur.fetchall())
            cur.execute(
                """SELECT event_type, recorded_at FROM skm_core.domain_events
                WHERE stream_kind='run' AND stream_id=%s ORDER BY stream_seq""",
                (run_id,),
            )
            transitions = tuple((row[0].split(":")[-2], row[1]) for row in cur.fetchall())
        current = self.get(run_id)
        if current.status.value == "paused" and not any(n == "run-paused" for n, _ in transitions):
            transitions += (("run-paused", current.created_at),)
        return active_stage_seconds(intervals, transitions, now)

    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def get(self, run_id: RunId, *, for_update: bool = False) -> Run:
        def _q() -> Run:
            with self._conn.cursor(row_factory=dict_row) as cur:
                if for_update:
                    cur.execute(
                        "SELECT * FROM skm_execution.runs WHERE id = %s FOR UPDATE", (UUID(str(run_id)),)
                    )
                else:
                    cur.execute("SELECT * FROM skm_execution.runs WHERE id = %s", (UUID(str(run_id)),))
                row = cur.fetchone()
            if row is None:
                raise not_found("run", run_id)
            return run_from_row(row)

        return run_op(_q)

    def add(self, run: Run) -> None:
        pause_reason = run.pause_reason if run.pause_source is None or run.pause_reason else run.pause_source

        def _ins() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skm_execution.runs (
                        id, workspace_id, project_id, kind, plan_id, revision_id, revision_no,
                        inline_spec_file_version_id,
                        status, requested_by, readiness_report_id, audited_report_id, review_request_id,
                        compiler_version, workflow_resource_version_id, review_grouping, autopilot, queued,
                        pause_reason, pause_source, stop_code, unmetered_at, row_version,
                        created_at, started_at, finished_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s
                    )
                    """,
                    (
                        UUID(str(run.id)),
                        UUID(str(run.workspace_id)),
                        UUID(str(run.project_id)),
                        run.kind.value,
                        run.plan_id,
                        run.revision_id,
                        run.revision_no,
                        run.inline_spec_file_version_id,
                        run.status.value,
                        UUID(str(run.requested_by)),
                        None if run.readiness_report_id is None else UUID(str(run.readiness_report_id)),
                        None if run.audited_report_id is None else UUID(str(run.audited_report_id)),
                        None if run.review_request_id is None else UUID(str(run.review_request_id)),
                        run.compiler_version,
                        UUID(str(run.workflow_resource_version_id)),
                        to_jsonb(review_grouping_to_json(run.review_grouping)),
                        run.autopilot,
                        run.queued,
                        pause_reason,
                        run.pause_source,
                        run.stop_code,
                        opt_aware(run.unmetered_at),
                        run.row_version,
                        require_aware(run.created_at),
                        opt_aware(run.started_at),
                        opt_aware(run.finished_at),
                    ),
                )

        run_op(_ins)

    def save(self, run: Run, *, expected_version: int) -> None:
        current = self.get(run.id, for_update=True)
        if current.row_version != expected_version:
            raise version_conflict("run", run.id, expected_version, current.row_version)
        require_unchanged("run", current, run, _RUN_OWNED)
        new_ver = run.row_version if run.row_version > expected_version else expected_version + 1
        pause_reason = run.pause_reason if run.pause_source is None or run.pause_reason else run.pause_source

        def _upd() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE skm_execution.runs
                       SET status = %s, autopilot = %s, queued = %s,
                           pause_reason = %s, pause_source = %s, stop_code = %s,
                           unmetered_at = %s, started_at = %s, finished_at = %s, row_version = %s
                     WHERE id = %s AND row_version = %s
                    """,
                    (
                        run.status.value,
                        run.autopilot,
                        run.queued,
                        pause_reason,
                        run.pause_source,
                        run.stop_code,
                        opt_aware(run.unmetered_at),
                        opt_aware(run.started_at),
                        opt_aware(run.finished_at),
                        new_ver,
                        UUID(str(run.id)),
                        expected_version,
                    ),
                )
                if cur.rowcount != 1:
                    raise version_conflict("run", run.id, expected_version, None)

        run_op(_upd)

    def list_active_ids(self, *, limit: int) -> tuple[RunId, ...]:
        def _q() -> tuple[RunId, ...]:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id FROM skm_execution.runs
                     WHERE status NOT IN ('succeeded', 'failed', 'cancelled')
                     ORDER BY created_at ASC, id ASC
                     LIMIT %s
                    """,
                    (limit,),
                )
                return tuple(RunId(row[0]) for row in cur.fetchall())

        return run_op(_q)


class PostgresBundleRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, bundle: ExecutionBundle) -> None:
        cfg_doc = config_snapshot_document(bundle)
        wp_doc = work_policies_document(bundle.work_policies)
        pins_doc = {
            "resources": [
                {
                    "kind": p.kind,
                    "key": p.key,
                    "resource_version_id": str(p.resource_version_id),
                    "digest": p.digest,
                }
                for p in bundle.resource_pins.resources
            ],
            "packs": {k: str(v) for k, v in sorted(bundle.resource_pins.packs.items())},
        }
        sel_doc = None if bundle.selection is None else run_selection_to_json(bundle.selection)

        def _ins() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT workspace_id FROM skm_execution.runs WHERE id = %s",
                    (UUID(str(bundle.run_id)),),
                )
                rrow = cur.fetchone()
                if rrow is None:
                    raise invalid_ref("fk_execution_bundles__runs", run_id=str(bundle.run_id))
                cur.execute(
                    """
                    INSERT INTO skm_execution.execution_bundles (
                        run_id, workspace_id, config_snapshot, config_digest, policy_digest,
                        resource_pins, selection, work_policies, context_policy, review_grouping, created_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        UUID(str(bundle.run_id)),
                        rrow[0],
                        to_jsonb(cfg_doc),
                        bundle.config_digest,
                        bundle.policy_digest,
                        to_jsonb(pins_doc),
                        opt_jsonb(sel_doc),
                        opt_jsonb(wp_doc),
                        to_jsonb(thaw_json(bundle.context_policy)),
                        to_jsonb(review_grouping_to_json(bundle.review_grouping)),
                        require_aware(bundle.created_at),
                    ),
                )

        run_op(_ins)

    def get(self, run_id: RunId) -> ExecutionBundle:
        def _q() -> ExecutionBundle:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.execution_bundles WHERE run_id = %s",
                    (UUID(str(run_id)),),
                )
                row = cur.fetchone()
            if row is None:
                raise not_found("execution_bundle", run_id)
            return bundle_from_row(row)

        return run_op(_q)

    def add_reconfiguration(self, record: ReconfigurationRecord) -> None:
        if not record.changes:
            raise schema_invalid("reconfiguration changes must not be empty", field="changes")
        if not 1 <= len(record.reason) <= 2000:
            raise schema_invalid("reconfiguration reason must be 1..2000 chars", field="reason")

        def _ins() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    "SELECT workspace_id FROM skm_execution.runs WHERE id = %s",
                    (UUID(str(record.run_id)),),
                )
                rrow = cur.fetchone()
                if rrow is None:
                    raise invalid_ref("fk_run_reconfigurations__runs", run_id=str(record.run_id))
                cur.execute(
                    """
                    INSERT INTO skm_execution.run_reconfigurations (
                        id, run_id, workspace_id, changes, reason, changed_by, changed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        record.id,
                        UUID(str(record.run_id)),
                        rrow[0],
                        to_jsonb(thaw_json(record.changes)),
                        record.reason,
                        UUID(str(record.changed_by)),
                        require_aware(record.changed_at),
                    ),
                )

        run_op(_ins)

    def reconfigurations(self, run_id: RunId) -> tuple[ReconfigurationRecord, ...]:
        def _q() -> tuple[ReconfigurationRecord, ...]:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM skm_execution.run_reconfigurations
                     WHERE run_id = %s
                     ORDER BY changed_at ASC, id ASC
                    """,
                    (UUID(str(run_id)),),
                )
                return tuple(reconfiguration_from_row(r) for r in cur.fetchall())

        return run_op(_q)


class PostgresReadinessRepository:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn

    def add(self, report: ReadinessReport) -> None:
        sr_doc, wp_doc = validate_readiness_report(report)

        def _ins() -> None:
            with self._conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO skm_execution.readiness_reports (
                        id, workspace_id, project_id, plan_id, revision_id, revision_digest, status,
                        scope, inputs, inputs_digest, policy_digest, results, findings, assumptions,
                        structural_counts, start_request, work_policies, estimate, audit,
                        supersedes_report_id, validator_version, created_by, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s
                    )
                    """,
                    (
                        UUID(str(report.id)),
                        UUID(str(report.workspace_id)),
                        UUID(str(report.project_id)),
                        UUID(str(report.plan_id)),
                        UUID(str(report.revision_id)),
                        report.revision_digest,
                        report.status.value,
                        to_jsonb({"kind": report.scope.kind, "phase_keys": list(report.scope.phase_keys)}),
                        to_jsonb(
                            {
                                "requirements": report.inputs.requirements,
                                "dependencies": report.inputs.dependencies,
                                "write_scopes": report.inputs.write_scopes,
                                "criteria": report.inputs.criteria,
                                "capability_requirements": report.inputs.capability_requirements,
                                "policy": report.inputs.policy,
                                "config": report.inputs.config,
                                "resources": report.inputs.resources,
                                "materials": report.inputs.materials,
                            }
                        ),
                        report.inputs_digest,
                        report.policy_digest,
                        to_jsonb(
                            [
                                {
                                    "rule_id": r.rule_id,
                                    "outcome": r.outcome,
                                    "findings_count": r.findings_count,
                                }
                                for r in report.results
                            ]
                        ),
                        to_jsonb(
                            [
                                {
                                    "code": f.code,
                                    "severity": f.severity,
                                    "entity_id": None if f.entity_id is None else str(f.entity_id),
                                    "message": f.message,
                                    "rule_id": f.rule_id,
                                }
                                for f in report.findings
                            ]
                        ),
                        to_jsonb(list(report.assumptions)),
                        to_jsonb({str(k): int(v) for k, v in report.structural_counts.items()}),
                        opt_jsonb(sr_doc),
                        opt_jsonb(wp_doc),
                        to_jsonb(thaw_json(report.estimate)),
                        opt_jsonb(report.audit),
                        (
                            None
                            if report.supersedes_report_id is None
                            else UUID(str(report.supersedes_report_id))
                        ),
                        report.validator_version,
                        UUID(str(report.created_by)),
                        require_aware(report.created_at),
                    ),
                )

        run_op(_ins)

    def get(self, report_id: ReadinessReportId) -> ReadinessReport:
        def _q() -> ReadinessReport:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    "SELECT * FROM skm_execution.readiness_reports WHERE id = %s",
                    (UUID(str(report_id)),),
                )
                row = cur.fetchone()
            if row is None:
                raise not_found("readiness_report", report_id)
            return readiness_from_row(row)

        return run_op(_q)

    def add_visa(self, visa: RevisionVisa) -> None:
        def insert() -> None:
            self._conn.execute(
                """INSERT INTO skm_execution.revision_visas
                   (id, workspace_id, plan_id, revision_id, readiness_report_id, selection,
                    signed_by, reason, signed_at)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    visa.id,
                    visa.workspace_id,
                    visa.plan_id,
                    visa.revision_id,
                    visa.readiness_report_id,
                    opt_jsonb(visa.selection),
                    visa.signed_by,
                    visa.reason,
                    require_aware(visa.signed_at),
                ),
            )

        run_op(insert)

    @staticmethod
    def _visa_from_row(row: tuple[Any, ...]) -> RevisionVisa:
        return RevisionVisa(
            row[0],
            WorkspaceId(row[1]),
            PlanId(row[2]),
            RevisionId(row[3]),
            ReadinessReportId(row[4]),
            row[5],
            PrincipalId(row[6]),
            row[7],
            row[8],
        )

    def get_visa(self, visa_id: UUID) -> RevisionVisa:
        def read() -> RevisionVisa:
            row = self._conn.execute(
                """SELECT id, workspace_id, plan_id, revision_id, readiness_report_id, selection, signed_by,
                          reason, signed_at FROM skm_execution.revision_visas WHERE id = %s""",
                (visa_id,),
            ).fetchone()
            if row is None:
                raise not_found("revision_visa", visa_id)
            return self._visa_from_row(row)

        return run_op(read)

    def latest_visa_for(self, revision_id: RevisionId) -> RevisionVisa | None:
        def read() -> RevisionVisa | None:
            row = self._conn.execute(
                """SELECT v.id, v.workspace_id, v.plan_id, v.revision_id, v.readiness_report_id,
                          v.selection, v.signed_by, v.reason, v.signed_at
                     FROM skm_execution.readiness_reports AS r
                     JOIN skm_execution.revision_visas AS v ON v.readiness_report_id = r.id
                    WHERE r.revision_id = %s ORDER BY v.signed_at DESC, v.id DESC LIMIT 1""",
                (revision_id,),
            ).fetchone()
            return None if row is None else self._visa_from_row(row)

        return run_op(read)

    def latest_for(self, revision_id: RevisionId) -> ReadinessReport | None:
        def _q() -> ReadinessReport | None:
            with self._conn.cursor(row_factory=dict_row) as cur:
                cur.execute(
                    """
                    SELECT * FROM skm_execution.readiness_reports
                     WHERE revision_id = %s
                     ORDER BY created_at DESC, id DESC
                     LIMIT 1
                    """,
                    (UUID(str(revision_id)),),
                )
                row = cur.fetchone()
            return None if row is None else readiness_from_row(row)

        return run_op(_q)
