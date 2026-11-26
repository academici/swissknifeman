import threading
from typing import Any, cast

import pytest
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from security.api.harness import make_world
from skm.application_bus.context import AuthBasis
from skm.entrypoints.api.app import call_bus
from skm.kernel.actor import Actor
from skm.kernel.error_codes import CATALOG, ErrorCode
from skm.kernel.ports_uow import RequestMeta
from skm.modules.access.public import WhoAmI
from skm.platform.logging.envelope import context_fields
from support.pg import clean_test_database as clean_test_database
from support.pg import pg_session as pg_session
from support.pg import test_database as test_database


def test_real_bus_actor_request_context_and_threadpool(tmp_path):
    world = make_world(tmp_path)
    seen: dict[str, Any] = {}
    original = world.core.bus.ask

    def ask(query: object, *, actor: Actor, meta: RequestMeta, auth_basis: AuthBasis | None = None) -> object:
        seen.update(actor=actor, meta=meta, thread=threading.get_ident(), log=context_fields())
        return original(query, actor=actor, meta=meta, auth_basis=auth_basis)

    world.core.bus.ask = ask

    async def endpoint(request: Request):
        seen["event_loop"] = threading.get_ident()
        await call_bus(request, WhoAmI())
        return JSONResponse({"ok": True})

    with world.client(routes=[Route("/api/v1/probe", endpoint)]) as client:
        response = client.get("/api/v1/probe", headers={**world.headers, "X-Request-Id": "api:test-42"})
    assert response.status_code == 200
    assert seen["actor"].principal_id == world.owner.principal_id
    assert seen["meta"].request_id == "api:test-42"
    assert seen["meta"].surface.value == "api"
    assert seen["log"]["request_id"] == "api:test-42"
    assert seen["thread"] != seen["event_loop"]
    assert response.headers["X-Request-Id"] == "api:test-42"
    assert context_fields() == {}


def test_health_is_public_and_minimal(tmp_path):
    with make_world(tmp_path).client() as client:
        assert client.get("/health/live").json() == {"status": "live"}
        ready = client.get("/health/ready")
        assert ready.status_code == 200
        assert ready.json() == {
            "status": "ready",
            "checks": {"database": "ok", "schema": "ok", "background": "ok"},
        }
        assert client.get("/health/details").status_code == 401


@pytest.mark.pg
def test_database_lock_degrades_readiness_without_touching_liveness_and_recovers(
    tmp_path, clean_test_database, monkeypatch
):
    import psycopg
    from psycopg.conninfo import make_conninfo

    from skm.adapters.postgres.core.schema_version import PostgresSchemaVersionReader
    from skm.kernel.errors import SkmError

    dsn = make_conninfo(clean_test_database.dsn, options="-c lock_timeout=50ms")
    world = make_world(tmp_path, database=dsn)
    original = PostgresSchemaVersionReader.applied
    calls = []
    failures = []

    def observed(reader):
        calls.append(True)
        try:
            return original(reader)
        except SkmError as error:
            failures.append(error)
            raise

    monkeypatch.setattr(PostgresSchemaVersionReader, "applied", observed)
    try:
        with world.client() as client:
            health = cast("Any", client.app).state.health
            health.interval = 0  # Every readiness request checks; the monitor is already waiting 30 s.
            assert client.get("/health/ready").status_code == 200
            with psycopg.connect(dsn) as blocker:
                blocker.execute("LOCK TABLE skm_core.schema_migrations IN ACCESS EXCLUSIVE MODE")
                count = len(calls)
                live = client.get("/health/live")
                assert live.status_code == 200
                assert live.json() == {"status": "live"}
                assert len(calls) == count
                ready = client.get("/health/ready")
                assert ready.status_code == 503
                assert ready.json()["checks"]["database"] == "fail"
                assert not world.core.schemas.validate("urn:skm:api:health:v1", ready.json())
                assert failures
                assert failures[-1].details["reason"] == "lock_timeout"
                assert isinstance(failures[-1].__cause__, psycopg.Error)
                count = len(calls)
                assert client.get("/health/live").status_code == 200
                assert len(calls) == count
            recovered = client.get("/health/ready")
            assert recovered.status_code == 200
            assert recovered.json()["checks"]["database"] == "ok"
    finally:
        world.core.close()


@pytest.mark.parametrize("failure", ["driver", "backend", "unexpected"])
def test_readiness_monitor_survives_failed_checks_and_recovers(tmp_path, monkeypatch, failure):
    import psycopg

    from security.api.harness import History
    from skm.kernel.errors import error_for

    world = make_world(tmp_path)
    failed, recovered = threading.Event(), threading.Event()
    errors = {
        "driver": psycopg.OperationalError("private database connection details"),
        "backend": error_for(ErrorCode.BACKEND_UNAVAILABLE, "private backend details"),
        "unexpected": RuntimeError("private unexpected failure"),
    }
    original = History.applied

    def fail(_reader):
        failed.set()
        raise errors[failure]

    def recover(reader):
        recovered.set()
        return original(reader)

    with world.client(settings={"api.schema_check_interval_seconds": 0.01}) as client:
        monkeypatch.setattr(History, "applied", fail)
        assert failed.wait(2), "periodic monitor did not check the database"
        assert client.get("/health/live").status_code == 200
        ready = client.get("/health/ready")
        assert ready.status_code == 503
        assert ready.json()["checks"]["database"] == "fail"
        assert "private" not in ready.text
        monkeypatch.setattr(History, "applied", recover)
        assert recovered.wait(2), "readiness monitor stopped after a check failure"
        assert client.get("/health/ready").status_code == 200


