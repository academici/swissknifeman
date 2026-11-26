"""Integration tests for artifact host operations with PG, blob store, and sandbox."""

from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from integration.artifacts.test_upload_flow import (
    NOW,
    OWNER_ID,
    Harness,
    dispatch_new,
    open_test_app,
    seed_principals,
)
from skm.adapters.blobs.local.materializer import (
    READY_MANIFEST_NAME,
    LocalMaterialWriter,
    LocalUploadSourceReader,
)
from skm.adapters.sandbox.landlock import WRITE_MIN_ABI
from skm.adapters.sandbox.landlock_exec import landlock_abi, probe_enforcement
from skm.application_bus.client import SkmClient
from skm.application_bus.host import HostServices
from skm.bootstrap.host_services import build_host_services
from skm.bootstrap.modules import MANIFESTS
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed, ValidationFailed
from skm.kernel.ids import FileVersionId, HostId, PrincipalId, ProjectId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.modules.access.domain.membership import Membership
from skm.modules.access.ports import MembershipRepository
from skm.modules.access.public import Role
from skm.modules.artifacts import public as artifacts
from skm.modules.artifacts.domain.materialization import MaterialEntry
from skm.modules.artifacts.generated.host import MaterializeFilesRequest
from skm.modules.artifacts.host.upload_file import UploadSourceReader
from skm.modules.artifacts.ports import BlobStore, MaterialWriter
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from skm.platform.system_ids import Uuid7Generator
from support.pg import TestDatabase, clean_test_database, pg_session, test_database
from support.seed import SEED

__all__ = ["clean_test_database", "pg_session", "test_database"]

HOST_ID = HostId(UUID("01900000-0000-7000-8000-0000000000e1"))
WORKER_ID = PrincipalId(UUID("01900000-0000-7000-8000-0000000000e2"))
ASSIGNMENT_ID = UUID("01900000-0000-7000-8000-0000000000e3")


def _services(client: SkmClient, surface: Surface = Surface.CLI) -> HostServices:
    return build_host_services(
        {"host": {"id": str(HOST_ID)}},
        client=client,
        plugins=(),
        environ={},
        surface=surface,
        host_config=dict,
        gateways={
            MaterialWriter: LocalMaterialWriter(),
            UploadSourceReader: LocalUploadSourceReader(),
        },
        operations=tuple(op for m in MANIFESTS for op in m.host_operations),
    )


def _run_op(services: HostServices, client: SkmClient, name: str, request: object) -> Any:
    return services.run(name, request, client=client, cancel=CancelSource().token)


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def dual_harness(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[Harness]:
    backend: str = request.param
    dsn: str | None = None
    if backend == "postgres":
        db: TestDatabase = request.getfixturevalue("clean_test_database")
        dsn = db.dsn
    app_root = tmp_path / f"app_{backend}"
    app_root.mkdir(parents=True, exist_ok=True)
    app, clock, blobs_root = open_test_app(backend, app_root, dsn)
    try:
        actor = seed_principals(
            app,
            backend,
            people=(
                (OWNER_ID, PrincipalKind.HUMAN, "owner"),
                (WORKER_ID, PrincipalKind.WORKER, "worker-1"),
            ),
            roles=((SEED.instance_id, OWNER_ID, Role.OWNER),),
        )
        client = app.client(actor=actor, surface=Surface.CLI)
        ws = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="main", title="Main")).workspace_id)
        proj = ProjectId(
            dispatch_new(client, CreateProject(workspace_id=ws, slug="skm", title="SKM")).project_id
        )
        with app.uow_factory(RequestMeta("req_" + "2" * 26, Surface.CLI, None, NOW)) as uow:
            uow.repo(MembershipRepository).upsert(
                Membership(ScopeId(ws), WORKER_ID, Role.WORKER, OWNER_ID, NOW)
            )
            uow.commit()
        yield Harness(app, clock, actor, client, ws, proj, blobs_root, dsn)
    finally:
        app.close()


