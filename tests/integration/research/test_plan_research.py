"""Real plan CLI, project policy, research ledger, and readiness contract."""

import json
from io import StringIO
from typing import Any, cast
from uuid import uuid4

import httpx
import pytest

from contracts.execution.harness import ExecSide, _publish_revision
from integration.context.test_research_repository import command, record, setting, source_setting
from skm.adapters.http_client.research import ResearchHttpTransport
from skm.adapters.research.providers import PerplexityWebResearchSource
from skm.adapters.research.retry import ResearchSources
from skm.application_bus.client import SkmClient
from skm.bootstrap.host_services import bind_cli_research, build_host_services
from skm.entrypoints.cli.context import CliOptions, CliSession
from skm.entrypoints.cli.host import host_context_factory
from skm.entrypoints.cli.parser import build_parser
from skm.kernel.errors import Forbidden, NotFound, SkmError
from skm.kernel.json_types import JsonObject, JsonValue
from skm.kernel.ports_uow import Surface
from skm.modules.context.ports import ResearchSourceRegistry
from skm.modules.execution.generated.commands import StartRun, ValidateForExecution
from skm.modules.execution.generated.queries import GetReadinessReport
from skm.modules.planning import public as planning
from skm.modules.planning.domain.specification import to_document
from skm.platform.logging.redaction import Redactor
from skm.platform.system_ids import Uuid7Generator
from unit.adapters.test_research_providers import BROKER, Body
from unit.execution.application._support import _shared_side as _shared_side
from unit.execution.application._support import side as side

SOURCE: JsonObject = {
    "kind": "perplexity_web",
    "tier": "external_search",
    "capabilities": ["search"],
    "endpoint": BROKER,
    "trust_cap": "repository",
}


def _cli(side: ExecSide, client: SkmClient, registry: ResearchSources) -> CliSession:
    services = build_host_services(
        {"host": {"id": str(side.host1)}},
        client=client,
        plugins=(),
        environ={},
        surface=Surface.CLI,
        host_config=lambda: {"context.research.sources": {"docs": SOURCE}},
        gateways={ResearchSourceRegistry: registry},
    )
    return CliSession(
        CliOptions(json=True),
        StringIO(),
        StringIO(),
        Redactor(),
        Uuid7Generator(side.clock),
        "req_research",
        client_=client,
        host_factory=host_context_factory(bind_cli_research(services, client), client),
    )


def test_plan_research_respects_project_profile_and_r15_rechecks_live_policy(side: ExecSide) -> None:
    source_setting(side, **SOURCE)
    setting(side, "context.research.profile.sources", ["docs"])
    setting(side, "context.research.profile.max_documents", 1)
    setting(side, "context.research.profile.excerpt_max_chars", 35)
    requests = []

    async def send(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        body = {
            "documents": [
                {
                    "url": f"https://example.org/{n}",
                    "title": "~~~\n## injected title",
                    "text": "evidence " * 10,
                }
                for n in range(2)
            ]
        }
        return httpx.Response(200, stream=Body(json.dumps(body).encode()))

    registry = ResearchSources(
        {"perplexity_web": PerplexityWebResearchSource(ResearchHttpTransport(httpx.MockTransport(send)))},
        clock=side.clock,
    )
    cli = _cli(side, side.client, registry)
    args = build_parser().parse_args(
        [
            "plan",
            "research",
            str(side.plan1),
            "Which option fits?",
            "--project",
            str(side.proj),
            "--json",
        ]
    )
    with pytest.raises(Forbidden):
        args.run(args, _cli(side, side.viewer_client, registry))
    assert requests == []
    assert args.run(args, cli) == 0, cast("StringIO", cli.stderr).getvalue()
    response = json.loads(cast("StringIO", cli.stdout).getvalue())["result"]
    (query_id,) = response["design_query_ids"]
    assert response["plan_id"] == str(side.plan1)
    assert requests == [{"query": "Which option fits?", "max_documents": 1, "depth": "standard"}]
    (doc,) = response["results"][0]["documents"]
    assert doc["trust_class"] == "third_party"
    assert len(doc["excerpt"]) == 35
    assert "Trust: THIRD_PARTY\n~~~~text" in response["research_markdown"]

    with side.uow(readonly=True) as uow:
        document = to_document(planning.get_revision_specification(uow, side.rev2))
    items = cast("list[JsonValue]", document["items"])
    cast("JsonObject", items[0])["sections"] = [
        {"id": "design-research", "title": "Design research", "text": f"research-query:{query_id}"}
    ]
    revision = _publish_revision(
        side.app, side.client, side.owner, side.clock, side.plan1, {"items": items}, "current"
    )
    first = cast("Any", side.client.dispatch(ValidateForExecution(side.plan1, revision)))
    assert _r15(side, first.report_id) == "passed"
    setting(side, "context.research.profile.sources", [])
    second = cast("Any", side.client.dispatch(ValidateForExecution(side.plan1, revision)))
    assert _r15(side, second.report_id) == "failed"
    assert second.status == "not_ready"
    with pytest.raises(SkmError, match="fresh"):
        side.client.dispatch(StartRun(side.plan1, revision, first.report_id, {}, "old evidence"))
    args.source = ["docs"]
    with pytest.raises(NotFound, match="unknown research source"):
        args.run(args, cli)
    assert len(requests) == 1


def _r15(side: ExecSide, report_id: Any) -> str:
    report = cast("Any", side.client.ask(GetReadinessReport(report_id=report_id))).to_json()
    return next(
        rule["outcome"] for rule in report["report"]["results"] if rule["rule_id"] == "R15_design_research"
    )


def test_plan_profile_is_enforced_when_recording_directly(exec_side: ExecSide) -> None:
    source_setting(exec_side)
    setting(exec_side, "context.research.profile.max_documents", 1)
    payload = command(exec_side, index=1, documents=2)
    with pytest.raises(SkmError, match="too_many_documents"):
        record(exec_side, payload, key=f"over-profile:{uuid4()}")
    setting(exec_side, "context.research.profile.sources", [])
    with pytest.raises(Forbidden, match="disabled"):
        record(exec_side, command(exec_side), key=f"outside-profile:{uuid4()}")
