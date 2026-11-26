"""Planning DDL in the project baseline (planning §11.1-11.4).

The database must refuse even a writer that bypasses the adapters, so the constraints are exercised with raw
SQL as the owner on the session database (``support.pg``) and as the runtime role ``skm_app``:

* a typed row needs a member of its own kind; a link connects members of one revision of one plan;
* parents, restore sources, drafts and the current pointer stay inside their plan; an entity id is never
  reused, even across plans, and an entity never changes kind;
* aliases, ``purpose``, ``origin`` and ``restored_from_revision_id`` keep their shapes;
* every row of a published revision refuses UPDATE and DELETE; a ``file_version`` material has its pin;
* ``work_policy`` is a nullable object of at most 4 KiB; omitted values stay NULL; closed shapes and enums
  belong to the application schema;
* ``skm_app`` appends to the immutable tables, changes only the mutable ones and executes no DDL.
"""

from collections.abc import Iterator, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from itertools import count
from typing import Any
from uuid import UUID, uuid4

import psycopg
import pytest
from psycopg import errors as pgerr
from psycopg import sql

from skm.adapters.postgres.jsonb import to_jsonb
from skm.adapters.postgres.migrations.runner import discover_migrations
from support.pg import (  # noqa: F401
    TestDatabase,
    clean_test_database,
    pg_session,
    test_database,
)
from support.seed import SEED

pytestmark = pytest.mark.pg

NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)
_DIGEST = "sha256:" + "a" * 64
_PRINCIPAL = UUID("01900000-0000-7000-8000-0000000000c1")
_DOCUMENT_LIMIT = 16 * 1024 * 1024
_POLICY_LIMIT = 4096
_POLICY_ENVELOPE = len('{"k": ""}')  # the bytes of jsonb::text around the padding of _policy

# table -> (entity kind, id column) of the typed rows of §11.1
_TYPED: Mapping[str, tuple[str, str]] = {
    "phase_specs": ("phase", "phase_id"),
    "item_specs": ("item", "item_id"),
    "unit_specs": ("unit", "unit_id"),
    "requirement_specs": ("requirement", "requirement_id"),
    "check_specs": ("check", "check_id"),
    "acceptance_criteria": ("criterion", "criterion_id"),
    "decision_specs": ("decision", "decision_id"),
    "material_specs": ("material", "material_id"),
}
# "неизменяемая" in §11.1: each has the trigger on skm_planning.tg_immutable and no UPDATE/DELETE for skm_app
_IMMUTABLE = (
    "acceptance_criteria",
    "artifact_specs",
    "batch_members",
    "batch_specs",
    "check_specs",
    "criterion_check_bindings",
    "decision_bindings",
    "decision_specs",
    "decision_supersessions",
    "dependency_edges",
    "entity_check_bindings",
    "entity_path_specs",
    "entity_read_specs",
    "entity_relations",
    "entity_requirement_links",
    "entity_skill_requirements",
    "item_specs",
    "material_bindings",
    "material_specs",
    "phase_specs",
    "plan_entity_identities",
    "plan_relations",
    "plan_revisions",
    "requirement_specs",
    "review_requirements",
    "revision_file_bindings",
    "revision_members",
    "revision_payloads",
    "revision_specs",
    "unit_specs",
)
_INSERT_ONLY = ("plan_aliases",)
_MUTABLE = ("plan_drafts", "plans", "project_plan_counters")
_INDEXES = (  # §11.4
    "ix_decision_bindings__revision_id_entity_id",
    "ix_dependency_edges__revision_id_prerequisite",
    "ix_entity_requirement_links__revision_id_requirement_id",
    "ix_plan_drafts__plan_id_state",
    "ix_plans__workspace_id_project_id_lifecycle_state_updated_at_id",
    "ix_revision_file_bindings__file_version_id",
    "ix_revision_members__revision_id_entity_kind_position",
    "uq_plan_revisions__plan_id_revision_no",
    "uq_revision_members__revision_id_display_key",
)
_DEFERRED_CROSS_MODULE = (  # examples/sql/README.md, "Отложенные ссылки"
    "fk_attempt_steps__context_manifests",
    "fk_reviews__resource_versions",
    "fk_runs__resource_versions",
)
_NUMBERS = count(1)


@dataclass(frozen=True)
class Rev:
    workspace: UUID
    plan: UUID
    id: UUID

    @property
    def scope(self) -> dict[str, object]:
        return {"workspace_id": self.workspace, "plan_id": self.plan, "revision_id": self.id}


@dataclass(frozen=True)
class Content(Rev):
    """A published revision with a row in every immutable table; the members are its entity ids."""

    phase: UUID
    item: UUID
    item2: UUID
    unit: UUID
    requirement: UUID
    check: UUID
    criterion: UUID
    decision: UUID
    decision2: UUID
    material: UUID


@dataclass(frozen=True)
class World:
    """Plans A and B in one project, A2 free for aliases, plan C of another workspace, and their revisions."""

    conn: psycopg.Connection
    ws_a: UUID
    ws_b: UUID
    project_a: UUID
    project_a2: UUID
    project_b: UUID
    plan_c: UUID
    rev_c: UUID
    file_a: UUID
    file_b: UUID
    a: Content
    b: Content


def _insert(conn: psycopg.Connection, table: str, row: Mapping[str, object]) -> None:
    """``table`` is ``schema.name``; a bare name belongs to ``skm_planning``."""
    name = table.split(".") if "." in table else ["skm_planning", table]
    conn.execute(
        sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(*name),
            sql.SQL(", ").join(sql.Identifier(column) for column in row),
            sql.SQL(", ").join(sql.Placeholder() for _ in row),
        ),
        list(row.values()),
    )


def _project(conn: psycopg.Connection, workspace: UUID, slug: str) -> UUID:
    project = uuid4()
    _insert(
        conn,
        "skm_core.scopes",
        {"id": project, "kind": "project", "parent_id": workspace, "workspace_id": workspace},
    )
    _insert(
        conn,
        "skm_workspace.projects",
        {
            "id": project,
            "workspace_id": workspace,
            "slug": slug,
            "title": "P",
            "created_at": NOW,
            "updated_at": NOW,
        },
    )
    return project


def _plan_row(workspace: UUID, project: UUID, plan: UUID, **changes: object) -> dict[str, object]:
    return {
        "workspace_id": workspace,
        "project_id": project,
        "id": plan,
        "title": "Plan",
        "created_by": _PRINCIPAL,
        "created_at": NOW,
        "updated_at": NOW,
    } | changes


def _plan_scope(conn: psycopg.Connection, workspace: UUID, project: UUID) -> UUID:
    plan = uuid4()
    _insert(
        conn,
        "skm_core.scopes",
        {"id": plan, "kind": "plan", "parent_id": project, "workspace_id": workspace},
    )
    return plan


def _plan(conn: psycopg.Connection, workspace: UUID, project: UUID, **changes: object) -> UUID:
    plan = _plan_scope(conn, workspace, project)
    _insert(conn, "plans", _plan_row(workspace, project, plan, **changes))
    return plan


def _revision_row(
    workspace: UUID, plan: UUID, no: int = 1, parent: object = None, **changes: object
) -> dict[str, object]:
    return {
        "workspace_id": workspace,
        "plan_id": plan,
        "id": uuid4(),
        "revision_no": no,
        "parent_revision_id": parent,
        "schema_version": 1,
        "content_digest": _DIGEST,
        "published_by": _PRINCIPAL,
        "published_at": NOW,
        "change_reason": "published",
    } | changes


def _revision(
    conn: psycopg.Connection, workspace: UUID, plan: UUID, no: int = 1, parent: UUID | None = None
) -> Rev:
    revision = uuid4()
    _insert(conn, "plan_revisions", _revision_row(workspace, plan, no, parent, id=revision))
    return Rev(workspace, plan, revision)


def _identity_row(rev: Rev, entity: UUID, kind: str) -> dict[str, object]:
    return {
        "workspace_id": rev.workspace,
        "plan_id": rev.plan,
        "entity_id": entity,
        "entity_kind": kind,
        "first_revision_id": rev.id,
        "created_at": NOW,
    }


def _member_row(rev: Rev, entity: UUID, kind: str, **changes: object) -> dict[str, object]:
    return (
        rev.scope
        | {
            "entity_id": entity,
            "entity_kind": kind,
            "display_key": f"{kind}-{entity.hex}",
            "position": 0,
        }
        | changes
    )


def _member(conn: psycopg.Connection, rev: Rev, kind: str) -> UUID:
    entity = uuid4()
    _insert(conn, "plan_entity_identities", _identity_row(rev, entity, kind))
    _insert(conn, "revision_members", _member_row(rev, entity, kind))
    return entity


