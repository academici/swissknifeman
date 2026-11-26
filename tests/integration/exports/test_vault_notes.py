"""Drive the real client, bus, receipt ledger and host writer over memory and PostgreSQL."""

import json
from dataclasses import replace
from io import StringIO
from itertools import count
from pathlib import Path
from typing import cast, override
from unittest.mock import Mock
from uuid import UUID

import pytest

from contracts.execution.harness import PEPPER, ExecSide, exec_side
from contracts.exports.test_vault_ledger import (
    archive_and_queue,
    bound_host,
    knowledge_side,
    materialize_archive,
)
from contracts.knowledge.harness import KnowledgeSide
from integration.artifacts.test_upload_flow import dispatch_new
from security.api.harness import BASE, TestClient
from skm.adapters.exports.obsidian.vault_fs import LocalVaultFs
from skm.adapters.http_client.client import HttpSkmClient
from skm.application_bus.host import HostContext, HostServices
from skm.background.vault_push import VaultConfig, VaultPush
from skm.bootstrap.host_services import build_host_storage
from skm.bootstrap.worker import embedded_vault_client, run_vault_host
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routing import build_route_table
from skm.entrypoints.cli.main import Backend, main
from skm.kernel.actor import Actor
from skm.kernel.cancel import CancelSource, CancelToken
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import BackendUnavailable, SkmError
from skm.kernel.gateways import GatewayTable
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import authenticate_token
from skm.modules.exports.host import push_vault_notes
from skm.modules.exports.host.locate_vault import vault_settings
from skm.modules.exports.ports import VaultFs, VaultNoteRepository
from skm.modules.exports.public import RenderPlanMarkdown, RequeueNote
from skm.modules.exports.settings import SECTION_URNS, VALIDATORS, VIEWS
from skm.modules.workspace.public import BindCheckout, RegisterWorker, RegisterWorkerResult
from skm.platform.config.keys import MISSING
from skm.platform.config.registry import SettingsRegistry
from skm.platform.config.secrets import SecretRef, SecretValue
from skm.platform.schema.registry import SchemaRegistry
from support.pg import clean_test_database, pg_session, test_database


def _config(**overrides: object) -> dict[str, object]:
    registry = SettingsRegistry.build(
        SchemaRegistry.load_default(),
        SECTION_URNS,
        validators=VALIDATORS,
        views=VIEWS,
        known_permissions=frozenset(),
    )
    keys = registry.keys()
    return {
        **{key.key: key.default for key in keys if key.default is not MISSING},
        **overrides,
    }


__all__ = ["clean_test_database", "exec_side", "knowledge_side", "pg_session", "test_database"]


def test_worker_without_local_vault_input_reports_no_vault() -> None:
    with pytest.raises(SkmError) as caught:
        vault_settings({"exports.vault.push_interval_seconds": 120})
    assert caught.value.code is ErrorCode.EXPORT_VAULT_NOT_FOUND


def _compose(side: KnowledgeSide, tmp_path: Path) -> tuple[HostContext, LocalVaultFs]:
    host = bound_host(side)
    root = tmp_path / "vault"
    root.mkdir()
    fs = LocalVaultFs(root, tmp_path)
    client = embedded_vault_client(side.app, side.owner, Surface.CLI, host)
    ctx = HostContext(
        client,
        GatewayTable({VaultFs: fs}, "host_gateway"),
        host,
        VaultConfig(_config(**{"exports.vault.path": str(root)}), client.ask),
        Mock(),
        CancelSource().token,
    )
    run_vault_host(ctx, "exports.host.locate_vault", {"bind_writer": str(host)})
    return ctx, fs


