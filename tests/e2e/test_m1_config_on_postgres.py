"""M1 (P03.Z): a clean install keeps its configuration and local identity on PostgreSQL across processes.

One scenario on a fresh scratch database created from ``SKM_TEST_DATABASE_URL`` (loopback and ``*_test``
only, dropped afterwards): ``skm init`` migrates the whole packaged chain and creates the instance, the local
owner and the personal workspace; ``skm db verify|status`` agree; ``skm config explain|set|get`` each run in
their own process and see only committed state; a narrowing violation writes nothing; every write leaves its
entry, history row, event, idempotency receipt and allowed audit in one transaction. Then every server session
is terminated, the CLI starts again from the profile and finds the same values, reads write nothing, a rerun
of ``skm init`` keeps everything, and an idempotency receipt survives a restart of the embedded composition.

Every ``skm`` is a real subprocess with explicit ``HOME``/``XDG_*`` under ``tmp_path`` and the production
composition; the DSN reaches it only through ``SKM_DATABASE_URL`` and the profile's reference. A skip for a
missing test database is not an M1 result: run with ``SKM_REQUIRE_PG=1``.
"""

import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from skm.adapters.postgres.migrations.runner import discover_migrations
from skm.application_bus.client import EmbeddedClient
from skm.bootstrap.composition import App, open_cli_app
from skm.kernel.errors import SkmError
from skm.kernel.ports_uow import Surface
from skm.modules.settings import public as settings
from skm.platform.config.bootstrap import load_bootstrap

pytestmark = [pytest.mark.e2e, pytest.mark.pg]

ENTRY = "import sys; from skm.entrypoints.cli.main import main; sys.exit(main())"
# Only what the interpreter needs; HOME and XDG always point into the sandbox.
PASSED = ("PATH", "PYTHONPATH", "LANG", "LC_ALL", "TMPDIR")
OWNER_NAME = "m1-owner"
ROUNDS = "execution.review.max_rounds"
CHANGED = "urn:skm:settings:event:config-changed:v1"
SET_VALUE = "settings.set_value"


@dataclass(frozen=True)
class Sandbox:
    root: Path
    dsn: str

    @property
    def home(self) -> Path:
        return self.root / "home"

    @property
    def bootstrap(self) -> Path:
        return self.root / "config/skm/bootstrap.toml"

    @property
    def owner_token(self) -> Path:
        return self.root / "state/skm/secrets/owner.token"

    def env(self) -> dict[str, str]:
        env = {name: os.environ[name] for name in PASSED if name in os.environ}
        env.update(
            HOME=str(self.home),
            XDG_CONFIG_HOME=str(self.root / "config"),
            XDG_STATE_HOME=str(self.root / "state"),
            XDG_DATA_HOME=str(self.root / "data"),
            USER=OWNER_NAME,
            PYTHONDONTWRITEBYTECODE="1",
            SKM_DATABASE_URL=self.dsn,  # the profile stores only a reference to it
        )
        return env


def skm(box: Sandbox, *argv: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", ENTRY, "--json", *argv],
        env=box.env(),
        cwd=box.root,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=300,
        check=False,
    )


def ok(box: Sandbox, *argv: str) -> dict[str, Any]:
    done = skm(box, *argv)
    assert done.returncode == 0, done.stdout + done.stderr
    return cast("dict[str, Any]", json.loads(done.stdout)["result"])


def failed(box: Sandbox, code: int, *argv: str) -> dict[str, Any]:
    done = skm(box, *argv)
    assert done.returncode == code, done.stdout + done.stderr
    return cast("dict[str, Any]", json.loads(done.stdout)["error"])


# --- the scratch database --------------------------------------------------------------------------


def _checked_admin(dsn: str) -> None:
    """CREATE/DROP DATABASE only on a loopback or socket test server through '*_test' (testing spec 1.11)."""
    info = {key: str(value) for key, value in conninfo_to_dict(dsn).items()}
    host = info.get("host", "")
    local = host in {"", "localhost", "127.0.0.1", "::1"} or host.startswith("/")
    if not local or not info.get("dbname", "").endswith("_test"):
        pytest.fail("M1 creates databases only on a local server through '*_test'", pytrace=False)


@dataclass(frozen=True)
class Scratch:
    admin_dsn: str
    name: str
    dsn: str


