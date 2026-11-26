"""Unit tests for ``skm file`` CLI commands, flags, human/JSON rendering, and upload safety."""

from __future__ import annotations

import hashlib
import io
import json
import os
from collections.abc import Generator
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, TextIO, cast, override
from uuid import UUID

import pytest

from fakes.app import FakeScopeChain
from fakes.authorizer import FakeAuthorizer
from skm.adapters.blobs.local.materializer import LocalMaterialWriter, LocalUploadSourceReader
from skm.application_bus.host import HostServices
from skm.bootstrap.composition import App, CompositionOverrides, build_app
from skm.bootstrap.host_services import build_host_services
from skm.bootstrap.modules import MANIFESTS
from skm.entrypoints.cli.commands import GROUPS
from skm.entrypoints.cli.commands.file import _HELP, GROUP
from skm.entrypoints.cli.host import host_context_factory
from skm.entrypoints.cli.main import Backend, app_backend, main
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.ids import HostId, PrincipalId, ScopeId
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import PrincipalRepository
from skm.modules.artifacts.host.upload_file import UploadSourceReader
from skm.modules.artifacts.ports import MaterialWriter
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.logging import setup
from skm.platform.system_clock import SystemClock

ACTOR = Actor(PrincipalId(UUID(int=100)), PrincipalKind.HUMAN, "fixture CLI owner")
INSTANCE_ID = ScopeId(UUID(int=1))
HOST_ID = HostId(UUID(int=50))


class _TtyStringIO(StringIO):
    @override
    def isatty(self) -> bool:
        return True


@dataclass
class Cli:
    app: App
    state_dir: Path
    env: dict[str, str]
    use_host_services: bool = False

    def _backend(self, _opts: object, _env: object) -> Backend:
        attached = app_backend(self.app, ACTOR)
        host_fn = attached.host_factory
        if self.use_host_services:
            services: HostServices = build_host_services(
                {"host": {"id": str(HOST_ID)}},
                client=attached.client,
                plugins=(),
                environ={},
                surface=Surface.CLI,
                host_config=dict,
                gateways={
                    MaterialWriter: LocalMaterialWriter(),
                    UploadSourceReader: LocalUploadSourceReader(),
                },
                operations=tuple(op for m in MANIFESTS for op in m.host_operations),
            )
            host_fn = host_context_factory(services, attached.client)
        return Backend(
            client=attached.client,
            host_factory=host_fn,
            state_dir=self.state_dir,
            instance_id=self.app.instance_id,
        )

    def run(
        self,
        *args: str,
        json_mode: bool = True,
        stdin: TextIO | None = None,
    ) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        argv = [*(["--json"] if json_mode else []), *args]
        code = main(argv, environ=dict(self.env), stdout=out, stderr=err, stdin=stdin, backend=self._backend)
        return code, out.getvalue(), err.getvalue()

    def run_bytes(self, *args: str) -> tuple[int, bytes]:
        raw_buf = BytesIO()
        out = io.TextIOWrapper(raw_buf, encoding="utf-8", write_through=True)
        code = main(list(args), environ=dict(self.env), stdout=out, stderr=StringIO(), backend=self._backend)
        out.flush()
        return code, raw_buf.getvalue()

    def result(self, *args: str) -> Any:
        code, out, err = self.run(*args, json_mode=True)
        assert code == 0, (code, out, err)
        doc = json.loads(out)
        assert doc["ok"] is True, doc
        return doc["result"]

    def error(self, *args: str) -> tuple[int, dict[str, Any]]:
        code, out, err = self.run(*args, json_mode=True)
        assert code != 0, (code, out, err)
        doc = json.loads(out)
        assert doc["ok"] is False, doc
        return code, cast("dict[str, Any]", doc["error"])


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[Cli]:
    monkeypatch.setattr(setup._state, "settings", setup._state.settings)
    state_dir = tmp_path / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    app = build_app(
        load_bootstrap(None, {"SKM_DATABASE_URL": "postgresql://unused"}, tmp_path),
        surface=Surface.CLI,
        environ={},
        invocation={},
        overrides=CompositionOverrides(
            authorizer=FakeAuthorizer(),
            scopes=FakeScopeChain(),
            instance_id=INSTANCE_ID,
        ),
    )
    now = SystemClock().now()
    with app.uow_factory(RequestMeta("req_" + "0" * 26, Surface.CLI, None, now)) as uow:
        uow.repo(ScopeRegistry).create(INSTANCE_ID, ScopeKind.INSTANCE, parent=None, workspace_id=None)
        uow.repo(PrincipalRepository).add(
            new_principal(
                principal_id=ACTOR.principal_id,
                kind=ACTOR.kind,
                display_name=ACTOR.display_name,
                created_by=None,
                now=now,
            )
        )
        uow.commit()
    helper = Cli(app=app, state_dir=state_dir, env={})
    ws = helper.result("workspace", "create", "ws1")
    proj = helper.result("project", "create", "proj1", "--workspace", ws["workspace_id"])
    helper.env.update(SKM_WORKSPACE=ws["workspace_id"], SKM_PROJECT=proj["project_id"])
    yield helper
    app.close()