@pytest.mark.parametrize("code", [ErrorCode.SCHEMA_NOT_MIGRATED, ErrorCode.SCHEMA_TOO_NEW])
def test_schema_gate_mounts_only_health_and_migration_status(tmp_path, code):
    # Real history port, not a flag passed to the middleware.
    from security.api.harness import NOW
    from skm.application_bus.platform.migrations import AppliedMigration, SchemaVersionReader

    world = make_world(tmp_path)
    history = world.backend.factories[SchemaVersionReader](world.backend.committed)
    history.applied = lambda: (
        () if code is ErrorCode.SCHEMA_NOT_MIGRATED else (AppliedMigration(2, "future", "sha256:b", NOW),)
    )
    world.backend.factories[SchemaVersionReader] = lambda _state: history
    with world.client() as client:
        assert client.get("/health/live").status_code == 200
        assert client.get("/health/ready").status_code == 503
        for path in ("/api/v1/me", "/api/v1/openapi.json", "/", "/health/details"):
            result = client.get(path)
            assert (result.status_code, result.json()["code"]) == (409, code.value)
        assert client.get("/api/v1/admin/migrations").status_code == 401
        result = client.get("/api/v1/admin/migrations", headers=world.headers)
        assert result.status_code == 200
        assert result.json()["state"] in {"not_migrated", "too_new"}
        assert all(route.path != "/api/v1/me" for route in cast("Any", client.app).routes)


def test_http_status_is_exact_catalog_projection():
    from skm.entrypoints.api.errors import HTTP_STATUS

    assert dict(HTTP_STATUS) == {code: info.http_status for code, info in CATALOG.items()}


def test_forbidden_key_has_no_receipt_and_token_is_returned_once(tmp_path):
    world = make_world(tmp_path)
    with world.client() as client:
        refused = client.post(
            "/api/v1/tokens",
            json={"name": "refused"},
            headers={**world.headers, "Idempotency-Key": "never-store"},
        )
        assert refused.status_code == 422
        assert refused.json()["details"]["reason"] == "not_idempotent"
        success = client.post("/api/v1/tokens", json={"name": "issued"}, headers=world.headers)
        assert success.status_code == 200
        assert success.json()["secret"].startswith("skm_")
        assert "Idempotency-Replayed" not in success.headers
    assert not world.backend.committed.core.idempotency


@pytest.mark.pg
@pytest.mark.parametrize("state", ["pending", "too_new"])
def test_postgres_runner_status_gates_api_without_migrating(tmp_path, clean_test_database, state):
    import psycopg

    from skm.bootstrap.platform_module import local_migration_runner

    dsn = clean_test_database.dsn
    world = make_world(tmp_path, database=dsn)
    runner = local_migration_runner(dsn)
    try:
        with psycopg.connect(dsn, autocommit=True) as conn:
            if state == "pending":
                conn.execute(
                    "DELETE FROM skm_core.schema_migrations WHERE version = "
                    "(SELECT max(version) FROM skm_core.schema_migrations)"
                )
            else:
                conn.execute(
                    "INSERT INTO skm_core.schema_migrations "
                    "(version, name, checksum, applied_by, duration_ms) "
                    "SELECT max(version)+1, 'future', 'sha256:' || repeat('a', 64), 'api-test', 0 "
                    "FROM skm_core.schema_migrations"
                )
        before = runner.status()
        world.restart(tmp_path, dsn)
        with world.client(migration_runner=runner) as client:
            assert client.get("/health/live").status_code == 200
            assert client.get("/health/ready").status_code == 503
            assert client.get("/api/v1/me", headers=world.headers).status_code == 409
            status = client.get("/api/v1/admin/migrations", headers=world.headers)
            assert status.status_code == 200
            assert status.json()["state"] == ("not_migrated" if state == "pending" else "too_new")
        assert runner.status() == before
    finally:
        world.core.close()
        # Restore only this worker's test history so the shared fixture remains usable.
        with psycopg.connect(dsn, autocommit=True) as conn:
            if state == "too_new":
                conn.execute("DELETE FROM skm_core.schema_migrations WHERE name = 'future'")
            else:
                last = runner.files[-1]
                conn.execute(
                    "INSERT INTO skm_core.schema_migrations "
                    "(version, name, checksum, applied_by, duration_ms) "
                    "VALUES (%s, %s, %s, 'api-test', 0)",
                    (last.version, last.filename, last.checksum),
                )
