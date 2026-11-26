"""Control-plane commands and queries over authenticated HTTP, on memory and PostgreSQL."""

from base64 import b64encode
from dataclasses import replace
from uuid import uuid4

import psycopg
import pytest

from contracts.extensions.harness import FakeBuiltinPacks, FakeEstimator, core_files, pack_payload
from integration.api.test_planning import key, ok, problem
from integration.api.test_worker_protocol import WORKER_CAPABILITIES
from integration.api.test_workspace_routes import host, workspace
from integration.artifacts.test_upload_flow import seed_principals
from integration.integrations._hook_support import _webhook_cfg
from security.api.harness import BASE, PEPPER, History, Pepper, TestClient
from skm.application_bus.platform.migrations import SchemaVersionReader
from skm.application_bus.ports import OutboxStore
from skm.bootstrap.composition import CompositionOverrides, StoredScopeChain, build_app
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.routing import build_route_table
from skm.kernel.gateways import GatewayTable
from skm.kernel.ports_uow import RequestMeta, Surface
from skm.kernel.tokens import TokenEstimator
from skm.modules.access.public import (
    CreateToken,
    CreateTokenResult,
    RbacAuthorizer,
    TokenPepperSource,
    authenticate_token,
)
from skm.modules.extensions.ports import BuiltinPacks
from skm.modules.runtimes.domain.capability import StaticCapabilityCatalog
from skm.modules.runtimes.ports import CapabilityCatalog
from skm.modules.workspace.public import checkout_locator
from skm.platform.config.bootstrap import load_bootstrap
from skm.platform.system_clock import SystemClock
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database
from support.seed import SEED
from unit.policy.application.harness import push_args
from unit.policy.application.test_queries import ROOTS
from unit.runtimes.application.test_catalog import CORE_MODELS_TOML, _static_caps

API = "/api/v1"
EXT = API + "/extensions"
POLICY = API + "/policy"
RUNTIMES = API + "/runtimes"
INTENTS = API + "/worker/intents"
V1 = {"If-Match": 'W/"v1"'}


def bearer(secret):
    return {"Authorization": "Bearer " + secret}


@pytest.fixture(params=["memory", pytest.param("postgres", marks=pytest.mark.pg)])
def http(request, tmp_path):
    backend = request.param
    dsn = (
        request.getfixturevalue("clean_test_database").dsn if backend == "postgres" else "postgresql://unused"
    )
    clock = SystemClock()
    boot = replace(load_bootstrap(None, {"SKM_DATABASE_URL": dsn}, tmp_path), instance_id=SEED.instance_id)
    if backend == "postgres":
        serving_host = uuid4()
        with psycopg.connect(dsn) as conn:
            conn.execute(
                "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) "
                "VALUES (%s, 'host', %s, NULL)",
                (serving_host, SEED.instance_id),
            )
        boot = replace(boot, host_id=serving_host)
    core = build_app(
        boot,
        surface=Surface.API,
        environ={},
        invocation={},
        backend=backend,
        overrides=CompositionOverrides(
            RbacAuthorizer(clock),
            StoredScopeChain(),
            clock=clock,
            instance_id=SEED.instance_id,
            repositories={SchemaVersionReader: lambda _: History()} if backend == "memory" else {},
            gateways=GatewayTable(
                {
                    TokenPepperSource: Pepper(),
                    BuiltinPacks: FakeBuiltinPacks(
                        pack_payload(files={**core_files(), "runtimes/models.toml": CORE_MODELS_TOML})
                    ),
                    TokenEstimator: FakeEstimator(),
                    CapabilityCatalog: StaticCapabilityCatalog({"codex": _static_caps("codex")}, {}),
                },
                "control_plane_gateway",
            ),
        ),
    )
    try:
        owner = seed_principals(core, backend)
        token = core.client(actor=owner, surface=Surface.CLI).dispatch(CreateToken(name="operator"))
        assert isinstance(token, CreateTokenResult)

        def authenticate(secret):
            with core.uow_factory(RequestMeta("auth", Surface.API, None, clock.now()), readonly=True) as uow:
                return authenticate_token(uow, secret, pepper=PEPPER, now=clock.now())

        api = create_app(
            replace(core, authenticator=authenticate),
            route_table=build_route_table(
                ("access", "settings", "workspace", "extensions", "policy", "runtimes", "integrations")
            ),
            registry=core.bus._registry,
            no_background=True,
        )
        with TestClient(api, base_url=BASE, headers=bearer(token.secret)) as client:
            yield client
    finally:
        core.close()