def test_discovered_group_and_help_need_no_backend() -> None:
    assert GROUP in GROUPS
    for argv in (["file", "--help"], *(["file", verb, "--help"] for verb in _HELP)):
        out, err = StringIO(), StringIO()
        code = main(
            argv,
            environ={},
            stdout=out,
            stderr=err,
            backend=lambda *_: pytest.fail("help must not open backend"),
        )
        assert (code, err.getvalue()) == (0, "")
        assert "usage: skm file" in out.getvalue()


@pytest.mark.parametrize("via_host", [False, True])
def test_cli_file_add_version_and_cat_byte_for_byte(cli: Cli, tmp_path: Path, via_host: bool) -> None:
    cli.use_host_services = via_host
    v1_bytes = b"\x89PNG\r\n\x1a\n\x00\xff\xfe\xfahello-v1"
    v2_bytes = b"second version utf-8 payload\nline two"
    v3_bytes = b"\x00\x01\x02\x80\xffbinary-v3-no-newline"
    src1 = tmp_path / "diagram.png"
    src2 = tmp_path / "notes.txt"
    src3 = tmp_path / "blob.bin"
    src1.write_bytes(v1_bytes)
    src2.write_bytes(v2_bytes)
    src3.write_bytes(v3_bytes)

    added = cli.result(
        "file",
        "add",
        str(src1),
        "--title",
        "Architecture Diagram",
        "--media-type",
        "image/png",
        "--description",
        "initial png",
    )
    file_id = added["file_id"]
    ver1_id = added["file_version_id"]
    assert added["version_no"] == 1
    assert added["classification"] == "internal"
    assert added["digest"] == f"sha256:{hashlib.sha256(v1_bytes).hexdigest()}"
    assert src1.read_bytes() == v1_bytes  # source untouched

    v2 = cli.result("file", "version", "add", f"file:{file_id}", str(src2), "--description", "text update")
    ver2_id = v2["file_version_id"]
    assert v2["version_no"] == 2
    assert src2.read_bytes() == v2_bytes

    prefix = UUID(file_id).hex[:16]
    cur_row_ver = str(cli.result("file", "show", file_id)["row_version"])
    v3 = cli.result(
        "file",
        "version",
        prefix,
        str(src3),
        "--expected-version",
        cur_row_ver,
        "--media-type",
        "application/octet-stream",
    )
    ver3_id = v3["file_version_id"]
    assert v3["version_no"] == 3
    assert src3.read_bytes() == v3_bytes

    # Raw binary stdout cat across all reference forms
    assert cli.run_bytes("file", "cat", f"fv:{ver1_id}") == (0, v1_bytes)
    assert cli.run_bytes("file", "cat", ver2_id) == (0, v2_bytes)
    assert cli.run_bytes("file", "cat", f"file:{file_id}") == (0, v3_bytes)
    assert cli.run_bytes("file", "cat", prefix, "--version", "1") == (0, v1_bytes)
    assert cli.run_bytes("file", "cat", UUID(ver2_id).hex[:16]) == (0, v2_bytes)

    # --output atomic file write + human and JSON cat modes
    out_file = tmp_path / "restored.png"
    code_h, out_h, _ = cli.run(
        "file", "cat", file_id, "--version", "1", "--output", str(out_file), json_mode=False
    )
    assert code_h == 0
    assert f"wrote {len(v1_bytes)} B" in out_h
    assert out_file.read_bytes() == v1_bytes

    cat_json = cli.result("file", "cat", ver3_id)
    assert cat_json["size_bytes"] == len(v3_bytes)
    assert cat_json["text"] is None


