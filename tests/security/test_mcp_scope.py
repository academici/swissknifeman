"""MCP discovery, project binding and live authorization (S23/SURFACE-02)."""

from pathlib import Path
from typing import cast

import pytest

from contracts.execution.harness import ExecSide
from contracts.execution.harness import exec_side as exec_side
from contracts.execution.test_step_notes import owned_agent
from integration.api.test_worker_protocol import worker_api
from integration.api.test_worker_protocol import worker_side as worker_side
from integration.mcp.test_protocol import call, content, exchange, request
from integration.mcp.test_session import _http
from security.api.harness import BASE, TestClient
from security.test_blob_access import assert_private_output, denial_checks
from security.test_cross_project_assignment import FOREIGN_RESULT, foreign_run_step
from skm.entrypoints.api.routing import build_route_table
from skm.entrypoints.mcp.protocol import INVALID_PARAMS
from skm.entrypoints.mcp.session import McpSession
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, PreconditionFailed
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access
from skm.modules.execution.ports import StepRepository
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

SCHEMAS = ("access", "artifacts", "execution", "knowledge", "planning", "workspace")
MODULES = ("access", "settings", "workspace", "artifacts", "context", "execution")


def test_session_ignores_missing_context_instead_of_choosing_an_arbitrary_project(
    exec_side: ExecSide, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    side = exec_side
    token = cast(
        "access.CreateTokenResult",
        side.client.dispatch(access.CreateToken("project discovery", permissions=("project.read",))),
    )
    with side.uow(readonly=True) as uow:
        actor = access.authenticate_token(
            uow,
            token.secret,
            pepper=side.app.gateways.get(access.TokenPepperSource).pepper(),
            now=side.clock.now(),
        )
    client = side.app.client(actor=actor, surface=Surface.MCP)
    with denial_checks(
        side.app,
        tmp_path,
        dsn=side.dsn,
        schemas=SCHEMAS,
        capsys=capsys,
        private=(token.secret, str(side.proj), str(side.proj2)),
    ) as check:
        with pytest.raises(PreconditionFailed) as caught:
            McpSession.open(
                client, cli_context_path=tmp_path / "missing.json", instance_id=side.app.instance_id
            )
        check((caught.value, caught.value.details))
    assert caught.value.code is ErrorCode.NO_PROJECT_SCOPE


def test_assignment_mcp_hides_writes_and_checks_live_credentials_on_each_call(
    worker_side: tuple[ExecSide, dict[str, str], dict[str, str]],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    side, worker, owner = worker_side
    run, _, _, _, _, step, runtime, token, secret = owned_agent(side)
    other_run, other_task, other_step = foreign_run_step(side)
    assert other_run.id != run.id
    assert other_run.workspace_id == run.workspace_id
    private = "private-mcp-write-probe-8159"
    markers = (
        private,
        FOREIGN_RESULT,
        "Secret Plan",
        secret,
        worker["Authorization"][7:],
        owner["Authorization"][7:],
    )
    with TestClient(worker_api(side), base_url=BASE) as transport:
        remote = _http(secret, transport, build_route_table(MODULES), tmp_path / "host")
        sessions = (McpSession.open(runtime), McpSession.open(remote))
        assert all((s.project_id, s.run_id, s.step_id) == (side.proj, run.id, step.id) for s in sessions)
        writes: tuple[tuple[str, JsonObject], ...] = (
            ("skm_memory_remember", {"key": "context", "text": private}),
            (
                "skm_plan_draft_open",
                {"plan": str(side.plan1), "base": "current", "idempotency_key": "hidden-open"},
            ),
            (
                "skm_plan_publish",
                {
                    "plan": str(side.plan1),
                    "idempotency_key": "hidden-publish",
                    "draft_id": str(side.new_id()),
                    "expected_edit_version": 1,
                    "expected_content_digest": "sha256:" + "a" * 64,
                    "reason": private,
                },
            ),
        )
        for session, client in zip(sessions, (runtime, remote), strict=True):
            with denial_checks(
                side.app,
                tmp_path,
                dsn=side.dsn,
                schemas=SCHEMAS,
                capsys=capsys,
                private=markers,
                audit=("workspace.get_project",),
            ) as check:
                with pytest.raises(Forbidden) as caught:
                    McpSession.open(client, project_id=side.proj2)
                check((caught.value, caught.value.details))
            with denial_checks(
                side.app,
                tmp_path,
                dsn=side.dsn,
                schemas=SCHEMAS,
                capsys=capsys,
                private=markers,
            ) as check:
                [listed] = exchange(session, [request("tools/list")])
                check(listed)
            names = {tool["name"] for tool in listed["result"]["tools"]}
            assert {"skm_plan_list", "skm_record_note"} <= names
            assert not names.intersection(name for name, _ in writes)
            for name, arguments in writes:
                with denial_checks(
                    side.app,
                    tmp_path,
                    dsn=side.dsn,
                    schemas=SCHEMAS,
                    capsys=capsys,
                    private=markers,
                ) as check:
                    [denied] = exchange(session, [call(name, arguments)])
                    check(denied)
                assert denied["result"]["isError"] is True
                assert content(denied)["error"]["code"] == "FORBIDDEN"
            [read] = exchange(session, [call("skm_run_status", {"run": str(run.id)})])
            assert read["result"]["isError"] is False, content(read)
            assert content(read)["run_id"] == str(run.id)

            read_probes: tuple[tuple[str, JsonObject], ...] = (
                ("skm_run_history", {"run": str(other_run.id)}),
                ("skm_task_context", {"task": str(other_task.id)}),
            )
            for tool, arguments in read_probes:
                with denial_checks(
                    side.app,
                    tmp_path,
                    dsn=side.dsn,
                    schemas=SCHEMAS,
                    capsys=capsys,
                    private=markers,
                ) as check:
                    [denied] = exchange(session, [call(tool, arguments)])
                    check(denied)
                assert denied["result"]["isError"] is True
                assert content(denied)["error"]["code"] == "NOT_FOUND"
                assert_private_output(denied, str(other_run.id), str(other_step.id), str(other_task.id))

            with denial_checks(
                side.app,
                tmp_path,
                dsn=side.dsn,
                schemas=SCHEMAS,
                capsys=capsys,
                private=markers,
            ) as check:
                [denied] = exchange(
                    session,
                    [
                        call(
                            "skm_record_note",
                            {
                                "kind": "progress",
                                "text": private,
                                "step_id": str(other_step.id),
                            },
                        )
                    ],
                )
                check(denied)
            assert denied["error"]["code"] == INVALID_PARAMS
            assert "result" not in denied
            assert_private_output(denied, str(other_run.id), str(other_step.id))

        side.client.dispatch(access.RevokeToken(token_id=token.token_id))
        for session in sessions:
            with denial_checks(
                side.app,
                tmp_path,
                dsn=side.dsn,
                schemas=SCHEMAS,
                capsys=capsys,
                private=markers,
            ) as check:
                [denied] = exchange(session, [call("skm_record_note", {"kind": "progress", "text": private})])
                check(denied)
            assert denied["result"]["isError"] is True
            assert content(denied)["error"]["code"] == "UNAUTHENTICATED"
            assert "note_id" not in content(denied)
    with side.uow(readonly=True) as uow:
        for item in (step, other_step):
            assert not uow.repo(StepRepository).notes_for_step(item.id)
