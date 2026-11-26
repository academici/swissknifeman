"""Unit tests for ``planning.rebase_draft`` and ``planning.restore_revision``."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal, cast
from uuid import UUID

import pytest

from integration.artifacts.test_upload_flow import OWNER_ID, Harness, dispatch_new
from integration.planning.publication import req_meta, upload_next_version, upload_v1
from skm.application_bus.ports import EventReader
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, Forbidden, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import EntityId, FileVersionId, PlanId, RevisionId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.artifacts import public as artifacts
from skm.modules.planning.application.revision_writer import write_revision
from skm.modules.planning.domain.canonical import normalize_document, specification_digest
from skm.modules.planning.domain.draft import Draft, DraftId, DraftState
from skm.modules.planning.domain.events import DraftRebased, PlanRevisionPublished, PlanRevisionRestored
from skm.modules.planning.domain.revision import RevisionOrigin
from skm.modules.planning.domain.specification import SPECIFICATION_URN, from_document
from skm.modules.planning.generated.commands import (
    AbandonDraft,
    ArchivePlan,
    CreatePlan,
    OpenDraft,
    PublishRevision,
    RebaseDraft,
    RebaseDraftResolutionsItemVariant1,
    RebaseDraftResolutionsItemVariant2,
    RestoreRevision,
    SaveDraft,
)
from skm.modules.planning.generated.queries import PreviewPublication
from skm.modules.planning.generated.results import (
    PublishRevisionResult,
    RebaseDraftResult,
    RestoreRevisionResult,
    SaveDraftResult,
)
from skm.modules.planning.generated.views import PublicationPreviewView
from skm.modules.planning.ports import DraftRepository, PlanningQueries, PlanRepository, RevisionRepository
from skm.modules.workspace.public import ArchiveProject
from unit.planning.application.test_publish_revision import (
    ITEM_ID,
    MAT_LATEST_ID,
    MAT_PINNED_ID,
    PHASE_ID,
    TOKEN_ID_1,
    TOKEN_ID_2,
    VIEWER_ID,
    _issue_narrowed_actor,
    mem_h,
)

__all__ = [
    "mem_h",
    "test_rebase_clean_merge_success",
    "test_rebase_conflicts_roll_back",
    "test_rebase_cycle_and_split_incoming_ref_block_publish",
    "test_rebase_resolutions_applied",
    "test_restore_expected_current_cas_failure",
    "test_restore_no_changes_rejected",
    "test_restore_publishes_new_revision",
]

ROOT = Path(__file__).resolve().parents[4]
REBASE_EXAMPLE = ROOT / "tests/fixtures/corpus/examples/plans/rebase-three-way.json"
ITEM_2_ID = "01900000-0000-7000-8000-000000000103"
ITEM_3_ID = "01900000-0000-7000-8000-000000000104"
ITEM_4_ID = "01900000-0000-7000-8000-000000000105"


def _item_doc(item_id: str, key: str, title: str, **extra: Any) -> JsonObject:
    return {
        "id": item_id,
        "key": key,
        "phase": "P1",
        "title": title,
        "summary": f"{title} summary.",
        "why": "Required by spec.",
        "review": {"mode": "self", "reason": "focused test spec"},
        **extra,
    }


def _mat_doc(
    mat_id: str, key: str, title: str, fv_id: FileVersionId, role: str, policy: str, target: str, **extra: Any
) -> JsonObject:
    base = {"id": mat_id, "key": key, "title": title, "kind": "file_version", "file_version_id": str(fv_id)}
    return {**base, "role": role, "freshness": {"policy": policy}, "applies_to": [target], **extra}


def _build_spec_doc(
    *,
    title: str = "Spec v1",
    item_title: str = "Item 1",
    item_depends_on: list[str] | None = None,
    extra_items: list[JsonObject] | None = None,
    fv_1_id: FileVersionId | None = None,
    fv_2_id: FileVersionId | None = None,
) -> JsonObject:
    deps = {"depends_on": item_depends_on} if item_depends_on is not None else {}
    items: list[JsonValue] = [_item_doc(ITEM_ID, "P1.1", item_title, **deps), *(extra_items or [])]
    phase: JsonObject = {"id": PHASE_ID, "key": "P1", "title": "Phase 1", "goal": "Build"}
    phase["design_state"] = "skeleton"
    doc: JsonObject = {
        "schema": SPECIFICATION_URN,
        "title": title,
        "goal": "Deliver revision workflow",
        "phases": [phase],
        "items": items,
        "execution_constraints": {"strategy": "dag"},
    }
    if fv_1_id is not None and fv_2_id is not None:
        req = {"required_for": ["execution"]}
        m1 = _mat_doc(
            MAT_LATEST_ID, "api-guide", "API Guide", fv_1_id, "input", "latest_at_publish", "P1", **req
        )
        m2 = _mat_doc(MAT_PINNED_ID, "ref-notes", "Reference Notes", fv_2_id, "reference", "pinned", "P1.1")
        doc["materials"] = [m1, m2]
    return doc


def _open_and_save(
    h: Harness, plan_id: PlanId, doc: JsonObject, *, base: Literal["empty", "current"] = "current"
) -> tuple[DraftId, SaveDraftResult]:
    opened = dispatch_new(h.client, OpenDraft(plan_id=plan_id, base=base))
    saved = dispatch_new(
        h.client,
        SaveDraft(
            plan_id=plan_id,
            draft_id=opened.draft_id,
            expected_edit_version=opened.edit_version,
            merge_patch=doc,
        ),
    )
    return DraftId(opened.draft_id), saved


def _publish_draft(
    h: Harness, plan_id: PlanId, draft_id: UUID, edit_version: int, *, reason: str = "Publish"
) -> PublishRevisionResult:
    q = PreviewPublication(plan_id=plan_id, draft_id=draft_id, expected_edit_version=edit_version)
    preview = cast("PublicationPreviewView", h.client.ask(q))
    return dispatch_new(
        h.client,
        PublishRevision(
            plan_id=plan_id,
            draft_id=draft_id,
            expected_edit_version=edit_version,
            expected_content_digest=preview.content_digest,
            reason=reason,
        ),
    )


def _publish_doc(
    h: Harness, plan_id: PlanId, doc: JsonObject, *, reason: str = "Publish"
) -> PublishRevisionResult:
    draft_id, saved = _open_and_save(h, plan_id, doc, base="empty")
    return _publish_draft(h, plan_id, draft_id, saved.edit_version, reason=reason)


def _rebase(
    h: Harness,
    plan_id: PlanId,
    draft_id: UUID,
    ver: int,
    *,
    onto: UUID | None = None,
    res: tuple[Any, ...] | None = None,
) -> RebaseDraftResult:
    return dispatch_new(
        h.client,
        RebaseDraft(
            plan_id=plan_id,
            draft_id=draft_id,
            expected_edit_version=ver,
            onto_revision_id=onto,
            resolutions=res,
        ),
    )


def _restore(
    h: Harness, plan_id: PlanId, rev_no: int, *, expected: UUID | None = None, reason: str = "Restore"
) -> RestoreRevisionResult:
    return dispatch_new(
        h.client,
        RestoreRevision(
            plan_id=plan_id, revision_no=rev_no, reason=reason, expected_current_revision_id=expected
        ),
    )


def _seed_golden_rebase_example(
    h: Harness, seq: int = 700
) -> tuple[PlanId, DraftId, RevisionId, RevisionId, dict[str, Any]]:
    ex: dict[str, Any] = json.loads(REBASE_EXAMPLE.read_text())
    plan_id = PlanId(dispatch_new(h.client, CreatePlan(project_id=h.proj, title="Token Rotation")).plan_id)
    r1_id = RevisionId(UUID(ex["base_revision"]["revision_id"]))
    r2_id = RevisionId(UUID(ex["theirs_revision"]["revision_id"]))
    draft_id = DraftId(UUID(ex["draft"]["draft_id"]))
    base_doc = normalize_document(ex["base_revision"]["document"])
    theirs_doc = normalize_document(ex["theirs_revision"]["document"])
    draft_doc = normalize_document(ex["draft"]["document"])

    with h.app.uow_factory(req_meta(h, seq), readonly=False) as uow:
        plan = uow.repo(PlanRepository).lock(plan_id)
        now = h.clock.now()
        for rev_id, doc in ((r1_id, base_doc), (r2_id, theirs_doc)):
            spec, _ = from_document(doc)
            plan = write_revision(
                uow,
                None,
                plan,
                spec,
                doc,
                specification_digest(doc),
                origin=RevisionOrigin.DRAFT,
                reason="seed",
                revision_id=rev_id,
                actor=OWNER_ID,
                now=now,
            ).plan
        uow.repo(DraftRepository).add(
            Draft(
                id=draft_id,
                plan_id=plan.id,
                workspace_id=plan.workspace_id,
                base_revision_id=r1_id,
                edit_version=int(ex["draft"]["edit_version"]),
                document=draft_doc,
                state=DraftState.OPEN,
                published_revision_id=None,
                created_by=OWNER_ID,
                created_at=now,
                updated_by=OWNER_ID,
                updated_at=now,
                closed_at=None,
            )
        )
        uow.commit()
    return plan_id, draft_id, r1_id, r2_id, ex


def test_rebase_clean_merge_success(mem_h: Harness) -> None:
    plan_id = PlanId(dispatch_new(mem_h.client, CreatePlan(project_id=mem_h.proj, title="Plan")).plan_id)
    r1 = _publish_doc(mem_h, plan_id, _build_spec_doc(title="Title R1", item_title="Item R1"))
    draft_id, draft_save = _open_and_save(
        mem_h, plan_id, _build_spec_doc(title="Title R1", item_title="Item Edited in Draft")
    )
    extra_item = _item_doc(ITEM_2_ID, "P1.2", "Item 2 from R2")
    r2 = _publish_doc(
        mem_h, plan_id, _build_spec_doc(title="Title R2", item_title="Item R1", extra_items=[extra_item])
    )

    rebased = _rebase(mem_h, plan_id, draft_id, draft_save.edit_version, onto=r2.revision_id)
    assert (rebased.changed, rebased.edit_version) == (True, draft_save.edit_version + 1)
    assert (rebased.previous_base_revision_id, rebased.base_revision_id) == (r1.revision_id, r2.revision_id)
    assert (rebased.taken_from_current, rebased.kept_from_draft, rebased.resolved) == (2, 2, 0)
    assert rebased.counts.error == 0

    with mem_h.app.uow_factory(req_meta(mem_h, 710), readonly=True) as uow:
        stored = uow.repo(DraftRepository).get(draft_id)
        assert (stored.base_revision_id, stored.edit_version) == (r2.revision_id, rebased.edit_version)
        assert stored.document["title"] == "Title R2"
        items = cast("list[JsonObject]", stored.document["items"])
        assert [it["title"] for it in items] == ["Item Edited in Draft", "Item 2 from R2"]
        events = uow.repo(EventReader).after_workspace_seq(
            mem_h.ws, 0, types=frozenset({DraftRebased.event_type}), limit=10
        )
        assert len(events) == 1
        assert events[0].payload["previous_base_revision_id"] == str(r1.revision_id)
        assert events[0].payload["base_revision_id"] == str(r2.revision_id)
        assert (events[0].payload["taken_from_current"], events[0].payload["kept_from_draft"]) == (2, 2)
        uow.rollback()

    noop = _rebase(mem_h, plan_id, draft_id, rebased.edit_version)
    assert (noop.changed, noop.edit_version) == (False, rebased.edit_version)
    assert (noop.taken_from_current, noop.kept_from_draft, noop.resolved) == (0, 0, 0)
    res_item = RebaseDraftResolutionsItemVariant1(conflict_id="rc-000000000000", keep="yours")
    with pytest.raises(ValidationFailed) as exc_noop_res:
        _rebase(mem_h, plan_id, draft_id, rebased.edit_version, res=(res_item,))
    assert (exc_noop_res.value.code, exc_noop_res.value.details["conflict_id"]) == (
        ErrorCode.INVALID_REFERENCE,
        "rc-000000000000",
    )
    with mem_h.app.uow_factory(req_meta(mem_h, 711), readonly=True) as uow:
        events = uow.repo(EventReader).after_workspace_seq(
            mem_h.ws, 0, types=frozenset({DraftRebased.event_type}), limit=10
        )
        assert len(events) == 1
        uow.rollback()


def test_rebase_conflicts_roll_back(mem_h: Harness) -> None:
    plan_id, draft_id, r1_id, r2_id, example = _seed_golden_rebase_example(mem_h, seq=720)
    expected_conflicts = example["attempts"][0]["outcome"]["error"]["details"]["conflicts"]
    initial_ver = int(example["draft"]["edit_version"])

    with pytest.raises(Conflict) as exc_info:
        _rebase(mem_h, plan_id, draft_id, initial_ver, onto=r2_id)
    err = exc_info.value
    assert err.code is ErrorCode.REBASE_CONFLICTS
    assert err.details["conflicts"] == expected_conflicts
    assert (err.details["base_revision_id"], err.details["current_revision_id"]) == (str(r1_id), str(r2_id))
    assert (
        err.details["edit_version"],
        err.details["taken_from_current"],
        err.details["kept_from_draft"],
    ) == (initial_ver, 3, 4)

    with mem_h.app.uow_factory(req_meta(mem_h, 721), readonly=True) as uow:
        stored = uow.repo(DraftRepository).get(draft_id)
        assert (stored.edit_version, stored.base_revision_id) == (initial_ver, r1_id)
        assert stored.document == normalize_document(example["draft"]["document"])
        events = uow.repo(EventReader).after_workspace_seq(
            mem_h.ws, 0, types=frozenset({DraftRebased.event_type}), limit=10
        )
        assert events == ()
        uow.rollback()


def test_rebase_resolutions_applied(mem_h: Harness) -> None:
    plan_id, draft_id, r1_id, r2_id, example = _seed_golden_rebase_example(mem_h, seq=730)
    initial_ver = int(example["draft"]["edit_version"])

    with pytest.raises(Conflict) as exc_onto:
        _rebase(mem_h, plan_id, draft_id, initial_ver, onto=r1_id)
    assert exc_onto.value.code is ErrorCode.BASE_REVISION_CHANGED

    with pytest.raises(Conflict) as exc_ver:
        _rebase(mem_h, plan_id, draft_id, initial_ver + 9)
    assert exc_ver.value.code is ErrorCode.VERSION_CONFLICT

    res_unknown = RebaseDraftResolutionsItemVariant1(conflict_id="rc-000000000000", keep="yours")
    with pytest.raises(ValidationFailed) as exc_unknown:
        _rebase(mem_h, plan_id, draft_id, initial_ver, res=(res_unknown,))
    assert exc_unknown.value.code is ErrorCode.INVALID_REFERENCE

    viewer_client = mem_h.app.client(
        actor=Actor(principal_id=VIEWER_ID, kind=PrincipalKind.HUMAN, display_name="viewer"),
        surface=Surface.CLI,
    )
    with pytest.raises(Forbidden):
        dispatch_new(
            viewer_client,
            RebaseDraft(plan_id=plan_id, draft_id=draft_id, expected_edit_version=initial_ver),
        )

    idem_key = mem_h.client.new_idempotency_key()
    cmd = RebaseDraft(
        plan_id=plan_id,
        draft_id=draft_id,
        expected_edit_version=initial_ver,
        onto_revision_id=r2_id,
        resolutions=(
            RebaseDraftResolutionsItemVariant1(conflict_id="rc-9cbaaa46efcf", keep="theirs"),
            RebaseDraftResolutionsItemVariant2(conflict_id="rc-f29269c02890", new_key="P1.6"),
        ),
    )
    res_1 = cast("RebaseDraftResult", mem_h.client.dispatch(cmd, idempotency_key=idem_key))
    res_2 = cast("RebaseDraftResult", mem_h.client.dispatch(cmd, idempotency_key=idem_key))
    assert res_1 == res_2
    assert (res_1.changed, res_1.edit_version) == (True, initial_ver + 1)
    assert (res_1.previous_base_revision_id, res_1.base_revision_id) == (r1_id, r2_id)
    assert (res_1.taken_from_current, res_1.kept_from_draft, res_1.resolved) == (3, 4, 2)

    with mem_h.app.uow_factory(req_meta(mem_h, 731), readonly=True) as uow:
        stored = uow.repo(DraftRepository).get(draft_id)
        assert stored.document == normalize_document(example["attempts"][1]["outcome"]["document"])
        uow.rollback()

    dispatch_new(
        mem_h.client,
        AbandonDraft(plan_id=plan_id, draft_id=draft_id, expected_edit_version=res_1.edit_version),
    )
    with pytest.raises(PreconditionFailed) as exc_closed:
        _rebase(mem_h, plan_id, draft_id, res_1.edit_version + 1)
    assert exc_closed.value.code is ErrorCode.DRAFT_NOT_OPEN


def test_rebase_cycle_and_split_incoming_ref_block_publish(mem_h: Harness) -> None:
    """Проверка ench6: A->B + B->A cycle and item split with unrewritten incoming ref block publish."""
    plan_id = PlanId(dispatch_new(mem_h.client, CreatePlan(project_id=mem_h.proj, title="Plan")).plan_id)
    item_2_base = _item_doc(ITEM_2_ID, "P1.2", "Item 2")
    _publish_doc(mem_h, plan_id, _build_spec_doc(extra_items=[item_2_base]), reason="R1")

    cycle_id, cycle_save = _open_and_save(
        mem_h, plan_id, _build_spec_doc(item_depends_on=["P1.2"], extra_items=[item_2_base])
    )
    split_items = [_item_doc(ITEM_3_ID, "P1.3", "Split A"), _item_doc(ITEM_4_ID, "P1.4", "Split B")]
    split_id, split_save = _open_and_save(mem_h, plan_id, _build_spec_doc(extra_items=split_items))
    assert (cycle_save.counts.error, split_save.counts.error) == (0, 0)

    r2 = _publish_doc(
        mem_h,
        plan_id,
        _build_spec_doc(extra_items=[_item_doc(ITEM_2_ID, "P1.2", "Item 2", depends_on=["P1.1"])]),
        reason="R2",
    )
    rebased_cycle = _rebase(mem_h, plan_id, cycle_id, cycle_save.edit_version, onto=r2.revision_id)
    assert (rebased_cycle.changed, rebased_cycle.counts.error >= 1) == (True, True)
    with pytest.raises(PreconditionFailed) as exc_cycle:
        _publish_draft(mem_h, plan_id, cycle_id, rebased_cycle.edit_version)
    assert exc_cycle.value.code is ErrorCode.PLAN_NOT_READY
    assert any(
        f["code"] == "dependency_cycle" for f in cast("list[JsonObject]", exc_cycle.value.details["findings"])
    )

    r3 = _publish_doc(
        mem_h, plan_id, _build_spec_doc(item_depends_on=["P1.2"], extra_items=[item_2_base]), reason="R3"
    )
    rebased_split = _rebase(mem_h, plan_id, split_id, split_save.edit_version, onto=r3.revision_id)
    assert (rebased_split.changed, rebased_split.counts.error >= 1) == (True, True)
    with pytest.raises(PreconditionFailed) as exc_split:
        _publish_draft(mem_h, plan_id, split_id, rebased_split.edit_version)
    assert exc_split.value.code is ErrorCode.PLAN_NOT_READY
    assert any(
        f["code"] == "ref_unknown" for f in cast("list[JsonObject]", exc_split.value.details["findings"])
    )

    with mem_h.app.uow_factory(req_meta(mem_h, 735), readonly=True) as uow:
        assert uow.repo(PlanRepository).get(plan_id).current_revision_id == r3.revision_id
        known_ids = set(uow.repo(RevisionRepository).identities(plan_id))
        assert EntityId(UUID(ITEM_2_ID)) in known_ids
        assert {EntityId(UUID(ITEM_3_ID)), EntityId(UUID(ITEM_4_ID))}.isdisjoint(known_ids)
        revs = uow.repo(RevisionRepository).list_for_plan(plan_id, before_revision_no=None, limit=10)
        assert [m.revision_no for m in revs] == [3, 2, 1]
        pub_events = uow.repo(EventReader).after_workspace_seq(
            mem_h.ws, 0, types=frozenset({PlanRevisionPublished.event_type}), limit=10
        )
        assert len(pub_events) == 3
        uow.rollback()


def test_restore_publishes_new_revision(mem_h: Harness) -> None:
    file_1, fv_1_v1 = upload_v1(mem_h, b"guide-v1", filename="guide.txt")
    _, fv_2 = upload_v1(mem_h, b"notes-v1", filename="notes.txt")
    plan_id = PlanId(dispatch_new(mem_h.client, CreatePlan(project_id=mem_h.proj, title="Plan")).plan_id)

    r1 = _publish_doc(
        mem_h, plan_id, _build_spec_doc(title="Plan R1", fv_1_id=fv_1_v1, fv_2_id=fv_2), reason="R1"
    )
    fv_1_v2 = upload_next_version(mem_h, file_1, 2, b"guide-v2", filename="guide-v2.txt")
    r2 = _publish_doc(
        mem_h, plan_id, _build_spec_doc(title="Plan R2", fv_1_id=fv_1_v1, fv_2_id=fv_2), reason="R2"
    )
    assert (r2.revision_no, r2.pinned_materials[0].file_version_id) == (2, fv_1_v2)

    open_on_r2 = dispatch_new(mem_h.client, OpenDraft(plan_id=plan_id, base="current"))
    idem_key = mem_h.client.new_idempotency_key()
    restore_cmd = RestoreRevision(
        plan_id=plan_id, revision_no=1, reason="Restore R1", expected_current_revision_id=r2.revision_id
    )
    r3 = cast("RestoreRevisionResult", mem_h.client.dispatch(restore_cmd, idempotency_key=idem_key))
    r3_replay = cast("RestoreRevisionResult", mem_h.client.dispatch(restore_cmd, idempotency_key=idem_key))
    assert r3 == r3_replay
    assert (r3.revision_no, r3.parent_revision_id) == (3, r2.revision_id)
    assert (r3.restored_from_revision_id, r3.restored_from_revision_no) == (r1.revision_id, 1)
    assert r3.content_digest == r1.content_digest

    with mem_h.app.uow_factory(req_meta(mem_h, 740), readonly=True) as uow:
        meta_3 = uow.repo(RevisionRepository).get_meta(RevisionId(r3.revision_id))
        assert meta_3.origin is RevisionOrigin.RESTORE
        assert (meta_3.restored_from_revision_id, meta_3.parent_revision_id) == (
            r1.revision_id,
            r2.revision_id,
        )
        assert meta_3.change_reason == "Restore R1"

        pins = uow.repo(PlanningQueries).revision_pins(RevisionId(r3.revision_id))
        assert {p.material_id: p.file_version_id for p in pins} == {
            EntityId(UUID(MAT_LATEST_ID)): fv_1_v1,
            EntityId(UUID(MAT_PINNED_ID)): fv_2,
        }
        assert uow.repo(DraftRepository).get(DraftId(open_on_r2.draft_id)).base_revision_id == r2.revision_id
        assert uow.repo(PlanRepository).get(plan_id).current_revision_id == r3.revision_id

        events = uow.repo(EventReader).after_workspace_seq(
            mem_h.ws,
            0,
            types=frozenset({PlanRevisionPublished.event_type, PlanRevisionRestored.event_type}),
            limit=20,
        )
        assert [ev.type for ev in events[-2:]] == [
            PlanRevisionPublished.event_type,
            PlanRevisionRestored.event_type,
        ]
        assert (events[-2].payload["origin"], events[-2].payload["draft_id"]) == ("restore", None)
        assert events[-1].payload["restored_from_revision_id"] == str(r1.revision_id)
        uow.rollback()


def test_restore_expected_current_cas_failure(mem_h: Harness) -> None:
    plan_id = PlanId(dispatch_new(mem_h.client, CreatePlan(project_id=mem_h.proj, title="Plan")).plan_id)
    r1 = _publish_doc(mem_h, plan_id, _build_spec_doc(title="Plan R1"))
    r2 = _publish_doc(mem_h, plan_id, _build_spec_doc(title="Plan R2"))

    d_r2, s_r2 = _open_and_save(mem_h, plan_id, _build_spec_doc(title="Plan R3 from draft"))
    r3 = _restore(mem_h, plan_id, 1, expected=r2.revision_id, reason="Restore R1")
    with pytest.raises(Conflict) as exc_stale_pub:
        _publish_draft(mem_h, plan_id, d_r2, s_r2.edit_version, reason="Stale draft publish")
    assert exc_stale_pub.value.code is ErrorCode.BASE_REVISION_CHANGED

    r4 = _publish_doc(mem_h, plan_id, _build_spec_doc(title="Plan R4"))
    with pytest.raises(Conflict) as exc_cas:
        _restore(mem_h, plan_id, 1, expected=r3.revision_id, reason="Stale expected current revision")
    assert exc_cas.value.code is ErrorCode.BASE_REVISION_CHANGED
    assert exc_cas.value.details["current_revision_id"] == str(r4.revision_id)

    r5 = _restore(mem_h, plan_id, 1, reason="Unconditional")
    assert (r5.revision_no, r5.parent_revision_id, r5.restored_from_revision_id) == (
        5,
        r4.revision_id,
        r1.revision_id,
    )


def _narrow_client(h: Harness, token_id: UUID, prefix: str, perms: tuple[str, ...], seq: int) -> Any:
    actor = _issue_narrowed_actor(
        h, token_id=token_id, prefix=prefix, name=prefix, permissions=perms, seq=seq
    )
    return h.app.client(actor=actor, surface=Surface.CLI)


def test_restore_no_changes_rejected(mem_h: Harness) -> None:
    file_1, fv_1 = upload_v1(mem_h, b"guide-v1", filename="guide.txt")
    _, fv_2 = upload_v1(mem_h, b"notes-v1", filename="notes.txt")
    plan_id = PlanId(dispatch_new(mem_h.client, CreatePlan(project_id=mem_h.proj, title="Plan")).plan_id)
    r1 = _publish_doc(mem_h, plan_id, _build_spec_doc(title="Plan R1", fv_1_id=fv_1, fv_2_id=fv_2))
    r2 = _publish_doc(mem_h, plan_id, _build_spec_doc(title="Plan R2", fv_1_id=fv_1, fv_2_id=fv_2))

    with pytest.raises(PreconditionFailed) as exc_same:
        _restore(mem_h, plan_id, 2, expected=r2.revision_id, reason="Same as current")
    assert exc_same.value.code is ErrorCode.NO_CHANGES

    with pytest.raises(NotFound) as exc_nf:
        _restore(mem_h, plan_id, 99, reason="Missing")
    assert (exc_nf.value.code, exc_nf.value.details["kind"]) == (ErrorCode.NOT_FOUND, "revision")

    no_plan_read = _narrow_client(mem_h, TOKEN_ID_1, "aaaaaaaa", ("plan.publish",), 750)
    with pytest.raises(Forbidden):
        dispatch_new(no_plan_read, RestoreRevision(plan_id=plan_id, revision_no=1, reason="No plan.read"))

    no_file_read = _narrow_client(mem_h, TOKEN_ID_2, "bbbbbbbb", ("plan.publish", "plan.read"), 751)
    with pytest.raises(Forbidden):
        dispatch_new(no_file_read, RestoreRevision(plan_id=plan_id, revision_no=1, reason="No file.read"))

    dispatch_new(mem_h.client, artifacts.TrashFile(file_id=file_1, expected_row_version=2, reason="trash"))
    with pytest.raises(PreconditionFailed) as exc_unready:
        _restore(mem_h, plan_id, 1, reason="Restore with trashed file")
    assert exc_unready.value.code is ErrorCode.PLAN_NOT_READY
    findings = cast("list[JsonObject]", exc_unready.value.details["findings"])
    assert any(f["code"] == "material_unavailable" for f in findings)
    assert all(f["severity"] == "error" for f in findings)

    dispatch_new(mem_h.client, artifacts.RestoreFile(file_id=file_1, expected_row_version=3))
    dispatch_new(mem_h.client, ArchivePlan(plan_id=plan_id, expected_row_version=3))
    with pytest.raises(PreconditionFailed) as exc_arch:
        _restore(mem_h, plan_id, 1, reason="Archived plan")
    assert exc_arch.value.code is ErrorCode.PLAN_ARCHIVED

    dispatch_new(
        mem_h.client, ArchiveProject(project_id=mem_h.proj, expected_row_version=1, reason="archive")
    )
    assert r1.revision_no == 1
