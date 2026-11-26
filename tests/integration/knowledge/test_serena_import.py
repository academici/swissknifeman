"""Exercise checkout imports and the graph CLI against the real knowledge bus."""

import json
import tomllib
from dataclasses import dataclass, replace
from datetime import timedelta
from io import StringIO
from pathlib import Path
from typing import Any, cast

import pytest

from contracts.execution.harness import ExecSide, exec_side
from e2e.test_instance_profiles import _Databases, _environment, _remote, databases
from integration.mcp.test_tools import authenticate
from skm.adapters.git.repo_inspect import MARKER_FILENAME, GitRepositoryInspector
from skm.adapters.knowledge.manifest_readers.composer_json import ComposerJsonReader
from skm.adapters.knowledge.manifest_readers.package_json import PackageJsonReader
from skm.adapters.knowledge.manifest_readers.pyproject import PyprojectReader
from skm.adapters.knowledge.serena_reader import SerenaCodeGraphReader
from skm.application_bus.host import HostContext, HostServices
from skm.bootstrap._knowledge_wiring import bind_cli_knowledge
from skm.entrypoints.cli.host import host_context_factory
from skm.entrypoints.cli.main import Backend, main
from skm.kernel.cancel import CancelSource
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import NotFound, SkmError, ValidationFailed
from skm.kernel.gateways import GatewayTable
from skm.kernel.ids import ProjectId, RepositoryId
from skm.kernel.json_types import JsonObject
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access
from skm.modules.knowledge import public as knowledge
from skm.modules.knowledge.host.derive_project_graph import derive_project_graph
from skm.modules.knowledge.host.import_code_graph import _chunks, import_code_graph
from skm.modules.knowledge.ports import CodeGraphReader, GraphCheckoutResolver, ManifestReader
from skm.modules.settings.public import SetValue
from skm.modules.workspace.public import (
    CheckoutLocationView,
    CheckoutMarker,
    MountName,
    ResolveCheckout,
    checkout_id_from_locator,
)
from skm.platform.jsonc.digest import digest
from skm.platform.system_clock import SystemClock
from support.client_transport import client_api
from support.git_repo import init_git_repo
from support.http_server import loopback_certificate, loopback_server
from support.pg import clean_test_database, pg_session, test_database

__all__ = ["clean_test_database", "databases", "exec_side", "pg_session", "test_database"]

_REF = "v1.2.3"
_REVISION = "a" * 40
_SCHEMA: JsonObject = {"find_symbol": {"type": "object"}}


class _Manifests:
    def read_snapshot(self, root: str) -> tuple[str, tuple[JsonObject, ...]]:
        return "2026-11-19T00:00:00Z", self.dependencies(Path(root))

    def dependencies(self, root: Path) -> tuple[JsonObject, ...]:
        return (
            *PyprojectReader(tomllib.loads).dependencies(root),
            *PackageJsonReader().dependencies(root),
            *ComposerJsonReader().dependencies(root),
        )


@dataclass(frozen=True)
class _SyntheticCheckout:
    side: ExecSide
    root: Path

    def resolve_graph(self, project_id: ProjectId, mount: str) -> tuple[RepositoryId, str]:
        assert (project_id, mount) == (self.side.proj, "repo")
        return self.side.repo_id, str(self.root)


def _host(side: ExecSide, root: Path, **overrides: Any) -> HostContext:
    root.mkdir()
    client = side.app.client(actor=side.owner, surface=Surface.CLI)
    argv = ["uvx", "--from", f"git+https://example.invalid/indexer@{_REF}"]
    config = {
        "knowledge.graph.enabled": True,
        "knowledge.graph.import_max_bytes": 32 * 1024 * 1024,
        "knowledge.code_graph.enabled": True,
        "knowledge.code_graph.argv": argv,
        "knowledge.code_graph.index_argv": argv,
        "knowledge.code_graph.ignores": ["generated", "other/skip"],
        "knowledge.code_graph.serena_schema_pin": digest(_SCHEMA),
        "knowledge.code_graph.stale_after_hours": 24,
        "knowledge.code_graph.keep_generations": 3,
        **overrides,
    }
    return HostContext(
        client,
        GatewayTable(
            {
                CodeGraphReader: SerenaCodeGraphReader(),
                ManifestReader: _Manifests(),
                GraphCheckoutResolver: _SyntheticCheckout(side, root),
            },
            "host_gateway",
        ),
        side.host1,
        config,
        None,
        CancelSource().token,
    )