def _typed_row(table: str, content: Content, entity: UUID, **changes: object) -> dict[str, object]:
    """A valid row of a typed table (a refusal differs from it by one value); owners come from content."""
    number = next(_NUMBERS)
    rows: dict[str, dict[str, object]] = {
        "phase_specs": {"title": "T", "goal": "G", "design_state": "skeleton", "depends_on_declared": False},
        "item_specs": {"phase_id": content.phase, "title": "T", "summary": "S", "why": "W"},
        "unit_specs": {"item_id": content.item, "local_key": f"U{number}", "title": "T", "goal": "G"},
        "requirement_specs": {"statement": "S", "priority": "must", "source_kind": "owner"},
        "check_specs": {
            "owner_entity_id": content.item,
            "owner_kind": "item",
            "local_key": f"V{number}",
            "kind": "manual",
            "category": "acceptance",
            "required": True,
            "definition": to_jsonb({}),
        },
        "acceptance_criteria": {
            "owner_entity_id": content.item,
            "owner_kind": "item",
            "statement": "S",
            "verification_mode": "manual",
        },
        "decision_specs": {"title": "T", "state": "rejected"},
        "material_specs": {
            "title": "T",
            "kind": "repository_path",
            "role": "reference",
            "mount_name": "main",
            "path": "README.md",
        },
    }
    identity = {_TYPED[table][1]: entity, "position": number}
    return content.scope | identity | rows[table] | changes


def _publish(conn: psycopg.Connection, workspace: UUID, plan: UUID, file_version: UUID) -> Content:
    """One revision in the order of §11.3; the pin of its material is checked when the transaction ends."""
    with conn.transaction():
        rev = _revision(conn, workspace, plan)
        made = Content(
            workspace,
            plan,
            rev.id,
            phase=_member(conn, rev, "phase"),
            item=_member(conn, rev, "item"),
            item2=_member(conn, rev, "item"),
            unit=_member(conn, rev, "unit"),
            requirement=_member(conn, rev, "requirement"),
            check=_member(conn, rev, "check"),
            criterion=_member(conn, rev, "criterion"),
            decision=_member(conn, rev, "decision"),
            decision2=_member(conn, rev, "decision"),
            material=_member(conn, rev, "material"),
        )
        scope = made.scope
        _insert(conn, "revision_specs", scope | {"title": "T", "goal": "G"})
        _insert(conn, "phase_specs", _typed_row("phase_specs", made, made.phase))
        _insert(
            conn,
            "batch_specs",
            scope | {"phase_id": made.phase, "batch_key": "B1", "position": 0, "mode": "recommended"},
        )
        for item in (made.item, made.item2):
            _insert(conn, "item_specs", _typed_row("item_specs", made, item))
        _insert(conn, "unit_specs", _typed_row("unit_specs", made, made.unit))
        _insert(conn, "requirement_specs", _typed_row("requirement_specs", made, made.requirement))
        _insert(conn, "check_specs", _typed_row("check_specs", made, made.check))
        _insert(conn, "acceptance_criteria", _typed_row("acceptance_criteria", made, made.criterion))
        for decision in (made.decision, made.decision2):
            _insert(conn, "decision_specs", _typed_row("decision_specs", made, decision))
        _insert(
            conn,
            "material_specs",
            _typed_row(
                "material_specs",
                made,
                made.material,
                kind="file_version",
                role="input",
                mount_name=None,
                path=None,
            ),
        )
        for table, row in (
            (
                "batch_members",
                {"phase_id": made.phase, "batch_key": "B1", "item_id": made.item, "position": 0},
            ),
            (
                "dependency_edges",
                {
                    "dependent_entity_id": made.item,
                    "prerequisite_entity_id": made.item2,
                    "dependency_kind": "item_depends_on",
                },
            ),
            (
                "entity_relations",
                {
                    "source_entity_id": made.item,
                    "target_entity_id": made.item2,
                    "relation": "informs",
                    "position": 0,
                },
            ),
            (
                "entity_requirement_links",
                {"entity_id": made.item, "requirement_id": made.requirement, "relation": "implements"},
            ),
            (
                "decision_supersessions",
                {"decision_id": made.decision, "superseded_decision_id": made.decision2},
            ),
            (
                "decision_bindings",
                {"decision_id": made.decision, "entity_id": made.item, "binding_kind": "applies_to"},
            ),
            ("material_bindings", {"material_id": made.material, "entity_id": made.item}),
            ("entity_check_bindings", {"entity_id": made.unit, "check_id": made.check}),
            ("criterion_check_bindings", {"criterion_id": made.criterion, "check_id": made.check}),
            ("review_requirements", {"owner_entity_id": made.item, "mode": "required"}),
            (
                "entity_path_specs",
                {
                    "entity_id": made.unit,
                    "role": "output",
                    "position": 0,
                    "mount_name": "main",
                    "pattern": "src/*",
                },
            ),
            (
                "artifact_specs",
                {
                    "item_id": made.item,
                    "position": 0,
                    "artifact_key": "report",
                    "role": "output",
                    "mount_name": "main",
                    "path": "out/report.md",
                },
            ),
            (
                "entity_read_specs",
                {
                    "entity_id": made.item,
                    "purpose": "read",
                    "position": 0,
                    "target_kind": "plan_entity",
                    "target_entity_id": made.unit,
                    "required": True,
                    "why": "W",
                },
            ),
            (
                "entity_skill_requirements",
                {"entity_id": made.item, "resource_key": "review-code", "position": 0},
            ),
            ("plan_relations", {"position": 0, "kind": "related", "target_ref": "PLAN1"}),
            (
                "revision_file_bindings",
                {"material_id": made.material, "file_version_id": file_version, "role": "input"},
            ),
            ("revision_payloads", {"document": to_jsonb({}), "document_digest": _DIGEST}),
        ):
            _insert(conn, table, scope | row)
    return made


def _file_version(conn: psycopg.Connection, workspace: UUID) -> UUID:
    blob, file, version = uuid4(), uuid4(), uuid4()
    _insert(
        conn,
        "skm_artifacts.blobs",
        {
            "id": blob,
            "workspace_id": workspace,
            "content_digest": "b" * 64,
            "size_bytes": 1,
            "detected_media_type": "text/plain",
            "created_at": NOW,
        },
    )
    _insert(
        conn,
        "skm_artifacts.files",
        {
            "id": file,
            "workspace_id": workspace,
            "title": "F",
            "origin": "upload",
            "classification": "internal",
            "created_at": NOW,
            "created_by": _PRINCIPAL,
            "updated_at": NOW,
        },
    )
    _insert(
        conn,
        "skm_artifacts.file_versions",
        {
            "id": version,
            "workspace_id": workspace,
            "file_id": file,
            "version_no": 1,
            "blob_id": blob,
            "original_filename": "a.md",
            "source": to_jsonb({}),
            "safety": to_jsonb({}),
            "created_by": _PRINCIPAL,
            "created_at": NOW,
        },
    )
    return version


def _build(conn: psycopg.Connection) -> World:
    ws_a, ws_b = UUID(int=SEED.workspace_id.int), UUID(int=SEED.other_workspace_id.int)
    with conn.transaction():
        for workspace, slug in ((ws_a, "alpha"), (ws_b, "beta")):
            _insert(
                conn,
                "skm_workspace.workspaces",
                {"id": workspace, "slug": slug, "title": "W", "created_at": NOW, "updated_at": NOW},
            )
        _insert(
            conn,
            "skm_access.principals",
            {"id": _PRINCIPAL, "kind": "human", "display_name": "o", "created_at": NOW, "updated_at": NOW},
        )
        project_a = _project(conn, ws_a, "app")
        project_a2 = _project(conn, ws_a, "other")
        project_b = _project(conn, ws_b, "app")
        plan_a = _plan(conn, ws_a, project_a)
        plan_b = _plan(conn, ws_a, project_a)
        plan_c = _plan(conn, ws_b, project_b)
        rev_c = _revision(conn, ws_b, plan_c)
        file_a = _file_version(conn, ws_a)
        file_b = _file_version(conn, ws_b)
        a = _publish(conn, ws_a, plan_a, file_a)
        b = _publish(conn, ws_a, plan_b, file_a)
    return World(conn, ws_a, ws_b, project_a, project_a2, project_b, plan_c, rev_c.id, file_a, file_b, a, b)


@pytest.fixture
def world(clean_test_database: TestDatabase) -> Iterator[World]:  # noqa: F811 - the imported fixture
    with psycopg.connect(clean_test_database.dsn, autocommit=True, connect_timeout=5) as conn:
        yield _build(conn)


def _refused(
    conn: psycopg.Connection,
    error: type[psycopg.Error],
    constraint: str,
    table: str,
    row: Mapping[str, object],
) -> None:
    with pytest.raises(error) as caught, conn.transaction():
        _insert(conn, table, row)
    assert caught.value.diag.constraint_name == constraint


def _outcome(conn: psycopg.Connection, statement: sql.SQL | sql.Composed) -> str:
    """The error class of a statement in its own transaction; ``accepted`` when nothing refused it."""
    try:
        with conn.transaction():
            conn.execute(statement)
    except psycopg.Error as exc:
        return type(exc).__name__
    return "accepted"


def _mutations(tables: tuple[str, ...]) -> dict[str, sql.Composed]:
    """A zero-row statement cannot raise from a row trigger: an empty table would show up as ``accepted``."""
    statements: dict[str, sql.Composed] = {}
    for table in tables:
        name = sql.Identifier("skm_planning", table)
        statements[f"UPDATE {table}"] = sql.SQL("UPDATE {} SET workspace_id = workspace_id").format(name)
        statements[f"DELETE {table}"] = sql.SQL("DELETE FROM {}").format(name)
    return statements