def test_fork_and_requeue_preserve_receipt_history(knowledge_side: KnowledgeSide, tmp_path: Path) -> None:
    side = knowledge_side
    ctx, fs = _compose(side, tmp_path)
    note = archive_and_queue(side)
    request: JsonObject = {"workspace_id": str(side.workspace)}
    op = "exports.host.push_vault_notes"

    (created,) = cast("list[JsonObject]", run_vault_host(ctx, op, request)["created"])
    expected = fs.root / str(created["relative_path"])
    assert expected.read_bytes() == note.body.encode()
    assert run_vault_host(ctx, op, request)["created"] == []

    dispatch_new(ctx.client, RequeueNote(side.project, note.id, 1))
    (verified,) = cast("list[JsonObject]", run_vault_host(ctx, op, request)["verified_existing"])
    assert verified["generation"] == 2

    old_vault = fs.require_writer(ctx.host_id).vault_id
    identity = run_vault_host(ctx, "exports.host.locate_vault", {"fork_identity": True})
    assert identity["writer_host_id"] is None
    new_vault = UUID(str(identity["vault_id"]))
    assert new_vault != old_vault
    with pytest.raises(SkmError, match="writer binding"):
        run_vault_host(ctx, op, request)
    run_vault_host(ctx, "exports.host.locate_vault", {"bind_writer": str(ctx.host_id)})
    assert run_vault_host(ctx, op, request)["verified_existing"]
    with side.uow(readonly=True) as uow:
        writes = uow.repo(VaultNoteRepository).writes(note.id)
        assert {(w.vault_id, w.generation) for w in writes} == {
            (old_vault, 1),
            (old_vault, 2),
            (new_vault, 2),
        }

    expected.unlink()
    assert run_vault_host(ctx, op, request)["created"] == []
    assert not expected.exists()


class _Terminal(StringIO):
    @override
    def isatty(self) -> bool:
        return True


def test_cli_fork_requires_confirmation(knowledge_side: KnowledgeSide, tmp_path: Path) -> None:
    ctx, fs = _compose(knowledge_side, tmp_path)
    old_identity = fs.require_writer(ctx.host_id)
    command = ["export", "vault", "--project", str(knowledge_side.project), "--fork-identity"]

    def fork(stdin: StringIO, *flags: str) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        code = main(
            [*command, *flags],
            backend=lambda *_: Backend(ctx.client, host_factory=lambda: ctx),
            stdin=stdin,
            stdout=out,
            stderr=err,
        )
        return code, out.getvalue(), err.getvalue()

    for stdin in (StringIO("yes\n"), _Terminal("no\n")):
        code, out, err = fork(stdin)
        assert code != 0
        assert out == ""
        assert "Confirmation required" in err
        assert fs.read_identity() == old_identity
    code, out, err = fork(_Terminal("yes\n"))
    assert code == 0
    assert "Replace the vault UUID? [y/N]" in err
    assert (forked := fs.read_identity()) is not None
    assert forked.vault_id != old_identity.vault_id
    assert str(forked.vault_id) in out

    code, out, err = fork(StringIO(), "--yes")
    assert code == 0
    assert err == ""
    assert (confirmed := fs.read_identity()) is not None
    assert confirmed.vault_id != forked.vault_id
    assert str(confirmed.vault_id) in out


@pytest.mark.parametrize("as_json", [False, True])
def test_cli_vault_mapping_error_retains_diagnostic_report(
    knowledge_side: KnowledgeSide, tmp_path: Path, as_json: bool
) -> None:
    ctx, fs = _compose(knowledge_side, tmp_path)
    assert fs.create_new(".projects.json", b"broken")
    out, err = StringIO(), StringIO()
    code = main(
        ["export", "vault", "--project", str(knowledge_side.project), *(["--json"] if as_json else [])],
        backend=lambda *_: Backend(ctx.client, host_factory=lambda: ctx),
        stdin=StringIO(),
        stdout=out,
        stderr=err,
    )
    assert code == 6
    if as_json:
        problem = json.loads(out.getvalue())["error"]
        assert problem["code"] == "EXPORT_VAULT_PROJECT_UNKNOWN"
        assert problem["details"]["report"]["mapping_error"]["reason"] == "invalid_or_unreadable_mapping"
        assert err.getvalue() == ""
    else:
        assert out.getvalue() == ""
        assert err.getvalue().startswith("error: EXPORT_VAULT_PROJECT_UNKNOWN:")
        assert "invalid_or_unreadable_mapping" in err.getvalue()


