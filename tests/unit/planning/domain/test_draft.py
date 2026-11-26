"""Draft aggregate: state before version, copy semantics, stale base (planning §4.4, §7.10)."""

from dataclasses import FrozenInstanceError, dataclass, replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, PreconditionFailed
from skm.kernel.ids import PlanId, PrincipalId, ProjectId, RevisionId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.modules.planning.domain.draft import (
    Draft,
    DraftId,
    DraftState,
    abandon,
    is_stale,
    mark_published,
    open_draft,
    rebase,
    require_current_base,
    require_edit_version,
    require_in_plan,
    require_open,
    save,
)
from skm.modules.planning.domain.plan import Plan, PlanPurpose, archive, new_plan, record_publication

NOW = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
LATER = NOW + timedelta(minutes=5)


def uid(n: int) -> UUID:
    return UUID(f"01900000-0000-7000-8000-{n:012d}")


@dataclass(frozen=True)
class Project:
    workspace_id: WorkspaceId
    project_id: ProjectId


ALICE = PrincipalId(uid(3))
BOB = PrincipalId(uid(4))
REV1 = RevisionId(uid(21))
REV2 = RevisionId(uid(22))
DOC: JsonObject = {"schema": "urn:skm:planning:specification:v1", "title": "T", "goal": "G"}


def make_plan() -> Plan:
    return new_plan(
        PlanId(uid(10)), Project(WorkspaceId(uid(1)), ProjectId(uid(2))), "PLAN1", "T", ALICE, NOW
    )


def make_draft(base: RevisionId | None = None) -> Draft:
    return open_draft(DraftId(uid(30)), make_plan(), base, DOC, ALICE, NOW)


def test_open_draft_takes_scope_from_the_plan_and_starts_at_version_one() -> None:
    plan = make_plan()
    draft = open_draft(DraftId(uid(30)), plan, REV1, DOC, ALICE, NOW)
    assert (draft.plan_id, draft.workspace_id) == (plan.id, plan.workspace_id)
    assert draft.base_revision_id == REV1
    assert draft.edit_version == 1
    assert draft.state is DraftState.OPEN
    assert draft.published_revision_id is None
    assert (draft.created_by, draft.updated_by, draft.created_at, draft.updated_at) == (
        ALICE,
        ALICE,
        NOW,
        NOW,
    )
    assert draft.closed_at is None


def test_open_draft_refuses_an_archived_plan() -> None:
    with pytest.raises(PreconditionFailed) as caught:
        open_draft(DraftId(uid(30)), archive(make_plan(), NOW), None, DOC, ALICE, NOW)
    assert caught.value.code is ErrorCode.PLAN_ARCHIVED


def test_open_draft_refuses_the_system_plan() -> None:
    system = replace(make_plan(), purpose=PlanPurpose.REVIEW_REQUESTS)
    with pytest.raises(PreconditionFailed) as caught:
        open_draft(DraftId(uid(30)), system, None, DOC, ALICE, NOW)
    assert caught.value.code is ErrorCode.INVALID_TRANSITION
    assert caught.value.details["reason"] == "system_plan"


def test_draft_keeps_its_own_copy_of_the_document() -> None:
    source: JsonObject = {"schema": "s", "title": "T"}
    draft = open_draft(DraftId(uid(30)), make_plan(), None, source, ALICE, NOW)
    source["title"] = "changed by the caller"
    assert draft.document["title"] == "T"
    saved = save(draft, source, 1, BOB, LATER)
    source["title"] = "changed again"
    assert saved.document["title"] == "changed by the caller"


def test_save_replaces_the_document_and_advances_the_version() -> None:
    draft = make_draft()
    new_doc: JsonObject = {**DOC, "title": "Second"}
    saved = save(draft, new_doc, 1, BOB, LATER)
    assert saved.document == new_doc
    assert saved.edit_version == 2
    assert (saved.updated_by, saved.updated_at) == (BOB, LATER)
    assert (saved.created_by, saved.created_at) == (ALICE, NOW)
    assert draft.edit_version == 1  # input untouched
    assert draft.document == DOC
    assert save(saved, new_doc, 2, BOB, LATER).edit_version == 3


def test_stale_expected_version_is_a_version_conflict_with_both_numbers() -> None:
    saved = save(make_draft(), DOC, 1, ALICE, LATER)
    with pytest.raises(Conflict) as caught:
        save(saved, DOC, 1, BOB, LATER)
    assert caught.value.code is ErrorCode.VERSION_CONFLICT
    assert dict(caught.value.details) == {"expected": 1, "actual": 2}