def _contents(conn: psycopg.Connection, tables: tuple[str, ...]) -> dict[str, list[Any]]:
    contents: dict[str, list[Any]] = {}
    for table in tables:
        rows = conn.execute(
            sql.SQL("SELECT row_to_json(t)::text FROM {} t ORDER BY 1").format(
                sql.Identifier("skm_planning", table)
            )
        ).fetchall()
        contents[table] = [row[0] for row in rows]
    return contents


def _as_runtime_role(conn: psycopg.Connection) -> None:
    """Not a skip: without the role the acceptance criteria of the runtime role would pass unproved."""
    if conn.execute("SELECT 1 FROM pg_roles WHERE rolname = 'skm_app'").fetchone() is None:
        pytest.fail("skm_app was not created: run this file as a user that can create roles", pytrace=False)
    conn.execute("SET ROLE skm_app")
    assert conn.execute("SELECT current_user").fetchone() == ("skm_app",)


# ---------------------------------------------------------------------------------------------------------
# the chain and the objects of §11


def test_the_whole_chain_is_applied_with_its_deferred_foreign_keys_validated(world: World) -> None:
    conn = world.conn
    applied = conn.execute("SELECT max(version) FROM skm_core.schema_migrations").fetchone()
    assert applied == (max(migration.version for migration in discover_migrations()),)
    found = conn.execute(
        "SELECT conname, convalidated FROM pg_constraint WHERE conname = ANY(%s) ORDER BY conname",
        (list(_DEFERRED_CROSS_MODULE),),
    ).fetchall()
    assert found == [(name, True) for name in _DEFERRED_CROSS_MODULE]
    unvalidated = conn.execute(
        "SELECT c.conname FROM pg_constraint c JOIN pg_namespace n ON n.oid = c.connamespace "
        "WHERE n.nspname LIKE 'skm\\_%' AND NOT c.convalidated"
    ).fetchall()
    assert unvalidated == []
    assert conn.execute(
        "SELECT condeferrable, condeferred FROM pg_constraint WHERE conname = 'fk_plans__current_revision'"
    ).fetchone() == (True, True)


def test_the_tables_triggers_and_indexes_of_the_section_exist(world: World) -> None:
    conn = world.conn
    tables = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'skm_planning'"
    ).fetchall()
    assert {row[0] for row in tables} >= {*_IMMUTABLE, *_INSERT_ONLY, *_MUTABLE}
    triggers = conn.execute(
        "SELECT c.relname FROM pg_trigger t "
        "JOIN pg_class c ON c.oid = t.tgrelid "
        "JOIN pg_namespace n ON n.oid = c.relnamespace "
        "JOIN pg_proc p ON p.oid = t.tgfoid "
        "WHERE n.nspname = 'skm_planning' AND p.proname = 'tg_immutable' AND t.tgenabled = 'O' ORDER BY 1"
    ).fetchall()
    assert [row[0] for row in triggers] == sorted(
        {
            *_IMMUTABLE,
            "plan_design_brief_rag_bindings",
            "plan_design_brief_research_references",
            "plan_design_briefs",
        }
    )
    indexes = conn.execute("SELECT indexname FROM pg_indexes WHERE schemaname = 'skm_planning'").fetchall()
    assert {row[0] for row in indexes} >= set(_INDEXES)


# ---------------------------------------------------------------------------------------------------------
# typed membership


@pytest.mark.parametrize("table", sorted(_TYPED))
def test_a_typed_row_needs_a_member_of_its_own_kind(world: World, table: str) -> None:
    conn, a, b = world.conn, world.a, world.b
    kind = _TYPED[table][0]
    other = "unit" if kind == "decision" else "decision"
    member = f"fk_{table}__member"
    with conn.transaction():
        _insert(conn, table, _typed_row(table, a, _member(conn, a, kind)))  # the row itself is valid
    free = _member(conn, a, kind)
    _refused(conn, pgerr.ForeignKeyViolation, member, table, _typed_row(table, a, _member(conn, a, other)))
    _refused(
        conn,
        pgerr.CheckViolation,
        f"ck_{table}__entity_kind_valid",
        table,
        _typed_row(table, a, free, entity_kind=other),
    )
    _refused(conn, pgerr.ForeignKeyViolation, member, table, _typed_row(table, a, uuid4()))
    _refused(conn, pgerr.ForeignKeyViolation, member, table, _typed_row(table, a, _member(conn, b, kind)))
    _refused(conn, pgerr.ForeignKeyViolation, member, table, _typed_row(table, a, free, plan_id=b.plan))
    _refused(
        conn, pgerr.ForeignKeyViolation, member, table, _typed_row(table, a, free, workspace_id=world.ws_b)
    )


def test_a_member_of_an_earlier_revision_is_not_a_member_of_the_next(world: World) -> None:
    conn, a = world.conn, world.a
    next_revision = _revision(conn, a.workspace, a.plan, 2, a.id)
    row = _typed_row("phase_specs", a, a.phase) | next_revision.scope
    _refused(conn, pgerr.ForeignKeyViolation, "fk_phase_specs__member", "phase_specs", row)
    with conn.transaction():
        _insert(conn, "revision_members", _member_row(next_revision, a.phase, "phase"))
        _insert(conn, "phase_specs", row)


def test_an_owner_is_a_member_of_the_kind_the_row_names(world: World) -> None:
    conn, a = world.conn, world.a
    for table, kind, owner_kind, fk in (
        ("check_specs", "check", "phase", "fk_check_specs__owner"),  # the owner member is an item
        ("acceptance_criteria", "criterion", "unit", "fk_acceptance_criteria__owner"),
    ):
        _refused(
            conn,
            pgerr.ForeignKeyViolation,
            fk,
            table,
            _typed_row(table, a, _member(conn, a, kind), owner_kind=owner_kind),
        )
    _refused(
        conn,
        pgerr.ForeignKeyViolation,
        "fk_review_requirements__owner",
        "review_requirements",
        a.scope | {"owner_entity_id": a.phase, "mode": "required"},
    )


def test_an_entity_never_changes_kind_between_revisions(world: World) -> None:
    conn, a = world.conn, world.a
    next_revision = _revision(conn, a.workspace, a.plan, 2, a.id)
    _insert(conn, "revision_members", _member_row(next_revision, a.unit, "unit"))  # the kind is kept
    with pytest.raises(pgerr.CheckViolation, match="changes kind"), conn.transaction():
        _insert(conn, "revision_members", _member_row(next_revision, a.item, "decision"))
    with pytest.raises(pgerr.CheckViolation, match="changes kind"), conn.transaction():
        _insert(conn, "revision_members", _member_row(next_revision, uuid4(), "batch"))
    _refused(
        conn,
        pgerr.CheckViolation,
        "ck_plan_entity_identities__entity_kind",
        "plan_entity_identities",
        _identity_row(next_revision, uuid4(), "batch"),
    )


def test_a_member_belongs_to_its_plan_and_its_revision(world: World) -> None:
    conn, a, b = world.conn, world.a, world.b
    # the identity of plan B is not an identity of plan A: the kind trigger fires before the FK
    with pytest.raises(pgerr.CheckViolation, match="changes kind"), conn.transaction():
        _insert(conn, "revision_members", _member_row(a, b.item, "item"))
    forged = Rev(a.workspace, b.plan, a.id)  # the identity of B exists, the revision is not B's
    _refused(
        conn,
        pgerr.ForeignKeyViolation,
        "fk_revision_members__plan_revisions",
        "revision_members",
        _member_row(forged, b.item, "item"),
    )
    _refused(
        conn, pgerr.UniqueViolation, "pk_revision_members", "revision_members", _member_row(a, a.item, "item")
    )
    entity = uuid4()
    _insert(conn, "plan_entity_identities", _identity_row(a, entity, "item"))
    for changes, error, constraint in (
        (
            {"display_key": f"item-{a.item.hex}"},
            pgerr.UniqueViolation,
            "uq_revision_members__revision_id_display_key",
        ),
        ({"display_key": ""}, pgerr.CheckViolation, "ck_revision_members__display_key_valid"),
        ({"position": -1}, pgerr.CheckViolation, "ck_revision_members__position_valid"),
    ):
        _refused(conn, error, constraint, "revision_members", _member_row(a, entity, "item", **changes))


# ---------------------------------------------------------------------------------------------------------
# identities


def test_an_entity_id_is_never_reused_even_across_plans(world: World) -> None:
    conn, a, b = world.conn, world.a, world.b
    write = (  # §11.3: only new identities; the plan's own id is the next revision of the entity
        "INSERT INTO skm_planning.plan_entity_identities "
        "(workspace_id, plan_id, entity_id, entity_kind, first_revision_id, created_at) "
        "VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (plan_id, entity_id) DO NOTHING"
    )
    same_plan = conn.execute(write, (a.workspace, a.plan, a.item, "item", a.id, NOW))
    assert same_plan.rowcount == 0
    for workspace, plan, revision in ((b.workspace, b.plan, b.id), (world.ws_b, world.plan_c, world.rev_c)):
        with pytest.raises(pgerr.UniqueViolation) as caught, conn.transaction():
            conn.execute(write, (workspace, plan, a.item, "item", revision, NOW))
        assert caught.value.diag.constraint_name == "uq_plan_entity_identities__entity_id"
    assert conn.execute(
        "SELECT plan_id, first_revision_id FROM skm_planning.plan_entity_identities WHERE entity_id = %s",
        (a.item,),
    ).fetchall() == [(a.plan, a.id)]
    _refused(
        conn,
        pgerr.ForeignKeyViolation,
        "fk_plan_entity_identities__first_revision",
        "plan_entity_identities",
        _identity_row(a, uuid4(), "item") | {"first_revision_id": b.id},
    )


