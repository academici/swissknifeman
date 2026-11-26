"""Wire validation, discovery purity and server binding regressions for P11.02.a."""

import subprocess
import sys
import warnings
from dataclasses import replace
from types import ModuleType, SimpleNamespace
from typing import Any, cast
from uuid import UUID

import pytest
from starlette.applications import Starlette

with warnings.catch_warnings():
    warnings.filterwarnings(
        "ignore", category=DeprecationWarning, message="The anyio.abc.BlockingPortal alias is deprecated"
    )
    from starlette.testclient import TestClient

from architecture.test_surface_coverage import DEFERRED_INTERNAL, INTERNAL, SURFACES
from security.api.harness import make_world
from skm.application_bus.registry import IdempotencyMode
from skm.bootstrap.modules import MANIFESTS
from skm.bootstrap.platform_module import PLATFORM_MANIFEST
from skm.entrypoints.api.app import build_routes
from skm.entrypoints.api.etag import check_version, encode_etag, parse_if_match, parse_if_none_match
from skm.entrypoints.api.pagination import CURSOR_MAX_LENGTH, decode_cursor, encode_cursor, page
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.routing import (
    Route,
    RouteMethodNotAllowed,
    RouteTable,
    build_route_table,
    decode_scope,
    encode_scope,
)
from skm.kernel.actor import Actor, PrincipalKind, TokenGrant
from skm.kernel.error_codes import CATALOG, ErrorCode
from skm.kernel.errors import InternalError, SkmError
from skm.kernel.ids import PrincipalId, ScopeId
from skm.platform.schema.registry import SchemaRegistry

ID = "0192f5c4-0000-7000-8000-000000000001"
OTHER = "0192f5c4-0000-7000-8000-000000000002"
SPECS = {
    cast("Any", s).name: cast("Any", s)
    for m in (*MANIFESTS, PLATFORM_MANIFEST)
    for s in (*m.commands, *m.queries)
}


def fake(**kwargs) -> Any:
    return SimpleNamespace(**kwargs)


def declaration(name="workspace.get_project", **kwargs):
    spec = SPECS[name]
    command = hasattr(spec, "idempotency")
    args = {
        "method": "POST" if command else "GET",
        "path": "/api/v1/projects/{project_id}",
        "result_type": spec.result,
        "command" if command else "query": spec.dto,
        "idempotency": getattr(spec, "idempotency", IdempotencyMode.FORBIDDEN),
        "path_params": {"project_id": "project_id"},
    }
    args.update(kwargs)
    return Route(**args)


def error_code(code, action):
    with pytest.raises(SkmError) as raised:
        action()
    assert raised.value.code == code
    return raised.value


def test_table_indexes_are_immutable_and_distinguish_404_405():
    route = declaration()
    table = RouteTable([route])
    assert table[route.dto_type] is route
    with pytest.raises(InternalError) as missing:
        table[object]
    assert missing.value.code == ErrorCode.INTERNAL_ERROR
    assert table.describe() == (route,)
    assert table.match("GET", f"/api/v1/projects/{ID}") == (route, {"project_id": ID})
    with pytest.raises(RouteMethodNotAllowed) as raised:
        table.match("POST", f"/api/v1/projects/{ID}")
    assert raised.value.status_code == 405
    assert raised.value.allowed == ("GET",)
    error_code(ErrorCode.NOT_FOUND, lambda: table.match("GET", "/missing"))
    with pytest.raises(AttributeError):
        table._routes = ()
    with pytest.raises(AttributeError):
        del table._routes
    with pytest.raises(TypeError):
        cast("Any", route.path_params)["x"] = "y"


@pytest.mark.parametrize(
    "changes",
    [
        {"path_params": {"project_id": "unknown"}},
        {"path_params": {}},
        {"query_params": {"x": "unknown"}},
        {"result_type": object},
        {"if_match_to": "missing"},
        {"etag_from": "missing"},
        {"path_guards": {"project_id": "actor.untrusted"}, "path_params": {}},
        {"internal": True},
    ],
)
def test_build_rejects_invalid_contract(changes):
    with pytest.raises(ValueError, match=r".+"):
        RouteTable([declaration(**changes)])


