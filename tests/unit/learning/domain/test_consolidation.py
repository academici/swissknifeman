"""Exact consolidation, proposal projection and human decisions."""

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.modules.knowledge.public import LessonId, LessonKind
from skm.modules.learning.domain.activity import DEFAULT_SETTINGS, ActivityRecordId
from skm.modules.learning.domain.candidate import (
    Candidate,
    CandidateId,
    CandidateState,
    ConfidenceTier,
    Signal,
    SignalId,
)
from skm.modules.learning.domain.confidence import aggregate
from skm.modules.learning.domain.consolidation import (
    ConsolidationAction,
    classify_consolidation,
    fingerprint,
    shortlist,
)
from skm.modules.learning.domain.detectors import Detector, Observation
from skm.modules.learning.domain.events import (
    CANDIDATE_STREAM_KIND,
    candidate_extracted_payload,
    candidate_promoted_payload,
    candidate_reviewed_payload,
    candidate_state_changed_payload,
)
from skm.modules.learning.domain.promotion import (
    require_human,
    validate_promotion,
)
from skm.modules.learning.domain.recompute import recompute
from skm.modules.learning.domain.review import (
    CandidateProposal,
    CandidateProposalId,
    CandidateReview,
    CandidateReviewId,
    ReviewVerdict,
    proposed_update,
    review_status,
    validate_review,
)
from skm.modules.learning.domain.tokens import jaccard

ID = UUID(int=1)
WHEN = datetime(2026, 11, 10, tzinfo=UTC)
HUMAN = Actor(PrincipalId(ID), PrincipalKind.HUMAN, "Reviewer")


def candidate(
    trigger: str, action: str, *, index: int = 1, kind: LessonKind = LessonKind.GOTCHA
) -> Candidate:
    return Candidate(
        id=CandidateId(UUID(int=index)),
        workspace_id=WorkspaceId(ID),
        project_id=ProjectId(ID),
        scope_id=ScopeId(ID),
        display_key=f"LC-{index}",
        detector=Detector.WORKAROUND,
        pathology_code=None,
        kind=kind,
        trigger=trigger,
        action=action,
        review_hint=None,
        meta={},
        evidence=(),
        fingerprint=fingerprint(kind, trigger, action),
        state=CandidateState.CANDIDATE,
        s_total=20,
        n_total=20,
        known_outcome_total=20,
        unknown_outcome_total=0,
        independent_known_total=20,
        independent_success_total=20,
        exposed_total=0,
        exposure_unknown_total=0,
        tests_total=30,
        tests_passed=21,
        days_since=1,
        support_score=0.603,
        freshness=0.95,
        stale=False,
        review_status="unreviewed",
        confidence=0.573,
        confidence_tier=ConfidenceTier.MODERATE,
        curated_ready=False,
        conflicts_with_id=None,
        proposed_update=None,
        lesson_id=None,
        recomputed_at=WHEN,
        row_version=1,
    )


def observation(trigger: str, action: str, kind: LessonKind = LessonKind.GOTCHA) -> Observation:
    return Observation(
        Detector.WORKAROUND, None, kind, trigger, action, (), 0, 0, {}, None, "diagnostic_hypothesis"
    )


@pytest.mark.parametrize("state", list(CandidateState))
def test_exact_lookup_ignores_shortlist_and_only_reopens_deprecated(state: CandidateState) -> None:
    old = replace(candidate("Café есть\nTLS", "  run pytest "), state=state)
    obs = observation(" Cafe\u0301 есть\r\nTLS\r", "run pytest")
    assert old.fingerprint == fingerprint(obs.kind, obs.trigger, obs.action)
    result = classify_consolidation(obs, (), exact=old)
    assert result.action is ConsolidationAction.NOOP
    assert result.target_id == old.id
    assert result.state is (CandidateState.OBSERVED if state is CandidateState.DEPRECATED else state)


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Не отключать TLS", "Отключать TLS"),  # noqa: RUF001 - intentional Cyrillic test data
        ("stop → delete", "delete → stop"),
        ("push only after approval", "approval only after push"),
        ("Run pytest", "run pytest"),
        ("set  value", "set value"),
        ("Все", "Всё"),  # noqa: RUF001 - intentional Cyrillic test data
    ],
)
def test_similar_wording_gets_separate_candidate(left: str, right: str) -> None:
    old = candidate("When checking TLS settings", left)
    obs = observation(old.trigger, right)
    matches = shortlist(obs, (old,))
    assert len(matches) == 1
    assert matches[0].asim == jaccard(left, right)
    result = classify_consolidation(obs, matches)
    assert result.action in (ConsolidationAction.UPDATE, ConsolidationAction.CONFLICT)
    assert result.conflicts_with_id == old.id
    assert result.state is CandidateState.OBSERVED
    assert (old.independent_success_total, old.independent_known_total) == (20, 20)


def test_signals_from_two_candidates_cannot_pool_to_reach_candidate() -> None:
    first = replace(candidate("When checking TLS", "Enable TLS"), state=CandidateState.OBSERVED)
    second = replace(candidate(first.trigger, "Disable TLS", index=2), state=CandidateState.OBSERVED)
    rows = tuple(
        Signal(
            SignalId(UUID(int=i)),
            first.id if i < 10 else second.id,
            ActivityRecordId(UUID(int=i)),
            "extract",
            1,
            1,
            1,
            "independent",
            1,
            1,
            WHEN,
        )
        for i in range(20)
    )
    for current, own in ((first, rows[:10]), (second, rows[10:])):
        updated, transition = recompute(current, iter(own), now=WHEN, project_sessions=20, t=DEFAULT_SETTINGS)
        assert updated.independent_success_total == updated.independent_known_total == 10
        assert updated.state is transition.state is CandidateState.OBSERVED

    with pytest.raises(ValueError, match="multiple candidates"):
        aggregate(iter(rows), WHEN)
    for foreign in (rows[10:], rows):
        with pytest.raises(ValidationFailed, match="belong to the candidate") as error:
            recompute(first, iter(foreign), now=WHEN, project_sessions=20, t=DEFAULT_SETTINGS)
        assert error.value.code is ErrorCode.SCHEMA_INVALID


