#!/usr/bin/env python3
"""Public tree hygiene: prohibited suffixes/names/prefixes in the TRACKED tree.

Catches SECRET/ARTIFACT (pathnames), does not scan the contents of files - it is not a secret scanner.
List source - `git ls-files` (index), not `os.walk` (P8.6, transfer raytsystem
public_hygiene.py).
"""
import hashlib
import re
import subprocess
import sys

# Rules - DATA, each with a named reason; expansion "just in case" prohibited
# (Code Guidance P8.6): undecrypted reason The ⇒ gate will start turning red on legal files.
SUFFIX_RULES = [
    (".sqlite", "SQLite-database - private artifact, not published"),
    (".log", "log file - runtime artifact, not published"),
    (".pem", "private key/certificate"),
    (".key", "private key"),
    (".zip", "archive - a binary artifact outside the source tree"),
    (".tar", "archive - a binary artifact outside the source tree"),
    (".tar.gz", "archive - a binary artifact outside the source tree"),
    (".tgz", "archive - a binary artifact outside the source tree"),
    (".rar", "archive - a binary artifact outside the source tree"),
    (".7z", "archive - a binary artifact outside the source tree"),
]

# *.example — exception from ANY suffix/name rules below (fixtures/templates are required
# pass: hygiene catches secret, not extension).
EXAMPLE_SUFFIX = ".example"

ENV_BASENAME = ".env"
ENV_REASON = "secret environment config (.env) — is not published except *.example"

COMPONENT_RULES = [
    ("__pycache__", "compiled cache Python — runtime artifact"),
    (".venv", "virtual environment Python — not published"),
    ("node_modules", "dependencies npm — not published"),
]


# Contents: absolute path of the working environment of a specific machine (home directory + typical
# project layout/configs). Synthetic examples (`/home/user/…`, `/home/example/…`) are not caught - only that
# breaks the installation on another computer and the username is displayed.
CONTENT_RULES = [
    (re.compile(r"(?:/home|/Users)/(?!(?:user|users|example|alice|bob|dev|operator|u|someone|you|me|name"
                r"|username|runner|ci|test)\b)[A-Za-z0-9_.-]+/(?:projects|Vaults|sibintek|Documents|Desktop"
                r"|Downloads|\.config|\.claude|\.codex|\.cursor|\.maind|\.swissknifeman)\b"
                r"|[A-Za-z]:\\+Users\\+(?!(?:user|users|example|alice|bob|dev|operator|u|someone|you|me|name"
                r"|username|runner|ci|test)\b)[A-Za-z0-9_.-]+"),
     "absolute path of the working environment (use a relative path, `<REPO_ROOT>` or `~`)"),
]
CONTENT_MAX_BYTES = 2_000_000
# Files whose bytes are frozen sha256 in code: rewrite path = break the chain. Only with a reason.
CONTENT_EXEMPT = {
    "packages/maind/tests/test_provider_deploy.py":
        "accurate historical preimage D108/D115, sha256 which is pinned to provider_deploy.py",
}
# Sealed measurement evidence: its text is the measured input, so rewriting it would falsify the measurement.
# None remain: the only one (the v2 calibration probe log) was deleted with the v2 runtime.
CONTENT_PLAN_EXEMPT: dict[str, str] = {}
# The exemption holds only while the sealed file is byte-identical to the reviewed one.
CONTENT_PLAN_EXEMPT_SHA256: dict[str, str] = {}

# Working documents are local-only; nothing tracked may live under or point into them.
WORKING_DOC_DIRS = ("plans/", "roadmap/", "tasks/", ".cursor/plans/")
# Concrete plan identity: dated plan ID, Short-ID citation, or a link into the working directories.
# Synthetic fixture IDs are namespaced `DEMO...` and are allowed.
PLAN_REFERENCE_RULES = [
    (re.compile(r"20\d\d\.[01]\d\.[0-3]\d-(?:№\d+-)?(?!DEMO(?:-|\b))[A-Z]"), "concrete plan ID"),
    (re.compile(r"PLAN\d+\.[DPF]\d"), "Short-ID plan citation"),
    (re.compile(r"(?<![\w<{./-])(?:roadmap|tasks)/(?![<{])[\w.№-]"), "link into a working directory"),
    (re.compile(r"(?<![\w<{./-])plans/(?:archive/)?(?:20\d\d\.[01]\d\.[0-3]\d-(?:№\d+-)?)?(?!DEMO)[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+"),
     "path into a plan directory"),
]


