"""Diagnose the development environment without changing it (tooling spec, section 3)."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
DEV_DATABASE_URL = "postgresql://skm:skm_dev@127.0.0.1:54329/skm_dev"
TEST_DATABASE_URL = "postgresql://skm:skm_dev@127.0.0.1:54329/skm_test"
COMMAND_TIMEOUT = 10


@dataclass(frozen=True)
class Check:
    id: str
    status: Literal["ok", "warn", "fail"]
    detail: str
    hint: str


def result(check_id: str, *, passed: bool, required: bool, detail: str, hint: str) -> Check:
    status = "ok" if passed else "fail" if required else "warn"
    return Check(check_id, status, detail, "" if passed else hint)


def command_check(
    check_id: str,
    command: list[str],
    *,
    required: bool,
    hint: str,
    minimum: tuple[int, ...] | None = None,
) -> Check:
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=COMMAND_TIMEOUT,
            check=False,
        )
    except OSError as exc:
        passed, detail = False, f"{command[0]} unavailable ({type(exc).__name__})"
    except subprocess.TimeoutExpired:
        passed, detail = False, f"{check_id} timed out after {COMMAND_TIMEOUT} seconds"
    else:
        passed = completed.returncode == 0
        output = " ".join((completed.stdout or completed.stderr).split())
        detail = output[:300] or f"exit {completed.returncode}"
        if minimum is not None and passed:
            match = re.search(r"\bv?(\d+)\.(\d+)(?:\.(\d+))?\b", output)
            version = tuple(int(part or 0) for part in match.groups()) if match else ()
            passed = version >= minimum
            if not passed:
                detail += "; requires " + ".".join(map(str, minimum)) + "+"
    return result(check_id, passed=passed, required=required, detail=detail, hint=hint)


def database_target(parameters: Mapping[str, str | int | None]) -> tuple[str, str, str]:
    """Compare database identities independently of passwords, users and URL spelling."""
    host = str(parameters.get("hostaddr") or parameters.get("host") or "")
    host = host.lower().rstrip(".")
    if host in {"localhost", "127.0.0.1", "::1"}:
        host = "localhost"
    # libpq uses PGPORT when the connection string leaves the port unspecified.
    port = parameters.get("port") or os.environ.get("PGPORT") or "5432"
    return host, str(port), str(parameters.get("dbname") or "")


def postgres_check() -> Check:
    hint = "Run make db-up; verify SKM_TEST_DATABASE_URL points to the separate skm_test database."
    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
    except ImportError:
        return result(
            "pg", passed=False, required=True, detail="psycopg is not installed", hint="Run uv sync --frozen."
        )

    dev_url = os.environ.get("SKM_DATABASE_URL", DEV_DATABASE_URL)
    test_url = os.environ.get("SKM_TEST_DATABASE_URL", TEST_DATABASE_URL)
    try:
        dev = conninfo_to_dict(dev_url)
        test = conninfo_to_dict(test_url)
    except psycopg.Error:
        return result(
            "pg", passed=False, required=True, detail="Invalid database connection settings", hint=hint
        )

    if not dev.get("dbname") or not test.get("dbname") or database_target(dev) == database_target(test):
        return result(
            "pg",
            passed=False,
            required=True,
            detail="SKM_DATABASE_URL and SKM_TEST_DATABASE_URL must name separate databases explicitly",
            hint=hint,
        )
    try:
        with psycopg.connect(test_url, connect_timeout=2) as connection:
            server_version = connection.info.server_version
    except psycopg.Error as exc:
        # Connection exceptions may contain credentials: report only the exception type.
        return result(
            "pg",
            passed=False,
            required=True,
            detail=f"Test database connection failed ({type(exc).__name__})",
            hint=hint,
        )
    return result(
        "pg",
        passed=server_version >= 160000,
        required=True,
        detail=f"server_version_num={server_version}; requires PostgreSQL 16+",
        hint=hint,
    )


def disk_check() -> Check:
    try:
        free = shutil.disk_usage(ROOT).free
    except OSError as exc:
        passed, detail = False, f"Cannot inspect free disk space ({type(exc).__name__})"
    else:
        passed, detail = free >= 2 * 1024**3, f"{free / 1024**3:.2f} GiB free in repository filesystem"
    return result(
        "disk", passed=passed, required=False, detail=detail, hint="Free at least 2 GiB of disk space."
    )


def ulimit_check() -> Check:
    try:
        import resource

        soft, _ = resource.getrlimit(resource.RLIMIT_NOFILE)
        passed = soft == resource.RLIM_INFINITY or soft >= 1024
        detail = f"RLIMIT_NOFILE={soft}"
    except (ImportError, OSError, ValueError) as exc:
        passed, detail = False, f"Cannot inspect RLIMIT_NOFILE ({type(exc).__name__})"
    return result("ulimit", passed=passed, required=False, detail=detail, hint="Run ulimit -n 4096.")


def required_checks(value: str) -> set[str]:
    selected = set(value.split(",")) if value else set()
    if selected - {"pg", "node", "git"}:
        raise argparse.ArgumentTypeError("--require accepts comma-separated pg,node,git")
    return selected


def collect_checks(required: set[str]) -> list[Check]:
    return [
        result(
            "python",
            passed=sys.version_info >= (3, 12),
            required=True,
            detail=sys.version.split()[0],
            hint="Install Python 3.12+ and run uv sync --frozen.",
        ),
        command_check(
            "uv", ["uv", "--version"], required=True, minimum=(0, 5, 0), hint="Run pip install -U uv."
        ),
        command_check(
            "lock", ["uv", "lock", "--check"], required=True, hint="Run uv lock, then uv sync --frozen."
        ),
        command_check(
            "docker",
            ["docker", "compose", "version"],
            required=True,
            hint="Install Docker Desktop or Docker Engine with Compose v2.",
        ),
        postgres_check(),
        command_check(
            "git",
            ["git", "--version"],
            required="git" in required,
            minimum=(2, 40, 0),
            hint="Install Git 2.40+ (needed by repository and execution commands).",
        ),
        command_check(
            "node",
            ["node", "--version"],
            required="node" in required,
            minimum=(22, 0, 0),
            hint="Install Node 22 LTS or newer (needed by the web client).",
        ),
        disk_check(),
        ulimit_check(),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--json", action="store_true", help="emit a JSON report")
    parser.add_argument("--require", type=required_checks, default="", metavar="pg,node,git")
    arguments = parser.parse_args(argv)
    checks = collect_checks(arguments.require)
    ok = all(check.status != "fail" for check in checks)
    if arguments.json:
        print(json.dumps({"checks": [asdict(check) for check in checks], "ok": ok}))
    else:
        print("check | status | detail | hint")
        for check in checks:
            print(f"{check.id} | {check.status} | {check.detail} | {check.hint}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
