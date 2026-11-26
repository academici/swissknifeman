"""P06.Z Milestone M2 acceptance tests: plan with pinned artifacts on PostgreSQL and local store."""

from __future__ import annotations

import hashlib
import json
import os
import stat
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from e2e import test_p05_planning as p05
from e2e.test_p05_planning import Sandbox, _new_project, _rich_spec, _write_json, err_cli, ok_cli, ok_sub
from fakes.clock import FrozenClock
from skm.adapters.blobs.local import materializer as local_mat
from skm.adapters.postgres.migrations.runner import discover_migrations
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostServices
from skm.bootstrap.composition import App, open_cli_app
from skm.bootstrap.host_services import build_host_services
from skm.bootstrap.modules import MANIFESTS
from skm.kernel.actor import SYSTEM_PRINCIPAL_ID, Actor, PrincipalKind
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, InternalError, PreconditionFailed, ValidationFailed
from skm.kernel.ids import FileVersionId, HostId, PrincipalId, ProjectId, RevisionId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRef, ScopeRegistry
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import Role
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.domain.blob import LocationState
from skm.modules.artifacts.domain.classification import allowed_for_runtime, derived_floor, ensure_not_lowered
from skm.modules.artifacts.domain.file_version import VersionSource
from skm.modules.artifacts.domain.materialization import MaterialEntry
from skm.modules.artifacts.generated.commands import ExpireStagedBlobs, PruneOrphanObjects
from skm.modules.artifacts.generated.host import MaterializeFilesRequest
from skm.modules.artifacts.generated.queries import FindOrphanBlobs
from skm.modules.artifacts.generated.results import ExpireStagedBlobsResult, PruneOrphanObjectsResult
from skm.modules.artifacts.generated.views import FindOrphanBlobsView
from skm.modules.artifacts.host.upload_file import UploadSourceReader
from skm.modules.artifacts.ports import BlobRepository, BlobStore, FileVersionRepository, MaterialWriter
from skm.modules.planning import public as planning_public
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.config.store import ConfigStore, ScopeTree
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

pytestmark = [pytest.mark.e2e, pytest.mark.pg]
HOST_ID = HostId(UUID("0192f5c4-0000-7000-8000-0000000000e1"))
WORKER_ID = PrincipalId(UUID("0192f5c4-0000-7000-8000-0000000000e2"))
SERVICE_ACTOR = Actor(SYSTEM_PRINCIPAL_ID, PrincipalKind.SERVICE, "system")


def _open_box_app(box: Sandbox) -> tuple[App, Actor, SkmClient, Path]:
    env = box.env()
    boot = load_bootstrap(None, env, box.home, instance=None)
    app, actor = open_cli_app(boot, environ=env, invocation={}, as_token=None)
    return app, actor, app.client(actor=actor, surface=Surface.CLI), boot.blobs_root


def _host_services(client: SkmClient, surface: Surface = Surface.CLI) -> HostServices:
    gw = {
        MaterialWriter: local_mat.LocalMaterialWriter(),
        UploadSourceReader: local_mat.LocalUploadSourceReader(),
    }
    ops = tuple(op for m in MANIFESTS for op in m.host_operations)
    kw: dict[str, Any] = {"plugins": (), "environ": {}, "surface": surface, "host_config": dict}
    return build_host_services(
        {"host": {"id": str(HOST_ID)}}, client=client, gateways=gw, operations=ops, **kw
    )


def _run_host_op(services: HostServices, client: SkmClient, name: str, request: object) -> Any:
    return services.run(name, request, client=client, cancel=CancelSource().token)


def _req_meta(seq: int, surface: Surface = Surface.CLI) -> RequestMeta:
    return RequestMeta(f"req_{seq:026d}".replace("0", "A"), surface, None, SystemClock().now())


@pytest.fixture(scope="module")
def _db_cache(tmp_path_factory: pytest.TempPathFactory) -> Iterator[list[Any]]:
    state: list[Any] = [tmp_path_factory.mktemp("p06_box"), None, None, None]
    try:
        yield state
    finally:
        if state[1] is not None:
            drop_q = sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(state[2]))
            with psycopg.connect(state[1], autocommit=True, connect_timeout=5) as admin:
                admin.execute(drop_q)


