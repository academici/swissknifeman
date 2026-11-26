"""Core scopes, event order, append-only rows and receipts against the project baseline.

Constraints are exercised as the database owner and through PostgresScopeRegistry.
"""

import os
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from importlib import resources
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import errors as pgerr
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from skm.adapters.postgres.core import REPOSITORIES
from skm.adapters.postgres.core.scopes import PostgresScopeRegistry, PostgresScopeTree
from skm.adapters.postgres.jsonb import to_jsonb
from skm.adapters.postgres.migrations.runner import MigrationRunner, discover_migrations, package_loader
from skm.kernel.error_codes import ErrorCode
from skm.kernel.errors import Conflict, NotFound, ValidationFailed
from skm.kernel.ids import ScopeId, WorkspaceId
from skm.kernel.scopes import ScopeKind, ScopeRegistry
from skm.platform.config.keys import Chain, Level
from skm.platform.config.scopes import ScopeRef
from skm.platform.config.store import ScopeTree

pg = pytest.mark.pg

_BASELINE_NAME = "0001_core_baseline.sql"
_NIL = UUID(int=0)
_EVENT_TYPE = "urn:skm:workspace:event:project-created:v1"
NOW = datetime(2026, 1, 1, tzinfo=UTC)
_DIGEST = "sha256:" + "a" * 64


class _Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)  # noqa: TID251 - migration runner clock of the scratch database, not product code


# --- no database needed -------------------------------------------------------------------------------------


def test_project_baseline_does_not_hard_code_the_instance_scope() -> None:
    uuid_literal = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
    text = (
        resources.files("skm.adapters.postgres.migrations").joinpath("sql", _BASELINE_NAME).read_text("utf-8")
    )
    found = {m for m in uuid_literal.findall(text) if UUID(m) != _NIL}
    assert not found
    assert "INSERT INTO skm_core.scopes" not in text


def test_core_repositories_bind_the_scope_ports() -> None:
    assert REPOSITORIES[ScopeRegistry] is PostgresScopeRegistry
    assert REPOSITORIES[ScopeTree] is PostgresScopeTree


# --- live PostgreSQL ----------------------------------------------------------------------------------------


def _checked_admin(dsn: str) -> None:
    """CREATE/DROP DATABASE only against a loopback or socket test server (testing spec 1.11)."""
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail(
            "core constraint tests create databases only on a local server through an '*_test' database",
            pytrace=False,
        )


@pytest.fixture
def db(pg_dsn: str) -> Iterator[psycopg.Connection]:
    """Owner connection to a scratch database migrated to the project baseline."""
    _checked_admin(pg_dsn)
    name = f"skm_t_core_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            dsn = make_conninfo(pg_dsn, dbname=name)
            runner = MigrationRunner(dsn, discover_migrations(), package_loader(), _Clock(), "skm-test")
            assert runner.migrate() == tuple(item.version for item in runner.files)
            with psycopg.connect(dsn, autocommit=True) as conn:
                yield conn
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def _scope(
    conn: psycopg.Connection,
    kind: str,
    parent: UUID | None,
    workspace: UUID | None,
    scope_id: UUID | None = None,
) -> UUID:
    scope_id = scope_id or uuid4()
    conn.execute(
        "INSERT INTO skm_core.scopes (id, kind, parent_id, workspace_id) VALUES (%s, %s, %s, %s)",
        (scope_id, kind, parent, workspace),
    )
    return scope_id


class Tree:
    """Instance, two workspaces and one chain project/plan/run under the first, plus a host."""

    def __init__(self, conn: psycopg.Connection) -> None:
        self.instance = _scope(conn, "instance", None, None)
        self.ws_a = uuid4()
        self.ws_b = uuid4()
        _scope(conn, "workspace", self.instance, self.ws_a, self.ws_a)
        _scope(conn, "workspace", self.instance, self.ws_b, self.ws_b)
        self.project = _scope(conn, "project", self.ws_a, self.ws_a)
        self.plan = _scope(conn, "plan", self.project, self.ws_a)
        self.run = _scope(conn, "run", self.plan, self.ws_a)
        self.host = _scope(conn, "host", self.instance, None)


@pytest.fixture
def tree(db: psycopg.Connection) -> Tree:
    return Tree(db)