# Plan-engine test data exercises the plan ID and Short-ID syntax itself (reference parsing, store,
# views, bridges, golden outputs), so its identifiers cannot avoid that shape. They are synthetic and
# these trees are exempt from the plan-reference rules ONLY; the content rules above still apply.
PLAN_SYNTAX_TEST_TREES = {
    "packages/task/tests/engine/": "plan engine tests and fixtures: ID, Short-ID and reference syntax",
    "packages/task/bridges/orch/tests/": "plan-to-orchestration bridge tests: Short-ID subjects and parity with plan files",
    "packages/orch/fixtures/exec/": "orchestration exec-contract fixtures: plan-bound identifiers",
    "packages/orch/tests/": "orchestration tests and goldens: plan-bound identifiers and profile examples",
    "tests/golden/": "golden fixtures of the plan CLI output on the synthetic engine demo plan: its ID shape",
}


def plan_reference_violations(paths, read=None):
    """Tracked files must not sit in working directories or reference concrete plans."""
    read = read or _read_text
    found = [(path, "tracked working document (plans/, roadmap/, tasks/, .cursor/plans/ are local-only)")
             for path in paths if path.startswith(WORKING_DOC_DIRS)]
    for path in paths:
        if path.startswith(WORKING_DOC_DIRS) or path.startswith(tuple(PLAN_SYNTAX_TEST_TREES)):
            continue
        text = read(path)
        if path in CONTENT_PLAN_EXEMPT:
            if text is not None and hashlib.sha256(text.encode("utf-8")).hexdigest() != CONTENT_PLAN_EXEMPT_SHA256[path]:
                found.append((path, "sealed measurement changed; exemption no longer applies"))
            continue
        if text is None:
            continue
        for pattern, reason in PLAN_REFERENCE_RULES:
            match = pattern.search(text)
            if match:
                found.append((f"{path} ({match.group(0)})", reason))
    return found


def content_violations(paths, read=None):
    """Content violations tracked-text files; binary and large ones are skipped."""
    read = read or _read_text
    found = []
    for path in paths:
        if path in CONTENT_EXEMPT:
            continue
        text = read(path)
        if text is None:
            continue
        for pattern, reason in CONTENT_RULES:
            match = pattern.search(text)
            if match:
                found.append((f"{path} ({match.group(0)})", reason))
    return found


def _read_text(path):
    try:
        with open(path, "rb") as stream:
            data = stream.read(CONTENT_MAX_BYTES + 1)
    except OSError:
        return None
    if len(data) > CONTENT_MAX_BYTES or b"\0" in data[:4096]:
        return None
    return data.decode("utf-8", "replace")


def list_tracked_files():
    try:
        out = subprocess.run(
            ["git", "ls-files"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"git ls-files not available: {exc}", file=sys.stderr)
        sys.exit(2)
    return [line for line in out.stdout.splitlines() if line]


def violation_reason(path):
    if path.endswith(EXAMPLE_SUFFIX):
        return None
    basename = path.rsplit("/", 1)[-1]
    if basename == ENV_BASENAME:
        return ENV_REASON
    for suffix, reason in SUFFIX_RULES:
        if path.endswith(suffix):
            return reason
    parts = path.split("/")
    for name, reason in COMPONENT_RULES:
        if name in parts:
            return reason
    return None


def check(paths):
    violations = []
    for path in paths:
        reason = violation_reason(path)
        if reason:
            violations.append((path, reason))
    return violations


def main(argv):
    paths = list_tracked_files()
    violations = check(paths) + content_violations(paths) + plan_reference_violations(paths)
    if violations:
        for path, reason in violations:
            print(f"{path} — is prohibited by the rule «{reason}»")
        return 1
    print("public-hygiene: 0 violations")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