@pytest.fixture
def scratch(pg_dsn: str) -> Iterator[Scratch]:
    _checked_admin(pg_dsn)
    name = f"skm_t_m1_{os.getpid()}_{uuid4().hex[:8]}"
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
        try:
            yield Scratch(pg_dsn, name, make_conninfo(pg_dsn, dbname=name))
        finally:
            admin.execute(sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(sql.Identifier(name)))


def rows(dsn: str, query: str, *params: object) -> list[tuple[Any, ...]]:
    with psycopg.connect(dsn, autocommit=True) as conn:
        return [tuple(row) for row in conn.execute(query, params).fetchall()]  # pyright: ignore[reportArgumentType]


def terminate_sessions(db: Scratch) -> int:
    """Every server session of the scratch database ends, as on a server restart."""
    with psycopg.connect(db.admin_dsn, autocommit=True) as admin:
        found = admin.execute(
            "SELECT count(pg_terminate_backend(pid)) FROM pg_stat_activity "
            "WHERE datname = %s AND pid <> pg_backend_pid()",
            (db.name,),
        ).fetchone()
    return cast("int", found[0]) if found else 0


@dataclass(frozen=True)
class Durable:
    """The rows M1 promises to keep: config state, its events, the command receipts and audit."""

    generation: int
    entries: list[tuple[Any, ...]]
    history: list[tuple[Any, ...]]
    events: list[tuple[Any, ...]]
    receipts: list[tuple[Any, ...]]
    audit: list[tuple[Any, ...]]


def durable(dsn: str) -> Durable:
    return Durable(
        generation=cast("int", rows(dsn, "SELECT value FROM skm_config.generation WHERE id = 1")[0][0]),
        entries=rows(
            dsn,
            "SELECT id, scope_id, key, op, value, locked, row_version, reason, created_by "
            "FROM skm_config.entries ORDER BY id",
        ),
        history=rows(
            dsn,
            "SELECT id, entry_id, scope_id, key, change_kind, new_value, actor_id, request_id, generation "
            "FROM skm_config.entry_history ORDER BY generation, id",
        ),
        events=rows(
            dsn,
            "SELECT id, event_type, workspace_id, workspace_seq, global_position, stream_kind, stream_id, "
            "stream_seq, actor_id, request_id, payload FROM skm_core.domain_events ORDER BY recorded_at, id",
        ),
        receipts=rows(
            dsn,
            "SELECT id, principal_id, operation, key, request_digest, result_type, result "
            "FROM skm_core.idempotency_receipts ORDER BY created_at, id",
        ),
        audit=rows(
            dsn,
            "SELECT id, actor_id, action, decision, reason_code, request_id, target "
            "FROM skm_core.audit_records ORDER BY recorded_at, id",
        ),
    )


def _kept(before: list[tuple[Any, ...]], after: list[tuple[Any, ...]]) -> bool:
    return all(row in after for row in before)


# --- the embedded composition of the sandbox profile -----------------------------------------------


class Embedded:
    """The production composition of the sandbox profile in this process (no overrides)."""

    def __init__(self, box: Sandbox) -> None:
        env = box.env()
        bootstrap = load_bootstrap(str(box.bootstrap), env, box.home)
        self.app: App
        self.app, owner = open_cli_app(bootstrap, environ=env, invocation={}, as_token=None)
        client = self.app.client(actor=owner, surface=Surface.CLI)
        assert isinstance(client, EmbeddedClient)
        self.owner = client

    def close(self) -> None:
        self.app.close()


@pytest.fixture
def embedded() -> Iterator[list[Embedded]]:
    opened: list[Embedded] = []
    yield opened
    for item in opened:
        item.close()


def _set_rounds(value: int) -> settings.SetValue:
    return settings.SetValue.from_json(
        {"scope": {"level": "instance"}, "key": ROUNDS, "value": value, "reason": "m1 replay"}
    )


# --- the scenario ----------------------------------------------------------------------------------


def _contribution_statuses(report: dict[str, Any]) -> dict[str, str]:
    return {item["layer"]["level"]: item["status"] for item in report["contributions"]}


