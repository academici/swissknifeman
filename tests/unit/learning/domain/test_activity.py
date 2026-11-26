"""Activity identity, availability and evidence limits."""

from dataclasses import replace
from datetime import UTC, datetime
from hashlib import sha256
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed
from skm.kernel.ids import ProjectId, ScopeId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.learning.domain.activity import (
    ACTIVITY_SCHEMA,
    DEFAULT_SETTINGS,
    MAX_DETECTOR_EVIDENCE_BYTES,
    ActivityRecord,
    ActivityRecordId,
    ActivitySummary,
    canonical_json,
    detector_evidence_json,
    validate_detector_evidence,
)
from skm.modules.learning.domain.detectors import extract_with_evidence
from skm.modules.learning.domain.evidence import DetectorEvidence, ExposedLessonRef

ID = UUID(int=1)


def test_missing_metrics_are_unknown_and_digest_is_canonical() -> None:
    wire: JsonObject = {
        "schema": ACTIVITY_SCHEMA,
        "source_kind": "attempt",
        "source_key": "работа",
        "outcome": "failure",
        "observed_at": "2026-10-25T13:40:00+00:00",
        "task_outcome": "success",
        "top_rereads": [],
        "reads_total": 0,
    }
    summary = ActivitySummary.from_json(wire)
    assert summary.reads_total == 0
    assert summary.reads_unique is None
    assert summary.top_rereads == ()
    assert summary.error_loops is None
    assert summary.checks is None
    assert summary.exposed_lesson_refs is None
    assert summary.exposure_coverage == "unknown"
    assert summary.observed_at == datetime(2026, 10, 25, 13, 40, tzinfo=UTC)
    assert ActivitySummary.from_json(summary.to_json()) == summary
    assert summary.summary_digest == "sha256:" + sha256(canonical_json(summary.to_json())).hexdigest()
    assert summary.summary_digest == ActivitySummary.from_json({**wire, "reads_unique": None}).summary_digest
    assert summary.summary_digest != replace(summary, checks=()).summary_digest


def test_exposure_requires_complete_lineage_and_known_refs() -> None:
    summary = ActivitySummary.from_json(
        {
            "schema": ACTIVITY_SCHEMA,
            "source_kind": "attempt",
            "source_key": "s",
            "outcome": "success",
            "observed_at": "2026-10-25T13:40:00Z",
        }
    )
    ref = ExposedLessonRef(ID, "v1", "sha256:" + "0" * 64)

    def record(activity: ActivitySummary) -> ActivityRecord:
        return ActivityRecord.from_summary(
            activity,
            id=ActivityRecordId(ID),
            workspace_id=WorkspaceId(ID),
            project_id=ProjectId(ID),
            scope_id=ScopeId(ID),
            pathology_codes=(),
            detector_evidence=(),
        )

    assert record(replace(summary, exposure_coverage="complete")).evidence_dependency == "unknown"
    assert record(replace(summary, exposed_lesson_refs=())).evidence_dependency == "unknown"
    assert (
        record(replace(summary, exposure_coverage="complete", exposed_lesson_refs=())).evidence_dependency
        == "independent"
    )
    assert (
        record(replace(summary, exposure_coverage="complete", exposed_lesson_refs=(ref,))).evidence_dependency
        == "exposed"
    )
    overflow = replace(summary, exposure_coverage="complete", exposed_lesson_refs=(ref,) * 2001)
    assert record(overflow).exposure_coverage == "unknown"


def test_evidence_byte_budget_applies_to_the_full_utf8_bundle() -> None:
    bundle = DetectorEvidence("v1", ACTIVITY_SCHEMA, {}, {}, (), {}, "unknown", None, {}, {}, (), "")
    overhead = len(canonical_json([detector_evidence_json(bundle)]))
    exact = replace(bundle, suggested_investigation="a" * (MAX_DETECTOR_EVIDENCE_BYTES - overhead))
    validate_detector_evidence((exact,))
    with pytest.raises(ValidationFailed) as error:
        validate_detector_evidence((exact, bundle))
    assert error.value.code is ErrorCode.SCHEMA_INVALID

    summary = ActivitySummary.from_json(
        {
            "schema": ACTIVITY_SCHEMA,
            "source_kind": "attempt",
            "source_key": "s",
            "outcome": "success",
            "observed_at": "2026-10-25T13:40:00Z",
            "workarounds": ["я" * 33_000],
        }
    )
    with pytest.raises(ValidationFailed) as error:
        extract_with_evidence(summary, {}, DEFAULT_SETTINGS)
    assert error.value.code is ErrorCode.SCHEMA_INVALID
