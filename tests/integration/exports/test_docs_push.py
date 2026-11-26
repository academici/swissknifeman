"""Check the wire representation against the export CLI and the disabled-module response."""

import json
from dataclasses import replace
from hashlib import sha256
from io import StringIO
from pathlib import Path
from typing import Any, cast

import pytest

from contracts.execution.harness import PEPPER, ExecSide, _publish_revision, exec_side
from contracts.execution.seed_helpers import seed_bundle, seed_run
from contracts.knowledge.harness import KnowledgeSide, knowledge_side
from integration.artifacts.test_upload_flow import dispatch_new
from integration.exports.test_vault_notes import _compose
from security.api.harness import BASE, TestClient
from skm.adapters.exports.obsidian.vault_fs import LocalVaultFs
from skm.application_bus.host import HostServices
from skm.application_bus.registry import BusRegistry
from skm.background.vault_push import export_settings
from skm.bootstrap.worker import run_vault_host
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routing import build_route_table
from skm.entrypoints.cli import main as cli
from skm.entrypoints.cli.main import Backend, main
from skm.kernel.actor import Actor
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import CreateToken, authenticate_token
from skm.modules.exports.module import MODULE
from skm.modules.workspace.public import BindCheckout, GetProject, ProjectView
from skm.platform.config.bootstrap import BOOTSTRAP_URN
from skm.platform.schema.registry import SchemaRegistry
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "exec_side", "knowledge_side", "pg_session", "test_database"]


def http_client(side: ExecSide, *, disabled: bool = False) -> TestClient:
    token = cast("Any", side.client.dispatch(CreateToken(name="download")))

    def authenticate(secret: str) -> Actor:
        with side.uow(readonly=True) as uow:
            return authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())

    registry = (
        BusRegistry.build(
            (MODULE,),
            schemas=SchemaRegistry.load_default(),
            permission_catalog=frozenset(),
            disabled_modules=frozenset({"exports"}),
        )
        if disabled
        else side.app.bus._registry
    )
    api = create_app(
        replace(side.app, authenticator=authenticate),
        route_table=build_route_table(("exports",)),
        registry=registry,
        no_background=True,
    )
    return TestClient(api, base_url=BASE, headers={"Authorization": f"Bearer {token.secret}"})


@pytest.mark.parametrize("verb", ["plan", "run"])
def test_markdown_downloads_match_cli_stdout_and_files_with_terminal_controls(
    exec_side: ExecSide, tmp_path: Path, verb: str
) -> None:
    side = exec_side
    revision = _publish_revision(
        side.app, side.client, side.owner, side.clock, side.plan1, {"title": "Café\x01report"}, "current"
    )
    with side.uow() as uow:
        run = seed_run(side, uow, rev_id=revision, revision_no=3)
        seed_bundle(side, uow, run.id)
        uow.commit()
    with http_client(exec_side) as http:
        identifier, suffix, query, args = (
            (side.plan1, "export.md", "revision_no=3", ["--revision", "3"])
            if verb == "plan"
            else (run.id, "report.md", "variant=summary", ["--summary"])
        )
        url = f"/api/v1/{verb}s/{identifier}/{suffix}?{query}"
        response = http.get(url)
        assert response.status_code == 200, response.text
        assert response.headers["Content-Type"] == "text/markdown; charset=utf-8"
        assert b"\x01" not in response.content
        assert "Café\\x01report".encode() in response.content
        digest = "sha256:" + sha256(response.content).hexdigest()
        assert response.headers["ETag"] == f'"{digest}"'
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        cached = http.get(url, headers={"If-None-Match": response.headers["ETag"]})
        assert cached.status_code == 304
        assert cached.content == b""
        assert cached.headers["ETag"] == response.headers["ETag"]

        stdout = StringIO()
        assert (
            main(
                ["export", verb, str(identifier), *args],
                backend=lambda *_: Backend(side.client),
                stdout=stdout,
                stderr=StringIO(),
            )
            == 0
        )
        assert stdout.getvalue().encode("utf-8") == response.content

        path = tmp_path / suffix
        output = StringIO()
        assert (
            main(
                ["export", verb, str(identifier), *args, "-o", str(path), "--json"],
                backend=lambda *_: Backend(side.client),
                stdout=output,
                stderr=StringIO(),
            )
            == 0
        )
        assert path.read_bytes() == response.content
        assert json.loads(output.getvalue())["result"]["digest"] == digest
        assert response.headers.get("Content-Disposition", "").split(";", 1)[0] == "attachment"


