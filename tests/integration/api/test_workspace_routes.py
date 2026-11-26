"""Real HTTP routing against the memory and migrated PostgreSQL application buses."""

from uuid import UUID, uuid4

import pytest

from architecture.test_surface_coverage import SURFACES
from security.api.harness import BASE, TestClient, make_world
from skm.adapters.memory.core.idempotency import MemoryIdempotencyStore
from skm.adapters.postgres.core.idempotency import PostgresIdempotencyStore
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.ports_uow import Surface
from skm.modules.access.public import RevokeMembership
from skm.modules.workspace.public import checkout_locator
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database

MODULES = ("access", "settings", "workspace", "artifacts")
PLATFORM = {"os": "linux", "arch": "x86_64"}


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def world(request, tmp_path):
    database = request.getfixturevalue("clean_test_database").dsn if request.param == "postgres" else None
    instance = make_world(tmp_path, database=database)
    try:
        yield instance
    finally:
        instance.core.close()


def application(world):
    return create_app(
        world.core,
        route_table=build_route_table(MODULES),
        registry=world.core.bus._registry,
        no_background=True,
    )


@pytest.fixture
def client(world):
    with TestClient(application(world), base_url=BASE, headers=world.headers) as client:
        yield client


def created(response):
    assert response.status_code == 201, response.text
    return response.json()


def workspace(client, slug="example"):
    return created(client.post("/api/v1/workspaces", json={"slug": slug, "title": slug}))["workspace_id"]


def host(client):
    return created(client.post("/api/v1/hosts", json={"name": "laptop", "platform": PLATFORM}))["host_id"]


def test_enabled_module_discovery_matches_every_json_surface():
    special = {"artifacts.record_staged_blob", "artifacts.open_file_version_content"}
    for module in MODULES:
        expected = {
            (name, method, path)
            for name, (owner, routes) in SURFACES.items()
            if name.startswith(module + ".")
            and name not in special
            and (
                owner == "P11.02.b"
                or name in {"artifacts.find_orphan_blobs", "artifacts.prune_orphan_objects"}
            )
            for method, path in routes
        }
        assert {(r.bus_name, r.method, r.path) for r in build_route_table([module]).describe()} == expected
    assert build_route_table([]).describe() == ()


def test_project_replay_cas_and_keyset_pagination(client):
    ws = workspace(client)
    path = f"/api/v1/workspaces/{ws}/projects"
    headers = {"Idempotency-Key": "project-repeat"}
    body = {"slug": "bravo", "title": "Bravo"}
    first = client.post(path, json=body, headers=headers)
    project = created(first)
    assert first.headers["ETag"] == 'W/"v1"'
    assert created(client.post(path, json=body, headers=headers)) == project
    conflict = client.post(path, json={**body, "title": "Different"}, headers=headers)
    assert (conflict.status_code, conflict.json()["code"]) == (409, "IDEMPOTENCY_KEY_REUSED")
    created(client.post(path, json={"slug": "delta", "title": "Delta"}))
    first_page = client.get(path, params={"limit": 1}).json()
    assert [p["slug"] for p in first_page["items"]] == ["bravo"]
    for slug in ("alpha", "charlie"):
        created(client.post(path, json={"slug": slug, "title": slug}))
    rest = client.get(path, params={"after": first_page["next"]}).json()
    assert [p["slug"] for p in rest["items"]] == ["charlie", "delta"]
    resource = f"/api/v1/projects/{project['project_id']}"
    cached = client.get(resource, headers={"If-None-Match": first.headers["ETag"]})
    assert (cached.status_code, cached.content) == (304, b"")
    archive = resource + "/archive"
    reason = {"reason": "completed"}
    assert client.post(archive, json=reason).status_code == 428
    changed = client.post(archive, json=reason, headers={"If-Match": 'W/"v1"'})
    assert (changed.status_code, changed.headers["ETag"]) == (200, 'W/"v2"')
    stale = client.post(archive, json=reason, headers={"If-Match": 'W/"v1"'})
    assert (stale.status_code, stale.json()["code"]) == (409, "VERSION_CONFLICT")


def test_match_then_bind_and_verify_checkout(client):
    ws, host_id = workspace(client), host(client)
    path = f"/api/v1/workspaces/{ws}/repositories"
    remote = "https://github.com/example/project.git"
    repo = created(client.post(path, json={"title": "Project", "remote_url": remote, "external_id": None}))
    checkout = checkout_locator(uuid4())
    facts = {
        "host_id": host_id,
        "observed_toplevel": checkout,
        "observed_remotes": ["github.com/example/project"],
        "observed_head": "a" * 40,
    }
    match = client.post(
        "/api/v1/checkout-bindings/match",
        json={
            **facts,
            "workspace_id": ws,
            "observed_exists": True,
            "observed_marker": None,
            "assume_yes": True,
        },
    )
    assert match.status_code == 200, match.text
    assert match.json()["repository_id"] == repo["repository_id"]
    bind = {
        **facts,
        "repository_id": repo["repository_id"],
        "local_locator": checkout,
        "observed_dirty": False,
        "observed_at": "2026-11-18T00:00:00Z",
    }
    private = "/srv/private-checkout"
    refused = client.post(
        "/api/v1/checkout-bindings",
        json={**bind, "local_locator": private, "observed_toplevel": private},
    )
    assert refused.status_code == 422
    assert private not in refused.text
    binding = created(client.post("/api/v1/checkout-bindings", json=bind))
    assert binding["row_version"] == 1
    verify = f"/api/v1/checkout-bindings/{binding['binding_id']}/verification"
    report = {key: value for key, value in bind.items() if key.startswith("observed_")}
    response = client.post(verify, json={**report, "observed_exists": True}, headers={"If-Match": 'W/"v1"'})
    assert response.status_code == 200, response.text
    assert response.json()["state"] == "active"


