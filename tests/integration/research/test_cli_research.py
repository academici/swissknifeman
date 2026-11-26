"""Thin CLI forwarding through an explicitly composed host operation."""

import json
from io import StringIO
from types import SimpleNamespace
from typing import cast
from uuid import uuid4

from skm.application_bus.host import HostServices
from skm.entrypoints.cli.commands import research
from skm.entrypoints.cli.context import CliOptions, CliSession
from skm.entrypoints.cli.parser import build_parser
from skm.kernel.ports_uow import Surface
from skm.modules.context.module import RESEARCH_SPEC as SPEC
from skm.platform.logging.redaction import Redactor
from skm.platform.system_clock import SystemClock
from skm.platform.system_ids import Uuid7Generator

from ._support import host


def session(ctx):
    services = HostServices(ctx.host_id, Surface.CLI, ctx.gateways, lambda: ctx.config, {SPEC.name: SPEC})
    return CliSession(
        CliOptions(json=True),
        StringIO(),
        StringIO(),
        Redactor(),
        Uuid7Generator(SystemClock()),
        "req_research",
        client_=ctx.client,
        host_factory=lambda: services.context(client=ctx.client, cancel=ctx.cancel, log=ctx.log),
    )


def test_cli_query_sources_json_and_all_failed_exit(monkeypatch):
    ctx = host()
    cli = session(ctx)
    # This test supplies an explicit HostServices composition, not an application/DB override.
    monkeypatch.setattr(research, "MANIFESTS", (SimpleNamespace(id="context", host_operations=(SPEC,)),))
    monkeypatch.setattr(
        research, "resolve_project_view", lambda *_: SimpleNamespace(workspace_id=uuid4(), project_id=uuid4())
    )
    parser = build_parser()
    args = parser.parse_args(["research", "query", "research", "--source", "docs", "--no-cache", "--json"])
    assert args.run(args, cli) == 0
    document = json.loads(cast("StringIO", cli.stdout).getvalue())
    assert document["ok"]
    assert document["result"]["results"][0]["cache_status"] == "bypass"
    cli.stdout.seek(0)
    cli.stdout.truncate()
    args = parser.parse_args(["research", "sources", "--json"])
    assert args.run(args, cli) == 0
    assert json.loads(cast("StringIO", cli.stdout).getvalue())["result"]["sources"][0]["id"] == "docs"
    ctx.config["context.research.sources"]["docs"]["argv"] = ["/definitely/not/a/research/program"]
    cli.stdout.seek(0)
    cli.stdout.truncate()
    args = parser.parse_args(["research", "query", "research", "--json"])
    assert args.run(args, cli) == 1
    document = json.loads(cast("StringIO", cli.stdout).getvalue())
    assert not document["ok"]
    assert document["error"]["code"] == "RESEARCH_SOURCE_UNAVAILABLE"


def test_cli_show_uses_public_query_without_host_services(monkeypatch):
    ctx = host()
    cli = session(ctx)
    cli.host_factory = None
    project = uuid4()
    monkeypatch.setattr(research, "resolve_project_view", lambda *_: SimpleNamespace(project_id=project))
    query_id = str(uuid4())
    ctx.client.records[query_id] = {"query_id": query_id}
    args = build_parser().parse_args(["research", "show", query_id, "--json"])
    assert args.run(args, cli) == 0
    assert ctx.client.queries[0].SCHEMA_URN == "urn:skm:context:query:get-research-query:v1"
    assert ctx.client.queries[0]["project_id"] == str(project)