# ---------------------------------------------------------------------------------------------------------
# revisions: parent, restore, origin


def test_parent_and_restore_source_stay_inside_the_plan(world: World) -> None:
    conn, a, b = world.conn, world.a, world.b
    second = _revision_row(a.workspace, a.plan, 2, a.id)
    _insert(conn, "plan_revisions", second)
    restored = _revision_row(
        a.workspace, a.plan, 3, second["id"], origin="restore", restored_from_revision_id=a.id
    )
    _insert(conn, "plan_revisions", restored)  # a restore names any earlier revision of its own plan
    _refused(
        conn,
        pgerr.ForeignKeyViolation,
        "fk_plan_revisions__parent",
        "plan_revisions",
        _revision_row(a.workspace, a.plan, 4, b.id),
    )
    _refused(
        conn,
        pgerr.ForeignKeyViolation,
        "fk_plan_revisions__restored_from",
        "plan_revisions",
        _revision_row(
            a.workspace, a.plan, 4, restored["id"], origin="restore", restored_from_revision_id=b.id
        ),
    )
    _refused(
        conn,
        pgerr.ForeignKeyViolation,
        "fk_plan_revisions__plans",
        "plan_revisions",
        _revision_row(world.ws_b, a.plan, 4, restored["id"]),  # the plan is not in that workspace
    )
    _refused(
        conn,
        pgerr.UniqueViolation,
        "uq_plan_revisions__plan_id_revision_no",
        "plan_revisions",
        _revision_row(a.workspace, a.plan, 2, a.id),
    )


@pytest.mark.parametrize(
    ("changes", "constraint"),
    [
        ({"revision_no": 1}, "ck_plan_revisions__parent"),  # the first revision has no parent
        ({"parent_revision_id": None}, "ck_plan_revisions__parent"),  # a later one has
        ({"revision_no": 0}, "ck_plan_revisions__revision_no_valid"),
        ({"origin": "manual"}, "ck_plan_revisions__origin"),
        ({"origin": "restore"}, "ck_plan_revisions__restored_from"),  # restore without a source
        ({"restored": True}, "ck_plan_revisions__restored_from"),  # a source without restore
        ({"origin": "restore", "self": True}, "ck_plan_revisions__restored_from"),  # restoring itself
        ({"content_digest": "sha256:ABC"}, "ck_plan_revisions__content_digest_valid"),
        ({"change_reason": ""}, "ck_plan_revisions__change_reason_valid"),
        ({"schema_version": 0}, "ck_plan_revisions__schema_version_valid"),
    ],
    ids=[
        "first-with-parent",
        "later-without-parent",
        "number-zero",
        "origin",
        "restore-without-source",
        "source-without-restore",
        "restore-itself",
        "digest",
        "reason",
        "schema-version",
    ],
)
def test_the_shape_of_a_revision_is_checked(
    world: World, changes: dict[str, object], constraint: str
) -> None:
    conn, a = world.conn, world.a
    given = dict(changes)
    row = _revision_row(a.workspace, a.plan, 2, a.id)
    if given.pop("restored", False):
        row["restored_from_revision_id"] = a.id
    if given.pop("self", False):
        row["restored_from_revision_id"] = row["id"]
    elif given.get("origin") == "restore":
        row["restored_from_revision_id"] = None
    _refused(conn, pgerr.CheckViolation, constraint, "plan_revisions", row | given)


def test_the_first_revision_cannot_be_a_restore_and_every_other_origin_is_accepted(world: World) -> None:
    conn, a = world.conn, world.b
    plan = _plan(conn, a.workspace, world.project_a2)
    _refused(
        conn,
        pgerr.CheckViolation,
        "ck_plan_revisions__restored_from",
        "plan_revisions",
        _revision_row(a.workspace, plan, 1, None, origin="restore", restored_from_revision_id=a.id),
    )
    parent = None
    for number, origin in enumerate(("import", "system", "draft"), start=1):
        row = _revision_row(a.workspace, plan, number, parent, origin=origin)
        _insert(conn, "plan_revisions", row)
        parent = row["id"]


def test_the_current_revision_is_checked_at_commit_and_stays_inside_the_plan(world: World) -> None:
    conn, a, b = world.conn, world.a, world.b
    point = "UPDATE skm_planning.plans SET current_revision_id = %s WHERE id = %s"
    with pytest.raises(pgerr.ForeignKeyViolation) as caught, conn.transaction():
        conn.execute(point, (b.id, a.plan))  # refused only when the transaction ends
    assert caught.value.diag.constraint_name == "fk_plans__current_revision"
    with pytest.raises(pgerr.ForeignKeyViolation) as caught, conn.transaction():
        conn.execute(point, (uuid4(), a.plan))
    assert caught.value.diag.constraint_name == "fk_plans__current_revision"
    conn.execute(point, (a.id, a.plan))
    with conn.transaction():  # the pointer may be written before its revision: that is why it is deferred
        plan = _plan_scope(conn, a.workspace, world.project_a2)
        row = _revision_row(a.workspace, plan)
        _insert(conn, "plans", _plan_row(a.workspace, world.project_a2, plan, current_revision_id=row["id"]))
        _insert(conn, "plan_revisions", row)
    assert conn.execute(
        "SELECT current_revision_id FROM skm_planning.plans WHERE id = %s", (plan,)
    ).fetchone() == (row["id"],)


def test_a_payload_and_a_draft_name_revisions_of_their_plan_and_keep_the_size_limit(world: World) -> None:
    conn, a, b = world.conn, world.a, world.b
    second = _revision(conn, a.workspace, a.plan, 2, a.id)
    _refused(
        conn,
        pgerr.ForeignKeyViolation,
        "fk_revision_payloads__plan_revisions",
        "revision_payloads",
        second.scope | {"plan_id": b.plan, "document": to_jsonb({}), "document_digest": _DIGEST},
    )
    _refused(
        conn,
        pgerr.CheckViolation,
        "ck_revision_payloads__document_digest_valid",
        "revision_payloads",
        second.scope | {"document": to_jsonb({}), "document_digest": "sha256:ABC"},
    )
    envelope = len('{"x": ""}')
    fits = to_jsonb({"x": "y" * (_DOCUMENT_LIMIT - envelope)})
    too_large = to_jsonb({"x": "y" * (_DOCUMENT_LIMIT - envelope + 1)})
    _refused(
        conn,
        pgerr.CheckViolation,
        "ck_revision_payloads__size",
        "revision_payloads",
        second.scope | {"document": too_large, "document_digest": _DIGEST},
    )
    _insert(conn, "revision_payloads", second.scope | {"document": fits, "document_digest": _DIGEST})

    def draft(**changes: object) -> dict[str, object]:
        return {
            "workspace_id": a.workspace,
            "plan_id": a.plan,
            "id": uuid4(),
            "base_revision_id": a.id,
            "document": to_jsonb({}),
            "created_by": _PRINCIPAL,
            "created_at": NOW,
            "updated_by": _PRINCIPAL,
            "updated_at": NOW,
        } | changes

    _insert(conn, "plan_drafts", draft(document=fits))
    _insert(
        conn,
        "plan_drafts",
        draft(state="published", published_revision_id=a.id, closed_at=NOW),
    )
    for changes, error, constraint in (
        ({"base_revision_id": b.id}, pgerr.ForeignKeyViolation, "fk_plan_drafts__base_revision"),
        (
            {"state": "published", "published_revision_id": b.id, "closed_at": NOW},
            pgerr.ForeignKeyViolation,
            "fk_plan_drafts__published_revision",
        ),
        ({"workspace_id": world.ws_b}, pgerr.ForeignKeyViolation, "fk_plan_drafts__plans"),
        ({"state": "merged", "closed_at": NOW}, pgerr.CheckViolation, "ck_plan_drafts__state"),
        ({"state": "published", "closed_at": NOW}, pgerr.CheckViolation, "ck_plan_drafts__published"),
        ({"state": "abandoned"}, pgerr.CheckViolation, "ck_plan_drafts__closed"),
        ({"edit_version": 0}, pgerr.CheckViolation, "ck_plan_drafts__edit_version_valid"),
        ({"document": too_large}, pgerr.CheckViolation, "ck_plan_drafts__size"),
    ):
        _refused(conn, error, constraint, "plan_drafts", draft(**changes))


# ---------------------------------------------------------------------------------------------------------
# aliases and purpose