def test_duplicate_routes_operations_and_explicit_aliases():
    route = declaration()
    with pytest.raises(ValueError, match=r".+"):
        RouteTable([route, route])
    alias = replace(route, path="/alias/{project_id}")
    with pytest.raises(ValueError, match=r".+"):
        RouteTable([route, alias])
    table = RouteTable([route, replace(alias, operation_id="get_project_alias")])
    assert len(table.describe()) == 2
    with pytest.raises(ValueError, match=r".+"):
        replace(route, idempotency=IdempotencyMode.REQUIRED)
    with pytest.raises(ValueError, match=r".+"):
        replace(route, command=route.query)


def test_path_body_collision_requires_exact_equality():
    route = declaration()
    result = route.bind({"project_id": ID}, {"project_id": ID}, {})
    assert result.to_json()["project_id"] == ID
    error_code(ErrorCode.SCHEMA_INVALID, lambda: route.bind({"project_id": OTHER}, {"project_id": ID}, {}))


@pytest.mark.parametrize(
    "name",
    [
        "execution.renew_lease",
        "execution.record_step_note",
        "runtimes.record_capability_verification",
        "integrations.get_hook_policy",
        "settings.explain_config",
    ],
)
def test_schema_metadata_supports_manual_and_dict_backed_dtos(name):
    spec = SPECS[name]
    schema = SchemaRegistry.load_default().get(spec.dto.SCHEMA_URN)
    properties = cast("dict[str, Any]", schema["properties"])
    field = next(iter(properties))
    route = declaration(name, path=f"/api/v1/test/{{{field}}}", path_params={field: field})
    assert RouteTable([route]).describe() == (route,)


def test_nested_path_schema_and_collision():
    route = declaration(
        "execution.renew_lease",
        path="/api/v1/assignments/{assignment_id}",
        path_params={"assignment_id": "claim.assignment_id"},
    )
    RouteTable([route])
    claim = {"assignment_id": ID, "attempt_id": OTHER, "worker_id": ID, "fencing_token": 1}
    dto = route.bind({"claim": claim}, {"assignment_id": ID}, {})
    assert dto.to_json() == {"claim": claim}
    error_code(
        ErrorCode.SCHEMA_INVALID,
        lambda: route.bind({"claim": {"assignment_id": OTHER}}, {"assignment_id": ID}, {}),
    )
    with pytest.raises(ValueError, match=r".+"):
        RouteTable([replace(route, path_params={"assignment_id": "claim.nonexistent"})])


def test_guard_only_run_id_is_never_injected_into_closed_dto():
    route = declaration(
        "execution.record_step_note",
        path="/api/v1/runs/{run_id}/steps/{step_id}/notes",
        path_params={"step_id": "step_id"},
        path_guards={"run_id": "actor.grant.scope_id"},
    )
    RouteTable([route])
    grant = TokenGrant(
        UUID(ID), "assignment", ScopeId(UUID(ID)), None, assignment_id=UUID(OTHER), step_id=UUID(ID)
    )
    actor = Actor(PrincipalId(UUID(ID)), PrincipalKind.WORKER, "worker", grant)
    schema = SchemaRegistry.load_default().get(route.dto_type.SCHEMA_URN)
    assert schema["additionalProperties"] is False
    assert "run_id" not in cast("dict[str, Any]", schema["properties"])
    error_code(ErrorCode.FORBIDDEN, lambda: route.bind({}, {"run_id": OTHER, "step_id": ID}, {}, actor=actor))
    error_code(ErrorCode.FORBIDDEN, lambda: route.bind({}, {"run_id": ID, "step_id": ID}, {}))
    err = error_code(
        ErrorCode.SCHEMA_INVALID, lambda: route.bind({}, {"run_id": ID, "step_id": ID}, {}, actor=actor)
    )
    assert "run_id" not in str(err.details)
    dto = route.bind({"kind": "progress", "text": "Working"}, {"run_id": ID, "step_id": ID}, {}, actor=actor)
    assert dto.to_json() == {"step_id": ID, "kind": "progress", "text": "Working"}


