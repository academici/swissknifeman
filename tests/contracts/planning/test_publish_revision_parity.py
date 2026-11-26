"""Contract parity tests for ``planning.publish_revision`` and Invariant I8."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg
import pytest

from integration.artifacts.test_upload_flow import (
    OWNER_ID,
    Harness,
    clean_test_database,
    dispatch_new,
    open_test_app,
    pg_session,
    seed_principals,
    test_database,
)
from integration.planning.publication import (
    MAT_LATEST_ID,
    MAT_PINNED_ID,
    make_prepare_ctx,
    req_meta,
    two_file_materials,
    upload_next_version,
    upload_v1,
)
from skm.application_bus.ports import EventReader
from skm.kernel.actor import PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, PreconditionFailed
from skm.kernel.ids import (
    EntityId,
    FileVersionId,
    PlanId,
    ProjectId,
    RevisionId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import Role
from skm.modules.planning.application.publication_candidate import prepare
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.draft import DraftId, DraftState
from skm.modules.planning.domain.events import PlanRevisionPublished
from skm.modules.planning.domain.revision import RevisionOrigin
from skm.modules.planning.domain.specification import SPECIFICATION_URN
from skm.modules.planning.generated.commands import (
    AbandonDraft,
    ArchivePlan,
    CreatePlan,
    OpenDraft,
    PublishRevision,
    SaveDraft,
)
from skm.modules.planning.generated.results import (
    PublishRevisionResult,
    PublishRevisionResultPinnedMaterialsItem,
)
from skm.modules.planning.ports import (
    DraftRepository,
    PlanningQueries,
    PlanRepository,
    RevisionRepository,
)
from skm.modules.workspace.public import ArchiveProject, CreateProject, CreateWorkspace
from support.pg import TestDatabase, clean_database
from support.seed import SEED

__all__ = ["clean_test_database", "pg_session", "test_database"]

PHASE_ID = "01900000-0000-7000-8000-000000000101"
ITEM_1_ID = "01900000-0000-7000-8000-000000000102"
ITEM_2_ID = "01900000-0000-7000-8000-000000000103"
UNIT_1_ID = "01900000-0000-7000-8000-000000000104"
UNIT_2_ID = "01900000-0000-7000-8000-000000000105"
REQ_ID = "01900000-0000-7000-8000-000000000106"
CRIT_ID = "01900000-0000-7000-8000-000000000107"
CHK_ID = "01900000-0000-7000-8000-000000000108"
DEC_1_ID = "01900000-0000-7000-8000-000000000109"
DEC_2_ID = "01900000-0000-7000-8000-00000000010a"


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def app_h(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Harness]:
    backend = str(request.param)
    db = (
        cast("TestDatabase", request.getfixturevalue("clean_test_database"))
        if backend == "postgres"
        else None
    )
    dsn = db.dsn if db is not None else None
    app, clock, blobs_root = open_test_app(backend, tmp_path, dsn, max_uow=4)
    try:
        actor = seed_principals(
            app,
            backend,
            people=((OWNER_ID, PrincipalKind.HUMAN, "owner"),),
            roles=((SEED.instance_id, OWNER_ID, Role.OWNER),),
        )
        client = app.client(actor=actor, surface=Surface.CLI)
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        yield Harness(app, clock, actor, client, ws, proj, blobs_root, dsn)
    finally:
        app.close()
        if db is not None:
            clean_database(db.dsn, db.tables)


def _build_rich_spec_doc(
    *, title: str = "Rich Spec v1", fv_1_id: FileVersionId, fv_2_id: FileVersionId
) -> JsonObject:
    materials = two_file_materials(fv_1_id, fv_2_id)
    return {
        "schema": SPECIFICATION_URN,
        "title": title,
        "goal": "Prove storage parity and I8 across memory and PostgreSQL",
        "materials": materials,
        "requirements": [
            {
                "id": REQ_ID,
                "key": "R1",
                "statement": "All revisions preserve canonical and typed parity.",
                "priority": "must",
                "source": {"kind": "owner"},
                "owners": ["P1.1"],
            }
        ],
        "decisions": [
            {
                "id": DEC_1_ID,
                "key": "D1",
                "title": "Initial storage layout",
                "state": "superseded",
                "question": "How to store revisions?",
                "decision": "JSON only.",
                "rationale": "Simple prototype.",
            },
            {
                "id": DEC_2_ID,
                "key": "D2",
                "title": "Typed + canonical payload storage",
                "state": "accepted",
                "question": "How to enforce I8?",
                "decision": "Write typed tables and canonical payload in one transaction.",
                "rationale": "Single authoritative representation.",
                "supersedes": ["D1"],
                "applies_to": ["P1.1"],
            },
        ],
        "phases": [
            {
                "id": PHASE_ID,
                "key": "P1",
                "title": "Phase 1",
                "goal": "Build vertical slice",
                "design_state": "skeleton",
                "batches": [{"key": "B1", "mode": "recommended", "items": ["P1.1", "P1.2"]}],
            }
        ],
        "items": [
            {
                "id": ITEM_1_ID,
                "key": "P1.1",
                "phase": "P1",
                "title": "Item 1",
                "summary": "Implement writer",
                "why": "Required by I8",
                "implements": ["R1"],
                "decisions": ["D2"],
                "review": {"mode": "self", "reason": "focused test spec"},
            },
            {
                "id": ITEM_2_ID,
                "key": "P1.2",
                "phase": "P1",
                "title": "Item 2",
                "summary": "Implement reader",
                "why": "Required by I8",
                "depends_on": ["P1.1"],
                "review": {"mode": "self", "reason": "focused test spec"},
            },
        ],
        "units": [
            {
                "id": UNIT_1_ID,
                "key": "P1.1/U1",
                "title": "Parent unit",
                "goal": "Write parent unit",
                "unit_kind": "implementation",
                "work_kind": "code",
                "mode": "either",
            },
            {
                "id": UNIT_2_ID,
                "key": "P1.1/U2",
                "parent": "P1.1/U1",
                "title": "Child unit",
                "goal": "Write child unit",
                "unit_kind": "verification",
                "work_kind": "test",
                "mode": "either",
                "checks": ["V1"],
                "implements": ["R1"],
            },
        ],
        "checks": [
            {
                "id": CHK_ID,
                "key": "V1",
                "owner": "P1.1",
                "title": "Manual check",
                "kind": "manual",
                "category": "acceptance",
                "required": True,
                "definition": {
                    "instructions_md": "Verify I8",
                    "actor_role": "owner",
                    "allowed_verdicts": ["pass", "fail"],
                },
            }
        ],
        "criteria": [
            {
                "id": CRIT_ID,
                "key": "AC1",
                "owner": "P1.1",
                "statement": "Typed document equals payload document.",
                "verification_mode": "manual",
                "checks": ["P1.1:V1"],
                "requirements": ["R1"],
            }
        ],
        "execution_constraints": {"strategy": "dag"},
    }


def _create_plan_and_draft(h: Harness, doc: JsonObject) -> tuple[PlanId, DraftId, int]:
    plan_id = PlanId(dispatch_new(h.client, CreatePlan(project_id=h.proj, title="Parity Plan")).plan_id)
    draft_res = dispatch_new(h.client, OpenDraft(plan_id=plan_id, base="empty"))
    draft_id = DraftId(draft_res.draft_id)
    save_cmd = SaveDraft(
        plan_id=plan_id, draft_id=draft_id, expected_edit_version=draft_res.edit_version, merge_patch=doc
    )
    save_res = dispatch_new(h.client, save_cmd)
    return plan_id, draft_id, int(save_res.edit_version)


def _compute_expected_digest(h: Harness, draft_id: DraftId, seq: int = 800) -> str:
    with h.app.uow_factory(req_meta(h, seq), readonly=True) as uow:
        draft = uow.repo(DraftRepository).get(draft_id)
        plan = uow.repo(PlanRepository).get(draft.plan_id)
        candidate = prepare(uow, make_prepare_ctx(uow, h, plan.id, seq=seq), plan, draft)
        uow.rollback()
        return candidate.content_digest


def _assert_pg_i8_single_authority_and_no_fallback(
    dsn: str, rev_1_id: RevisionId, expected_digest: str
) -> None:
    from skm.adapters.postgres.planning.revisions import PostgresRevisionRepository

    with psycopg.connect(dsn, autocommit=False) as conn:
        batch_rows = conn.execute(
            "SELECT batch_key, item_id FROM skm_planning.batch_members "
            "WHERE revision_id = %s ORDER BY position",
            (rev_1_id,),
        ).fetchall()
        assert batch_rows == [("B1", UUID(ITEM_1_ID)), ("B1", UUID(ITEM_2_ID))]

        unit_parent = conn.execute(
            "SELECT parent_unit_id FROM skm_planning.unit_specs WHERE revision_id = %s AND unit_id = %s",
            (rev_1_id, UUID(UNIT_2_ID)),
        ).fetchone()
        assert unit_parent == (UUID(UNIT_1_ID),)

        sup_rows = conn.execute(
            "SELECT decision_id, superseded_decision_id FROM skm_planning.decision_supersessions "
            "WHERE revision_id = %s",
            (rev_1_id,),
        ).fetchall()
        assert sup_rows == [(UUID(DEC_2_ID), UUID(DEC_1_ID))]

        # Prove load_typed_document never silently falls back to revision_payloads when typed rows diverge
        conn.execute("ALTER TABLE skm_planning.revision_specs DISABLE TRIGGER tg_revision_specs__immutable")
        conn.execute(
            "UPDATE skm_planning.revision_specs SET title = 'Tampered Typed Row' WHERE revision_id = %s",
            (rev_1_id,),
        )
        conn.execute("ALTER TABLE skm_planning.revision_specs ENABLE TRIGGER tg_revision_specs__immutable")
        pg_revs = PostgresRevisionRepository(conn)
        assert pg_revs.get_document(rev_1_id)["title"] == "Rich Spec v1"
        assert pg_revs.load_typed_document(rev_1_id)["title"] == "Tampered Typed Row"
        assert specification_digest(pg_revs.load_typed_document(rev_1_id)) != expected_digest
        conn.rollback()


def test_contract_spec_storage_parity(app_h: Harness) -> None:
    """Verify end-to-end ``PublishRevision`` storage parity and Invariant I8 on memory and PostgreSQL."""
    file_1, fv_1_v1 = upload_v1(app_h, b"guideline-v1", filename="guide.txt")
    fv_1_v2 = upload_next_version(app_h, file_1, 2, b"guideline-v2", filename="guide-v2.txt")
    _, fv_2 = upload_v1(app_h, b"reference-v1", filename="ref.txt")

    doc = _build_rich_spec_doc(fv_1_id=fv_1_v1, fv_2_id=fv_2)
    plan_id, draft_id, draft_ver = _create_plan_and_draft(app_h, doc)
    expected_digest = _compute_expected_digest(app_h, draft_id, seq=801)

    pub_1: PublishRevisionResult = dispatch_new(
        app_h.client,
        PublishRevision(plan_id, draft_id, draft_ver, expected_digest, reason="Initial release"),
    )
    assert pub_1.revision_no == 1
    assert pub_1.parent_revision_id is None
    assert pub_1.content_digest == expected_digest
    assert pub_1.pinned_materials == (
        PublishRevisionResultPinnedMaterialsItem("api-guide", UUID(str(fv_1_v2)), "latest_at_publish"),
        PublishRevisionResultPinnedMaterialsItem("ref-notes", UUID(str(fv_2)), "pinned"),
    )

    rev_1_id = RevisionId(pub_1.revision_id)
    with app_h.app.uow_factory(req_meta(app_h, 802), readonly=True) as uow:
        revs = uow.repo(RevisionRepository)
        meta = revs.get_meta(rev_1_id)
        payload_doc, typed_doc = revs.get_document(rev_1_id), revs.load_typed_document(rev_1_id)

        # Invariant I8: payload == normalize_document(load_typed_document(revision_id)) and digests match
        assert typed_doc == normalize_document(typed_doc)
        assert payload_doc == typed_doc
        assert specification_digest(typed_doc) == specification_digest(payload_doc) == meta.content_digest

        pins = uow.repo(PlanningQueries).revision_pins(rev_1_id)
        assert {p.material_id: p.file_version_id for p in pins} == {
            EntityId(UUID(MAT_LATEST_ID)): UUID(str(fv_1_v2)),
            EntityId(UUID(MAT_PINNED_ID)): UUID(str(fv_2)),
        }

        draft = uow.repo(DraftRepository).get(draft_id)
        assert draft.state is DraftState.PUBLISHED
        assert draft.published_revision_id == rev_1_id

        events = uow.repo(EventReader).after_workspace_seq(
            app_h.ws, 0, types=frozenset({PlanRevisionPublished.event_type}), limit=50
        )
        assert len(events) == 1
        assert events[0].payload["revision_id"] == str(rev_1_id)
        assert events[0].payload["origin"] == RevisionOrigin.DRAFT.value
        uow.rollback()

    # Publish R2 from R1 and verify parent linkage and I8 on the second revision
    draft_2_res = dispatch_new(app_h.client, OpenDraft(plan_id=plan_id, base="current"))
    draft_2_id = DraftId(draft_2_res.draft_id)
    save_2 = dispatch_new(
        app_h.client,
        SaveDraft(plan_id, draft_2_id, draft_2_res.edit_version, merge_patch={"title": "Rich Spec v2"}),
    )
    digest_2 = _compute_expected_digest(app_h, draft_2_id, seq=803)
    pub_2: PublishRevisionResult = dispatch_new(
        app_h.client,
        PublishRevision(plan_id, draft_2_id, save_2.edit_version, digest_2, reason="Second release"),
    )
    assert pub_2.revision_no == 2
    assert pub_2.parent_revision_id == pub_1.revision_id

    rev_2_id = RevisionId(pub_2.revision_id)
    with app_h.app.uow_factory(req_meta(app_h, 804), readonly=True) as uow:
        revs = uow.repo(RevisionRepository)
        assert revs.load_typed_document(rev_2_id) == revs.get_document(rev_2_id)
        assert specification_digest(revs.load_typed_document(rev_2_id)) == pub_2.content_digest
        uow.rollback()

    if app_h.dsn is not None:
        _assert_pg_i8_single_authority_and_no_fallback(app_h.dsn, rev_1_id, pub_1.content_digest)


def test_contract_publish_revision_rejections_and_idempotency_parity(app_h: Harness) -> None:
    """Verify rejection codes and idempotent replay parity across memory and PostgreSQL."""
    file_1, fv_1_v1 = upload_v1(app_h, b"guideline-v1", filename="guide.txt")
    _, fv_2 = upload_v1(app_h, b"reference-v1", filename="ref.txt")
    doc = _build_rich_spec_doc(fv_1_id=fv_1_v1, fv_2_id=fv_2)
    plan_id, draft_a_id, draft_a_ver = _create_plan_and_draft(app_h, doc)

    # Second draft on the same initial base (None)
    draft_b_res = dispatch_new(app_h.client, OpenDraft(plan_id=plan_id, base="empty"))
    draft_b_id = DraftId(draft_b_res.draft_id)
    doc_b = _build_rich_spec_doc(title="Draft B", fv_1_id=fv_1_v1, fv_2_id=fv_2)
    save_b = dispatch_new(
        app_h.client, SaveDraft(plan_id, draft_b_id, draft_b_res.edit_version, merge_patch=doc_b)
    )

    digest_a = _compute_expected_digest(app_h, draft_a_id, seq=820)

    # 1. Wrong expected_edit_version -> VERSION_CONFLICT
    with pytest.raises(Conflict) as exc_ver:
        dispatch_new(
            app_h.client,
            PublishRevision(plan_id, draft_a_id, draft_a_ver + 5, digest_a, reason="Wrong edit version"),
        )
    assert exc_ver.value.code is ErrorCode.VERSION_CONFLICT

    # 2. Candidate digest mismatch after new latest_at_publish version -> VERSION_CONFLICT(candidate_changed)
    fv_1_v2 = upload_next_version(app_h, file_1, 2, b"guideline-v2", filename="guide-v2.txt")
    assert fv_1_v2 != fv_1_v1
    with pytest.raises(Conflict) as exc_cas:
        dispatch_new(
            app_h.client,
            PublishRevision(plan_id, draft_a_id, draft_a_ver, digest_a, reason="Stale candidate digest"),
        )
    assert exc_cas.value.code is ErrorCode.VERSION_CONFLICT
    assert exc_cas.value.details["reason"] == "candidate_changed"

    # 3. Publish draft A with fresh digest and replay with the same idempotency_key
    fresh_digest_a = _compute_expected_digest(app_h, draft_a_id, seq=821)
    idem_key = app_h.client.new_idempotency_key()
    pub_cmd = PublishRevision(plan_id, draft_a_id, draft_a_ver, fresh_digest_a, reason="Idempotent release")
    res_1 = cast("PublishRevisionResult", app_h.client.dispatch(pub_cmd, idempotency_key=idem_key))
    res_2 = cast("PublishRevisionResult", app_h.client.dispatch(pub_cmd, idempotency_key=idem_key))
    assert res_1 == res_2
    assert res_1.revision_no == 1

    # 4. Republishing closed draft A with a new key -> DRAFT_NOT_OPEN
    with pytest.raises(PreconditionFailed) as exc_closed:
        dispatch_new(app_h.client, pub_cmd)
    assert exc_closed.value.code is ErrorCode.DRAFT_NOT_OPEN

    # 5. Publishing draft B (base_revision_id=None != current_revision_id) -> BASE_REVISION_CHANGED
    with pytest.raises(Conflict) as exc_base:
        dispatch_new(
            app_h.client,
            PublishRevision(plan_id, draft_b_id, save_b.edit_version, fresh_digest_a, reason="Stale base"),
        )
    assert exc_base.value.code is ErrorCode.BASE_REVISION_CHANGED
    assert exc_base.value.details["base_revision_id"] is None
    assert exc_base.value.details["current_revision_id"] == str(res_1.revision_id)

    # 6. Publishing new draft from current revision without changes -> NO_CHANGES
    draft_c_res = dispatch_new(app_h.client, OpenDraft(plan_id=plan_id, base="current"))
    draft_c_id = DraftId(draft_c_res.draft_id)
    with pytest.raises(PreconditionFailed) as exc_no_changes:
        dispatch_new(
            app_h.client,
            PublishRevision(plan_id, draft_c_id, draft_c_res.edit_version, fresh_digest_a, reason="No diff"),
        )
    assert exc_no_changes.value.code is ErrorCode.NO_CHANGES

    # 7. Archived plan and archived project guards
    dispatch_new(app_h.client, AbandonDraft(plan_id=plan_id, draft_id=draft_b_id, expected_edit_version=2))
    dispatch_new(app_h.client, AbandonDraft(plan_id=plan_id, draft_id=draft_c_id, expected_edit_version=1))
    dispatch_new(app_h.client, ArchivePlan(plan_id=plan_id, expected_row_version=2))
    with pytest.raises(PreconditionFailed) as exc_plan_arch:
        dispatch_new(
            app_h.client,
            PublishRevision(plan_id, draft_c_id, 1, fresh_digest_a, reason="Archived plan"),
        )
    assert exc_plan_arch.value.code is ErrorCode.PLAN_ARCHIVED

    plan_2_id = PlanId(dispatch_new(app_h.client, CreatePlan(project_id=app_h.proj, title="P2")).plan_id)
    draft_2_res = dispatch_new(app_h.client, OpenDraft(plan_id=plan_2_id, base="empty"))
    dispatch_new(app_h.client, ArchiveProject(app_h.proj, expected_row_version=1, reason="Archive project"))
    with pytest.raises(PreconditionFailed) as exc_proj_arch:
        dispatch_new(
            app_h.client,
            PublishRevision(plan_2_id, DraftId(draft_2_res.draft_id), 1, fresh_digest_a, reason="Archived"),
        )
    assert exc_proj_arch.value.code is ErrorCode.PROJECT_ARCHIVED