def test_host_upload_and_materialize_end_to_end(dual_harness: Harness, tmp_path: Path) -> None:
    services = _services(dual_harness.client, Surface.CLI)

    src_dir = tmp_path / "sources"
    src_dir.mkdir()
    p1 = src_dir / "CON.txt"
    p2 = src_dir / "spec.md"
    b1 = b"reserved-windows-name-payload\n"
    b2 = b"# Specification\nPinned content v2.\n"
    p1.write_bytes(b1)
    p2.write_bytes(b2)

    # Symlink upload is rejected via UploadSourceReader gateway without reading target
    sym = src_dir / "link.md"
    sym.symlink_to(p2)
    with pytest.raises(ValidationFailed) as sym_err:
        _run_op(
            services,
            dual_harness.client,
            "artifacts.host.upload_file",
            {"path": str(sym), "workspace_id": str(dual_harness.ws)},
        )
    assert sym_err.value.code is ErrorCode.CONTENT_UNSAFE
    assert sym_err.value.details is not None
    findings = cast("list[dict[str, object]]", sym_err.value.details["findings"])
    assert findings[0]["rule"] == "CS-SYMLINK"

    up1 = _run_op(
        services,
        dual_harness.client,
        "artifacts.host.upload_file",
        {"path": str(p1), "workspace_id": str(dual_harness.ws), "project_id": str(dual_harness.proj)},
    )
    up2 = _run_op(
        services,
        dual_harness.client,
        "artifacts.host.upload_file",
        {"path": str(p2), "file_id": up1["file_id"]},
    )
    v1_id = UUID(up1["file_version_id"])
    v2_id = UUID(up2["file_version_id"])

    mat_root = tmp_path / "materials" / "attempt-1"
    entries = _run_op(
        services,
        dual_harness.client,
        "artifacts.host.materialize_files",
        MaterializeFilesRequest(file_version_ids=(v1_id, v2_id), target_dir=str(mat_root)),
    )
    assert isinstance(entries, tuple)
    assert len(entries) == 2
    for item in cast("tuple[MaterialEntry, ...]", entries):
        assert isinstance(item, MaterialEntry)
        assert str(dual_harness.blobs_root) not in item.relative_path
        mat_file = mat_root / item.relative_path
        st = os.lstat(mat_file)
        assert stat.S_ISREG(st.st_mode)
        assert stat.S_IMODE(st.st_mode) == 0o444
        assert (st.st_mode & 0o111) == 0
        assert stat.S_IMODE(os.lstat(mat_file.parent).st_mode) == 0o555
        digest = "sha256:" + hashlib.sha256(mat_file.read_bytes()).hexdigest()
        assert digest == item.digest.value

    typed_entries = cast("tuple[MaterialEntry, ...]", entries)
    assert typed_entries[0].relative_path == f"{v1_id}/_CON.txt"
    assert typed_entries[1].relative_path == f"{v2_id}/spec.md"
    assert stat.S_IMODE(os.lstat(mat_root).st_mode) == 0o555
    assert stat.S_IMODE(os.lstat(mat_root / READY_MANIFEST_NAME).st_mode) == 0o444


def test_worker_grant_enforcement_and_trashed_refusal(dual_harness: Harness, tmp_path: Path) -> None:
    cli_services = _services(dual_harness.client, Surface.CLI)
    src = tmp_path / "input.txt"
    src.write_bytes(b"worker-bound-bytes")
    up = _run_op(
        cli_services,
        dual_harness.client,
        "artifacts.host.upload_file",
        {"path": str(src), "workspace_id": str(dual_harness.ws), "project_id": str(dual_harness.proj)},
    )
    vid = FileVersionId(UUID(up["file_version_id"]))
    file_id = artifacts.FileId(UUID(up["file_id"]))

    worker_actor = Actor(WORKER_ID, PrincipalKind.WORKER, "worker-1")
    worker_client = dual_harness.app.client(actor=worker_actor, surface=Surface.WORKER)
    worker_services = _services(worker_client, Surface.WORKER)

    # Without active AccessGrant, worker cannot materialize
    with pytest.raises(Forbidden) as denied:
        _run_op(
            worker_services,
            worker_client,
            "artifacts.host.materialize_files",
            MaterializeFilesRequest(file_version_ids=(vid,), target_dir=str(tmp_path / "denied_mat")),
        )
    assert denied.value.code is ErrorCode.FORBIDDEN

    # Issue assignment grant and materialize on WORKER surface
    with dual_harness.app.uow_factory(RequestMeta("req_" + "3" * 26, Surface.WORKER, None, NOW)) as uow:
        artifacts.grant_access(
            uow,
            principal_id=WORKER_ID,
            version_ids=(vid,),
            reason=artifacts.GrantReason.ASSIGNMENT,
            ref=str(ASSIGNMENT_ID),
            expires_at=NOW + timedelta(hours=1),
            ids=Uuid7Generator(dual_harness.clock),
            now=NOW,
        )
        uow.commit()

    worker_mat = tmp_path / "worker_mat"
    res = cast(
        "tuple[MaterialEntry, ...]",
        _run_op(
            worker_services,
            worker_client,
            "artifacts.host.materialize_files",
            MaterializeFilesRequest(file_version_ids=(vid,), target_dir=str(worker_mat)),
        ),
    )
    assert len(res) == 1
    assert (worker_mat / res[0].relative_path).read_bytes() == b"worker-bound-bytes"

    # Trashing the file blocks subsequent materialization with FILE_VERSION_NOT_READY
    cur_file = cast("artifacts.GetFileView", dual_harness.client.ask(artifacts.GetFile(file_id=file_id)))
    dispatch_new(
        dual_harness.client,
        artifacts.TrashFile(file_id=file_id, expected_row_version=cur_file.row_version, reason="obsolete"),
    )
    with pytest.raises(PreconditionFailed) as trashed_err:
        _run_op(
            cli_services,
            dual_harness.client,
            "artifacts.host.materialize_files",
            MaterializeFilesRequest(file_version_ids=(vid,), target_dir=str(tmp_path / "trashed_mat")),
        )
    assert trashed_err.value.code is ErrorCode.FILE_VERSION_NOT_READY


