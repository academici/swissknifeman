#!/usr/bin/env python3
"""gui-workspace commands for the GUI broker: a fixed set of verbs, each one `workspace ... --json`, nothing else runs.

    run.py init                                     run.py sync-commit | sync-pull | sync-push | sync-resolve-reset
    run.py project-attach DIR                       run.py sync-resolve PATH local|remote
    run.py project-scan DIR                         run.py connect URL [--branch B]
    run.py project-rebind PROJECT_ID DIR
    run.py migrate-plan|migrate-apply DIR [--on-conflict keep-workspace|import-copy]
    run.py migrate-verify DIR                       run.py migrate-cleanup DIR PROJECT_ID

Every value is checked here before the workspace command line starts (exit 2, nothing runs): absolute existing folders,
a project id, a branch, a relative path without ``..`` or ``=``, a remote URL without a password. The argv is a list
(no shell). The cleanup runs only when the typed id equals the project_id of the folder; a push first prints the
remote and the branch it publishes to.
"""
from __future__ import annotations

import os
import re
import sys
from typing import Callable, Dict, List, Optional, Tuple

from adapter import WorkspaceError, has_userinfo, workspace_command, workspace_json

PROJECT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
BRANCH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
ON_CONFLICT = ("keep-workspace", "import-copy")
SIDES = ("local", "remote")