def _event(conn: psycopg.Connection, **changes: object) -> UUID:
    stream_id = uuid4()
    row: dict[str, object] = {
        "id": uuid4(),
        "workspace_id": None,
        "stream_kind": "workspace",
        "stream_id": stream_id,
        "stream_seq": 1,
        "workspace_seq": None,
        "global_position": None,
        "event_type": _EVENT_TYPE,
        "correlation_id": "req-1",
        "payload": to_jsonb({}),
        "occurred_at": NOW,
    }
    row.update(changes)
    columns = sql.SQL(", ").join(sql.Identifier(name) for name in row)
    marks = sql.SQL(", ").join(sql.Placeholder() for _ in row)
    conn.execute(
        sql.SQL("INSERT INTO skm_core.domain_events ({}) VALUES ({})").format(columns, marks),
        list(row.values()),
    )
    return row["id"]  # pyright: ignore[reportReturnType]


def _workspace_event(conn: psycopg.Connection, workspace: UUID, seq: int, **changes: object) -> UUID:
    return _event(conn, workspace_id=workspace, workspace_seq=seq, **changes)


def _instance_event(conn: psycopg.Connection, position: int, **changes: object) -> UUID:
    return _event(conn, global_position=position, **changes)


# --- scope lineage ------------------------------------------------------------------------------------------


@pg
@pytest.mark.parametrize(
    "shape",
    [
        "project-under-instance",
        "plan-under-workspace",
        "run-under-workspace",
        "workspace-under-project",
        "workspace-under-workspace",
        "host-under-workspace",
        "project-under-host",
        "project-in-foreign-workspace",
        "plan-in-foreign-workspace",
        "run-in-foreign-workspace",
        "project-without-workspace",
        "workspace-pointing-elsewhere",
        "workspace-without-workspace",
        "host-with-workspace",
        "instance-with-parent",
        "instance-with-workspace",
        "project-without-parent",
        "unknown-parent",
        "unknown-kind",
    ],
)
def test_scope_lineage_is_enforced_by_the_database(db: psycopg.Connection, tree: Tree, shape: str) -> None:
    new = uuid4()
    cases: dict[str, tuple[str, UUID | None, UUID | None]] = {
        "project-under-instance": ("project", tree.instance, tree.ws_a),
        "plan-under-workspace": ("plan", tree.ws_a, tree.ws_a),
        "run-under-workspace": ("run", tree.ws_a, tree.ws_a),
        "workspace-under-project": ("workspace", tree.project, new),
        "workspace-under-workspace": ("workspace", tree.ws_a, new),
        "host-under-workspace": ("host", tree.ws_a, None),
        "project-under-host": ("project", tree.host, tree.ws_a),
        "project-in-foreign-workspace": ("project", tree.ws_a, tree.ws_b),
        "plan-in-foreign-workspace": ("plan", tree.project, tree.ws_b),
        "run-in-foreign-workspace": ("run", tree.plan, tree.ws_b),
        "project-without-workspace": ("project", tree.ws_a, None),
        "workspace-pointing-elsewhere": ("workspace", tree.instance, tree.ws_a),
        "workspace-without-workspace": ("workspace", tree.instance, None),
        "host-with-workspace": ("host", tree.instance, tree.ws_a),
        "instance-with-parent": ("instance", tree.instance, None),
        "instance-with-workspace": ("instance", None, tree.ws_a),
        "project-without-parent": ("project", None, tree.ws_a),
        "unknown-parent": ("project", uuid4(), tree.ws_a),
        "unknown-kind": ("tenant", tree.instance, None),
    }
    kind, parent, workspace = cases[shape]
    with pytest.raises(pgerr.CheckViolation):
        _scope(db, kind, parent, workspace, new)
    assert db.execute("SELECT count(*) FROM skm_core.scopes WHERE id = %s", (new,)).fetchone() == (0,)


@pg
def test_run_under_project(db: psycopg.Connection, tree: Tree) -> None:
    _require_app_role(db)
    with db.transaction():
        db.execute("SET LOCAL ROLE skm_app")
        run_id = uuid4()
        _scope(db, "run", tree.project, tree.ws_a, run_id)
        assert db.execute(
            "SELECT parent_id, workspace_id FROM skm_core.scopes WHERE id = %s", (run_id,)
        ).fetchone() == (tree.project, tree.ws_a)


