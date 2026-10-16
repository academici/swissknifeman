#!/usr/bin/env python3
"""Static test-isolation check of a Laravel project: prints one check-result/v1 JSON, exit 1 on fail.

Checks the first lines of the guard (phpunit.xml, tests/bootstrap.php, TestEnvironmentGuard, TestCase wiring).
Usage: preflight.py [--root DIR]
"""
import argparse
import json
import re
import sys
from pathlib import Path

CHECK_ID = "test-isolation-guard.static"
SCHEMA = "urn:swissknifeman:aicore:check-result:v1"


def _read(path):
    return path.read_text(encoding="utf-8") if path.is_file() else None


def _env(xml, name):
    match = re.search(rf'<env\s+name="{name}"\s+value="([^"]*)"', xml)
    return match.group(1) if match else None


def findings(root):
    out = []
    xml = _read(root / "phpunit.xml") or _read(root / "phpunit.xml.dist")
    if xml is None:
        return ["phpunit.xml is missing"]
    if _env(xml, "APP_ENV") != "testing":
        out.append("phpunit.xml: APP_ENV is not 'testing'")
    db = _env(xml, "DB_DATABASE")
    if not db or not db.endswith("_test"):
        out.append(f"phpunit.xml: DB_DATABASE {db!r} does not end with _test")
    if _env(xml, "MEDIA_DISK") != "media-test":
        out.append("phpunit.xml: MEDIA_DISK is not 'media-test'")
    if not re.search(r'bootstrap="tests/bootstrap\.php"', xml):
        out.append("phpunit.xml: tests/bootstrap.php is not wired")
    boot = _read(root / "tests" / "bootstrap.php")
    if boot is None:
        out.append("tests/bootstrap.php is missing")
    else:
        for needle in ("$_SERVER", "$_ENV", "putenv("):
            if needle not in boot:
                out.append(f"tests/bootstrap.php: {needle} is not written")
        load = re.search(r"require(?:_once)?[^;]*autoload\.php", boot)
        autoload = load.start() if load else -1
        first = min((boot.find(n) for n in ("DB_DATABASE", "MEDIA_DISK") if n in boot), default=-1)
        if autoload != -1 and (first == -1 or first > autoload):
            out.append("tests/bootstrap.php: test env is not set before vendor/autoload.php")
    guard = _read(root / "tests" / "Support" / "TestEnvironmentGuard.php")
    if guard is None:
        out.append("tests/Support/TestEnvironmentGuard.php is missing")
    else:
        for method in ("assertIsolatedTestDatabase", "assertIsolatedTestMediaDisk"):
            if method not in guard:
                out.append(f"TestEnvironmentGuard: {method} is missing")
    case = _read(root / "tests" / "TestCase.php")
    if case is None:
        out.append("tests/TestCase.php is missing")
    elif "createApplication" not in case or "TestEnvironmentGuard" not in case:
        out.append("tests/TestCase.php: createApplication does not call TestEnvironmentGuard")
    return out


def run(root):
    problems = findings(root)
    if not (root / "phpunit.xml").is_file() and not (root / "phpunit.xml.dist").is_file():
        return {"$schema": SCHEMA, "check_id": CHECK_ID, "status": "skip", "category": "config",
                "observed": "not a Laravel test project: no phpunit.xml", "evidence": [f"root: {root}"]}
    if problems:
        return {"$schema": SCHEMA, "check_id": CHECK_ID, "status": "fail", "category": "config",
                "observed": f"{len(problems)} isolation gap(s)", "evidence": problems,
                "remediation": "wire the missing lines with the skill snippets (bootstrap.php, TestEnvironmentGuard.php, TestCase.php)"}
    return {"$schema": SCHEMA, "check_id": CHECK_ID, "status": "ok", "category": "config",
            "observed": "serial isolation lines 1-2 are in place", "evidence": ["phpunit.xml", "tests/bootstrap.php",
            "tests/Support/TestEnvironmentGuard.php", "tests/TestCase.php"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    result = run(Path(args.root).resolve())
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    sys.exit(1 if result["status"] == "fail" else 0)