def test_corrupt_blob_and_checkout_target_refused(dual_harness: Harness, tmp_path: Path) -> None:
    services = _services(dual_harness.client, Surface.CLI)
    src = tmp_path / "clean.txt"
    src.write_bytes(b"clean-bytes-before-corruption")
    up = _run_op(
        services,
        dual_harness.client,
        "artifacts.host.upload_file",
        {"path": str(src), "workspace_id": str(dual_harness.ws)},
    )
    vid = UUID(up["file_version_id"])

    # 1. Refuses materialization into a Git checkout / worktree
    checkout = tmp_path / "repo_checkout"
    (checkout / ".git").mkdir(parents=True)
    with pytest.raises(ValidationFailed) as chk_err:
        _run_op(
            services,
            dual_harness.client,
            "artifacts.host.materialize_files",
            MaterializeFilesRequest(file_version_ids=(vid,), target_dir=str(checkout / "materials")),
        )
    assert chk_err.value.code is ErrorCode.INVALID_REFERENCE
    assert chk_err.value.details is not None
    assert chk_err.value.details["reason"] == "inside_checkout"

    # 2. Corrupt underlying blob object -> BLOB_DIGEST_MISMATCH and no ready manifest
    store: Any = dual_harness.app.gateways.get(BlobStore)
    if hasattr(store, "_objects"):
        key = next(iter(store._objects))
        store._objects[key] = replace(store._objects[key], data=b"corrupted!")
    else:
        ws_objs = dual_harness.blobs_root / str(dual_harness.ws) / "objects"
        obj_files = [p for p in ws_objs.rglob("*") if p.is_file()]
        assert len(obj_files) == 1
        os.chmod(obj_files[0], 0o600)
        obj_files[0].write_bytes(b"corrupted!")
        os.chmod(obj_files[0], 0o444)

    bad_target = tmp_path / "corrupt_mat"
    with pytest.raises(ValidationFailed) as bad_err:
        _run_op(
            services,
            dual_harness.client,
            "artifacts.host.materialize_files",
            MaterializeFilesRequest(file_version_ids=(vid,), target_dir=str(bad_target)),
        )
    assert bad_err.value.code is ErrorCode.BLOB_DIGEST_MISMATCH
    assert not (bad_target / READY_MANIFEST_NAME).exists()


def test_materialized_root_read_only_under_sandbox_isolation(dual_harness: Harness, tmp_path: Path) -> None:
    services = _services(dual_harness.client, Surface.CLI)
    src = tmp_path / "readonly.txt"
    src.write_bytes(b"immutable-sandbox-input")
    up = _run_op(
        services,
        dual_harness.client,
        "artifacts.host.upload_file",
        {"path": str(src), "workspace_id": str(dual_harness.ws)},
    )
    vid = UUID(up["file_version_id"])

    mat_root = tmp_path / "sandbox_materials"
    work_dir = tmp_path / "sandbox_work"
    work_dir.mkdir(mode=0o700)
    entries = cast(
        "tuple[MaterialEntry, ...]",
        _run_op(
            services,
            dual_harness.client,
            "artifacts.host.materialize_files",
            MaterializeFilesRequest(file_version_ids=(vid,), target_dir=str(mat_root)),
        ),
    )
    mat_file = mat_root / entries[0].relative_path

    script = (
        "import pathlib, sys\n"
        "mat = pathlib.Path(sys.argv[1])\n"
        "out = pathlib.Path(sys.argv[2]) / 'copied.txt'\n"
        "out.write_bytes(mat.read_bytes())\n"
        "try:\n"
        "    mat.write_bytes(b'mutated')\n"
        "    sys.exit(99)\n"
        "except OSError:\n"
        "    pass\n"
        "try:\n"
        "    (mat.parent / 'injected.txt').write_bytes(b'nope')\n"
        "    sys.exit(98)\n"
        "except OSError:\n"
        "    pass\n"
    )
    child_argv = [sys.executable, "-c", script, str(mat_file), str(work_dir)]
    if landlock_abi() >= WRITE_MIN_ABI and probe_enforcement(sys.executable, WRITE_MIN_ABI) is None:
        argv = [
            sys.executable,
            "-P",
            "-m",
            "skm.adapters.sandbox.landlock_exec",
            "--no-default-rw",
            "--min-abi",
            str(WRITE_MIN_ABI),
            "--rw",
            str(work_dir),
            "--protect",
            str(mat_root),
            "--",
            *child_argv,
        ]
    else:
        argv = child_argv

    proc = subprocess.run(argv, cwd=work_dir, capture_output=True, text=True, timeout=10, check=False)
    assert proc.returncode == 0, (proc.stdout, proc.stderr)
    assert (work_dir / "copied.txt").read_bytes() == b"immutable-sandbox-input"
    assert mat_file.read_bytes() == b"immutable-sandbox-input"
    assert stat.S_IMODE(os.lstat(mat_file).st_mode) == 0o444
