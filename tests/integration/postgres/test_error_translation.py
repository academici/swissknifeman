"""SQLSTATE translation (adapters §1.7) plus the jsonb and keyset helpers that share the adapter boundary."""

import base64
import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta, timezone
from uuid import uuid4

import psycopg
import psycopg.errors
import psycopg_pool
import pytest

from skm.adapters.postgres.errors import translate_pg_error
from skm.adapters.postgres.jsonb import canonical_dumps, require_aware, to_jsonb
from skm.adapters.postgres.pagination import (
    MAX_LIMIT,
    Cursor,
    decode_cursor,
    encode_cursor,
    keyset_clause,
    page_of,
    query_digest,
    validate_limit,
)
from skm.kernel.errors import (
    BackendUnavailable,
    Conflict,
    InternalError,
    PreconditionFailed,
    SkmError,
    ValidationFailed,
)
from skm.kernel.generated.error_codes import ErrorCode

# (sqlstate, error class, code, retryable, details without the diagnostics-derived keys)
_MATRIX = [
    ("23505", Conflict, ErrorCode.ALREADY_EXISTS, False, {}),
    ("23503", ValidationFailed, ErrorCode.INVALID_REFERENCE, False, {}),
    ("23514", ValidationFailed, ErrorCode.SCHEMA_INVALID, False, {}),
    ("23P01", Conflict, ErrorCode.ALREADY_EXISTS, False, {}),
    ("23502", InternalError, ErrorCode.INTERNAL_ERROR, False, {}),
    ("22P02", ValidationFailed, ErrorCode.SCHEMA_INVALID, False, {}),
    ("22007", ValidationFailed, ErrorCode.SCHEMA_INVALID, False, {}),
    ("22008", ValidationFailed, ErrorCode.SCHEMA_INVALID, False, {}),
    ("22003", ValidationFailed, ErrorCode.SCHEMA_INVALID, False, {}),
    ("40001", Conflict, ErrorCode.SERIALIZATION_FAILURE, True, {}),
    ("40P01", Conflict, ErrorCode.SERIALIZATION_FAILURE, True, {}),
    ("55P03", Conflict, ErrorCode.SERIALIZATION_FAILURE, True, {"reason": "lock_timeout"}),
    ("57014", BackendUnavailable, ErrorCode.BACKEND_UNAVAILABLE, True, {"reason": "statement_timeout"}),
    ("57P01", BackendUnavailable, ErrorCode.BACKEND_UNAVAILABLE, True, {}),
    ("57P02", BackendUnavailable, ErrorCode.BACKEND_UNAVAILABLE, True, {}),
    ("57P03", BackendUnavailable, ErrorCode.BACKEND_UNAVAILABLE, True, {}),
    ("08006", BackendUnavailable, ErrorCode.BACKEND_UNAVAILABLE, True, {}),  # class 08
    ("08001", BackendUnavailable, ErrorCode.BACKEND_UNAVAILABLE, True, {}),
    ("53200", BackendUnavailable, ErrorCode.BACKEND_UNAVAILABLE, True, {}),  # class 53
    ("53300", BackendUnavailable, ErrorCode.BACKEND_UNAVAILABLE, True, {}),
    ("42P01", PreconditionFailed, ErrorCode.SCHEMA_NOT_MIGRATED, False, {"hint": "skm db migrate"}),
    ("42703", PreconditionFailed, ErrorCode.SCHEMA_NOT_MIGRATED, False, {"hint": "skm db migrate"}),
    ("3F000", PreconditionFailed, ErrorCode.SCHEMA_NOT_MIGRATED, False, {"hint": "skm db migrate"}),
    ("42501", InternalError, ErrorCode.INTERNAL_ERROR, False, {"reason": "db_privilege"}),
    ("P0001", InternalError, ErrorCode.INTERNAL_ERROR, False, {}),
    ("XX000", InternalError, ErrorCode.INTERNAL_ERROR, False, {"sqlstate": "XX000"}),  # default row
    (
        "23000",
        InternalError,
        ErrorCode.INTERNAL_ERROR,
        False,
        {"sqlstate": "23000"},
    ),  # other class 23 is not mapped
    ("40002", InternalError, ErrorCode.INTERNAL_ERROR, False, {"sqlstate": "40002"}),
]


