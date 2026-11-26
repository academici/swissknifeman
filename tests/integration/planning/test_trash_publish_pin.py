"""Integration tests for logical file trash, restore, and concurrent publish serialization."""

from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.clock import FrozenClock
from integration.artifacts.test_upload_flow import (
    NOW,
    Harness,
    add_file_dto,
    clean_test_database,
    dispatch_new,
    pg_session,
    seed_principals,
    test_database,
)
from skm.adapters.blobs.local.store import LocalBlobStore
from skm.bootstrap.composition import CompositionOverrides, StoredScopeChain, build_app
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import PreconditionFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import FileVersionId, PlanId, ProjectId, RevisionId, WorkspaceId
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access.public import RbacAuthorizer
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.generated import commands as art_cmds
from skm.modules.artifacts.generated.queries import GetFile
from skm.modules.artifacts.ports import BlobStore
from skm.modules.planning import public as planning
from skm.modules.planning.domain.draft import DraftId, DraftState
from skm.modules.planning.domain.specification import SPECIFICATION_URN
from skm.modules.planning.generated.commands import (
    CreatePlan,
    OpenDraft,
    PublishRevision,
    RestoreRevision,
    SaveDraft,
)
from skm.modules.planning.generated.queries import PreviewPublication
from skm.modules.planning.ports import DraftRepository, PlanningQueries, PlanRepository, RevisionRepository
from skm.modules.workspace.public import AttachRepository, CreateProject, CreateWorkspace, RegisterRepository
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.fs.storage_budget import StorageBudget, StorageOwnerIdentity
from support.pg import TestDatabase
from support.seed import SEED

__all__ = [
    "base_spec_doc",
    "clean_test_database",
    "open_env",
    "pg_session",
    "req_meta",
    "test_database",
    "upload_file",
    "upload_version",
]


def _uid(seed: int, slot: int) -> UUID:
    return UUID(f"0192f5c4-{seed:04x}-7000-8000-0000000000{slot:02x}")


def open_env(backend: str, tmp_path: Path, db: TestDatabase | None) -> Iterator[Harness]:
    dsn = db.dsn if backend == "postgres" and db is not None else None
    clock = FrozenClock(NOW)
    env = {"SKM_DATABASE_URL": dsn} if dsn else {}
    bs_env = {"SKM_DATABASE_URL": dsn or "postgresql://127.0.0.1:5432/mem"}
    bs = replace(
        load_bootstrap(None, bs_env, tmp_path),
        instance_id=SEED.instance_id,
        database_application_name="skm-p0604b-int",
        database_pool_min_size=0,
        database_pool_max_size=4,
        database_pool_timeout_seconds=2,
    )
    gateways: GatewayTable | None = None
    if backend != "postgres":
        budget = StorageBudget(
            tmp_path / "ledger",
            free_bytes=lambda _: 1 << 40,
            identity=lambda: StorageOwnerIdentity("boot", os.getpid(), "p0604b"),
            owner_alive=lambda _: True,
        )
        store = LocalBlobStore(
            bs.blobs_root, max_bytes=16 * 1024 * 1024, min_free_bytes=0, storage_budget=budget
        )
        gateways = GatewayTable({BlobStore: store}, "control_plane_gateway")
    ov = CompositionOverrides(
        authorizer=RbacAuthorizer(clock),
        scopes=StoredScopeChain(),
        clock=clock,
        instance_id=SEED.instance_id,
        gateways=gateways,
    )
    be = "postgres" if backend == "postgres" else None
    app = build_app(bs, surface=Surface.CLI, environ=env, invocation={}, backend=be, overrides=ov)
    try:
        actor = seed_principals(app, backend)
        client = app.client(actor=actor, surface=Surface.CLI)
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        repo = dispatch_new(
            client,
            RegisterRepository(ws, "api-repo", remote_url="https://example.test/api.git", external_id=None),
        )
        dispatch_new(client, AttachRepository(proj, repo.repository_id, mount_name="api", role="primary"))
        yield Harness(app, clock, actor, client, ws, proj, bs.blobs_root, dsn)
    finally:
        app.close()


@pytest.fixture
def mem_env(tmp_path: Path) -> Iterator[Harness]:
    yield from open_env("memory", tmp_path, None)


@pytest.fixture
def pg_env(clean_test_database: TestDatabase, tmp_path: Path) -> Iterator[Harness]:
    yield from open_env("postgres", tmp_path, clean_test_database)


