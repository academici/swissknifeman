"""Learning curation through the command bus and real memory UoW."""

from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from itertools import count
from json import loads
from pathlib import Path
from threading import Barrier
from typing import Any, Literal
from uuid import UUID, uuid4

import pytest

from contracts.knowledge.harness import KnowledgeSide
from contracts.learning.support import add_activity
from integration.artifacts.test_upload_flow import (
    OWNER_ID,
    SEED,
    audit_rows,
    dispatch_new,
    open_test_app,
    seed_principals,
)
from skm.adapters.memory.learning.reviews import MemoryCandidateReviewRepository
from skm.application_bus.ports import EventReader
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import (
    Conflict,
    Forbidden,
    InternalError,
    NotFound,
    PreconditionFailed,
    ValidationFailed,
)
from skm.kernel.events import EventEnvelope
from skm.kernel.ids import PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import Role
from skm.modules.knowledge.ports import LessonRepository
from skm.modules.knowledge.public import LessonApplicability, LessonId, LessonState
from skm.modules.learning.domain.activity import ActivityRecordId
from skm.modules.learning.domain.candidate import Candidate, CandidateState, Signal, SignalId
from skm.modules.learning.domain.review import CandidateProposal, CandidateProposalId, CandidateReview
from skm.modules.learning.ports import (
    CandidateProposalRepository,
    CandidateRepository,
    CandidateReviewRepository,
    SignalRepository,
)
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from unit.learning.domain.test_consolidation import candidate

_REVIEWER = {
    PrincipalKind.SERVICE: PrincipalId(UUID(int=31)),
    PrincipalKind.WORKER: PrincipalId(UUID(int=32)),
}
_REVIEWED = "urn:skm:learning:event:candidate-reviewed:v1"
_STATE_CHANGED = "urn:skm:learning:event:candidate-state-changed:v1"


@pytest.fixture
def side(tmp_path: Path) -> Iterator[KnowledgeSide]:
    app, clock, _ = open_test_app("memory", tmp_path)
    try:
        owner = seed_principals(
            app,
            "memory",
            (
                (OWNER_ID, PrincipalKind.HUMAN, "owner"),
                *((pid, kind, kind.value) for kind, pid in _REVIEWER.items()),
            ),
            (
                (SEED.instance_id, OWNER_ID, Role.OWNER),
                *((SEED.instance_id, pid, Role.OWNER) for pid in _REVIEWER.values()),
            ),
        )
        client = app.client(actor=owner, surface=Surface.TEST)
        workspace = WorkspaceId(
            dispatch_new(client, CreateWorkspace(slug="learning", title="Learning")).workspace_id
        )
        project = ProjectId(
            dispatch_new(
                client, CreateProject(workspace_id=workspace, slug="initial", title="Initial")
            ).project_id
        )
        yield KnowledgeSide("memory", app, clock, owner, workspace, project, count(1))
    finally:
        app.close()


def _dispatch(
    side: KnowledgeSide,
    name: str,
    args: dict[str, Any],
    *,
    key: str | None = None,
    actor: Actor | None = None,
) -> Any:
    spec = side.app.bus._registry.command_by_name(f"learning.{name}")
    return side.app.bus.dispatch(
        spec.dto.from_json(args),
        actor=actor or side.owner,
        meta=side.meta(key or f"learning-{next(side.requests)}"),
    )


def _command(row: Candidate, **fields: Any) -> dict[str, Any]:
    return {
        "workspace_id": str(row.workspace_id),
        "candidate_id": str(row.id),
        "expected_row_version": row.row_version,
        **fields,
    }


def _new_candidate(side: KnowledgeSide, index: int, **overrides: Any) -> Candidate:
    return replace(
        candidate("After changes", f"Run checks #{index}", index=index),
        **{
            "workspace_id": side.workspace,
            "project_id": side.project,
            "scope_id": ScopeId(side.project),
            **overrides,
        },
    )


