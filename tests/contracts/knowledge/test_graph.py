"""Exercise the registered graph operations over Memory and PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import timedelta
from itertools import pairwise
from typing import Any, Literal
from uuid import UUID

import pytest

from integration.artifacts.test_upload_flow import dispatch_new
from skm.application_bus.ports import EventReader
from skm.kernel.actor import Actor, PrincipalKind
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Forbidden, NotFound, PreconditionFailed, ValidationFailed
from skm.kernel.ids import PrincipalId, ScopeId, WorkspaceId
from skm.kernel.ports_uow import Surface
from skm.modules.access.domain.membership import Membership
from skm.modules.access.domain.principal import new_principal
from skm.modules.access.ports import MembershipRepository, PrincipalRepository
from skm.modules.access.public import Role
from skm.modules.context.ports import MemoryRetriever
from skm.modules.knowledge.application.commands import import_graph
from skm.modules.knowledge.domain.graph import EdgeType, GraphEdge, GraphEdgeId, GraphNodeId, NodeType
from skm.modules.knowledge.domain.graph_algorithms import Neighborhood
from skm.modules.knowledge.ports import GraphRepository
from skm.modules.planning.public import CreatePlan, GetPlan
from skm.modules.settings.generated.commands import SetValue, SetValueDefsScopeRef
from skm.modules.workspace.public import ArchiveProject, CreateWorkspace, GetProject, RegisterRepository
from support.pg import clean_test_database, pg_session, test_database  # noqa: F401
from support.seed import SEED

from .harness import KnowledgeSide, knowledge_side

__all__ = ["clean_test_database", "knowledge_side"]

_REV = "a" * 40


def _node(key: str, **attrs: Any) -> dict[str, Any]:
    return {"node_key": key, "type": key.partition(":")[0], "attrs": attrs}


def _edge(src: str, dst: str, key: str = "", **fields: Any) -> dict[str, Any]:
    return {"src_key": src, "dst_key": dst, "type": "references", "attrs": {}, "source_key": key, **fields}


def _import(side: KnowledgeSide, **changes: Any) -> dict[str, Any]:
    return {
        "project_id": str(side.project),
        "source": "serena",
        "repository_id": None,
        "index": {
            "revision": _REV,
            "dirty": False,
            "languages": ["python"],
            "basis_default": "lsp",
            "tool_name": "serena",
            "tool_version": "1",
            "indexed_at": side.clock.now().isoformat(),
            "completeness": "complete",
            "limitations": [],
            "files_indexed": 1,
            "files_skipped": 0,
        },
        "nodes": [],
        "edges": [],
        **changes,
    }


def _neighbors(side: KnowledgeSide, key: str, **params: Any) -> Any:
    return side.query("graph_neighbors", {"workspace_id": str(side.workspace), "node_key": key, **params})


def _setting(
    side: KnowledgeSide, scope: Literal["instance", "project"], scope_id: ScopeId, key: str, value: Any
) -> None:
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    dispatch_new(client, SetValue(SetValueDefsScopeRef(scope, scope_id), f"knowledge.graph.{key}", value))


def test_import_and_directed_queries_include_graph_provenance(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    repository = dispatch_new(client, RegisterRepository(side.workspace, "repo", None, None)).repository_id
    root = f"symbol:{repository}:src/app.py#Root"
    target = f"symbol:{repository}:src/app.py#Target"
    args = _import(
        side,
        repository_id=str(repository),
        nodes=[_node(root), _node(target)],
        edges=[_edge(root, target, "one"), _edge(root, target, "two", basis="text")],
    )
    first = side.action("import_graph", args, key="lost-import-response")
    assert first == side.action("import_graph", args, key="lost-import-response")
    assert first["generation"] == 1
    assert first["edges_added"] == 2

    out = _neighbors(side, root, at_revision=_REV)
    assert out["schema"] == "urn:skm:knowledge:graph-answer:v1"
    assert out["repository_id"] == str(repository)
    assert out["index_generation"] == 1
    assert out["revision"] == _REV
    assert out["basis"] == "text"
    assert out["languages"] == ["python"]
    assert out["relation_kind"] == "references"
    assert out["completeness"] == "complete"
    assert out["freshness"]["state"] == "fresh"
    assert len(out["edges"]) == 2
    assert {edge["basis"] for edge in out["edges"]} == {"text", "lsp"}
    assert {hit["node_key"]: hit["distance"] for hit in out["nodes"]} == {root: 0, target: 1}
    assert _neighbors(side, target)["edges"] == []
    assert len(_neighbors(side, target, direction="in")["edges"]) == 2
    assert _neighbors(side, root, depth=0)["edges"] == []
    assert _neighbors(side, root, edge_types=["uses"])["edges"] == []

    path = {"workspace_id": str(side.workspace), "src_key": target, "dst_key": root}
    assert side.query("graph_path", path)["path"] is None
    assert side.query("graph_path", {**path, "direction": "in"})["path"] == [target, root]
    summary = side.query(
        "graph_stats", {"workspace_id": str(side.workspace), "project_id": str(side.project)}
    )
    assert summary["nodes"] == summary["edges"] == []
    assert summary["stats"] == {
        "nodes_by_type": {"symbol": 2},
        "edges_by_type": {"references": 2},
        "components": 1,
        "isolated": 0,
    }
    with side.uow(readonly=True) as uow:
        events = uow.repo(EventReader).after_workspace_seq(
            side.workspace, 0, types=frozenset({"urn:skm:knowledge:event:graph-imported:v1"}), limit=10
        )
    assert len(events) == 1
    assert events[0].payload["counts"] == {
        "nodes_upserted": 2,
        "nodes_removed": 0,
        "edges_added": 2,
        "edges_removed": 0,
    }


def test_replace_retains_nodes_referenced_by_other_sources(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    root, shared, stale = "doc:root", "doc:shared", "doc:stale"
    assert (
        side.action(
            "import_graph",
            _import(
                side,
                nodes=[_node(root), _node(shared), _node(stale)],
                edges=[_edge(root, shared), _edge(root, stale)],
            ),
        )["edges_added"]
        == 2
    )
    assert (
        side.action(
            "import_graph",
            _import(side, source="other", nodes=[_node(root), _node(shared)], edges=[_edge(shared, root)]),
        )["generation"]
        == 1
    )
    replacement = _import(side, nodes=[_node(root)])
    replacement["index"]["revision"] = "b" * 40
    replaced = side.action("import_graph", replacement)
    assert (replaced["generation"], replaced["nodes_removed"], replaced["edges_removed"]) == (2, 1, 2)
    answer = _neighbors(side, shared, at_revision="b" * 40)
    assert len(answer["edges"]) == 1
    assert (answer["index_generation"], answer["revision"], answer["freshness"]["state"]) == (
        1,
        _REV,
        "stale",
    )
    mixed = _neighbors(side, root, direction="in", at_revision="b" * 40)
    assert (mixed["index_generation"], mixed["revision"], mixed["freshness"]["state"]) == (
        2,
        "b" * 40,
        "stale",
    )
    assert [(source["source"], source["generation"]) for source in mixed["sources"]] == [
        ("other", 1),
        ("serena", 1),
        ("serena", 2),
    ]
    with side.uow(readonly=True) as uow:
        repo = uow.repo(GraphRepository)
        assert repo.node_by_key(side.workspace, stale) is None
        assert repo.node_by_key(side.workspace, root) is not None
        assert repo.node_by_key(side.workspace, shared) is not None
    side.action("import_graph", _import(side, source="other"))
    assert side.action("import_graph", _import(side))["nodes_removed"] == 2


def test_append_and_concurrent_generations_preserve_edges(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    root, target = "doc:root", "doc:target"
    side.action("import_graph", _import(side, nodes=[_node(root), _node(target)]))
    chunks = [
        _import(side, replace=False, edges=[_edge(root, target, source_key)]) for source_key in ("a", "b")
    ]
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(lambda chunk: side.action("import_graph", chunk), chunks))
    assert sorted(result["generation"] for result in results) == [2, 3]
    answer = _neighbors(side, root, at_revision=_REV)
    assert len(answer["edges"]) == 2
    assert [source["generation"] for source in answer["sources"]] == [1, 2, 3]
    assert answer["freshness"]["state"] == "fresh"
    different = _import(side, replace=False, edges=[_edge(root, target, "c")])
    different["index"]["revision"] = "b" * 40
    with pytest.raises(ValidationFailed) as rejected:
        side.action("import_graph", different)
    assert rejected.value.details["reason"] == "append_snapshot_mismatch"
    assert _neighbors(side, root, at_revision=_REV) == answer
    renewed = side.action("import_graph", chunks[0])
    assert renewed["edges_added"] == renewed["edges_removed"] == 0
    generations = [source["generation"] for source in _neighbors(side, root)["sources"]]
    assert generations == [1, results[1]["generation"], 4]


def test_bounded_neighbors_and_path_report_truncation(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    keys = [f"doc:{key}" for key in "abcdef"]
    side.action(
        "import_graph",
        _import(
            side,
            nodes=[_node(key) for key in keys],
            edges=[_edge(src, dst) for src, dst in pairwise(keys)],
        ),
    )
    query = {"workspace_id": str(side.workspace), "src_key": keys[0], "dst_key": keys[-1]}
    path = side.query("graph_path", query)
    assert path["path"] is None
    assert path["completeness"] == "truncated"
    assert [(lim["code"], lim["count"]) for lim in path["limitations"]] == [("depth_limit", 1)]
    capped = _neighbors(side, keys[0], depth=8)
    assert len(capped["nodes"]) == 5
    assert capped["completeness"] == "truncated"
    assert capped["limitations"][0]["code"] == "depth_limit"
    _setting(side, "instance", SEED.instance_id, "max_nodes", 2)
    limited = _neighbors(side, keys[0], depth=3, at_revision="b" * 40)
    assert limited["completeness"] == "truncated"
    assert limited["freshness"]["state"] == "stale"
    assert {lim["code"]: lim["count"] for lim in limited["limitations"]} == {
        "node_limit": 1,
        "index_stale": None,
    }
    with side.uow(readonly=True) as uow:
        repo = uow.repo(GraphRepository)
        root = repo.node_by_key(side.workspace, keys[0])
        assert root is not None
        result = Neighborhood.from_adjacency(
            repo.neighborhood(side.workspace, (root.id,), depth=50, max_nodes=2)
        )
        assert len(result.nodes) == 2
        assert result.omitted_nodes == 1


def test_import_namespace_and_workspace_validation(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    other = side.new_project("other")
    _setting(side, "project", ScopeId(side.project), "namespaces", ["one"])
    _setting(side, "project", ScopeId(other), "namespaces", ["two"])
    side.action(
        "import_graph", _import(side, project_id=str(other), source="other", nodes=[_node("doc:other")])
    )
    args = _import(side, nodes=[_node("doc:root")], edges=[_edge("doc:root", "doc:other")])
    assert side.action("import_graph", args)["edges_added"] == 1

    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    foreign = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="foreign", title="Foreign")).workspace_id)
    foreign_project = side.new_project("isolated", foreign)
    foreign_repo = dispatch_new(client, RegisterRepository(foreign, "foreign-repo", None, None)).repository_id
    side.action("import_graph", _import(side, project_id=str(foreign_project), nodes=[_node("doc:foreign")]))
    with pytest.raises(NotFound):
        side.action("import_graph", {**args, "edges": [_edge("doc:root", "doc:foreign")]})
    with pytest.raises(NotFound):
        side.action("import_graph", {**args, "repository_id": str(foreign_repo)})
    assert _neighbors(side, "doc:root")["index_generation"] == 1

    # The repository is sufficient to resolve the owning workspace for a projectless import.
    unscoped = _import(side, project_id=None, repository_id=str(foreign_repo), nodes=[_node("doc:unscoped")])
    assert side.action("import_graph", unscoped)["generation"] == 1
    assert side.query("graph_stats", {"workspace_id": str(foreign)})["stats"]["nodes_by_type"] == {"doc": 2}


def test_import_checks_stored_endpoint_projects(
    knowledge_side: KnowledgeSide, monkeypatch: pytest.MonkeyPatch
) -> None:
    side = knowledge_side
    other = side.new_project("other")
    _setting(side, "project", ScopeId(side.project), "namespaces", ["one"])
    _setting(side, "project", ScopeId(other), "namespaces", ["two"])
    # With the catalog's shared default, force the gate to deny and observe which projects it checks.
    calls: list[tuple[frozenset[str], frozenset[str]]] = []

    def deny(src: frozenset[str], dst: frozenset[str]) -> bool:
        calls.append((src, dst))
        return False

    monkeypatch.setattr(import_graph, "link_allowed", deny)
    reference = f"project:{side.project}"
    side.action(
        "import_graph", _import(side, project_id=str(other), source="other", nodes=[_node(reference)])
    )
    denied = side.action(
        "import_graph", _import(side, nodes=[_node("doc:root")], edges=[_edge("doc:root", reference)])
    )
    assert calls == [(frozenset({"default", "one"}), frozenset({"default", "two"}))]
    assert denied["edges_added"] == 0
    assert denied["edges_rejected"] == [
        {
            "code": "GRAPH_LINK_NOT_ALLOWED",
            "src_key": "doc:root",
            "dst_key": reference,
            "type": "references",
            "source_key": "",
        }
    ]


def test_repository_replacement_is_atomic_on_foreign_endpoint(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    foreign = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="other", title="Other")).workspace_id)
    foreign_project = side.new_project("other-project", foreign)
    side.action(
        "import_graph",
        _import(side, nodes=[_node("doc:root"), _node("doc:old")], edges=[_edge("doc:root", "doc:old")]),
    )
    side.action("import_graph", _import(side, project_id=str(foreign_project), nodes=[_node("doc:remote")]))
    with side.uow() as uow:
        repo = uow.repo(GraphRepository)
        root = repo.node_by_key(side.workspace, "doc:root")
        remote = repo.node_by_key(foreign, "doc:remote")
        assert root is not None
        assert remote is not None
        draft = replace(root, id=GraphNodeId(UUID(int=909)), node_key="doc:new")
        forged = GraphEdge(
            GraphEdgeId(UUID(int=910)),
            side.workspace,
            draft.id,
            remote.id,
            EdgeType.REFERENCES,
            {},
            "serena",
            None,
            "",
            None,
        )
        with pytest.raises(NotFound):
            repo.replace_from_source(side.workspace, "serena", None, (draft,), (forged,))
        assert repo.node_by_key(side.workspace, "doc:new") is None
        assert repo.node_by_key(side.workspace, "doc:old") is not None
        assert repo.node_by_key(foreign, "doc:remote") == remote
        assert (
            len(
                Neighborhood.from_adjacency(
                    repo.neighborhood(side.workspace, (root.id,), depth=1, max_nodes=4)
                ).edges
            )
            == 1
        )
        uow.commit()


def _reader(side: KnowledgeSide) -> Actor:
    reader = Actor(PrincipalId(UUID(int=920)), PrincipalKind.HUMAN, "graph-reader")
    with side.uow() as uow:
        uow.repo(PrincipalRepository).add(
            new_principal(
                principal_id=reader.principal_id,
                kind=reader.kind,
                display_name=reader.display_name,
                created_by=side.owner.principal_id,
                now=side.clock.now(),
            )
        )
        uow.repo(MembershipRepository).upsert(
            Membership(ScopeId(side.workspace), reader.principal_id, Role.VIEWER, None, side.clock.now())
        )
        uow.commit()
    return reader


def test_hidden_nodes_do_not_affect_visible_traversal(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    foreign = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="private", title="Private")).workspace_id)
    project = side.new_project("private-project", foreign)
    reader = _reader(side)
    root, target, isolated = "doc:root", "doc:target", "doc:isolated"
    side.action(
        "import_graph",
        _import(side, nodes=list(map(_node, (root, target, isolated))), edges=[_edge(root, target)]),
    )
    _setting(side, "instance", SEED.instance_id, "max_nodes", 2)
    scope = {"workspace_id": str(side.workspace)}

    def answers() -> tuple[Any, ...]:
        return (
            side.query("graph_neighbors", {**scope, "node_key": root, "depth": 8}, actor=reader),
            side.query("graph_path", {**scope, "src_key": root, "dst_key": target}, actor=reader),
            side.query("graph_path", {**scope, "src_key": root, "dst_key": isolated}, actor=reader),
            side.query("graph_stats", scope, actor=reader),
        )

    baseline = answers()
    assert {node["node_key"] for node in baseline[0]["nodes"]} == {root, target}
    assert baseline[0]["limitations"] == []
    assert baseline[1]["path"] == [root, target]
    assert baseline[2]["path"] is None
    assert baseline[3]["limitations"][0]["count"] == 1
    _setting(side, "instance", SEED.instance_id, "max_nodes", 20)
    ample = answers()
    _setting(side, "instance", SEED.instance_id, "max_depth", 1)
    shallow = answers()
    assert shallow[0]["limitations"] == []

    # Model an existing workspace-local row whose typed reference is hidden from the reader.
    hidden_key = f"project:{project.hex.upper()}"
    with side.uow() as uow:
        repo = uow.repo(GraphRepository)
        first = repo.node_by_key(side.workspace, root)
        second = repo.node_by_key(side.workspace, target)
        last = repo.node_by_key(side.workspace, isolated)
        assert first is not None
        assert second is not None
        assert last is not None
        hidden = replace(
            first, id=GraphNodeId(UUID(int=1)), node_key=hidden_key, type=NodeType.PROJECT, source="legacy"
        )
        edges = tuple(
            GraphEdge(
                GraphEdgeId(UUID(int=idx)),
                side.workspace,
                src.id,
                dst.id,
                EdgeType.REFERENCES,
                {},
                "legacy",
                None,
                "",
                None,
            )
            for idx, (src, dst) in enumerate(((first, hidden), (second, hidden), (hidden, last)), 2)
        )
        repo.replace_from_source(side.workspace, "legacy", None, (hidden,), edges)
        uow.commit()

    assert answers() == shallow
    _setting(side, "instance", SEED.instance_id, "max_depth", 4)
    assert answers() == ample
    _setting(side, "instance", SEED.instance_id, "max_nodes", 2)
    assert answers() == baseline
    with pytest.raises(NotFound):
        side.query("graph_neighbors", {**scope, "node_key": hidden_key}, actor=reader)


def test_knowledge_04_imported_link_cannot_dereference_or_delete_foreign_project(
    knowledge_side: KnowledgeSide,
) -> None:
    side = knowledge_side
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    foreign = WorkspaceId(dispatch_new(client, CreateWorkspace(slug="private", title="Private")).workspace_id)
    project = side.new_project("private-project", foreign)
    reader = _reader(side)
    reader_client = side.app.client(actor=reader, surface=Surface.TEST)
    original = client.ask(GetProject(project_id=project))
    plan_id = dispatch_new(client, CreatePlan(project_id=project, title="Private plan")).plan_id
    plan = GetPlan(plan_id=plan_id)
    original_plan = client.ask(plan)
    side.remember(project_id=str(project), body="Private build status")
    with pytest.raises(Forbidden) as plan_before:
        reader_client.ask(plan)
    with pytest.raises(Forbidden) as before:
        reader_client.ask(GetProject(project_id=project))

    reference = f"project:{project}"
    root = "doc:root"
    plan_reference = f"entity:{plan_id}"
    # Both node keys are importer-controlled. The plan reference is stored as an opaque graph label.
    imported = side.action(
        "import_graph",
        _import(
            side,
            nodes=[_node(root), _node(reference, workspace_id=str(side.workspace)), _node(plan_reference)],
            edges=[_edge(root, reference), _edge(root, plan_reference, type="depends_on")],
        ),
    )
    assert imported["edges_rejected"][0]["code"] == "GRAPH_LINK_NOT_ALLOWED"
    ask = {"workspace_id": str(side.workspace), "node_key": root}
    visible = side.query("graph_neighbors", ask, actor=reader)
    assert {hit["node_key"] for hit in visible["nodes"]} == {root, plan_reference}
    assert [edge["dst_key"] for edge in visible["edges"]] == [plan_reference]
    with pytest.raises(NotFound):
        side.query("graph_neighbors", {**ask, "node_key": reference}, actor=reader)
    with pytest.raises(Forbidden) as after:
        reader_client.ask(GetProject(project_id=project))
    assert before.value.code == after.value.code
    with pytest.raises(Forbidden) as plan_after:
        reader_client.ask(plan)
    assert plan_before.value.code == plan_after.value.code
    with side.uow(readonly=True) as uow:
        retriever = side.app.gateways.get(MemoryRetriever)
        assert retriever.search(
            uow, actor=side.owner, project_id=project, workspace_id=foreign, query="", top_k=2
        )
        assert not retriever.search(
            uow, actor=reader, project_id=project, workspace_id=foreign, query="", top_k=2
        )
        assert not retriever.search(
            uow,
            actor=reader,
            project_id=project,
            workspace_id=side.workspace,
            query="",
            top_k=2,
        )

    assert side.action("import_graph", _import(side))["nodes_removed"] == 3
    assert client.ask(GetProject(project_id=project)) == original
    assert client.ask(plan) == original_plan


def test_import_size_active_project_and_atomic_rollback(knowledge_side: KnowledgeSide) -> None:
    side = knowledge_side
    _setting(side, "instance", SEED.instance_id, "import_max_bytes", 1048576)
    with pytest.raises(ValidationFailed) as oversized:
        side.action("import_graph", _import(side, nodes=[_node("doc:large", value="é" * 530000)]))
    assert oversized.value.details["reason"] == "too_large"

    root = "doc:root"
    side.action("import_graph", _import(side, nodes=[_node(root)]))
    invalid = _import(side, nodes=[_node("doc:replacement")])
    invalid["index"]["revision"] = "invalid"
    with pytest.raises(ValidationFailed):
        side.action("import_graph", invalid)
    assert _neighbors(side, root)["index_generation"] == 1
    with pytest.raises(NotFound):
        _neighbors(side, "doc:replacement")
    side.clock.advance(timedelta(hours=25))
    assert _neighbors(side, root)["freshness"]["state"] == "stale"
    client = side.app.client(actor=side.owner, surface=Surface.TEST)
    dispatch_new(client, ArchiveProject(side.project, 1, "retired"))
    with pytest.raises(PreconditionFailed) as archived:
        side.action("import_graph", _import(side))
    assert archived.value.code == ErrorCode.PROJECT_ARCHIVED
