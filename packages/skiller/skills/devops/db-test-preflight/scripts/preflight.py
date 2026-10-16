#!/usr/bin/env python3
"""DB test preflight gates: prints one check-result/v1 JSON, exit 1 on fail.

Static gates always run (target DB from TEST_DB or phpunit.xml, name must match *_test).
`--live` adds the runtime gates of snippets/preflight.sh: container up and Postgres ready.
Usage: preflight.py [--root DIR] [--mode docker|host] [--live]
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

CHECK_ID = "db-test-preflight.gates"
SCHEMA = "urn:swissknifeman:aicore:check-result:v1"
NAME_GATE = re.compile(r"^[a-z0-9_]+_test$")
PHPUNIT_DB = re.compile(r'<env\s+name="DB_DATABASE"\s+value="([^"]+)"')


def _result(status, observed, evidence, remediation=None):
    doc = {"$schema": SCHEMA, "check_id": CHECK_ID, "status": status, "category": "state",
           "observed": observed, "evidence": evidence}
    if remediation:
        doc["remediation"] = remediation
    return doc


def _target_db(root):
    if os.environ.get("TEST_DB"):
        return os.environ["TEST_DB"], "TEST_DB"
    phpunit = root / "phpunit.xml"
    if phpunit.is_file():
        match = PHPUNIT_DB.search(phpunit.read_text(encoding="utf-8"))
        if match:
            return match.group(1), "phpunit.xml"
    return None, None


def _run(argv, cwd):
    try:
        return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, timeout=60).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def _live(root, mode, evidence):
    if mode == "host":
        if not shutil.which("pg_isready"):
            return "pg_isready is not installed", "install the PostgreSQL client tools"
        port = os.environ.get("DB_PORT", "5432")
        if not _run(["pg_isready", "-h", "127.0.0.1", "-p", port], root):
            return f"Postgres not ready on 127.0.0.1:{port}", "start Postgres or fix DB_PORT"
        evidence.append(f"pg_isready ok on 127.0.0.1:{port}")
        return None, None
    service = os.environ.get("DB_SERVICE", "pgsql")
    if not shutil.which("docker"):
        return "docker is not installed", "install docker or use --mode host"
    probe = subprocess.run(["docker", "compose", "ps", "--status", "running", "--services"],
                           cwd=root, capture_output=True, text=True, timeout=60)
    if service not in probe.stdout.split():
        return f"container '{service}' is not running", f"docker compose up -d {service}"
    evidence.append(f"container {service} running")
    if not _run(["docker", "compose", "exec", "-T", service, "sh", "-lc",
                 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'], root):
        return f"Postgres inside '{service}' is not ready", "wait for Postgres to finish initializing"
    evidence.append(f"pg_isready ok inside {service}")
    return None, None


def run(root, mode, live):
    db, source = _target_db(root)
    if not db:
        return _result("fail", "target test database is unknown", [f"root: {root}"],
                       "set TEST_DB or DB_DATABASE in phpunit.xml")
    evidence = [f"target database {db} (from {source})"]
    if not NAME_GATE.match(db):
        return _result("fail", f"target database '{db}' does not end with _test", evidence,
                       "point DB_DATABASE in phpunit.xml and tests/bootstrap.php to <app>_test; never run tests on dev/prod")
    if live:
        problem, fix = _live(root, mode, evidence)
        if problem:
            return _result("fail", problem, evidence, fix)
    return _result("ok", f"test database '{db}' passes the *_test gate" + (" and is reachable" if live else ""),
                   evidence)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--mode", choices=("docker", "host"), default="docker")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    result = run(Path(args.root).resolve(), args.mode, args.live)
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(1 if result["status"] == "fail" else 0)