def _export(root: Path, side: ExecSide, *, replace_export: bool = False, revision: str = _REVISION) -> Path:
    index = root / ".serena" / "graph.json"
    index.parent.mkdir(exist_ok=True)
    first = {"path": "src/app.py", "qualified_name": "Runner.execute"}
    second = {"path": "src/app.py", "qualified_name": "run"}
    ignored = {"path": "sub/generated/machine.py", "qualified_name": "machine"}
    index.write_text(
        json.dumps(
            {
                "ref": _REF,
                "tool_schema": _SCHEMA,
                "index": {
                    "revision": revision,
                    "dirty": False,
                    "languages": ["python"],
                    "basis_default": "lsp",
                    "tool_name": "serena",
                    "tool_version": _REF,
                    "indexed_at": side.clock.now().isoformat(),
                    "completeness": "complete",
                    "limitations": [],
                    "files_indexed": 2,
                    "files_skipped": 0,
                },
                "symbols": [first] if replace_export else [first, second, ignored],
                "references": []
                if replace_export
                else [{"src": first, "dst": second}, {"src": first, "dst": ignored}],
            }
        ),
        encoding="utf-8",
    )
    return index


def _setup_manifests(root: Path) -> None:
    (root / "pyproject.toml").write_text(
        '[project]\nname = "Sample_App"\nversion = "1"\ndependencies = ["example-lib>=1"]\n',
        encoding="utf-8",
    )
    (root / "package.json").write_text('{"dependencies":{"@example/library":"^2"}}', encoding="utf-8")
    (root / "composer.json").write_text('{"require":{"example/library":"^3","php":"^8"}}', encoding="utf-8")
    for directory in ("vendor", "node_modules", ".git", "dist", "build"):
        ignored = root / directory
        ignored.mkdir(exist_ok=True)
        (ignored / "package.json").write_text("invalid", encoding="utf-8")


def _files(root: Path) -> dict[Path, bytes]:
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


def test_index_replacement_and_reader_gates(exec_side: ExecSide, tmp_path: Path) -> None:
    side = exec_side
    root = tmp_path / "checkout"
    ctx = _host(side, root)
    _export(root, side)
    (root / ".serena" / "project.yml").write_text("read_only: true\n", encoding="utf-8")
    _setup_manifests(root)
    request: JsonObject = {"project_id": str(side.proj), "mount": "repo"}
    initial = _files(root)
    imported = import_code_graph(ctx, request)
    derived = derive_project_graph(ctx, request)
    assert (imported["generation"], derived["generation"], derived["edges_added"]) == (1, 1, 4)
    assert _files(root) == initial

    def neighbors(name: str) -> Any:
        return ctx.client.ask(
            knowledge.GraphNeighbors.from_json(
                {
                    "workspace_id": str(side.ws),
                    "node_key": f"symbol:{side.repo_id}:src/app.py#{name}",
                }
            )
        )

    answer = neighbors("Runner.execute")
    assert answer["completeness"] == "partial"
    assert answer["limitations"][0]["code"] == "generated_excluded"
    assert {edge["type"] for edge in answer["edges"]} == {"references", "belongs_to"}
    assert all("machine" not in item["node_key"] for item in answer["nodes"])
    _export(root, side, replace_export=True)
    for key, value, error in (
        ("knowledge.code_graph.serena_schema_pin", "sha256:wrong", ErrorCode.CONFIG_INVALID),
        (
            "knowledge.code_graph.index_argv",
            ["uvx", "--from", "git+https://example.invalid/indexer"],
            ErrorCode.CONFIG_INVALID,
        ),
        ("knowledge.code_graph.enabled", False, ErrorCode.MODULE_DISABLED),
        ("knowledge.graph.enabled", False, ErrorCode.MODULE_DISABLED),
    ):
        with pytest.raises(SkmError) as failure:
            import_code_graph(replace(ctx, config={**cast("JsonObject", ctx.config), key: value}), request)
        assert failure.value.code is error
        assert neighbors("run")["index_generation"] == 1
    updated = import_code_graph(ctx, request)
    assert updated["generation"] == 2
    with pytest.raises(NotFound):
        neighbors("run")
    stats: Any = ctx.client.ask(knowledge.GraphStats.from_json({"workspace_id": str(side.ws)}))
    assert {source["source"] for source in stats["sources"]} == {"manifests", "serena"}
    assert stats["stats"]["nodes_by_type"]["package"] == 4