@pytest.mark.slow
def test_m1_init_config_and_identity_survive_processes_and_restarts(  # noqa: PLR0915 - one ordered scenario
    tmp_path: Path, scratch: Scratch, embedded: list[Embedded]
) -> None:
    box = Sandbox(tmp_path / "sandbox", scratch.dsn)
    box.home.mkdir(parents=True)
    chain = [item.version for item in discover_migrations()]
    current = chain[-1]

    # 1. clean init: the whole packaged chain, the instance, the local owner, the personal workspace
    first = ok(box, "init", "--database-url", scratch.dsn, "--host-name", "m1")
    assert first["already_initialized"] is False
    assert first["migrations"] == {"applied": chain, "current": current}
    instance_id = UUID(first["instance_id"])
    owner_id = UUID(first["owner_principal_id"])
    workspace_id = UUID(first["workspace"]["workspace_id"])
    assert first["workspace"]["slug"] == "personal"
    secret = box.owner_token.read_text(encoding="utf-8").strip()
    assert secret
    assert rows(scratch.dsn, "SELECT id FROM skm_core.scopes WHERE kind = 'instance'") == [(instance_id,)]
    assert str(conninfo_to_dict(scratch.dsn)["dbname"]) not in box.bootstrap.read_text(encoding="utf-8")

    # 2. the migration history verifies; the DSN comes from the profile's reference
    assert ok(box, "db", "verify") == {"ok": True, "known_version": current, "pending": []}
    status = ok(box, "db", "status")
    assert (status["state"], status["db_version"], status["known_version"]) == ("ok", current, current)
    who = ok(box, "whoami")
    assert who["principal"]["principal_id"] == str(owner_id)

    # 3. config across processes: explain the default, set, get, narrow, explain the provenance
    start = durable(scratch.dsn)
    untouched = ok(box, "config", "explain", ROUNDS, "--scope", "instance")
    assert untouched["keys"][0]["value"] == 2
    assert untouched["keys"][0]["winner"]["level"] == "default"
    assert untouched["generation"] == start.generation

    at_instance = ok(
        box, "config", "set", ROUNDS, "4", "--scope", "instance", "--reason", "allow deeper reviews"
    )
    assert (at_instance["changed"], at_instance["generation"]) == (True, start.generation + 1)
    assert ok(box, "config", "get", ROUNDS, "--scope", "instance")["value"] == 4
    assert ok(box, "config", "get", ROUNDS)["value"] == 4  # the selected personal workspace inherits it

    workspace = f"workspace:{workspace_id}"
    ok(box, "config", "set", ROUNDS, "3", "--scope", workspace, "--reason", "complex workspace")
    written = durable(scratch.dsn)
    wider = failed(box, 1, "config", "set", ROUNDS, "6", "--scope", workspace)
    assert wider["code"] == "CONFIG_NARROWING_VIOLATION"
    assert durable(scratch.dsn) == written  # a refused write leaves no entry, event, receipt or audit

    explained = ok(box, "config", "explain", ROUNDS, "--scope", workspace)
    report = explained["keys"][0]
    assert explained["generation"] == start.generation + 2
    assert report["value"] == 3
    assert (report["winner"]["level"], report["winner"]["scope_id"], report["winner"]["row_version"]) == (
        "workspace",
        str(workspace_id),
        1,
    )
    statuses = _contribution_statuses(report)
    assert (statuses["instance"], statuses["workspace"]) == ("used", "winner")

    # 4. every write committed state, history, event, receipt and allowed audit together
    assert written.generation == start.generation + 2
    assert sorted((str(row[1]), row[2], row[3], row[4], row[6], row[8]) for row in written.entries) == sorted(
        [
            (str(instance_id), ROUNDS, "set", 4, 1, owner_id),
            (str(workspace_id), ROUNDS, "set", 3, 1, owner_id),
        ]
    )
    new_history = [row for row in written.history if row not in start.history]
    assert [(row[2], row[4], row[5], row[6], row[8]) for row in new_history] == [
        (instance_id, "created", 4, owner_id, start.generation + 1),
        (workspace_id, "created", 3, owner_id, start.generation + 2),
    ]
    changed = [row for row in written.events if row[1] == CHANGED and row not in start.events]
    assert [row[10]["generation"] for row in changed] == [start.generation + 1, start.generation + 2]
    # an event's actor is optional (EventEnvelope.actor_id); the audit row of the same request names it
    assert {row[8] for row in changed} <= {None, owner_id}
    receipts = [row for row in written.receipts if row[2] == SET_VALUE and row not in start.receipts]
    assert len(receipts) == 2
    assert all(row[1] == owner_id for row in receipts)
    allowed = [row for row in written.audit if row[2] == SET_VALUE and row not in start.audit]
    assert [(row[1], row[3], row[4]) for row in allowed] == [(owner_id, "allowed", None)] * 2
    # the event, the history row and the audit of one write carry the same request
    assert [row[9] for row in changed] == [row[5] for row in allowed] == [row[7] for row in new_history]

    # 5. restart: every server session ends; new processes start from the profile and find the same state
    terminate_sessions(scratch)
    assert ok(box, "config", "get", ROUNDS, "--scope", "instance")["value"] == 4
    again = ok(box, "config", "explain", ROUNDS, "--scope", workspace)
    assert again["keys"][0] == report
    assert again["generation"] == explained["generation"]
    history = ok(box, "config", "history", ROUNDS, "--scope", workspace)
    assert [item["change_kind"] for item in history["items"]] == ["created"]
    reads = durable(scratch.dsn)
    assert (reads.generation, reads.entries, reads.history) == (
        written.generation,
        written.entries,
        written.history,
    )
    assert (reads.events, reads.receipts) == (written.events, written.receipts)  # reads write nothing
    assert _kept(written.audit, reads.audit)
    assert [row for row in reads.audit if row[2] == SET_VALUE] == [
        row for row in written.audit if row[2] == SET_VALUE
    ]

    # 6. a rerun of init keeps the instance, the owner, the workspace and every config row
    rerun = ok(box, "init")
    assert rerun["already_initialized"] is True
    assert rerun["migrations"] == {"applied": [], "current": current}
    assert (rerun["instance_id"], rerun["owner_principal_id"]) == (str(instance_id), str(owner_id))
    assert rerun["workspace"] == {"workspace_id": str(workspace_id), "slug": "personal", "created": False}
    assert box.owner_token.read_text(encoding="utf-8").strip() == secret
    after_init = durable(scratch.dsn)
    assert (after_init.generation, after_init.entries, after_init.history) == (
        written.generation,
        written.entries,
        written.history,
    )
    for name in ("events", "receipts", "audit"):
        assert _kept(getattr(written, name), getattr(after_init, name)), name
    assert ok(box, "db", "verify") == {"ok": True, "known_version": current, "pending": []}
    assert ok(box, "config", "get", ROUNDS, "--scope", "instance")["value"] == 4

    # 7. an idempotency receipt outlives the composition that wrote it
    world = Embedded(box)
    embedded.append(world)
    replayed = cast(
        "settings.SetValueResult", world.owner.dispatch(_set_rounds(5), idempotency_key="m1-replay")
    )
    assert (replayed.changed, replayed.generation) == (True, written.generation + 1)
    terminate_sessions(scratch)
    world.close()
    embedded.remove(world)
    once = durable(scratch.dsn)

    restarted = Embedded(box)
    embedded.append(restarted)
    repeat = cast(
        "settings.SetValueResult", restarted.owner.dispatch(_set_rounds(5), idempotency_key="m1-replay")
    )
    assert repeat.to_json() == replayed.to_json()  # the stored result, not a second write
    with pytest.raises(SkmError) as reused:
        restarted.owner.dispatch(_set_rounds(6), idempotency_key="m1-replay")
    assert reused.value.code.value == "IDEMPOTENCY_KEY_REUSED"
    final = durable(scratch.dsn)
    assert (final.generation, final.entries, final.history) == (once.generation, once.entries, once.history)
    assert (final.events, final.receipts) == (once.events, once.receipts)
    assert ok(box, "config", "get", ROUNDS, "--scope", "instance")["value"] == 5
    assert ok(box, "config", "get", ROUNDS, "--scope", workspace)["value"] == 3

    # the owner token never reaches the database's events or audit
    dumped = rows(
        scratch.dsn,
        "SELECT coalesce(string_agg(payload::text, ''), '') FROM skm_core.domain_events "
        "UNION ALL SELECT coalesce(string_agg(target::text, ''), '') FROM skm_core.audit_records",
    )
    assert all(secret not in cast("str", text) for (text,) in dumped)