@pytest.mark.parametrize("operation", ["bind", "verify"])
def test_checkout_receipts_require_current_workspace_permission(client, world, monkeypatch, operation):
    ws, host_id = workspace(client), host(client)
    other_ws = workspace(client, "other")
    repo = created(
        client.post(
            f"/api/v1/workspaces/{ws}/repositories",
            json={
                "title": "Project",
                "remote_url": "https://example.com/group/project.git",
                "external_id": None,
            },
        )
    )
    principal = created(client.post("/api/v1/principals", json={"kind": "human", "display_name": "Binder"}))
    for target in (ws, other_ws):
        created(
            client.post(
                "/api/v1/memberships",
                json={"scope_id": target, "principal_id": principal["principal_id"], "role": "member"},
            )
        )

    def token(name, **restrictions):
        return created(
            client.post(
                "/api/v1/tokens",
                json={"name": name, "principal_id": principal["principal_id"], **restrictions},
            )
        )

    credential = token("checkout-original")
    bind_path = "/api/v1/checkout-bindings"
    checkout = checkout_locator(uuid4())
    facts = {
        "observed_toplevel": checkout,
        "observed_remotes": ["example.com/group/project"],
        "observed_head": "b" * 40,
        "observed_dirty": False,
        "observed_at": "2026-11-18T00:00:00Z",
    }
    bind_body = {
        **facts,
        "host_id": host_id,
        "repository_id": repo["repository_id"],
        "local_locator": checkout,
    }
    key = f"current-permission-{operation}"
    if operation == "bind":
        path, body, request_headers, bus_name = bind_path, bind_body, {}, "workspace.bind_checkout"
    else:
        binding = created(client.post(bind_path, json=bind_body))
        path = f"{bind_path}/{binding['binding_id']}/verification"
        body = {**facts, "observed_exists": True}
        request_headers = {"If-Match": 'W/"v1"'}
        bus_name = "workspace.record_checkout_verification"

    def replay(secret, *, payload=body):
        return client.post(
            path,
            json=payload,
            headers={**request_headers, "Idempotency-Key": key, "Authorization": f"Bearer {secret}"},
        )

    first = replay(credential["secret"])
    assert first.status_code == (201 if operation == "bind" else 200), first.text
    rotation = client.post(f"/api/v1/tokens/{credential['token_id']}/rotate", json={"grace_minutes": 0})
    assert rotation.status_code == 200, rotation.text
    rotated = rotation.json()["secret"]
    assert replay(rotated).json() == first.json()
    different = replay(rotated, payload={**body, "observed_head": "c" * 40})
    assert (different.status_code, different.json()["code"]) == (409, "IDEMPOTENCY_KEY_REUSED")

    narrowed = token(
        "checkout-other-workspace", scope_id=other_ws, permissions=["token.own", "checkout.bind"]
    )
    wrong_scope = replay(narrowed["secret"])
    assert (wrong_scope.status_code, wrong_scope.json()["code"]) == (403, "FORBIDDEN")
    assert wrong_scope.json()["details"]["scope_id"] == ws

    owner = world.core.client(actor=world.core.authenticate(world.secret), surface=Surface.TEST)
    withdraw = RevokeMembership(scope_id=UUID(ws), principal_id=UUID(principal["principal_id"]))
    store = MemoryIdempotencyStore if world.backend is not None else PostgresIdempotencyStore
    get_receipt = store.get
    reads = 0

    def miss_first_receipt(self, workspace_id, principal_id, bus_operation, receipt_key):
        nonlocal reads
        if (bus_operation, receipt_key) == (bus_name, key):
            reads += 1
            if reads == 1:
                return None
        return get_receipt(self, workspace_id, principal_id, bus_operation, receipt_key)

    # Simulate the duplicate's first lookup occurring before the winning receipt was committed.
    with monkeypatch.context() as patch:
        patch.setattr(store, "get", miss_first_receipt)
        assert replay(rotated).json() == first.json()
        assert reads == 2
        reads = 0
        replay_receipt = world.core.bus._replay_receipt

        def withdraw_before_second_read(*args, **kwargs):
            owner.dispatch(withdraw)
            return replay_receipt(*args, **kwargs)

        patch.setattr(world.core.bus, "_replay_receipt", withdraw_before_second_read)
        after_conflict = replay(rotated)
        assert reads == 2
        assert (after_conflict.status_code, after_conflict.json()["code"]) == (403, "FORBIDDEN")

    assert client.get("/api/v1/me", headers={"Authorization": f"Bearer {rotated}"}).status_code == 200
    after_revocation = replay(rotated)
    assert (after_revocation.status_code, after_revocation.json()["code"]) == (403, "FORBIDDEN")
    assert after_revocation.json()["details"]["scope_id"] == ws