@pg
def test_a_valid_tree_is_accepted(db: psycopg.Connection, tree: Tree) -> None:
    rows = db.execute("SELECT kind, count(*) FROM skm_core.scopes GROUP BY kind").fetchall()
    assert dict(rows) == {"instance": 1, "workspace": 2, "project": 1, "plan": 1, "run": 1, "host": 1}


@pg
def test_only_one_instance_row_exists_whatever_its_id(db: psycopg.Connection, tree: Tree) -> None:
    with pytest.raises(pgerr.UniqueViolation):
        _scope(db, "instance", None, None)
    assert db.execute("SELECT count(*) FROM skm_core.scopes WHERE kind = 'instance'").fetchone() == (1,)


@pg
def test_the_instance_id_is_not_fixed_by_the_migration(db: psycopg.Connection) -> None:
    assert db.execute("SELECT count(*) FROM skm_core.scopes").fetchone() == (0,)
    chosen = uuid4()
    assert _scope(db, "instance", None, None, chosen) == chosen


@pg
def test_scope_rows_are_immutable_and_a_parent_with_children_cannot_be_deleted(
    db: psycopg.Connection, tree: Tree
) -> None:
    with pytest.raises(pgerr.RestrictViolation):
        db.execute("UPDATE skm_core.scopes SET parent_id = %s WHERE id = %s", (tree.ws_b, tree.project))
    with pytest.raises(pgerr.RestrictViolation):
        db.execute("UPDATE skm_core.scopes SET workspace_id = %s WHERE id = %s", (tree.ws_b, tree.project))
    # ON DELETE RESTRICT: foreign_key_violation on PostgreSQL 16, restrict_violation on newer servers
    with pytest.raises((pgerr.ForeignKeyViolation, pgerr.RestrictViolation)):
        db.execute("DELETE FROM skm_core.scopes WHERE id = %s", (tree.project,))


# --- runtime role -------------------------------------------------------------------------------------------


def _require_app_role(conn: psycopg.Connection) -> None:
    if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'skm_app'").fetchone() is None:
        pytest.skip(
            "skm_app was not created: the test user can neither create roles nor see them (server mode)"
        )


def _privilege(conn: psycopg.Connection, table: str, privilege: str) -> bool:
    row = conn.execute(
        "SELECT has_table_privilege('skm_app', %s, %s)", (f"skm_core.{table}", privilege)
    ).fetchone()
    assert row is not None
    return bool(row[0])


@pg
@pytest.mark.parametrize("table", ["scopes", "domain_events", "audit_records"])
def test_runtime_role_only_appends_to_append_only_tables(db: psycopg.Connection, table: str) -> None:
    _require_app_role(db)
    assert _privilege(db, table, "SELECT")
    assert _privilege(db, table, "INSERT")
    assert not _privilege(db, table, "UPDATE")
    assert not _privilege(db, table, "DELETE")


@pg
@pytest.mark.parametrize(
    "table", ["event_streams", "workspace_event_counters", "outbox", "idempotency_receipts"]
)
def test_runtime_role_keeps_dml_on_mutable_tables(db: psycopg.Connection, table: str) -> None:
    _require_app_role(db)
    assert all(_privilege(db, table, p) for p in ("SELECT", "INSERT", "UPDATE", "DELETE"))


@pg
def test_consumer_receipts_are_deletable_by_the_runtime_role_but_never_updatable(
    db: psycopg.Connection, tree: Tree
) -> None:
    _require_app_role(db)
    assert _privilege(db, "consumer_receipts", "DELETE")
    event = _workspace_event(db, tree.ws_a, 1)
    now = NOW
    db.execute("INSERT INTO skm_core.consumer_receipts VALUES ('exports.note', %s, %s)", (event, now))
    # UPDATE is granted as a privilege but refused by the trigger, for the owner and the runtime role alike.
    with pytest.raises(pgerr.RestrictViolation):
        db.execute("UPDATE skm_core.consumer_receipts SET processed_at = %s", (now + timedelta(hours=1),))
    with db.transaction():
        db.execute("SET LOCAL ROLE skm_app")
        with pytest.raises(pgerr.RestrictViolation), db.transaction():
            db.execute("UPDATE skm_core.consumer_receipts SET processed_at = %s", (now + timedelta(hours=1),))
        assert db.execute("DELETE FROM skm_core.consumer_receipts").rowcount == 1