def _exception(sqlstate: str) -> psycopg.Error:
    return psycopg.errors.lookup(sqlstate)("driver text with secret-host.internal")


@pytest.mark.parametrize(("sqlstate", "cls", "code", "retryable", "details"), _MATRIX)
def test_sqlstate_table(
    sqlstate: str, cls: type[SkmError], code: ErrorCode, retryable: bool, details: dict[str, str]
) -> None:
    cause = _exception(sqlstate)
    error = translate_pg_error(cause)
    assert type(error) is cls
    assert error.code is code
    assert error.retryable is retryable
    assert dict(error.details) == details
    assert error.__cause__ is cause
    assert "secret-host" not in str(error)
    assert "secret-host" not in json.dumps(error.to_problem())


def test_non_sqlstate_errors() -> None:
    operational = translate_pg_error(psycopg.OperationalError("connection refused"))
    assert type(operational) is BackendUnavailable
    assert operational.retryable is True
    assert dict(operational.details) == {}
    timeout = translate_pg_error(psycopg_pool.PoolTimeout("couldn't get a connection"))
    assert type(timeout) is BackendUnavailable
    assert timeout.retryable is True
    assert dict(timeout.details) == {"reason": "pool_timeout"}
    other = translate_pg_error(psycopg.ProgrammingError("bad"))
    assert type(other) is InternalError
    assert other.retryable is False


# --- live PostgreSQL -----------------------------------------------------------------------------------


@pytest.fixture
def autocommit(pg_dsn: str) -> Iterator[psycopg.Connection]:
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as conn:
        yield conn


def _failure(conn: psycopg.Connection, statement: str, params: tuple[object, ...] | None = None) -> SkmError:
    with pytest.raises(psycopg.Error) as caught:
        conn.execute(statement, params)  # pyright: ignore[reportArgumentType]
    return translate_pg_error(caught.value)


_RAISE_STATE = (
    "CREATE FUNCTION pg_temp.raise_state(state text) RETURNS void LANGUAGE plpgsql AS "
    "$$ BEGIN RAISE EXCEPTION 'x' USING ERRCODE = state; END $$"
)


@pytest.mark.pg
def test_constraint_violations_carry_constraint_and_column(autocommit: psycopg.Connection) -> None:
    for statement in (
        "CREATE TEMP TABLE u (id int CONSTRAINT uq_u__id UNIQUE)",
        "CREATE TEMP TABLE p (id int PRIMARY KEY)",
        "CREATE TEMP TABLE c (pid int CONSTRAINT fk_c__pid REFERENCES p (id), "
        "n int CONSTRAINT ck_c__n CHECK (n > 0))",
        "CREATE TEMP TABLE e (a int, CONSTRAINT ex_e__a EXCLUDE USING btree (a WITH =))",
        "CREATE TEMP TABLE nn (col_a int NOT NULL)",
        "INSERT INTO u VALUES (1)",
        "INSERT INTO e VALUES (1)",
    ):
        autocommit.execute(statement)

    unique = _failure(autocommit, "INSERT INTO u VALUES (1)")
    assert (type(unique), unique.code, dict(unique.details)) == (
        Conflict,
        ErrorCode.ALREADY_EXISTS,
        {"constraint": "uq_u__id"},
    )
    reference = _failure(autocommit, "INSERT INTO c (pid) VALUES (42)")
    assert (type(reference), reference.code, dict(reference.details)) == (
        ValidationFailed,
        ErrorCode.INVALID_REFERENCE,
        {"constraint": "fk_c__pid"},
    )
    check = _failure(autocommit, "INSERT INTO c (n) VALUES (0)")
    assert (type(check), check.code, dict(check.details)) == (
        ValidationFailed,
        ErrorCode.SCHEMA_INVALID,
        {"constraint": "ck_c__n"},
    )
    exclusion = _failure(autocommit, "INSERT INTO e VALUES (1)")
    assert (type(exclusion), exclusion.code, dict(exclusion.details)) == (
        Conflict,
        ErrorCode.ALREADY_EXISTS,
        {"constraint": "ex_e__a"},
    )
    not_null = _failure(autocommit, "INSERT INTO nn VALUES (NULL)")
    assert (type(not_null), not_null.code, dict(not_null.details)) == (
        InternalError,
        ErrorCode.INTERNAL_ERROR,
        {"column": "col_a"},
    )


