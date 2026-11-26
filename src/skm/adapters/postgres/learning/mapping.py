"""PostgreSQL codecs and cursor handling for learning rows."""

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from json import dumps
from typing import Any
from uuid import UUID

import psycopg

from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.pagination import Cursor, validate_page_limit
from skm.modules.knowledge.ports import start_after
from skm.modules.knowledge.public import EvidenceRef, LessonKind
from skm.modules.learning.domain.activity import (
    ActivityRecord,
    Outcome,
    SourceKind,
    detector_evidence_from_json,
)
from skm.modules.learning.domain.candidate import Candidate, CandidateState, ConfidenceTier
from skm.modules.learning.domain.detectors import Detector
from skm.modules.learning.domain.evidence import ExposedLessonRef
from skm.modules.learning.domain.pathology import PathologyCode
from skm.modules.learning.domain.review import CandidateProposal, CandidateReview, ReviewVerdict

__all__: list[str] = []

type Row = dict[str, Any]


def run[T](action: Callable[[], T]) -> T:
    try:
        return action()
    except psycopg.Error as exc:
        raise translate_pg_error(exc) from exc


def rows(query: Callable[[], psycopg.Cursor[tuple[Any, ...]]]) -> list[Row]:
    cursor = run(query)
    columns = tuple(column.name for column in cursor.description or ())
    return [dict(zip(columns, row, strict=True)) for row in run(cursor.fetchall)]


def activity_from_row(row: Row) -> ActivityRecord:
    values = {key: value for key, value in row.items() if key != "created_at"}
    values.update(
        source_kind=SourceKind(row["source_kind"]),
        outcome=Outcome(row["outcome"]),
        task_outcome=None if row["task_outcome"] is None else Outcome(row["task_outcome"]),
        pathology_codes=tuple(PathologyCode(code) for code in row["pathology_codes"]),
        exposed_lesson_refs=tuple(
            ExposedLessonRef(UUID(ref["id"]), ref["version"], ref["content_digest"])
            for ref in row["exposed_lesson_refs"]
        ),
        detector_evidence=tuple(detector_evidence_from_json(e) for e in row["detector_evidence"]),
    )
    return ActivityRecord(**values)


def candidate_from_row(row: Row) -> Candidate:
    values = {key: value for key, value in row.items() if key not in {"created_at", "updated_at"}}
    values.update(
        detector=Detector(row["detector"]),
        kind=LessonKind(row["kind"]),
        pathology_code=None if row["pathology_code"] is None else PathologyCode(row["pathology_code"]),
        state=CandidateState(row["state"]),
        confidence_tier=ConfidenceTier(row["confidence_tier"]),
        evidence=tuple(EvidenceRef(**ref) for ref in row["evidence"]),
        review_status="unreviewed",
        proposed_update=None,
    )
    return Candidate(**values)


def review_from_row(row: Row) -> CandidateReview:
    return CandidateReview(
        id=row["id"],
        candidate_id=row["candidate_id"],
        reviewer_id=row["reviewer_id"],
        reviewer_kind=PrincipalKind(row["reviewer_kind"]),
        verdict=ReviewVerdict(row["verdict"]),
        note=row["note"],
        edited_trigger=row["edited_trigger"],
        edited_action=row["edited_action"],
        edited_kind=LessonKind(row["edited_kind"]) if row["edited_kind"] is not None else None,
        proposal_id=row["proposal_id"],
        created_at=row["created_at"],
    )


def proposal_view(proposal: CandidateProposal) -> Row:
    # Proposals are frozen dataclasses, including only scalar values.
    data = asdict(proposal)
    return {
        key: str(value)
        if isinstance(value, UUID)
        else value.isoformat()
        if isinstance(value, datetime)
        else value.value
        if isinstance(value, StrEnum)
        else value
        for key, value in data.items()
    } | {"status": "pending"}


def paging(after: Cursor | None, limit: int, filters: Row) -> tuple[str, datetime | None, UUID | None]:
    try:
        validate_page_limit(limit, maximum=200)
    except (TypeError, ValueError) as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid learning page limit") from exc
    fingerprint = sha256(dumps(filters, sort_keys=True).encode()).hexdigest()[:16]
    when, row_id = start_after(after, fingerprint)
    return fingerprint, when, row_id
