"""Integration tests for planning material pins and file-version availability."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import cast
from uuid import UUID

import psycopg
import psycopg.errors
import pytest

from fakes.ids import SequentialIds
from integration.artifacts.test_upload_flow import (
    Harness,
    clean_test_database,
    dispatch_new,
    open_test_app,
    pg_session,
    seed_principals,
    test_database,
)
from integration.planning.publication import req_meta, upload_next_version, upload_v1
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, PreconditionFailed
from skm.kernel.ids import FileVersionId, PlanId, ProjectId, RevisionId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.domain.blob import LocationState
from skm.modules.artifacts.ports import BlobRepository, FileVersionRepository
from skm.modules.planning.application.revision_writer import (
    PinnedMaterial,
    WrittenRevision,
    resolve_publication_materials,
    write_revision,
)
from skm.modules.planning.domain.canonical import specification_digest
from skm.modules.planning.domain.material_status import (
    MaterialObservation,
    MaterialState,
    assess_material,
)
from skm.modules.planning.domain.revision import RevisionOrigin
from skm.modules.planning.domain.specification import SPECIFICATION_URN, from_document, to_document
from skm.modules.planning.domain.validation.context import FileVersionObservation, FileVersionStatus
from skm.modules.planning.generated.commands import CreatePlan
from skm.modules.planning.ports import PlanningQueries, PlanRepository, RevisionRepository
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from support.pg import TestDatabase

__all__ = ["clean_test_database", "pg_session", "test_database"]

PHASE_ID = "01900000-0000-7000-8000-000000000101"
ITEM_ID = "01900000-0000-7000-8000-000000000102"
MAT_GUIDE_ID = "01900000-0000-7000-8000-000000000201"
MAT_REF_ID = "01900000-0000-7000-8000-000000000202"
MAT_REPO_ID = "01900000-0000-7000-8000-000000000203"


def _open_harness(
    backend: str, tmp_path: Path, db: TestDatabase | None
) -> Iterator[tuple[Harness, SequentialIds]]:
    dsn = db.dsn if backend == "postgres" and db is not None else None
    app, clock, blobs_root = open_test_app(backend, tmp_path, dsn, max_uow=3)
    try:
        actor = seed_principals(app, backend)
        client = app.client(actor=actor, surface=Surface.CLI)
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        yield Harness(app, clock, actor, client, ws, proj, blobs_root, dsn), SequentialIds(start=900)
    finally:
        app.close()


@pytest.fixture
def mem_env(tmp_path: Path) -> Iterator[tuple[Harness, SequentialIds]]:
    yield from _open_harness("memory", tmp_path, None)


@pytest.fixture
def pg_env(clean_test_database: TestDatabase, tmp_path: Path) -> Iterator[tuple[Harness, SequentialIds]]:
    yield from _open_harness("postgres", tmp_path, clean_test_database)


def _spec_doc(materials: list[JsonValue], *, title: str = "Material Pin Spec") -> JsonObject:
    doc: JsonObject = {
        "schema": SPECIFICATION_URN,
        "title": title,
        "goal": "Verify material pin storage and availability",
        "phases": [
            {
                "id": PHASE_ID,
                "key": "P01",
                "title": "Phase 1",
                "goal": "Deliver material pins",
                "design_state": "detailed",
            }
        ],
        "items": [
            {
                "id": ITEM_ID,
                "key": "P01.01",
                "phase": "P01",
                "title": "Item 1",
                "summary": "Pin file versions",
                "why": "Published revisions must be immutable",
                "review": {"mode": "self", "reason": "focused test spec"},
            }
        ],
        "execution_constraints": {"strategy": "dag"},
    }
    if materials:
        doc["materials"] = materials
    return doc


def _publish_doc(
    h: Harness,
    ids: SequentialIds,
    plan_id: PlanId,
    raw_doc: JsonObject,
    *,
    seq: int,
    reason: str = "publish revision",
) -> WrittenRevision:
    with h.app.uow_factory(req_meta(h, seq)) as uow:
        plan = uow.repo(PlanRepository).lock(plan_id)
        resolved_doc, pinned_items = resolve_publication_materials(uow, plan.workspace_id, raw_doc)
        spec, _ = from_document(resolved_doc)
        canonical_doc = to_document(spec)
        digest = specification_digest(canonical_doc)
        written = write_revision(
            uow,
            None,
            plan,
            spec,
            canonical_doc,
            digest,
            origin=RevisionOrigin.DRAFT,
            reason=reason,
            actor=h.owner.principal_id,
            ids=ids,
            now=h.clock.now(),
            pinned_materials=pinned_items,
        )
        uow.commit()
        return written


def _mark_blob_missing(h: Harness, version_id: FileVersionId, *, seq: int) -> None:
    with h.app.uow_factory(req_meta(h, seq)) as uow:
        version = uow.repo(FileVersionRepository).get(version_id)
        blobs = uow.repo(BlobRepository)
        loc = blobs.locations(version.blob_id)[0]
        blobs.mark_location(version.blob_id, loc.backend_id, LocationState.MISSING, h.clock.now())
        uow.commit()


def _exercise_pin_persistence_and_queries(h: Harness, ids: SequentialIds) -> None:
    guide_file, guide_v1 = upload_v1(h, b"guide v1\n", filename="guide.md", title="Guide")
    h.clock.advance(timedelta(seconds=5))
    guide_v2 = upload_next_version(h, guide_file, 2, b"guide v2\n", filename="guide.md")
    _, ref_v1 = upload_v1(h, b"reference v1\n", filename="ref.txt", title="Ref")

    plan_res = dispatch_new(h.client, CreatePlan(project_id=h.proj, title="Pin Plan"))
    plan_id = PlanId(UUID(str(plan_res.plan_id)))

    doc = _spec_doc(
        [
            {
                "id": MAT_GUIDE_ID,
                "key": "api-guide",
                "title": "API Guide",
                "kind": "file_version",
                "file_version_id": str(guide_v1),
                "role": "input",
                "required_for": ["execution"],
                "freshness": {"policy": "latest_at_publish"},
                "selector": {"lines": "1-20"},
                "applies_to": ["P01"],
            },
            {
                "id": MAT_REF_ID,
                "key": "ref-notes",
                "title": "Reference Notes",
                "kind": "file_version",
                "file_version_id": str(ref_v1),
                "role": "reference",
                "freshness": {"policy": "pinned"},
                "applies_to": ["P01.01"],
            },
            {
                "id": MAT_REPO_ID,
                "key": "readme",
                "title": "Repo Readme",
                "kind": "repository_path",
                "mount": "repo",
                "path": "README.md",
                "role": "reference",
                "global": True,
            },
        ]
    )

    written = _publish_doc(h, ids, plan_id, doc, seq=1)
    assert written.revision_no == 1
    assert written.pinned_materials == (
        PinnedMaterial("api-guide", guide_v2, "latest_at_publish"),
        PinnedMaterial("ref-notes", ref_v1, "pinned"),
    )

    if h.dsn is not None:
        with psycopg.connect(h.dsn, autocommit=True) as conn:
            rows = conn.execute(
                "SELECT workspace_id, plan_id, revision_id, material_id, file_version_id, role, selector "
                "FROM skm_planning.revision_file_bindings WHERE revision_id = %s ORDER BY material_id",
                (written.revision_id,),
            ).fetchall()
        assert rows == [
            (
                UUID(str(h.ws)),
                UUID(str(plan_id)),
                UUID(str(written.revision_id)),
                UUID(MAT_GUIDE_ID),
                UUID(str(guide_v2)),
                "input",
                {"lines": "1-20"},
            ),
            (
                UUID(str(h.ws)),
                UUID(str(plan_id)),
                UUID(str(written.revision_id)),
                UUID(MAT_REF_ID),
                UUID(str(ref_v1)),
                "reference",
                None,
            ),
        ]

    with h.app.uow_factory(req_meta(h, 2), readonly=True) as uow:
        revs = uow.repo(RevisionRepository)
        queries = uow.repo(PlanningQueries)
        payload_doc = revs.get_document(written.revision_id)
        typed_doc = revs.load_typed_document(written.revision_id)
        assert typed_doc == payload_doc

        pins = queries.revision_pins(written.revision_id)
        assert [(str(p.material_id), p.file_version_id, p.role, p.selector) for p in pins] == [
            (MAT_GUIDE_ID, UUID(str(guide_v2)), "input", {"lines": "1-20"}),
            (MAT_REF_ID, UUID(str(ref_v1)), "reference", None),
        ]
        cast("dict[str, JsonValue]", pins[0].selector)["lines"] = "mutated"
        assert queries.revision_pins(written.revision_id)[0].selector == {"lines": "1-20"}

        materials = queries.revision_materials(written.revision_id)
        assert [m["key"] for m in materials] == ["api-guide", "ref-notes", "readme"]
        assert materials[0]["file_version_id"] == str(guide_v2)
        assert materials[0]["applies_to_entity_ids"] == [PHASE_ID]
        assert materials[1]["file_version_id"] == str(ref_v1)
        assert materials[1]["applies_to_entity_ids"] == [ITEM_ID]
        assert materials[2]["file_version_id"] is None
        assert materials[2]["is_global"] is True

        obs = MaterialObservation(
            file_version=FileVersionObservation(FileVersionStatus.READY, h.clock.now()),
            checkout_has_path=None,
        )
        assessment = assess_material(materials[0], obs, now=h.clock.now())
        assert assessment.state is MaterialState.AVAILABLE

        assert queries.revisions_pinning_file_version(UUID(str(guide_v2))) == (written.revision_id,)
        assert queries.revisions_pinning_file_version(UUID(str(guide_v1))) == ()
        with pytest.raises(NotFound) as missing_rev:
            queries.revision_materials(RevisionId(UUID("01900000-0000-7000-8000-000000009999")))
        assert missing_rev.value.details == {
            "kind": "revision",
            "ref": "01900000-0000-7000-8000-000000009999",
        }
        uow.rollback()


def test_pin_persisted_on_publication_memory(mem_env: tuple[Harness, SequentialIds]) -> None:
    _exercise_pin_persistence_and_queries(*mem_env)


@pytest.mark.pg
def test_pin_persisted_on_publication_postgres(pg_env: tuple[Harness, SequentialIds]) -> None:
    _exercise_pin_persistence_and_queries(*pg_env)


def _file_mat(
    key: str,
    version_id: str,
    *,
    mat_id: str = MAT_GUIDE_ID,
    role: str = "input",
    policy: str = "pinned",
) -> JsonObject:
    return {
        "id": mat_id,
        "key": key,
        "title": key.title(),
        "kind": "file_version",
        "file_version_id": version_id,
        "role": role,
        "freshness": {"policy": policy},
    }


def _exercise_new_version_and_post_publish_trash(h: Harness, ids: SequentialIds) -> None:
    file_id, v1 = upload_v1(h, b"version-one-bytes\n", filename="design.md", title="Design")
    plan_id = PlanId(
        UUID(str(dispatch_new(h.client, CreatePlan(project_id=h.proj, title="History")).plan_id))
    )

    doc_v1 = _spec_doc([_file_mat("design", str(v1), policy="latest_at_publish")], title="Rev 1")
    rev1 = _publish_doc(h, ids, plan_id, doc_v1, seq=10, reason="pin v1")
    assert rev1.pins[0].file_version_id == UUID(str(v1))

    h.clock.advance(timedelta(seconds=10))
    v2 = upload_next_version(h, file_id, 2, b"version-two-bytes\n", filename="design.md")

    with h.app.uow_factory(req_meta(h, 11), readonly=True) as uow:
        assert uow.repo(PlanningQueries).revision_pins(rev1.revision_id)[0].file_version_id == UUID(str(v1))
        mats_r1 = uow.repo(PlanningQueries).revision_materials(rev1.revision_id)
        assert mats_r1[0]["file_version_id"] == str(v1)
        uow.rollback()

    doc_v2 = _spec_doc([_file_mat("design", str(v1), policy="latest_at_publish")], title="Rev 2")
    rev2 = _publish_doc(h, ids, plan_id, doc_v2, seq=12, reason="pin v2")
    assert rev2.pins[0].file_version_id == UUID(str(v2))

    # Trash file AFTER revisions 1 and 2 are published: existing pins and bytes remain accessible.
    dispatch_new(h.client, artifacts.TrashFile(file_id=file_id, expected_row_version=3, reason="obsolete"))

    with h.client.open_file_version_content(v1) as stream:
        assert stream.read() == b"version-one-bytes\n"
    with h.app.uow_factory(req_meta(h, 13), readonly=True) as uow:
        queries = uow.repo(PlanningQueries)
        assert queries.revision_pins(rev1.revision_id)[0].file_version_id == UUID(str(v1))
        assert queries.revision_pins(rev2.revision_id)[0].file_version_id == UUID(str(v2))
        assert queries.revisions_pinning_file_version(UUID(str(v1))) == (rev1.revision_id,)
        assert queries.revisions_pinning_file_version(UUID(str(v2))) == (rev2.revision_id,)
        assert artifacts.get_file_version(uow, v1).version_no == 1
        assert artifacts.read_text_content(uow, v1, max_bytes=1024) == "version-one-bytes\n"
        uow.rollback()

    # Publishing a NEW revision referencing the now-trashed file fails with FILE_VERSION_NOT_READY.
    doc_v3 = _spec_doc([_file_mat("design", str(v1), policy="latest_at_publish")], title="Rev 3")
    with pytest.raises(PreconditionFailed) as exc_info:
        _publish_doc(h, ids, plan_id, doc_v3, seq=14)
    assert exc_info.value.code is ErrorCode.FILE_VERSION_NOT_READY
    assert exc_info.value.details == {"file_ids": [str(file_id)]}


def test_new_version_and_post_publish_trash_memory(mem_env: tuple[Harness, SequentialIds]) -> None:
    _exercise_new_version_and_post_publish_trash(*mem_env)


@pytest.mark.pg
def test_new_version_and_post_publish_trash_postgres(pg_env: tuple[Harness, SequentialIds]) -> None:
    _exercise_new_version_and_post_publish_trash(*pg_env)


def _exercise_pre_publish_rejections(h: Harness, ids: SequentialIds) -> None:
    plan_id = PlanId(UUID(str(dispatch_new(h.client, CreatePlan(project_id=h.proj, title="Guards")).plan_id)))

    # 1. Staged-only blob UUID (not consumed into a file_version) and unknown UUID -> NOT_FOUND.
    staged_only = h.client.upload_blob(h.ws, [b"staged-only\n"], size=12, media_type="text/plain")
    unknown_vid = "01900000-0000-7000-8000-00000000dead"
    for bad_vid in (str(staged_only.staged_blob_id), unknown_vid):
        with pytest.raises(NotFound) as nf_err:
            _publish_doc(h, ids, plan_id, _spec_doc([_file_mat("missing", bad_vid)]), seq=20)
        assert nf_err.value.code is ErrorCode.NOT_FOUND
        assert nf_err.value.details == {"kind": "file_version", "ids": [bad_vid]}

    # 2. Cross-workspace file_version -> NOT_FOUND (both pinned and latest_at_publish).
    ws2 = WorkspaceId(dispatch_new(h.client, CreateWorkspace(slug="other", title="Other")).workspace_id)
    proj2 = ProjectId(
        dispatch_new(h.client, CreateProject(workspace_id=ws2, slug="other-p", title="Other P")).project_id
    )
    _, foreign_v1 = upload_v1(h, b"foreign\n", ws=ws2, proj=proj2)
    for policy in ("pinned", "latest_at_publish"):
        foreign_doc = _spec_doc([_file_mat("foreign", str(foreign_v1), policy=policy)])
        with pytest.raises(NotFound) as foreign_err:
            _publish_doc(h, ids, plan_id, foreign_doc, seq=21)
        assert foreign_err.value.details == {"kind": "file_version", "ids": [str(foreign_v1)]}

    # 3. Trashed file pre-publish with pinned policy -> FILE_VERSION_NOT_READY (details.ids).
    trashed_file, trashed_v1 = upload_v1(h, b"trash-me\n", filename="trash.txt")
    dispatch_new(h.client, artifacts.TrashFile(file_id=trashed_file, expected_row_version=2, reason="drop"))
    with pytest.raises(PreconditionFailed) as trashed_err:
        _publish_doc(h, ids, plan_id, _spec_doc([_file_mat("trashed", str(trashed_v1))]), seq=22)
    assert trashed_err.value.code is ErrorCode.FILE_VERSION_NOT_READY
    assert trashed_err.value.details == {"ids": [str(trashed_v1)]}

    # 4. Blob location marked missing -> FILE_VERSION_NOT_READY.
    _, missing_blob_v1 = upload_v1(h, b"corrupt-bytes\n", filename="corrupt.txt")
    _mark_blob_missing(h, missing_blob_v1, seq=23)
    with pytest.raises(PreconditionFailed) as corrupt_err:
        _publish_doc(h, ids, plan_id, _spec_doc([_file_mat("corrupt", str(missing_blob_v1))]), seq=24)
    assert corrupt_err.value.code is ErrorCode.FILE_VERSION_NOT_READY
    assert corrupt_err.value.details == {"ids": [str(missing_blob_v1)]}

    # Plan state remained untouched across all aborted publications.
    with h.app.uow_factory(req_meta(h, 25), readonly=True) as uow:
        stored_plan = uow.repo(PlanRepository).get(plan_id)
        assert stored_plan.current_revision_id is None
        assert stored_plan.next_revision_no == 1
        assert stored_plan.row_version == 1
        uow.rollback()


def test_pre_publish_rejections_memory(mem_env: tuple[Harness, SequentialIds]) -> None:
    _exercise_pre_publish_rejections(*mem_env)


@pytest.mark.pg
def test_pre_publish_rejections_postgres(pg_env: tuple[Harness, SequentialIds]) -> None:
    _exercise_pre_publish_rejections(*pg_env)


@pytest.mark.pg
def test_postgres_ddl_invariants_on_revision_file_bindings(
    pg_env: tuple[Harness, SequentialIds],
    clean_test_database: TestDatabase,
) -> None:
    h, ids = pg_env
    pinned_file, v1 = upload_v1(h, b"pinned-bytes\n", filename="pinned.txt")
    ws2 = WorkspaceId(dispatch_new(h.client, CreateWorkspace(slug="ws-two", title="WS Two")).workspace_id)
    proj2 = ProjectId(
        dispatch_new(h.client, CreateProject(workspace_id=ws2, slug="p-two", title="P Two")).project_id
    )
    _, foreign_v1 = upload_v1(h, b"other-ws\n", ws=ws2, proj=proj2)

    plan_id = PlanId(
        UUID(str(dispatch_new(h.client, CreatePlan(project_id=h.proj, title="DDL Plan")).plan_id))
    )
    written = _publish_doc(h, ids, plan_id, _spec_doc([_file_mat("pinned-mat", str(v1))]), seq=30)

    # 1. Immutability trigger on revision_file_bindings blocks UPDATE and DELETE.
    with psycopg.connect(clean_test_database.dsn, autocommit=False) as conn:
        with pytest.raises(psycopg.errors.RestrictViolation):
            conn.execute(
                "UPDATE skm_planning.revision_file_bindings SET role = 'reference' WHERE revision_id = %s",
                (written.revision_id,),
            )
        conn.rollback()

        with pytest.raises(psycopg.errors.RestrictViolation):
            conn.execute(
                "DELETE FROM skm_planning.revision_file_bindings WHERE revision_id = %s",
                (written.revision_id,),
            )
        conn.rollback()

        # 2. Deleting a pinned file_version is blocked by tg_file_versions__immutable.
        with pytest.raises(psycopg.errors.RestrictViolation):
            conn.execute("DELETE FROM skm_artifacts.file_versions WHERE id = %s", (UUID(str(v1)),))
        conn.rollback()

    # 3. With tg_file_versions__immutable disabled in a rolled-back owner transaction,
    #    fk_revision_file_bindings__file_version ON DELETE RESTRICT still refuses deleting v1.
    #    A newer version first takes over files.current_version_id, so the pin binding is the only
    #    reference left on v1 and the refusal must come from that constraint.
    upload_next_version(h, pinned_file, 2, b"pinned-bytes v2\n", filename="pinned.txt")
    with psycopg.connect(clean_test_database.dsn, autocommit=False) as mconn:
        mconn.execute("ALTER TABLE skm_artifacts.file_versions DISABLE TRIGGER tg_file_versions__immutable")
        # ON DELETE RESTRICT reports 23001 starting with PostgreSQL 18 and 23503 on earlier versions.
        with pytest.raises((psycopg.errors.ForeignKeyViolation, psycopg.errors.RestrictViolation)) as refused:
            mconn.execute("DELETE FROM skm_artifacts.file_versions WHERE id = %s", (UUID(str(v1)),))
        assert refused.value.diag.constraint_name == "fk_revision_file_bindings__file_version"
        mconn.rollback()

    # 4. Deferred tg_material_specs__has_pin, role CHECK, and composite workspace FK on a second revision.
    rev2_id = UUID("01900000-0000-7000-8000-000000000901")
    mat2_id = UUID("01900000-0000-7000-8000-000000000902")
    with psycopg.connect(clean_test_database.dsn, autocommit=False) as conn:

        def _seed_rev2_material() -> None:
            conn.execute(
                "INSERT INTO skm_planning.plan_revisions ("
                "workspace_id, plan_id, id, revision_no, parent_revision_id, schema_version, content_digest, "
                "canonicalization_version, compiler_version, published_by, published_at, "
                "change_reason, origin"
                ") VALUES (%s, %s, %s, 2, %s, 1, %s, 1, 1, %s, %s, 'ddl check', 'draft')",
                (
                    UUID(str(h.ws)),
                    UUID(str(plan_id)),
                    rev2_id,
                    UUID(str(written.revision_id)),
                    "sha256:" + "b" * 64,
                    UUID(str(h.owner.principal_id)),
                    h.clock.now(),
                ),
            )
            conn.execute(
                "INSERT INTO skm_planning.plan_entity_identities "
                "(workspace_id, plan_id, entity_id, entity_kind, first_revision_id, created_at) "
                "VALUES (%s, %s, %s, 'material', %s, %s)",
                (UUID(str(h.ws)), UUID(str(plan_id)), mat2_id, rev2_id, h.clock.now()),
            )
            conn.execute(
                "INSERT INTO skm_planning.revision_members "
                "(workspace_id, plan_id, revision_id, entity_id, entity_kind, display_key, position) "
                "VALUES (%s, %s, %s, %s, 'material', 'material/unpinned', 0)",
                (UUID(str(h.ws)), UUID(str(plan_id)), rev2_id, mat2_id),
            )
            conn.execute(
                "INSERT INTO skm_planning.material_specs ("
                "workspace_id, plan_id, revision_id, material_id, entity_kind, position, title, kind, role, "
                "required_for, freshness_policy, is_global"
                ") VALUES (%s, %s, %s, %s, 'material', 0, 'Unpinned', 'file_version', "
                "'input', '{}', 'pinned', false)",
                (UUID(str(h.ws)), UUID(str(plan_id)), rev2_id, mat2_id),
            )

        # 4a. Invalid role rejected by ck_revision_file_bindings__role_valid.
        _seed_rev2_material()
        with pytest.raises(psycopg.errors.CheckViolation):
            conn.execute(
                "INSERT INTO skm_planning.revision_file_bindings "
                "(workspace_id, plan_id, revision_id, material_id, file_version_id, role) "
                "VALUES (%s, %s, %s, %s, %s, 'deliverable')",
                (UUID(str(h.ws)), UUID(str(plan_id)), rev2_id, mat2_id, UUID(str(v1))),
            )
        conn.rollback()

        # 4b. Foreign-workspace file_version_id rejected by fk_revision_file_bindings__file_version.
        _seed_rev2_material()
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.execute(
                "INSERT INTO skm_planning.revision_file_bindings "
                "(workspace_id, plan_id, revision_id, material_id, file_version_id, role) "
                "VALUES (%s, %s, %s, %s, %s, 'input')",
                (UUID(str(h.ws)), UUID(str(plan_id)), rev2_id, mat2_id, UUID(str(foreign_v1))),
            )
        conn.rollback()

        # 4c. Missing revision_file_bindings row for kind='file_version' fails deferred trigger at COMMIT.
        _seed_rev2_material()
        with pytest.raises(psycopg.errors.ForeignKeyViolation):
            conn.commit()
        conn.rollback()