def test_cli_human_and_json_modes_pagination_trash_restore_and_scopes(cli: Cli, tmp_path: Path) -> None:
    ws2 = cli.result("workspace", "create", "ws2")["workspace_id"]
    proj2 = cli.result("project", "create", "proj2", "--workspace", ws2)["project_id"]

    f_paths = [tmp_path / f"doc-{idx}.txt" for idx in range(3)]
    for idx, p in enumerate(f_paths):
        p.write_text(f"hello-{idx}\n", encoding="utf-8")

    # Human mode add + quiet mode
    code, out, _ = cli.run("file", "add", str(f_paths[0]), "--title", "Doc Zero", json_mode=False)
    assert code == 0
    assert "v1 (sha256:" in out

    f1 = cli.result("file", "add", str(f_paths[1]), "--title", "Doc One")
    f2 = cli.result(
        "file", "add", str(f_paths[2]), "--workspace", ws2, "--project", proj2, "--title", "Other WS"
    )
    v2_path = tmp_path / "doc-1-v2.txt"
    v2_path.write_text("hello-1-v2\n", encoding="utf-8")
    code, out, _ = cli.run("file", "version", f1["file_id"], str(v2_path), json_mode=False)
    assert code == 0
    assert "v2 (sha256:" in out

    # List pagination (--limit, --after, --all, --origin) in JSON and human mode
    p1 = cli.result("file", "list", "--limit", "1", "--origin", "upload")
    assert len(p1["items"]) == 1
    assert p1["next"] is not None
    p2 = cli.result("file", "list", "--limit", "1", "--after", p1["next"])
    assert len(p2["items"]) == 1
    all_ws1 = cli.result("file", "list", "--limit", "1", "--all")
    assert len(all_ws1["items"]) == 2
    assert all_ws1["next"] is None

    code, out, err = cli.run("file", "list", "--limit", "1", json_mode=False)
    assert code == 0
    assert "Doc One" in out or "Doc Zero" in out
    assert "more results are available" in err

    # Show in human mode (multi-line kv_lines + table, no escaped \n) and JSON mode
    code, show_h, _ = cli.run("file", "show", f1["file_id"], json_mode=False)
    assert code == 0
    assert "Doc One" in show_h
    assert "\\n" not in show_h
    assert len(show_h.strip().splitlines()) >= 12
    show_j = cli.result("file", "show", f1["file_id"])
    assert len(show_j["versions"]) == 2

    # Versions pagination in JSON and human mode
    vp1 = cli.result("file", "versions", f1["file_id"], "--limit", "1")
    assert len(vp1["items"]) == 1
    assert vp1["next"] is not None
    vp_all = cli.result("file", "versions", f1["file_id"], "--limit", "1", "--all")
    assert len(vp_all["items"]) == 2
    assert vp_all["next"] is None
    code, ver_h, _ = cli.run("file", "versions", f1["file_id"], json_mode=False)
    assert code == 0
    assert "doc-1-v2.txt" in ver_h

    # Scope mismatch checks (--workspace / --project)
    _, scope_err = cli.error("file", "show", f2["file_id"], "--workspace", cli.env["SKM_WORKSPACE"])
    assert scope_err["code"] == "NOT_FOUND"
    _, ws_proj_err = cli.error(
        "file", "add", str(f_paths[0]), "--workspace", cli.env["SKM_WORKSPACE"], "--project", proj2
    )
    assert ws_proj_err["code"] == "INVALID_REFERENCE"

    # Trash confirmation: non-TTY without --yes fails; TTY "y" succeeds; restore succeeds
    _, confirm_err = cli.error("file", "trash", f1["file_id"])
    assert confirm_err["code"] == "SCHEMA_INVALID"

    code, trash_h, _ = cli.run(
        "file", "trash", f1["file_id"], "--reason", "cleanup", json_mode=False, stdin=_TtyStringIO("y\n")
    )
    assert code == 0
    assert "trashed" in trash_h

    trashed_list = cli.result("file", "list", "--state", "trashed")
    assert [i["file_id"] for i in trashed_list["items"]] == [f1["file_id"]]
    all_states = cli.result("file", "list", "--state", "all")
    assert len(all_states["items"]) == 2

    code, rest_h, _ = cli.run(
        "file",
        "restore",
        f1["file_id"],
        "--expected-version",
        str(trashed_list["items"][0]["row_version"]),
        json_mode=False,
    )
    assert code == 0
    assert "restored" in rest_h