def test_aliases_keep_their_kinds_and_one_primary_per_plan(world: World) -> None:
    conn, a, b = world.conn, world.a, world.b
    project = world.project_a

    def alias(alias: str, kind: str, plan: UUID = a.plan, project_id: UUID = project) -> dict[str, object]:
        return {
            "workspace_id": a.workspace,
            "project_id": project_id,
            "plan_id": plan,
            "alias": alias,
            "alias_kind": kind,
            "created_at": NOW,
        }

    _insert(conn, "plan_aliases", alias("PLAN1", "short"))
    _insert(conn, "plan_aliases", alias("old-name", "legacy"))  # additional aliases are not primary
    _insert(conn, "plan_aliases", alias("jira:PRJ-1", "external"))
    for row, error, constraint in (
        (alias("PLAN2", "short"), pgerr.UniqueViolation, "uq_plan_aliases__plan_id_short"),
        (alias("review-requests", "system"), pgerr.UniqueViolation, "uq_plan_aliases__plan_id_short"),
        (alias("PLAN1", "short", b.plan), pgerr.UniqueViolation, "pk_plan_aliases"),
        (
            alias("PLAN2", "short", b.plan, world.project_a2),
            pgerr.ForeignKeyViolation,
            "fk_plan_aliases__plans",
        ),
        (alias("plan2", "short", b.plan), pgerr.CheckViolation, "ck_plan_aliases__short"),
        (alias("PLAN0", "short", b.plan), pgerr.CheckViolation, "ck_plan_aliases__short"),
        (alias("AC1", "short", b.plan), pgerr.CheckViolation, "ck_plan_aliases__short"),  # a criterion key
        (alias("other", "system", b.plan), pgerr.CheckViolation, "ck_plan_aliases__system"),
        (alias("x", "nick", b.plan), pgerr.CheckViolation, "ck_plan_aliases__alias_kind"),
        (alias("x" * 201, "legacy", b.plan), pgerr.CheckViolation, "ck_plan_aliases__alias"),
    ):
        _refused(conn, error, constraint, "plan_aliases", row)
    _insert(conn, "plan_aliases", alias("PLAN2", "short", b.plan))
    other = _plan(conn, a.workspace, world.project_a2)
    _insert(conn, "plan_aliases", alias("PLAN1", "short", other, world.project_a2))  # per project


def test_one_review_requests_plan_per_project_and_the_shape_of_a_plan(world: World) -> None:
    conn, a = world.conn, world.a
    project = world.project_a
    _plan(conn, a.workspace, project)  # standard plans are not limited
    _plan(conn, a.workspace, project, purpose="review_requests")
    _plan(conn, a.workspace, world.project_a2, purpose="review_requests")

    def row(**changes: object) -> dict[str, object]:
        return _plan_row(a.workspace, project, _plan_scope(conn, a.workspace, project), **changes)

    for changes, error, constraint in (
        ({"purpose": "review_requests"}, pgerr.UniqueViolation, "uq_plans__project_id_review_requests"),
        ({"purpose": "system"}, pgerr.CheckViolation, "ck_plans__purpose"),
        ({"lifecycle_state": "deleted"}, pgerr.CheckViolation, "ck_plans__lifecycle_state"),
        ({"lifecycle_state": "archived"}, pgerr.CheckViolation, "ck_plans__archived_at"),
        ({"archived_at": NOW}, pgerr.CheckViolation, "ck_plans__archived_at"),
        ({"next_revision_no": 0}, pgerr.CheckViolation, "ck_plans__next_revision_no"),
        ({"title": ""}, pgerr.CheckViolation, "ck_plans__title_valid"),
        ({"project_id": world.project_b}, pgerr.ForeignKeyViolation, "fk_plans__projects"),
    ):
        _refused(conn, error, constraint, "plans", row(**changes))
    with pytest.raises(pgerr.ForeignKeyViolation), conn.transaction():
        _insert(conn, "plans", _plan_row(a.workspace, project, uuid4()))  # a plan is a scope
    # ON DELETE RESTRICT reports 23001 starting with PostgreSQL 18 and 23503 on earlier versions.
    with pytest.raises((pgerr.ForeignKeyViolation, pgerr.RestrictViolation)), conn.transaction():
        conn.execute("DELETE FROM skm_planning.plans WHERE id = %s", (a.plan,))


# ---------------------------------------------------------------------------------------------------------
# links of one revision


def _cross_plan_links(a: Content, b: Content, world: World) -> dict[str, tuple[str, str, dict[str, object]]]:
    """name -> table, the constraint that refuses it, a row of revision A that names an entity of plan B."""
    read = {"purpose": "read", "position": 0, "required": True, "why": "W"}
    return {
        "dependency-dependent": (
            "dependency_edges",
            "fk_dependency_edges__dependent",
            {
                "dependent_entity_id": b.item,
                "prerequisite_entity_id": a.item,
                "dependency_kind": "item_depends_on",
            },
        ),
        "dependency-prerequisite": (
            "dependency_edges",
            "fk_dependency_edges__prerequisite",
            {
                "dependent_entity_id": a.item,
                "prerequisite_entity_id": b.item,
                "dependency_kind": "item_depends_on",
            },
        ),
        "relation-source": (
            "entity_relations",
            "fk_entity_relations__source",
            {"source_entity_id": b.item, "target_entity_id": a.item, "relation": "informs", "position": 1},
        ),
        "relation-target": (
            "entity_relations",
            "fk_entity_relations__target",
            {"source_entity_id": a.item, "target_entity_id": b.item, "relation": "informs", "position": 1},
        ),
        "requirement-link-entity": (
            "entity_requirement_links",
            "fk_entity_requirement_links__entity",
            {"entity_id": b.item, "requirement_id": a.requirement, "relation": "implements"},
        ),
        "requirement-link-requirement": (
            "entity_requirement_links",
            "fk_entity_requirement_links__requirement",
            {"entity_id": a.item, "requirement_id": b.requirement, "relation": "implements"},
        ),
        "decision-binding-decision": (
            "decision_bindings",
            "fk_decision_bindings__decision",
            {"decision_id": b.decision, "entity_id": a.item, "binding_kind": "cited_by"},
        ),
        "decision-binding-entity": (
            "decision_bindings",
            "fk_decision_bindings__entity",
            {"decision_id": a.decision, "entity_id": b.item, "binding_kind": "cited_by"},
        ),
        "supersession-superseded": (
            "decision_supersessions",
            "fk_decision_supersessions__superseded",
            {"decision_id": a.decision, "superseded_decision_id": b.decision},
        ),
        "material-binding-material": (
            "material_bindings",
            "fk_material_bindings__material",
            {"material_id": b.material, "entity_id": a.item},
        ),
        "material-binding-entity": (
            "material_bindings",
            "fk_material_bindings__entity",
            {"material_id": a.material, "entity_id": b.item},
        ),
        "check-binding-entity": (
            "entity_check_bindings",
            "fk_entity_check_bindings__entity",
            {"entity_id": b.unit, "check_id": a.check},
        ),
        "check-binding-check": (
            "entity_check_bindings",
            "fk_entity_check_bindings__check",
            {"entity_id": a.unit, "check_id": b.check},
        ),
        "criterion-binding-criterion": (
            "criterion_check_bindings",
            "fk_criterion_check_bindings__criterion",
            {"criterion_id": b.criterion, "check_id": a.check},
        ),
        "criterion-binding-check": (
            "criterion_check_bindings",
            "fk_criterion_check_bindings__check",
            {"criterion_id": a.criterion, "check_id": b.check},
        ),
        "review-owner": (
            "review_requirements",
            "fk_review_requirements__owner",
            {"owner_entity_id": b.item, "mode": "required"},
        ),
        "path-entity": (
            "entity_path_specs",
            "fk_entity_path_specs__entity",
            {"entity_id": b.unit, "role": "output", "position": 1, "mount_name": "main", "pattern": "src/*"},
        ),
        "artifact-item": (
            "artifact_specs",
            "fk_artifact_specs__item",
            {"item_id": b.item, "position": 1, "role": "input", "mount_name": "main", "path": "in.md"},
        ),
        "read-entity": (
            "entity_read_specs",
            "fk_entity_read_specs__entity",
            read | {"entity_id": b.item, "target_kind": "plan_entity", "target_entity_id": a.unit},
        ),
        "read-target": (
            "entity_read_specs",
            "fk_entity_read_specs__target",
            read | {"entity_id": a.item2, "target_kind": "plan_entity", "target_entity_id": b.unit},
        ),
        "read-material": (
            "entity_read_specs",
            "fk_entity_read_specs__material",
            read | {"entity_id": a.item2, "target_kind": "material", "material_id": b.material},
        ),
        "skill-entity": (
            "entity_skill_requirements",
            "fk_entity_skill_requirements__entity",
            {"entity_id": b.item, "resource_key": "review-code", "position": 1},
        ),
        "batch-phase": (
            "batch_specs",
            "fk_batch_specs__phase",
            {"phase_id": b.phase, "batch_key": "B2", "position": 1, "mode": "required"},
        ),
        "batch-member-batch": (
            "batch_members",
            "fk_batch_members__batch",
            {"phase_id": b.phase, "batch_key": "B1", "item_id": a.item2, "position": 1},
        ),
        "batch-member-item": (
            "batch_members",
            "fk_batch_members__item",
            {"phase_id": a.phase, "batch_key": "B1", "item_id": b.item, "position": 1},
        ),
        "plan-relation-plan": (
            "plan_relations",
            "fk_plan_relations__revision",
            {"plan_id": b.plan, "position": 1, "kind": "related", "target_ref": "PLAN2"},
        ),
        "plan-relation-other-workspace": (
            "plan_relations",
            "fk_plan_relations__target",
            {"position": 1, "kind": "related", "target_ref": "PLAN2", "target_plan_id": world.plan_c},
        ),
        "pin-material": (
            "revision_file_bindings",
            "fk_revision_file_bindings__material",
            {"material_id": b.material, "file_version_id": world.file_a, "role": "input"},
        ),
    }