def test_lost_ack_recovers_exact_key_even_after_requeue(
    knowledge_side: KnowledgeSide,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    side = knowledge_side
    ctx, fs = _compose(side, tmp_path)
    note = archive_and_queue(side)
    uncertain = Mock(wraps=ctx.client)
    calls: list[tuple[object, str]] = []

    def lose_response(command: object, *, idempotency_key: str) -> object:
        calls.append((command, idempotency_key))
        result = ctx.client.dispatch(command, idempotency_key=idempotency_key)
        if len(calls) == 1:
            raise BackendUnavailable(ErrorCode.BACKEND_UNAVAILABLE, "receipt response lost")
        return result

    uncertain.dispatch.side_effect = lose_response
    now = 1000.0
    monkeypatch.setattr(LocalVaultFs, "retry_time", lambda self: now)
    monkeypatch.setattr(LocalVaultFs, "retry_jitter", lambda self: 1.0)
    request: JsonObject = {"workspace_id": str(side.workspace)}
    restarted = replace(ctx, client=uncertain)
    first = push_vault_notes.run(restarted, request)
    assert first["errors"]
    assert first["created"] == []
    dispatch_new(ctx.client, RequeueNote(side.project, note.id, 1))
    now += 31
    second = push_vault_notes.run(restarted, request)
    (verified,) = cast("list[JsonObject]", second["verified_existing"])
    assert verified["generation"] == 2
    assert calls[-1] == calls[0]
    with side.uow(readonly=True) as uow:
        assert len(uow.repo(VaultNoteRepository).writes(note.id)) == 2
    assert b'"entries":{}' in next(fs.state().root.glob("*.journal")).read_bytes()


def test_http_worker_delivery_authorization_and_markdown(
    exec_side: ExecSide,
    tmp_path: Path,
) -> None:
    side = exec_side
    dispatch_new(
        side.client,
        BindCheckout(
            side.repo_id,
            side.host1,
            "/opt/checkout",
            "/opt/checkout",
            ("example.invalid/skm",),
            None,
            False,
            side.clock.now(),
        ),
    )
    worker = cast(
        "RegisterWorkerResult",
        side.client.dispatch(
            RegisterWorker.from_json(
                {
                    "workspace_id": str(side.ws),
                    "host_id": str(side.host1),
                    "display_name": "vault writer",
                    "capabilities": {
                        "platform": {"os": "linux", "arch": "x86_64"},
                        "runtimes": [],
                        "isolation_profiles": ["worktree"],
                        "max_concurrency": 1,
                        "labels": [],
                        "skm_version": "2.0.0",
                    },
                }
            )
        ),
    )

    def authenticate(secret: str) -> Actor:
        with side.uow(readonly=True) as uow:
            return authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())

    routes = build_route_table(("exports", "access", "settings", "workspace"))
    api = create_app(
        replace(side.app, authenticator=authenticate),
        route_table=routes,
        registry=side.app.bus._registry,
        no_background=True,
    )
    root = tmp_path / "vault"
    root.mkdir()
    fs = LocalVaultFs(root, tmp_path)
    fs.update_identity(side.host1, fork=False, deadline_seconds=1)
    config = _config(**{"exports.vault.path": str(root)})
    with TestClient(api, base_url=BASE) as http:
        client = HttpSkmClient(
            BASE,
            SecretValue(SecretRef.parse("secret://env/TEST_TOKEN"), worker.token_secret),
            routes,
            http=http,
            spool_root=tmp_path / "uploads",
            storage_budget=build_host_storage(tmp_path),
            min_free_bytes=0,
            host_id=side.host1,
        )
        rendered = cast("JsonObject", client.ask(RenderPlanMarkdown(side.plan1, 1)))
        assert "Verify Phase-A/B/C" in str(rendered["markdown"])
        output = StringIO()
        assert (
            main(
                ["export", "plan", str(side.plan1), "--revision", "1", "--json"],
                backend=lambda *_: Backend(client),
                stdout=output,
                stderr=StringIO(),
            )
            == 0
        ), output.getvalue()
        assert "Verify Phase-A/B/C" in output.getvalue()
        note = materialize_archive(
            KnowledgeSide(side.kind, side.app, side.clock, side.owner, side.ws, side.proj, count()),
            side.plan1,
        )
        host = HostServices(
            side.host1,
            Surface.WORKER,
            GatewayTable({VaultFs: fs}, "host_gateway"),
            lambda: VaultConfig(config, client.ask),
            {},
        )

        def push(workspace: UUID, cancel: CancelToken) -> JsonObject:
            return push_vault_notes.run(
                host.context(client=client, cancel=cancel, log=Mock()), {"workspace_id": str(workspace)}
            )

        service = VaultPush(client.ask, push, interval=300, log=Mock())
        try:
            assert service.tick().processed == 1
        finally:
            service.close()
        assert (root / "SKM" / "Unsorted" / note.name).read_bytes() == note.body.encode()
        with pytest.raises(SkmError) as denied:
            client.dispatch(RequeueNote(side.proj, note.id, 1), idempotency_key=client.new_idempotency_key())
        assert denied.value.code == ErrorCode.FORBIDDEN
