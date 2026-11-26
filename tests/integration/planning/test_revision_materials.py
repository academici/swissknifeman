"""End-to-end integration tests for revision materials, freshness, and blob integrity."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from integration.artifacts.test_upload_flow import (
    Harness,
    clean_test_database,
    dispatch_new,
    pg_session,
    test_database,
)
from integration.planning.test_trash_publish_pin import (
    base_spec_doc,
    open_env,
    req_meta,
    upload_file,
    upload_version,
)
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, InternalError, NotFound, PreconditionFailed
from skm.kernel.ids import EntityId, FileVersionId, RevisionId, ScopeId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import UnitOfWork
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.domain.blob import LocationState
from skm.modules.artifacts.ports import BlobLocationRef, BlobRepository, BlobStore, FileVersionRepository
from skm.modules.planning import public as planning
from skm.modules.planning.generated.commands import (
    CreatePlan,
    OpenDraft,
    PublishRevision,
    RestoreRevision,
    SaveDraft,
)
from skm.modules.planning.generated.queries import GetRevision, PreviewPublication
from skm.modules.planning.ports import RevisionRepository
from skm.platform.config.store import ConfigStore, ScopeTree
from support.pg import TestDatabase

__all__ = ["clean_test_database", "pg_session", "test_database"]

PHASE_UUID = UUID("0192f5c4-0000-7000-8000-000000000011")
ITEM_UUID = UUID("0192f5c4-0000-7000-8000-000000000012")
MAT_PINNED_UUID, MAT_LATEST_UUID, MAT_REFRESH_FV_UUID, MAT_REPO_UUID, MAT_EXT_UUID = (
    UUID(f"0192f5c4-0000-7000-8000-00000000004{i}") for i in range(1, 6)
)
EXT_SRC_ID = "0193a000-0000-7000-8000-000000ee0001"
SELECTOR_ROTATION: JsonObject = {"kind": "section_id", "value": "rotation"}


@pytest.fixture
def mem_env(tmp_path: Path) -> Iterator[Harness]:
    yield from open_env("memory", tmp_path, None)


@pytest.fixture
def pg_env(clean_test_database: TestDatabase, tmp_path: Path) -> Iterator[Harness]:
    yield from open_env("postgres", tmp_path, clean_test_database)


def _fv_mat(
    uid: UUID,
    key: str,
    vid: FileVersionId,
    role: str,
    req: list[str],
    freshness: JsonObject,
    applies_to: list[str],
    selector: JsonObject | None = None,
) -> JsonObject:
    mat: JsonObject = {
        "id": str(uid),
        "key": key,
        "title": key,
        "kind": "file_version",
        "file_version_id": str(vid),
        "role": role,
        "required_for": cast("list[JsonValue]", req),
        "freshness": freshness,
        "applies_to": cast("list[JsonValue]", applies_to),
    }
    if selector is not None:
        mat["selector"] = selector
    return mat


def _build_spec_doc(
    pinned_vid: FileVersionId,
    latest_vid: FileVersionId,
    refresh_vid: FileVersionId,
    retrieved_at: str,
    goal: str = "Issue one-time refresh tokens and preserve material pins.",
) -> JsonObject:
    refresh_policy: JsonObject = {"policy": "must_refresh", "max_age_seconds": 3600}
    ext_policy: JsonObject = {"policy": "must_refresh", "max_age_seconds": 7200}
    materials: list[JsonValue] = [
        _fv_mat(
            MAT_PINNED_UUID,
            "storage-design",
            pinned_vid,
            "input",
            ["execution", "review"],
            {"policy": "pinned"},
            ["P1", "P1.1"],
        ),
        _fv_mat(
            MAT_LATEST_UUID,
            "rotation-guide",
            latest_vid,
            "input",
            ["execution"],
            {"policy": "latest_at_publish"},
            ["P1.1"],
            SELECTOR_ROTATION,
        ),
        _fv_mat(
            MAT_REFRESH_FV_UUID,
            "security-checklist",
            refresh_vid,
            "reference",
            ["acceptance"],
            refresh_policy,
            ["P1.1"],
        ),
        {
            "id": str(MAT_REPO_UUID),
            "key": "auth-module",
            "title": "Current auth module",
            "kind": "repository_path",
            "mount": "api",
            "path": "src/auth/README.md",
            "role": "reference",
            "required_for": ["review"],
            "freshness": {"policy": "pinned"},
            "global": True,
        },
        {
            "id": str(MAT_EXT_UUID),
            "key": "oauth-threats",
            "title": "OAuth 2.0 refresh token threats",
            "kind": "external_source",
            "url": "https://datatracker.ietf.org/doc/html/rfc6819#section-5.2.2.3",
            "retrieved_at": retrieved_at,
            "role": "reference",
            "required_for": ["review"],
            "freshness": ext_policy,
            "applies_to": ["P1.1"],
            "external_source_id": EXT_SRC_ID,
        },
    ]
    return base_spec_doc(materials, goal=goal, phase_id=PHASE_UUID, item_id=ITEM_UUID)


def _publish_via_bus(
    h: Harness, plan_id: UUID, doc: JsonObject, *, base: str, reason: str
) -> tuple[RevisionId, str]:
    opened = dispatch_new(h.client, OpenDraft(plan_id=plan_id, base=cast("Any", base)))
    saved = dispatch_new(h.client, SaveDraft(plan_id, opened.draft_id, opened.edit_version, cast("Any", doc)))
    preview: Any = h.client.ask(PreviewPublication(plan_id, opened.draft_id, saved.edit_version))
    assert preview.publishable
    pub = dispatch_new(
        h.client,
        PublishRevision(plan_id, opened.draft_id, saved.edit_version, preview.content_digest, reason),
    )
    return RevisionId(pub.revision_id), str(pub.content_digest)


def _verify_candidate_cas_and_restore(
    h: Harness,
    plan_uuid: UUID,
    *,
    design_v1: FileVersionId,
    guide_file: UUID,
    guide_v1: FileVersionId,
    guide_v2: FileVersionId,
    checklist_v1: FileVersionId,
    retrieved_iso: str,
) -> None:
    opened2 = dispatch_new(h.client, OpenDraft(plan_id=plan_uuid, base="current"))
    doc2 = _build_spec_doc(
        design_v1, guide_v1, checklist_v1, retrieved_iso, goal="Updated goal resolving latest guide."
    )
    saved2 = dispatch_new(
        h.client, SaveDraft(plan_uuid, opened2.draft_id, opened2.edit_version, cast("Any", doc2))
    )
    preview2: Any = h.client.ask(PreviewPublication(plan_uuid, opened2.draft_id, saved2.edit_version))
    assert preview2.pinned_materials[1].file_version_id == guide_v2

    guide_v3 = upload_version(h, guide_file, 3, b"guide v3\n", filename="guide.md")
    with pytest.raises(Conflict) as cas_err:
        dispatch_new(
            h.client,
            PublishRevision(plan_uuid, opened2.draft_id, saved2.edit_version, preview2.content_digest, "cas"),
        )
    assert cas_err.value.code is ErrorCode.VERSION_CONFLICT
    assert cas_err.value.details.get("reason") == "candidate_changed"

    fresh: Any = h.client.ask(PreviewPublication(plan_uuid, opened2.draft_id, saved2.edit_version))
    pub2 = dispatch_new(
        h.client,
        PublishRevision(plan_uuid, opened2.draft_id, saved2.edit_version, fresh.content_digest, "r2"),
    )
    rev2_id = RevisionId(pub2.revision_id)

    # RestoreRevision(1) keeps rev1's historical guide_v1 pin without re-resolving to guide_v3.
    restored = dispatch_new(h.client, RestoreRevision(plan_uuid, 1, "restore rev1", pub2.revision_id))
    rev3_id = RevisionId(restored.revision_id)

    with h.app.uow_factory(req_meta(h, 20), readonly=True) as uow:
        mats_r2 = planning.revision_materials(uow, rev2_id)
        mats_r3 = planning.revision_materials(uow, rev3_id)
        assert [m["file_version_id"] for m in mats_r2[:2]] == [str(design_v1), str(guide_v3)]
        assert [m["file_version_id"] for m in mats_r3[:2]] == [str(design_v1), str(guide_v1)]
        revs = uow.repo(RevisionRepository)
        assert revs.load_typed_document(rev3_id) == revs.get_document(rev3_id)
        uow.rollback()


def _exercise_end_to_end_revision_materials(h: Harness) -> None:
    design_file, design_v1 = upload_file(h, b"storage schema v1\n", filename="storage.md", title="Storage")
    guide_file, guide_v1 = upload_file(h, b"guide v1\n", filename="guide.md", title="Rotation Guide")
    _, checklist_v1 = upload_file(h, b"checklist v1\n", filename="check.md", title="Checklist")

    retrieved_iso = h.clock.now().isoformat().replace("+00:00", "Z")
    plan_uuid = UUID(str(dispatch_new(h.client, CreatePlan(h.proj, "Refresh token rotation")).plan_id))

    doc1 = _build_spec_doc(design_v1, guide_v1, checklist_v1, retrieved_iso)
    rev1_id, rev1_digest = _publish_via_bus(h, plan_uuid, doc1, base="empty", reason="publish rev1")

    # Upload v2 of both files AFTER rev1 publication: rev1 must keep reading v1 snapshots.
    h.clock.advance(timedelta(seconds=30))
    design_v2 = upload_version(h, design_file, 2, b"storage schema v2\n", filename="storage.md")
    guide_v2 = upload_version(h, guide_file, 2, b"guide v2\n", filename="guide.md")

    rev_view: Any = h.client.ask(GetRevision(plan_uuid, UUID(str(rev1_id)), include_document=True))
    assert rev_view.content_digest == rev1_digest

    with h.app.uow_factory(req_meta(h, 10), readonly=True) as uow:
        mats_r1 = planning.revision_materials(uow, rev1_id)
        expected = ["storage-design", "rotation-guide", "security-checklist", "auth-module", "oauth-threats"]
        assert [m["key"] for m in mats_r1] == expected
        assert mats_r1[0]["file_version_id"] == str(design_v1)
        assert mats_r1[0]["applies_to"] == ["P1.1", "P1"]
        assert mats_r1[0]["applies_to_entity_ids"] == [str(ITEM_UUID), str(PHASE_UUID)]
        assert mats_r1[1]["file_version_id"] == str(guide_v1)
        assert mats_r1[1]["selector"] == SELECTOR_ROTATION
        assert mats_r1[2]["file_version_id"] == str(checklist_v1)
        assert mats_r1[3]["is_global"] is True
        assert mats_r1[4]["external_source_id"] == EXT_SRC_ID

        # Mutating returned MaterialRef must never mutate persisted/cached revision state.
        cast("dict[str, JsonValue]", mats_r1[1]["selector"])["value"] = "tampered"
        cast("list[JsonValue]", mats_r1[0]["required_for"]).append("acceptance")
        reread = planning.revision_materials(uow, rev1_id)
        assert reread[1]["selector"] == SELECTOR_ROTATION
        assert reread[0]["required_for"] == ["execution", "review"]

        revs = uow.repo(RevisionRepository)
        assert revs.load_typed_document(rev1_id) == revs.get_document(rev1_id)
        spec_r1 = planning.get_revision_specification(uow, rev1_id)
        assert [m.file_version_id for m in spec_r1.materials[:2]] == [design_v1, guide_v1]
        assert artifacts.read_text_content(uow, design_v1, max_bytes=1024) == "storage schema v1\n"
        assert artifacts.read_text_content(uow, design_v2, max_bytes=1024) == "storage schema v2\n"
        uow.rollback()

    with h.client.open_file_version_content(design_v1) as stream:
        assert stream.read() == b"storage schema v1\n"

    _verify_candidate_cas_and_restore(
        h,
        plan_uuid,
        design_v1=design_v1,
        guide_file=guide_file,
        guide_v1=guide_v1,
        guide_v2=guide_v2,
        checklist_v1=checklist_v1,
        retrieved_iso=retrieved_iso,
    )


def test_end_to_end_revision_materials_memory(mem_env: Harness) -> None:
    _exercise_end_to_end_revision_materials(mem_env)


@pytest.mark.pg
def test_end_to_end_revision_materials_postgres(pg_env: Harness) -> None:
    _exercise_end_to_end_revision_materials(pg_env)


def _exercise_assess_material_without_run(h: Harness) -> None:
    t0 = h.clock.now()
    _, v1 = upload_file(h, b"v1\n", filename="doc.md", title="Doc")
    plan_uuid = UUID(str(dispatch_new(h.client, CreatePlan(h.proj, "Assess")).plan_id))
    doc = _build_spec_doc(v1, v1, v1, t0.isoformat().replace("+00:00", "Z"))
    rev_id, _ = _publish_via_bus(h, plan_uuid, doc, base="empty", reason="assess")

    with h.app.uow_factory(req_meta(h, 30), readonly=True) as uow:
        pinned_ref, latest_ref, refresh_fv_ref, repo_ref, ext_ref = planning.revision_materials(uow, rev_id)
        spec = planning.get_revision_specification(uow, rev_id)
        uow.rollback()

    ready = planning.MaterialObservation(
        planning.FileVersionObservation(planning.FileVersionStatus.READY, t0), None
    )
    later = t0 + timedelta(days=30)
    avail = planning.MaterialState.AVAILABLE
    assert planning.assess_material(pinned_ref, ready, now=later).state is avail
    assert planning.assess_material(latest_ref, ready, now=later).state is avail
    assert planning.assess_material(spec.materials[0], ready, now=later).material_id == EntityId(
        MAT_PINNED_UUID
    )

    assert planning.assess_material(refresh_fv_ref, ready, now=t0 + timedelta(seconds=3600)).state is avail
    stale_fv = planning.assess_material(refresh_fv_ref, ready, now=t0 + timedelta(seconds=3601))
    assert (stale_fv.state, stale_fv.blocks) == (
        planning.MaterialState.STALE,
        frozenset({planning.MaterialStage.ACCEPTANCE}),
    )

    assert planning.assess_material(ext_ref, None, now=t0 + timedelta(seconds=7200)).state is avail
    stale_ext = planning.assess_material(ext_ref, None, now=t0 + timedelta(seconds=7201))
    assert (stale_ext.state, stale_ext.blocks) == (
        planning.MaterialState.STALE,
        frozenset({planning.MaterialStage.REVIEW}),
    )

    not_ready = planning.MaterialObservation(
        planning.FileVersionObservation(planning.FileVersionStatus.NOT_READY, t0), None
    )
    nr = planning.assess_material(pinned_ref, not_ready, now=t0)
    assert (nr.state, nr.blocks) == (
        planning.MaterialState.NOT_READY,
        frozenset({planning.MaterialStage.EXECUTION, planning.MaterialStage.REVIEW}),
    )
    assert planning.assess_material(pinned_ref, None, now=t0).state is planning.MaterialState.MISSING

    unknown_repo = planning.assess_material(repo_ref, None, now=t0)
    assert (unknown_repo.state, unknown_repo.blocks) == (planning.MaterialState.UNKNOWN, frozenset())
    missing_repo = planning.assess_material(repo_ref, planning.MaterialObservation(None, False), now=t0)
    assert (missing_repo.state, missing_repo.blocks) == (
        planning.MaterialState.MISSING,
        frozenset({planning.MaterialStage.REVIEW}),
    )
    assert planning.assess_material(repo_ref, planning.MaterialObservation(None, True), now=t0).state is avail


def test_assess_material_without_run_memory(mem_env: Harness) -> None:
    _exercise_assess_material_without_run(mem_env)


@pytest.mark.pg
def test_assess_material_without_run_postgres(pg_env: Harness) -> None:
    _exercise_assess_material_without_run(pg_env)


def _blob_location_and_digest(
    h: Harness, version_id: FileVersionId, *, seq: int
) -> tuple[BlobLocationRef, str]:
    with h.app.uow_factory(req_meta(h, seq), readonly=True) as uow:
        ver = uow.repo(FileVersionRepository).get(version_id)
        blobs = uow.repo(BlobRepository)
        blob, loc = blobs.get(ver.blob_id), blobs.locations(ver.blob_id)[0]
        uow.rollback()
        ref: BlobLocationRef = {
            "backend_id": loc.backend_id,
            "storage_key": loc.storage_key,
            "storage_version": None,
        }
        return ref, blob.digest.value


def _set_location_state(h: Harness, version_id: FileVersionId, state: LocationState, *, seq: int) -> None:
    with h.app.uow_factory(req_meta(h, seq)) as uow:
        ver = uow.repo(FileVersionRepository).get(version_id)
        blobs = uow.repo(BlobRepository)
        blobs.mark_location(ver.blob_id, blobs.locations(ver.blob_id)[0].backend_id, state, h.clock.now())
        uow.commit()


def _validate_rev(h: Harness, uow: UnitOfWork, plan_uuid: UUID, rev_id: RevisionId) -> Any:
    scope_id = ScopeId(plan_uuid)
    chain = uow.repo(ScopeRegistry).ancestors(scope_id)
    eff_cfg = h.app.config.effective(
        uow.repo(ConfigStore), uow.repo(ScopeTree), ScopeRef(ScopeKind.PLAN, scope_id)
    )
    return planning.validate_revision(uow, rev_id, scope_chain=chain, config=eff_cfg, now=h.clock.now())


def _verify_corruption_and_recovery(
    h: Harness,
    plan_uuid: UUID,
    rev1_id: RevisionId,
    v1: FileVersionId,
    v1_bytes: bytes,
    v2_bytes: bytes,
    v1_digest: str,
    loc_v1: BlobLocationRef,
    v1_path: Path,
    v2_path: Path,
) -> None:
    store = h.app.gateways.get(BlobStore)

    # Structural corruption (symlink v1 -> v2): refused with blob_corrupt, never reads v2 bytes.
    os.symlink(v2_path, v1_path)
    assert store.verify(loc_v1, v1_digest) is False
    with pytest.raises(InternalError) as sym_open:
        h.client.open_file_version_content(v1)
    assert sym_open.value.details.get("reason") == "blob_corrupt"
    with h.app.uow_factory(req_meta(h, 45), readonly=True) as uow:
        with pytest.raises(InternalError) as sym_text:
            artifacts.read_text_content(uow, v1, max_bytes=1024)
        assert sym_text.value.details.get("reason") == "blob_corrupt"
        uow.rollback()
    os.unlink(v1_path)

    # Bit-level corruption at v1's object path: verify is False and promote detects blob_corrupt.
    v1_path.write_bytes(v2_bytes)
    os.chmod(v1_path, 0o444)
    assert store.verify(loc_v1, v1_digest) is False
    with pytest.raises(InternalError) as reupload_corrupt:
        h.client.upload_blob(h.ws, [v1_bytes], size=len(v1_bytes), media_type="text/plain")
    assert reupload_corrupt.value.details.get("reason") == "blob_corrupt"

    # Restore exact original v1 bytes: verify, stream open, text read, and validation all recover.
    os.chmod(v1_path, 0o600)
    v1_path.write_bytes(v1_bytes)
    os.chmod(v1_path, 0o444)

    assert store.verify(loc_v1, v1_digest) is True
    with h.client.open_file_version_content(v1) as recovered:
        assert recovered.read() == v1_bytes
    with h.app.uow_factory(req_meta(h, 46), readonly=True) as uow:
        assert planning.revision_materials(uow, rev1_id)[0]["file_version_id"] == str(v1)
        assert artifacts.read_text_content(uow, v1, max_bytes=1024) == v1_bytes.decode("utf-8")
        clean_report = _validate_rev(h, uow, plan_uuid, rev1_id)
        assert not clean_report.has_errors(plugin_failures_block=False)
        assert not [f for f in clean_report.findings if f.code == "material_unavailable"]
        uow.rollback()


def _exercise_post_publish_blob_deletion_and_corruption_ench6(h: Harness) -> None:
    v1_bytes = b"PINNED-V1-AUTHENTIC-CONTENT\n"
    v2_bytes = b"NEWER-V2-DIFFERENT-CONTENT!\n"
    v1_digest = "sha256:" + hashlib.sha256(v1_bytes).hexdigest()

    file_id, v1 = upload_file(h, v1_bytes, filename="design.md", title="Design")
    plan_uuid = UUID(str(dispatch_new(h.client, CreatePlan(h.proj, "Ench6")).plan_id))
    doc = _build_spec_doc(v1, v1, v1, h.clock.now().isoformat().replace("+00:00", "Z"))
    rev1_id, rev1_digest = _publish_via_bus(h, plan_uuid, doc, base="empty", reason="pin v1")

    # Upload healthy v2 on the same file so an alternate version exists in storage.
    v2 = upload_version(h, file_id, 2, v2_bytes, filename="design.md")
    loc_v1, stored_digest = _blob_location_and_digest(h, v1, seq=40)
    loc_v2, _ = _blob_location_and_digest(h, v2, seq=41)
    assert stored_digest == v1_digest
    v1_path = h.blobs_root / str(loc_v1["storage_key"])
    v2_path = h.blobs_root / str(loc_v2["storage_key"])
    store = h.app.gateways.get(BlobStore)

    # Delete physical bytes of v1: revision never substitutes v2, surfaces FILE_VERSION_NOT_READY.
    os.chmod(v1_path, 0o600)
    os.unlink(v1_path)

    with pytest.raises(NotFound):
        store.verify(loc_v1, v1_digest)
    with pytest.raises(PreconditionFailed) as open_missing:
        h.client.open_file_version_content(v1)
    assert open_missing.value.code is ErrorCode.FILE_VERSION_NOT_READY
    assert open_missing.value.details == {"ids": [str(v1)]}

    _set_location_state(h, v1, LocationState.MISSING, seq=42)
    with h.app.uow_factory(req_meta(h, 43), readonly=True) as uow:
        assert planning.revision_materials(uow, rev1_id)[0]["file_version_id"] == str(v1)
        assert planning.get_revision_meta(uow, rev1_id).digest == rev1_digest
        with pytest.raises(PreconditionFailed) as text_missing:
            artifacts.read_text_content(uow, v1, max_bytes=1024)
        assert text_missing.value.code is ErrorCode.FILE_VERSION_NOT_READY

        report = _validate_rev(h, uow, plan_uuid, rev1_id)
        assert any(
            f.code == "material_unavailable" and f.details.get("status") == "not_ready"
            for f in report.findings
        )
        uow.rollback()

    _set_location_state(h, v1, LocationState.PRESENT, seq=44)
    _verify_corruption_and_recovery(
        h, plan_uuid, rev1_id, v1, v1_bytes, v2_bytes, v1_digest, loc_v1, v1_path, v2_path
    )


def test_post_publish_blob_deletion_and_corruption_ench6_memory(mem_env: Harness) -> None:
    _exercise_post_publish_blob_deletion_and_corruption_ench6(mem_env)


@pytest.mark.pg
def test_post_publish_blob_deletion_and_corruption_ench6_postgres(pg_env: Harness) -> None:
    _exercise_post_publish_blob_deletion_and_corruption_ench6(pg_env)