def req_meta(h: Harness, seq: int) -> RequestMeta:
    return RequestMeta(f"req_{seq:026d}", Surface.CLI, None, h.clock.now())


def upload_file(h: Harness, data: bytes, *, filename: str, title: str) -> tuple[UUID, FileVersionId]:
    staged = h.client.upload_blob(h.ws, [data], size=len(data), media_type="text/plain")
    dto = replace(add_file_dto(h.ws, h.proj, staged), title=title, original_filename=filename)
    res = dispatch_new(h.client, dto)
    return UUID(str(res.file_id)), FileVersionId(UUID(str(res.file_version_id)))


def upload_version(
    h: Harness, file_id: UUID, expected_row_version: int, data: bytes, *, filename: str
) -> FileVersionId:
    staged = h.client.upload_blob(h.ws, [data], size=len(data), media_type="text/plain")
    blob_ref = art_cmds.AddFileVersionDefsStagedBlobRef(
        staged.staged_blob_id, staged.workspace_id, staged.digest, staged.size, staged.media_type
    )
    src = art_cmds.AddFileVersionDefsVersionSource(kind="upload")
    cmd = artifacts.AddFileVersion(file_id, expected_row_version, blob_ref, filename, "text/plain", src)
    return FileVersionId(UUID(str(dispatch_new(h.client, cmd).file_version_id)))


def base_spec_doc(
    materials: list[JsonValue],
    *,
    goal: str = "Pin file versions cleanly.",
    seed: int = 0,
    phase_id: UUID | None = None,
    item_id: UUID | None = None,
) -> JsonObject:
    doc: JsonObject = {
        "schema": SPECIFICATION_URN,
        "title": "Material Pin Plan",
        "goal": goal,
        "requirements": [
            {
                "id": str(_uid(seed, 3)),
                "key": "R1",
                "statement": "Preserve material pins.",
                "priority": "must",
                "source": {"kind": "owner"},
                "owners": ["P1.1"],
            }
        ],
        "phases": [
            {
                "id": str(phase_id or _uid(seed, 1)),
                "key": "P1",
                "title": "Phase 1",
                "goal": "Deliver material pins",
                "design_state": "detailed",
                "depends_on": [],
            }
        ],
        "items": [
            {
                "id": str(item_id or _uid(seed, 2)),
                "key": "P1.1",
                "phase": "P1",
                "title": "Item 1",
                "summary": "Verify material pin semantics",
                "why": "Published revisions keep reading pinned bytes",
                "work_kind": "code",
                "scope": {"include": ["src/pin.py"], "exclude": []},
                "implements": ["R1"],
                "decisions": ["D1"],
                "deliverables": ["Pin verification"],
                "guidance_md": "Verify pins.",
                "review": {"mode": "self", "reason": "Focused test spec."},
            }
        ],
        "units": [
            {
                "id": str(_uid(seed, 4)),
                "key": "P1.1/U1",
                "title": "Verify pin behavior",
                "goal": "Implement pin check.",
                "work_kind": "code",
                "write_scope": [{"mount": "api", "pattern": "src/pin.py"}],
                "checks": ["V1"],
                "implements": ["R1"],
            }
        ],
        "criteria": [
            {
                "id": str(_uid(seed, 5)),
                "key": "AC1",
                "owner": "P1.1",
                "statement": "Tests pass.",
                "verification_mode": "check",
                "checks": ["V1"],
                "requirements": ["R1"],
            }
        ],
        "checks": [
            {
                "id": str(_uid(seed, 6)),
                "key": "V1",
                "owner": "P1.1",
                "title": "Pin tests",
                "category": "acceptance",
                "kind": "command",
                "definition": {"argv": ["pytest", "-q"], "cwd": {"mount": "api", "path": "."}},
            }
        ],
        "decisions": [
            {
                "id": str(_uid(seed, 7)),
                "key": "D1",
                "title": "Immutable pins",
                "state": "accepted",
                "question": "Re-evaluate pins after publish?",
                "decision": "Never re-evaluate published pins.",
                "rationale": "Snapshot integrity.",
                "applies_to": ["P1.1"],
            }
        ],
    }
    if materials:
        doc["materials"] = materials
    return doc


