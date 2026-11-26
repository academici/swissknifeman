"""Generated and served OpenAPI contract."""

import json
import re
import subprocess
import sys
from functools import partial
from importlib import import_module
from importlib.resources import files
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from referencing import Registry
from referencing.jsonschema import DRAFT202012
from starlette.routing import Route

from security.api.harness import BASE, TestClient, make_world
from skm import __version__
from skm.bootstrap.modules import MANIFESTS, MODULE_CATALOG
from skm.entrypoints.api.app import create_app
from skm.entrypoints.api.blobs import mount_blobs
from skm.entrypoints.api.routing import build_route_table
from skm.modules.artifacts.application.upload import bind_embedded_upload

gen = import_module("tools.gen")
_openapi = import_module("tools._openapi")
CodegenError = import_module("tools.codegen.model").CodegenError

_SCHEMA_ROOT = gen.ROOT / "src/skm/schemas"
_RESOURCE = files("skm.entrypoints.api").joinpath("openapi.json")
_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


@pytest.fixture(scope="module")
def document():
    return json.loads(_RESOURCE.read_bytes())


@pytest.fixture(scope="module")
def api_client(tmp_path_factory):
    world = make_world(tmp_path_factory.mktemp("openapi"))
    core = world.core
    bus = core.bus
    try:
        api = create_app(
            core,
            route_table=build_route_table(entry.id for entry in MODULE_CATALOG),
            registry=bus._registry,
            no_background=True,
        )
        upload, _ = bind_embedded_upload(
            core.uow_factory,
            bus._authorizer,
            bus._scopes,
            core.config,
            core.gateways,
            bus._clock,
            bus._ids,
            bus.dispatch,
            bus.ask,
        )
        mount_blobs(api, upload)
        with TestClient(api, base_url=BASE, headers=world.headers) as client:
            yield client
    finally:
        core.close()