@pg
def test_runtime_role_cannot_touch_the_migration_ledger(db: psycopg.Connection) -> None:
    _require_app_role(db)
    for table in ("schema_migrations", "schema_baseline"):
        assert _privilege(db, table, "SELECT")
        for privilege in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER"):
            assert not _privilege(db, table, privilege)


def _execute_as_runtime_role(conn: psycopg.Connection, statement: str) -> None:
    with conn.transaction():
        conn.execute("SET LOCAL ROLE skm_app")
        conn.execute(sql.SQL(statement))  # pyright: ignore[reportArgumentType]


@pg
@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE skm_core.scopes SET kind = 'host'",
        "DELETE FROM skm_core.scopes",
        "UPDATE skm_core.domain_events SET event_type = event_type",
        "DELETE FROM skm_core.domain_events",
        "UPDATE skm_core.audit_records SET reason_code = 'x'",
        "DELETE FROM skm_core.audit_records",
        "INSERT INTO skm_core.schema_migrations (version, name, checksum, duration_ms) "
        "VALUES (99, 'x', 'sha256:' || repeat('0', 64), 1)",
    ],
)
def test_runtime_role_is_refused_by_the_privilege_layer(
    db: psycopg.Connection, tree: Tree, statement: str
) -> None:
    _require_app_role(db)
    _workspace_event(db, tree.ws_a, 1)
    db.execute(
        "INSERT INTO skm_core.audit_records (id, actor_id, action, decision, request_id) "
        "VALUES (%s, %s, 'a.b', 'allowed', 'r')",
        (uuid4(), uuid4()),
    )
    with pytest.raises(pgerr.InsufficientPrivilege):
        _execute_as_runtime_role(db, statement)


@pg
def test_runtime_role_can_append_scopes_and_events(db: psycopg.Connection, tree: Tree) -> None:
    _require_app_role(db)
    with db.transaction():
        db.execute("SET LOCAL ROLE skm_app")
        _scope(db, "project", tree.ws_b, tree.ws_b)
        _workspace_event(db, tree.ws_b, 1)


# --- events: two orders -------------------------------------------------------------------------------------


@pg
def test_workspace_and_instance_events_use_independent_orders(db: psycopg.Connection, tree: Tree) -> None:
    _workspace_event(db, tree.ws_a, 1)
    _workspace_event(db, tree.ws_a, 2)
    _workspace_event(db, tree.ws_b, 1)
    _instance_event(db, 1)
    _instance_event(db, 2)
    rows = db.execute(
        "SELECT workspace_id, workspace_seq, global_position FROM skm_core.domain_events "
        "ORDER BY recorded_at, id"
    ).fetchall()
    assert len(rows) == 5
    assert {(r[0] is None, r[1] is None, r[2] is None) for r in rows} == {
        (False, False, True),
        (True, True, False),
    }


@pg
@pytest.mark.parametrize(
    "shape",
    [
        "workspace-event-with-global-position",
        "instance-event-without-global-position",
        "instance-event-with-zero-position",
        "workspace-without-workspace-seq",
        "workspace-seq-without-workspace",
        "stream-seq-zero",
        "bad-event-type",
        "payload-not-an-object",
        "payload-too-large",
        "schema-version-zero",
    ],
)
def test_event_shape_is_checked(db: psycopg.Connection, tree: Tree, shape: str) -> None:
    ws = tree.ws_a
    cases: dict[str, dict[str, object]] = {
        "workspace-event-with-global-position": {
            "workspace_id": ws,
            "workspace_seq": 1,
            "global_position": 1,
        },
        "instance-event-without-global-position": {},
        "instance-event-with-zero-position": {"global_position": 0},
        "workspace-without-workspace-seq": {"workspace_id": ws},
        "workspace-seq-without-workspace": {"workspace_seq": 1, "global_position": 1},
        "stream-seq-zero": {"workspace_id": ws, "workspace_seq": 1, "stream_seq": 0},
        "bad-event-type": {"workspace_id": ws, "workspace_seq": 1, "event_type": "project.created"},
        "payload-not-an-object": {"workspace_id": ws, "workspace_seq": 1, "payload": to_jsonb([1])},
        "payload-too-large": {
            "workspace_id": ws,
            "workspace_seq": 1,
            "payload": to_jsonb({"x": "y" * 262144}),
        },
        "schema-version-zero": {"workspace_id": ws, "workspace_seq": 1, "schema_version": 0},
    }
    with pytest.raises(pgerr.CheckViolation):
        _event(db, **cases[shape])
    assert db.execute("SELECT count(*) FROM skm_core.domain_events").fetchone() == (0,)