class Invalid(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def folder(value: str) -> str:
    if not value or value.startswith("-") or "\x00" in value or "\n" in value:
        raise Invalid("INVALID_PATH", "expected an absolute folder")
    if not os.path.isabs(value):
        raise Invalid("INVALID_PATH", "expected an absolute folder")
    real = os.path.realpath(value)
    if not os.path.isdir(real):
        raise Invalid("INVALID_PATH", f"not a folder: {value}")
    return real


def project_id(value: str) -> str:
    if not PROJECT_ID.match(value):
        raise Invalid("INVALID_PROJECT_ID", "not a project id")
    return value


def branch(value: str) -> str:
    if not BRANCH.match(value) or ".." in value:
        raise Invalid("INVALID_BRANCH", "not a branch name")
    return value


def conflict_path(value: str) -> str:
    parts = value.split("/")
    if (not value or value.startswith(("-", "/")) or "=" in value or "\x00" in value or "\n" in value
            or ".." in parts or "" in parts):
        raise Invalid("INVALID_PATH", "expected a path inside the workspace without '..' or '='")
    return value


def remote_url(value: str) -> str:
    if not value or value.startswith("-") or re.search(r"[\s\x00]", value):
        raise Invalid("INVALID_REMOTE", "expected a git remote URL")
    match = re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://([^/?#]*@)?", value)
    if match and match.group(1) and (":" in match.group(1)[:-1] or value.lower().startswith(("http://", "https://"))):
        raise Invalid("REMOTE_HAS_CREDENTIALS", "the remote URL must not carry a password or token; use a credential helper")
    return value


def enum(allowed: Tuple[str, ...]) -> Callable[[str], str]:
    def check(value: str) -> str:
        if value not in allowed:
            raise Invalid("INVALID_VALUE", f"{value!r} is not one of {', '.join(allowed)}")
        return value
    return check


# verb -> (positional checks, allowed flags {flag: check}, builder of workspace args from the checked values)
SPEC: Dict[str, Tuple[List[Callable[[str], str]], Dict[str, Callable[[str], str]], Callable[[List[str], Dict[str, str]], List[str]]]] = {
    "init": ([], {}, lambda p, f: ["init"]),
    "project-attach": ([folder], {}, lambda p, f: ["project", "attach", "--project", p[0]]),
    "project-scan": ([folder], {}, lambda p, f: ["project", "scan", p[0]]),
    "project-rebind": ([project_id, folder], {}, lambda p, f: ["project", "rebind", p[0], "--path", p[1]]),
    "migrate-plan": ([folder], {"--on-conflict": enum(ON_CONFLICT)},
                     lambda p, f: ["migrate", "plan", "--project", p[0], *_flags(f)]),
    "migrate-apply": ([folder], {"--on-conflict": enum(ON_CONFLICT)},
                      lambda p, f: ["migrate", "apply", "--project", p[0], "--yes", *_flags(f)]),
    "migrate-verify": ([folder], {}, lambda p, f: ["migrate", "verify", "--project", p[0]]),
    "migrate-cleanup": ([folder, project_id], {}, lambda p, f: ["migrate", "cleanup", "--project", p[0], "--confirm", p[1]]),
    "sync-commit": ([], {}, lambda p, f: ["sync", "--commit"]),
    "sync-pull": ([], {}, lambda p, f: ["sync", "--pull"]),
    "sync-push": ([], {}, lambda p, f: ["sync", "--push"]),
    "sync-resolve": ([conflict_path, enum(SIDES)], {}, lambda p, f: ["sync", "--resolve", f"{p[0]}={p[1]}"]),
    "sync-resolve-reset": ([], {}, lambda p, f: ["sync", "--resolve-reset"]),
    "connect": ([remote_url], {"--branch": branch}, lambda p, f: ["connect", "--remote", p[0], *_flags(f)]),
}
USAGE = "usage: run.py <" + "|".join(SPEC) + "> [values] (see the header of run.py)"


def _flags(values: Dict[str, str]) -> List[str]:
    return [item for flag, value in values.items() for item in (flag, value)]


def parse(argv: List[str]) -> List[str]:
    """The workspace args of ``argv`` (without ``--json``); ``Invalid`` for anything outside the spec."""
    if not argv or argv[0] not in SPEC:
        raise Invalid("USAGE", USAGE)
    checks, flags, build = SPEC[argv[0]]
    rest = argv[1:]
    if len(rest) < len(checks):
        raise Invalid("USAGE", USAGE)
    positional = [check(value) for check, value in zip(checks, rest)]
    rest = rest[len(checks):]
    given: Dict[str, str] = {}
    while rest:
        if len(rest) < 2 or rest[0] not in flags or rest[0] in given:
            raise Invalid("USAGE", USAGE)
        given[rest[0]] = flags[rest[0]](rest[1])
        rest = rest[2:]
    return build(positional, given)


def _check_cleanup(args: List[str]) -> None:
    """The typed id must be the project_id of the folder (the CLI checks it again)."""
    target, typed = args[args.index("--project") + 1], args[args.index("--confirm") + 1]
    listed = workspace_json(["project", "list"], 60)
    rows = listed.get("projects") if isinstance(listed, dict) else None
    owner: Optional[str] = None
    for row in rows if isinstance(rows, list) else []:
        if isinstance(row, dict) and any(isinstance(p, str) and os.path.realpath(p) == target for p in row.get("paths") or ()):
            owner = row.get("project_id")
    if owner is None:
        raise Invalid("PROJECT_NOT_BOUND", f"{target} is not bound to a project of the workspace")
    if owner != typed:
        raise Invalid("CONFIRM_MISMATCH", "the typed project id does not match the project of this folder")


def _announce_push() -> None:
    doc = workspace_json(["status"], 60)
    git = doc.get("git") if isinstance(doc, dict) and isinstance(doc.get("git"), dict) else {}
    if not git.get("remote"):
        raise Invalid("NO_REMOTE", "the workspace has no remote; connect one first")
    if has_userinfo(git["remote"]):
        raise Invalid("WORKSPACE_REMOTE_LEAK", "the remote carries userinfo; refused")
    print(f"pushing to {git['remote']} branch {git.get('branch')}", flush=True)


def main(argv: List[str]) -> int:
    try:
        args = parse(argv)
        if argv[0] == "migrate-cleanup":
            _check_cleanup(args)
        elif argv[0] == "sync-push":
            _announce_push()
        command = [*workspace_command(), *args, "--json"]
    except Invalid as error:
        print(f"{error.code}: {error}", file=sys.stderr)
        return 2
    sys.stdout.flush()
    os.execv(command[0], command)
    return 1  # not reached


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except WorkspaceError as error:
        print(f"{error.code}: {error.message}", file=sys.stderr)
        sys.exit(1)
