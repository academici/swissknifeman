"""Unit tests for full revision publication."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from fakes.ids import SequentialIds
from integration.artifacts.test_upload_flow import (
    NOW,
    OWNER_ID,
    Harness,
    add_file_dto,
    dispatch_new,
    open_test_app,
    seed_principals,
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
from skm.adapters.memory.planning.repositories import MemoryPlanRepository
from skm.application_bus.ports import EventReader
from skm.kernel.actor import Actor, PrincipalKind, TokenGrant
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, InternalError, PreconditionFailed
from skm.kernel.ids import (
    EntityId,
    FileVersionId,
    PlanId,
    PrincipalId,
    ProjectId,
    RevisionId,
    ScopeId,
    WorkspaceId,
)
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeRegistry
from skm.modules.access.domain.token import ApiToken
from skm.modules.access.ports import TokenRepository
from skm.modules.access.public import Role, TokenId, TokenKind, grant_initial_membership
from skm.modules.artifacts import public as artifacts
from skm.modules.planning.application.publication_candidate import PinnedMaterial, prepare
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.draft import DraftId, DraftState
from skm.modules.planning.domain.events import PlanRevisionPublished
from skm.modules.planning.domain.plan import Plan
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
from support.seed import SEED

VIEWER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d2"))
WORKER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000d3"))
TOKEN_ID_1 = UUID("01900000-0000-7000-8000-0000000000e1")
TOKEN_ID_2 = UUID("01900000-0000-7000-8000-0000000000e2")
PHASE_ID = "01900000-0000-7000-8000-000000000101"
ITEM_ID = "01900000-0000-7000-8000-000000000102"


def _issue_narrowed_actor(
    h: Harness,
    *,
    token_id: UUID,
    prefix: str,
    name: str,
    permissions: tuple[str, ...],
    scope_id: ScopeId | None = None,
    scope_ancestors: tuple[ScopeId, ...] = (),
    seq: int = 910,
) -> Actor:
    token = ApiToken(
        id=TokenId(token_id),
        principal_id=OWNER_ID,
        kind=TokenKind.PERSONAL,
        name=name,
        prefix=prefix,
        secret_hash=b"\x01" * 32,
        scope_id=scope_id,
        permissions=frozenset(permissions),
        expires_at=None,
        created_at=h.clock.now(),
        created_by=OWNER_ID,
        last_used_at=None,
        revoked_at=None,
        revoked_by=None,
        assignment_id=None,
        step_id=None,
        superseded_by=None,
    )
    with h.app.uow_factory(req_meta(h, seq), readonly=False) as uow:
        uow.repo(TokenRepository).add(token)
        uow.commit()
    return Actor(
        principal_id=OWNER_ID,
        kind=PrincipalKind.HUMAN,
        display_name="owner",
        grant=TokenGrant(
            token_id=token_id,
            kind="personal",
            scope_id=scope_id,
            permissions=frozenset(permissions),
            scope_ancestors=scope_ancestors,
        ),
    )


@pytest.fixture
def mem_h(tmp_path: Path) -> Iterator[Harness]:
    app, clock, blobs_root = open_test_app("memory", tmp_path)
    try:
        actor = seed_principals(
            app,
            "memory",
            people=(
                (OWNER_ID, PrincipalKind.HUMAN, "owner"),
                (VIEWER_ID, PrincipalKind.HUMAN, "viewer"),
                (WORKER_ID, PrincipalKind.WORKER, "worker"),
            ),
            roles=(
                (SEED.instance_id, OWNER_ID, Role.OWNER),
                (SEED.instance_id, VIEWER_ID, Role.VIEWER),
            ),
        )
        client = app.client(actor=actor, surface=Surface.CLI)
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        with app.uow_factory(
            RequestMeta("req_" + "0" * 26, Surface.CLI, None, clock.now()), readonly=False
        ) as uow:
            grant_initial_membership(
                uow,
                scope_id=ScopeId(ws),
                principal_id=WORKER_ID,
                role=Role.WORKER,
                now=clock.now(),
            )
            uow.commit()
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        yield Harness(app, clock, actor, client, ws, proj, blobs_root, None)
    finally:
        app.close()


def _build_valid_spec_doc(
    *,
    title: str = "Spec v1",
    fv_1_id: FileVersionId,
    fv_2_id: FileVersionId,
) -> JsonObject:
    materials = two_file_materials(fv_1_id, fv_2_id)
    return {
        "schema": SPECIFICATION_URN,
        "title": title,
        "goal": "Deliver full revision publication",
        "materials": materials,
        "phases": [
            {
                "id": PHASE_ID,
                "key": "P1",
                "title": "Phase 1",
                "goal": "Build feature",
                "design_state": "skeleton",
            }
        ],
        "items": [
            {
                "id": ITEM_ID,
                "key": "P1.1",
                "phase": "P1",
                "title": "Item 1",
                "summary": "Implement handler",
                "why": "Required by spec",
                "review": {"mode": "self", "reason": "focused test spec"},
            }
        ],
        "execution_constraints": {"strategy": "dag"},
    }


def _create_plan_and_draft(h: Harness, doc: JsonObject) -> tuple[PlanId, DraftId, int]:
    plan_res = dispatch_new(h.client, CreatePlan(project_id=h.proj, title="Alpha Plan"))
    plan_id = PlanId(plan_res.plan_id)
    draft_res = dispatch_new(h.client, OpenDraft(plan_id=plan_id, base="empty"))
    draft_id = DraftId(draft_res.draft_id)
    save_res = dispatch_new(
        h.client,
        SaveDraft(
            plan_id=plan_id,
            draft_id=draft_id,
            expected_edit_version=draft_res.edit_version,
            merge_patch=doc,
        ),
    )
    return plan_id, draft_id, int(save_res.edit_version)


def _compute_expected_digest(h: Harness, draft_id: DraftId, seq: int = 800) -> str:
    with h.app.uow_factory(req_meta(h, seq), readonly=True) as uow:
        draft = uow.repo(DraftRepository).get(draft_id)
        plan = uow.repo(PlanRepository).get(draft.plan_id)
        ctx = make_prepare_ctx(uow, h, plan.id, seq=seq)
        candidate = prepare(uow, ctx, plan, draft)
        uow.rollback()
        return candidate.content_digest


def _assert_persisted_revision(
    h: Harness,
    *,
    plan_id: PlanId,
    draft_id: DraftId,
    pub_1: PublishRevisionResult,
    fv_1_initial: FileVersionId,
    fv_1_latest: FileVersionId,
    fv_2: FileVersionId,
) -> None:
    with h.app.uow_factory(req_meta(h, 810), readonly=True) as uow:
        rev_id = RevisionId(pub_1.revision_id)
        plan = uow.repo(PlanRepository).get(plan_id)
        assert plan.current_revision_id == rev_id
        assert plan.next_revision_no == 2
        assert plan.row_version == 2

        meta = uow.repo(RevisionRepository).get_meta(rev_id)
        assert meta.revision_no == 1
        assert meta.origin is RevisionOrigin.DRAFT
        assert meta.parent_revision_id is None
        assert meta.content_digest == pub_1.content_digest

        rev_doc = uow.repo(RevisionRepository).get_document(rev_id)
        materials = cast("list[JsonObject]", rev_doc["materials"])
        mat_by_id = {str(m["id"]): m for m in materials}
        assert mat_by_id[MAT_LATEST_ID]["file_version_id"] == str(fv_1_latest)
        assert mat_by_id[MAT_PINNED_ID]["file_version_id"] == str(fv_2)

        pins = uow.repo(PlanningQueries).revision_pins(rev_id)
        assert len(pins) == 2
        assert {p.material_id: p.file_version_id for p in pins} == {
            EntityId(UUID(MAT_LATEST_ID)): UUID(str(fv_1_latest)),
            EntityId(UUID(MAT_PINNED_ID)): UUID(str(fv_2)),
        }

        draft = uow.repo(DraftRepository).get(draft_id)
        assert draft.state is DraftState.PUBLISHED
        assert draft.published_revision_id == rev_id
        assert draft.closed_at == NOW
        draft_mats = cast("list[JsonObject]", draft.document["materials"])
        draft_mat_by_id = {str(m["id"]): m for m in draft_mats}
        assert draft_mat_by_id[MAT_LATEST_ID]["file_version_id"] == str(fv_1_initial)

        events = uow.repo(EventReader).after_workspace_seq(
            h.ws,
            0,
            types=frozenset({PlanRevisionPublished.event_type}),
            limit=50,
        )
        assert len(events) == 1
        payload = events[0].payload
        assert payload["plan_id"] == str(plan_id)
        assert payload["revision_id"] == str(pub_1.revision_id)
        assert payload["revision_no"] == 1
        assert payload["parent_revision_id"] is None
        assert payload["content_digest"] == pub_1.content_digest
        assert payload["origin"] == "draft"
        assert payload["draft_id"] == str(draft_id)
        uow.rollback()


def test_publish_success_memory(mem_h: Harness) -> None:
    file_1, fv_1_v1 = upload_v1(mem_h, b"guideline-v1", filename="guide.txt")
    fv_1_v2 = upload_next_version(mem_h, file_1, 2, b"guideline-v2", filename="guide-v2.txt")
    _, fv_2 = upload_v1(mem_h, b"reference-v1", filename="ref.txt")

    # Draft references fv_1_v1 with policy="latest_at_publish", which resolves to fv_1_v2 on publish
    doc = _build_valid_spec_doc(fv_1_id=fv_1_v1, fv_2_id=fv_2)
    plan_id, draft_id, draft_ver = _create_plan_and_draft(mem_h, doc)
    expected_digest = _compute_expected_digest(mem_h, draft_id)

    pub_1: PublishRevisionResult = dispatch_new(
        mem_h.client,
        PublishRevision(
            plan_id=plan_id,
            draft_id=draft_id,
            expected_edit_version=draft_ver,
            expected_content_digest=expected_digest,
            reason="Initial release",
        ),
    )
    assert pub_1.plan_id == UUID(str(plan_id))
    assert pub_1.revision_no == 1
    assert pub_1.parent_revision_id is None
    assert pub_1.content_digest == expected_digest
    assert pub_1.pinned_materials == (
        PublishRevisionResultPinnedMaterialsItem(
            material_key="api-guide",
            file_version_id=UUID(str(fv_1_v2)),
            resolved_from="latest_at_publish",
        ),
        PublishRevisionResultPinnedMaterialsItem(
            material_key="ref-notes",
            file_version_id=UUID(str(fv_2)),
            resolved_from="pinned",
        ),
    )
    assert pub_1.counts.warning >= 0
    assert pub_1.counts.info >= 0

    _assert_persisted_revision(
        mem_h,
        plan_id=plan_id,
        draft_id=draft_id,
        pub_1=pub_1,
        fv_1_initial=fv_1_v1,
        fv_1_latest=fv_1_v2,
        fv_2=fv_2,
    )

    # Publish a second revision and verify parent_revision_id and revision_no=2
    draft_2_res = dispatch_new(mem_h.client, OpenDraft(plan_id=plan_id, base="current"))
    draft_2_id = DraftId(draft_2_res.draft_id)
    doc_2 = _build_valid_spec_doc(title="Spec v2", fv_1_id=fv_1_v2, fv_2_id=fv_2)
    save_2 = dispatch_new(
        mem_h.client,
        SaveDraft(
            plan_id=plan_id,
            draft_id=draft_2_id,
            expected_edit_version=draft_2_res.edit_version,
            merge_patch=doc_2,
        ),
    )
    digest_2 = _compute_expected_digest(mem_h, draft_2_id, seq=811)
    pub_2: PublishRevisionResult = dispatch_new(
        mem_h.client,
        PublishRevision(
            plan_id=plan_id,
            draft_id=draft_2_id,
            expected_edit_version=save_2.edit_version,
            expected_content_digest=digest_2,
            reason="Second release",
        ),
    )
    assert pub_2.revision_no == 2
    assert pub_2.parent_revision_id == pub_1.revision_id
    with mem_h.app.uow_factory(req_meta(mem_h, 812), readonly=True) as uow:
        meta_2 = uow.repo(RevisionRepository).get_meta(RevisionId(pub_2.revision_id))
        assert meta_2.parent_revision_id == RevisionId(pub_1.revision_id)
        uow.rollback()


def test_base_revision_changed_rejected(mem_h: Harness) -> None:
    _, fv_1 = upload_v1(mem_h, b"guideline-v1", filename="guide.txt")
    _, fv_2 = upload_v1(mem_h, b"reference-v1", filename="ref.txt")
    doc_a = _build_valid_spec_doc(title="Spec A", fv_1_id=fv_1, fv_2_id=fv_2)
    plan_id, draft_a_id, draft_a_ver = _create_plan_and_draft(mem_h, doc_a)

    # Open a second draft while plan.current_revision_id is still None
    draft_b_res = dispatch_new(mem_h.client, OpenDraft(plan_id=plan_id, base="empty"))
    draft_b_id = DraftId(draft_b_res.draft_id)
    doc_b = _build_valid_spec_doc(title="Spec B", fv_1_id=fv_1, fv_2_id=fv_2)
    save_b = dispatch_new(
        mem_h.client,
        SaveDraft(
            plan_id=plan_id,
            draft_id=draft_b_id,
            expected_edit_version=draft_b_res.edit_version,
            merge_patch=doc_b,
        ),
    )

    # Wrong expected_edit_version -> VERSION_CONFLICT
    digest_a = _compute_expected_digest(mem_h, draft_a_id, seq=820)
    with pytest.raises(Conflict) as exc_ver:
        dispatch_new(
            mem_h.client,
            PublishRevision(
                plan_id=plan_id,
                draft_id=draft_a_id,
                expected_edit_version=draft_a_ver + 99,
                expected_content_digest=digest_a,
                reason="Wrong version",
            ),
        )
    assert exc_ver.value.code is ErrorCode.VERSION_CONFLICT

    # Publish draft A -> plan.current_revision_id advances to rev_1
    pub_a: PublishRevisionResult = dispatch_new(
        mem_h.client,
        PublishRevision(
            plan_id=plan_id,
            draft_id=draft_a_id,
            expected_edit_version=draft_a_ver,
            expected_content_digest=digest_a,
            reason="Publish A",
        ),
    )

    # Republishing already published draft A -> DRAFT_NOT_OPEN
    with pytest.raises(PreconditionFailed) as exc_closed:
        dispatch_new(
            mem_h.client,
            PublishRevision(
                plan_id=plan_id,
                draft_id=draft_a_id,
                expected_edit_version=draft_a_ver,
                expected_content_digest=digest_a,
                reason="Republish A",
            ),
        )
    assert exc_closed.value.code is ErrorCode.DRAFT_NOT_OPEN

    # Publishing draft B (whose base_revision_id is None != rev_1) -> BASE_REVISION_CHANGED
    with pytest.raises(Conflict) as exc_base:
        dispatch_new(
            mem_h.client,
            PublishRevision(
                plan_id=plan_id,
                draft_id=draft_b_id,
                expected_edit_version=save_b.edit_version,
                expected_content_digest=digest_a,
                reason="Publish B on stale base",
            ),
        )
    assert exc_base.value.code is ErrorCode.BASE_REVISION_CHANGED
    assert exc_base.value.details["base_revision_id"] is None
    assert exc_base.value.details["current_revision_id"] == str(pub_a.revision_id)


def test_candidate_changed_digest_mismatch(mem_h: Harness) -> None:
    file_1, fv_1_old = upload_v1(mem_h, b"guideline-v1", filename="guide.txt")
    _, fv_2 = upload_v1(mem_h, b"reference-v1", filename="ref.txt")
    doc = _build_valid_spec_doc(fv_1_id=fv_1_old, fv_2_id=fv_2)
    plan_id, draft_id, draft_ver = _create_plan_and_draft(mem_h, doc)
    preview_digest = _compute_expected_digest(mem_h, draft_id, seq=830)

    # Advance file_1 latest ready version before PublishRevision executes
    fv_1_new = upload_next_version(mem_h, file_1, 2, b"guideline-v2", filename="guide-v2.txt")
    assert fv_1_new != fv_1_old

    with pytest.raises(Conflict) as exc_info:
        dispatch_new(
            mem_h.client,
            PublishRevision(
                plan_id=plan_id,
                draft_id=draft_id,
                expected_edit_version=draft_ver,
                expected_content_digest=preview_digest,
                reason="Publish after concurrent file update",
            ),
        )
    assert exc_info.value.code is ErrorCode.VERSION_CONFLICT
    assert exc_info.value.details["reason"] == "candidate_changed"
    assert exc_info.value.details["expected_content_digest"] == preview_digest
    assert exc_info.value.details["actual_content_digest"] != preview_digest

    with mem_h.app.uow_factory(req_meta(mem_h, 831), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        assert plan.current_revision_id is None
        assert plan.next_revision_no == 1
        assert plan.row_version == 1

        draft = uow.repo(DraftRepository).get(draft_id)
        assert draft.state is DraftState.OPEN
        assert draft.edit_version == draft_ver
        assert draft.closed_at is None
        assert draft.published_revision_id is None

        events = uow.repo(EventReader).after_workspace_seq(
            mem_h.ws,
            0,
            types=frozenset({PlanRevisionPublished.event_type}),
            limit=50,
        )
        assert events == ()
        uow.rollback()


def test_no_changes_rejected(mem_h: Harness) -> None:
    file_1, fv_1 = upload_v1(mem_h, b"guideline-v1", filename="guide.txt")
    _, fv_2 = upload_v1(mem_h, b"reference-v1", filename="ref.txt")
    doc = _build_valid_spec_doc(fv_1_id=fv_1, fv_2_id=fv_2)
    plan_id, draft_1_id, draft_1_ver = _create_plan_and_draft(mem_h, doc)
    digest_1 = _compute_expected_digest(mem_h, draft_1_id, seq=840)
    dispatch_new(
        mem_h.client,
        PublishRevision(
            plan_id=plan_id,
            draft_id=draft_1_id,
            expected_edit_version=draft_1_ver,
            expected_content_digest=digest_1,
            reason="Initial publish",
        ),
    )

    # Open a new draft from current revision without any changes -> NO_CHANGES
    draft_2_res = dispatch_new(mem_h.client, OpenDraft(plan_id=plan_id, base="current"))
    draft_2_id = DraftId(draft_2_res.draft_id)
    digest_2 = _compute_expected_digest(mem_h, draft_2_id, seq=841)
    assert digest_2 == digest_1

    with pytest.raises(PreconditionFailed) as exc_info:
        dispatch_new(
            mem_h.client,
            PublishRevision(
                plan_id=plan_id,
                draft_id=draft_2_id,
                expected_edit_version=draft_2_res.edit_version,
                expected_content_digest=digest_2,
                reason="No-op publish",
            ),
        )
    assert exc_info.value.code is ErrorCode.NO_CHANGES

    # When file_1 advances to a new version, publishing draft_2 (with latest_at_publish) succeeds!
    fv_1_v2 = upload_next_version(mem_h, file_1, 2, b"guideline-v2", filename="guide-v2.txt")
    digest_after_file_update = _compute_expected_digest(mem_h, draft_2_id, seq=842)
    assert digest_after_file_update != digest_1

    pub_2: PublishRevisionResult = dispatch_new(
        mem_h.client,
        PublishRevision(
            plan_id=plan_id,
            draft_id=draft_2_id,
            expected_edit_version=draft_2_res.edit_version,
            expected_content_digest=digest_after_file_update,
            reason="Repin material to v2",
        ),
    )
    assert pub_2.revision_no == 2
    assert {m.material_key: m.file_version_id for m in pub_2.pinned_materials}["api-guide"] == UUID(
        str(fv_1_v2)
    )


def test_plan_not_ready_rejected(mem_h: Harness) -> None:
    _, fv_1 = upload_v1(mem_h, b"guideline-v1", filename="guide.txt")
    _, fv_2 = upload_v1(mem_h, b"reference-v1", filename="ref.txt")

    # 1. Structural error: item references unknown phase "P99"
    bad_doc = _build_valid_spec_doc(fv_1_id=fv_1, fv_2_id=fv_2)
    bad_items = list(cast("list[JsonObject]", bad_doc["items"]))
    bad_items[0] = {**bad_items[0], "phase": "P99"}
    bad_doc = {**bad_doc, "items": bad_items}

    plan_id, draft_id, draft_ver = _create_plan_and_draft(mem_h, bad_doc)
    bad_digest = _compute_expected_digest(mem_h, draft_id, seq=850)

    with pytest.raises(PreconditionFailed) as exc_struct:
        dispatch_new(
            mem_h.client,
            PublishRevision(
                plan_id=plan_id,
                draft_id=draft_id,
                expected_edit_version=draft_ver,
                expected_content_digest=bad_digest,
                reason="Publish invalid phase ref",
            ),
        )
    assert exc_struct.value.code is ErrorCode.PLAN_NOT_READY
    findings = cast("list[JsonObject]", exc_struct.value.details["findings"])
    assert any(f["code"] == "ref_unknown" for f in findings)

    # 2. External validation error: item change_hints references unknown repository mount
    ext_bad_doc = _build_valid_spec_doc(fv_1_id=fv_1, fv_2_id=fv_2)
    ext_items = list(cast("list[JsonObject]", ext_bad_doc["items"]))
    ext_items[0] = {
        **ext_items[0],
        "change_hints": [
            {"mount": "missing-mount", "pattern": "src/**", "change": "modify"},
        ],
    }
    ext_bad_doc = {**ext_bad_doc, "items": ext_items}
    save_ext = dispatch_new(
        mem_h.client,
        SaveDraft(
            plan_id=plan_id,
            draft_id=draft_id,
            expected_edit_version=draft_ver,
            merge_patch=ext_bad_doc,
        ),
    )
    ext_digest = _compute_expected_digest(mem_h, draft_id, seq=851)
    with pytest.raises(PreconditionFailed) as exc_ext:
        dispatch_new(
            mem_h.client,
            PublishRevision(
                plan_id=plan_id,
                draft_id=draft_id,
                expected_edit_version=save_ext.edit_version,
                expected_content_digest=ext_digest,
                reason="Publish invalid mount ref",
            ),
        )
    assert exc_ext.value.code is ErrorCode.PLAN_NOT_READY
    ext_findings = cast("list[JsonObject]", exc_ext.value.details["findings"])
    assert any(f["code"] == "mount_unknown" for f in ext_findings)

    # Restore valid document
    valid_doc = _build_valid_spec_doc(fv_1_id=fv_1, fv_2_id=fv_2)
    save_valid = dispatch_new(
        mem_h.client,
        SaveDraft(
            plan_id=plan_id,
            draft_id=draft_id,
            expected_edit_version=save_ext.edit_version,
            merge_patch=valid_doc,
        ),
    )
    valid_digest = _compute_expected_digest(mem_h, draft_id, seq=852)

    # 3. Missing permission (viewer has plan.read but lacks plan.publish) -> FORBIDDEN
    viewer_client = mem_h.app.client(
        actor=Actor(VIEWER_ID, PrincipalKind.HUMAN, "viewer"), surface=Surface.CLI
    )
    with pytest.raises(Forbidden) as exc_perm:
        dispatch_new(
            viewer_client,
            PublishRevision(
                plan_id=plan_id,
                draft_id=draft_id,
                expected_edit_version=save_valid.edit_version,
                expected_content_digest=valid_digest,
                reason="Forbidden publish",
            ),
        )
    assert exc_perm.value.code is ErrorCode.FORBIDDEN

    # 4. Archived project -> PROJECT_ARCHIVED
    dispatch_new(
        mem_h.client,
        ArchiveProject(project_id=mem_h.proj, expected_row_version=1, reason="archive project"),
    )
    with pytest.raises(PreconditionFailed) as exc_proj:
        dispatch_new(
            mem_h.client,
            PublishRevision(
                plan_id=plan_id,
                draft_id=draft_id,
                expected_edit_version=save_valid.edit_version,
                expected_content_digest=valid_digest,
                reason="Publish on archived project",
            ),
        )
    assert exc_proj.value.code is ErrorCode.PROJECT_ARCHIVED

    # 5. Active project with archived plan -> PLAN_ARCHIVED
    proj_2 = ProjectId(
        dispatch_new(
            mem_h.client, CreateProject(workspace_id=mem_h.ws, slug="skm2", title="SKM 2")
        ).project_id
    )
    plan_2_res = dispatch_new(mem_h.client, CreatePlan(project_id=proj_2, title="Beta Plan"))
    plan_2_id = PlanId(plan_2_res.plan_id)
    draft_2_res = dispatch_new(mem_h.client, OpenDraft(plan_id=plan_2_id, base="empty"))
    draft_2_id = DraftId(draft_2_res.draft_id)
    dispatch_new(
        mem_h.client,
        AbandonDraft(plan_id=plan_2_id, draft_id=draft_2_id, expected_edit_version=1),
    )
    dispatch_new(mem_h.client, ArchivePlan(plan_id=plan_2_id, expected_row_version=1))
    with pytest.raises(PreconditionFailed) as exc_plan_arch:
        dispatch_new(
            mem_h.client,
            PublishRevision(
                plan_id=plan_2_id,
                draft_id=draft_2_id,
                expected_edit_version=1,
                expected_content_digest=valid_digest,
                reason="Publish on archived plan",
            ),
        )
    assert exc_plan_arch.value.code is ErrorCode.PLAN_ARCHIVED


def test_idempotent_replay(mem_h: Harness) -> None:
    _, fv_1 = upload_v1(mem_h, b"guideline-v1", filename="guide.txt")
    _, fv_2 = upload_v1(mem_h, b"reference-v1", filename="ref.txt")
    doc = _build_valid_spec_doc(fv_1_id=fv_1, fv_2_id=fv_2)
    plan_id, draft_id, draft_ver = _create_plan_and_draft(mem_h, doc)
    expected_digest = _compute_expected_digest(mem_h, draft_id, seq=860)

    idem_key = mem_h.client.new_idempotency_key()
    cmd = PublishRevision(
        plan_id=plan_id,
        draft_id=draft_id,
        expected_edit_version=draft_ver,
        expected_content_digest=expected_digest,
        reason="Idempotent release",
    )
    res_1 = cast("PublishRevisionResult", mem_h.client.dispatch(cmd, idempotency_key=idem_key))
    res_2 = cast("PublishRevisionResult", mem_h.client.dispatch(cmd, idempotency_key=idem_key))

    assert res_1 == res_2
    assert res_1.revision_no == 1
    with mem_h.app.uow_factory(req_meta(mem_h, 861), readonly=True) as uow:
        assert uow.repo(PlanRepository).get(plan_id).next_revision_no == 2
        uow.rollback()

    # (a) Replay by same principal with token lacking plan.read (only {"plan.publish"}) -> FORBIDDEN
    no_plan_read_actor = _issue_narrowed_actor(
        mem_h,
        token_id=TOKEN_ID_1,
        prefix="aaaaaaaa",
        name="no-plan-read",
        permissions=("plan.publish",),
        seq=862,
    )
    no_plan_read_client = mem_h.app.client(actor=no_plan_read_actor, surface=Surface.CLI)
    with pytest.raises(Forbidden) as exc_no_read:
        no_plan_read_client.dispatch(cmd, idempotency_key=idem_key)
    assert exc_no_read.value.code is ErrorCode.FORBIDDEN

    # (b) Replay by same principal with {"plan.read", "plan.publish"} (no file.read) returns cached result
    no_file_read_actor = _issue_narrowed_actor(
        mem_h,
        token_id=TOKEN_ID_2,
        prefix="bbbbbbbb",
        name="no-file-read",
        permissions=("plan.read", "plan.publish"),
        seq=863,
    )
    no_file_read_client = mem_h.app.client(actor=no_file_read_actor, surface=Surface.CLI)
    res_3 = cast("PublishRevisionResult", no_file_read_client.dispatch(cmd, idempotency_key=idem_key))
    assert res_3 == res_1

    # Fresh metadata lookup (GetFileVersion) with that same token without file.read -> FORBIDDEN
    with pytest.raises(Forbidden) as exc_fv_lookup:
        no_file_read_client.ask(artifacts.GetFileVersion(file_version_id=UUID(str(fv_1))))
    assert exc_fv_lookup.value.code is ErrorCode.FORBIDDEN

    # Fresh prepare(...) on a new open draft with that same token without file.read -> FORBIDDEN
    draft_2_res = dispatch_new(mem_h.client, OpenDraft(plan_id=plan_id, base="current"))
    draft_2_id = DraftId(draft_2_res.draft_id)
    with mem_h.app.uow_factory(req_meta(mem_h, 862), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        draft_2 = uow.repo(DraftRepository).get(draft_2_id)
        ctx_no_file = make_prepare_ctx(uow, mem_h, plan_id, actor=no_file_read_actor, seq=862)
        with pytest.raises(Forbidden) as exc_prep_no_file:
            prepare(uow, ctx_no_file, plan, draft_2)
        assert exc_prep_no_file.value.code is ErrorCode.FORBIDDEN
        uow.rollback()


def _assert_prepare_archived_states(mem_h: Harness, plan_id: PlanId) -> None:
    draft_c_res = dispatch_new(mem_h.client, OpenDraft(plan_id=plan_id, base="current"))
    draft_c_id = DraftId(draft_c_res.draft_id)
    dispatch_new(
        mem_h.client,
        ArchiveProject(project_id=mem_h.proj, expected_row_version=1, reason="archive project"),
    )
    with mem_h.app.uow_factory(req_meta(mem_h, 882), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        draft_c = uow.repo(DraftRepository).get(draft_c_id)
        ctx = make_prepare_ctx(uow, mem_h, plan_id, seq=882)
        with pytest.raises(PreconditionFailed) as exc_proj:
            prepare(uow, ctx, plan, draft_c)
        assert exc_proj.value.code is ErrorCode.PROJECT_ARCHIVED
        uow.rollback()

    proj_2 = ProjectId(
        dispatch_new(
            mem_h.client, CreateProject(workspace_id=mem_h.ws, slug="skm-prep", title="SKM Prep")
        ).project_id
    )
    plan_2_id = PlanId(
        dispatch_new(mem_h.client, CreatePlan(project_id=proj_2, title="Archived Plan")).plan_id
    )
    draft_2_id = DraftId(dispatch_new(mem_h.client, OpenDraft(plan_id=plan_2_id, base="empty")).draft_id)
    dispatch_new(
        mem_h.client,
        AbandonDraft(plan_id=plan_2_id, draft_id=draft_2_id, expected_edit_version=1),
    )
    dispatch_new(mem_h.client, ArchivePlan(plan_id=plan_2_id, expected_row_version=1))
    with mem_h.app.uow_factory(req_meta(mem_h, 883), readonly=True) as uow:
        archived_plan = uow.repo(PlanRepository).get(plan_2_id)
        abandoned_draft = uow.repo(DraftRepository).get(draft_2_id)
        ctx_2 = make_prepare_ctx(uow, mem_h, plan_2_id, seq=883)
        with pytest.raises(PreconditionFailed) as exc_plan_arch:
            prepare(uow, ctx_2, archived_plan, abandoned_draft)
        assert exc_plan_arch.value.code is ErrorCode.PLAN_ARCHIVED
        uow.rollback()


def test_publication_candidate_prepare_contract(mem_h: Harness) -> None:
    file_1, fv_1_v1 = upload_v1(mem_h, b"guideline-v1", filename="guide.txt")
    fv_1_v2 = upload_next_version(mem_h, file_1, 2, b"guideline-v2", filename="guide-v2.txt")
    _, fv_2 = upload_v1(mem_h, b"reference-v1", filename="ref.txt")

    doc = _build_valid_spec_doc(fv_1_id=fv_1_v1, fv_2_id=fv_2)
    plan_id, draft_id, draft_ver = _create_plan_and_draft(mem_h, doc)
    draft_b_res = dispatch_new(mem_h.client, OpenDraft(plan_id=plan_id, base="empty"))
    draft_b_id = DraftId(draft_b_res.draft_id)
    save_b = dispatch_new(
        mem_h.client,
        SaveDraft(
            plan_id=plan_id,
            draft_id=draft_b_id,
            expected_edit_version=draft_b_res.edit_version,
            merge_patch=_build_valid_spec_doc(title="Spec B", fv_1_id=fv_1_v1, fv_2_id=fv_2),
        ),
    )

    with mem_h.app.uow_factory(req_meta(mem_h, 880), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        draft = uow.repo(DraftRepository).get(draft_id)
        ctx = make_prepare_ctx(uow, mem_h, plan_id, seq=880)

        candidate = prepare(uow, ctx, plan, draft, expected_edit_version=draft_ver)
        assert candidate.publishable is True
        assert candidate.has_errors is False
        assert candidate.base_changed is False
        assert candidate.no_changes is False
        assert candidate.document_digest == specification_digest(normalize_document(draft.document))
        assert candidate.content_digest != candidate.document_digest
        assert candidate.pinned_materials == (
            PinnedMaterial("api-guide", fv_1_v2, "latest_at_publish"),
            PinnedMaterial("ref-notes", fv_2, "pinned"),
        )
        draft_mats = cast("list[JsonObject]", draft.document["materials"])
        assert draft_mats[0]["file_version_id"] == str(fv_1_v1)

        with pytest.raises(Conflict) as exc_ver:
            prepare(uow, ctx, plan, draft, expected_edit_version=draft_ver + 10)
        assert exc_ver.value.code is ErrorCode.VERSION_CONFLICT
        uow.rollback()

    pub_res: PublishRevisionResult = dispatch_new(
        mem_h.client,
        PublishRevision(
            plan_id=plan_id,
            draft_id=draft_id,
            expected_edit_version=draft_ver,
            expected_content_digest=candidate.content_digest,
            reason="Publish initial revision",
        ),
    )

    with mem_h.app.uow_factory(req_meta(mem_h, 881), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        closed_draft = uow.repo(DraftRepository).get(draft_id)
        stale_draft = uow.repo(DraftRepository).get(draft_b_id)
        ctx = make_prepare_ctx(uow, mem_h, plan_id, seq=881)

        with pytest.raises(PreconditionFailed) as exc_closed:
            prepare(uow, ctx, plan, closed_draft)
        assert exc_closed.value.code is ErrorCode.DRAFT_NOT_OPEN

        with pytest.raises(Conflict) as exc_base:
            prepare(uow, ctx, plan, stale_draft, expected_edit_version=save_b.edit_version)
        assert exc_base.value.code is ErrorCode.BASE_REVISION_CHANGED
        assert exc_base.value.details["base_revision_id"] is None
        assert exc_base.value.details["current_revision_id"] == str(pub_res.revision_id)
        uow.rollback()

    _assert_prepare_archived_states(mem_h, plan_id)


def test_file_read_enforced_without_leaking_latest_metadata(mem_h: Harness) -> None:
    file_1, fv_1_v1 = upload_v1(mem_h, b"guideline-v1", filename="guide.txt")
    fv_1_v2 = upload_next_version(mem_h, file_1, 2, b"guideline-v2", filename="guide-v2.txt")
    _, fv_2 = upload_v1(mem_h, b"reference-v1", filename="ref.txt")

    doc = _build_valid_spec_doc(fv_1_id=fv_1_v1, fv_2_id=fv_2)
    plan_id, draft_id, draft_ver = _create_plan_and_draft(mem_h, doc)
    expected_digest = _compute_expected_digest(mem_h, draft_id, seq=890)

    # 1. Token without file.read -> FORBIDDEN without leaking fv_1_v2 or digest
    no_file_read_actor = _issue_narrowed_actor(
        mem_h,
        token_id=TOKEN_ID_1,
        prefix="cccccccc",
        name="prep-no-file-read",
        permissions=("plan.read", "plan.publish"),
        seq=891,
    )
    with mem_h.app.uow_factory(req_meta(mem_h, 892), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        draft = uow.repo(DraftRepository).get(draft_id)
        ctx = make_prepare_ctx(uow, mem_h, plan_id, actor=no_file_read_actor, seq=892)
        with pytest.raises(Forbidden) as exc_no_fr:
            prepare(uow, ctx, plan, draft)
        assert exc_no_fr.value.code is ErrorCode.FORBIDDEN
        assert str(fv_1_v2) not in str(exc_no_fr.value.details)
        assert expected_digest not in str(exc_no_fr.value.details)
        uow.rollback()

    no_file_read_client = mem_h.app.client(actor=no_file_read_actor, surface=Surface.CLI)
    with pytest.raises(Forbidden) as exc_pub_no_fr:
        dispatch_new(
            no_file_read_client,
            PublishRevision(
                plan_id=plan_id,
                draft_id=draft_id,
                expected_edit_version=draft_ver,
                expected_content_digest="sha256:" + "0" * 64,
                reason="Attempt publish without file.read",
            ),
        )
    assert exc_pub_no_fr.value.code is ErrorCode.FORBIDDEN
    assert str(fv_1_v2) not in str(exc_pub_no_fr.value.details)
    assert expected_digest not in str(exc_pub_no_fr.value.details)

    # 2. File in another project within the same workspace where caller token is scoped only to mem_h.proj
    other_proj = ProjectId(
        dispatch_new(
            mem_h.client, CreateProject(workspace_id=mem_h.ws, slug="other-proj", title="Other")
        ).project_id
    )
    staged_other_1 = mem_h.client.upload_blob(mem_h.ws, [b"other-v1"], size=8, media_type="text/plain")
    other_res_1 = dispatch_new(mem_h.client, add_file_dto(mem_h.ws, other_proj, staged_other_1))
    other_file_id = UUID(str(other_res_1.file_id))
    other_fv_v1 = FileVersionId(UUID(str(other_res_1.file_version_id)))
    other_fv_v2 = upload_next_version(mem_h, other_file_id, 2, b"other-v2", filename="other-v2.txt")

    doc_cross_proj = _build_valid_spec_doc(fv_1_id=other_fv_v1, fv_2_id=fv_2)
    plan_cp_id, draft_cp_id, _ = _create_plan_and_draft(mem_h, doc_cross_proj)
    with mem_h.app.uow_factory(req_meta(mem_h, 893), readonly=True) as uow:
        proj_ancestors = tuple(r.id for r in uow.repo(ScopeRegistry).ancestors(ScopeId(mem_h.proj)))
        uow.rollback()
    proj_scoped_actor = _issue_narrowed_actor(
        mem_h,
        token_id=TOKEN_ID_2,
        prefix="dddddddd",
        name="proj-scoped",
        permissions=("plan.read", "plan.publish", "file.read"),
        scope_id=ScopeId(mem_h.proj),
        scope_ancestors=proj_ancestors,
        seq=894,
    )
    with mem_h.app.uow_factory(req_meta(mem_h, 895), readonly=True) as uow:
        plan_cp = uow.repo(PlanRepository).get(plan_cp_id)
        draft_cp = uow.repo(DraftRepository).get(draft_cp_id)
        ctx_cp = make_prepare_ctx(uow, mem_h, plan_cp_id, actor=proj_scoped_actor, seq=895)
        with pytest.raises(Forbidden) as exc_cross_proj:
            prepare(uow, ctx_cp, plan_cp, draft_cp)
        assert exc_cross_proj.value.code is ErrorCode.FORBIDDEN
        assert str(other_fv_v2) not in str(exc_cross_proj.value.details)
        uow.rollback()


def test_worker_grant_enforced_without_leaking_latest_metadata(mem_h: Harness) -> None:
    file_1, fv_1_v1 = upload_v1(mem_h, b"guideline-v1", filename="guide.txt")
    fv_1_v2 = upload_next_version(mem_h, file_1, 2, b"guideline-v2", filename="guide-v2.txt")
    _, fv_2 = upload_v1(mem_h, b"reference-v1", filename="ref.txt")

    doc = _build_valid_spec_doc(fv_1_id=fv_1_v1, fv_2_id=fv_2)
    plan_id, draft_id, _ = _create_plan_and_draft(mem_h, doc)
    expected_digest = _compute_expected_digest(mem_h, draft_id, seq=894)
    grant_ids = SequentialIds()

    worker_actor = Actor(principal_id=WORKER_ID, kind=PrincipalKind.WORKER, display_name="worker")
    with mem_h.app.uow_factory(req_meta(mem_h, 895), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        draft = uow.repo(DraftRepository).get(draft_id)
        ctx_worker = make_prepare_ctx(uow, mem_h, plan_id, actor=worker_actor, seq=895)
        with pytest.raises(Forbidden) as exc_worker_missing:
            prepare(uow, ctx_worker, plan, draft)
        assert exc_worker_missing.value.code is ErrorCode.FORBIDDEN
        assert exc_worker_missing.value.details["reason"] == "no_active_grant"
        assert str(fv_1_v2) not in str(exc_worker_missing.value.details)
        assert expected_digest not in str(exc_worker_missing.value.details)
        uow.rollback()

    # Issue a short-lived grant on v1 only (not v2) -> still FORBIDDEN without leaking fv_1_v2
    with mem_h.app.uow_factory(req_meta(mem_h, 896), readonly=False) as uow:
        artifacts.grant_access(
            uow,
            principal_id=WORKER_ID,
            version_ids=(fv_1_v1, fv_2),
            reason=artifacts.GrantReason.ASSIGNMENT,
            ref="assign-1",
            expires_at=mem_h.clock.now() + timedelta(minutes=5),
            ids=grant_ids,
            now=mem_h.clock.now(),
        )
        uow.commit()

    with mem_h.app.uow_factory(req_meta(mem_h, 897), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        draft = uow.repo(DraftRepository).get(draft_id)
        ctx_worker = make_prepare_ctx(uow, mem_h, plan_id, actor=worker_actor, seq=897)
        with pytest.raises(Forbidden) as exc_worker_no_v2:
            prepare(uow, ctx_worker, plan, draft)
        assert exc_worker_no_v2.value.code is ErrorCode.FORBIDDEN
        assert exc_worker_no_v2.value.details["reason"] == "no_active_grant"
        assert str(fv_1_v2) not in str(exc_worker_no_v2.value.details)
        assert expected_digest not in str(exc_worker_no_v2.value.details)
        uow.rollback()

    # Advance clock past expiry so grant is expired -> FORBIDDEN without leaking fv_1_v2
    mem_h.clock.advance(timedelta(minutes=10))
    with mem_h.app.uow_factory(req_meta(mem_h, 898), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        draft = uow.repo(DraftRepository).get(draft_id)
        ctx_worker = make_prepare_ctx(uow, mem_h, plan_id, actor=worker_actor, seq=898)
        with pytest.raises(Forbidden) as exc_worker_expired:
            prepare(uow, ctx_worker, plan, draft)
        assert exc_worker_expired.value.code is ErrorCode.FORBIDDEN
        assert exc_worker_expired.value.details["reason"] == "no_active_grant"
        assert str(fv_1_v2) not in str(exc_worker_expired.value.details)
        uow.rollback()

    # Issue active grants covering fv_1_v1, fv_1_v2, and fv_2 -> worker prepare succeeds
    with mem_h.app.uow_factory(req_meta(mem_h, 899), readonly=False) as uow:
        artifacts.grant_access(
            uow,
            principal_id=WORKER_ID,
            version_ids=(fv_1_v1, fv_1_v2, fv_2),
            reason=artifacts.GrantReason.ASSIGNMENT,
            ref="assign-2",
            expires_at=mem_h.clock.now() + timedelta(minutes=30),
            ids=grant_ids,
            now=mem_h.clock.now(),
        )
        uow.commit()

    with mem_h.app.uow_factory(req_meta(mem_h, 901), readonly=True) as uow:
        plan = uow.repo(PlanRepository).get(plan_id)
        draft = uow.repo(DraftRepository).get(draft_id)
        ctx_worker = make_prepare_ctx(uow, mem_h, plan_id, actor=worker_actor, seq=901)
        cand_worker = prepare(uow, ctx_worker, plan, draft)
        assert cand_worker.content_digest == expected_digest
        uow.rollback()


def test_rollback_preserves_draft(mem_h: Harness, monkeypatch: pytest.MonkeyPatch) -> None:
    _, fv_1 = upload_v1(mem_h, b"guideline-v1", filename="guide.txt")
    _, fv_2 = upload_v1(mem_h, b"reference-v1", filename="ref.txt")
    doc = _build_valid_spec_doc(fv_1_id=fv_1, fv_2_id=fv_2)
    plan_id, draft_id, draft_ver = _create_plan_and_draft(mem_h, doc)
    expected_digest = _compute_expected_digest(mem_h, draft_id, seq=870)

    def _bad_save(self: MemoryPlanRepository, plan: Plan, *, expected_version: int) -> None:
        raise RuntimeError("simulated database failure while updating plan")

    monkeypatch.setattr(MemoryPlanRepository, "save", _bad_save)

    with pytest.raises(InternalError) as exc_err:
        dispatch_new(
            mem_h.client,
            PublishRevision(
                plan_id=plan_id,
                draft_id=draft_id,
                expected_edit_version=draft_ver,
                expected_content_digest=expected_digest,
                reason="Failing publish",
            ),
        )
    assert exc_err.value.code is ErrorCode.INTERNAL_ERROR

    with mem_h.app.uow_factory(req_meta(mem_h, 871), readonly=True) as uow:
        draft = uow.repo(DraftRepository).get(draft_id)
        assert draft.state is DraftState.OPEN
        assert draft.edit_version == draft_ver
        assert draft.closed_at is None

        plan = uow.repo(PlanRepository).get(plan_id)
        assert plan.current_revision_id is None
        assert plan.next_revision_no == 1
        assert plan.row_version == 1

        events = uow.repo(EventReader).after_workspace_seq(
            mem_h.ws,
            0,
            types=frozenset({PlanRevisionPublished.event_type}),
            limit=50,
        )
        assert events == ()
        uow.rollback()