@pg
def test_event_positions_are_unique_per_feed(db: psycopg.Connection, tree: Tree) -> None:
    _workspace_event(db, tree.ws_a, 1)
    with pytest.raises(pgerr.UniqueViolation):
        _workspace_event(db, tree.ws_a, 1)
    _instance_event(db, 1)
    with pytest.raises(pgerr.UniqueViolation):
        _instance_event(db, 1)
    stream = uuid4()
    _workspace_event(db, tree.ws_b, 1, stream_id=stream)
    with pytest.raises(pgerr.UniqueViolation):
        _workspace_event(db, tree.ws_b, 2, stream_id=stream)  # same (stream_kind, stream_id, stream_seq)


@pg
def test_event_workspace_must_be_a_scope(db: psycopg.Connection, tree: Tree) -> None:
    with pytest.raises(pgerr.ForeignKeyViolation):
        _workspace_event(db, uuid4(), 1)


@pg
def test_events_are_append_only_even_for_the_owner(db: psycopg.Connection, tree: Tree) -> None:
    event = _workspace_event(db, tree.ws_a, 1)
    with pytest.raises(pgerr.RestrictViolation):
        db.execute("UPDATE skm_core.domain_events SET payload = '{\"x\":1}'::jsonb WHERE id = %s", (event,))
    with pytest.raises(pgerr.RestrictViolation):
        db.execute("DELETE FROM skm_core.domain_events WHERE id = %s", (event,))
    assert db.execute("SELECT payload FROM skm_core.domain_events WHERE id = %s", (event,)).fetchone() == (
        {},
    )


@pg
def test_counters_are_scoped_and_non_negative(db: psycopg.Connection, tree: Tree) -> None:
    db.execute("INSERT INTO skm_core.workspace_event_counters VALUES (%s, 0)", (tree.ws_a,))
    with pytest.raises(pgerr.ForeignKeyViolation):
        db.execute("INSERT INTO skm_core.workspace_event_counters VALUES (%s, 0)", (uuid4(),))
    with pytest.raises(pgerr.CheckViolation):
        db.execute("UPDATE skm_core.workspace_event_counters SET last_seq = -1")
    db.execute("INSERT INTO skm_core.event_streams VALUES ('instance_feed', %s, 0)", (tree.instance,))
    with pytest.raises(pgerr.CheckViolation):
        db.execute("UPDATE skm_core.event_streams SET last_seq = -1")
    row = db.execute(
        "INSERT INTO skm_core.event_streams AS s VALUES ('instance_feed', %s, 1) "
        "ON CONFLICT (stream_kind, stream_id) DO UPDATE SET last_seq = s.last_seq + 1 RETURNING last_seq",
        (tree.instance,),
    ).fetchone()
    assert row == (1,)


# --- outbox and receipts ------------------------------------------------------------------------------------


def _outbox(
    conn: psycopg.Connection, event: UUID, destination: str, state: str = "pending", delivered: bool = False
) -> None:
    now = NOW
    conn.execute(
        "INSERT INTO skm_core.outbox (id, event_id, destination, state, available_at, delivered_at) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (uuid4(), event, destination, state, now, now if delivered else None),
    )


@pg
def test_outbox_rows_are_unique_per_destination_and_validated(db: psycopg.Connection, tree: Tree) -> None:
    event = _workspace_event(db, tree.ws_a, 1)
    _outbox(db, event, "sse")
    _outbox(db, event, "exports.plan_archived_note")
    _outbox(db, event, "hook:audit-1")
    with pytest.raises(pgerr.UniqueViolation):
        _outbox(db, event, "sse")
    for destination in ("Exports.Note", "plain", "hook:"):
        with pytest.raises(pgerr.CheckViolation):
            _outbox(db, event, destination)
    with pytest.raises(pgerr.CheckViolation):
        _outbox(db, event, "other.consumer", state="delivered")  # delivered needs delivered_at
    with pytest.raises(pgerr.CheckViolation):
        _outbox(db, event, "other.consumer", state="pending", delivered=True)
    with pytest.raises(pgerr.ForeignKeyViolation):
        _outbox(db, uuid4(), "sse")
    _outbox(db, event, "other.consumer", state="delivered", delivered=True)