def worker(http, ws, host_id, *, capabilities=WORKER_CAPABILITIES):
    body = {"display_name": "worker", "host_id": host_id, "capabilities": capabilities}
    registered = ok(http.post(f"{API}/workspaces/{ws}/workers", json=body), 201)
    return bearer(registered["token_secret"])


def setting(http, scope, name, value):
    return ok(http.put(f"{API}/config/entries/{scope}/{name}", json={"value": value, "confirmed": True}))


def sync(http):
    return ok(http.post(EXT + "/packs/sync-builtin", json={}))


def test_pack_install_resolution_and_quarantine_authority(http):
    ws = workspace(http)
    assert sync(http)["installed"][0]["slug"] == "core"
    payload = pack_payload("sample", trust="operator", files={"prompts/shared/example.md": "Sample text."})
    body = {
        "payload": {
            "manifest_text": payload.manifest_text,
            "files": [
                {"path": f.path, "content_b64": b64encode(f.content).decode("ascii")} for f in payload.files
            ],
        },
        "origin_label": "path:operator/sample",
        "trust": "operator",
    }
    pack = ok(http.post(EXT + "/packs", json=body), 201)
    assert "sample" in {p["slug"] for p in ok(http.get(EXT + "/packs", params={"state": "active"}))["items"]}
    for identifier in (pack["pack_id"], "sample"):
        assert ok(http.get(EXT + "/packs/" + identifier))["pack_id"] == pack["pack_id"]

    scope = f"workspace:{ws}"
    setting(http, scope, "extensions.packs.enabled", ["core", "sample"])
    params = {"scope": scope, "kind": "prompt_block"}
    resources = ok(http.get(EXT + "/resources", params=params))["items"]
    resource = next(r for r in resources if r["pack_slug"] == "sample")
    chosen = ok(http.get(EXT + "/resolve", params={**params, "key": resource["key"]}))["chosen"]
    path = EXT + "/resource-versions/" + chosen["resource_version_id"]
    assert ok(http.get(path, params={"include_bodies": "true"}))["bodies"]
    pid = ok(http.post(API + "/principals", json={"kind": "human", "display_name": "maintainer"}), 201)[
        "principal_id"
    ]
    ok(
        http.post(
            API + "/memberships",
            json={"scope_id": str(SEED.instance_id), "principal_id": pid, "role": "maintainer"},
        ),
        201,
    )
    token = ok(http.post(API + "/tokens", json={"name": "maintainer", "principal_id": pid}), 201)
    maintainer = bearer(token["secret"])
    reason = {"reason": "manual review"}
    assert ok(http.post(path + "/quarantine", headers=maintainer, json=reason))["quarantined"]
    problem(http.post(path + "/release", headers=maintainer, json=reason), 403, "FORBIDDEN")
    assert ok(http.post(path + "/release", json=reason))["quarantined"] is False
    setting(http, scope, "extensions.packs.enabled", ["core"])
    retired = http.delete(
        EXT + "/pack-versions/" + pack["pack_version_id"], headers={"Content-Type": "application/json"}
    )
    assert ok(retired)["state"] == "retired"
    problem(http.get(EXT + "/upstream"), 404, "NOT_FOUND")


