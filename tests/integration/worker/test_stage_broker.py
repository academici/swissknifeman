"""The actual child MCP transport uses a local channel and the current fenced assignment."""

from __future__ import annotations

import json
import socket
import sys
from contextlib import ExitStack, nullcontext, suppress
from dataclasses import replace
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest

from contracts.execution._client_execution import (
    begin_command,
    configure_execution,
    prepare_agent_request,
    register_worker,
    schedule,
    start_run_command,
)
from contracts.execution.test_client_worker_protocol import worker_plan
from integration.artifacts.test_upload_flow import dispatch_new
from skm.adapters.runtimes.fake.runtime import FakeRuntime
from skm.application_bus.host import HostContext, HostServices
from skm.bootstrap.host_services import build_worker_services
from skm.bootstrap.stage_broker import bind_stage_broker
from skm.entrypoints.mcp.server import serve_stage
from skm.kernel.cancel import CancelSource
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import AttemptId, HostId, WorkerId
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import generate_secret
from skm.modules.execution import public as execution
from skm.modules.execution.domain.ids import AssignmentId
from skm.modules.execution.domain.lease import WorkerClaim
from skm.modules.execution.host.context import WorkerServices
from skm.modules.execution.host.stages.registry import StageRegistry
from skm.modules.execution.host.worker_loop import _bind_stage_tools
from skm.modules.execution.ports import AssignmentRepository, StageDeps
from skm.modules.runtimes.public import ProcessOwnership, SecretStr, SessionHandle
from skm.modules.settings.public import SetValue
from skm.platform.process.runner import ProcessHandle, spawn
from skm.platform.system_clock import SystemClock
from support.backend import ClientBackend, client_backend
from support.pg import clean_test_database, pg_session, test_database
from support.runtime_bootstrap import TestRuntimeRegistry

__all__ = ["clean_test_database", "client_backend", "pg_session", "test_database"]

_CHILD = """
import os, subprocess, sys
assert not set(os.environ).intersection((
    "SKM_TOKEN", "SKM_API_TOKEN", "SKM_DATABASE_URL", "SKM_MACHINE_DATABASE_URL",
))
raise SystemExit(subprocess.run(
    [sys.executable, "-m", "skm.entrypoints.cli.main", "mcp"], check=False,
).returncode)
"""


def _request(process: ProcessHandle, output: Queue[bytes], request: dict[str, Any]) -> str:
    process.write_stdin((json.dumps({"jsonrpc": "2.0", **request}) + "\n").encode())
    return output.get(timeout=10).decode()


