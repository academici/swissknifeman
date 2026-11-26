"""Bearer identity, scoped token rotation and settings CAS through discovered declarations."""

from datetime import timedelta

from integration.api.test_workspace_routes import PLATFORM, created, host, workspace
from integration.api.test_workspace_routes import client as client
from integration.api.test_workspace_routes import world as world
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database


def test_worker_rotates_own_token_without_instance_membership(client, world):
    ws, host_id = workspace(client), host(client)
    capabilities = {
        "platform": PLATFORM,
        "runtimes": [],
        "isolation_profiles": ["worktree"],
        "max_concurrency": 1,
        "labels": [],
        "skm_version": "2.0.0",
    }
    worker = created(
        client.post(
            f"/api/v1/workspaces/{ws}/workers",
            json={
                "host_id": host_id,
                "display_name": "worker",
                "capabilities": capabilities,
            },
        )
    )
    headers = {"Authorization": "Bearer " + worker["token_secret"]}
    me = client.get("/api/v1/me", headers=headers).json()
    assert {entry["scope_id"] for entry in me["memberships"]} == {ws}
    world.core.bus._clock.advance(timedelta(seconds=1))
    old = me["token"]["token_id"]
    path = f"/api/v1/tokens/{old}/rotate"
    forbidden = client.post(path, json={}, headers={**headers, "Idempotency-Key": "secret"})
    assert forbidden.status_code == 422
    result = client.post(path, json={"grace_minutes": 0}, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["previous_token_id"] == old
    assert client.get("/api/v1/me", headers=headers).status_code == 401
    new = {"Authorization": "Bearer " + result.json()["secret"]}
    assert client.get("/api/v1/me", headers=new).json()["token"]["token_id"] == result.json()["token_id"]


def test_scoped_config_compare_and_set_and_explain(client):
    ws = workspace(client)
    scope = f"workspace:{ws}"
    key = "api.page.default_limit"
    path = f"/api/v1/config/entries/instance/{key}"
    create = {"If-None-Match": "*"}
    first = client.put(path, json={"value": 31}, headers=create)
    assert first.is_success, first.text
    retry = client.put(path, json={"value": 32}, headers=create)
    assert (retry.status_code, retry.json()["code"]) == (409, "ALREADY_EXISTS")
    updated = client.put(path, json={"value": 32}, headers={"If-Match": 'W/"v1"'})
    assert updated.json()["entry"]["row_version"] == 2
    stale = client.put(path, json={"value": 33}, headers={"If-Match": 'W/"v1"'})
    assert (stale.status_code, stale.json()["code"]) == (409, "VERSION_CONFLICT")
    for alias, selector, detail in (("effective", "keys", False), ("explain", "key", True)):
        response = client.get("/api/v1/config/" + alias, params={"scope": scope, selector: key})
        assert response.status_code == 200, response.text
        assert response.json()["scope"]["scope_id"] == ws
        [row] = response.json()["keys"]
        assert row["key"] == key
        assert bool(row["contributions"]) is detail
    malformed = client.get("/api/v1/config/generation", params={"scope": "workspace:bad"})
    assert (malformed.status_code, malformed.json()["code"]) == (422, "SCHEMA_INVALID")
    collision = client.put(path, json={"scope": {"level": "workspace", "scope_id": ws}, "value": 33})
    assert collision.status_code == 422


def test_config_import_preview_apply_export_and_generation(client):
    def generation():
        return client.get("/api/v1/config/generation").json()["generation"]

    base = generation()
    document = {"schema": "urn:skm:settings:document:v1", "api": {"page": {"default_limit": 37}}}
    body = {"scope": {"level": "instance"}, "format": "json", "document": document}
    preview = client.post("/api/v1/config/import", json={**body, "dry_run": True})
    assert preview.status_code == 200, preview.text
    assert not preview.json()["problems"]
    assert generation() == base
    headers = {"Idempotency-Key": "apply-config"}
    applied = client.post("/api/v1/config/import", json=body, headers=headers)
    assert applied.status_code == 200, applied.text
    assert client.post("/api/v1/config/import", json=body, headers=headers).json() == applied.json()
    assert generation() == base + 1
    exported = client.get("/api/v1/config/export", params={"scope": "instance", "format": "json"})
    assert exported.status_code == 200, exported.text
    assert exported.json()["digest"] == applied.json()["entries_digest_after"]