def test_policy_decisions_and_optimistic_intent_lifecycle(http):
    ws = workspace(http)
    setting(http, "instance", "policy.ceiling.external_effects", ["git_push"])
    scope = {"scope_id": ws}
    assert ok(http.get(POLICY + "/effective", params=scope))["permissions"]["digest"]
    assert ok(http.get(POLICY + "/explain", params=scope))["items"]
    assert ok(http.get(POLICY + "/profiles"))["profiles"]
    call = {
        "call": {"tool": "fs.read", "path": "/work/main/example"},
        "roots": ROOTS.to_json(),
        "observed_origins": {},
        "mode": "agent_unattended",
        **scope,
    }
    assert ok(http.post(POLICY + "/check-tool-call", json=call))["outcome"] == "allow"
    record = {
        "at": "2026-11-18T00:00:00Z",
        "tool": "fs.read",
        "call_summary": "read",
        "source": "worker",
        "outcome": "allow",
        "code": None,
        "operation": None,
        "rule": None,
    }
    records = {"records": [record], **scope}
    problem(http.post(POLICY + "/tool-decisions", json=records), 403, "FORBIDDEN")
    headers = worker(http, ws, host(http))
    assert ok(http.post(POLICY + "/tool-decisions", json=records, headers=headers))["recorded"] == 1

    body = {**scope, "subject_ref": "run:1", "args": push_args(), "kind": "git_push", "reason": "publish"}
    proposed = ok(http.post(INTENTS, json=body, headers=headers), 201)
    intent = proposed["intent_id"]
    path = POLICY + "/intents/" + intent
    fetched = http.get(path)
    digest = {"args_digest": ok(fetched)["args_digest"]}
    assert fetched.headers["ETag"] == V1["If-Match"]
    assert [
        i["intent_id"] for i in ok(http.get(POLICY + "/intents", params={"workspace_id": ws}))["items"]
    ] == [intent]
    problem(http.post(path + "/approve", json=digest), 428, "PRECONDITION_REQUIRED")
    problem(
        http.post(path + "/approve", headers={"If-Match": 'W/"v2"'}, json=digest), 409, "VERSION_CONFLICT"
    )
    assert ok(http.post(path + "/approve", headers=V1, json=digest))["state"] == "approved"
    start = INTENTS + "/" + intent + "/start"
    problem(
        http.post(start, headers=headers, json={"args_digest": "sha256:" + "a" * 64}),
        403,
        "APPROVAL_MISMATCH",
    )
    assert ok(http.post(start, headers=headers, json=digest))["state"] == "executing"
    outcome = {"outcome": "succeeded", "receipt": {"sha": "c" * 40}}
    assert (
        ok(http.post(INTENTS + "/" + intent + "/outcome", headers=headers, json=outcome))["state"]
        == "succeeded"
    )
    other = ok(http.post(INTENTS, headers=headers, json={**body, "args": push_args(after_sha="b" * 40)}), 201)
    deny = POLICY + "/intents/" + other["intent_id"] + "/deny"
    assert ok(http.post(deny, headers=V1, json={"reason": "hold"}))["state"] == "denied"


def test_runtime_observations_are_bound_to_worker_host(http):
    ws, own = workspace(http), host(http)
    headers = worker(http, ws, own, capabilities={**WORKER_CAPABILITIES, "runtimes": ["codex"]})
    other = ok(
        http.post(API + "/hosts", json={"name": "other", "platform": WORKER_CAPABILITIES["platform"]}), 201
    )["host_id"]
    assert {m["scope_id"] for m in ok(http.get(API + "/me", headers=headers))["memberships"]} == {ws}
    observed_at = SystemClock().now().isoformat()
    installations = [
        {
            "runtime_id": "codex",
            "version": "1.0.0",
            "binary_locator": None,
            "auth_state": "ok",
            "detected_at": observed_at,
            "details": {},
        }
    ]
    observed = {
        "installations": installations,
        "refresh_model_offers": True,
        "model_offers_observed_at": observed_at,
        "model_offers": [],
    }

    def report(host_id, body):
        return http.post(f"{API}/hosts/{host_id}/runtimes", json=body, headers=headers)

    problem(report(own, {"installations": installations}), 422, "SCHEMA_INVALID")
    assert ok(report(own, observed))["runtimes"][0]["changed"]
    problem(report(other, observed), 403, "FORBIDDEN")
    repeated = {**observed, "model_offers_observed_at": SystemClock().now().isoformat()}
    assert not ok(report(own, repeated))["runtimes"][0]["changed"]
    # Worker observations stay scoped to its snapshot. The host inventory is operator-owned.
    assert ok(http.get(RUNTIMES, params={"host_id": own}))["items"][0]["installations"] == []
    ok(http.post(f"{API}/hosts/{own}/runtimes", json={"installations": installations}))
    assert ok(http.get(RUNTIMES, params={"host_id": own}))["items"][0]["installations"][0]["host_id"] == own
    assert ok(http.get(RUNTIMES, params={"host_id": other}))["items"][0]["installations"] == []
    sync(http)
    assert ok(http.get(RUNTIMES + "/codex/capabilities"))["records"]
    models = ok(http.get(RUNTIMES + "/models", params={"model_class": "implementation"}))["models"]
    assert models
    assert all("implementation" in m["classes"] for m in models)
    routing = {"scope": f"workspace:{ws}", "role": "executor", "required_capabilities": "headless_execution"}
    assert ok(http.get(RUNTIMES + "/routing", params=routing))["role"] == "executor"
    verification = {
        "runtime_version": "1.0",
        "capability": "headless_execution",
        "status": "native",
        "evidence": "observed",
        "limitations": "",
        "verified_at": "2026-11-18",
        "verification_context": None,
    }
    assert (
        ok(http.post(RUNTIMES + "/codex/capability-verifications", json=verification), 201)["status"]
        == "native"
    )
    problem(http.post(RUNTIMES + "/detect", json={}), 404, "NOT_FOUND")