def _objects(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from _objects(child)


def _resolve(document, value):
    if "$ref" not in value:
        return value
    resolver = Registry().resolver_with_root(DRAFT202012.create_resource(document))
    return resolver.lookup(value["$ref"]).contents


def _header(document, operation, name):
    return next(
        (
            parameter
            for value in operation.get("parameters", [])
            if (parameter := _resolve(document, value))["name"] == name and parameter["in"] == "header"
        ),
        None,
    )


def _header_required(document, operation, name):
    header = _header(document, operation, name)
    assert header is not None
    return header["required"]


def test_openapi_valid(document):
    assert document["openapi"] == "3.1.0"
    assert document["info"] == {"title": "Swiss Knife Man API", "version": __version__}
    assert document["servers"] == [{"url": "/api/v1"}]
    assert document["security"] == [{"bearer": []}]
    assert document["components"]["securitySchemes"]["bearer"] == {"type": "http", "scheme": "bearer"}
    resolver = Registry().resolver_with_root(DRAFT202012.create_resource(document))
    for node in _objects(document):
        if "$ref" in node:
            assert node["$ref"].startswith("#/components/")
            assert node["$ref"].count("#") == 1
            assert isinstance(resolver.lookup(node["$ref"]).contents, (dict, bool))

    for name, schema in document["components"]["schemas"].items():
        assert re.fullmatch(r"[a-z0-9.-]+", name)
        assert "$id" not in schema
        Draft202012Validator.check_schema(schema)

    ids = set()
    for path, item in document["paths"].items():
        assert not path.startswith("/api/v1/")
        if path.startswith("/health/"):
            assert item["servers"] == [{"url": "/"}]
        for method, operation in item.items():
            if method == "servers":
                continue
            assert method in _METHODS
            assert operation["operationId"] not in ids
            ids.add(operation["operationId"])
            params = [_resolve(document, param) for param in operation.get("parameters", ())]
            assert len({(p["in"], p["name"]) for p in params}) == len(params)
            path_params = [p for p in params if p["in"] == "path"]
            assert {p["name"] for p in path_params} == set(re.findall(r"{(\w+)}", path))
            assert all(p["required"] is True for p in path_params)
            assert operation["responses"]["default"] == {"$ref": "#/components/responses/Problem"}
            assert any(status.startswith("2") for status in operation["responses"])
            if path.startswith("/worker/"):
                assert "worker" in operation["tags"]

    host_ids = {spec.name.replace(".", "_") for manifest in MANIFESTS for spec in manifest.host_operations}
    assert ids.isdisjoint(host_ids)
    for method, path in (
        ("get", "/health/live"),
        ("get", "/health/ready"),
        ("get", "/openapi.json"),
        ("get", "/auth/csrf"),
        ("post", "/auth/login"),
        ("post", "/auth/pairing/exchange"),
    ):
        assert document["paths"][path][method]["security"] == []
    assert document["paths"]["/health/details"]["get"]["security"] == [
        {"bearer": []},
        {"sessionCookie": []},
    ]
    assert document["paths"]["/auth/session"]["get"]["security"] == [
        {"bearer": []},
        {"sessionCookie": []},
    ]
    assert document["paths"]["/auth/logout"]["post"]["security"] == [
        {"sessionCookie": [], "csrfToken": []},
    ]
    assert document["paths"]["/auth/session/reload"]["post"]["security"] == [
        {"sessionCookie": [], "csrfToken": []},
    ]
    assert document["paths"]["/worker/assignments/claim"]["post"]["security"] == [{"bearer": []}]
    assert document["paths"]["/worker/attempts/{attempt_id}/live"]["post"]["security"] == [{"bearer": []}]
    assert document["paths"]["/events"]["get"]["security"] == [
        {"bearer": []},
        {"sessionCookie": []},
    ]
    assert document["paths"]["/projects/{project_id}/events/stream"]["get"]["security"] == [
        {"bearer": []},
        {"sessionCookie": []},
    ]
    assert document["paths"]["/attempts/{attempt_id}/live"]["get"]["security"] == [
        {"bearer": []},
        {"sessionCookie": []},
    ]
    assert document["paths"]["/tokens"]["post"]["security"] == [
        {"bearer": []},
        {"sessionCookie": [], "csrfToken": []},
    ]


def test_route_declarations_are_projected(document):
    routes = build_route_table(entry.id for entry in MODULE_CATALOG).describe()
    paths = document["paths"]
    declared = {
        (route.path.removeprefix("/api/v1"), route.method.lower()): route.effective_operation_id
        for route in routes
        if not route.internal and route.dto_type.SCHEMA_URN.split(":")[3] != "host"
    }
    assert {
        (path, method): item[method]["operationId"]
        for path, item in paths.items()
        for method in _METHODS & item.keys()
        if item[method].get("x-skm-bus", True)
    } == declared


def test_published_routes_are_mounted(document, api_client):
    mounted = {
        (method, route.path_format)
        for route in api_client.app.routes
        if isinstance(route, Route)
        for method in route.methods or ()
    }
    published = {
        (method.upper(), server["url"].rstrip("/") + path)
        for path, item in document["paths"].items()
        for server in item.get("servers", document["servers"])
        for method in _METHODS & item.keys()
    }
    assert published <= mounted


def test_created_locations_and_project_page_match_http(document, api_client):
    created = api_client.post("/api/v1/workspaces", json={"slug": "example", "title": "Example"})
    assert created.status_code == 201, created.text
    workspace_url = f"/api/v1/workspaces/{created.json()['workspace_id']}"
    assert created.headers["Location"] == workspace_url
    projects_url = workspace_url + "/projects"
    for slug in ("alpha", "bravo"):
        project = api_client.post(projects_url, json={"slug": slug, "title": slug})
        assert project.status_code == 201, project.text
        assert project.headers["Location"] == f"/api/v1/projects/{project.json()['project_id']}"

    response = api_client.get(projects_url, params={"limit": 1})
    assert response.status_code == 200, response.text
    page = response.json()
    assert [item["slug"] for item in page["items"]] == ["alpha"]
    assert page["next"] is not None
    operation = document["paths"]["/workspaces/{workspace_id}/projects"]["get"]
    schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
    Draft202012Validator(document).evolve(schema=schema).validate(page)


def test_headers_and_special_wire_formats(document):
    paths = document["paths"]
    draft = paths["/plans/{plan_id}/drafts/{draft_id}"]["patch"]
    assert _header_required(document, draft, "If-Match") is True
    assert _header_required(document, draft, "Idempotency-Key") is False
    assert {"200", "409", "428"} <= draft["responses"].keys()
    assert "ETag" in draft["responses"]["200"]["headers"]
    assert "application/merge-patch+json" in draft["requestBody"]["content"]

    create = paths["/projects/{project_id}/projections"]["post"]
    assert _header(document, create, "If-Match") is None
    create_body = create["requestBody"]["content"]["application/json"]["schema"]
    assert "base_row_version" not in create_body["properties"]
    assert "base_row_version" not in create_body["required"]
    assert _header_required(document, create, "Idempotency-Key") is True
    assert "409" in create["responses"]
    assert "428" not in create["responses"]

    projects = paths["/workspaces/{workspace_id}/projects"]
    query = projects["get"]
    assert _header(document, query, "Idempotency-Key") is None
    assert {"state", "after", "limit"} <= {p["name"] for p in query["parameters"]}
    page = query["responses"]["200"]["content"]["application/json"]["schema"]
    assert page == {"$ref": "#/components/schemas/workspace.view.list-projects.v1"}

    response = projects["post"]["responses"]["201"]
    assert {"ETag", "Location"} <= response["headers"].keys()
    assert projects["post"]["x-skm-permission"] == "project.create"
    body = projects["post"]["requestBody"]["content"]["application/json"]["schema"]
    assert body["required"] == ["slug", "title"]
    assert "workspace_id" not in body["properties"]

    claim = paths["/worker/assignments/claim"]["post"]
    assert "oneOf" in claim["responses"]["200"]["content"]["application/json"]["schema"]
    assert {"200", "201"} <= paths["/worker/integration-slots"]["post"]["responses"].keys()

    upload = paths["/workspaces/{workspace_id}/blobs"]["post"]
    assert _header_required(document, upload, "Content-Length") is True
    assert "application/octet-stream" in upload["requestBody"]["content"]
    assert "/files/{file_version_id}/content" not in paths
    download = paths["/file-versions/{file_version_id}/content"]["get"]
    assert "application/octet-stream" in download["responses"]["200"]["content"]
    assert "304" in download["responses"]
    for path in ("/events", "/projects/{project_id}/events/stream", "/attempts/{attempt_id}/live"):
        assert "text/event-stream" in paths[path]["get"]["responses"]["200"]["content"]
    live = paths["/worker/attempts/{attempt_id}/live"]["post"]
    assert "application/x-ndjson" in live["requestBody"]["content"]
    assert "202" in live["responses"]


def test_references_rebase_local_and_external_fragments(document):
    schemas = document["components"]["schemas"]
    defs = schemas["kernel.defs.v1"]["$defs"]
    assert defs["scope-ref"]["properties"]["id"]["$ref"] == "#/components/schemas/kernel.defs.v1/$defs/uuid"
    operation = document["paths"]["/workspaces/{workspace_id}/projects"]["get"]
    workspace = next(p for p in operation["parameters"] if p["name"] == "workspace_id")
    assert workspace["schema"]["$ref"] == "#/components/schemas/kernel.defs.v1/$defs/uuid"


def test_server_settings_defaults_are_not_openapi_defaults(document):
    settings = document["components"]["schemas"]["settings.document.v1"]["properties"]
    email = settings["worker"]["properties"]["git"]["properties"]["author_email"]
    assert "pattern" in email
    assert "default" not in email
    project_list = document["paths"]["/workspaces/{workspace_id}/projects"]["get"]
    limit = next(p for p in project_list["parameters"] if p["name"] == "limit")
    assert limit["schema"]["default"] == 50


def test_duplicate_operation_id_fails_generation(monkeypatch):
    original = _openapi._event_paths

    def duplicate():
        for path, method, operation in original():
            yield path, method, operation
            yield path + "-duplicate", method, operation

    monkeypatch.setattr(_openapi, "_event_paths", duplicate)
    with pytest.raises(CodegenError, match="Duplicate OpenAPI operation"):
        _openapi.render(_SCHEMA_ROOT)


def test_generator_rejects_missing_fragment(tmp_path):
    urn = "urn:skm:api:problem:v1"
    schema_root = tmp_path / "schemas"
    schema_root.mkdir()
    (schema_root / "api").mkdir()
    path = schema_root / "api/problem.v1.json"
    path.write_text(
        json.dumps(
            {
                "$schema": DRAFT202012.id_of(Draft202012Validator.META_SCHEMA),
                "$id": urn,
                "$ref": "#/$defs/missing",
            }
        ),
        encoding="utf-8",
    )
    schemas = _openapi.SchemaRegistry.load(schema_root, validate=False)
    components = _openapi._Components(schemas)
    components.ref(urn)
    with pytest.raises(CodegenError, match=r"Unresolved OpenAPI reference"):
        components.validate_refs()


def test_narrow_generator_check_reports_drift_without_writing(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(gen, "generate", partial(gen.generate, tmp_path, schema_root=_SCHEMA_ROOT))
    assert gen.main(["openapi"]) == 0
    output = tmp_path / _openapi.OUTPUT
    assert output.read_bytes() == _RESOURCE.read_bytes()

    output.write_bytes(b"stale")
    assert gen.main(["--only", "openapi", "--check"]) == 1
    assert capsys.readouterr().err == f"SCHEMA_CODEGEN_DRIFT: {_openapi.OUTPUT}\n"
    assert output.read_bytes() == b"stale"


def test_generator_imports_no_runtime():
    script = """
import sys
from importlib.abc import MetaPathFinder

class Guard(MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(("starlette", "uvicorn", "psycopg")) or fullname in {
            "skm.entrypoints.api.app", "skm.bootstrap.composition", "skm.application_bus.bus",
        }:
            raise AssertionError(f"OpenAPI generation imported {fullname}")

sys.meta_path.insert(0, Guard())
from tools import gen
raise SystemExit(gen.main(["openapi", "--check"]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script], cwd=gen.ROOT, capture_output=True, text=True, timeout=60, check=False
    )
    assert result.returncode == 0, result.stderr


def test_openapi_endpoint_serves_package_resource_without_auth(tmp_path: Path, monkeypatch):
    world = make_world(tmp_path)
    monkeypatch.chdir(tmp_path)

    def unexpected_auth(self, secret):
        pytest.fail("Attempted to authenticate a public OpenAPI request")

    monkeypatch.setattr(type(world.core), "authenticate", unexpected_auth)
    try:
        with world.client(no_background=True) as client:
            response = client.get("/api/v1/openapi.json")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/json"
        assert response.content == _RESOURCE.read_bytes()
    finally:
        world.core.close()