def test_collision_and_kind_check() -> None:
    obs = observation("When TLS fails", "Inspect logs")
    other = candidate(obs.trigger, obs.action, kind=LessonKind.PROCEDURE)
    assert classify_consolidation(obs, shortlist(obs, (other,))).action is ConsolidationAction.UPDATE
    collision = replace(other, fingerprint=fingerprint(obs.kind, obs.trigger, obs.action))
    with pytest.raises(Conflict) as error:
        classify_consolidation(obs, (), exact=collision)
    assert error.value.code is ErrorCode.ID_CONFLICT


def test_add_conflict_and_stable_shortlist_order() -> None:
    obs = observation("When TLS verification fails", "Read logs")
    targets = (
        candidate(obs.trigger, "Check certificates", index=1),
        candidate(obs.trigger, "Inspect proxy", index=2),
    )
    first = min(targets, key=lambda item: item.fingerprint)
    for order in (targets, targets[::-1]):
        matches = shortlist(obs, order)
        assert matches[0].candidate == first
        assert classify_consolidation(obs, matches).action is ConsolidationAction.CONFLICT
    assert (
        classify_consolidation(obs, shortlist(obs, (candidate("Unrelated", "Retry"),))).action
        is ConsolidationAction.ADD
    )


def test_pending_proposals_use_observed_at_and_human_resolution() -> None:
    target = candidate("When TLS verification fails", "Read logs")
    older = CandidateProposal(
        CandidateProposalId(ID),
        target.scope_id,
        target.id,
        CandidateId(UUID(int=2)),
        ActivityRecordId(ID),
        "one",
        WHEN,
        WHEN + timedelta(days=3),
        target.kind,
        target.trigger,
        "Inspect certificates",
        "fp1",
        "v1",
        "update",
    )
    newer = replace(
        older,
        id=CandidateProposalId(UUID(int=2)),
        observed_at=WHEN + timedelta(days=1),
        received_at=WHEN + timedelta(days=1),
        source_key="two",
        action="Read the proxy logs",
        fingerprint="fp2",
    )
    reject = CandidateReview(
        CandidateReviewId(ID),
        target.id,
        HUMAN.principal_id,
        PrincipalKind.HUMAN,
        ReviewVerdict.REJECT,
        None,
        None,
        None,
        None,
        newer.id,
        WHEN + timedelta(days=4),
    )
    for ordered in ((older, newer), (newer, older)):
        assert proposed_update(ordered, ()) == newer
        assert proposed_update(ordered, (reject,)) == older
    worker_approve = replace(
        reject, verdict=ReviewVerdict.APPROVE, proposal_id=None, reviewer_kind=PrincipalKind.WORKER
    )
    human_approve = replace(worker_approve, reviewer_kind=PrincipalKind.HUMAN)
    assert review_status((worker_approve, reject)) == "unreviewed"
    assert review_status((human_approve, reject)) == "approved"


def test_human_promotion_prerequisites_and_event_payloads() -> None:
    c = candidate("After changes", "Run checks")
    for kind in (PrincipalKind.SERVICE, PrincipalKind.WORKER):
        actor = replace(HUMAN, kind=kind)
        with pytest.raises(Forbidden) as error:
            require_human(actor)
        assert error.value.code is ErrorCode.FORBIDDEN
        assert error.value.details == {"reason": "human_gate"}
        validate_review(actor, ReviewVerdict.APPROVE)
        with pytest.raises(Forbidden):
            validate_review(actor, ReviewVerdict.EDIT)
    validate_promotion(c, HUMAN)
    observed = replace(c, state=CandidateState.OBSERVED, conflicts_with_id=CandidateId(UUID(int=2)))
    with pytest.raises(PreconditionFailed) as error:
        validate_promotion(observed, HUMAN, override_low_confidence=True, override_reason="Manually verified")
    assert error.value.code is ErrorCode.INVALID_TRANSITION
    assert error.value.details["reason"] == "conflict_unresolved"
    validate_promotion(
        observed,
        HUMAN,
        override_low_confidence=True,
        override_reason="Manually verified",
        resolve_conflict="keep_both",
    )

    payloads = (
        candidate_extracted_payload(
            c.id, c.project_id, c.detector, c.pathology_code, ConsolidationAction.ADD, None
        ),
        candidate_state_changed_payload(
            c.id, CandidateState.OBSERVED, CandidateState.CANDIDATE, "numeric_gate"
        ),
        candidate_reviewed_payload(c.id, CandidateReviewId(ID), ReviewVerdict.APPROVE, HUMAN.principal_id),
        candidate_promoted_payload(c.id, LessonId(ID), HUMAN.principal_id, override_low_confidence=False),
    )
    assert CANDIDATE_STREAM_KIND == "candidate"
    for payload in payloads:
        assert payload["candidate_id"] == str(c.id)
        assert {"trigger", "action"}.isdisjoint(payload)
