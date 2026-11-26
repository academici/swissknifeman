"""Request paths and preconditions selected by DTO values on aliased routes."""

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

import httpx
import pytest

from integration.http.test_client import client_factory, routes
from skm.entrypoints.api.etag import encode_etag
from skm.kernel.errors import NotFound
from skm.modules.artifacts import public as artifacts
from skm.modules.integrations import public as integrations
from skm.modules.knowledge import public as knowledge
from skm.modules.planning import public as planning

__all__ = ["client_factory"]

_PLAN, _DRAFT, _REV = UUID(int=101), UUID(int=102), UUID(int=103)
_DIGEST = "sha256:" + 64 * "a"


def _check_wire(client_factory: Any, dto: Any, method: str, path: str, *, version: int | None = None) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        assert (request.method, request.url.path) == (method, "/api/v1" + path)
        assert request.headers.get("If-Match") == (encode_etag(version) if version is not None else None)
        route, params = routes().match(request.method, request.url.path)
        body = json.loads(request.content) if request.content else {}
        reconstructed = route.bind(body, params, request.url.params, version=version)
        assert reconstructed.to_json() == dto.to_json()
        return httpx.Response(
            404,
            headers={"Content-Type": "application/problem+json"},
            json={"code": "NOT_FOUND", "detail": "checked request"},
        )

    client = client_factory(handle)
    operation: Callable[..., object] = client.ask if method == "GET" else client.dispatch
    with pytest.raises(NotFound, match="checked request"):
        operation(dto)


@pytest.mark.parametrize(
    ("query", "suffix"),
    [
        (
            planning.DiffRevisions(_PLAN, draft_id=_DRAFT, from_revision_id=_REV, expected_edit_version=3),
            f"drafts/{_DRAFT}/diff",
        ),
        (
            planning.GetEntity(_PLAN, "P1.1", draft_id=_DRAFT, expected_edit_version=3),
            f"drafts/{_DRAFT}/entities/P1.1",
        ),
        (
            planning.ReadyPreview(_PLAN, draft_id=_DRAFT, expected_edit_version=3),
            f"drafts/{_DRAFT}/ready-preview",
        ),
        (planning.PlanStats(_PLAN, draft_id=_DRAFT, expected_edit_version=3), f"drafts/{_DRAFT}/stats"),
        (planning.ExportSpecification(_PLAN, revision_id=_REV), f"revisions/{_REV}/export"),
        (planning.ListEntities(_PLAN, draft_id=_DRAFT, expected_edit_version=3), "entities"),
        (planning.ReadText(_PLAN, "P1.1", "/summary", revision_id=_REV), "text"),
    ],
)
def test_planning_read_routes(client_factory: Any, query: object, suffix: str) -> None:
    _check_wire(client_factory, query, "GET", f"/plans/{_PLAN}/{suffix}")


@pytest.mark.parametrize(
    ("method", "field"), [("PUT", "document"), ("PATCH", "merge_patch"), ("POST", "changes")]
)
def test_save_draft_routes(client_factory: Any, method: str, field: str) -> None:
    values = {
        "document": json.loads(Path("tests/fixtures/planning/valid/minimal.json").read_text()),
        "merge_patch": {},
        "changes": [{"op": "remove", "target": "P1.1"}],
    }
    command = planning.SaveDraft.from_json(
        {"plan_id": str(_PLAN), "draft_id": str(_DRAFT), "expected_edit_version": 3, field: values[field]}
    )
    path = f"/plans/{_PLAN}/drafts/{_DRAFT}" + ("/changes" if field == "changes" else "")
    _check_wire(client_factory, command, method, path, version=3)


@pytest.mark.parametrize("version", [None, 3])
def test_projection_routes(client_factory: Any, version: int | None) -> None:
    command = integrations.RecordProjectionApplied(
        _PLAN, _DRAFT, "cursor", _DIGEST, _DIGEST, "1.0", version, (), (), (), (), (), ()
    )
    path = f"/projects/{_PLAN}/projections" + ("/applied" if version is not None else "")
    _check_wire(client_factory, command, "POST", path, version=version)


@pytest.mark.parametrize("project", [None, _PLAN])
def test_file_routes(client_factory: Any, project: UUID | None) -> None:
    command = artifacts.AddFile.from_json(
        {
            "workspace_id": str(_REV),
            "project_id": str(project) if project else None,
            "title": "File",
            "original_filename": "test.txt",
            "origin": "upload",
            "source": {"kind": "upload"},
            "blob": {
                "staged_blob_id": str(_DRAFT),
                "workspace_id": str(_REV),
                "digest": _DIGEST,
                "size": 1,
                "media_type": "text/plain",
            },
        }
    )
    path = f"/projects/{project}/files" if project else f"/workspaces/{_REV}/files"
    _check_wire(client_factory, command, "POST", path)


def test_knowledge_search_route(client_factory: Any) -> None:
    query = knowledge.SearchMemory.from_json(
        {"project_id": str(_PLAN), "query": "pool", "scope": {"kind": "namespace", "namespace": "team"}}
    )
    _check_wire(client_factory, query, "GET", f"/projects/{_PLAN}/memory")


def test_knowledge_deprecate_route(client_factory: Any) -> None:
    command = knowledge.DeprecateLesson.from_json(
        {
            "workspace_id": str(_PLAN),
            "lesson_id": str(_DRAFT),
            "reason": "Retired",
            "expected_row_version": 3,
        }
    )
    _check_wire(client_factory, command, "POST", f"/workspaces/{_PLAN}/lessons/{_DRAFT}/deprecate", version=3)


@pytest.mark.parametrize(
    ("operation", "suffix", "fields"),
    [
        (
            knowledge.GraphNeighbors,
            "neighbors",
            {"node_key": "doc:src/main.py", "depth": 2, "edge_types": ["uses", "references"]},
        ),
        (
            knowledge.GraphPath,
            "path",
            {"src_key": "doc:src/main.py", "dst_key": "doc:src/lib.py", "direction": "both"},
        ),
        (knowledge.GraphPath, "path", {"src_key": "doc:a", "dst_key": "doc:b", "edge_types": []}),
        (knowledge.GraphStats, "stats", {"project_id": str(_DRAFT)}),
        (
            knowledge.GraphSubgraph,
            "subgraph",
            {"roots": ["doc:src/a.py", "doc:src/b.py"], "depth": 0, "edge_types": ["references"]},
        ),
        (knowledge.ListGraphIndexes, "indexes", {"repository_id": str(_DRAFT), "source": "serena"}),
    ],
)
def test_knowledge_graph_read_routes(client_factory: Any, operation: Any, suffix: str, fields: dict) -> None:
    query = operation.from_json({"workspace_id": str(_PLAN), **fields})
    _check_wire(client_factory, query, "GET", f"/workspaces/{_PLAN}/graph/{suffix}")
