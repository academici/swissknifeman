"""Workspace read isolation and HTTP admission with real scoped credentials (S1/S3/S4/SURF-17)."""

from pathlib import Path
from typing import cast
from uuid import UUID

import pytest

from integration.api.test_workspace_routes import client as client
from integration.api.test_workspace_routes import created, workspace
from integration.api.test_workspace_routes import world as world
from integration.artifacts.test_upload_flow import audit_rows
from security.api.harness import TestClient, World
from security.test_blob_access import assert_private_output, denial_checks
from skm.kernel.ports_uow import Surface
from skm.modules.access import public as access
from support.pg import TestDatabase
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

SCHEMAS = ("access", "workspace", "artifacts")


def _denial_count(world: World, dsn: str | None, actor_id: UUID, action: str) -> int:
    return sum(
        (observed, decision, principal_id) == (action, "denied", actor_id)
        for observed, decision, principal_id, _ in audit_rows(world.core, dsn)
    )


def _dsn(world: World, request: pytest.FixtureRequest) -> str | None:
    if world.backend is None:
        database: TestDatabase = request.getfixturevalue("clean_test_database")
        return database.dsn
    return None


def test_workspace_member_reads_sibling_projects_but_cannot_cross_workspace(
    client: TestClient,
    world: World,
    request: pytest.FixtureRequest,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first, second = workspace(client, "first"), workspace(client, "second")
    private = "private-sibling-workspace-project-6193"
    own = [
        created(client.post(f"/api/v1/workspaces/{first}/projects", json={"slug": slug, "title": slug}))
        for slug in ("own-one", "own-two")
    ]
    foreign = created(
        client.post(
            f"/api/v1/workspaces/{second}/projects", json={"slug": "foreign-project", "title": private}
        )
    )
    owner = world.core.client(actor=world.core.authenticate(world.secret), surface=Surface.CLI)
    principal = cast(
        "access.CreatePrincipalResult",
        owner.dispatch(access.CreatePrincipal.from_json({"kind": "human", "display_name": "first viewer"})),
    )
    for scope_id in (first, own[0]["project_id"]):
        owner.dispatch(
            access.GrantMembership.from_json(
                {"scope_id": scope_id, "principal_id": str(principal.principal_id), "role": "viewer"}
            )
        )
    token = cast(
        "access.CreateTokenResult",
        owner.dispatch(
            access.CreateToken(
                "workspace reader",
                principal_id=principal.principal_id,
                permissions=("token.own", "workspace.read", "project.read"),
            )
        ),
    )
    headers = {"Authorization": f"Bearer {token.secret}"}
    dsn = _dsn(world, request)
    markers = (private, token.secret, world.secret)
    with denial_checks(
        world.core,
        tmp_path,
        dsn=dsn,
        schemas=SCHEMAS,
        capsys=capsys,
        private=markers,
    ) as check:
        visible = client.get("/api/v1/workspaces", headers=headers)
        sibling = client.get(f"/api/v1/projects/{own[1]['project_id']}", headers=headers)
        listing = client.get(f"/api/v1/workspaces/{first}/projects", headers=headers)
        check(tuple((res.text, res.headers) for res in (visible, sibling, listing)))
    assert visible.status_code == sibling.status_code == listing.status_code == 200
    assert {item["workspace_id"] for item in visible.json()["items"]} == {first}
    assert sibling.json()["project_id"] == own[1]["project_id"]
    assert {item["project_id"] for item in listing.json()["items"]} == {item["project_id"] for item in own}
    assert_private_output(
        (visible.text, listing.text, sibling.text), private, token.secret, world.secret, second
    )

    path = f"/api/v1/projects/{foreign['project_id']}"
    attempts = [
        ("GET", path, "workspace.get_project", {}),
        ("GET", f"/api/v1/workspaces/{second}/projects", "workspace.list_projects", {}),
        ("POST", path + "/archive", "workspace.archive_project", {"json": {"reason": "no access"}}),
    ]
    for method, url, action, extra in attempts:
        before = _denial_count(world, dsn, principal.principal_id, action)
        with denial_checks(
            world.core,
            tmp_path,
            dsn=dsn,
            schemas=SCHEMAS,
            capsys=capsys,
            private=markers,
            audit=(action,),
        ) as check:
            response = client.request(method, url, headers={**headers, "If-Match": 'W/"v1"'}, **extra)
            check((response.text, response.headers))
        assert response.status_code in {403, 404}
        assert response.json()["code"] in {"FORBIDDEN", "NOT_FOUND"}
        assert not {"items", "project_id", "row_version"} & response.json().keys()
        assert _denial_count(world, dsn, principal.principal_id, action) == before + 1
    retained = client.get(path).json()
    assert (retained["row_version"], retained["state"], retained["title"]) == (1, "active", private)


@pytest.mark.parametrize(
    ("headers", "status", "code"),
    [
        ({"Authorization": ""}, 401, "UNAUTHENTICATED"),
        ({"Origin": "https://foreign.example"}, 403, "ORIGIN_REJECTED"),
    ],
)
def test_http_checks_credentials_and_origin_before_workspace_mutations(
    client: TestClient,
    world: World,
    request: pytest.FixtureRequest,
    tmp_path: Path,
    headers: dict[str, str],
    status: int,
    code: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    dsn = _dsn(world, request)
    title = "private-cross-origin-marker-4268"
    with denial_checks(
        world.core,
        tmp_path,
        dsn=dsn,
        schemas=SCHEMAS,
        capsys=capsys,
        private=(title, world.secret),
    ) as check:
        response = client.post(
            "/api/v1/workspaces", headers=headers, json={"slug": "cross-origin", "title": title}
        )
        check((response.text, response.headers))
    assert (response.status_code, response.json()["code"]) == (status, code)
    assert "workspace_id" not in response.json()