@pytest.mark.parametrize("scope", ["instance", f"workspace:{ID}", f"run:{ID}", f"host:{ID}"])
def test_scope_wire_roundtrip(scope):
    assert encode_scope(decode_scope(scope)) == scope


@pytest.mark.parametrize("operation", ["get_value", "lock_value", "unlock_value"])
@pytest.mark.parametrize(
    ("scope", "expected"),
    [("instance", {"level": "instance"}), (f"workspace:{ID}", {"level": "workspace", "scope_id": ID})],
)
def test_settings_scope_is_normalized_against_owning_schema(operation, scope, expected):
    route = declaration(
        f"settings.{operation}",
        path="/api/v1/config/entries/{scope}/{key}",
        path_params={"scope": "scope", "key": "key"},
    )
    RouteTable([route])
    path = {"scope": scope, "key": "worker.enabled"}
    assert route.bind({}, path, {}).to_json()["scope"] == expected
    assert route.bind({"scope": scope}, path, {}).to_json()["scope"] == expected
    assert encode_scope(expected) == scope
    if operation != "get_value":
        error_code(ErrorCode.SCHEMA_INVALID, lambda: route.bind({}, {**path, "scope": f"run:{ID}"}, {}))


DIGEST = "sha256:" + "a" * 64
DRAFT_PATH = "/api/v1/plans/{plan_id}/drafts/{draft_id}"
DRAFT_PARAMS = {"plan_id": ID, "draft_id": OTHER}
CONFIG_PATH = "/api/v1/config/entries/{scope}/{key}"


@pytest.mark.parametrize(
    ("method", "codec", "field", "value"),
    [
        ("PATCH", "merge_patch", "merge_patch", {"context_md": None, "title": "Changed"}),
        (
            "PUT",
            "json",
            "document",
            {
                "schema": "urn:skm:planning:specification:v1",
                "title": "Plan",
                "goal": "Test",
                "phases": [],
                "items": [],
            },
        ),
    ],
)
def test_save_draft_binds_raw_and_wrapped_http_bodies(tmp_path, monkeypatch, method, codec, field, value):
    route = declaration(
        "planning.save_draft",
        method=method,
        path=DRAFT_PATH,
        path_params={key: key for key in DRAFT_PARAMS},
        body=codec,
        if_match_to="expected_edit_version",
        etag_from="edit_version",
    )
    expected = {**DRAFT_PARAMS, "expected_edit_version": 4, field: value}
    assert route.bind({**value, "expected_edit_version": 4}, DRAFT_PARAMS, {}).to_json() == expected
    world = make_world(tmp_path)

    def dispatch(dto, **kwargs):
        assert dto.to_json() == expected
        return fake(to_json=lambda: {"edit_version": 5})

    monkeypatch.setattr(world.core.bus, "dispatch", dispatch)
    registry = fake(command=lambda dto: SPECS[route.bus_name])
    headers = {
        **world.headers,
        "Content-Type": "application/merge-patch+json" if codec == "merge_patch" else "application/json",
    }
    path = DRAFT_PATH.format_map(DRAFT_PARAMS)
    with world.client(route_table=RouteTable([route]), registry=registry) as client:
        missing = client.request(method, path, json=value, headers=headers)
        assert missing.status_code == 428
        assert missing.json()["details"] == {"header": "If-Match"}
        headers["If-Match"] = encode_etag(4)
        conflict = client.request(method, path, json={**value, "expected_edit_version": 3}, headers=headers)
        assert conflict.status_code == 409
        assert conflict.json()["code"] == "VERSION_CONFLICT"
        assert conflict.json()["details"] == {"expected": 4, "actual": 3}
        for body in (value, {field: value, "expected_edit_version": 4}):
            response = client.request(method, path, json=body, headers=headers)
            assert response.status_code == 200
            assert response.headers["ETag"] == 'W/"v5"'