@pytest.mark.pg
def test_a_restricted_delete_is_an_invalid_reference_on_every_server(autocommit: psycopg.Connection) -> None:
    # PostgreSQL 16 reports ON DELETE RESTRICT as 23503, newer servers as 23001 with the constraint name.
    for statement in (
        "CREATE TEMP TABLE rp (id int PRIMARY KEY)",
        "CREATE TEMP TABLE rc (pid int CONSTRAINT fk_rc__pid REFERENCES rp (id) ON DELETE RESTRICT)",
        "INSERT INTO rp VALUES (1)",
        "INSERT INTO rc VALUES (1)",
    ):
        autocommit.execute(statement)
    error = _failure(autocommit, "DELETE FROM rp WHERE id = 1")
    assert (type(error), error.code, dict(error.details)) == (
        ValidationFailed,
        ErrorCode.INVALID_REFERENCE,
        {"constraint": "fk_rc__pid"},
    )


@pytest.mark.pg
def test_a_trigger_restrict_violation_stays_a_database_failure(autocommit: psycopg.Connection) -> None:
    autocommit.execute(_RAISE_STATE)
    error = _failure(autocommit, "SELECT pg_temp.raise_state(%s)", ("23001",))
    assert (type(error), error.code, dict(error.details)) == (
        InternalError,
        ErrorCode.INTERNAL_ERROR,
        {"sqlstate": "23001"},
    )


@pytest.mark.pg
@pytest.mark.parametrize(
    "statement",
    [
        "SELECT 'x'::int",  # 22P02
        "SELECT 99999999999::int",  # 22003
        "SELECT 'not a time'::timestamptz",  # 22007
        "SELECT '2024-13-45'::date",  # 22008
    ],
)
def test_value_errors_are_schema_invalid(autocommit: psycopg.Connection, statement: str) -> None:
    error = _failure(autocommit, statement)
    assert (type(error), error.code, error.retryable) == (ValidationFailed, ErrorCode.SCHEMA_INVALID, False)


@pytest.mark.pg
def test_missing_objects_are_not_migrated(autocommit: psycopg.Connection) -> None:
    for statement in (
        "SELECT * FROM public.skm_no_such_table",  # 42P01
        "SELECT no_such_column FROM (SELECT 1 AS a) s",  # 42703
        "CREATE TABLE skm_no_such_schema.t (a int)",  # 3F000
    ):
        error = _failure(autocommit, statement)
        assert (type(error), error.code) == (PreconditionFailed, ErrorCode.SCHEMA_NOT_MIGRATED)
        assert dict(error.details) == {"hint": "skm db migrate"}


@pytest.mark.pg
def test_statement_timeout(autocommit: psycopg.Connection) -> None:
    autocommit.execute("SET statement_timeout = 50")
    error = _failure(autocommit, "SELECT pg_sleep(5)")
    assert (type(error), error.code, error.retryable) == (
        BackendUnavailable,
        ErrorCode.BACKEND_UNAVAILABLE,
        True,
    )
    assert dict(error.details) == {"reason": "statement_timeout"}