def test_disabled_exports_cannot_return_cached_markdown(exec_side: ExecSide) -> None:
    with http_client(exec_side, disabled=True) as http:
        for url in (f"plans/{exec_side.plan1}/export.md", f"runs/{exec_side.new_id()}/report.md"):
            response = http.get(f"/api/v1/{url}", headers={"If-None-Match": "*"})
            assert response.status_code == 409
            assert response.json()["code"] == "MODULE_DISABLED"


def test_host_admission_and_empty_selection_on_bound_checkout(
    knowledge_side: KnowledgeSide, tmp_path: Path
) -> None:
    ctx, fs = _compose(knowledge_side, tmp_path)
    op = "exports.host.push_vault_docs"
    project = cast("ProjectView", ctx.client.ask(GetProject(knowledge_side.project)))
    args: JsonObject = {"project_id": str(project.project_id), "patterns": [], "dry_run": True}
    with pytest.raises(SkmError) as missing:
        run_vault_host(ctx, op, args)
    assert missing.value.code == ErrorCode.EXPORT_VAULT_PROJECT_UNKNOWN
    fs.write_atomic(
        ".projects.json",
        json.dumps(
            {
                "projects": [
                    {"skm_project": project.slug, "vault_path": "Project"},
                ]
            }
        ).encode(),
        replace=True,
    )
    result = run_vault_host(ctx, op, args)
    assert result["partial"] is False
    assert result["totals"] == {"copied": 0, "identical": 0, "conflicts": 0, "refused": 0}
    assert not (fs.state().root / "docs").exists()


def test_embedded_cli_reads_bound_checkout_and_prunes_protected_roots(
    exec_side: ExecSide, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    side = exec_side
    checkout = tmp_path / "checkout"
    state, blobs, backups, materialized, vault = (
        checkout / name for name in ("state", "blobs", "backups", "materialized", "vault")
    )
    for root in (state, blobs, backups, materialized, vault):
        root.mkdir(parents=True)
        (root / "private.md").write_bytes(b"protected bytes")
    data = "héritage\n".encode()
    (checkout / "README.md").write_bytes(data)
    (vault / ".projects.json").write_text('{"projects":[{"skm_project":"skm","vault_path":"Project"}]}')
    LocalVaultFs(vault, state).update_identity(side.host1, fork=False, deadline_seconds=10)
    dispatch_new(
        side.client,
        BindCheckout(
            side.repo_id,
            side.host1,
            str(checkout),
            str(checkout),
            ("example.invalid/skm",),
            None,
            False,
            side.clock.now(),
        ),
    )

    bootstrap = tmp_path / "bootstrap.toml"
    bootstrap.write_text(
        f'schema = "{BOOTSTRAP_URN}"\ninstance_id = "{side.app.instance_id}"\n'
        '[access]\nmode = "embedded"\n[database]\nurl = "secret://env/SKM_DATABASE_URL"\n'
        f'[paths]\nstate_dir = "{state}"\nblobs_root = "{blobs}"\n'
        f'backups_root = "{backups}"\nmaterialized_root = "{materialized}"\n',
        encoding="utf-8",
    )
    host = HostServices(
        side.host1,
        Surface.CLI,
        GatewayTable({}, "host_gateway"),
        lambda: {**export_settings(side.client.ask, "host", side.host1), "exports.vault.path": str(vault)},
        {},
    )
    app = replace(side.app, host=host, closers=(), closed=[False])
    monkeypatch.setattr(cli, "open_cli_app", lambda *_args, **_kwargs: (app, side.owner))
    output, errors = StringIO(), StringIO()
    status = main(
        [
            "-vv",
            "--bootstrap",
            str(bootstrap),
            "export",
            "docs-push",
            "--project",
            str(side.proj),
            "--mount",
            "repo",
            "--pattern",
            "**",
            "--force",
        ],
        environ={"HOME": str(tmp_path)},
        stdout=output,
        stderr=errors,
    )
    assert status == 0, errors.getvalue()
    target = vault / "Project" / "Docs"
    assert list(target.iterdir()) == [target / "README.md"]
    assert (target / "README.md").read_bytes() == data
    assert sha256(data).hexdigest() in output.getvalue()
    assert "protected bytes" not in output.getvalue()