@pytest.mark.parametrize(
    ("operation", "method", "path", "params", "body"),
    [
        ("execution.pause_run", "POST", "/api/v1/runs/{run_id}/pause", {"run_id": ID}, {"reason": "Wait"}),
        ("execution.resume_run", "POST", "/api/v1/runs/{run_id}/resume", {"run_id": ID}, {}),
        ("planning.archive_plan", "POST", "/api/v1/plans/{plan_id}/archive", {"plan_id": ID}, {}),
        *[
            (
                f"settings.{op}",
                method,
                CONFIG_PATH + suffix,
                {"scope": "instance", "key": "api.page.default_limit"},
                body,
            )
            for op, method, suffix, body in [
                ("set_value", "PUT", "", {"value": 42}),
                ("unset_value", "POST", "/unset", {}),
                ("remove_value", "DELETE", "", {}),
                ("lock_value", "POST", "/lock", {}),
                ("unlock_value", "POST", "/unlock", {}),
            ]
        ],
    ],
)
def test_optional_if_match_uses_header_or_preserves_body(
    tmp_path, monkeypatch, operation, method, path, params, body
):
    route = declaration(
        operation,
        method=method,
        path=path,
        path_params={key: key for key in params},
        if_match_to="expected_row_version",
    )
    world = make_world(tmp_path)
    monkeypatch.setattr(world.core.bus, "dispatch", lambda dto, **kwargs: dto)
    registry = fake(command=lambda dto: SPECS[operation])
    with world.client(route_table=RouteTable([route]), registry=registry) as client:
        for headers, data, expected in [
            ({}, body, None),
            ({}, {**body, "expected_row_version": 3}, 3),
            ({"If-Match": encode_etag(4)}, body, 4),
        ]:
            response = client.request(
                method, path.format_map(params), json=data, headers={**world.headers, **headers}
            )
            assert response.status_code == 200
            assert response.json().get("expected_row_version") == expected


@pytest.mark.parametrize(
    ("operation", "method", "suffix", "body"),
    [("settings.set_value", "PUT", "", {"value": 42}), ("settings.unset_value", "POST", "/unset", {})],
)
def test_create_only_config_precondition_is_atomic(tmp_path, operation, method, suffix, body):
    route = declaration(
        operation,
        method=method,
        path=CONFIG_PATH + suffix,
        path_params={"scope": "scope", "key": "key"},
        if_match_to="expected_row_version",
    )
    world = make_world(tmp_path)
    registry = fake(command=lambda dto: SPECS[operation])
    with world.client(route_table=RouteTable([route]), registry=registry) as client:
        path = "/api/v1/config/entries/instance/api.page.default_limit" + suffix
        headers = {**world.headers, "If-None-Match": "*"}
        created = client.request(method, path, json=body, headers=headers)
        assert created.status_code == 200
        exists = client.request(method, path, json=body, headers=headers)
        assert exists.status_code == 409
        assert exists.json()["code"] == "ALREADY_EXISTS"


def test_digest_etag_roundtrip_and_conditional_get(tmp_path, monkeypatch):
    route = declaration("planning.get_revision", body="none", etag_from="content_digest")
    route = replace(
        route,
        path="/api/v1/plans/{plan_id}/revisions/{revision_id}",
        path_params={"plan_id": "plan_id", "revision_id": "revision_id"},
    )
    world = make_world(tmp_path)
    monkeypatch.setattr(
        world.core.bus,
        "ask_with_meta",
        lambda dto, **kwargs: (fake(to_json=lambda: {"content_digest": DIGEST}), fake(events_cursor=None)),
    )
    registry = fake(query=lambda dto: SPECS[route.bus_name])
    tag = encode_etag(DIGEST)
    assert tag == f'"{DIGEST}"'
    path = f"/api/v1/plans/{ID}/revisions/{OTHER}"
    with world.client(route_table=RouteTable([route]), registry=registry) as client:
        full = client.get(path, headers={**world.headers, "If-None-Match": '"other"'})
        assert full.status_code == 200
        assert full.headers["ETag"] == tag
        cached = client.get(path, headers={**world.headers, "If-None-Match": tag})
        assert cached.status_code == 304
        assert cached.content == b""
        assert cached.headers["ETag"] == tag


