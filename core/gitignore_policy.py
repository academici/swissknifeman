"""Check a project's .gitignore/tracking state against the shared gitignore policy.

The policy (`configs/gitignore-policy.json`) maps every service file that swissknifeman, maind,
harness, skiller and task hand out to `ignore` / `commit` / `portable-or-ignore` / `project`.
`check_project` is read-only: it asks git what is tracked, untracked-and-not-ignored or ignored and
reports drift with a concrete fix. stdlib only.
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
import re
import subprocess

from .config_paths import shared_config_path

POLICIES = ("ignore", "commit", "portable-or-ignore", "project")
# Absolute home paths and Windows user dirs: the machine-specific marker used by the runbook.
_MACHINE = re.compile(r"/home/[^/\s\"']+|/Users/[^/\s\"']+|[A-Za-z]:\\\\?Users\\\\?")
_MAX_READ = 1_000_000


class PolicyError(ValueError):
    pass


def load_policy(path: str | Path | None = None) -> dict:
    target = Path(path) if path else shared_config_path("gitignore-policy")
    try:
        policy = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PolicyError(f"gitignore policy unreadable: {target}: {exc}") from exc
    if policy.get("schema_version") != "gitignore-policy/v1" or not isinstance(policy.get("entries"), list):
        raise PolicyError(f"unsupported gitignore policy shape: {target}")
    seen = set()
    for entry in policy["entries"]:
        if (entry.get("policy") not in POLICIES or not entry.get("id") or entry["id"] in seen
                or not entry.get("paths") or not all(isinstance(p, str) and p for p in entry["paths"])):
            raise PolicyError(f"invalid gitignore policy entry: {entry.get('id')!r}")
        seen.add(entry["id"])
    return policy


def _regex(pattern: str) -> re.Pattern:
    """Root-anchored gitignore glob → regex. Trailing `/` matches everything beneath."""
    directory = pattern.endswith("/")
    body = pattern.rstrip("/")
    out, index = [], 0
    while index < len(body):
        char = body[index]
        if body.startswith("**/", index):
            out.append("(?:.*/)?")
            index += 3
            continue
        if body.startswith("**", index):
            out.append(".*")
            index += 2
            continue
        out.append("[^/]*" if char == "*" else "[^/]" if char == "?" else re.escape(char))
        index += 1
    return re.compile("^" + "".join(out) + ("(?:/.*)?$" if directory else "(?:/.*)?$"))


# Only the repository's own .gitignore counts: a user-global excludes file or .git/info/exclude hides
# a file locally but protects neither teammates nor CI.
_ENV = {**os.environ, "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_SYSTEM": os.devnull}
_SHARED_EXCLUDES = ("--exclude-per-directory=.gitignore",)


def _git(root: Path, *args: str) -> list[str]:
    done = subprocess.run(("git", "-C", str(root), "-c", f"core.excludesFile={os.devnull}", *args),
                          capture_output=True, check=False, env=_ENV)
    if done.returncode != 0:
        raise PolicyError(f"git {' '.join(args)} failed: {done.stderr.decode(errors='replace').strip()}")
    return [item.decode("utf-8", "replace") for item in done.stdout.split(b"\0") if item]


def _ignored(root: Path, relative: str) -> bool:
    try:
        return bool(_git(root, "ls-files", "-z", "--others", "--ignored", *_SHARED_EXCLUDES, "--", relative))
    except PolicyError:
        return False


def _machine_specific(path: Path) -> bool:
    try:
        if path.is_dir():
            return False
        return bool(_MACHINE.search(path.read_bytes()[:_MAX_READ].decode("utf-8", "replace")))
    except OSError:
        return False


def _existing(root: Path, pattern: str) -> list[str]:
    """Worktree paths matching one root-anchored pattern (a directory pattern yields the directory)."""
    base = pattern.rstrip("/")
    hits = glob.glob(os.path.join(str(root), base), recursive=True)
    return sorted(os.path.relpath(hit, root) for hit in hits)


def check_project(project_root: str | Path, policy: dict | None = None) -> list[dict]:
    """Findings: {entry, policy, path, level, code, fix}. Empty list means no drift."""
    root = Path(project_root)
    policy = policy or load_policy()
    try:
        tracked = _git(root, "ls-files", "-z")
        untracked = _git(root, "ls-files", "-z", "--others", *_SHARED_EXCLUDES)
    except (PolicyError, OSError) as exc:
        return [{"entry": "-", "policy": "-", "path": ".", "level": "info", "code": "not-a-git-worktree",
                 "fix": str(exc)}]
    findings: list[dict] = []
    groups: dict[str, dict[str, dict[str, str]]] = {}

    def add(entry, path, level, code, fix):
        findings.append({"entry": entry["id"], "policy": entry["policy"], "path": path,
                         "level": level, "code": code, "fix": fix})

    for entry in policy["entries"]:
        kind = entry["policy"]
        for pattern in entry["paths"]:
            matcher = _regex(pattern)
            tracked_hits = [p for p in tracked if matcher.match(p)]
            untracked_hits = [p for p in untracked if matcher.match(p)]
            if kind == "ignore":
                for path in tracked_hits:
                    add(entry, path, "error", "tracked-must-be-ignored",
                        f"git rm --cached -- '{path}' и добавить `{pattern}` в .gitignore")
                if untracked_hits:
                    add(entry, untracked_hits[0], "error", "unignored",
                        f"добавить `{pattern}` в .gitignore ({len(untracked_hits)} файл(ов) не игнорируются)")
            elif kind == "portable-or-ignore":
                for path in tracked_hits + untracked_hits:
                    if _machine_specific(root / path):
                        state = "tracked" if path in tracked_hits else "unignored"
                        add(entry, path, "error", f"{state}-machine-specific",
                            "убрать абсолютные пути (indirection `${VAR:-default}`) либо "
                            f"`git rm --cached` + .gitignore `{pattern}` + `.example`")
            else:  # commit / project
                for path in _existing(root, pattern):
                    relative = path.replace(os.sep, "/")
                    is_tracked = any(matcher.match(p) and (p == relative or p.startswith(relative + "/"))
                                     for p in tracked_hits)
                    is_untracked = any(p == relative or p.startswith(relative + "/") for p in untracked_hits)
                    if is_tracked:
                        state = "tracked"
                    elif is_untracked:
                        state = "untracked"
                    elif _ignored(root, relative):
                        state = "ignored"
                    else:
                        continue
                    if kind == "project":
                        groups.setdefault(entry.get("group") or entry["id"], {}).setdefault(
                            entry["id"], {})[relative] = state
                    elif state == "ignored":
                        add(entry, relative, "error", "ignored-must-be-committed",
                            f"убрать `{pattern}` из .gitignore: файл общий для команды")
                    elif state == "untracked":
                        add(entry, relative, "warn", "not-committed-yet",
                            f"git add -- '{relative}' (общий артефакт ещё не в репозитории)")
    for group, entries in groups.items():
        states = {state for paths in entries.values() for state in paths.values()}
        if len(states) > 1:
            detail = ", ".join(f"{path}={state}" for paths in entries.values() for path, state in sorted(paths.items()))
            findings.append({"entry": group, "policy": "project", "path": group, "level": "warn",
                             "code": "mixed-group-state",
                             "fix": f"единообразить состояние группы: {detail}"})
    order = {"error": 0, "warn": 1, "info": 2}
    return sorted(findings, key=lambda f: (order[f["level"]], f["entry"], f["path"]))


def recommended_block(findings: list[dict], policy: dict | None = None) -> list[str]:
    """.gitignore lines that would resolve the `ignore`-type findings (read-only suggestion)."""
    policy = policy or load_policy()
    patterns = {entry["id"]: entry["paths"] for entry in policy["entries"]}
    lines: list[str] = []
    for finding in findings:
        if finding["code"] in {"tracked-must-be-ignored", "unignored", "tracked-machine-specific",
                               "unignored-machine-specific"}:
            for pattern in patterns.get(finding["entry"], ()):
                if _regex(pattern).match(finding["path"]) and pattern not in lines:
                    lines.append(pattern)
    return lines