@pytest.mark.pg
def test_lock_timeout(pg_dsn: str, autocommit: psycopg.Connection) -> None:
    key = uuid4().int % 2**31
    with psycopg.connect(pg_dsn, autocommit=True, connect_timeout=5) as holder:
        holder.execute("SELECT pg_advisory_lock(%s)", (key,))
        autocommit.execute("SET lock_timeout = 100")
        with pytest.raises(psycopg.Error) as caught:
            autocommit.execute("SELECT pg_advisory_lock(%s)", (key,))
        error = translate_pg_error(caught.value)
    assert (type(error), error.code, error.retryable) == (Conflict, ErrorCode.SERIALIZATION_FAILURE, True)
    assert dict(error.details) == {"reason": "lock_timeout"}


@pytest.mark.pg
@pytest.mark.parametrize(
    ("sqlstate", "cls", "code", "retryable"),
    [
        ("40001", Conflict, ErrorCode.SERIALIZATION_FAILURE, True),
        ("40P01", Conflict, ErrorCode.SERIALIZATION_FAILURE, True),
        ("57P03", BackendUnavailable, ErrorCode.BACKEND_UNAVAILABLE, True),
        ("53200", BackendUnavailable, ErrorCode.BACKEND_UNAVAILABLE, True),
        ("42501", InternalError, ErrorCode.INTERNAL_ERROR, False),
    ],
)
def test_server_raised_sqlstates(
    autocommit: psycopg.Connection, sqlstate: str, cls: type[SkmError], code: ErrorCode, retryable: bool
) -> None:
    autocommit.execute(_RAISE_STATE)
    error = _failure(autocommit, "SELECT pg_temp.raise_state(%s)", (sqlstate,))
    assert (type(error), error.code, error.retryable) == (cls, code, retryable)


@pytest.mark.pg
def test_trigger_message_comes_from_the_server(autocommit: psycopg.Connection) -> None:
    error = _failure(autocommit, "DO $$ BEGIN RAISE EXCEPTION 'append-only table'; END $$")
    assert (type(error), error.code) == (InternalError, ErrorCode.INTERNAL_ERROR)
    assert dict(error.details) == {"trigger_message": "append-only table"}


@pytest.mark.pg
def test_unknown_sqlstate_keeps_only_the_code(autocommit: psycopg.Connection) -> None:
    autocommit.execute(_RAISE_STATE)
    error = _failure(autocommit, "SELECT pg_temp.raise_state(%s)", ("XX001",))
    assert (type(error), error.code, dict(error.details)) == (
        InternalError,
        ErrorCode.INTERNAL_ERROR,
        {"sqlstate": "XX001"},
    )


def test_refused_connection_is_backend_unavailable() -> None:
    with pytest.raises(psycopg.OperationalError) as caught:
        psycopg.connect("host=127.0.0.1 port=1 dbname=x connect_timeout=2")
    error = translate_pg_error(caught.value)
    assert (type(error), error.retryable) == (BackendUnavailable, True)


# --- jsonb ---------------------------------------------------------------------------------------------


def test_canonical_json_is_compact_sorted_and_unescaped() -> None:
    assert (
        canonical_dumps({"b": 1, "a": ["é", {"z": None, "y": True}]})
        == '{"a":["é",{"y":true,"z":null}],"b":1}'
    )
    assert to_jsonb({"b": 1, "a": 2}).obj == {"b": 1, "a": 2}
    with pytest.raises(ValueError, match="Out of range"):
        canonical_dumps({"x": float("nan")})


def test_naive_datetimes_are_refused() -> None:
    aware = datetime(2026, 1, 1, tzinfo=UTC)
    assert require_aware(aware) is aware
    assert require_aware(datetime(2026, 1, 1, tzinfo=timezone(timedelta(hours=3)))).utcoffset() == timedelta(
        hours=3
    )
    with pytest.raises(ValueError, match="naive"):
        require_aware(datetime(2026, 1, 1))  # noqa: DTZ001


@pytest.mark.pg
def test_jsonb_round_trip_through_the_server(autocommit: psycopg.Connection) -> None:
    row = autocommit.execute(
        "SELECT %s::jsonb, %s::timestamptz", (to_jsonb({"k": ["é", 1]}), datetime(2026, 1, 1, tzinfo=UTC))
    ).fetchone()
    assert row == ({"k": ["é", 1]}, datetime(2026, 1, 1, tzinfo=UTC))


