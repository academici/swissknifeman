"""Memory repositories for checks, reviews, findings, fix briefs, and acceptance (DDL ``0015-0016``)."""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import TYPE_CHECKING, Final
from uuid import UUID

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.execution.state import clone_value, execution_state
from skm.modules.execution.domain.check_execution import CheckExecution, CheckState
from skm.modules.execution.domain.ids import StepId
from skm.modules.execution.domain.review import ReviewerKind
from skm.modules.execution.domain.stored_payloads import (
    already_exists,
    field_owned,
    invalid_ref,
    not_found,
    schema_invalid,
)

if TYPE_CHECKING:
    from skm.kernel.ids import EntityId, ProjectId, RunId, TaskId, WorkspaceId
    from skm.modules.execution.domain.acceptance import AcceptanceDecision
    from skm.modules.execution.domain.carry_forward import CarryForward
    from skm.modules.execution.domain.deviation import DeviationAcceptance
    from skm.modules.execution.domain.finding import Finding
    from skm.modules.execution.domain.finding_resolution import FindingResolution
    from skm.modules.execution.domain.fix_brief import FixBrief
    from skm.modules.execution.domain.ids import CheckExecutionId, FixBriefId, OutputId
    from skm.modules.execution.domain.manual_verdict import ManualVerdict
    from skm.modules.execution.domain.review import Review

__all__ = [
    "MemoryAcceptanceRepository",
    "MemoryCheckRepository",
    "MemoryReviewRepository",
]

_DIGEST_RE: Final = re.compile(r"^sha256:[0-9a-f]{64}$")
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


class MemoryCheckRepository:
    def get(self, check_id: CheckExecutionId) -> CheckExecution:
        found = self._state.checks.get(check_id)
        if found is None:
            raise not_found("check_execution", check_id)
        return clone_value(found)

    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _check_refs(self, ex: CheckExecution) -> None:
        att = self._state.attempts.get(ex.attempt_id)
        if att is None or (att.run_id, att.task_id, att.workspace_id) != (
            ex.run_id,
            ex.task_id,
            ex.workspace_id,
        ):
            raise invalid_ref("fk_check_executions__attempts", attempt_id=str(ex.attempt_id))
        out = self._state.outputs.get(ex.output_id)
        if out is None or out.attempt_id != ex.attempt_id:
            raise invalid_ref("fk_check_executions__attempt_outputs", output_id=str(ex.output_id))
        if ex.reused_from_id is not None:
            src = self._state.checks.get(ex.reused_from_id)
            if src is None or src.workspace_id != ex.workspace_id:
                raise invalid_ref("fk_check_executions__reused_from", reused_from_id=str(ex.reused_from_id))

    def add_many(self, executions: Sequence[CheckExecution]) -> None:
        self._backend.core.require_writable()
        staged: dict[CheckExecutionId, CheckExecution] = {}
        seen_keys = {(c.output_id, c.check_spec_id, c.round_no) for c in self._state.checks.values()}
        for ex in executions:
            if ex.id in self._state.checks or ex.id in staged:
                raise already_exists("pk_check_executions", check_execution_id=str(ex.id))
            ukey = (ex.output_id, ex.check_spec_id, ex.round_no)
            if ukey in seen_keys:
                raise already_exists(
                    "uq_check_executions__output_id_check_spec_id_round_no", output_id=str(ex.output_id)
                )
            self._check_refs(ex)
            seen_keys.add(ukey)
            staged[ex.id] = clone_value(ex)
        self._state.checks.update(staged)

    def save(self, execution: CheckExecution) -> None:
        self._backend.core.require_writable()
        cur = self._state.checks.get(execution.id)
        if cur is None:
            raise not_found("check_execution", execution.id)
        for fname in _CHECK_OWNED:
            if getattr(execution, fname) != getattr(cur, fname):
                raise field_owned("check_execution", fname)
        self._check_refs(execution)
        self._state.checks[execution.id] = clone_value(execution)

    def for_output(self, output_id: OutputId) -> tuple[CheckExecution, ...]:
        rows = sorted(
            (c for c in self._state.checks.values() if c.output_id == output_id),
            key=lambda c: (c.round_no, c.check_key, str(c.id)),
        )
        return tuple(clone_value(c) for c in rows)

    def reusable(
        self, workspace_id: WorkspaceId, project_id: ProjectId, fingerprint: str, check_spec_id: EntityId
    ) -> CheckExecution | None:
        run_ids = {r.id for r in self._state.runs.values() if r.project_id == project_id}
        matches = [
            c
            for c in self._state.checks.values()
            if c.workspace_id == workspace_id
            and c.run_id in run_ids
            and c.fingerprint == fingerprint
            and c.check_spec_id == check_spec_id
            and c.state is CheckState.PASSED
            and c.reused_from_id is None
        ]
        if not matches:
            return None
        best = max(matches, key=lambda c: (c.finished_at or c.started_at, str(c.id)))
        return clone_value(best)

    def add_verdict(self, verdict: ManualVerdict) -> None:
        self._backend.core.require_writable()
        if verdict.id in self._state.manual_verdicts:
            raise already_exists("pk_manual_check_verdicts", id=str(verdict.id))
        if verdict.check_execution_id not in self._state.checks:
            raise invalid_ref(
                "fk_manual_check_verdicts__check_executions",
                check_execution_id=str(verdict.check_execution_id),
            )
        if verdict.supersedes_id is not None:
            sup = self._state.manual_verdicts.get(verdict.supersedes_id)
            if sup is None or sup.check_execution_id != verdict.check_execution_id:
                raise invalid_ref(
                    "fk_manual_check_verdicts__supersedes", supersedes_id=str(verdict.supersedes_id)
                )
            if any(v.supersedes_id == verdict.supersedes_id for v in self._state.manual_verdicts.values()):
                raise already_exists(
                    "uq_manual_check_verdicts__supersedes_id", supersedes_id=str(verdict.supersedes_id)
                )
        self._state.manual_verdicts[verdict.id] = clone_value(verdict)

    def verdicts(self, check_execution_id: CheckExecutionId) -> tuple[ManualVerdict, ...]:
        rows = sorted(
            (v for v in self._state.manual_verdicts.values() if v.check_execution_id == check_execution_id),
            key=lambda v: (v.recorded_at, str(v.id)),
        )
        return tuple(clone_value(v) for v in rows)


class MemoryReviewRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def _check_review(self, review: Review) -> None:
        att = self._state.attempts.get(review.attempt_id)
        if att is None or (att.run_id, att.task_id, att.workspace_id) != (
            review.run_id,
            review.task_id,
            review.workspace_id,
        ):
            raise invalid_ref("fk_reviews__attempts", attempt_id=str(review.attempt_id))
        out = self._state.outputs.get(review.output_id)
        if out is None or out.attempt_id != review.attempt_id:
            raise invalid_ref("fk_reviews__attempt_outputs", output_id=str(review.output_id))
        if review.base_output_id is not None:
            bout = self._state.outputs.get(review.base_output_id)
            if bout is None or bout.task_id != review.task_id:
                raise invalid_ref("fk_reviews__base_output", base_output_id=str(review.base_output_id))
        if review.reviewer_kind is ReviewerKind.AGENT:
            sid_raw = review.reviewer_ref.get("step_id")
            if not isinstance(sid_raw, str):
                raise schema_invalid("agent review requires reviewer_ref.step_id")
            try:
                sid = StepId(UUID(sid_raw))
            except ValueError:
                raise schema_invalid("invalid reviewer_ref.step_id") from None
            stp = self._state.steps.get(sid)
            if stp is None or stp.attempt_id != review.attempt_id:
                raise invalid_ref("fk_reviews__attempt_steps", step_id=sid_raw)

    def add(self, review: Review) -> None:
        self._backend.core.require_writable()
        if review.id in self._state.reviews:
            raise already_exists("pk_reviews", review_id=str(review.id))
        if any(
            r.task_id == review.task_id and r.round_no == review.round_no
            for r in self._state.reviews.values()
        ):
            raise already_exists("uq_reviews__task_id_round_no", round_no=review.round_no)
        self._check_review(review)
        self._state.reviews[review.id] = clone_value(review)

    def save(self, review: Review) -> None:
        self._backend.core.require_writable()
        cur = self._state.reviews.get(review.id)
        if cur is None:
            raise not_found("review", review.id)
        for fname in _REVIEW_OWNED:
            if getattr(review, fname) != getattr(cur, fname):
                raise field_owned("review", fname)
        self._check_review(review)
        self._state.reviews[review.id] = clone_value(review)

    def for_task(self, task_id: TaskId) -> tuple[Review, ...]:
        rows = sorted(
            (r for r in self._state.reviews.values() if r.task_id == task_id), key=lambda r: r.round_no
        )
        return tuple(clone_value(r) for r in rows)

    def add_findings(self, findings: Sequence[Finding]) -> None:
        self._backend.core.require_writable()
        seen_local = {(f.review_id, f.local_id) for f in self._state.findings.values()}
        seen_key = {(f.review_id, f.finding_key) for f in self._state.findings.values()}
        staged: list[tuple[Finding, TaskId]] = []
        for f in findings:
            if f.id in self._state.findings or any(x.id == f.id for x, _ in staged):
                raise already_exists("pk_review_findings", finding_id=str(f.id))
            rev = self._state.reviews.get(f.review_id)
            first_rev = self._state.reviews.get(f.first_seen_review_id)
            if rev is None or first_rev is None or first_rev.task_id != rev.task_id:
                raise invalid_ref("fk_review_findings__reviews", review_id=str(f.review_id))
            if (f.review_id, f.local_id) in seen_local:
                raise already_exists("uq_review_findings__review_id_local_id", local_id=f.local_id)
            if (f.review_id, f.finding_key) in seen_key:
                raise already_exists("uq_review_findings__review_id_finding_key", finding_key=f.finding_key)
            seen_local.add((f.review_id, f.local_id))
            seen_key.add((f.review_id, f.finding_key))
            staged.append((clone_value(f), rev.task_id))
        for f, tid in staged:
            self._state.findings[f.id] = f
            self._state.finding_tasks[f.id] = tid

    def save_finding(self, finding: Finding) -> None:
        self._backend.core.require_writable()
        cur = self._state.findings.get(finding.id)
        if cur is None:
            raise not_found("finding", finding.id)
        for fname in _FINDING_OWNED:
            if getattr(finding, fname) != getattr(cur, fname):
                raise field_owned("finding", fname)
        self._state.findings[finding.id] = clone_value(finding)

    def findings_for_task(self, task_id: TaskId) -> tuple[Finding, ...]:
        rev_rounds = {r.id: r.round_no for r in self._state.reviews.values() if r.task_id == task_id}
        rows = sorted(
            (f for f in self._state.findings.values() if f.review_id in rev_rounds),
            key=lambda f: (rev_rounds[f.review_id], f.local_id, str(f.id)),
        )
        return tuple(clone_value(f) for f in rows)

    def add_resolution(self, resolution: FindingResolution) -> None:
        self._backend.core.require_writable()
        if resolution.id in self._state.resolutions:
            raise already_exists("pk_finding_resolutions", id=str(resolution.id))
        tid = self._state.finding_tasks.get(resolution.finding_id)
        if tid is None:
            raise invalid_ref(
                "fk_finding_resolutions__review_findings", finding_id=str(resolution.finding_id)
            )
        if resolution.target_output_id is not None:
            out = self._state.outputs.get(resolution.target_output_id)
            if out is None or out.task_id != tid:
                raise invalid_ref(
                    "fk_finding_resolutions__attempt_outputs",
                    target_output_id=str(resolution.target_output_id),
                )
        self._state.resolutions[resolution.id] = clone_value(resolution)

    def add_fix_brief(self, brief: FixBrief) -> None:
        self._backend.core.require_writable()
        if brief.id in self._state.fix_briefs:
            raise already_exists("pk_fix_briefs", id=str(brief.id))
        att = self._state.attempts.get(brief.attempt_id)
        if att is None or att.task_id != brief.task_id:
            raise invalid_ref("fk_fix_briefs__attempts", attempt_id=str(brief.attempt_id))
        if brief.source_review_id is not None:
            rev = self._state.reviews.get(brief.source_review_id)
            if rev is None or rev.task_id != brief.task_id:
                raise invalid_ref("fk_fix_briefs__reviews", source_review_id=str(brief.source_review_id))
        self._state.fix_briefs[brief.id] = clone_value(brief)

    def get_fix_brief(self, brief_id: FixBriefId) -> FixBrief:
        found = self._state.fix_briefs.get(brief_id)
        if found is None:
            raise not_found("fix_brief", brief_id)
        return clone_value(found)