def test_surface_ledger_contains_deferred_aliases():
    for name, suffix in (
        ("diff_revisions", "diff"),
        ("ready_preview", "ready-preview"),
        ("plan_stats", "stats"),
    ):
        assert ("GET", f"{DRAFT_PATH}/{suffix}") in SURFACES[f"planning.{name}"][1]
    assert ("POST", f"{DRAFT_PATH}/changes") in SURFACES["planning.save_draft"][1]
    finalize = ("POST", "/api/v1/context-manifests/{manifest_id}/finalize")
    assert SURFACES["context.finalize_manifest"][1].count(finalize) == 1
    assert SURFACES["knowledge.list_memory"][0] == "P13.01.c"
    assert SURFACES["knowledge.graph_stats"][0] == "P13.02.b"
    for name in (
        "knowledge.graph_subgraph",
        "knowledge.list_graph_indexes",
    ):
        assert SURFACES[name][0] == "P13"
    for name, (owner, _) in SURFACES.items():
        if name.startswith("learning."):
            assert owner == "P13.03.c"
    assert "learning.extract_candidates" in INTERNAL
    assert "learning.extract_candidates" not in DEFERRED_INTERNAL


@pytest.mark.parametrize(
    ("value", "status", "code"),
    [
        (None, 428, ErrorCode.PRECONDITION_REQUIRED),
        ('"v2"', 422, ErrorCode.SCHEMA_INVALID),
        ('W/"v0"', 422, ErrorCode.SCHEMA_INVALID),
        ('W/"v1", W/"v2"', 422, ErrorCode.SCHEMA_INVALID),
    ],
)
def test_if_match_errors(value, status, code):
    error = error_code(code, lambda: parse_if_match(value))
    assert CATALOG[error.code].http_status == status
    if value is None:
        assert dict(error.details) == {"header": "If-Match"}


def test_etag_version_conflict_and_creation_precondition():
    assert parse_if_match(encode_etag(5)) == 5
    assert parse_if_match(None, required=False) is None
    for tag in (None, "*", encode_etag(5), encode_etag(DIGEST)):
        assert parse_if_none_match(tag) == tag
    error = error_code(ErrorCode.VERSION_CONFLICT, lambda: check_version(4, 5))
    assert CATALOG[error.code].http_status == 409
    assert dict(error.details) == {"expected": 4, "actual": 5}
    error_code(ErrorCode.SCHEMA_INVALID, lambda: parse_if_none_match("foo"))


def test_cursor_roundtrip_page_and_malformed_tamper():
    cursor = encode_cursor(("2026-10-25T12:00:00Z", 5), ID)
    assert decode_cursor(cursor) == (("2026-10-25T12:00:00Z", 5), ID)
    assert page([], cursor, 50) == {"items": [], "next": cursor, "limit": 50}
    assert page([], None)["limit"] == 50
    assert page([], None, 500)["limit"] == 500
    assert page([], None, 3, max_limit=3)["limit"] == 3
    for limit, max_limit in ((0, 500), (501, 500), (4, 3)):
        with pytest.raises(SkmError) as raised:
            page([], None, limit, max_limit=max_limit)
        assert raised.value.code == ErrorCode.SCHEMA_INVALID
    for bad in ("!", cursor + "=", cursor[:-1], "x" * (CURSOR_MAX_LENGTH + 1), "e30"):
        error_code(ErrorCode.SCHEMA_INVALID, lambda bad=bad: decode_cursor(bad))


def test_dynamic_discovery_and_broken_dependency_are_not_silenced(monkeypatch):
    route = declaration()
    for fixed in ("worker", "platform"):
        empty_mod = ModuleType(f"skm.entrypoints.api.routes.{fixed}")
        vars(empty_mod)["ROUTES"] = ()
        monkeypatch.setitem(sys.modules, empty_mod.__name__, empty_mod)
    module = ModuleType("skm.entrypoints.api.routes.workspace")
    vars(module)["ROUTES"] = (route,)
    monkeypatch.setitem(sys.modules, module.__name__, module)
    assert build_route_table(["workspace"]).describe() == (route,)
    assert build_route_table([]).describe() == ()
    with pytest.raises(ValueError, match=r".+"):
        build_route_table(["bogus"])
    import skm.entrypoints.api.routes as discovery

    def broken(name):
        raise ModuleNotFoundError("dependency missing", name="dependency")

    monkeypatch.setattr(discovery, "import_module", broken)
    with pytest.raises(ModuleNotFoundError, match="dependency missing"):
        build_route_table(MODULE_IDS)


