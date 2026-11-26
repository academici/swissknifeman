"""Knowledge contract fixture over the real Memory and PostgreSQL app compositions."""

import itertools
from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest

from fakes.clock import FrozenClock
from integration.artifacts.test_upload_flow import dispatch_new, open_test_app, seed_principals
from skm.bootstrap.composition import App
from skm.kernel.actor import Actor
from skm.kernel.ids import ProjectId, WorkspaceId
from skm.kernel.json_types import JsonValue
from skm.kernel.ports_uow import RequestMeta, Surface, UnitOfWork
from skm.modules.workspace.public import CreateProject, CreateWorkspace
from support.pg import TestDatabase


@dataclass
class KnowledgeSide:
    backend: str
    app: App
    clock: FrozenClock
    owner: Actor
    workspace: WorkspaceId
    project: ProjectId
    requests: Iterator[int]

    def uow(self, *, readonly: bool = False) -> UnitOfWork:
        return self.app.uow_factory(self.meta(), readonly=readonly)

    def meta(self, key: str | None = None) -> RequestMeta:
        return RequestMeta(f"req_{next(self.requests):026}", Surface.TEST, key, self.clock.now())

    def action(
        self, name: str, args: Mapping[str, JsonValue], *, key: str | None = None, actor: Actor | None = None
    ) -> Any:
        spec = self.app.bus._registry.command_by_name(f"knowledge.{name}")
        key = key or f"knowledge-{next(self.requests)}"
        return self.app.bus.dispatch(spec.dto.from_json(args), actor=actor or self.owner, meta=self.meta(key))

    def query(self, name: str, args: Mapping[str, JsonValue], *, actor: Actor | None = None) -> Any:
        spec = self.app.bus._registry.query_by_name(f"knowledge.{name}")
        return self.app.bus.ask(spec.dto.from_json(args), actor=actor or self.owner, meta=self.meta())

    def remember(self, **kwargs: Any) -> Any:
        return self.action(
            "remember",
            {
                "project_id": str(self.project),
                "kind": "fact",
                "body": "Temporary pool status",
                "ttl_hours": None,
                "source": "api",
                **kwargs,
            },
        )

    def new_project(self, slug: str, workspace: WorkspaceId | None = None) -> ProjectId:
        client = self.app.client(actor=self.owner, surface=Surface.TEST)
        result = dispatch_new(
            client, CreateProject(workspace_id=workspace or self.workspace, slug=slug, title=slug)
        )
        return ProjectId(result.project_id)


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def knowledge_side(request: pytest.FixtureRequest, tmp_path: Path) -> Iterator[KnowledgeSide]:
    backend = str(request.param)
    dsn = None
    if backend == "postgres":
        dsn = cast("TestDatabase", request.getfixturevalue("clean_test_database")).dsn
    app, clock, _ = open_test_app(backend, tmp_path, dsn, max_uow=4)
    try:
        owner = seed_principals(app, backend)
        client = app.client(actor=owner, surface=Surface.TEST)
        workspace = WorkspaceId(
            dispatch_new(client, CreateWorkspace(slug="knowledge", title="Knowledge")).workspace_id
        )
        project = ProjectId(
            dispatch_new(
                client, CreateProject(workspace_id=workspace, slug="initial", title="Initial")
            ).project_id
        )
        assert isinstance(workspace, UUID)
        yield KnowledgeSide(backend, app, clock, owner, workspace, project, itertools.count(1))
    finally:
        app.close()
