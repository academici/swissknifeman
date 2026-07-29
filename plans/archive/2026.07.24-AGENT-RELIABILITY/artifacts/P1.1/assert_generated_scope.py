#!/usr/bin/env python3
"""P1.1 — item baseline carrier and generated-artifact scope guard (stdlib-only).

Two subcommands, both fail-closed:

``baseline``
    ``--capture-or-verify`` exclusively creates ``artifacts/<owner>/base-sha.txt``
    from the exact current ``HEAD``, and only when every owner path except that
    carrier is clean.  If the file already exists it is validated (one lowercase
    40-hex line, object type ``commit``, ancestor of ``HEAD``, expected owner
    path) and its bytes are reused **without a write**.  A missing carrier with
    dirty owner paths, a malformed/non-commit/non-ancestor SHA, an owner/path
    mismatch and any overwrite attempt fail (D36).
    ``--verify-and-print`` is the ONLY producer of ``ITEM_BASE_SHA``.

``generated-scope``
    Retains every check of the frozen contract: private-source leakage,
    version/tuple completeness, byte-identical guards, undeclared drift and the
    no-op second run — plus D47 foreign-commit attribution.  A path drifted only
    by commits outside this item's own commit set **and** outside the owner path
    set is reported ``foreign-commit`` and excluded from undeclared drift; a
    foreign commit touching an owner path fails closed with the exact commit and
    path plus an Owner question.  Attribution never mutates, reverts or widens.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PLAN_CARVE_OUT = ("plans/",)


class ScopeError(RuntimeError):
    """Every refusal is an explicit, named failure — never a downgrade to a warning."""


def git(repo: Path, *args: str, check: bool = True) -> str:
    completed = subprocess.run(["git", "-C", str(repo), *args],
                               capture_output=True, text=True, check=False)
    if check and completed.returncode != 0:
        raise ScopeError(f"git {' '.join(args)} failed: {completed.stderr.strip()}")
    return completed.stdout


def load_scope_map(path: Path) -> dict:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ScopeError(f"unreadable scope map {path}: {error}") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("owners"), dict):
        raise ScopeError(f"scope map {path} carries no owners object")
    return payload


def owner_record(scope_map: dict, owner: str) -> dict:
    record = scope_map["owners"].get(owner)
    if not isinstance(record, dict) or not isinstance(record.get("paths"), list):
        raise ScopeError(f"owner {owner} is not declared in the scope map")
    return record


def matches_owner(path: str, owner_paths: list[str]) -> bool:
    for declared in owner_paths:
        if declared.endswith("/"):
            if path == declared.rstrip("/") or path.startswith(declared):
                return True
        elif path == declared:
            return True
    return False


def in_carve_out(path: str) -> bool:
    return any(path.startswith(prefix) for prefix in PLAN_CARVE_OUT)


def dirty_paths(repo: Path, owner_paths: list[str], *, exclude: str) -> list[str]:
    """Owner paths with uncommitted content, excluding the baseline carrier itself."""
    output = git(repo, "status", "--porcelain", "--untracked-files=all")
    dirty = []
    for line in output.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:  # rename record: both sides count
            path = path.split(" -> ")[-1]
        path = path.strip('"')
        if path == exclude:
            continue
        if matches_owner(path, owner_paths):
            dirty.append(path)
    return sorted(set(dirty))


def validate_sha(repo: Path, value: str) -> str:
    if not SHA_RE.fullmatch(value):
        raise ScopeError(f"baseline must be exactly one lowercase 40-hex SHA, got {value!r}")
    kind = git(repo, "cat-file", "-t", value, check=False).strip()
    if kind != "commit":
        raise ScopeError(f"baseline {value} is not a commit object (got {kind or 'nothing'})")
    ancestor = subprocess.run(
        ["git", "-C", str(repo), "merge-base", "--is-ancestor", value, "HEAD"],
        capture_output=True, text=True, check=False)
    if ancestor.returncode != 0:
        raise ScopeError(f"baseline {value} is not an ancestor of HEAD")
    return value


def read_baseline_file(repo: Path, carrier: Path) -> str:
    raw = carrier.read_text(encoding="utf-8")
    lines = [line for line in raw.split("\n")]
    if len(lines) != 2 or lines[1] != "":
        raise ScopeError(f"baseline carrier {carrier} must contain exactly one "
                         "SHA line terminated by a newline")
    return validate_sha(repo, lines[0])


def cmd_baseline(args) -> int:
    repo = Path(args.repo).resolve()
    scope_map = load_scope_map(Path(args.scope_map))
    record = owner_record(scope_map, args.owner)
    carrier_rel = record.get("baseline_file")
    given = Path(args.baseline_file)
    try:
        given_rel = given.resolve().relative_to(repo).as_posix()
    except ValueError:
        given_rel = given.as_posix()
    if carrier_rel != given_rel:
        raise ScopeError(f"owner/path mismatch: owner {args.owner} declares "
                         f"{carrier_rel!r}, got {given_rel!r}")
    carrier = repo / carrier_rel

    if args.verify_and_print:
        if not carrier.is_file():
            raise ScopeError(f"baseline carrier {carrier_rel} does not exist; "
                             "run --capture-or-verify first")
        print(read_baseline_file(repo, carrier))
        return 0

    if carrier.is_file():
        value = read_baseline_file(repo, carrier)
        before = carrier.read_bytes()
        # Resume is byte-for-byte reuse: the carrier is never recomputed or rewritten.
        if carrier.read_bytes() != before:  # pragma: no cover — defensive
            raise ScopeError("baseline carrier changed during verification")
        print(f"baseline: reused {value} for {args.owner} (no write)")
        return 0

    dirty = dirty_paths(repo, record["paths"], exclude=carrier_rel)
    if dirty:
        raise ScopeError(
            f"cannot capture the {args.owner} baseline: owner paths are dirty: {dirty}. "
            "Commit or set aside your own owner-path work first; foreign diff is never "
            "stashed, reverted or cleaned by this guard")
    head = git(repo, "rev-parse", "HEAD").strip()
    validate_sha(repo, head)
    carrier.parent.mkdir(parents=True, exist_ok=True)
    carrier.write_text(head + "\n", encoding="utf-8")
    print(f"baseline: captured {head} for {args.owner} → {carrier_rel}")
    return 0


def changed_paths(repo: Path, baseline: str) -> list[str]:
    committed = git(repo, "diff", "--name-only", f"{baseline}..HEAD").split()
    working = git(repo, "status", "--porcelain", "--untracked-files=all")
    paths = set(committed)
    for line in working.splitlines():
        if not line.strip():
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[-1]
        paths.add(path.strip('"'))
    return sorted(paths)


def own_commits(repo: Path, baseline: str, owner_paths: list[str]) -> set[str]:
    """Commits in the range whose entire footprint stays inside owner+carve-out."""
    revisions = git(repo, "rev-list", f"{baseline}..HEAD").split()
    mine = set()
    for revision in revisions:
        touched = git(repo, "show", "--name-only", "--format=", revision).split()
        if touched and all(matches_owner(path, owner_paths) or in_carve_out(path)
                           for path in touched):
            mine.add(revision)
    return mine


def attribute(repo: Path, baseline: str, path: str) -> list[str]:
    return git(repo, "log", "--format=%H", f"{baseline}..HEAD", "--", path).split()


def private_leakage(repo: Path, prefix: str) -> list[str]:
    """The private/source-only bucket may never reach an ordinary publication unit."""
    findings = []
    bucket = prefix.rstrip("/").rsplit("/", 1)[-1]
    for relative in (".claude-plugin/marketplace.json", ".agents/plugins/marketplace.json"):
        path = repo / relative
        if not path.is_file():
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            findings.append(f"{relative}: unreadable ({error})")
            continue
        for entry in payload.get("plugins", ()):
            if not isinstance(entry, dict):
                continue
            source = entry.get("source")
            source = source.get("path") if isinstance(source, dict) else source
            declared = entry.get("skills")
            declared = [declared] if isinstance(declared, str) else (declared or [])
            if entry.get("name") == bucket:
                findings.append(f"{relative}: private bucket published as unit {bucket!r}")
            if isinstance(source, str) and prefix in source:
                findings.append(f"{relative}: unit {entry.get('name')!r} sources the "
                                f"private bucket ({source})")
            for item in declared:
                if isinstance(item, str) and prefix in item:
                    findings.append(f"{relative}: unit {entry.get('name')!r} lists a "
                                    f"private-source skill ({item})")
    return findings


def _json_version(path: Path) -> str | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    return payload.get("version") if isinstance(payload, dict) else None


def version_completeness(repo: Path, record: dict) -> list[str]:
    """Every declared bump of this owner must be materialised in its exact carrier."""
    failures = []
    for bump in record.get("version_bumps", ()):
        carrier, target = bump.get("carrier"), bump.get("to")
        if carrier == "publication-unit":
            path = repo / "packages/skiller/configs/publication-versions.json"
            if not path.is_file():
                failures.append(f"{bump['unit']}: publication-versions.json is missing")
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                failures.append(f"publication-versions.json unreadable: {error}")
                continue
            units = payload.get("units", payload)
            actual = units.get(bump["unit"]) if isinstance(units, dict) else None
            if isinstance(actual, dict):
                actual = actual.get("version")
            if actual != target:
                failures.append(f"{bump['unit']}: publication unit version is "
                                f"{actual!r}, declared {target!r}")
        elif carrier == "plugin_version":
            path = repo / "packages/task/configs/command-routing.json"
            if not path.is_file():
                failures.append("task command-routing.json is missing")
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as error:
                failures.append(f"command-routing.json unreadable: {error}")
                continue
            if payload.get("plugin_version") != target:
                failures.append(f"task plugin_version is "
                                f"{payload.get('plugin_version')!r}, declared {target!r}")
        elif isinstance(carrier, str) and carrier.endswith(".json"):
            path = repo / carrier
            if not path.is_file():
                failures.append(f"{carrier}: version carrier is missing")
                continue
            actual = _json_version(path)
            if actual != target:
                failures.append(f"{carrier}: version is {actual!r}, declared {target!r}")
        elif isinstance(carrier, str):
            if not (repo / carrier).exists():
                failures.append(f"{carrier}: declared version carrier does not exist")
    return failures


def byte_identical_guards(repo: Path, baseline: str, record: dict,
                          scope_map: dict) -> list[str]:
    """A named guard freezes bytes across the range; a touched path is a failure."""
    failures = []
    guarded_prefixes = []
    for guard in record.get("byte_identical_guards", ()):
        if "class-A" in guard.get("unit", "") or "class-A" in guard.get("rule", ""):
            guarded_prefixes.extend(
                [f".claude/skills/{item['identity']}/" for item in _class_a(scope_map)]
                + [f".agents/skills/{item['identity']}/" for item in _class_a(scope_map)])
    if not guarded_prefixes:
        return failures
    for path in git(repo, "diff", "--name-only", f"{baseline}..HEAD").split():
        for prefix in guarded_prefixes:
            if path.startswith(prefix):
                failures.append(f"{path}: byte-identical guard violated")
    return sorted(set(failures))


def _class_a(scope_map: dict) -> list[dict]:
    """Class-A identities are read from the owner map, never re-derived here."""
    return [record for record in scope_map.get("class_a_identities", ())
            if isinstance(record, dict) and record.get("identity")]


def cmd_generated_scope(args) -> int:
    repo = Path(args.repo).resolve()
    contract = Path(args.contract)
    if not contract.is_file():
        raise ScopeError(f"frozen contract {contract} does not exist")
    contract_text = contract.read_text(encoding="utf-8")
    for anchor in ("Version-first", "Diff-scope guard", "foreign-commit"):
        if anchor not in contract_text:
            raise ScopeError(f"frozen contract {contract} lost the {anchor!r} rule")
    scope_map = load_scope_map(Path(args.scope_map))
    record = owner_record(scope_map, args.owner)
    baseline = validate_sha(repo, args.baseline.strip())
    owner_paths = record["paths"]

    mine = own_commits(repo, baseline, owner_paths)
    report = {
        "owner": args.owner,
        "baseline": baseline,
        "head": git(repo, "rev-parse", "HEAD").strip(),
        "own_commits": sorted(mine),
        "owned": [],
        "undeclared_drift": [],
        "foreign_commit": [],
        "failures": [],
    }
    for path in changed_paths(repo, baseline):
        if in_carve_out(path):
            continue
        commits = attribute(repo, baseline, path)
        foreign = [commit for commit in commits if commit not in mine]
        if matches_owner(path, owner_paths):
            report["owned"].append(path)
            if foreign:
                report["failures"].append(
                    f"foreign commit(s) {foreign} touched owner path {path} — fail closed; "
                    "Owner question: whose change is this and may this item publish over it? "
                    "(never stashed, reverted or reset by this guard)")
            continue
        if commits and not [commit for commit in commits if commit in mine]:
            report["foreign_commit"].append({"path": path, "commits": foreign})
            continue
        report["undeclared_drift"].append(
            path if commits else f"{path} (uncommitted working-tree change)")

    report["failures"].extend(
        f"private-source leakage: {item}"
        for item in private_leakage(repo, scope_map.get("private_source_prefix",
                                                        "packages/skiller/skills/repository-bootstrap/")))
    report["failures"].extend(f"version/tuple completeness: {item}"
                              for item in version_completeness(repo, record))
    report["failures"].extend(f"byte-identical guard: {item}"
                              for item in byte_identical_guards(repo, baseline, record, scope_map))
    report["failures"].extend(f"undeclared drift outside the {args.owner} owner set: {path}"
                              for path in report["undeclared_drift"])
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    return 1 if report["failures"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)

    baseline = sub.add_parser("baseline")
    baseline.add_argument("--repo", required=True)
    baseline.add_argument("--owner", required=True)
    baseline.add_argument("--scope-map", required=True)
    baseline.add_argument("--baseline-file", required=True)
    mode = baseline.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture-or-verify", action="store_true")
    mode.add_argument("--verify-and-print", action="store_true")
    baseline.set_defaults(handler=cmd_baseline)

    scope = sub.add_parser("generated-scope")
    scope.add_argument("--repo", required=True)
    scope.add_argument("--baseline", required=True)
    scope.add_argument("--contract", required=True)
    scope.add_argument("--scope-map", required=True)
    scope.add_argument("--owner", required=True)
    scope.set_defaults(handler=cmd_generated_scope)

    args = parser.parse_args(argv)
    try:
        return args.handler(args)
    except ScopeError as error:
        print(f"FAIL: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