def test_bytes_chunking_replaces_once_and_rejects_oversized_item(exec_side: ExecSide, tmp_path: Path) -> None:
    side = exec_side
    root = tmp_path / "checkout"
    ctx = _host(side, root, **{"knowledge.graph.import_max_bytes": 950})
    export = _export(root, side)
    request: JsonObject = {"project_id": str(side.proj), "mount": "repo"}
    imported = import_code_graph(ctx, request)
    assert cast("int", imported["chunks"]) > 1
    assert (imported["nodes_upserted"], imported["edges_added"]) == (3, 3)
    stats = knowledge.GraphStats.from_json({"workspace_id": str(side.ws)})
    original = ctx.client.ask(stats)
    document = json.loads(export.read_text(encoding="utf-8"))
    document["symbols"][-2]["metadata"] = "⚙" * 2_000
    export.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValidationFailed) as rejected:
        import_code_graph(ctx, request)
    assert rejected.value.code is ErrorCode.PAYLOAD_TOO_LARGE
    assert ctx.client.ask(stats) == original


def test_chunk_item_caps_and_replacement_flag() -> None:
    node: JsonObject = {"node_key": "doc:a", "type": "doc", "attrs": {}}
    edge: JsonObject = {
        "src_key": "doc:a",
        "dst_key": "doc:a",
        "type": "references",
        "attrs": {},
        "source_key": "",
    }
    chunks = list(_chunks({}, [node] * 20_001, [edge] * 50_001, 32 * 1024 * 1024))
    assert [
        (chunk["replace"], len(cast("list", chunk["nodes"])), len(cast("list", chunk["edges"])))
        for chunk in chunks
    ] == [(True, 20_000, 0), (False, 1, 50_000), (False, 0, 1)]


@pytest.mark.parametrize("exec_side", ["memory"], indirect=True)
@pytest.mark.parametrize("json_mode", [False, True])
def test_graph_cli(exec_side: ExecSide, tmp_path: Path, json_mode: bool) -> None:
    side = exec_side
    root = tmp_path / "checkout"
    ctx = _host(side, root)
    _export(root, side)
    _setup_manifests(root)
    for key, value in (("enabled", True), ("ignores", ["generated"])):
        ctx.client.dispatch(
            SetValue.from_json(
                {
                    "scope": {"level": "project", "scope_id": str(side.proj)},
                    "key": f"knowledge.code_graph.{key}",
                    "value": value,
                    "reason": "Test Serena import",
                }
            )
        )
    host = HostServices(side.host1, Surface.CLI, cast(GatewayTable, ctx.gateways), lambda: ctx.config, {})
    app, _ = bind_cli_knowledge(replace(side.app, host=host), side.owner)
    host_factory = host_context_factory(app.host, ctx.client)
    first = f"symbol:{side.repo_id}:src/app.py#Runner.execute"
    second = f"symbol:{side.repo_id}:src/app.py#run"

    def invoke(verb: str, *args: str, host: bool = False) -> Any:
        out, err = StringIO(), StringIO()
        scope = ["--project", str(side.proj), "--mount", "repo"] if host else ["--workspace", str(side.ws)]
        code = main(
            ["graph", verb, *args, *scope, *(["--json"] if json_mode else [])],
            stdout=out,
            stderr=err,
            environ={"HOME": str(tmp_path)},
            backend=lambda *_: Backend(
                ctx.client, host_factory=host_factory, instance_id=side.app.instance_id
            ),
        )
        assert code == 0, out.getvalue() + err.getvalue()
        if json_mode:
            document = json.loads(out.getvalue())
            assert document["ok"]
            return document["result"]
        return out.getvalue()

    imported = invoke("import-code", host=True)
    derived = invoke("derive", host=True)
    neighbors = invoke("neighbors", first, "--depth", "1", "--direction", "out", "--edge-type", "references")
    path = invoke("path", first, second, "--at-revision", _REVISION)
    stats = invoke("stats", "--project", str(side.proj))
    subgraph = invoke("subgraph", first, second, "--depth", "0", "--edge-type", "references")
    indexes = invoke("indexes", "--source", "serena", "--repository", str(side.repo_id))
    if json_mode:
        assert (imported["source"], derived["source"]) == ("serena", "manifests")
        assert [edge["type"] for edge in neighbors["edges"]] == ["references"]
        assert path["path"] == [first, second]
        assert stats["stats"]["nodes_by_type"]["package"] == 4
        assert {node["node_key"] for node in subgraph["nodes"]} == {first, second}
        assert [edge["type"] for edge in subgraph["edges"]] == ["references"]
        assert [(row["source"], row["generation"]) for row in indexes["items"]] == [("serena", 1)]
    else:
        assert "serena" in imported
        assert "manifests" in derived
        assert "freshness" in neighbors
        assert "references" in neighbors
        assert f"{first} → {second}" in path
        assert "package" in stats
        assert "references" in subgraph
        assert "serena" in indexes


