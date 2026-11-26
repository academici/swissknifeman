"""Read empirical signals and their retained activity evidence."""

from json import loads
from typing import Any, cast
from uuid import UUID

from skm.application_bus.context import QueryContext
from skm.application_bus.registry import QuerySpec
from skm.kernel.ids import WorkspaceId
from skm.kernel.pagination import Cursor
from skm.kernel.ports_uow import UnitOfWork
from skm.modules.learning.application.commands.extract_candidates import ActivityStorage
from skm.modules.learning.application.commands.review_candidate import require_candidate, workspace_ref
from skm.modules.learning.domain.activity import ActivityRecord, canonical_json, detector_evidence_json
from skm.modules.learning.domain.candidate import CandidateId
from skm.modules.learning.generated.queries import ListSignals
from skm.modules.learning.generated.views import SignalsView, signal_view_from_json
from skm.modules.learning.ports import ActivityRecordRepository, CandidateRepository, SignalRepository


def _view(r: ActivityRecord) -> dict[str, object]:
    return {
        "id": str(r.id),
        "workspace_id": str(r.workspace_id),
        "project_id": str(r.project_id),
        "scope_id": str(r.scope_id),
        "source_kind": r.source_kind.value,
        "source_key": r.source_key,
        "run_id": str(r.run_id) if r.run_id else None,
        "task_id": str(r.task_id) if r.task_id else None,
        "attempt_id": str(r.attempt_id) if r.attempt_id else None,
        "outcome": r.outcome.value,
        "task_outcome": r.task_outcome.value if r.task_outcome else None,
        "observed_at": r.observed_at.isoformat(),
        "pathology_codes": [code.value for code in r.pathology_codes],
        "summary_digest": r.summary_digest,
        "exposure_coverage": r.exposure_coverage,
        "exposed_lesson_refs": [
            {"id": str(ref.id), "version": ref.version, "content_digest": ref.content_digest}
            for ref in r.exposed_lesson_refs
        ],
        "detector_evidence": loads(
            canonical_json([detector_evidence_json(bundle) for bundle in r.detector_evidence])
        ),
    }


def handle(cmd: dict[str, Any], _ctx: QueryContext, uow: UnitOfWork) -> SignalsView:
    candidate = require_candidate(
        uow.repo(CandidateRepository),
        CandidateId(UUID(cmd["candidate_id"])),
        WorkspaceId(UUID(cmd["workspace_id"])),
    )
    records = cast("ActivityStorage", uow.repo(ActivityRecordRepository))
    after = cmd.get("after")
    page = uow.repo(SignalRepository).list(
        candidate.id, after=Cursor(after) if after else None, limit=cmd.get("limit", 100)
    )
    return SignalsView(
        items=[
            signal_view_from_json(
                {
                    "signal_id": str(s.id),
                    "source": s.source,
                    "observed_at": s.observed_at.isoformat(),
                    "sessions_known": s.sessions_known,
                    "sessions_success": s.sessions_success,
                    "evidence_dependency": s.evidence_dependency,
                    "tests_total": s.tests_total,
                    "tests_passed": s.tests_passed,
                    "activity": _view(activity),
                }
            )
            for s in page.items
            if (activity := records.get(s.activity_record_id)).project_id == candidate.project_id
            and activity.workspace_id == candidate.workspace_id
        ],
        next_cursor=page.next,
        has_more=page.next is not None,
    )


SPEC = QuerySpec(
    name="learning.list_signals",
    dto=cast("type[dict[str, Any]]", ListSignals),
    result=SignalsView,
    permission="lesson.read",
    scope_of=lambda cmd: workspace_ref(cmd["workspace_id"]),
    handler=handle,
)
