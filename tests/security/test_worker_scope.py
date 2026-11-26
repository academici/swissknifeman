"""Worker workspace scope, assignment authority, handler isolation and secret confinement (K17)."""

from __future__ import annotations

import ast
from dataclasses import fields
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from contracts.execution._worker_protocol_support import make_case
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.test_step_notes import owned_agent
from integration.worker._support import make_host, result_scenario
from skm.kernel.errors import SkmError
from skm.kernel.ids import AttemptId, WorkerId, WorkspaceId
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import RotateToken
from skm.modules.execution import public as execution
from skm.modules.execution.domain.ids import AssignmentId
from skm.modules.execution.domain.lease import WorkerClaim
from skm.modules.execution.host.context import build_stage_deps
from skm.modules.execution.host.stage_client import BoundStageClient
from skm.modules.execution.host.worker_loop import run
from skm.modules.execution.ports import StageDeps
from skm.platform.logging.redaction import MASK
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "exec_side", "pg_session", "test_database"]


def test_handler_dependencies_have_no_host_client_or_database_capability(tmp_path, monkeypatch):
    fixture = make_host(tmp_path, monkeypatch)
    claim = WorkerClaim(
        AssignmentId(UUID(fixture.ids["assignment"])),
        AttemptId(UUID(fixture.ids["attempt"])),
        WorkerId(UUID(fixture.ids["worker"])),
        1,
    )
    deps = build_stage_deps(
        fixture.ctx, claim, fixture.environment, workspace_id=WorkspaceId(UUID(fixture.ids["workspace"]))
    )
    assert {f.name for f in fields(StageDeps)}.isdisjoint({"ctx", "host", "client", "uow", "gateways"})
    assert not hasattr(deps.worker, "client")
    assert not hasattr(deps.uploader, "ctx")
    assert not hasattr(deps.uploader, "client")
    for method in (
        "dispatch",
        "ask",
        "claim_assignment",
        "begin_stage",
        "record_stage_result",
        "release_assignment",
        "report_attempt_failure",
    ):
        assert not hasattr(BoundStageClient, method)
    for path in (Path(__file__).resolve().parents[2] / "src/skm/modules/execution/host/stages").glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert not (node.module or "").startswith("skm.application_bus")
                assert ".application" not in (node.module or "")
            assert not (isinstance(node, ast.Attribute) and node.attr in {"client", "uow"})


def test_worker_cannot_claim_another_workspace(exec_side):
    side = exec_side
    make_case(side)
    with pytest.raises(SkmError) as caught:
        side.worker1_client.dispatch(
            execution.ClaimAssignment(
                worker_id=str(side.worker1),
                host_id=str(side.host1),
                workspace_id=str(uuid4()),
                offer={
                    "capabilities": [],
                    "labels": [],
                    "environment_kinds": ["git_worktree"],
                    "isolation_profiles": [],
                },
            ),
            idempotency_key=f"scope:{side.new_id()}",
        )
    assert caught.value.code.value in {"FORBIDDEN", "NOT_FOUND"}


def test_assignment_token_cannot_authorize_worker_management_or_rotation(exec_side):
    side = exec_side
    _, _, _, claimed, _, _, runtime, token, _ = owned_agent(side)
    client = side.app.client(actor=runtime._actor, surface=Surface.WORKER)
    for command in (
        execution.ClaimAssignment(
            worker_id=str(side.worker1),
            host_id=str(side.host1),
            workspace_id=str(side.ws),
            offer={"capabilities": [], "labels": [], "environment_kinds": [], "isolation_profiles": []},
        ),
        execution.RenewLease(
            claim={
                "assignment_id": claimed["assignment_id"],
                "attempt_id": claimed["attempt_id"],
                "worker_id": str(side.worker1),
                "fencing_token": claimed["fencing_token"],
            }
        ),
        RotateToken(UUID(str(token.token_id))),
    ):
        with pytest.raises(SkmError) as caught:
            client.dispatch(
                command,
                idempotency_key=None
                if isinstance(command, RotateToken)
                else f"runtime-management:{side.new_id()}",
            )
        assert caught.value.code.value in {"FORBIDDEN", "UNAUTHENTICATED"}


def test_runtime_echoed_secret_is_redacted_in_raw_evidence_and_result(tmp_path, monkeypatch, caplog):
    doc = {
        "schema": "urn:skm:execution:role-result:triager:v1",
        "confirmed": [],
        "rejected": [],
        "summary": "safe fixture",
    }
    fixture = make_host(tmp_path, monkeypatch, scenario=result_scenario(tmp_path, "triager", doc))
    original = fixture.runtime.result
    secrets = []
    start = fixture.runtime.start

    def remember(request):
        begin = next(command for command, _ in fixture.client.calls if command["operation"] == "begin_stage")
        secrets.append(begin["runtime_token_secret"])
        assert request.secret_env == {}
        assert "SKM_TOKEN" not in request.extra_env
        assert "SKM_TOKEN" not in request.env_allowlist
        assert secrets[-1] not in repr(request)
        return start(request)

    def echo(handle):
        import json
        from dataclasses import replace

        result = original(handle)
        document = {**doc, "summary": secrets[-1]}
        return replace(result, structured=document, final_text=json.dumps(document))

    monkeypatch.setattr(fixture.runtime, "start", remember)
    monkeypatch.setattr(fixture.runtime, "result", echo)
    run(fixture.ctx, fixture.request)
    recorded = next(c for c, _ in fixture.client.calls if c["operation"] == "record_stage_result")
    assert recorded["outcome"]["role_result"]["summary"] == MASK
    raw = next(fixture.services.state_dir.rglob("raw.json"))
    assert MASK in raw.read_text()
    assert secrets[0] not in repr(recorded)
    assert secrets[0] not in caplog.text
    assert all(
        secrets[0].encode() not in p.read_bytes()
        for p in fixture.services.state_dir.rglob("*")
        if p.is_file()
    )


def test_worker_host_operations_enforce_surface_whitelist(tmp_path, monkeypatch):
    from skm.bootstrap.host_services import build_host_services
    from skm.kernel.module_manifest import HostOperationSpec

    fixture = make_host(tmp_path, monkeypatch)
    worker_op = HostOperationSpec(
        "execution.host.worker_test", lambda *_: {"ok": True}, dict, dict, frozenset({Surface.WORKER})
    )
    cli_op = HostOperationSpec(
        "execution.host.cli_test",
        lambda *_: pytest.fail("CLI op ran on WORKER"),
        dict,
        dict,
        frozenset({Surface.CLI}),
    )
    services = build_host_services(
        {"host": {"id": str(fixture.ctx.host_id)}},
        client=fixture.client,
        plugins=(),
        environ={},
        surface=Surface.WORKER,
        host_config=lambda: fixture.ctx.config,
        gateways=fixture.entries,
        operations=(worker_op, cli_op),
        worker_services=fixture.services,
    )
    assert services.run(worker_op.name, {}, client=fixture.client, cancel=fixture.ctx.cancel) == {"ok": True}
    assert cli_op.name not in services.operations
    services.operations = {cli_op.name: cli_op}
    with pytest.raises(SkmError) as caught:
        services.run(cli_op.name, {}, client=fixture.client, cancel=fixture.ctx.cancel)
    assert caught.value.code.value == "FORBIDDEN"