def test_late_invalid_chunk_preserves_active_snapshot(exec_side: ExecSide, tmp_path: Path) -> None:
    side = exec_side
    root = tmp_path / "checkout"
    key = "knowledge.graph.import_max_bytes"
    limit = 1_048_576
    ctx = _host(side, root, **{key: limit})
    ctx.client.dispatch(SetValue.from_json({"scope": {"level": "instance"}, "key": key, "value": limit}))
    export = _export(root, side)
    request: JsonObject = {"project_id": str(side.proj), "mount": "repo"}
    import_code_graph(ctx, request)
    stats = knowledge.GraphStats.from_json({"workspace_id": str(side.ws)})
    original = ctx.client.ask(stats)

    snapshot = json.loads(export.read_text(encoding="utf-8"))
    snapshot["symbols"].extend(
        {"path": "src/app.py", "qualified_name": f"extra_{n}", "metadata": "x" * 15_000} for n in range(80)
    )
    snapshot["symbols"].append({"path": "src/app.py", "qualified_name": "invalid", "metadata": "x" * 16_384})
    export.write_text(json.dumps(snapshot), encoding="utf-8")
    with pytest.raises(ValidationFailed) as rejected:
        import_code_graph(ctx, request)
    assert rejected.value.details == {"field": "attrs", "reason": "too_large"}
    assert ctx.client.ask(stats) == original


def test_serena_reference_occurrences(exec_side: ExecSide, tmp_path: Path) -> None:
    side = exec_side
    root = tmp_path / "checkout"
    ctx = _host(side, root)
    export = _export(root, side)
    snapshot = json.loads(export.read_text(encoding="utf-8"))
    ref = snapshot["references"][0]
    first = {**ref, "attrs": {"line": 10, "col": 5}}
    second = {**ref, "attrs": {"line": 20, "col": 5}}
    snapshot["references"] = [first, second, first]
    export.write_text(json.dumps(snapshot), encoding="utf-8")
    request: JsonObject = {"project_id": str(side.proj), "mount": "repo"}
    import_code_graph(ctx, request)
    query = knowledge.GraphNeighbors.from_json(
        {
            "workspace_id": str(side.ws),
            "node_key": f"symbol:{side.repo_id}:src/app.py#Runner.execute",
            "edge_types": ["references"],
        }
    )
    answer: Any = ctx.client.ask(query)
    assert sorted(edge["attrs"]["line"] for edge in answer["edges"]) == [10, 20]


def _marked_repository(root: Path, side: ExecSide):
    repo = init_git_repo(root)
    GitRepositoryInspector().write_marker(
        root,
        marker=CheckoutMarker(side.app.instance_id, side.ws, side.proj, side.repo_id, MountName("repo")),
    )
    return repo