@pg
def test_consumer_receipts_reference_events_and_reject_update(db: psycopg.Connection, tree: Tree) -> None:
    event = _workspace_event(db, tree.ws_a, 1)
    now = NOW
    db.execute("INSERT INTO skm_core.consumer_receipts VALUES ('exports.note', %s, %s)", (event, now))
    with pytest.raises(pgerr.UniqueViolation):
        db.execute("INSERT INTO skm_core.consumer_receipts VALUES ('exports.note', %s, %s)", (event, now))
    with pytest.raises(pgerr.ForeignKeyViolation):
        db.execute("INSERT INTO skm_core.consumer_receipts VALUES ('exports.note', %s, %s)", (uuid4(), now))
    with pytest.raises(pgerr.RestrictViolation):
        db.execute("UPDATE skm_core.consumer_receipts SET consumer_id = 'exports.other'")
    assert db.execute("DELETE FROM skm_core.consumer_receipts").rowcount == 1  # outbox_gc


def _receipt(conn: psycopg.Connection, workspace: UUID | None, **columns: object) -> None:
    now = NOW
    row: dict[str, object] = {
        "id": uuid4(),
        "workspace_id": workspace,
        "principal_id": _NIL,
        "operation": "planning.publish_revision",
        "key": "k1",
        "request_digest": _DIGEST,
        "result_type": "urn:skm:workspace:result:create-project:v1",
        "result": to_jsonb({}),
        "created_at": now,
        "expires_at": now + timedelta(hours=1),
    }
    row.update(columns)
    names = sql.SQL(", ").join(sql.Identifier(name) for name in row)
    marks = sql.SQL(", ").join(sql.Placeholder() for _ in row)
    conn.execute(
        sql.SQL("INSERT INTO skm_core.idempotency_receipts ({}) VALUES ({})").format(names, marks),
        list(row.values()),
    )


@pg
def test_instance_level_receipts_are_unique_although_workspace_id_is_null(
    db: psycopg.Connection, tree: Tree
) -> None:
    _receipt(db, None)
    with pytest.raises(pgerr.UniqueViolation):
        _receipt(db, None)
    _receipt(db, None, key="k2")
    _receipt(db, None, principal_id=uuid4())
    _receipt(db, tree.ws_a)  # the same identity in a workspace is another scope
    with pytest.raises(pgerr.UniqueViolation):
        _receipt(db, tree.ws_a)
    _receipt(db, tree.ws_b)


@pg
def test_scope_key_is_generated_and_never_inserted(db: psycopg.Connection, tree: Tree) -> None:
    with pytest.raises(pgerr.GeneratedAlways):
        _receipt(db, None, scope_key=tree.ws_a)
    with pytest.raises(pgerr.GeneratedAlways):
        _receipt(db, tree.ws_a, scope_key=tree.ws_a)
    _receipt(db, None)
    _receipt(db, tree.ws_a)
    keys = db.execute(
        "SELECT workspace_id, scope_key FROM skm_core.idempotency_receipts ORDER BY workspace_id NULLS FIRST"
    ).fetchall()
    assert keys == [(None, _NIL), (tree.ws_a, tree.ws_a)]
    with pytest.raises(pgerr.GeneratedAlways):
        db.execute("UPDATE skm_core.idempotency_receipts SET scope_key = %s", (tree.ws_b,))


@pg
@pytest.mark.parametrize(
    "changes",
    [
        {"key": "has space"},
        {"key": ""},
        {"operation": "NoDot"},
        {"request_digest": "sha256:ABC"},
        {"result_type": ""},
        {"result": to_jsonb({"x": "y" * 1048576})},
    ],
    ids=["key-space", "key-empty", "operation", "digest", "result-type", "result-size"],
)
def test_receipt_shape_is_checked(db: psycopg.Connection, changes: dict[str, object]) -> None:
    with pytest.raises(pgerr.CheckViolation):
        _receipt(db, None, **changes)