def _signal(row: Candidate, side: KnowledgeSide, *, days: int = 0) -> Signal:
    return Signal(
        SignalId(uuid4()),
        row.id,
        ActivityRecordId(uuid4()),
        "extract",
        1,
        1,
        1,
        "independent",
        1,
        1,
        side.clock.now() - timedelta(days=days),
    )


def _seed(side: KnowledgeSide, *rows: Candidate) -> None:
    with side.uow() as uow:
        for row in rows:
            uow.repo(CandidateRepository).add(row)
        uow.commit()


def _get(side: KnowledgeSide, row: Candidate) -> Candidate:
    with side.uow(readonly=True) as uow:
        return uow.repo(CandidateRepository).get(row.id)


def _lesson_id(result: Any) -> LessonId:
    return LessonId(UUID(result["lesson_id"]))


def _events(side: KnowledgeSide, *types: str) -> tuple[EventEnvelope, ...]:
    with side.uow(readonly=True) as uow:
        return uow.repo(EventReader).after_workspace_seq(side.workspace, 0, types=frozenset(types), limit=20)


@pytest.mark.parametrize("kind", [PrincipalKind.SERVICE, PrincipalKind.WORKER])
def test_advisory_review_is_idempotent_and_never_satisfies_promotion_gate(
    side: KnowledgeSide, kind: PrincipalKind
) -> None:
    row = _new_candidate(side, 1, state=CandidateState.OBSERVED)
    _seed(side, row)
    actor = Actor(_REVIEWER[kind], kind, kind.value)
    args = _command(row, verdict="approve")
    first = _dispatch(side, "review_candidate", args, key="review", actor=actor)
    assert _dispatch(side, "review_candidate", args, key="review", actor=actor) == first
    reviewed = _get(side, row)
    assert reviewed == replace(row, row_version=row.row_version + 1)
    (event,) = _events(side, _REVIEWED, _STATE_CHANGED)
    assert (event.type, event.workspace_id, event.stream_kind, event.stream_id) == (
        _REVIEWED,
        side.workspace,
        "candidate",
        row.id,
    )
    assert event.payload == {
        "candidate_id": str(row.id),
        "review_id": first["review_id"],
        "verdict": "approve",
        "reviewer_id": str(actor.principal_id),
    }

    with pytest.raises(Forbidden) as forbidden:
        _dispatch(side, "promote_candidate", _command(reviewed), actor=actor)
    assert forbidden.value.details == {"reason": "human_gate"}
    with pytest.raises(PreconditionFailed) as low:
        _dispatch(
            side,
            "promote_candidate",
            _command(reviewed, override_low_confidence=True, override_reason="  short  "),
        )
    assert low.value.details["reason"] == "override_reason_required"

    result = _dispatch(
        side,
        "promote_candidate",
        _command(reviewed, override_low_confidence=True, override_reason="  Manually checked  "),
    )
    with side.uow(readonly=True) as uow:
        reviews = uow.repo(CandidateReviewRepository).for_candidate(row.id)
        assert [(r.reviewer_kind, r.note) for r in reviews] == [
            (kind, None),
            (PrincipalKind.HUMAN, "Manually checked"),
        ]
        assert uow.repo(SignalRepository).for_candidate(row.id) == ()
        assert uow.repo(LessonRepository).get(_lesson_id(result)).applicability == LessonApplicability()
    assert _get(side, row) == replace(
        row,
        row_version=3,
        state=CandidateState.PROMOTED,
        lesson_id=_lesson_id(result),
        review_status="approved",
    )