@pytest.fixture
def sandbox(pg_dsn: str, _db_cache: list[Any]) -> Sandbox:
    if _db_cache[3] is not None:
        return cast("Sandbox", _db_cache[3])
    info = {k: str(v) for k, v in conninfo_to_dict(pg_dsn).items()}
    host, dbname = info.get("host", ""), info.get("dbname", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not dbname.endswith("_test"):
        pytest.fail("P06.Z e2e creates databases only on a local server through '*_test'", pytrace=False)
    root, db_name = cast("Path", _db_cache[0]), f"skm_t_p06_{os.getpid()}_{uuid4().hex[:8]}"
    _db_cache[1], _db_cache[2] = pg_dsn, db_name
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
    dsn = make_conninfo(pg_dsn, dbname=db_name)
    init_res = ok_sub(Sandbox(root, dsn, UUID(int=0)), "init --database-url", dsn, "--host-name", "p06-host")
    head_ver = discover_migrations()[-1].version
    assert (init_res["already_initialized"], init_res["migrations"]["current"]) == (False, head_ver)
    _db_cache[3] = Sandbox(root, dsn, UUID(str(init_res["workspace"]["workspace_id"])))
    return cast("Sandbox", _db_cache[3])


def _verify_safety_ack_and_cli_views(box: Sandbox, tmp_path: Path, file1_id: str, v1_bytes: bytes) -> None:
    secret_file = tmp_path / ".env.production"
    secret_val = "skm_a1b2c3d4_super_secret_token_payload_99887766"
    secret_file.write_text(f"API_TOKEN={secret_val}\n", encoding="utf-8")
    unsafe_err = p05.err_sub(box, 1, "file add", str(secret_file), "--title", "Prod Env")
    assert (unsafe_err["code"], secret_val not in json.dumps(unsafe_err)) == ("CONTENT_UNSAFE", True)
    assert "CS-SECRET-NAME" in {f["rule"] for f in unsafe_err["details"]["findings"]}
    low_cmd = "file add --ack CS-SECRET-NAME --classification public"
    assert err_cli(box, 1, low_cmd, str(secret_file))["code"] == "CONTENT_UNSAFE"
    ack_cmd = "file add --ack CS-SECRET-NAME --ack CS-SECRET-CONTENT --classification confidential"
    acked = ok_cli(box, ack_cmd, str(secret_file))
    assert (acked["classification"], acked["safety"]["verdict"]) == ("confidential", "warn")
    show_human = p05.run_sub(box, "file show", file1_id, json_mode=False)
    assert (show_human.returncode, "Architecture Specification" in show_human.stdout) == (0, True)
    cat_raw = p05.run_sub(box, "file cat", file1_id, json_mode=False)
    assert (cat_raw.returncode, cat_raw.stdout.encode("utf-8")) == (0, v1_bytes)


def _verify_r1_immutability_and_r2_restore(
    box: Sandbox, tmp_path: Path, r1_id: str, r1_doc: dict[str, Any], ids: tuple[str, ...], v1_bytes: bytes
) -> None:
    file1_id, file1_v1_id, file1_v2_id, guide_v1_id, guide_v2_id = ids
    expected_r1_mats = {"api-guide": guide_v1_id, "ref-notes": file1_v1_id}
    app, _, _, _ = _open_box_app(box)
    try:
        with app.uow_factory(_req_meta(10), readonly=True) as uow:
            mats_facade = planning_public.revision_materials(uow, RevisionId(UUID(r1_id)))
            assert {m["key"]: m["file_version_id"] for m in mats_facade} == expected_r1_mats
            txt = artifacts.read_text_content(uow, FileVersionId(UUID(file1_v1_id)), max_bytes=1024)
            assert txt == v1_bytes.decode("utf-8")
            latest_v = artifacts.latest_ready_version(uow, artifacts.FileId(UUID(file1_id)))
            assert latest_v is not None
            assert str(latest_v.file_version_id) == file1_v2_id
            uow.rollback()
    finally:
        app.close()

    d2_id = str(ok_cli(box, "plan draft open PLAN1")["draft_id"])
    spec_r2 = _rich_spec(title="M2 Foundation R2", fv_lat=guide_v1_id, fv_pin=file1_v1_id, seed=1)
    ok_cli(box, "plan draft save PLAN1", str(_write_json(tmp_path / "m2_r2.json", spec_r2)))
    r2 = ok_cli(box, f"plan publish PLAN1 --draft {d2_id} --reason M2-R2")
    pins_r2 = {m["material_key"]: m["file_version_id"] for m in r2["pinned_materials"]}
    assert pins_r2 == {"api-guide": guide_v2_id, "ref-notes": file1_v1_id}
    assert p05.assert_typed_equals_payload(box.dsn, r1_id) == r1_doc
    restore_cmd = f"plan restore PLAN1 1 --reason r1 --expected-current revision:{r2['revision_id']}"
    restored = ok_cli(box, restore_cmd)
    r3_doc = p05.assert_typed_equals_payload(box.dsn, restored["revision_id"])
    assert {m["key"]: m["file_version_id"] for m in r3_doc["materials"]} == expected_r1_mats


def test_m2_e2e_plan_with_pinned_material(sandbox: Sandbox, tmp_path: Path) -> None:
    """Full M2 flow via CLI subprocesses: upload v1 -> plan pin -> publish r1 -> upload v2 -> r1 stays v1."""
    _new_project(sandbox, "p-m2-pin")
    v1_bytes = b"# Architecture Specification v1\nImmutable baseline content.\n"
    v2_bytes = b"# Architecture Specification v2\nUpdated content after R1 publication.\n"
    v1_digest, v2_digest = (f"sha256:{hashlib.sha256(b).hexdigest()}" for b in (v1_bytes, v2_bytes))
    initial_txt, updated_txt = tmp_path / "initial.txt", tmp_path / "updated.txt"
    guide_v1_md, guide_v2_md = tmp_path / "guide_v1.md", tmp_path / "guide_v2.md"
    initial_txt.write_bytes(v1_bytes)
    updated_txt.write_bytes(v2_bytes)
    guide_v1_md.write_bytes(b"# Operational Guide v1\n")
    guide_v2_md.write_bytes(b"# Operational Guide v2\n")

    added1 = ok_sub(sandbox, "file add", str(initial_txt), "--title", "Architecture Specification")
    file1_id, file1_v1_id = str(added1["file_id"]), str(added1["file_version_id"])
    assert (added1["version_no"], added1["digest"], added1["size_bytes"]) == (1, v1_digest, len(v1_bytes))
    added_guide = ok_cli(sandbox, "file add", str(guide_v1_md), "--title", "Operational Guide")
    guide_id, guide_v1_id = str(added_guide["file_id"]), str(added_guide["file_version_id"])
    _verify_safety_ack_and_cli_views(sandbox, tmp_path, file1_id, v1_bytes)

    assert ok_cli(sandbox, "plan create --no-draft", "M2 Foundation")["alias"] == "PLAN1"
    d1_id = str(ok_cli(sandbox, "plan draft open PLAN1")["draft_id"])
    spec_1 = _rich_spec(title="M2 Foundation", fv_lat=guide_v1_id, fv_pin=file1_v1_id, seed=1)
    spec_f = _write_json(tmp_path / "m2.json", spec_1)
    assert ok_cli(sandbox, "plan draft save PLAN1", str(spec_f))["counts"]["error"] == 0
    cand_digest = str(ok_cli(sandbox, "plan draft publication-preview PLAN1")["content_digest"])

    pub_cmd = f"plan publish PLAN1 --draft {d1_id} --reason M2-R1 --expected-content-digest"
    r1 = ok_sub(sandbox, pub_cmd, cand_digest)
    r1_id = str(r1["revision_id"])
    assert (r1["revision_no"], r1["content_digest"]) == (1, cand_digest)
    pins_r1 = {m["material_key"]: (m["file_version_id"], m["resolved_from"]) for m in r1["pinned_materials"]}
    assert pins_r1 == {"api-guide": (guide_v1_id, "latest_at_publish"), "ref-notes": (file1_v1_id, "pinned")}
    r1_doc = p05.assert_typed_equals_payload(sandbox.dsn, r1_id)
    bind_q = (
        "SELECT file_version_id::text, role "
        "FROM skm_planning.revision_file_bindings WHERE revision_id = %s ORDER BY role"
    )
    assert p05.rows(sandbox.dsn, bind_q, r1_id) == [(guide_v1_id, "input"), (file1_v1_id, "reference")]

    ver2 = ok_sub(sandbox, "file version", file1_id, str(updated_txt))
    file1_v2_id = str(ver2["file_version_id"])
    assert (ver2["version_no"], ver2["digest"], file1_v2_id != file1_v1_id) == (2, v2_digest, True)
    guide_v2_id = str(ok_cli(sandbox, "file version add", guide_id, str(guide_v2_md))["file_version_id"])

    f_show = ok_cli(sandbox, "file show", file1_id)
    assert f_show["current_version"]["file_version_id"] == file1_v2_id
    assert [v["version_no"] for v in f_show["versions"]] == [2, 1]
    assert ok_cli(sandbox, "file cat", file1_id)["text"] == v2_bytes.decode("utf-8")
    assert ok_cli(sandbox, f"file cat {file1_id} --version 1")["text"] == v1_bytes.decode("utf-8")
    assert ok_cli(sandbox, "file cat", f"fv:{file1_v1_id}")["text"] == v1_bytes.decode("utf-8")

    rev1_show = ok_sub(sandbox, "plan show PLAN1 --revision 1")
    assert rev1_show["content_digest"] == cand_digest
    rev1_mats = {m["key"]: m["file_version_id"] for m in rev1_show["document"]["materials"]}
    assert rev1_mats == {"api-guide": guide_v1_id, "ref-notes": file1_v1_id}
    ent_show = ok_cli(sandbox, "plan show PLAN1 --revision 1 --entity material/ref-notes")
    assert ent_show["document"]["file_version_id"] == file1_v1_id
    id_pack = (file1_id, file1_v1_id, file1_v2_id, guide_v1_id, guide_v2_id)
    _verify_r1_immutability_and_r2_restore(sandbox, tmp_path, r1_id, r1_doc, id_pack, v1_bytes)


def _verify_version_scoped_access_and_classification_floor(
    app: App, client: SkmClient, ws_id: WorkspaceId, proj_id: ProjectId, tmp_path: Path
) -> None:
    shared_bytes = b"identical-content-digest-across-two-logical-files\n"
    f_a, f_b = tmp_path / "file_a.txt", tmp_path / "file_b.txt"
    f_a.write_bytes(shared_bytes)
    f_b.write_bytes(shared_bytes)
    services = _host_services(client, Surface.CLI)
    base_req = {"workspace_id": str(ws_id), "project_id": str(proj_id)}
    req_a = {**base_req, "path": str(f_a), "classification": "internal"}
    req_b = {**base_req, "path": str(f_b), "classification": "confidential"}
    up_a = _run_host_op(services, client, "artifacts.host.upload_file", req_a)
    up_b = _run_host_op(services, client, "artifacts.host.upload_file", req_b)
    ver_a, ver_b = FileVersionId(UUID(up_a["file_version_id"])), FileVersionId(UUID(up_b["file_version_id"]))
    assert (ver_a != ver_b, up_a["digest"] == up_b["digest"]) == (True, True)

    now, ids = SystemClock().now(), Uuid7Generator(SystemClock())
    with app.uow_factory(_req_meta(20)) as uow:
        p_kw: dict[str, Any] = {"principal_id": WORKER_ID, "kind": PrincipalKind.WORKER, "created_by": None}
        uow.repo(PrincipalRepository).add(new_principal(**p_kw, display_name="m2-worker", now=now))
        uow.repo(MembershipRepository).upsert(Membership(ScopeId(ws_id), WORKER_ID, Role.WORKER, None, now))
        uow.commit()

    w_actor = Actor(WORKER_ID, PrincipalKind.WORKER, "m2-worker")
    worker_client = app.client(actor=w_actor, surface=Surface.WORKER)
    worker_services = _host_services(worker_client, Surface.WORKER)
    with pytest.raises(Forbidden):
        worker_client.open_file_version_content(ver_a)

    reason, ref = artifacts.GrantReason.ASSIGNMENT, "assign:m2-only-a"
    with app.uow_factory(_req_meta(21, Surface.WORKER)) as uow:
        g_kw: dict[str, Any] = {"principal_id": WORKER_ID, "version_ids": (ver_a,), "reason": reason}
        artifacts.grant_access(uow, **g_kw, ref=ref, expires_at=now + timedelta(minutes=30), ids=ids, now=now)
        ext_t = now + timedelta(hours=2)
        assert artifacts.extend_grants(uow, reason=reason, ref=ref, expires_at=ext_t, now=now) == 1
        uow.commit()

    open_stream = worker_client.open_file_version_content(ver_a)
    try:
        with pytest.raises(Forbidden) as b_denied:
            worker_client.open_file_version_content(ver_b)
        assert b_denied.value.code is ErrorCode.FORBIDDEN
        mat_b_req = MaterializeFilesRequest(file_version_ids=(ver_b,), target_dir=str(tmp_path / "denied_b"))
        with pytest.raises(Forbidden):
            _run_host_op(worker_services, worker_client, "artifacts.host.materialize_files", mat_b_req)
        with app.uow_factory(_req_meta(22)) as uow:
            assert artifacts.revoke_grants(uow, reason=reason, ref=ref, now=now) == 1
            uow.commit()
        assert open_stream.read() == shared_bytes
    finally:
        open_stream.close()

    with pytest.raises(Forbidden):
        worker_client.open_file_version_content(ver_a)

    cls = artifacts.Classification
    assert derived_floor(requested=cls.PUBLIC, sources=[cls.CONFIDENTIAL, cls.PUBLIC]) is cls.CONFIDENTIAL
    assert allowed_for_runtime(cls.CONFIDENTIAL, cls.INTERNAL) is False
    with pytest.raises(ValidationFailed) as unk_err:
        derived_floor(requested=cls.INTERNAL, sources=[None])
    assert unk_err.value.details == {"field": "classification", "reason": "unknown_lineage"}
    with pytest.raises(ValidationFailed) as lower_err:
        ensure_not_lowered(cls.CONFIDENTIAL, cls.INTERNAL)
    assert (lower_err.value.details or {}).get("reason") == "declassification"


def test_m2_e2e_materialization_verifies_v1_bytes(sandbox: Sandbox, tmp_path: Path) -> None:
    """Materialize pinned Revision 1 materials to host: mode 0444/0555, exact v1 digest, ARTIFACT-01..05."""
    proj_id = _new_project(sandbox, "p-m2-mat")
    v1_bytes = b"pinned-v1-bytes-for-portable-materialization\n"
    v2_bytes = b"updated-v2-bytes-must-not-replace-v1-materialization\n"
    v1_digest = "sha256:" + hashlib.sha256(v1_bytes).hexdigest()

    src_dir = tmp_path / "src_files"
    src_dir.mkdir()
    con_file, v2_file, sym_path = src_dir / "CON.txt", src_dir / "spec_v2.txt", src_dir / "symlink.txt"
    con_file.write_bytes(v1_bytes)
    v2_file.write_bytes(v2_bytes)
    sym_path.symlink_to(con_file)
    assert err_cli(sandbox, 1, "file add", str(sym_path))["code"] == "CONTENT_UNSAFE"

    up1 = ok_cli(sandbox, "file add", str(con_file), "--title", "Reserved Name Spec")
    file1_id, v1_id = str(up1["file_id"]), UUID(str(up1["file_version_id"]))
    ok_cli(sandbox, "plan create", "Materialization Plan")
    spec_path = _write_json(tmp_path / "mat_spec.json", _rich_spec(fv_pin=v1_id, seed=2))
    ok_cli(sandbox, "plan draft save PLAN1", str(spec_path))
    r1_id = RevisionId(UUID(str(ok_cli(sandbox, "plan publish PLAN1 --reason pin-v1")["revision_id"])))
    ok_cli(sandbox, "file version", file1_id, str(v2_file))

    app, _, client, blobs_root = _open_box_app(sandbox)
    try:
        with app.uow_factory(_req_meta(15), readonly=True) as uow:
            rev_mats = planning_public.revision_materials(uow, r1_id)
            pinned_ids = tuple(UUID(str(m["file_version_id"])) for m in rev_mats if m["file_version_id"])
            uow.rollback()
        assert pinned_ids == (v1_id,)

        services = _host_services(client, Surface.CLI)
        mat_root = tmp_path / "materialized" / "rev1"
        req = MaterializeFilesRequest(file_version_ids=pinned_ids, target_dir=str(mat_root))
        entries = cast(
            "tuple[MaterialEntry, ...]",
            _run_host_op(services, client, "artifacts.host.materialize_files", req),
        )
        rel_p = entries[0].relative_path
        assert (len(entries), rel_p, str(blobs_root) not in rel_p) == (1, f"{v1_id}/_CON.txt", True)

        mat_file = mat_root / rel_p
        st_f = os.lstat(mat_file)
        assert (stat.S_ISREG(st_f.st_mode), stat.S_IMODE(st_f.st_mode), st_f.st_mode & 0o111) == (
            True,
            0o444,
            0,
        )
        assert stat.S_IMODE(os.lstat(mat_file.parent).st_mode) == 0o555
        assert stat.S_IMODE(os.lstat(mat_root).st_mode) == 0o555
        assert stat.S_IMODE(os.lstat(mat_root / local_mat.READY_MANIFEST_NAME).st_mode) == 0o444
        actual_dig = f"sha256:{hashlib.sha256(mat_file.read_bytes()).hexdigest()}"
        assert (mat_file.read_bytes(), actual_dig) == (v1_bytes, v1_digest)
        assert _run_host_op(services, client, "artifacts.host.materialize_files", req) == entries

        fake_checkout = tmp_path / "git_checkout"
        (fake_checkout / ".git").mkdir(parents=True)
        chk_req = MaterializeFilesRequest(file_version_ids=pinned_ids, target_dir=str(fake_checkout / "mat"))
        with pytest.raises(ValidationFailed) as chk_err:
            _run_host_op(services, client, "artifacts.host.materialize_files", chk_req)
        assert chk_err.value.code is ErrorCode.INVALID_REFERENCE
        _verify_version_scoped_access_and_classification_floor(
            app, client, WorkspaceId(sandbox.ws_id), ProjectId(proj_id), tmp_path
        )
    finally:
        app.close()


def _verify_ench6_blob_corruption_and_recovery(
    app: App, client: SkmClient, blobs_root: Path, ctx: tuple[UUID, RevisionId, FileVersionId, bytes, bytes]
) -> None:
    plan_uuid, rev1_id, v1_id, v1_b, v2_b = ctx
    with app.uow_factory(_req_meta(30), readonly=True) as uow:
        ver = uow.repo(FileVersionRepository).get(v1_id)
        loc = uow.repo(BlobRepository).locations(ver.blob_id)[0]
        blob_id, backend_id, storage_key = ver.blob_id, loc.backend_id, loc.storage_key
        uow.rollback()

    v1_path = blobs_root / storage_key
    os.chmod(v1_path, 0o600)
    v1_path.write_bytes(v2_b)
    os.chmod(v1_path, 0o444)
    services = _host_services(client, Surface.CLI)
    bad_mat = MaterializeFilesRequest(file_version_ids=(v1_id,), target_dir=str(blobs_root.parent / "bad_m"))
    with pytest.raises(ValidationFailed) as digest_err:
        _run_host_op(services, client, "artifacts.host.materialize_files", bad_mat)
    assert digest_err.value.code is ErrorCode.BLOB_DIGEST_MISMATCH

    os.chmod(v1_path, 0o600)
    os.unlink(v1_path)
    v1_path.symlink_to(blobs_root.parent)
    with pytest.raises(InternalError) as corrupt_err:
        client.open_file_version_content(v1_id)
    assert (corrupt_err.value.details or {}).get("reason") == "blob_corrupt"
    os.unlink(v1_path)
    now = SystemClock().now()
    with app.uow_factory(_req_meta(31)) as uow:
        uow.repo(BlobRepository).mark_location(blob_id, backend_id, LocationState.MISSING, now)
        uow.commit()
    with pytest.raises(PreconditionFailed) as missing_err:
        client.open_file_version_content(v1_id)
    assert missing_err.value.code is ErrorCode.FILE_VERSION_NOT_READY

    with app.uow_factory(_req_meta(32), readonly=True) as uow:
        assert planning_public.revision_materials(uow, rev1_id)[0]["file_version_id"] == str(v1_id)
        chain = uow.repo(ScopeRegistry).ancestors(ScopeId(plan_uuid))
        s_ref = ScopeRef(ScopeKind.PLAN, ScopeId(plan_uuid))
        eff = app.config.effective(uow.repo(ConfigStore), uow.repo(ScopeTree), s_ref)
        rep = planning_public.validate_revision(uow, rev1_id, scope_chain=chain, config=eff, now=now)
        assert any(
            f.code == "material_unavailable" and f.details.get("status") == "not_ready" for f in rep.findings
        )
        uow.rollback()

    v1_path.write_bytes(v1_b)
    os.chmod(v1_path, 0o444)
    with app.uow_factory(_req_meta(33)) as uow:
        uow.repo(BlobRepository).mark_location(blob_id, backend_id, LocationState.PRESENT, now)
        uow.commit()
    with client.open_file_version_content(v1_id) as recovered:
        assert recovered.read() == v1_b


def test_m2_e2e_trash_does_not_break_published_pins(sandbox: Sandbox, tmp_path: Path) -> None:
    """Trashing a file or archiving a plan preserves published pins and never orphans referenced blobs."""
    proj_id = _new_project(sandbox, "p-m2-trash")
    v1_bytes = b"durable-pinned-v1-content-survives-trash\n"
    v2_bytes = b"subsequent-v2-content-before-trash\n"
    ev_bytes = b"referenced-evidence-for-outcome-unknown-effect\n"
    p_v1, p_v2 = tmp_path / "pinned_v1.md", tmp_path / "pinned_v2.md"
    p_v1.write_bytes(v1_bytes)
    p_v2.write_bytes(v2_bytes)

    up1 = ok_cli(sandbox, "file add", str(p_v1), "--title", "Durable Spec")
    file1_id, v1_id_str = str(up1["file_id"]), str(up1["file_version_id"])
    v1_id = FileVersionId(UUID(v1_id_str))

    plan_uuid = UUID(str(ok_cli(sandbox, "plan create", "Trash Resilience Plan")["plan_id"]))
    spec_f = _write_json(tmp_path / "trash_spec.json", _rich_spec(fv_pin=v1_id_str, seed=3))
    ok_cli(sandbox, "plan draft save PLAN1", str(spec_f))
    pub1 = ok_cli(sandbox, "plan publish PLAN1 --reason pin-before-trash")
    rev1_id = RevisionId(UUID(str(pub1["revision_id"])))
    ok_cli(sandbox, "file version", file1_id, str(p_v2))

    assert ok_sub(sandbox, "file trash", file1_id, "--yes", "--reason", "superseded")["state"] == "trashed"
    active_ids = [f["file_id"] for f in ok_cli(sandbox, "file list")["items"]]
    trashed_ids = [f["file_id"] for f in ok_cli(sandbox, "file list --state trashed")["items"]]
    assert (file1_id not in active_ids, file1_id in trashed_ids) == (True, True)
    assert err_cli(sandbox, 6, "file version", file1_id, str(p_v1))["code"] == "FILE_TRASHED"

    d2 = ok_cli(sandbox, "plan draft open PLAN1")
    spec2 = _rich_spec(title="Fail trashed.", fv_pin=v1_id_str, seed=3)
    ok_cli(sandbox, "plan draft save PLAN1", str(_write_json(tmp_path / "trash_d2.json", spec2)))
    pub_err = err_cli(sandbox, 6, f"plan publish PLAN1 --draft {d2['draft_id']} --reason fail")
    assert pub_err["code"] == "PLAN_NOT_READY"
    ok_cli(sandbox, f"plan draft abandon PLAN1 --draft {d2['draft_id']} --yes")

    assert ok_sub(sandbox, "file cat", f"fv:{v1_id_str}")["text"] == v1_bytes.decode("utf-8")
    r1_show = ok_cli(sandbox, "plan show PLAN1 --revision 1")
    assert r1_show["document"]["materials"][0]["file_version_id"] == v1_id_str

    app, actor, client, blobs_root = _open_box_app(sandbox)
    try:
        now, ids, ws_id = SystemClock().now(), Uuid7Generator(SystemClock()), WorkspaceId(sandbox.ws_id)
        ev_staged = client.upload_blob(ws_id, [ev_bytes], size=len(ev_bytes), media_type="text/plain")
        with app.uow_factory(_req_meta(25)) as uow:
            c_ref, req_id = ev_staged.to_json(), "req_" + "E" * 26
            consumed = artifacts.consume_staged_blob(
                uow, ref=c_ref, workspace_id=ws_id, request_id=req_id, now=now
            )
            ev_kw: dict[str, Any] = {
                **{"workspace_id": ws_id, "project_id": ProjectId(proj_id), "title": "Evidence"},
                **{
                    "origin": artifacts.FileOrigin.EVIDENCE,
                    "staged": consumed,
                    "original_filename": "ev.log",
                },
                **{
                    "media_type": "text/plain",
                    "source": VersionSource(kind="evidence", ref="effect:1", captured_at=now),
                },
                **{
                    "classification": artifacts.Classification.INTERNAL,
                    "safety": artifacts.SafetyReport((), (), False),
                },
                **{"created_by": actor.principal_id, "ids": ids, "now": now},
            }
            ev_vid = FileVersionId(
                UUID(str(artifacts.register_file_version(uow, **ev_kw)["file_version_id"]))
            )
            uow.commit()

        ok_cli(sandbox, "plan archive PLAN1 --yes")
        bg_meta = _req_meta(26, Surface.BACKGROUND)
        exp = app.bus.dispatch(ExpireStagedBlobs(limit=100), actor=SERVICE_ACTOR, meta=bg_meta)
        assert isinstance(exp, ExpireStagedBlobsResult)
        assert exp.objects_deleted == 0

        orph = client.ask(FindOrphanBlobs(workspace_id=ws_id))
        assert isinstance(orph, FindOrphanBlobsView)
        assert (orph.orphan_objects, orph.missing_objects) == ((), ())
        with client.open_file_version_content(ev_vid) as ev_stream:
            assert ev_stream.read() == ev_bytes

        assert ok_cli(sandbox, "file restore", file1_id)["state"] == "active"
        ench6_ctx = (plan_uuid, rev1_id, v1_id, v1_bytes, v2_bytes)
        _verify_ench6_blob_corruption_and_recovery(app, client, blobs_root, ench6_ctx)
    finally:
        app.close()


def _promote_crash_orphan(app: App, ws_id: WorkspaceId, payload: bytes) -> str:
    store = app.gateways.get(BlobStore)
    return str(store.promote(store.stage(ws_id, [payload]))["storage_key"])


def test_m2_e2e_crash_after_promote_leaves_orphan(sandbox: Sandbox, tmp_path: Path) -> None:
    """Crash after promote leaves an unrecorded orphan discovered by FindOrphanBlobs and safely pruned."""
    _new_project(sandbox, "p-m2-orphan")
    ws_id = WorkspaceId(sandbox.ws_id)
    app, _, client, blobs_root = _open_box_app(sandbox)
    try:
        orphan1_bytes = b"crash-after-promote-orphan-1-reused-later\n"
        orphan2_bytes = b"crash-after-promote-orphan-2-pruned-old\n"
        orphan3_bytes = b"crash-after-promote-orphan-3-young-kept\n"
        orphan1_hex = hashlib.sha256(orphan1_bytes).hexdigest()

        key1 = _promote_crash_orphan(app, ws_id, orphan1_bytes)
        assert (blobs_root / key1).is_file()
        q_blobs = "SELECT count(*) FROM skm_artifacts.blobs WHERE content_digest = %s"
        q_staged = "SELECT count(*) FROM skm_artifacts.staged_blobs WHERE content_digest = %s"
        assert p05.rows(sandbox.dsn, q_blobs, orphan1_hex) == [(0,)]
        assert p05.rows(sandbox.dsn, q_staged, orphan1_hex) == [(0,)]

        rep1 = client.ask(FindOrphanBlobs(workspace_id=ws_id))
        assert isinstance(rep1, FindOrphanBlobsView)
        assert ([o.storage_key for o in rep1.orphan_objects], rep1.missing_objects) == ([key1], ())

        key2 = _promote_crash_orphan(app, ws_id, orphan2_bytes)
        prune_1 = PruneOrphanObjects(workspace_id=ws_id, report_digest=rep1.report_digest, confirm=True)
        with pytest.raises(PreconditionFailed) as stale_err:
            client.dispatch(prune_1, idempotency_key=client.new_idempotency_key())
        assert (stale_err.value.code, stale_err.value.details) == (
            ErrorCode.INVALID_TRANSITION,
            {"reason": "report_changed"},
        )
        t_future = SystemClock().now() + timedelta(hours=25)
        app.bus._clock = FrozenClock(t_future)
        key3 = _promote_crash_orphan(app, ws_id, orphan3_bytes)
        future_ts = t_future.timestamp()
        os.utime(blobs_root / key3, (future_ts, future_ts))
        rep2 = client.ask(FindOrphanBlobs(workspace_id=ws_id))
        assert isinstance(rep2, FindOrphanBlobsView)
        assert {o.storage_key for o in rep2.orphan_objects} == {key1, key2, key3}
        reused = client.upload_blob(ws_id, [orphan1_bytes], size=len(orphan1_bytes), media_type="text/plain")
        assert reused.digest == f"sha256:{orphan1_hex}"
        prune_2 = PruneOrphanObjects(workspace_id=ws_id, report_digest=rep2.report_digest, confirm=True)
        pruned = client.dispatch(prune_2, idempotency_key=client.new_idempotency_key())
        assert isinstance(pruned, PruneOrphanObjectsResult)
        assert (pruned.deleted, pruned.skipped_referenced) == (1, 1)
        assert (
            (blobs_root / key1).is_file(),
            (blobs_root / key2).exists(),
            (blobs_root / key3).is_file(),
        ) == (
            True,
            False,
            True,
        )
        reused_file = tmp_path / "reused_after_orphan.txt"
        reused_file.write_bytes(orphan1_bytes)
        added = ok_cli(sandbox, "file add", str(reused_file), "--title", "Recovered After Crash")
        assert ok_cli(sandbox, "file cat", str(added["file_id"]))["text"] == orphan1_bytes.decode("utf-8")
        rep3 = client.ask(FindOrphanBlobs(workspace_id=ws_id))
        assert isinstance(rep3, FindOrphanBlobsView)
        assert ([o.storage_key for o in rep3.orphan_objects], rep3.missing_objects) == ([key3], ())
        audit_q = (
            "SELECT count(*) FROM skm_core.audit_records WHERE action = 'artifacts.prune_orphan_objects'"
        )
        assert p05.rows(sandbox.dsn, audit_q)[0][0] >= 1
    finally:
        app.close()