@pytest.mark.skipif(sys.platform != "linux", reason="Linux peer process and subprocess containment fixture")
@pytest.mark.parametrize(
    "admitted_tools",
    [
        pytest.param(frozenset(), id="allow-none"),
        pytest.param(frozenset({"mcp:skm/skm_plan_list"}), id="allow-one"),
        pytest.param(frozenset({"mcp:skm/*"}), id="allow-skm"),
    ],
)
def test_stage_mcp_child_uses_only_the_channel_and_loses_it_when_fence_is_dropped(  # noqa: PLR0915
    client_backend: ClientBackend,
    admitted_tools: frozenset[str],
) -> None:
    side = client_backend
    owner = side.client()
    repo_id = configure_execution(side, owner)
    worker = register_worker(side, owner, "broker-worker")
    plan, revision = worker_plan(side)
    dispatch_new(owner, start_run_command(plan, revision, "P1.1"))
    schedule(side)
    claimed = dispatch_new(worker.client, worker.claim())
    prepared = dispatch_new(worker.client, begin_command(worker, claimed))
    secret = SecretStr(str(generate_secret(lambda n: b"B" * n)))
    admitted = prepare_agent_request(
        side, worker, claimed, prepared, repo_id, runtime_token_secret=secret.reveal()
    )
    assert admitted.request.secret_env == {}
    process_owner = admitted.request.process_owner
    dispatch_new(
        worker.client,
        execution.RenewLease(
            claim=worker.fence(claimed),
            progress={
                "phase": "runtime_started",
                "stage_record_id": str(process_owner.stage_record_id),
                "step_id": str(process_owner.unit_id),
            },
        ),
    )
    services = build_worker_services(
        side.root / "broker-state", stages=StageRegistry(()), context_inputs=None, resolve=lambda _: None
    )
    services = replace(
        services, stage_tool_client=lambda _, value: nullcontext(side.client(token=value.reveal()))
    )
    host = bind_stage_broker(
        HostServices(
            HostId(worker.host_id),
            Surface.WORKER,
            GatewayTable({WorkerServices: services}, "host_gateway"),
            dict,
            {},
        ),
        serve_stage,
    )
    claim = WorkerClaim(
        AssignmentId(UUID(claimed["assignment_id"])),
        AttemptId(UUID(claimed["attempt_id"])),
        WorkerId(worker.worker_id),
        int(claimed["fencing_token"]),
    )
    runtime = FakeRuntime(
        state_dir=side.root / "fake-runtime",
        scenario=Path(__file__).parents[2] / "fixtures/runtimes/fake/review-green.toml",
    )
    deps = cast("StageDeps", SimpleNamespace(runtimes=TestRuntimeRegistry(runtime)))
    ctx = HostContext(worker.client, host.gateways, host.host_id, {}, None, CancelSource().token)
    request = replace(
        admitted.stage,
        task={**admitted.stage.task, "workspace_id": str(worker.workspace_id)},
        runtime_request=replace(
            admitted.request, permissions=replace(admitted.request.permissions, tools=admitted_tools)
        ),
    )
    with ExitStack() as stack:
        bound = _bind_stage_tools(stack, ctx, host.gateways.get(WorkerServices), request, deps, secret, claim)
        assert bound.runtime_request is not None
        assert bound.process_started is not None
        assert bound.runtime_request.secret_env == {}
        socket_path = bound.runtime_request.extra_env["SKM_STAGE_SOCKET"]
        output = Queue[bytes]()
        stderr = Queue[bytes]()
        process = spawn(
            [sys.executable, "-c", _CHILD],
            cwd=side.root,
            env={"SKM_STAGE_SOCKET": socket_path},
            on_stdout=output.put,
            on_stderr=stderr.put,
        )
        try:
            bound.process_started(
                SessionHandle(
                    "fake",
                    admitted.request.request_id,
                    process.pid,
                    process.identity.start_ticks,
                    SystemClock().now(),
                    ProcessOwnership(process_owner, "pgroup_best_effort", str(process.pgid)),
                )
            )
            # A different process of the same Unix user cannot borrow the socket path.
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as foreign:
                foreign.settimeout(3)
                foreign.connect(socket_path)
                with suppress(ConnectionResetError, BrokenPipeError):
                    foreign.sendall(b'{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n')
                    assert foreign.recv(16) == b""

            raw = _request(
                process,
                output,
                {"id": 1, "method": "tools/call", "params": {"name": "skm_plan_list", "arguments": {}}},
            )
            result = json.loads(raw)["result"]
            plan_list_allowed = bool(admitted_tools)
            assert result["isError"] is not plan_list_allowed, raw
            if plan_list_allowed:
                assert str(plan) in raw
            else:
                assert "FORBIDDEN" in raw
            assert secret.reveal() not in raw

            tool_list = json.loads(_request(process, output, {"id": 2, "method": "tools/list"}))
            names = {item["name"] for item in tool_list["result"]["tools"]}
            assert ("skm_plan_list" in names) is plan_list_allowed
            assert "skm_plan_draft_open" not in names
            if "mcp:skm/*" not in admitted_tools:
                assert names == ({"skm_plan_list"} if plan_list_allowed else set())
                denied_read = _request(
                    process,
                    output,
                    {
                        "id": 3,
                        "method": "tools/call",
                        "params": {"name": "skm_plan_show", "arguments": {"plan": str(plan)}},
                    },
                )
                assert json.loads(denied_read)["result"]["isError"]
                assert "FORBIDDEN" in denied_read
                # Authoring continuation is also restricted by stage policy.
                fetch = _request(
                    process,
                    output,
                    {"id": 4, "method": "tools/call", "params": {"name": "skm_fetch", "arguments": {}}},
                )
                assert json.loads(fetch)["result"]["isError"]
                assert "FORBIDDEN" in fetch
            if admitted_tools == {"mcp:skm/skm_plan_list"}:
                dispatch_new(
                    owner,
                    SetValue.from_json(
                        {
                            "scope": {"level": "project", "scope_id": str(side.seed.project_id)},
                            "key": "policy.restrictions",
                            "value": [{"tools": {"allow": []}}],
                            "expected_row_version": 0,
                        }
                    ),
                )
            else:
                with side.uow(readonly=False) as uow:
                    uow.repo(AssignmentRepository).drop_lease(claim.assignment_id)
                    uow.commit()
            process.write_stdin(b'{"jsonrpc":"2.0","id":3,"method":"tools/list"}\n')
            assert process.wait(timeout_seconds=10) == 0
            assert output.empty()
            assert stderr.empty()
        finally:
            process.terminate(grace_seconds=1)

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as closed, pytest.raises(FileNotFoundError):
        closed.connect(socket_path)