def test_review_scope_version_rejection_and_fingerprint_collision(side: KnowledgeSide) -> None:
    row, other = _new_candidate(side, 1), _new_candidate(side, 2)
    _seed(side, row, other)
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    foreign = dispatch_new(client, CreateWorkspace(slug="foreign", title="Foreign")).workspace_id
    with pytest.raises(NotFound):
        _dispatch(side, "review_candidate", _command(row, workspace_id=str(foreign), verdict="comment"))
    with pytest.raises(Conflict) as duplicate:
        _dispatch(
            side,
            "review_candidate",
            _command(
                row,
                verdict="edit",
                edited_kind=other.kind.value,
                edited_trigger=other.trigger,
                edited_action=other.action,
            ),
        )
    assert duplicate.value.code is ErrorCode.ALREADY_EXISTS
    args = _command(row, verdict="reject")
    first = _dispatch(side, "review_candidate", args, key="reject")
    assert _dispatch(side, "review_candidate", args, key="reject") == first
    reviewed, changed = _events(side, _REVIEWED, _STATE_CHANGED)
    assert (reviewed.type, changed.type, changed.stream_id) == (_REVIEWED, _STATE_CHANGED, row.id)
    assert reviewed.payload["review_id"] == first["review_id"]
    assert changed.payload == {
        "candidate_id": str(row.id),
        "from": "candidate",
        "to": "rejected",
        "reason": "rejected",
    }
    with pytest.raises(Conflict) as stale:
        _dispatch(side, "review_candidate", _command(row, verdict="comment"))
    assert stale.value.code is ErrorCode.VERSION_CONFLICT
    rejected = _get(side, row)
    assert rejected.state is CandidateState.REJECTED
    assert rejected.review_status == "rejected"
    with pytest.raises(PreconditionFailed) as gate:
        _dispatch(side, "promote_candidate", _command(rejected))
    assert gate.value.code is ErrorCode.INVALID_TRANSITION


def test_partial_edit_and_backdated_approval_use_review_history(side: KnowledgeSide) -> None:
    row, other = _new_candidate(side, 1), _new_candidate(side, 2)
    _seed(side, row, other)
    with pytest.raises(ValidationFailed) as missing:
        _dispatch(side, "review_candidate", _command(row, verdict="edit"))
    assert missing.value.code is ErrorCode.SCHEMA_INVALID
    _dispatch(side, "review_candidate", _command(row, verdict="edit", edited_action="Run the full suite"))
    edited = _get(side, row)
    assert (edited.trigger, edited.action, edited.kind) == (row.trigger, "Run the full suite", row.kind)
    assert edited.fingerprint != row.fingerprint

    side.clock.advance(timedelta(minutes=-1))
    _dispatch(side, "review_candidate", _command(edited, verdict="approve"))
    with side.uow(readonly=True) as uow:
        repo = uow.repo(CandidateRepository)
        assert repo.get(row.id).review_status == "edited"
        assert repo.by_fingerprint(row.scope_id, edited.fingerprint) == repo.get(row.id)
        page = repo.list((row.scope_id,), states=frozenset(), after=None, limit=10)
        assert {item.id: item.review_status for item in page.items} == {
            row.id: "edited",
            other.id: "unreviewed",
        }
        assert [r.verdict for r in uow.repo(CandidateReviewRepository).for_candidate(row.id)] == [
            "approve",
            "edit",
        ]


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_promotion_creates_one_lesson(side: KnowledgeSide, same_key: bool) -> None:
    row = _new_candidate(side, 1)
    _seed(side, row)
    now = side.clock.now()
    args = _command(
        row,
        applicability={
            "applies_to": "Staging only",
            "validated_versions": [["repo:version", "v3 "]],
            "review_after": (now + timedelta(days=1)).isoformat(),
        },
    )
    barrier = Barrier(2)

    def promote(index: int) -> LessonId | None:
        barrier.wait(timeout=5)
        try:
            return _lesson_id(
                _dispatch(side, "promote_candidate", args, key=f"promote-{0 if same_key else index}")
            )
        except Conflict as error:
            if error.code is not ErrorCode.VERSION_CONFLICT:
                raise
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(promote, range(2)))
    lesson = next(result for result in results if result is not None)
    assert set(results) == ({lesson} if same_key else {lesson, None})
    promoted = _get(side, row)
    with pytest.raises(PreconditionFailed) as forbidden:
        _dispatch(side, "review_candidate", _command(promoted, verdict="comment"))
    assert forbidden.value.code is ErrorCode.INVALID_TRANSITION

    with side.uow(readonly=True) as uow:
        saved = uow.repo(LessonRepository).get(lesson)
        assert (saved.workspace_id, saved.scope_id) == (row.workspace_id, row.scope_id)
        assert saved.applicability == LessonApplicability(
            "Staging only", (("repo:version", "v3 "),), now + timedelta(days=1)
        )
        assert len(uow.repo(CandidateReviewRepository).for_candidate(row.id)) == 1
        assert uow.repo(SignalRepository).for_candidate(row.id) == ()
        types = frozenset(
            {
                "urn:skm:knowledge:event:lesson-promoted:v1",
                "urn:skm:learning:event:candidate-promoted:v1",
            }
        )
        events = uow.repo(EventReader).after_workspace_seq(row.workspace_id, 0, types=types, limit=20)
        assert [event.type for event in events] == sorted(types)