def _file_mat(uid: UUID, key: str, vid: FileVersionId, *, policy: str) -> JsonObject:
    return {
        "id": str(uid),
        "key": key,
        "title": key.title(),
        "kind": "file_version",
        "file_version_id": str(vid),
        "role": "input",
        "required_for": ["execution"],
        "freshness": {"policy": policy},
        "applies_to": ["P1.1"],
    }


def _prepare_open_draft(h: Harness, plan_uuid: UUID, doc: JsonObject, *, base: str) -> tuple[UUID, int, str]:
    opened = dispatch_new(h.client, OpenDraft(plan_id=plan_uuid, base=cast("Any", base)))
    saved = dispatch_new(
        h.client, SaveDraft(plan_uuid, opened.draft_id, opened.edit_version, cast("Any", doc))
    )
    preview: Any = h.client.ask(PreviewPublication(plan_uuid, opened.draft_id, saved.edit_version))
    assert preview.publishable
    return UUID(str(opened.draft_id)), int(saved.edit_version), str(preview.content_digest)


def _exercise_logical_trash_and_restore_preserves_pins(h: Harness) -> None:
    mat_pin_id, mat_lat_id = _uid(0, 0x21), _uid(0, 0x22)
    pinned_file, pinned_v1 = upload_file(h, b"pinned-v1-bytes\n", filename="pinned.md", title="Pinned")
    latest_file, latest_v1 = upload_file(h, b"latest-v1-bytes\n", filename="latest.md", title="Latest")

    plan_uuid = UUID(str(dispatch_new(h.client, CreatePlan(project_id=h.proj, title="Trash Plan")).plan_id))
    doc_r1 = base_spec_doc(
        [
            _file_mat(mat_pin_id, "pinned-spec", pinned_v1, policy="pinned"),
            _file_mat(mat_lat_id, "latest-spec", latest_v1, policy="latest_at_publish"),
        ]
    )
    draft1_id, edit_v1, digest_r1 = _prepare_open_draft(h, plan_uuid, doc_r1, base="empty")
    pub1 = dispatch_new(h.client, PublishRevision(plan_uuid, draft1_id, edit_v1, digest_r1, "publish rev1"))
    rev1_id = RevisionId(pub1.revision_id)

    h.clock.advance(timedelta(seconds=10))
    latest_v2 = upload_version(h, latest_file, 2, b"latest-v2-bytes\n", filename="latest.md")

    # Logically trash both files after rev1 publication.
    dispatch_new(h.client, artifacts.TrashFile(file_id=pinned_file, expected_row_version=2, reason="retire"))
    dispatch_new(h.client, artifacts.TrashFile(file_id=latest_file, expected_row_version=3, reason="retire"))

    # Published rev1 continues reading exact v1 pins and physical bytes without error.
    with h.client.open_file_version_content(pinned_v1) as s_pin:
        assert s_pin.read() == b"pinned-v1-bytes\n"
    with h.client.open_file_version_content(latest_v1) as s_lat:
        assert s_lat.read() == b"latest-v1-bytes\n"

    with h.app.uow_factory(req_meta(h, 10), readonly=True) as uow:
        mats = planning.revision_materials(uow, rev1_id)
        assert [m["file_version_id"] for m in mats] == [str(pinned_v1), str(latest_v1)]
        revs = uow.repo(RevisionRepository)
        assert revs.load_typed_document(rev1_id) == revs.get_document(rev1_id)
        assert artifacts.read_text_content(uow, pinned_v1, max_bytes=1024) == "pinned-v1-bytes\n"
        assert artifacts.read_text_content(uow, latest_v1, max_bytes=1024) == "latest-v1-bytes\n"
        uow.rollback()

    # New draft with latest_at_publish on trashed file fails preview & publish with FILE_VERSION_NOT_READY.
    d_lat = dispatch_new(h.client, OpenDraft(plan_id=plan_uuid, base="current"))
    s_lat_draft = dispatch_new(
        h.client,
        SaveDraft(
            plan_uuid,
            d_lat.draft_id,
            d_lat.edit_version,
            cast(
                "Any",
                base_spec_doc(
                    [_file_mat(mat_lat_id, "latest-spec", latest_v1, policy="latest_at_publish")],
                    goal="Attempt trashed latest_at_publish.",
                ),
            ),
        ),
    )
    with pytest.raises(PreconditionFailed) as lat_prev_err:
        h.client.ask(PreviewPublication(plan_uuid, d_lat.draft_id, s_lat_draft.edit_version))
    assert lat_prev_err.value.code is ErrorCode.FILE_VERSION_NOT_READY
    assert lat_prev_err.value.details == {"file_ids": [str(latest_file)]}

    # New draft with pinned trashed file reports publishable=False and rejects PublishRevision.
    d_pin = dispatch_new(h.client, OpenDraft(plan_id=plan_uuid, base="current"))
    s_pin_draft = dispatch_new(
        h.client,
        SaveDraft(
            plan_uuid,
            d_pin.draft_id,
            d_pin.edit_version,
            cast(
                "Any",
                base_spec_doc(
                    [_file_mat(mat_pin_id, "pinned-spec", pinned_v1, policy="pinned")],
                    goal="Attempt trashed pinned.",
                ),
            ),
        ),
    )
    pin_preview: Any = h.client.ask(PreviewPublication(plan_uuid, d_pin.draft_id, s_pin_draft.edit_version))
    assert not pin_preview.publishable
    with pytest.raises(PreconditionFailed) as pin_pub_err:
        dispatch_new(
            h.client,
            PublishRevision(
                plan_uuid, d_pin.draft_id, s_pin_draft.edit_version, pin_preview.content_digest, "must fail"
            ),
        )
    assert pin_pub_err.value.code is ErrorCode.PLAN_NOT_READY

    # Publish material-free rev2; RestoreRevision(1) fails while trashed, succeeds after RestoreFile.
    d2_id, d2_ev, d2_dig = _prepare_open_draft(
        h, plan_uuid, base_spec_doc([], goal="Temporarily drop materials."), base="current"
    )
    pub2 = dispatch_new(h.client, PublishRevision(plan_uuid, d2_id, d2_ev, d2_dig, "publish rev2"))
    with pytest.raises(PreconditionFailed) as restore_trashed_err:
        dispatch_new(h.client, RestoreRevision(plan_uuid, 1, "cannot restore trashed", pub2.revision_id))
    assert restore_trashed_err.value.code is ErrorCode.PLAN_NOT_READY

    dispatch_new(h.client, artifacts.RestoreFile(file_id=pinned_file, expected_row_version=3))
    dispatch_new(h.client, artifacts.RestoreFile(file_id=latest_file, expected_row_version=4))

    restored = dispatch_new(h.client, RestoreRevision(plan_uuid, 1, "restore rev1", pub2.revision_id))
    rev3_id = RevisionId(restored.revision_id)

    d4_id, d4_ev, d4_dig = _prepare_open_draft(
        h,
        plan_uuid,
        base_spec_doc(
            [_file_mat(mat_lat_id, "latest-spec", latest_v1, policy="latest_at_publish")],
            goal="Publish rev4 resolving latest_v2.",
        ),
        base="current",
    )
    pub4 = dispatch_new(h.client, PublishRevision(plan_uuid, d4_id, d4_ev, d4_dig, "publish rev4"))
    rev4_id = RevisionId(pub4.revision_id)

    with h.app.uow_factory(req_meta(h, 20), readonly=True) as uow:
        assert [m["file_version_id"] for m in planning.revision_materials(uow, rev3_id)] == [
            str(pinned_v1),
            str(latest_v1),
        ]
        assert [m["file_version_id"] for m in planning.revision_materials(uow, rev4_id)] == [str(latest_v2)]
        uow.rollback()


