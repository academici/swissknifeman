"""Integration tests for I-10.2 M0-M3 HTTP API endpoints (runtimes, hosts, pairing, project config CAS)."""

from __future__ import annotations

from pathlib import Path

from security.api.harness import BASE, TestClient, World, make_world
from skm.bootstrap.builtins import builtin_runtime_data
from skm.bootstrap.plugins import capability_catalog
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import build_route_table
from skm.modules.runtimes.ports import CapabilityCatalog


def _hub_client(tmp_path: Path) -> tuple[World, TestClient]:
    world = make_world(tmp_path, gateways={CapabilityCatalog: capability_catalog((), builtin_runtime_data())})
    api = create_app(
        world.core,
        route_table=build_route_table(MODULE_IDS),
        registry=world.core.bus._registry,
        no_background=True,
    )
    return world, TestClient(api, base_url=BASE, headers=world.headers)


def _create_workspace_and_project(client: TestClient) -> tuple[str, str]:
    ws_resp = client.post("/api/v1/workspaces", json={"slug": "hub-ws", "title": "Hub Workspace"})
    assert ws_resp.status_code == 201, ws_resp.text
    ws_id = ws_resp.json()["workspace_id"]
    proj_resp = client.post(
        f"/api/v1/workspaces/{ws_id}/projects",
        json={"slug": "hub-proj", "title": "Hub Project"},
    )
    assert proj_resp.status_code == 201, proj_resp.text
    return ws_id, proj_resp.json()["project_id"]


def test_m0_m3_runtimes_hosts_principals_and_tokens_endpoints(tmp_path: Path) -> None:
    world, client = _hub_client(tmp_path)
    try:
        with client:
            _create_workspace_and_project(client)

            # Principals & tokens
            principals = client.get("/api/v1/principals")
            assert principals.status_code == 200
            assert len(principals.json()["items"]) >= 1

            # Hosts: register, list, get
            reg_host = client.post(
                "/api/v1/hosts",
                json={
                    "name": "hub-node-1",
                    "platform": {"os": "linux", "arch": "x86_64"},
                },
            )
            assert reg_host.status_code == 201, reg_host.text
            host_id = reg_host.json()["host_id"]

            hosts = client.get("/api/v1/hosts")
            assert hosts.status_code == 200
            assert any(item["host_id"] == host_id for item in hosts.json()["items"])

            host_detail = client.get(f"/api/v1/hosts/{host_id}")
            assert host_detail.status_code == 200
            assert host_detail.json()["name"] == "hub-node-1"

            # Runtimes catalog & models
            runtimes = client.get("/api/v1/runtimes", params={"host_id": host_id})
            assert runtimes.status_code == 200, runtimes.text
            assert runtimes.json()["items"]

            models = client.get("/api/v1/runtimes/models")
            assert models.status_code == 200, models.text
            assert "models" in models.json()
    finally:
        world.core.close()


def test_pairing_issue_and_exchange_over_http(tmp_path: Path) -> None:
    world, client = _hub_client(tmp_path)
    try:
        with client:
            ws_id, _ = _create_workspace_and_project(client)

            # Unauthenticated pairing issuance is rejected
            unauth = client.post(
                "/api/v1/auth/pairing",
                json={"workspace_id": ws_id},
                headers={"Authorization": ""},
            )
            assert unauth.status_code == 401

            # Owner issues a personal pairing token
            issued = client.post(
                "/api/v1/auth/pairing",
                json={
                    "workspace_id": ws_id,
                    "principal_id": str(world.owner.principal_id),
                    "scope_grants": {ws_id: ["workspace.read", "project.read"]},
                    "ttl_seconds": 300,
                },
            )
            assert issued.status_code == 201, issued.text
            body = issued.json()
            assert body["pairing_secret"].startswith("skm_pair_")
            assert body["workspace_id"] == ws_id

            # Exchange the pairing token without bearer credentials
            exchange = client.build_request(
                "POST",
                "/api/v1/auth/pairing/exchange",
                json={
                    "workspace_id": ws_id,
                    "pairing_id": body["pairing_id"],
                    "pairing_secret": body["pairing_secret"],
                },
            )
            del exchange.headers["authorization"]
            exchanged = client.send(exchange)
            assert exchanged.status_code == 200, exchanged.text
            token_secret = exchanged.json()["token_secret"]
            assert token_secret.startswith("skm_")

            # Exchanged token authenticates against GET /api/v1/me
            me = client.get("/api/v1/me", headers={"Authorization": f"Bearer {token_secret}"})
            assert me.status_code == 200, me.text
            assert me.json()["principal"]["principal_id"] == str(world.owner.principal_id)
    finally:
        world.core.close()


def test_project_config_http_get_put_and_cas_conflict(tmp_path: Path) -> None:
    world, client = _hub_client(tmp_path)
    try:
        with client:
            _, project_id = _create_workspace_and_project(client)

            initial = client.get(f"/api/v1/projects/{project_id}/config", params={"format": "json"})
            assert initial.status_code == 200, initial.text
            digest_v1 = initial.json()["digest"]
            etag = initial.headers["etag"]

            # Conditional GET with matching ETag returns 304
            not_modified = client.get(
                f"/api/v1/projects/{project_id}/config",
                params={"format": "json"},
                headers={"If-None-Match": etag},
            )
            assert not_modified.status_code == 304

            for scope in ({"level": "project"}, {"level": "project", "scope_id": project_id}):
                scoped = client.put(
                    f"/api/v1/projects/{project_id}/config",
                    json={
                        "format": "json",
                        "document": {"schema": "urn:skm:settings:document:v1"},
                        "scope": scope,
                    },
                )
                assert scoped.status_code == 422, scoped.text
                assert scoped.json()["code"] == "SCHEMA_INVALID"

            # PUT with matching CAS digest succeeds (narrowing within default ceiling <= 3)
            updated = client.put(
                f"/api/v1/projects/{project_id}/config",
                json={
                    "format": "json",
                    "document": {
                        "schema": "urn:skm:settings:document:v1",
                        "execution": {"review": {"max_rounds": 2}},
                    },
                    "mode": "merge",
                    "expected_entries_digest": digest_v1,
                    "reason": "set review rounds",
                    "confirmed": True,
                },
            )
            assert updated.status_code == 200, updated.text
            assert updated.json()["applied"] is True
            digest_v2 = updated.json()["entries_digest_after"]
            assert digest_v2 != digest_v1

            # PUT with stale CAS digest fails with 409 VERSION_CONFLICT
            stale = client.put(
                f"/api/v1/projects/{project_id}/config",
                json={
                    "format": "json",
                    "document": {
                        "schema": "urn:skm:settings:document:v1",
                        "execution": {"review": {"max_rounds": 1}},
                    },
                    "mode": "merge",
                    "expected_entries_digest": digest_v1,
                    "reason": "stale update",
                    "confirmed": True,
                },
            )
            assert stale.status_code == 409
            assert stale.json()["code"] == "VERSION_CONFLICT"

            # Verify persisted value on GET
            fetched = client.get(f"/api/v1/projects/{project_id}/config", params={"format": "json"})
            assert fetched.status_code == 200
            assert fetched.json()["digest"] == digest_v2
            assert fetched.json()["document"]["execution"]["review"]["max_rounds"] == 2
    finally:
        world.core.close()
