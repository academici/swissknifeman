"""Fixtures for empirical activity foreign keys."""

from skm.kernel.ports_uow import UnitOfWork
from skm.modules.learning.domain.activity import ActivityRecord, Outcome, SourceKind
from skm.modules.learning.domain.candidate import Candidate, Signal
from skm.modules.learning.ports import ActivityRecordRepository


def add_activity(uow: UnitOfWork, candidate: Candidate, signal: Signal) -> None:
    assert uow.repo(ActivityRecordRepository).add(
        ActivityRecord(
            signal.activity_record_id,
            candidate.workspace_id,
            candidate.project_id,
            candidate.scope_id,
            SourceKind.CLIENT_SESSION,
            f"test:{signal.activity_record_id}",
            None,
            None,
            None,
            Outcome.UNKNOWN,
            signal.observed_at,
            (),
            "sha256:" + "0" * 64,
            None,
            "unknown",
            (),
            (),
        )
    )