def test_logical_trash_and_restore_preserves_pins_memory(mem_env: Harness) -> None:
    _exercise_logical_trash_and_restore_preserves_pins(mem_env)


@pytest.mark.pg
def test_logical_trash_and_restore_preserves_pins_postgres(pg_env: Harness) -> None:
    _exercise_logical_trash_and_restore_preserves_pins(pg_env)


def _run_concurrent_trash_publish_trial(h: Harness, *, policy: str, trial: int) -> str:
    seed = 10 + trial
    mat_uid = _uid(seed, 0x21)
    payload = f"race-payload-{policy}-{trial}\n".encode()
    file_id, v1 = upload_file(
        h, payload, filename=f"race-{policy}-{trial}.md", title=f"Race {policy} {trial}"
    )
    plan_uuid = UUID(str(dispatch_new(h.client, CreatePlan(h.proj, f"Race Plan {policy} {trial}")).plan_id))
    doc = base_spec_doc([_file_mat(mat_uid, "race-mat", v1, policy=policy)], seed=seed)
    draft_id, edit_ver, content_digest = _prepare_open_draft(h, plan_uuid, doc, base="empty")

    client_trash = h.app.client(actor=h.owner, surface=Surface.CLI)
    client_pub = h.app.client(actor=h.owner, surface=Surface.CLI)
    barrier = threading.Barrier(2)

    def do_trash() -> Any:
        barrier.wait(timeout=5)
        return dispatch_new(client_trash, artifacts.TrashFile(file_id, 2, "race"))

    def do_publish() -> Any:
        barrier.wait(timeout=5)
        return dispatch_new(
            client_pub, PublishRevision(plan_uuid, draft_id, edit_ver, content_digest, "race publish")
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_trash = pool.submit(do_trash)
        fut_pub = pool.submit(do_publish)
        fut_trash.result(timeout=10)
        pub_outcome: Any = None
        pub_err: PreconditionFailed | None = None
        try:
            pub_outcome = fut_pub.result(timeout=10)
        except PreconditionFailed as exc:
            pub_err = exc

    file_view: Any = h.client.ask(GetFile(file_id=file_id))
    assert str(file_view.state) == "trashed"

    seq_base = 100 + trial * 10
    if pub_err is not None:
        # Trash ran before publish: publish aborted cleanly, no revision/pin written, draft stays open.
        assert pub_err.code in (ErrorCode.FILE_VERSION_NOT_READY, ErrorCode.PLAN_NOT_READY)
        with h.app.uow_factory(req_meta(h, seq_base), readonly=True) as uow:
            plan = uow.repo(PlanRepository).get(PlanId(plan_uuid))
            draft = uow.repo(DraftRepository).get(DraftId(draft_id))
            assert plan.current_revision_id is None
            assert plan.next_revision_no == 1
            assert draft.state is DraftState.OPEN
            assert uow.repo(PlanningQueries).revisions_pinning_file_version(UUID(str(v1))) == ()
            uow.rollback()
        return "trash_first"

    # Publish serialized before trash: immutable v1 pin committed and remains readable after trash.
    assert pub_outcome is not None
    rev_id = RevisionId(pub_outcome.revision_id)
    with h.client.open_file_version_content(v1) as stream:
        assert stream.read() == payload
    with h.app.uow_factory(req_meta(h, seq_base + 1), readonly=True) as uow:
        mats = planning.revision_materials(uow, rev_id)
        assert len(mats) == 1
        assert mats[0]["file_version_id"] == str(v1)
        revs = uow.repo(RevisionRepository)
        assert revs.load_typed_document(rev_id) == revs.get_document(rev_id)
        assert uow.repo(PlanningQueries).revisions_pinning_file_version(UUID(str(v1))) == (rev_id,)
        uow.rollback()

    # Any subsequent publication referencing the now-trashed file is rejected.
    next_draft = dispatch_new(h.client, OpenDraft(plan_id=plan_uuid, base="current"))
    next_doc = base_spec_doc(
        [_file_mat(mat_uid, "race-mat", v1, policy=policy)],
        goal="Post-trash publish must fail.",
        seed=seed,
    )
    next_saved = dispatch_new(
        h.client, SaveDraft(plan_uuid, next_draft.draft_id, next_draft.edit_version, cast("Any", next_doc))
    )
    with pytest.raises(PreconditionFailed) as post_err:
        dispatch_new(
            h.client,
            PublishRevision(
                plan_uuid, next_draft.draft_id, next_saved.edit_version, content_digest, "must fail"
            ),
        )
    assert post_err.value.code in (ErrorCode.FILE_VERSION_NOT_READY, ErrorCode.PLAN_NOT_READY)
    return "publish_first"


def _exercise_concurrent_trash_and_publish_serialized(h: Harness) -> None:
    outcomes: set[str] = set()
    for idx, policy in enumerate(("latest_at_publish", "pinned", "latest_at_publish", "pinned")):
        outcomes.add(_run_concurrent_trash_publish_trial(h, policy=policy, trial=idx))
    assert outcomes <= {"trash_first", "publish_first"}


def test_concurrent_trash_and_publish_serialized_memory(mem_env: Harness) -> None:
    _exercise_concurrent_trash_and_publish_serialized(mem_env)


@pytest.mark.pg
def test_concurrent_trash_and_publish_serialized_postgres(pg_env: Harness) -> None:
    _exercise_concurrent_trash_and_publish_serialized(pg_env)