@pytest.mark.pg
def test_graph_imports_through_production_http_cli(
    exec_side: ExecSide, databases: _Databases, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    side = exec_side
    side.clock.set(SystemClock().now())
    root = tmp_path / "checkout"
    ctx = _host(side, root)
    repo = init_git_repo(root)
    repo.add_remote("origin", "https://example.invalid/skm.git")
    revision = repo.commit_file()
    _export(root, side, revision=revision)
    _setup_manifests(root)
    settings = cast("JsonObject", ctx.config)
    for field in ("enabled", "ignores", "argv", "index_argv", "serena_schema_pin"):
        key = f"knowledge.code_graph.{field}"
        project = field in {"enabled", "ignores"}
        ctx.client.dispatch(
            SetValue.from_json(
                {
                    "scope": {
                        "level": "project" if project else "host",
                        "scope_id": str(side.proj if project else side.host1),
                    },
                    "key": key,
                    "value": settings[key],
                    "reason": "Configure Serena test checkout",
                    "confirmed": True,
                }
            )
        )
    token: Any = ctx.client.dispatch(access.CreateToken(name="CLI graph integration"))
    core = replace(side.app, authenticator=lambda secret: authenticate(side, secret))
    monkeypatch.chdir(root)
    tls = loopback_certificate(tmp_path / "tls")
    with loopback_server(lambda authority: client_api(core, authority), tls=tls) as endpoint:
        environ = _environment(
            tmp_path / "client",
            GRAPH_TOKEN=token.secret,
            SKM_HOST_ID=str(side.host1),
            SKM_PROJECT=str(side.proj),
            SKM_WORKSPACE=str(side.ws),
            **databases.machine_env,
        )

        def invoke(*args: str, error: ErrorCode | None = None) -> Any:
            out, err = StringIO(), StringIO()
            code = main(["--json", *args], stdout=out, stderr=err, environ=environ)
            output = json.loads(out.getvalue())
            if error is not None:
                assert code != 0, output
                assert output["error"]["code"] == error.value, output
                return None
            assert code == 0, out.getvalue() + err.getvalue()
            return output["result"]

        invoke("instance", "add", "graph-hub", "--mode", "http", *_remote(endpoint, tls[0], "GRAPH_TOKEN"))
        invoke("instance", "use", "graph-hub")
        scope = ["--project", str(side.proj), "--mount", "repo"]
        invoke("graph", "import-code", *scope, error=ErrorCode.CHECKOUT_UNBOUND)
        invoke("repo", "bind", *scope, "--repo", str(side.repo_id), "--write-marker", "--yes")
        location = side.client.ask(ResolveCheckout(side.proj, "repo", side.host1))
        assert isinstance(location, CheckoutLocationView)
        assert checkout_id_from_locator(location.local_locator) is not None
        assert invoke("graph", "import-code", *scope)["edges_added"] == 3
        assert invoke("graph", "derive", *scope)["source"] == "manifests"
        roots = [f"symbol:{side.repo_id}:src/app.py#{name}" for name in ("Runner.execute", "run")]
        query = [*roots, "--depth", "0", "--workspace", str(side.ws)]
        fresh = invoke("graph", "subgraph", *query, "--at-revision", "b" * 40)
        assert fresh["revision"] == revision
        assert fresh["freshness"]["state"] == "fresh"
        (root / MARKER_FILENAME).unlink()
        head = repo.commit_file(content="HEAD moved")
        stale = invoke("graph", "subgraph", *query, "--at-revision", revision)
        assert stale["freshness"]["state"] == "stale"
        assert stale["freshness"]["at_revision"] == head
        repo.runner.run(
            root, ("remote", "set-url", "origin", "https://example.invalid/other.git"), check=True
        )
        invoke("graph", "import-code", *scope, error=ErrorCode.CHECKOUT_MISMATCH)
        side.clock.advance(timedelta(days=31))
        invoke("graph", "derive", *scope, error=ErrorCode.CHECKOUT_UNBOUND)