_CROSS_PLAN = [
    "dependency-dependent",
    "dependency-prerequisite",
    "relation-source",
    "relation-target",
    "requirement-link-entity",
    "requirement-link-requirement",
    "decision-binding-decision",
    "decision-binding-entity",
    "supersession-superseded",
    "material-binding-material",
    "material-binding-entity",
    "check-binding-entity",
    "check-binding-check",
    "criterion-binding-criterion",
    "criterion-binding-check",
    "review-owner",
    "path-entity",
    "artifact-item",
    "read-entity",
    "read-target",
    "read-material",
    "skill-entity",
    "batch-phase",
    "batch-member-batch",
    "batch-member-item",
    "plan-relation-plan",
    "plan-relation-other-workspace",
    "pin-material",
]


@pytest.mark.parametrize("case", _CROSS_PLAN)
def test_a_link_never_leaves_its_revision(world: World, case: str) -> None:
    a = world.a
    cases = _cross_plan_links(a, world.b, world)
    assert sorted(cases) == sorted(_CROSS_PLAN)
    table, constraint, row = cases[case]
    _refused(world.conn, pgerr.ForeignKeyViolation, constraint, table, a.scope | row)


_ROW_SCOPE_TABLES = (
    "batch_specs",
    "batch_members",
    "decision_supersessions",
    "criterion_check_bindings",
    "artifact_specs",
)


def _row_with_valid_endpoints(conn: psycopg.Connection, a: Content, table: str) -> dict[str, object]:
    """Unused row keys and endpoints in A: only the tested row's workspace/plan may be forged."""
    decision, check = a.decision, a.check
    if table == "decision_supersessions":
        decision = _member(conn, a, "decision")
        _insert(conn, "decision_specs", _typed_row("decision_specs", a, decision))
    if table == "criterion_check_bindings":
        check = _member(conn, a, "check")
        _insert(conn, "check_specs", _typed_row("check_specs", a, check))
    rows: dict[str, dict[str, object]] = {
        "batch_specs": {"phase_id": a.phase, "batch_key": "B2", "position": 1, "mode": "required"},
        "batch_members": {"phase_id": a.phase, "batch_key": "B1", "item_id": a.item2, "position": 1},
        "decision_supersessions": {"decision_id": decision, "superseded_decision_id": a.decision2},
        "criterion_check_bindings": {"criterion_id": a.criterion, "check_id": check},
        "artifact_specs": {
            "item_id": a.item,
            "position": 1,
            "artifact_key": "scope-proof",
            "role": "output",
            "mount_name": "main",
            "path": "out/scope-proof.md",
        },
    }
    return a.scope | rows[table]


@pytest.mark.parametrize("table", _ROW_SCOPE_TABLES)
@pytest.mark.parametrize("runtime_role", [False, True], ids=["owner", "skm_app"])
@pytest.mark.parametrize("row_scope", ["valid", "other-workspace", "other-plan", "nonexistent-scope"])
def test_link_row_scope_matches_its_revision(
    world: World, table: str, runtime_role: bool, row_scope: str
) -> None:
    """F1: valid revision and endpoint FKs alone do not prove the row's own workspace/plan scope."""
    conn, a = world.conn, world.a
    row = _row_with_valid_endpoints(conn, a, table)
    scopes = {
        "valid": a.scope,
        "other-workspace": Rev(world.ws_b, world.plan_c, a.id).scope,
        "other-plan": Rev(a.workspace, world.b.plan, a.id).scope,
        "nonexistent-scope": Rev(uuid4(), uuid4(), a.id).scope,
    }
    if runtime_role:
        _as_runtime_role(conn)
    if row_scope == "valid":
        with conn.transaction():
            _insert(conn, table, row)
        return

    # Leave the revision and every endpoint untouched. Independent cases expose each missing guard,
    # without a duplicate key or a cross-revision endpoint masking an accepted forged row.
    with pytest.raises(pgerr.ForeignKeyViolation) as caught, conn.transaction():
        _insert(conn, table, row | scopes[row_scope])
    assert caught.value.sqlstate == "23503"
    assert caught.value.diag.schema_name == "skm_planning"
    assert caught.value.diag.table_name == table


def test_units_and_items_nest_inside_their_revision_and_item(world: World) -> None:
    conn, a, b = world.conn, world.a, world.b
    other_item_unit = _member(conn, a, "unit")
    _insert(conn, "unit_specs", _typed_row("unit_specs", a, other_item_unit, item_id=a.item2))
    _insert(conn, "unit_specs", _typed_row("unit_specs", a, _member(conn, a, "unit"), parent_unit_id=a.unit))
    for changes, constraint in (
        ({"item_id": b.item}, "fk_unit_specs__item"),
        ({"parent_unit_id": b.unit}, "fk_unit_specs__parent"),
        (
            {"parent_unit_id": other_item_unit},
            "fk_unit_specs__parent",
        ),  # the parent is a unit of the same item
    ):
        row = _typed_row("unit_specs", a, _member(conn, a, "unit"), **changes)
        _refused(conn, pgerr.ForeignKeyViolation, constraint, "unit_specs", row)
    row = _typed_row("item_specs", a, _member(conn, a, "item"), phase_id=b.phase)
    _refused(conn, pgerr.ForeignKeyViolation, "fk_item_specs__phase", "item_specs", row)


def test_a_material_file_pin_is_required_at_commit_and_stays_in_the_workspace(world: World) -> None:
    conn, a = world.conn, world.a

    def material() -> UUID:
        entity = _member(conn, a, "material")
        _insert(conn, "material_specs", _typed_row("material_specs", a, entity))  # repository_path: no pin
        return entity

    unpinned = _member(conn, a, "material")
    with pytest.raises(pgerr.ForeignKeyViolation, match="has no file version pin"), conn.transaction():
        _insert(
            conn,
            "material_specs",
            _typed_row("material_specs", a, unpinned, kind="file_version", mount_name=None, path=None),
        )
    _refused(
        conn,
        pgerr.ForeignKeyViolation,
        "fk_revision_file_bindings__file_version",
        "revision_file_bindings",
        a.scope | {"material_id": material(), "file_version_id": world.file_b, "role": "input"},
    )
    _refused(
        conn,
        pgerr.CheckViolation,
        "ck_revision_file_bindings__role_valid",
        "revision_file_bindings",
        a.scope | {"material_id": material(), "file_version_id": world.file_a, "role": "output"},
    )


def test_execution_rows_name_a_revision_of_the_plan_across_modules(world: World) -> None:
    conn, a, b = world.conn, world.a, world.b

    def report(plan: UUID) -> dict[str, object]:
        return {
            "id": uuid4(),
            "workspace_id": a.workspace,
            "project_id": world.project_a,
            "plan_id": plan,
            "revision_id": a.id,
            "revision_digest": _DIGEST,
            "status": "ready",
            "inputs": to_jsonb({}),
            "inputs_digest": _DIGEST,
            "policy_digest": _DIGEST,
            "results": to_jsonb([]),
            "structural_counts": to_jsonb({}),
            "estimate": to_jsonb({}),
            "validator_version": 1,
            "created_by": _PRINCIPAL,
            "created_at": NOW,
        }

    _insert(conn, "skm_execution.readiness_reports", report(a.plan))
    _refused(
        conn,
        pgerr.ForeignKeyViolation,
        "fk_readiness_reports__plan_revisions",
        "skm_execution.readiness_reports",
        report(b.plan),
    )


# ---------------------------------------------------------------------------------------------------------
# shapes of typed and link rows