def test_startup_cross_checks_bus_metadata():
    route = declaration()
    spec = SPECS[route.bus_name]
    registry = fake(query=lambda dto: spec)
    assert len(build_routes(RouteTable([route]), registry)) == 1
    for changed in (replace(spec, internal=True), replace(spec, result=object), replace(spec, name="wrong")):
        with pytest.raises(ValueError, match="metadata drift"):
            build_routes(RouteTable([route]), fake(query=lambda dto, changed=changed: changed))
    command = declaration(
        "access.disable_principal",
        path="/principals/{principal_id}",
        path_params={"principal_id": "principal_id"},
    )
    spec = SPECS[command.bus_name]
    with pytest.raises(ValueError, match="metadata drift"):
        build_routes(
            RouteTable([replace(command, idempotency=IdempotencyMode.FORBIDDEN)]),
            fake(command=lambda dto: spec),
        )


def test_binding_dispatches_in_threadpool_and_waiting_is_http_200(monkeypatch):
    import threading

    import skm.entrypoints.api.app as binding

    route = declaration(body="none", success_status=201)
    main = threading.get_ident()

    def ask_with_meta(dto):
        assert threading.get_ident() != main
        assert dto.to_json()["project_id"] == ID
        return fake(to_json=lambda: {"outcome": {"kind": "waiting"}, "result": None}), fake(
            events_cursor=None
        )

    app = Starlette(routes=build_routes(RouteTable([route]), fake(query=lambda dto: SPECS[route.bus_name])))
    monkeypatch.setattr(binding, "_request_client", lambda *_: fake(ask_with_meta=ask_with_meta))

    # Supply the existing authentication/request context contract without a second composition.
    async def actor_context(request, call_next):
        request.state.actor = None
        return await call_next(request)

    from starlette.middleware.base import BaseHTTPMiddleware

    app.add_middleware(BaseHTTPMiddleware, dispatch=actor_context)
    monkeypatch.setattr(binding, "request_meta", lambda request, *, host_metadata=None: None)
    with TestClient(app) as client:
        response = client.get(f"/api/v1/projects/{ID}")
    assert response.status_code == 200
    assert response.json()["result"] is None


def test_client_safe_contract_imports_in_fresh_subprocess():
    script = """
import importlib.abc
import sys
class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        forbidden = ("starlette", "uvicorn", "psycopg", "skm.entrypoints.api.app",
            "skm.adapters", "skm.bootstrap.composition", "skm.bootstrap.modules",
            "skm.bootstrap.platform_module", "skm.modules.knowledge.application",
            "skm.modules.learning.application")
        if (any(fullname == p or fullname.startswith(p + ".") for p in forbidden)
                or fullname.startswith("psycopg")
                or fullname.startswith("skm.modules.") and fullname.endswith(".module")):
            raise AssertionError("forbidden import: " + fullname)
sys.meta_path.insert(0, Blocker())
from skm.entrypoints.api.routing import Route, RouteTable, build_route_table
from skm.entrypoints.api.routes import MODULE_IDS
from skm.entrypoints.api.etag import encode_etag
from skm.entrypoints.api.pagination import encode_cursor
from skm.platform.generated.queries import Doctor
from skm.platform.generated.results import DoctorResult
# Discover all currently implemented declaration modules; this leaf cannot create later owners' files.
table = build_route_table(MODULE_IDS)
route = Route("GET", "/health/details", DoctorResult, query=Doctor, body="none")
assert RouteTable([route])[Doctor] == route
from types import ModuleType
module = ModuleType("skm.entrypoints.api.routes.platform")
vars(module)["ROUTES"] = (route,)
sys.modules[module.__name__] = module
assert route in build_route_table(MODULE_IDS).describe()
assert Doctor.from_json(Doctor().to_json()).to_json() == Doctor().to_json()
assert "skm.bootstrap.modules" not in sys.modules
assert DoctorResult.from_json({"checks": []}).to_json() == {"checks": []}
"""
    result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