@pytest.mark.parametrize("failure", ["validation", "after_review"])
def test_promotion_failure_rolls_back_both_modules(
    side: KnowledgeSide, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    prior = _new_candidate(side, 1)
    row = _new_candidate(side, 2, conflicts_with_id=prior.id)
    _seed(side, prior, row)
    prior_lesson = _lesson_id(_dispatch(side, "promote_candidate", _command(prior)))
    with side.uow(readonly=True) as uow:
        head = uow.repo(EventReader).head_workspace_seq(row.workspace_id)
    applicability = {"validated_versions": [["repo:version", "v3"]]}
    expected = InternalError
    if failure == "validation":
        applicability["validated_versions"].append(["repo:version", "duplicate"])
        expected = ValidationFailed
    else:
        add = MemoryCandidateReviewRepository.add

        def fail(repo: MemoryCandidateReviewRepository, review: CandidateReview) -> None:
            add(repo, review)
            raise InternalError(ErrorCode.INTERNAL_ERROR, "injected after appending review")

        monkeypatch.setattr(MemoryCandidateReviewRepository, "add", fail)

    args = _command(row, applicability=applicability, resolve_conflict="supersede")
    with pytest.raises(expected):
        _dispatch(side, "promote_candidate", args, key="retry")

    assert _get(side, row) == row
    with side.uow(readonly=True) as uow:
        assert uow.repo(CandidateReviewRepository).for_candidate(row.id) == ()
        assert uow.repo(LessonRepository).by_candidate(row.id) is None
        assert uow.repo(LessonRepository).get(prior_lesson).state is LessonState.CURATED
        assert uow.repo(EventReader).head_workspace_seq(row.workspace_id) == head
    monkeypatch.undo()
    result = _dispatch(side, "promote_candidate", _command(row, resolve_conflict="supersede"), key="retry")
    assert _get(side, row).lesson_id == _lesson_id(result)


@pytest.mark.parametrize("decision", ["supersede", "keep_both"])
def test_conflict_resolution_is_explicit_and_exact_scope(side: KnowledgeSide, decision: str) -> None:
    prior = _new_candidate(side, 1)
    replacement = _new_candidate(side, 2, conflicts_with_id=prior.id)
    _seed(side, prior, replacement)
    old = _lesson_id(_dispatch(side, "promote_candidate", _command(prior)))
    project = side.new_project("another")
    foreign = _new_candidate(side, 3, project_id=project, scope_id=ScopeId(project))
    _seed(side, foreign)
    with pytest.raises(ValidationFailed) as scope:
        _dispatch(side, "promote_candidate", _command(foreign, supersedes_lesson_id=str(old)))
    assert scope.value.code is ErrorCode.SCHEMA_INVALID
    with pytest.raises(PreconditionFailed) as unresolved:
        _dispatch(side, "promote_candidate", _command(replacement))
    assert unresolved.value.details["reason"] == "conflict_unresolved"
    args = _command(replacement, resolve_conflict=decision)
    result = _dispatch(side, "promote_candidate", args, key="resolve")
    assert _dispatch(side, "promote_candidate", args, key="resolve") == result
    new = _lesson_id(result)
    targets = (
        loads(target)
        for action, _, _, target in audit_rows(side.app, None)
        if action == "learning.promote_candidate"
    )
    resolutions = [target for target in targets if "resolve_conflict" in target]
    assert [(r["candidate_id"], r["lesson_id"], r["resolve_conflict"]) for r in resolutions] == [
        (str(replacement.id), str(new), decision),
    ]
    with side.uow(readonly=True) as uow:
        lessons = uow.repo(LessonRepository)
        if decision == "supersede":
            assert lessons.get(new).supersedes_id == old
            assert lessons.get(old).state is LessonState.DEPRECATED
            assert lessons.get(old).deprecation_reason == f"superseded by {new}"
        else:
            assert lessons.get(new).supersedes_id is None
            assert lessons.get(old).state is LessonState.CURATED


@pytest.mark.parametrize("explicit", [False, True])
def test_supersede_requires_the_conflict_target_to_have_a_lesson(side: KnowledgeSide, explicit: bool) -> None:
    prior, unrelated = _new_candidate(side, 1), _new_candidate(side, 2)
    replacement = _new_candidate(side, 3, conflicts_with_id=prior.id)
    _seed(side, prior, unrelated, replacement)
    fields = (
        {"supersedes_lesson_id": str(_lesson_id(_dispatch(side, "promote_candidate", _command(unrelated))))}
        if explicit
        else {}
    )

    with pytest.raises(ValidationFailed, match="promoted conflict target"):
        _dispatch(side, "promote_candidate", _command(replacement, resolve_conflict="supersede", **fields))

    assert _get(side, replacement) == replacement
    with side.uow(readonly=True) as uow:
        assert uow.repo(LessonRepository).by_candidate(replacement.id) is None
        assert uow.repo(CandidateReviewRepository).for_candidate(replacement.id) == ()


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("verdict", ["edit", "reject"])
def test_proposals_preserve_wordings_and_review_targets_the_source(
    side: KnowledgeSide, reverse: bool, verdict: Literal["edit", "reject"]
) -> None:
    target = _new_candidate(side, 1)
    sources = tuple(_new_candidate(side, i, conflicts_with_id=target.id) for i in (2, 3))
    _seed(side, target, *sources)
    now = side.clock.now()
    signals = tuple(_signal(source, side) for source in sources)
    proposals = tuple(
        CandidateProposal(
            CandidateProposalId(uuid4()),
            target.scope_id,
            target.id,
            source.id,
            signal.activity_record_id,
            str(source.id),
            now + timedelta(days=index),
            now + timedelta(days=2 - index),
            source.kind,
            source.trigger,
            source.action,
            source.fingerprint,
            "v1",
            "update",
        )
        for index, (source, signal) in enumerate(zip(sources, signals, strict=True))
    )
    with side.uow() as uow:
        proposal_repo = uow.repo(CandidateProposalRepository)
        for source, signal in zip(sources, signals, strict=True):
            add_activity(uow, source, signal)
        for proposal in proposals[::-1] if reverse else proposals:
            assert proposal_repo.add(proposal)
            assert not proposal_repo.add(replace(proposal, id=CandidateProposalId(uuid4())))
        for signal in signals:
            assert uow.repo(SignalRepository).add(signal)
            assert not uow.repo(SignalRepository).add(replace(signal, id=SignalId(uuid4())))
        uow.commit()

    picked = _get(side, target).proposed_update
    assert picked is not None
    assert picked["id"] == str(proposals[1].id)
    fields = (
        {"edited_kind": "procedure", "edited_trigger": "Edited trigger", "edited_action": "Edited action"}
        if verdict == "edit"
        else {}
    )
    args = {"verdict": verdict, "proposal_id": str(proposals[1].id), **fields}
    with pytest.raises(NotFound):
        _dispatch(side, "review_candidate", _command(sources[0], **args))
    response = _dispatch(side, "review_candidate", _command(target, **args), key="address")
    assert _dispatch(side, "review_candidate", _command(target, **args), key="address") == response
    updated_target = _get(side, target)
    assert replace(updated_target, proposed_update=None) == target
    assert updated_target.proposed_update is not None
    assert updated_target.proposed_update["id"] == str(proposals[0].id)
    source = _get(side, sources[1])
    assert source.n_total == sources[1].n_total
    assert source.evidence == sources[1].evidence
    if verdict == "edit":
        assert source.fingerprint != sources[1].fingerprint
        assert source.review_status == "edited"
    else:
        assert source.state is CandidateState.REJECTED
    with side.uow(readonly=True) as uow:
        repo = uow.repo(CandidateProposalRepository)
        page = repo.list(target.id, after=None, limit=1)
        assert tuple(page.items) == (proposals[1],)
        assert tuple(repo.list(target.id, after=page.next, limit=1).items) == (proposals[0],)
        assert uow.repo(CandidateReviewRepository).for_candidate(target.id) == ()
        assert len(uow.repo(CandidateReviewRepository).for_candidate(source.id)) == 1
        assert uow.repo(SignalRepository).for_candidate(target.id) == ()
        assert uow.repo(SignalRepository).for_candidate(source.id) == (signals[1],)


def test_recompute_uses_distinct_signals_and_flags_stale_promoted_lesson(side: KnowledgeSide) -> None:
    promoted = _new_candidate(side, 1)
    observed = _new_candidate(side, 2, state=CandidateState.OBSERVED)
    low_support = _new_candidate(side, 3)
    _seed(side, promoted, observed, low_support)
    lesson_id = _lesson_id(_dispatch(side, "promote_candidate", _command(promoted)))
    with side.uow() as uow:
        signals = uow.repo(SignalRepository)
        for row in (promoted, observed):
            for _ in range(20):
                signal = _signal(row, side, days=20)
                add_activity(uow, row, signal)
                assert signals.add(signal)
        uow.commit()

    args = {"workspace_id": str(side.workspace), "project_id": str(side.project), "batch": 1}
    result = _dispatch(side, "recompute_confidence", args, key="recompute")
    assert _dispatch(side, "recompute_confidence", args, key="recompute") == result
    assert result == {
        "recomputed": 3,
        "transitions": {
            "to_candidate": 1,
            "deprecated": 1,
            "curated_ready": 0,
            "lesson_decay": 1,
        },
    }
    assert _get(side, observed).state is CandidateState.CANDIDATE
    assert _get(side, low_support).state is CandidateState.DEPRECATED
    stale = _get(side, promoted)
    assert stale.state is CandidateState.PROMOTED
    assert stale.n_total == stale.independent_known_total == stale.tests_passed == 20
    assert stale.freshness < 1
    assert stale.stale
    with side.uow(readonly=True) as uow:
        lesson = uow.repo(LessonRepository).get(lesson_id)
        assert lesson.state is LessonState.CURATED
        assert lesson.review_flag == "decay"
        assert lesson.confidence == stale.support_score
    rerun = _dispatch(side, "recompute_confidence", args)
    assert rerun["transitions"] == {"to_candidate": 0, "deprecated": 0, "curated_ready": 0, "lesson_decay": 1}
    assert [(event.stream_id, event.payload) for event in _events(side, _STATE_CHANGED)] == [
        (
            observed.id,
            {
                "candidate_id": str(observed.id),
                "from": "observed",
                "to": "candidate",
                "reason": "numeric_gate",
            },
        ),
        (
            low_support.id,
            {
                "candidate_id": str(low_support.id),
                "from": "candidate",
                "to": "deprecated",
                "reason": "source_support_low",
            },
        ),
    ]
    assert _get(side, promoted).row_version == stale.row_version