def project(http, ws, slug):
    return ok(http.post(f"{API}/workspaces/{ws}/projects", json={"slug": slug, "title": slug}), 201)[
        "project_id"
    ]


def checkout(http, ws, project_id, host_id):
    repo = ok(
        http.post(
            f"{API}/workspaces/{ws}/repositories",
            json={
                "title": "sample",
                "remote_url": "https://github.com/example/sample.git",
                "external_id": None,
            },
        ),
        201,
    )
    repo_id = repo["repository_id"]
    ok(http.post(f"{API}/projects/{project_id}/repositories", json={"repository_id": repo_id}), 201)
    locator = checkout_locator(uuid4())
    body = {
        "repository_id": repo_id,
        "host_id": host_id,
        "local_locator": locator,
        "observed_toplevel": locator,
        "observed_remotes": ["github.com/example/sample"],
        "observed_head": "a" * 40,
        "observed_dirty": False,
        "observed_at": SystemClock().now().isoformat(),
    }
    return ok(http.post(API + "/checkout-bindings", json=body), 201)["binding_id"]


def test_projection_callbacks_and_scope(http):
    ws, host_id = workspace(http), host(http)
    pid = project(http, ws, "sample")
    identity = {"checkout_binding_id": checkout(http, ws, pid, host_id), "target": "codex"}
    root = f"{API}/projects/{pid}"
    projections = root + "/projections"
    sync(http)
    desired = ok(http.get(root + "/integrations/desired-projection", params=identity))
    body = {
        **identity,
        "desired_digest": "sha256:" + "a" * 64,
        "inputs_digest": desired["inputs_digest"],
        "renderer_version": "codex@1",
        "files": [],
        "removed": [],
        "conflicts": [],
        "failed": [],
        "adopted": [],
        "left_modified": [],
    }
    other = project(http, ws, "other")
    problem(http.post(f"{API}/projects/{other}/projections", json=body, headers=key()), 404, "NOT_FOUND")
    foreign = ok(
        http.post(API + "/hosts", json={"name": "foreign", "platform": WORKER_CAPABILITIES["platform"]}), 201
    )
    credentials = worker(http, ws, foreign["host_id"])
    problem(http.post(projections, json=body, headers={**credentials, **key()}), 403, "FORBIDDEN")
    receipt = key()
    first = http.post(projections, json=body, headers=receipt)
    projection_id = ok(first, 201)["projection_id"]
    assert first.headers["ETag"] == V1["If-Match"]
    assert ok(http.post(projections, json=body, headers=receipt), 201) == first.json()
    problem(http.post(projections, json=body, headers={**V1, **key()}), 422, "SCHEMA_INVALID")
    problem(
        http.post(projections, json={**body, "base_row_version": 1}, headers=key()),
        422,
        "SCHEMA_INVALID",
    )
    applied = projections + "/applied"
    assert ok(http.get(applied, params=identity))["projection"]["projection_id"] == projection_id
    assert ok(http.get(projections))["items"][0]["projection_id"] == projection_id
    updated = http.post(applied, json=body, headers={**V1, **key()})
    assert ok(updated, 200)["row_version"] == 2
    problem(http.post(applied, json=body, headers={**V1, **key()}), 409, "VERSION_CONFLICT")
    drift = {**identity, "desired_digest": body["desired_digest"], "files": []}
    assert (
        ok(http.post(projections + "/drift", json=drift, headers={"If-Match": updated.headers["ETag"]}))[
            "drifted"
        ]
        == 0
    )
    removal = projections + "/" + projection_id + "/removal"
    result = {"removed": [], "left_modified": [], "failed": []}
    problem(http.post(removal, json=result, headers=key()), 428, "PRECONDITION_REQUIRED")
    version = ok(http.get(applied, params=identity))["projection"]["row_version"]
    assert (
        ok(http.post(removal, json=result, headers={**key(), "If-Match": f'W/"v{version}"'}))["state"]
        == "removed"
    )