@pg
def test_receipt_must_expire_after_creation_and_reference_a_scope(db: psycopg.Connection) -> None:
    now = NOW
    with pytest.raises(pgerr.CheckViolation):
        _receipt(db, None, created_at=now, expires_at=now)
    with pytest.raises(pgerr.ForeignKeyViolation):
        _receipt(db, uuid4())


def _audit(conn: psycopg.Connection, workspace: UUID | None, decision: str, reason: str | None) -> UUID:
    audit_id = uuid4()
    conn.execute(
        "INSERT INTO skm_core.audit_records "
        "(id, workspace_id, actor_id, action, decision, reason_code, request_id) "
        "VALUES (%s, %s, %s, 'planning.read', %s, %s, 'r1')",
        (audit_id, workspace, uuid4(), decision, reason),
    )
    return audit_id


@pg
def test_audit_records_are_append_only_and_consistent(db: psycopg.Connection, tree: Tree) -> None:
    allowed = _audit(db, tree.ws_a, "allowed", None)
    _audit(db, None, "denied", "permission_denied")
    with pytest.raises(pgerr.CheckViolation):
        _audit(db, None, "denied", None)
    with pytest.raises(pgerr.CheckViolation):
        _audit(db, None, "allowed", "permission_denied")
    with pytest.raises(pgerr.CheckViolation):
        _audit(db, None, "maybe", None)
    with pytest.raises(pgerr.ForeignKeyViolation):
        _audit(db, uuid4(), "allowed", None)
    with pytest.raises(pgerr.RestrictViolation):
        db.execute("UPDATE skm_core.audit_records SET action = 'x.y' WHERE id = %s", (allowed,))
    with pytest.raises(pgerr.RestrictViolation):
        db.execute("DELETE FROM skm_core.audit_records WHERE id = %s", (allowed,))
    assert db.execute("SELECT count(*) FROM skm_core.audit_records").fetchone() == (2,)


# --- PostgresScopeRegistry / PostgresScopeTree over the real DDL --------------------------------------------


def _sid(value: UUID) -> ScopeId:
    return ScopeId(value)


@pg
def test_registry_builds_the_tree_and_reads_it_back(db: psycopg.Connection) -> None:
    registry = PostgresScopeRegistry(db)
    instance, ws, project, plan, run, host = (_sid(uuid4()) for _ in range(6))
    with pytest.raises(NotFound):
        registry.instance()
    registry.create(instance, ScopeKind.INSTANCE, parent=None, workspace_id=None)
    registry.create(ws, ScopeKind.WORKSPACE, parent=instance, workspace_id=WorkspaceId(ws))
    registry.create(project, ScopeKind.PROJECT, parent=ws, workspace_id=WorkspaceId(ws))
    registry.create(plan, ScopeKind.PLAN, parent=project, workspace_id=WorkspaceId(ws))
    registry.create(run, ScopeKind.RUN, parent=plan, workspace_id=WorkspaceId(ws))
    registry.create(host, ScopeKind.HOST, parent=instance, workspace_id=None)
    assert registry.instance().id == instance
    record = registry.get(run)
    assert (record.kind, record.parent_id, record.workspace_id) == (ScopeKind.RUN, plan, ws)
    assert record.created_at.tzinfo is not None
    assert [r.id for r in registry.ancestors(run)] == [instance, ws, project, plan, run]
    assert [r.id for r in registry.ancestors(host)] == [instance, host]
    ids = sorted((instance, ws, project, plan, run, host))
    assert [r.id for r in registry.list_scopes()] == ids
    assert [r.id for r in registry.list_scopes(limit=2)] == ids[:2]
    assert [r.id for r in registry.list_scopes(after=ids[1], limit=2)] == ids[2:4]
    assert registry.list_scopes(after=ids[-1]) == ()
    with pytest.raises(NotFound):
        registry.get(_sid(uuid4()))
    with pytest.raises(NotFound):
        registry.ancestors(_sid(uuid4()))
    with pytest.raises(ValueError, match="page limit"):
        registry.list_scopes(limit=0)
    with pytest.raises(TypeError, match="UUID"):
        registry.list_scopes(after="x")  # pyright: ignore[reportArgumentType]