def _shapes(a: Content) -> dict[str, tuple[str, str, dict[str, object]]]:
    """name -> table, the CHECK or UNIQUE that refuses it, the row; a typed row gets a free member first."""
    read = {"purpose": "read", "position": 1, "required": True, "why": "W"}
    path = {"entity_id": a.unit, "position": 1, "mount_name": "main"}
    return {
        "item-routine-with-gate": ("item_specs", "ck_item_specs__gate", {"authority_gate": "G1"}),
        "item-gate-without-scope": ("item_specs", "ck_item_specs__gate", {"authority_kind": "owner_gate"}),
        "item-gate-and-label": (
            "item_specs",
            "ck_item_specs__gate",
            {
                "authority_kind": "owner_gate",
                "authority_scope": "x",
                "authority_gate": "G1",
                "authority_label": "l",
            },
        ),
        "unit-command-without-definition": ("unit_specs", "ck_unit_specs__command", {"unit_kind": "command"}),
        "unit-definition-without-command": (
            "unit_specs",
            "ck_unit_specs__command",
            {"command": to_jsonb({"kind": "command"})},
        ),
        "unit-local-key": ("unit_specs", "ck_unit_specs__local_key_valid", {"local_key": "X1"}),
        "check-owner-kind": ("check_specs", "ck_check_specs__owner_kind_valid", {"owner_kind": "unit"}),
        "criterion-owner-kind": (
            "acceptance_criteria",
            "ck_acceptance_criteria__owner_kind_valid",
            {"owner_kind": "phase"},
        ),
        "decision-open-without-question": ("decision_specs", "ck_decision_specs__fields", {"state": "open"}),
        "decision-accepted-without-rationale": (
            "decision_specs",
            "ck_decision_specs__fields",
            {"state": "accepted", "decision": "d"},
        ),
        "material-target": ("material_specs", "ck_material_specs__target", {"path": None}),
        "material-required-for": (
            "material_specs",
            "ck_material_specs__required_for",
            {"required_for": ["deploy"]},
        ),
        "material-max-age": (
            "material_specs",
            "ck_material_specs__max_age",
            {
                "kind": "external_source",
                "mount_name": None,
                "path": None,
                "external_url": "https://x",
                "freshness_policy": "must_refresh",
            },
        ),
        "material-freshness-kind": (
            "material_specs",
            "ck_material_specs__freshness_kind",
            {"freshness_policy": "must_refresh", "freshness_max_age_s": 60},
        ),
        "review-self-without-reason": (
            "review_requirements",
            "ck_review_requirements__mode",
            a.scope | {"owner_entity_id": a.item2, "mode": "self"},
        ),
        "review-waived-without-actor": (
            "review_requirements",
            "ck_review_requirements__mode",
            a.scope | {"owner_entity_id": a.item2, "mode": "waived", "reason": "r"},
        ),
        "review-owner-kind": (
            "review_requirements",
            "ck_review_requirements__owner_kind_valid",
            a.scope | {"owner_entity_id": a.phase, "owner_kind": "phase", "mode": "required"},
        ),
        "read-two-targets": (
            "entity_read_specs",
            "ck_entity_read_specs__target",
            a.scope
            | read
            | {
                "entity_id": a.item,
                "target_kind": "plan_entity",
                "target_entity_id": a.unit,
                "material_id": a.material,
            },
        ),
        "read-purpose": (
            "entity_read_specs",
            "ck_entity_read_specs__purpose_valid",
            a.scope
            | read
            | {
                "entity_id": a.item,
                "purpose": "any",
                "target_kind": "plan_entity",
                "target_entity_id": a.unit,
            },
        ),
        "path-hint-without-change": (
            "entity_path_specs",
            "ck_entity_path_specs__change",
            a.scope | path | {"role": "change_hint", "pattern": "src/*"},
        ),
        "path-traversal": (
            "entity_path_specs",
            "ck_entity_path_specs__pattern_valid",
            a.scope | path | {"role": "output", "pattern": "src/../etc"},
        ),
        "dependency-self": (
            "dependency_edges",
            "ck_dependency_edges__no_self",
            a.scope
            | {
                "dependent_entity_id": a.item,
                "prerequisite_entity_id": a.item,
                "dependency_kind": "item_depends_on",
            },
        ),
        "dependency-implicit-item": (
            "dependency_edges",
            "ck_dependency_edges__implicit",
            a.scope
            | {
                "dependent_entity_id": a.item2,
                "prerequisite_entity_id": a.item,
                "dependency_kind": "item_depends_on",
                "implicit": True,
            },
        ),
        "relation-self": (
            "entity_relations",
            "ck_entity_relations__no_self",
            a.scope
            | {"source_entity_id": a.item, "target_entity_id": a.item, "relation": "informs", "position": 1},
        ),
        "supersession-self": (
            "decision_supersessions",
            "ck_decision_supersessions__no_self",
            a.scope | {"decision_id": a.decision, "superseded_decision_id": a.decision},
        ),
        "plan-relation-self": (
            "plan_relations",
            "ck_plan_relations__no_self",
            a.scope | {"position": 1, "kind": "related", "target_ref": "PLAN1", "target_plan_id": a.plan},
        ),
        "artifact-output-key-twice": (
            "artifact_specs",
            "uq_artifact_specs__output_key",
            a.scope
            | {
                "item_id": a.item2,
                "position": 1,
                "artifact_key": "report",
                "role": "output",
                "mount_name": "main",
                "path": "out/other.md",
            },
        ),
    }


_SHAPES = [
    "item-routine-with-gate",
    "item-gate-without-scope",
    "item-gate-and-label",
    "unit-command-without-definition",
    "unit-definition-without-command",
    "unit-local-key",
    "check-owner-kind",
    "criterion-owner-kind",
    "decision-open-without-question",
    "decision-accepted-without-rationale",
    "material-target",
    "material-required-for",
    "material-max-age",
    "material-freshness-kind",
    "review-self-without-reason",
    "review-waived-without-actor",
    "review-owner-kind",
    "read-two-targets",
    "read-purpose",
    "path-hint-without-change",
    "path-traversal",
    "dependency-self",
    "dependency-implicit-item",
    "relation-self",
    "supersession-self",
    "plan-relation-self",
    "artifact-output-key-twice",
]


@pytest.mark.parametrize("case", _SHAPES)
def test_the_shape_of_a_row_is_checked(world: World, case: str) -> None:
    conn, a = world.conn, world.a
    cases = _shapes(a)
    assert sorted(cases) == sorted(_SHAPES)
    table, constraint, row = cases[case]
    if table in _TYPED:
        row = _typed_row(table, a, _member(conn, a, _TYPED[table][0]), **row)
    error = pgerr.UniqueViolation if constraint.startswith("uq_") else pgerr.CheckViolation
    _refused(conn, error, constraint, table, row)


def test_a_unit_cannot_be_its_own_parent(world: World) -> None:
    conn, a = world.conn, world.a
    entity = _member(conn, a, "unit")
    row = _typed_row("unit_specs", a, entity, parent_unit_id=entity)
    _refused(conn, pgerr.CheckViolation, "ck_unit_specs__no_self_parent", "unit_specs", row)


def test_an_item_is_in_at_most_one_batch(world: World) -> None:
    conn, a = world.conn, world.a
    _insert(
        conn,
        "batch_specs",
        a.scope | {"phase_id": a.phase, "batch_key": "B2", "position": 1, "mode": "required"},
    )
    _refused(
        conn,
        pgerr.UniqueViolation,
        "uq_batch_members__item",
        "batch_members",
        a.scope | {"phase_id": a.phase, "batch_key": "B2", "item_id": a.item, "position": 0},
    )


# ---------------------------------------------------------------------------------------------------------
# published rows are immutable


def test_published_rows_refuse_update_and_delete_even_for_the_owner(world: World) -> None:
    conn = world.conn
    before = _contents(conn, _IMMUTABLE)
    assert all(before.values())
    statements = _mutations(_IMMUTABLE)
    outcomes = {name: _outcome(conn, statement) for name, statement in statements.items()}
    assert outcomes == dict.fromkeys(statements, "RestrictViolation")
    assert _contents(conn, _IMMUTABLE) == before


def test_a_revision_cannot_be_rewritten_or_moved(world: World) -> None:
    conn, a, b = world.conn, world.a, world.b
    for statement, params in (
        ("UPDATE skm_planning.plan_revisions SET change_reason = 'rewritten' WHERE id = %s", (a.id,)),
        ("UPDATE skm_planning.plan_revisions SET plan_id = %s WHERE id = %s", (b.plan, a.id)),
        ("UPDATE skm_planning.revision_payloads SET document = '{}' WHERE revision_id = %s", (a.id,)),
        ("UPDATE skm_planning.revision_members SET entity_kind = 'unit' WHERE entity_id = %s", (a.item,)),
        (
            "UPDATE skm_planning.plan_entity_identities SET entity_kind = 'unit' WHERE entity_id = %s",
            (a.item,),
        ),
        ("DELETE FROM skm_planning.plan_revisions WHERE id = %s", (a.id,)),
    ):
        with pytest.raises(pgerr.RestrictViolation, match="rows are immutable"), conn.transaction():
            conn.execute(statement, params)  # pyright: ignore[reportArgumentType]


# ---------------------------------------------------------------------------------------------------------
# work_policy (0029): the database is a backstop, the application schema owns the closed shape


