"""In-memory counterparts to the learning table constraints."""

import json
import re
from dataclasses import asdict
from decimal import Decimal

from skm.adapters.memory.core.state import MemoryBackendState
from skm.adapters.memory.workspace.state import workspace_state
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import ValidationFailed, error_for
from skm.modules.learning.domain.activity import ActivityRecord, Outcome, SourceKind, detector_evidence_json
from skm.modules.learning.domain.candidate import Candidate, CandidateState, ConfidenceTier, Signal
from skm.modules.learning.domain.detectors import Detector
from skm.modules.learning.domain.pathology import PathologyCode
from skm.modules.learning.domain.review import CandidateProposal, CandidateReview, ReviewVerdict

__all__: list[str] = []

_KINDS = {"heuristic", "procedure", "gotcha"}
_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")


def check(valid: bool, field: str) -> None:
    if not valid:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid learning record", details={"field": field})


def reference(valid: bool, field: str) -> None:
    if not valid:
        raise error_for(ErrorCode.INVALID_REFERENCE, "Invalid learning reference", details={"field": field})


def project_scope(state: MemoryBackendState, row: Candidate | ActivityRecord) -> None:
    project = workspace_state(state).projects.get(row.project_id)
    reference(project is not None and project.workspace_id == row.workspace_id, "project_id")
    reference(row.scope_id in state.core.scopes, "scope_id")


def _json_size(value: object) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, allow_nan=False).encode())
    except (TypeError, ValueError) as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid learning JSON") from exc


def _jsonb_text_size(value: object) -> int:
    """Count JSONB text bytes, including PostgreSQL's expansion of exponent notation."""
    try:
        encoded = json.dumps(value, ensure_ascii=False, allow_nan=False)
        size = len(encoded.encode())

        def expand_number(token: str) -> None:
            nonlocal size
            number = Decimal(token)
            size += len(format(number if number else number.copy_abs(), "f")) - len(token)

        json.loads(encoded, parse_float=expand_number)
    except (TypeError, ValueError) as exc:
        raise ValidationFailed(ErrorCode.SCHEMA_INVALID, "Invalid learning JSON") from exc
    return size


def activity_checks(row: ActivityRecord) -> None:
    attempt = row.source_kind == SourceKind.ATTEMPT
    valid_source = (
        row.run_id is not None
        and row.task_id is not None
        and row.attempt_id is not None
        and row.source_key == str(row.attempt_id)
        if attempt
        else row.source_kind == SourceKind.CLIENT_SESSION
        and row.attempt_id is None
        and re.fullmatch(r"[a-z][a-z0-9_]{1,31}:\S{1,200}", row.source_key) is not None
    )
    check(valid_source, "source_key")
    check(row.outcome in set(Outcome) and row.task_outcome in {*Outcome, None}, "outcome")
    check(row.exposure_coverage in {"complete", "unknown"}, "exposure_coverage")
    check(set(row.pathology_codes) <= set(PathologyCode), "pathology_codes")
    check(_DIGEST.fullmatch(row.summary_digest) is not None, "summary_digest")
    check(
        _json_size([detector_evidence_json(e) for e in row.detector_evidence]) <= 65536, "detector_evidence"
    )


def _wording(row: Candidate | CandidateProposal) -> None:
    check(row.kind in _KINDS and 1 <= len(row.trigger) <= 500 and 1 <= len(row.action) <= 1000, "wording")
    check(_DIGEST.fullmatch(row.fingerprint) is not None, "fingerprint")


def candidate_checks(row: Candidate) -> None:
    _wording(row)
    check(re.fullmatch(r"LC-[1-9][0-9]*", row.display_key) is not None, "display_key")
    check(row.detector in set(Detector), "detector")
    check(
        (row.detector == Detector.PATHOLOGY) == (row.pathology_code is not None)
        and row.pathology_code in {None, "file_reread", "tool_error_loop", "no_verify", "protected_write"},
        "pathology_code",
    )
    check(row.review_hint is None or len(row.review_hint) <= 300, "review_hint")
    check(_jsonb_text_size(dict(row.meta)) < 16384, "meta")
    check(len(row.evidence) <= 50 and _json_size([asdict(e) for e in row.evidence]) >= 2, "evidence")
    check(
        row.state in set(CandidateState)
        and (row.state == CandidateState.PROMOTED) == (row.lesson_id is not None),
        "state",
    )
    check(row.conflicts_with_id != row.id, "conflicts_with_id")
    check(
        row.known_outcome_total + row.unknown_outcome_total == row.n_total
        and 0 <= row.s_total <= row.known_outcome_total
        and 0 <= row.independent_success_total <= row.s_total
        and row.independent_success_total <= row.independent_known_total <= row.known_outcome_total
        and min(row.unknown_outcome_total, row.exposed_total, row.exposure_unknown_total, row.days_since) >= 0
        and row.independent_known_total + row.exposed_total + row.exposure_unknown_total <= row.n_total
        and 0 <= row.tests_passed <= row.tests_total,
        "counters",
    )
    check(
        0 <= row.confidence < 1
        and 0 <= row.support_score < 1
        and 0 <= row.freshness <= 1
        and row.confidence_tier in set(ConfidenceTier),
        "confidence",
    )


def signal_checks(row: Signal) -> None:
    check(
        row.source == "extract" and row.evidence_dependency in {"independent", "exposed", "unknown"}, "source"
    )
    check(
        row.sessions_total == 1
        and row.sessions_known in {0, 1}
        and 0 <= row.sessions_success <= row.sessions_known
        and 0 <= row.tests_passed <= row.tests_total,
        "counters",
    )


def proposal_checks(row: CandidateProposal) -> None:
    _wording(row)
    check(row.candidate_id != row.source_candidate_id, "source_candidate_id")
    check(row.relation in {"update", "conflict"} and 1 <= len(row.detector_version) <= 100, "relation")


def review_checks(row: CandidateReview) -> None:
    check(
        row.reviewer_kind in {"human", "service", "worker"} and row.verdict in set(ReviewVerdict), "verdict"
    )
    check(
        row.reviewer_kind == "human" or row.verdict in {ReviewVerdict.APPROVE, ReviewVerdict.COMMENT},
        "verdict",
    )
    check(row.note is None or len(row.note) <= 2000, "note")
    check(
        (row.verdict == ReviewVerdict.EDIT)
        == any(v is not None for v in (row.edited_trigger, row.edited_action, row.edited_kind))
        and row.edited_kind in {*_KINDS, None},
        "edit",
    )
