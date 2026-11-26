"""Schema snapshot: normalized ``pg_dump --schema-only`` of the ``skm_*`` schemas (adapters §1.10)."""

import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path
from typing import Final

import psycopg
from psycopg.conninfo import conninfo_to_dict

from skm.adapters.postgres.errors import translate_pg_error
from skm.kernel.errors import BackendUnavailable, InternalError
from skm.kernel.generated.error_codes import ErrorCode

__all__ = ["normalize_dump", "schema_snapshot"]

_DROPPED_PREFIXES: Final = ("--", "SET ", "SELECT pg_catalog.set_config", r"\restrict", r"\unrestrict")
_DUMP_ARGS: Final = ("--schema-only", "--no-owner", "--no-privileges", "--no-comments", "--schema=skm_*")
_COMPOSE_FILE: Final = "deploy/compose.dev.yaml"
_VERSION: Final = re.compile(r"(\d+)")
# conninfo keyword -> libpq environment variable; the dump tool gets the connection from the environment so
# that no secret appears on a command line.
_ENV: Final[Mapping[str, str]] = {
    "host": "PGHOST",
    "port": "PGPORT",
    "user": "PGUSER",
    "password": "PGPASSWORD",
    "dbname": "PGDATABASE",
    "sslmode": "PGSSLMODE",
}


def normalize_dump(text: str) -> str:
    """Drop volatile lines, collapse blank runs, trim trailing spaces and end with one newline."""
    lines: list[str] = []
    for raw in text.splitlines():
        if raw.startswith(_DROPPED_PREFIXES):
            continue
        line = raw.rstrip()
        if not line and (not lines or not lines[-1]):
            continue
        lines.append(line)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines) + "\n" if lines else ""


def _major(version_text: str) -> int:
    match = _VERSION.search(version_text)
    if match is None:
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "cannot read the pg_dump version", details={"reason": "version"}
        )
    return int(match.group(1))


def _run(args: list[str], env: Mapping[str, str] | None = None) -> str:
    try:
        done = subprocess.run(args, check=False, capture_output=True, text=True, env=env, timeout=300)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE, "pg_dump could not run", details={"reason": "pg_dump"}
        ) from exc
    if done.returncode != 0:
        raise InternalError(
            ErrorCode.INTERNAL_ERROR, "pg_dump failed", details={"reason": "pg_dump", "exit": done.returncode}
        )
    return done.stdout


def _server_major(dsn: str) -> int:
    try:
        with psycopg.connect(dsn, autocommit=True, connect_timeout=10) as conn:
            return conn.info.server_version // 10000
    except psycopg.Error as exc:
        raise BackendUnavailable(
            ErrorCode.BACKEND_UNAVAILABLE, "cannot connect to the database", details={"phase": "connect"}
        ) from translate_pg_error(exc)


def schema_snapshot(dsn: str, *, repo_root: Path | None = None) -> str:
    """The normalized snapshot text of a migrated database; the caller decides whether to write the file.

    A local ``pg_dump`` is used when its major version is at least the server's; otherwise the dump runs in
    the ``postgres`` service of ``deploy/compose.dev.yaml``.
    """
    server = _server_major(dsn)
    settings = conninfo_to_dict(dsn)
    local = shutil.which("pg_dump")
    if local is not None and _major(_run([local, "--version"])) >= server:
        env = {_ENV[key]: str(value) for key, value in settings.items() if key in _ENV}
        return normalize_dump(_run([local, *_DUMP_ARGS], env))
    compose = ["docker", "compose", "-f", str((repo_root or Path.cwd()) / _COMPOSE_FILE), "exec", "-T"]
    user = settings.get("user")
    name = settings.get("dbname")
    target = [*(["--username", str(user)] if user else []), *(["--dbname", str(name)] if name else [])]
    return normalize_dump(_run([*compose, "postgres", "pg_dump", *_DUMP_ARGS, *target]))