@pytest.mark.parametrize("via_host", [False, True])
def test_cli_upload_symlink_rejected(cli: Cli, tmp_path: Path, via_host: bool) -> None:
    cli.use_host_services = via_host
    # Point symlink at a FIFO so any illegal open without O_NOFOLLOW/lstat check would fail/block
    fifo = tmp_path / "never_open.fifo"
    os.mkfifo(fifo)
    sym = tmp_path / "evil-link.txt"
    sym.symlink_to(fifo)

    code, err = cli.error("file", "add", str(sym))
    assert code != 0
    assert err["code"] == "CONTENT_UNSAFE"
    assert err["details"]["findings"][0]["rule"] == "CS-SYMLINK"

    # Symlinked parent directory is also rejected as CS-SYMLINK without reading target
    real_dir = tmp_path / "real_dir"
    real_dir.mkdir()
    secret = real_dir / "secret.txt"
    secret.write_text("top-secret", encoding="utf-8")
    sym_dir = tmp_path / "sym_dir"
    sym_dir.symlink_to(real_dir)

    _, parent_err = cli.error("file", "add", str(sym_dir / "secret.txt"))
    assert parent_err["code"] == "CONTENT_UNSAFE"
    assert parent_err["details"]["findings"][0]["rule"] == "CS-SYMLINK"
    assert cli.result("file", "list")["items"] == []


def test_cli_classification_and_acknowledge(cli: Cli, tmp_path: Path) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        'api_key = "sk-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789"\n',
        encoding="utf-8",
    )

    # 1. Refused without --ack
    _, err_no_ack = cli.error("file", "add", str(env_file))
    assert err_no_ack["code"] == "CONTENT_UNSAFE"
    assert err_no_ack["details"]["reason"] == "not_acknowledged"
    rules = {f["rule"] for f in err_no_ack["details"]["findings"]}
    assert {"CS-SECRET-NAME", "CS-SECRET-CONTENT"} <= rules

    # 2. Refused with --ack when classification is below confidential floor
    _, err_floor = cli.error(
        "file",
        "add",
        str(env_file),
        "--classification",
        "internal",
        "--ack",
        "CS-SECRET-NAME",
        "--ack",
        "CS-SECRET-CONTENT",
    )
    assert err_floor["code"] == "CONTENT_UNSAFE"
    assert err_floor["details"]["reason"] == "classification_below_acknowledge_minimum"

    # 3. Admitted with --ack and --classification confidential
    admitted = cli.result(
        "file",
        "add",
        str(env_file),
        "--classification",
        "confidential",
        "--ack",
        "CS-SECRET-NAME",
        "--ack",
        "CS-SECRET-CONTENT",
    )
    assert admitted["classification"] == "confidential"
    assert set(admitted["safety"]["acknowledged"]) == {"CS-SECRET-CONTENT", "CS-SECRET-NAME"}