@pg
def test_registry_refuses_foreign_workspaces_and_wrong_parents(db: psycopg.Connection, tree: Tree) -> None:
    registry = PostgresScopeRegistry(db)
    new = _sid(uuid4())
    refused = [
        (ScopeKind.PROJECT, tree.ws_a, tree.ws_b),
        (ScopeKind.PROJECT, tree.ws_a, None),
        (ScopeKind.PROJECT, tree.instance, tree.ws_a),
        (ScopeKind.PLAN, tree.ws_a, tree.ws_a),
        (ScopeKind.RUN, tree.ws_a, tree.ws_a),
        (ScopeKind.HOST, tree.ws_a, None),
        (ScopeKind.HOST, tree.instance, tree.ws_a),
        (ScopeKind.WORKSPACE, tree.instance, tree.ws_a),
        (ScopeKind.INSTANCE, tree.instance, None),
    ]
    for kind, parent, workspace in refused:
        with pytest.raises(ValidationFailed) as caught:
            registry.create(
                new,
                kind,
                parent=_sid(parent),
                workspace_id=None if workspace is None else WorkspaceId(workspace),
            )
        assert caught.value.code is ErrorCode.SCHEMA_INVALID
    with pytest.raises(NotFound):
        registry.create(new, ScopeKind.PROJECT, parent=_sid(uuid4()), workspace_id=WorkspaceId(tree.ws_a))
    assert db.execute("SELECT count(*) FROM skm_core.scopes WHERE id = %s", (new,)).fetchone() == (0,)

    registry.create(new, ScopeKind.RUN, parent=_sid(tree.project), workspace_id=WorkspaceId(tree.ws_a))
    assert [record.id for record in registry.ancestors(new)] == [tree.instance, tree.ws_a, tree.project, new]


@pg
def test_registry_maps_a_second_instance_and_a_duplicate_id_to_already_exists(
    db: psycopg.Connection, tree: Tree
) -> None:
    registry = PostgresScopeRegistry(db)
    with pytest.raises(Conflict) as second:
        registry.create(_sid(uuid4()), ScopeKind.INSTANCE, parent=None, workspace_id=None)
    assert second.value.code is ErrorCode.ALREADY_EXISTS
    with pytest.raises(Conflict) as duplicate:
        registry.create(
            _sid(tree.project), ScopeKind.PROJECT, parent=_sid(tree.ws_b), workspace_id=WorkspaceId(tree.ws_b)
        )
    assert duplicate.value.code is ErrorCode.ALREADY_EXISTS
    assert registry.get(_sid(tree.project)).parent_id == tree.ws_a


@pg
def test_scope_tree_chains_follow_parents_and_reject_the_other_chain(
    db: psycopg.Connection, tree: Tree
) -> None:
    scopes = PostgresScopeTree(db)
    assert scopes.instance_scope().scope_id == tree.instance
    work = scopes.chain_for(ScopeRef(Level.RUN, tree.run), Chain.WORK)
    assert [s.scope_id for s in work.scopes] == [tree.instance, tree.ws_a, tree.project, tree.plan, tree.run]
    assert work.scopes[0].label == "instance"
    assert work.scopes[-1].label == f"run:{tree.run}"
    host = scopes.chain_for(ScopeRef(Level.HOST, tree.host), Chain.HOST)
    assert [s.scope_id for s in host.scopes] == [tree.instance, tree.host]
    assert [
        s.scope_id for s in scopes.chain_for(ScopeRef(Level.INSTANCE, tree.instance), Chain.HOST).scopes
    ] == [tree.instance]
    with pytest.raises(ValidationFailed) as caught:
        scopes.chain_for(ScopeRef(Level.HOST, tree.host), Chain.WORK)
    assert caught.value.code is ErrorCode.CONFIG_SCOPE_NOT_ALLOWED
    with pytest.raises(ValidationFailed) as caught:
        scopes.chain_for(ScopeRef(Level.WORKSPACE, tree.project), Chain.WORK)
    assert caught.value.code is ErrorCode.INVALID_REFERENCE
    with pytest.raises(NotFound):
        scopes.chain_for(ScopeRef(Level.PROJECT, uuid4()), Chain.WORK)
