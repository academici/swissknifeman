"""Exercise the built-in research sources through CLI and worker host composition."""

import json
import sys
from io import StringIO
from pathlib import Path
from typing import Any, cast, override
from uuid import uuid4

from skm.application_bus.client import SkmClient
from skm.bootstrap.host_services import build_context_inputs, build_host_services
from skm.entrypoints.cli.context import CliOptions, CliSession
from skm.entrypoints.cli.host import host_context_factory
from skm.entrypoints.cli.parser import build_parser
from skm.kernel.cancel import CancelSource
from skm.kernel.ids import AttemptId, WorkerId, WorkspaceId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.context.application.commands.finalize_manifest import FinalizeManifest
from skm.modules.context.domain.draft import build_draft, host_input_to_json, make_research_request
from skm.modules.context.domain.research_rules import query_digest
from skm.modules.context.module import RESEARCH_SPEC
from skm.modules.execution.domain.ids import AssignmentId, EnvironmentId
from skm.modules.execution.domain.lease import WorkerClaim
from skm.modules.execution.host.context_inputs import finalize_stage_context
from skm.modules.execution.host.environment import PreparedEnvironment
from skm.modules.workspace.public import GetProject, ProjectView
from skm.platform.logging.logger import get_logger
from skm.platform.logging.redaction import Redactor
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

from ._support import Client, json_script, spec
from .test_mcp_stdio_adapter import SERVER


class ResearchClient(Client):
    def __init__(self, project: ProjectView) -> None:
        super().__init__()
        self.project = project
        self.finalization: FinalizeManifest | None = None

    @override
    def ask(self, request: Any) -> Any:
        if isinstance(request, GetProject):
            assert request.project_id == self.project.project_id
            return self.project
        return super().ask(request)

    @override
    def dispatch(self, request: Any, *, idempotency_key: str | None = None) -> Any:
        if isinstance(request, FinalizeManifest):
            self.finalization = request
            return {}
        return super().dispatch(request, idempotency_key=idempotency_key)


def test_cli_and_worker_run_all_builtin_research_sources(tmp_path: Path) -> None:
    (tmp_path / "evidence.md").write_text("research from filesystem", encoding="utf-8")
    sources: JsonObject = {
        "command": {
            "kind": "command",
            "tier": "local_docs",
            "capabilities": ["search"],
            "argv": [
                sys.executable,
                "-c",
                json_script(
                    {
                        "documents": [
                            {
                                "origin": "mcp:command/docs",
                                "title": "Command",
                                "text": "research from command",
                            }
                        ]
                    }
                ),
            ],
        },
        "filesystem": {
            "kind": "filesystem",
            "tier": "local_docs",
            "capabilities": ["search"],
            "roots": [str(tmp_path)],
        },
        "mcp": {
            "kind": "mcp_stdio",
            "tier": "local_docs",
            "capabilities": ["search"],
            "argv": [sys.executable, "-c", SERVER],
            "tool": "lookup",
        },
    }
    host_config: JsonObject = {
        "context.research.sources": sources,
        "context.research.fs_roots_allow": [str(tmp_path)],
    }
    project = ProjectView(uuid4(), uuid4(), "research", "Research", "", "active", 1, ())
    bootstrap: JsonObject = {"host": {"id": str(uuid4())}}
    backend = ResearchClient(project)
    client = cast("SkmClient", backend)
    cli_host = build_host_services(
        bootstrap, client=client, plugins=(), environ={}, surface=Surface.CLI, host_config=lambda: host_config
    )
    assert cli_host.operations[RESEARCH_SPEC.name] is RESEARCH_SPEC
    stdout = StringIO()
    cli = CliSession(
        CliOptions(json=True),
        stdout,
        StringIO(),
        Redactor(),
        Uuid7Generator(SystemClock()),
        "req_research",
        client_=client,
        host_factory=host_context_factory(cli_host, client),
    )
    args = build_parser().parse_args(
        ["research", "query", "research", "--project", str(project.project_id), "--no-cache", "--json"]
    )
    assert args.run(args, cli) == 0, stdout.getvalue()
    results = json.loads(stdout.getvalue())["result"]["results"]
    expected = {
        "command": ("command", "research from command"),
        "filesystem": ("filesystem", "research from filesystem"),
        "mcp": ("mcp_stdio", "research evidence"),
    }
    assert {row["source_id"] for row in results} == expected.keys()
    for row in results:
        kind, evidence = expected[row["source_id"]]
        assert row["status"] == "ok", row
        assert row["kind"] == kind
        assert evidence in row["documents"][0]["excerpt"]

    # A separate worker client lets prompt publication verify that the step owns every recorded result.
    backend = ResearchClient(project)
    client = cast("SkmClient", backend)
    worker_host = build_host_services(
        bootstrap,
        client=client,
        plugins=(),
        environ={},
        surface=Surface.WORKER,
        host_config=lambda: host_config,
    )
    assert worker_host.operations[RESEARCH_SPEC.name] is RESEARCH_SPEC
    workspace_id = WorkspaceId(project.workspace_id)
    published: list[bytes] = []

    def publish(_ctx: object, content: bytes, step_id: str) -> JsonObject:
        [(record, _)] = backend.commands
        assert record["step_ref"] == f"step:{step_id}"
        assert {row["source_id"] for row in backend.records.values()} == expected.keys()
        published.append(content)
        return backend.upload_blob(workspace_id, (content,), size=len(content)).to_json()

    inputs = build_context_inputs(publish_prompt=publish)
    request = make_research_request(
        "research:1", query_spec=spec(use_cache=False), query_digest=query_digest("research"), max_bytes=65536
    )
    step_id = uuid4()
    draft: JsonObject = {
        "manifest_id": str(uuid4()),
        "manifest": {"project_id": str(project.project_id)},
        "host_inputs": [host_input_to_json(request)],
        "budget": {"estimator_id": "heuristic-v1"},
    }
    draft["draft_digest"] = build_draft(draft).draft_digest
    begin: JsonObject = {
        "step": {
            "step_id": str(step_id),
            "context": {
                "draft": draft,
                "estimator_id": "heuristic-v1",
                "host_limits": {"max_bytes": 2097152, "max_work_paths": 300},
            },
        }
    }
    result = finalize_stage_context(
        worker_host.context(client=client, cancel=CancelSource().token, log=get_logger("test.research")),
        WorkerClaim(AssignmentId(uuid4()), AttemptId(uuid4()), WorkerId(uuid4()), 1),
        begin,
        PreparedEnvironment(EnvironmentId(uuid4()), str(tmp_path), {"repo": tmp_path}, (), "attempt"),
        inputs,
        workspace_id=workspace_id,
    )
    assert published == [result.rendered_prompt.encode()]
    for _, evidence in expected.values():
        assert evidence in result.rendered_prompt
    assert backend.finalization is not None
    assert set(backend.finalization["host_blocks"][0]["research_query_ids"]) == backend.records.keys()