# --- keyset pagination ---------------------------------------------------------------------------------


def test_cursor_round_trip_and_filter_binding() -> None:
    digest = query_digest({"status": "open", "project": 7})
    assert len(digest) == 16
    assert digest == query_digest({"project": 7, "status": "open"})
    assert digest != query_digest({"status": "closed", "project": 7})
    cursor = Cursor(("2026-01-01T00:00:00+00:00", 41), digest)
    text = encode_cursor(cursor)
    assert "=" not in text
    assert decode_cursor(text, expected_query_digest=digest) == cursor


def _raw_cursor(body: str) -> str:
    return base64.urlsafe_b64encode(body.encode()).decode().rstrip("=")


@pytest.mark.parametrize(
    "text",
    [
        "",
        "!!!",  # not base64
        _raw_cursor("not json"),
        _raw_cursor("{}"),
        _raw_cursor("[]"),
        _raw_cursor('{"v":2,"k":[1],"q":"0000000000000000"}'),  # unknown version
        _raw_cursor('{"v":1,"k":[],"q":"0000000000000000"}'),  # no key
        _raw_cursor('{"v":1,"k":[true],"q":"0000000000000000"}'),  # boolean is not a sort value
        _raw_cursor('{"v":1,"k":[1.5],"q":"0000000000000000"}'),  # nor a float
        _raw_cursor('{"v":true,"k":[1],"q":"0000000000000000"}'),
        _raw_cursor('{"v":1,"k":[1],"q":"0000000000000000","x":1}'),  # extra field
        "x" * 600,  # over the 512 character cursor bound
    ],
)
def test_bad_cursors_are_schema_invalid_on_after(text: str) -> None:
    with pytest.raises(ValidationFailed) as caught:
        decode_cursor(text, expected_query_digest="0" * 16)
    assert caught.value.code is ErrorCode.SCHEMA_INVALID
    assert caught.value.details["field"] == "after"


def test_foreign_cursor_is_rejected() -> None:
    text = encode_cursor(Cursor((1,), query_digest({"a": 1})))
    with pytest.raises(ValidationFailed) as caught:
        decode_cursor(text, expected_query_digest=query_digest({"a": 2}))
    assert caught.value.details == {"field": "after", "reason": "query_mismatch"}


def test_keyset_clause() -> None:
    digest = "0" * 16
    assert keyset_clause(["updated_at", "id"], None) == ("TRUE", ())
    cursor = Cursor(("2026-01-01T00:00:00+00:00", 9), digest)
    assert keyset_clause(["updated_at", "id"], cursor) == ("(updated_at, id) < (%s, %s)", cursor.sort_values)
    assert (
        keyset_clause(["t.updated_at", "t.id"], cursor, descending=False)[0]
        == "(t.updated_at, t.id) > (%s, %s)"
    )
    with pytest.raises(ValidationFailed):
        keyset_clause(["id"], cursor)  # key count does not match the sort columns
    for columns in (["id; DROP TABLE x"], ["id", "1 OR 1=1"], []):
        with pytest.raises(ValueError, match="identifiers"):
            keyset_clause(columns, cursor)


def test_limit_bounds_and_pages() -> None:
    assert validate_limit(None) == 50
    assert validate_limit(MAX_LIMIT) == 200
    for bad in (0, -1, MAX_LIMIT + 1, True):
        with pytest.raises(ValidationFailed) as caught:
            validate_limit(bad)
        assert caught.value.details["field"] == "limit"
    digest = "a" * 16
    rows = list(range(1, 6))
    full = page_of(rows, limit=4, digest=digest, key_of=lambda row: (row,))
    assert full.items == (1, 2, 3, 4)
    assert full.next is not None
    assert decode_cursor(full.next, expected_query_digest=digest).sort_values == (4,)
    last = page_of(rows[:4], limit=4, digest=digest, key_of=lambda row: (row,))
    assert last.items == (1, 2, 3, 4)
    assert last.next is None