def _policy(size: int, char: str = "x") -> dict[str, str]:
    """An object whose ``jsonb::text`` takes ``size`` bytes; ``char`` is one or two bytes of UTF-8."""
    return {"k": char * ((size - _POLICY_ENVELOPE) // len(char.encode()))}


_POLICIES = {"item_specs": "item", "unit_specs": "unit"}


@pytest.mark.parametrize("table", sorted(_POLICIES))
def test_work_policy_is_a_nullable_object_of_at_most_four_kibibytes(world: World, table: str) -> None:
    conn, a = world.conn, world.a
    kind = _POLICIES[table]
    id_column = sql.Identifier(_TYPED[table][1])
    check = f"ck_{table}__work_policy"

    def row(**changes: object) -> dict[str, object]:
        return _typed_row(table, a, _member(conn, a, kind), **changes)

    def stored(values: dict[str, object]) -> tuple[Any, ...] | None:
        query = sql.SQL("SELECT work_policy IS NULL, work_policy FROM {} WHERE {} = %s").format(
            sql.Identifier("skm_planning", table), id_column
        )
        return conn.execute(query, (values[_TYPED[table][1]],)).fetchone()

    absent = row()  # a writer that does not know the column
    _insert(conn, table, absent)
    assert stored(absent) == (True, None)
    explicit = row(work_policy=None)
    _insert(conn, table, explicit)
    assert stored(explicit) == (True, None)
    # the boundary in bytes of the stored text, and any object: enums and fields are not the database's
    for policy in ({}, {"unknown_field": 1}, _policy(_POLICY_LIMIT)):
        accepted = row(work_policy=to_jsonb(policy))
        _insert(conn, table, accepted)
        assert stored(accepted) == (False, policy)
    length = conn.execute(
        "SELECT octet_length(%s::jsonb::text)", (to_jsonb(_policy(_POLICY_LIMIT)),)
    ).fetchone()
    assert length == (_POLICY_LIMIT,)
    two_bytes = _policy(_POLICY_LIMIT + 1, "я")  # the limit is bytes: this is half as many characters
    assert conn.execute("SELECT octet_length(%s::jsonb::text)", (to_jsonb(two_bytes),)).fetchone() == (
        _POLICY_LIMIT + 1,
    )
    for refused in (_policy(_POLICY_LIMIT + 1), two_bytes, [], "fast", 1, True, None):  # None: the JSON null
        _refused(conn, pgerr.CheckViolation, check, table, row(work_policy=to_jsonb(refused)))
    update = sql.SQL("UPDATE {} SET work_policy = '{{}}' WHERE {} = %s").format(
        sql.Identifier("skm_planning", table), id_column
    )
    with pytest.raises(pgerr.RestrictViolation), conn.transaction():
        conn.execute(update, (absent[_TYPED[table][1]],))  # no backfill of a published row
    assert stored(absent) == (True, None)


def test_published_revision_preserves_its_digest_and_omitted_work_policy(world: World) -> None:
    conn = world.conn
    published = world.a
    digest = conn.execute(
        "SELECT content_digest FROM skm_planning.plan_revisions WHERE id = %s", (published.id,)
    ).fetchone()
    assert digest is not None
    for table, id_col, entity in (
        ("item_specs", "item_id", published.item),
        ("unit_specs", "unit_id", published.unit),
    ):
        relation = sql.Identifier("skm_planning", table)
        column = sql.Identifier(id_col)
        read = sql.SQL("SELECT work_policy FROM {} WHERE {} = %s").format(relation, column)
        assert conn.execute(read, (entity,)).fetchone() == (None,)
        update = sql.SQL("UPDATE {} SET work_policy = '{{}}' WHERE {} = %s").format(relation, column)
        with pytest.raises(pgerr.RestrictViolation), conn.transaction():
            conn.execute(update, (entity,))
    assert (
        conn.execute(
            "SELECT content_digest FROM skm_planning.plan_revisions WHERE id = %s", (published.id,)
        ).fetchone()
        == digest
    )


# ---------------------------------------------------------------------------------------------------------
# the runtime role


def test_the_runtime_role_only_appends_to_immutable_tables(world: World) -> None:
    conn = world.conn
    _as_runtime_role(conn)
    before = _contents(conn, _IMMUTABLE)
    statements = _mutations(_IMMUTABLE)
    outcomes = {name: _outcome(conn, statement) for name, statement in statements.items()}
    assert outcomes == dict.fromkeys(statements, "InsufficientPrivilege")
    aliases = _mutations(_INSERT_ONLY)
    assert {name: _outcome(conn, statement) for name, statement in aliases.items()} == dict.fromkeys(
        aliases, "InsufficientPrivilege"
    )
    assert _contents(conn, _IMMUTABLE) == before


def test_the_runtime_role_privileges_on_every_planning_table(world: World) -> None:
    conn = world.conn
    _as_runtime_role(conn)

    def privileges(table: str) -> set[str]:
        return {
            privilege
            for privilege in ("SELECT", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "REFERENCES", "TRIGGER")
            if conn.execute(
                "SELECT has_table_privilege('skm_app', %s, %s)", (f"skm_planning.{table}", privilege)
            ).fetchone()
            == (True,)
        }

    for table in (*_IMMUTABLE, *_INSERT_ONLY):
        assert privileges(table) == {"SELECT", "INSERT"}, table
    for table in _MUTABLE:  # DELETE of drafts and plans is the application's rule (§11.4), not the database's
        assert (
            {"SELECT", "INSERT", "UPDATE"} <= privileges(table) <= {"SELECT", "INSERT", "UPDATE", "DELETE"}
        ), table
    schemas = conn.execute(
        "SELECT nspname FROM pg_namespace WHERE nspname LIKE 'skm\\_%' ORDER BY 1"
    ).fetchall()
    assert schemas
    for (schema,) in schemas:
        assert conn.execute("SELECT has_schema_privilege('skm_app', %s, 'CREATE')", (schema,)).fetchone() == (
            False,
        ), schema


def test_the_runtime_role_publishes_a_revision_and_moves_the_plan(world: World) -> None:
    conn, a, b = world.conn, world.a, world.b
    _as_runtime_role(conn)
    with conn.transaction():
        next_revision = _revision(conn, a.workspace, a.plan, 2, a.id)
        kept = _member_row(next_revision, a.phase, "phase")
        _insert(conn, "revision_members", kept)  # the kind trigger reads identities as the role
        new_item = _member(conn, next_revision, "item")
        _insert(conn, "phase_specs", _typed_row("phase_specs", a, a.phase) | next_revision.scope)
        _insert(
            conn,
            "item_specs",
            _typed_row("item_specs", a, new_item, work_policy=to_jsonb({})) | next_revision.scope,
        )
        _insert(
            conn,
            "plan_aliases",
            {
                "workspace_id": a.workspace,
                "project_id": world.project_a,
                "plan_id": a.plan,
                "alias": "PLAN1",
                "alias_kind": "short",
                "created_at": NOW,
            },
        )
        conn.execute(
            "UPDATE skm_planning.plans SET current_revision_id = %s, next_revision_no = 3, row_version = 2 "
            "WHERE id = %s",
            (next_revision.id, a.plan),
        )
        _insert(
            conn,
            "project_plan_counters",
            {"workspace_id": a.workspace, "project_id": world.project_a, "next_plan_no": 2},
        )
        conn.execute("UPDATE skm_planning.project_plan_counters SET next_plan_no = 3")
    _refused(
        conn,
        pgerr.ForeignKeyViolation,
        "fk_phase_specs__member",
        "phase_specs",
        _typed_row("phase_specs", a, b.phase),
    )
    with pytest.raises(pgerr.ForeignKeyViolation) as caught, conn.transaction():
        conn.execute("UPDATE skm_planning.plans SET current_revision_id = %s WHERE id = %s", (b.id, a.plan))
    assert caught.value.diag.constraint_name == "fk_plans__current_revision"


def test_the_runtime_role_executes_no_ddl(world: World) -> None:
    conn = world.conn
    _as_runtime_role(conn)
    statements = (
        "CREATE SCHEMA skm_rogue",
        "CREATE TABLE skm_planning.rogue (id integer)",
        "CREATE TABLE skm_core.rogue (id integer)",
        "CREATE INDEX ix_rogue ON skm_planning.plans (title)",
        "ALTER TABLE skm_planning.plan_revisions ADD COLUMN rogue integer",
        "ALTER TABLE skm_planning.unit_specs DROP CONSTRAINT fk_unit_specs__member",
        "ALTER TABLE skm_planning.unit_specs DROP CONSTRAINT ck_unit_specs__work_policy",
        "ALTER TABLE skm_planning.plan_revisions DISABLE TRIGGER ALL",
        "ALTER TABLE skm_planning.plan_revisions OWNER TO skm_app",
        "DROP TRIGGER tg_plan_revisions__immutable ON skm_planning.plan_revisions",
        "CREATE TRIGGER rogue BEFORE INSERT ON skm_planning.plans "
        "FOR EACH ROW EXECUTE FUNCTION skm_planning.tg_immutable()",
        "CREATE OR REPLACE FUNCTION skm_planning.tg_immutable() RETURNS trigger "
        "LANGUAGE plpgsql AS 'BEGIN RETURN NEW; END'",
        "DROP TABLE skm_planning.plan_drafts",
        "TRUNCATE skm_planning.plan_revisions CASCADE",
        "TRUNCATE skm_planning.plans CASCADE",
        "SET session_replication_role = replica",
    )
    outcomes = {statement: _outcome(conn, sql.SQL(statement)) for statement in statements}
    assert outcomes == dict.fromkeys(statements, "InsufficientPrivilege")


def test_the_grant_helper_gives_the_runtime_role_nothing(world: World) -> None:
    # skm_core.grant_app runs with the caller's rights: PostgreSQL only warns that no privileges were granted
    conn = world.conn
    _as_runtime_role(conn)
    with conn.transaction(
        force_rollback=True
    ):  # its default privileges of the role itself stay out of the session
        conn.execute("SELECT skm_core.grant_app('skm_planning', '{}'::text[])")
        for table in (*_IMMUTABLE, *_INSERT_ONLY):
            for privilege in ("UPDATE", "DELETE", "TRUNCATE"):
                assert conn.execute(
                    "SELECT has_table_privilege('skm_app', %s, %s)", (f"skm_planning.{table}", privilege)
                ).fetchone() == (False,), (table, privilege)