@pytest.mark.parametrize("state", [DraftState.PUBLISHED, DraftState.ABANDONED])
def test_closed_draft_answers_not_open_before_version_conflict(state: DraftState) -> None:
    closed = replace(make_draft(), state=state, closed_at=LATER, edit_version=5)
    for transition in (
        lambda: save(closed, DOC, 1, ALICE, LATER),
        lambda: rebase(closed, DOC, REV1, 1, ALICE, LATER),
        lambda: abandon(closed, 1, LATER),
    ):
        with pytest.raises(PreconditionFailed) as caught:
            transition()
        assert caught.value.code is ErrorCode.DRAFT_NOT_OPEN
        assert caught.value.details["state"] == state.value


def test_rebase_moves_the_base_and_counts_as_an_edit() -> None:
    draft = make_draft(base=None)
    rebased = rebase(draft, {**DOC, "title": "Merged"}, REV1, 1, BOB, LATER)
    assert rebased.base_revision_id == REV1
    assert rebased.edit_version == 2
    assert rebased.document["title"] == "Merged"
    assert rebased.state is DraftState.OPEN
    with pytest.raises(Conflict) as caught:
        rebase(rebased, DOC, REV2, 1, BOB, LATER)
    assert caught.value.code is ErrorCode.VERSION_CONFLICT


def test_rebase_onto_an_empty_base_is_possible() -> None:
    assert rebase(make_draft(base=REV1), DOC, None, 1, ALICE, LATER).base_revision_id is None


def test_abandon_closes_without_touching_the_document_or_the_version() -> None:
    draft = save(make_draft(), {**DOC, "title": "Edited"}, 1, ALICE, NOW)
    abandoned = abandon(draft, 2, LATER)
    assert abandoned.state is DraftState.ABANDONED
    assert abandoned.closed_at == LATER
    assert abandoned.document == draft.document
    assert abandoned.edit_version == draft.edit_version
    assert abandoned.published_revision_id is None
    assert abandoned.updated_by == draft.updated_by
    assert abandon(draft, 2, LATER, actor=BOB).updated_by == BOB


def test_abandon_checks_the_expected_version() -> None:
    with pytest.raises(Conflict) as caught:
        abandon(make_draft(), 7, LATER)
    assert dict(caught.value.details) == {"expected": 7, "actual": 1}


def test_mark_published_records_the_revision_and_closes_the_draft() -> None:
    draft = make_draft(base=REV1)
    published = mark_published(draft, REV2, LATER, actor=BOB)
    assert published.state is DraftState.PUBLISHED
    assert published.published_revision_id == REV2
    assert published.closed_at == LATER
    assert (published.updated_by, published.updated_at) == (BOB, LATER)
    assert published.edit_version == draft.edit_version
    assert mark_published(draft, REV2, LATER).updated_by == draft.updated_by


def test_mark_published_twice_is_refused() -> None:
    published = mark_published(make_draft(), REV2, LATER)
    with pytest.raises(PreconditionFailed) as caught:
        mark_published(published, REV2, LATER)
    assert caught.value.code is ErrorCode.DRAFT_NOT_OPEN


def test_guards_can_be_used_on_their_own() -> None:
    draft = make_draft()
    require_open(draft)
    require_edit_version(draft, 1)
    with pytest.raises(Conflict):
        require_edit_version(draft, 2)


def test_draft_of_another_plan_is_not_found_not_forbidden() -> None:
    draft = make_draft()
    require_in_plan(draft, draft.plan_id)
    with pytest.raises(NotFound) as caught:
        require_in_plan(draft, PlanId(uid(99)))
    assert caught.value.code is ErrorCode.NOT_FOUND
    assert caught.value.details["kind"] == "draft"


def test_stale_means_open_and_based_on_something_other_than_current() -> None:
    plan = make_plan()
    assert not is_stale(make_draft(base=None), plan)  # both None: nothing was published yet
    published_plan = record_publication(plan, REV2, "T", LATER)
    assert is_stale(make_draft(base=None), published_plan)
    assert is_stale(make_draft(base=REV1), published_plan)
    assert not is_stale(make_draft(base=REV2), published_plan)
    assert not is_stale(replace(make_draft(base=REV1), state=DraftState.ABANDONED), published_plan)


def test_publishing_from_a_stale_base_is_refused_with_both_revisions() -> None:
    published_plan = record_publication(make_plan(), REV2, "T", LATER)
    require_current_base(make_draft(base=REV2), published_plan)
    with pytest.raises(Conflict) as caught:
        require_current_base(make_draft(base=REV1), published_plan)
    assert caught.value.code is ErrorCode.BASE_REVISION_CHANGED
    assert dict(caught.value.details) == {"base_revision_id": str(REV1), "current_revision_id": str(REV2)}
    with pytest.raises(Conflict) as empty:
        require_current_base(make_draft(base=None), published_plan)
    assert empty.value.details["base_revision_id"] is None


def test_draft_is_frozen() -> None:
    with pytest.raises(FrozenInstanceError):
        setattr(make_draft(), "edit_version", 9)  # noqa: B010 -- exercise the frozen setter at runtime.