class MemoryAcceptanceRepository:
    def __init__(self, state: MemoryBackendState) -> None:
        self._backend = state
        self._state = execution_state(state)

    def add_decision(self, decision: AcceptanceDecision) -> None:
        self._backend.core.require_writable()
        if decision.id in self._state.acceptance_decisions:
            raise already_exists("pk_acceptance_decisions", id=str(decision.id))
        task = self._state.tasks.get(decision.task_id)
        if task is None or (task.run_id, task.workspace_id) != (decision.run_id, decision.workspace_id):
            raise invalid_ref("fk_acceptance_decisions__run_tasks", task_id=str(decision.task_id))
        att = self._state.attempts.get(decision.attempt_id)
        if att is None or (att.run_id, att.task_id) != (decision.run_id, decision.task_id):
            raise invalid_ref("fk_acceptance_decisions__attempts", attempt_id=str(decision.attempt_id))
        if decision.output_id is not None:
            out = self._state.outputs.get(decision.output_id)
            if out is None or out.attempt_id != decision.attempt_id:
                raise invalid_ref(
                    "fk_acceptance_decisions__attempt_outputs", output_id=str(decision.output_id)
                )
        self._state.acceptance_decisions[decision.id] = clone_value(decision)

    def decisions_for_task(self, task_id: TaskId) -> tuple[AcceptanceDecision, ...]:
        rows = sorted(
            (d for d in self._state.acceptance_decisions.values() if d.task_id == task_id),
            key=lambda d: (d.decided_at, str(d.id)),
        )
        return tuple(clone_value(d) for d in rows)

    def add_deviation(self, deviation: DeviationAcceptance) -> None:
        self._backend.core.require_writable()
        if deviation.id in self._state.deviations:
            raise already_exists("pk_deviation_acceptances", id=str(deviation.id))
        task = self._state.tasks.get(deviation.task_id)
        if task is None or task.run_id != deviation.run_id:
            raise invalid_ref("fk_deviation_acceptances__run_tasks", task_id=str(deviation.task_id))
        if (
            deviation.finding_id is not None
            and self._state.finding_tasks.get(deviation.finding_id) != task.id
        ):
            raise invalid_ref(
                "fk_deviation_acceptances__review_findings", finding_id=str(deviation.finding_id)
            )
        self._state.deviations[deviation.id] = clone_value(deviation)

    def deviations_for_task(self, task_id: TaskId) -> tuple[DeviationAcceptance, ...]:
        rows = sorted(
            (d for d in self._state.deviations.values() if d.task_id == task_id),
            key=lambda d: (d.approved_at, str(d.id)),
        )
        return tuple(clone_value(d) for d in rows)

    def add_carry_forward(self, carry_forward: CarryForward) -> None:
        self._backend.core.require_writable()
        cf = carry_forward
        if cf.id in self._state.carry_forwards:
            raise already_exists("pk_result_carry_forwards", id=str(cf.id))
        if cf.source_run_id == cf.target_run_id or not _DIGEST_RE.fullmatch(cf.compatibility_digest):
            raise schema_invalid("carry_forward requires distinct runs and sha256 compatibility_digest")
        src_att = self._state.attempts.get(cf.source_attempt_id)
        src_out = self._state.outputs.get(cf.source_output_id)
        tgt_task = self._state.tasks.get(cf.target_task_id)
        if (
            src_att is None
            or (src_att.run_id, src_att.task_id) != (cf.source_run_id, cf.source_task_id)
            or src_out is None
            or src_out.attempt_id != cf.source_attempt_id
            or tgt_task is None
            or tgt_task.run_id != cf.target_run_id
        ):
            raise invalid_ref("fk_result_carry_forwards", id=str(cf.id))
        if cf.decision == "accepted" and any(
            x.target_task_id == cf.target_task_id and x.decision == "accepted"
            for x in self._state.carry_forwards.values()
        ):
            raise already_exists(
                "uq_result_carry_forwards__target_task_id_accepted", target_task_id=str(cf.target_task_id)
            )
        self._state.carry_forwards[cf.id] = clone_value(cf)

    def carry_forwards_for_run(self, run_id: RunId) -> tuple[CarryForward, ...]:
        rows = sorted(
            (c for c in self._state.carry_forwards.values() if c.target_run_id == run_id),
            key=lambda c: (c.created_at, str(c.id)),
        )
        return tuple(clone_value(c) for c in rows)
