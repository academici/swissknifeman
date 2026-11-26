"""Integration tests for ``skm project config pull|push|watch`` (CAS + I-10.1c project SSE)."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any, cast

import httpx
import pytest

from security.api.harness import BASE, TestClient, make_world
from skm.adapters.http_client.client import HttpSkmClient
from skm.bootstrap.host_services import build_host_storage
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.entrypoints.cli.context import CliOptions, CliRedactor, CliSession
from skm.entrypoints.cli.parser import build_parser
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, ValidationFailed
from skm.kernel.ids import WorkspaceId
from skm.kernel.ports_uow import Surface
from skm.modules.settings import public as settings
from skm.modules.workspace import public as workspace
from skm.platform.config.secrets import SecretRef, SecretValue
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator


def _run_cli(
    client: Any, argv: list[str], *, json_output: bool = True, assume_yes: bool = True
) -> tuple[int, str]:
    parser = build_parser()
    args = parser.parse_args(argv)
    stdout = io.StringIO()
    stderr = io.StringIO()
    ctx = CliSession(
        options=CliOptions(json=json_output, quiet=False, assume_yes=assume_yes),
        stdout=stdout,
        stderr=stderr,
        redactor=CliRedactor(),
        ids=Uuid7Generator(SystemClock()),
        request_id="req-cli-test",
        client_=client,
    )
    code = args.run(args, ctx)
    return code, stdout.getvalue()


def _seed_project(client: Any) -> tuple[str, str]:
    ws = cast(
        "workspace.CreateWorkspaceResult",
        client.dispatch(
            workspace.CreateWorkspace(slug="cfg-ws", title="Config Workspace"),
            idempotency_key=client.new_idempotency_key(),
        ),
    )
    proj = cast(
        "workspace.CreateProjectResult",
        client.dispatch(
            workspace.CreateProject(
                workspace_id=WorkspaceId(ws.workspace_id), slug="cfg-proj", title="Config Project"
            ),
            idempotency_key=client.new_idempotency_key(),
        ),
    )
    return str(ws.workspace_id), str(proj.project_id)


def test_project_config_pull_and_push_with_cas(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    try:
        actor = world.core.authenticate(world.secret)
        client = world.core.client(actor=actor, surface=Surface.CLI)
        _, project_id = _seed_project(client)

        cfg_file = tmp_path / "project-config.json"
        code, out = _run_cli(
            client,
            ["project", "config", "pull", project_id, "--file", str(cfg_file), "--format", "json", "--json"],
        )
        assert code == 0
        pulled = json.loads(out)
        digest_v1 = pulled["result"]["digest"]
        assert cfg_file.exists()

        # Pushing without --expect-digest or --force must fail CAS check
        doc = json.loads(cfg_file.read_text(encoding="utf-8"))
        doc["execution"] = {"review": {"max_rounds": 2}}
        cfg_file.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(ValidationFailed) as missing_cas:
            _run_cli(
                client,
                ["project", "config", "push", str(cfg_file), "--project", project_id, "--yes", "--json"],
            )
        assert missing_cas.value.code is ErrorCode.SCHEMA_INVALID
        assert missing_cas.value.details.get("reason") == "cas_digest_required"

        # Push with matching CAS digest succeeds
        code, out = _run_cli(
            client,
            [
                "project",
                "config",
                "push",
                str(cfg_file),
                "--project",
                project_id,
                "--expect-digest",
                digest_v1,
                "--reason",
                "cli push",
                "--yes",
                "--json",
            ],
        )
        assert code == 0
        pushed = json.loads(out)["result"]
        assert pushed["applied"] is True
        digest_v2 = pushed["entries_digest_after"]
        assert digest_v2 != digest_v1

        # Pushing again with stale digest_v1 must fail with VERSION_CONFLICT
        doc["execution"] = {"review": {"max_rounds": 1}}
        cfg_file.write_text(json.dumps(doc), encoding="utf-8")
        with pytest.raises(Conflict) as exc_info:
            _run_cli(
                client,
                [
                    "project",
                    "config",
                    "push",
                    str(cfg_file),
                    "--project",
                    project_id,
                    "--expect-digest",
                    digest_v1,
                    "--yes",
                    "--json",
                ],
            )
        assert exc_info.value.code is ErrorCode.VERSION_CONFLICT

        # Dry-run with current digest_v2 previews without writing
        code, out = _run_cli(
            client,
            [
                "project",
                "config",
                "push",
                str(cfg_file),
                "--project",
                project_id,
                "--expect-digest",
                digest_v2,
                "--dry-run",
                "--yes",
                "--json",
            ],
        )
        assert code == 0
        preview = json.loads(out)["result"]
        assert preview["dry_run"] is True
        assert preview["applied"] is False

        # Explicit --force bypasses CAS check
        code, out = _run_cli(
            client,
            [
                "project",
                "config",
                "push",
                str(cfg_file),
                "--project",
                project_id,
                "--force",
                "--yes",
                "--json",
            ],
        )
        assert code == 0
        assert json.loads(out)["result"]["applied"] is True
    finally:
        world.core.close()


def test_project_config_watch_uses_project_sse_endpoint_and_updates_file(tmp_path: Path) -> None:
    world = make_world(tmp_path)
    try:
        api = create_app(
            world.core,
            route_table=build_route_table(MODULE_IDS),
            registry=world.core.bus._registry,
            no_background=True,
        )
        seen_paths: list[str] = []

        with TestClient(api, base_url=BASE) as test_http:
            orig_send = test_http.send

            def recording_send(request: httpx.Request, *args: Any, **kwargs: Any) -> httpx.Response:
                seen_paths.append(request.url.path)
                if request.url.path.endswith("/events/stream") and seen_paths.count(request.url.path) == 1:
                    raise httpx.ConnectError("disconnected")
                return orig_send(request, *args, **kwargs)

            test_http.send = recording_send
            http_client = HttpSkmClient(
                BASE,
                SecretValue(SecretRef.parse("secret://env/SKM_TEST_TOKEN"), world.secret),
                build_route_table(MODULE_IDS),
                spool_root=tmp_path / "spool",
                storage_budget=build_host_storage(tmp_path / "budget"),
                min_free_bytes=0,
                http=test_http,
                timeout_seconds=5,
                sleeper=lambda _: None,
            )
            _, project_id = _seed_project(http_client)

            for rounds in (2, 1):
                http_client.dispatch(
                    settings.ImportConfig.from_json(
                        {
                            "scope": {"level": "project", "scope_id": project_id},
                            "format": "json",
                            "document": {
                                "schema": "urn:skm:settings:document:v1",
                                "execution": {"review": {"max_rounds": rounds}},
                            },
                            "mode": "merge",
                            "reason": "trigger sse",
                            "confirmed": True,
                        }
                    ),
                    idempotency_key=http_client.new_idempotency_key(),
                )

            out_file = tmp_path / "watched.json"
            code, out = _run_cli(
                http_client,
                [
                    "project",
                    "config",
                    "watch",
                    project_id,
                    "--after",
                    "0",
                    "--wait",
                    "0",
                    "--file",
                    str(out_file),
                    "--format",
                    "json",
                    "--json",
                ],
            )
            assert code == 0
            assert seen_paths.count(f"/api/v1/projects/{project_id}/events/stream") == 2
            lines = [json.loads(line) for line in out.strip().splitlines() if line.strip()]
            assert len(lines) == 2
            assert lines[0]["seq"] < lines[1]["seq"]
            for event in lines:
                assert event["type"] == "urn:skm:settings:event:config-changed:v1"
                assert event["project_id"] == project_id
                assert event["digest"] is not None
            synced = json.loads(out_file.read_text(encoding="utf-8"))
            assert synced["execution"]["review"]["max_rounds"] == 1
    finally:
        world.core.close()
