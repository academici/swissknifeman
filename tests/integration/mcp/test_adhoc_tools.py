"""MCP discovery, session scoping and dispatch for the ad hoc tools."""

from contracts.execution.harness import PEPPER, ExecSide
from integration.mcp.test_protocol import call, content, exchange, request
from skm.entrypoints.mcp.session import McpSession
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access
from support.adhoc import adhoc_side as adhoc_side
from support.adhoc import assembly, token, workflow


def session_for(side: ExecSide, permissions: tuple[str, ...] | None = None) -> McpSession:
    secret = token(side, permissions=permissions)
    with side.uow(readonly=True) as uow:
        actor = access.authenticate_token(uow, secret, pepper=PEPPER, now=side.clock.now())
    return McpSession.open(side.app.client(actor=actor, surface=Surface.MCP), project_id=side.proj)


def test_mcp_discovers_and_calls_both_tools(adhoc_side: ExecSide) -> None:
    session = session_for(adhoc_side)
    listing, run, manifest, foreign = exchange(
        session,
        [
            request("tools/list", 1),
            call("skm_run_adhoc", {"prompt": "Inspect the architecture.", "workflow": workflow()}, 2),
            call("skm_context_assemble", assembly(), 3),
            call("skm_context_assemble", {**assembly(), "project_id": str(adhoc_side.proj2)}, 4),
        ],
    )
    names = {tool["name"] for tool in listing["result"]["tools"]}
    assert {"skm_run_adhoc", "skm_context_assemble"} <= names
    assert content(run)["task_count"] == 1
    assert content(manifest)["draft_digest"].startswith("sha256:")
    assert foreign["error"]["code"] == -32602


def test_mcp_narrow_token_cannot_assemble_or_start(adhoc_side: ExecSide) -> None:
    session = session_for(adhoc_side, ("project.read", "run.read", "context.read"))
    listing, run, manifest = exchange(
        session,
        [
            request("tools/list", 1),
            call("skm_run_adhoc", {"prompt": "No authority to start."}, 2),
            call("skm_context_assemble", assembly(), 3),
        ],
    )
    names = {tool["name"] for tool in listing["result"]["tools"]}
    assert not {"skm_run_adhoc", "skm_context_assemble"} & names
    for response in (run, manifest):
        assert response["result"]["isError"]
        assert content(response)["error"]["code"] == "FORBIDDEN"