def test_subscription_test_and_delivery_management(http):
    ws = workspace(http)
    pid = project(http, ws, "sample")
    setting(http, f"workspace:{ws}", "hooks.subscriptions", {"audit": _webhook_cfg()})
    assert "permissions" in ok(
        http.get(f"{API}/projects/{pid}/integrations/hook-policy", params={"target": "codex"})
    )
    prefix = f"{API}/workspaces/{ws}"
    subscriptions = prefix + "/hook-subscriptions"
    assert ok(http.get(subscriptions, params={"project_id": pid}))["items"]
    assert ok(http.post(subscriptions + "/audit/test", json={}), 201)["test_id"]
    deliveries = prefix + "/hook-deliveries"
    assert "items" in ok(http.get(deliveries, params={"subscription_id": "audit"}))
    assert ok(http.post(deliveries + "/retry", json={"subscription_id": "audit"}))["requeued"] == 0


def test_platform_diagnostics_status_and_outbox_permissions(http):
    verify = API + "/admin/storage/verify"
    for path, operation in (
        ("/health/details", "platform_health_details"),
        (API + "/doctor", "platform_doctor"),
        (API + "/admin/migrations", "platform_migration_status"),
        (verify, "platform_verify_storage"),
    ):
        assert [route.name for route in http.app.routes if route.path == path] == [operation]
    token = ok(http.post(API + "/tokens", json={"name": "limited", "permissions": ["workspace.read"]}), 201)
    restricted = bearer(token["secret"])
    for path in (
        "/health/details",
        API + "/doctor?only=config.registry",
        API + "/admin/migrations",
        verify,
        API + "/admin/outbox/dead",
    ):
        problem(http.get(path, headers=restricted), 403, "FORBIDDEN")
    assert ok(http.get("/health/details"))["checks"]
    assert [c["id"] for c in ok(http.get(API + "/doctor?only=config.registry"))["checks"]] == [
        "config.registry"
    ]
    assert ok(http.get(API + "/admin/migrations"))["migrations"]
    assert http.post(API + "/admin/migrations", json={}).status_code == 405
    assert ok(http.get(verify)) == {
        "checked_levels": [
            "relational",
            "specification",
            "execution",
            "files",
            "cryptographic",
            "authorization",
            "recovery",
        ],
        "findings": [],
        "counts": {"error": 0, "warning": 0, "info": 0},
    }
    dead = API + "/admin/outbox/dead"
    workspace(http)
    now = SystemClock().now()
    with http.app.state.core.uow_factory(RequestMeta("relay", Surface.BACKGROUND, None, now)) as uow:
        store = uow.repo(OutboxStore)
        (row,) = store.claim(destination="sse", relay_id="test-relay", now=now, limit=1)
        assert store.mark_failed(
            row.id, relay_id="test-relay", error="delivery failed", next_at=now, dead=True
        )
        uow.commit()
    assert [r["outbox_id"] for r in ok(http.get(dead))["items"]] == [str(row.id)]
    retry = f"{API}/admin/outbox/{row.id}/retry"
    problem(http.post(retry, json={}, headers=restricted), 403, "FORBIDDEN")
    assert ok(http.post(retry, json={}))["requeued"] == 1
    assert ok(http.get(dead))["items"] == []
