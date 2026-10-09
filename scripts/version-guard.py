#!/usr/bin/env python3
"""Version helper: find units whose content changed without a version bump, bump them consistently.

Provider caches are keyed by plugin version (`~/.claude/plugins/cache/<marketplace>/<plugin>/<version>`).
Changed bytes under an unchanged version are never re-fetched, so every shipped change needs a bump.

  version-guard.py status [--since vX.Y.Z] [--installed]   # exit 1 when a changed unit keeps its version
  version-guard.py bump <package|unit> [--part patch|minor|X.Y.Z]

Version owners (configs/release-units.json): package units live in packages/<name>/package.json,
skill units in packages/skiller/configs/publication-versions.json, `planner` follows the umbrella
(CHANGELOG heading, bumped by `skiller release`). Run `skiller registry` after `bump`.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "packages/aicore/lib")]

from aicore.release import attestation  # noqa: E402

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
SHA = re.compile(r"^[0-9a-f]{12}$")
PUBLICATION_VERSIONS = ROOT / "packages/skiller/configs/publication-versions.json"


def _key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def latest_snapshot(since: str | None) -> dict:
    releases = {path.stem[1:]: path for path in (ROOT / "releases").glob("v*.json")
                if SEMVER.match(path.stem[1:])}
    if since is None:  # draft snapshots (no git tag yet) are regenerated, so never a baseline
        tagged = [v for v in releases if subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/tags/v{v}"], cwd=ROOT,
            capture_output=True).returncode == 0]
        releases_pool = {v: releases[v] for v in tagged} or releases
    else:
        releases_pool = releases
    version = since.lstrip("v") if since else max(releases_pool, key=_key)
    if version not in releases:
        sys.exit(f"ERROR: no releases/v{version}.json")
    return json.loads(releases[version].read_text(encoding="utf-8"))


def changed_units(previous: dict, current: dict) -> list[dict]:
    old = {unit["id"]: unit for unit in previous["units"]}
    rows = []
    for unit in current["units"]:
        prior = old.get(unit["id"])
        if prior is None:
            rows.append({"id": unit["id"], "state": "new", "from": None, "to": unit["version"]})
        elif prior["tree_digest"] != unit["tree_digest"]:
            state = "bumped" if prior["version"] != unit["version"] else "NOT-BUMPED"
            rows.append({"id": unit["id"], "state": state, "from": prior["version"],
                         "to": unit["version"], "source": unit["version_source"]})
    return rows


def installed_drift(current: dict) -> list[str]:
    path = Path.home() / ".claude/plugins/installed_plugins.json"
    if not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    wanted = {unit["id"]: unit["version"] for unit in current["units"]}
    lines, sha_keyed = [], 0
    for key, entries in data.get("plugins", data).items():
        name, _, marketplace = key.partition("@")
        if marketplace != "swissknifeman" or name not in wanted:
            continue
        installed = sorted({entry.get("version") for entry in entries}, key=str)
        if all(SHA.match(str(version)) for version in installed):
            sha_keyed += 1  # git-SHA installs follow the marketplace ref, not the plugin version
        elif installed != [wanted[name]]:
            lines.append(f"{name}: installed {', '.join(map(str, installed))} != repo {wanted[name]}")
    if sha_keyed:
        lines.append(f"({sha_keyed} plugin(s) installed by git SHA — refresh via `claude plugin marketplace update`)")
    return lines


def cmd_status(args: argparse.Namespace) -> int:
    previous = latest_snapshot(args.since)
    current = attestation.build(ROOT, None, package_root=ROOT / "packages/skiller")
    print(f"baseline {previous['umbrella']['tag']}, working tree umbrella {current['umbrella']['version']}")
    rows = changed_units(previous, current)
    stale = [row for row in rows if row["state"] == "NOT-BUMPED"]
    for row in rows if args.all else [r for r in rows if r["state"] != "bumped"]:
        print(f"  {row['state']:<10} {row['id']}: {row['from']} -> {row['to']}")
    print(f"  {len(rows) - len(stale)} changed unit(s) already bumped"
          + ("" if args.all else " (--all to list)"))
    if args.installed:
        for line in installed_drift(current):
            print("  stale-cache", line)
    if stale:
        print(f"{len(stale)} unit(s) changed without a version bump: run `version-guard.py bump <unit>`")
    return 1 if stale else 0


def next_version(current: str, part: str) -> str:
    if SEMVER.match(part):
        return part
    major, minor, patch = _key(current)
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    if part == "patch":
        return f"{major}.{minor}.{patch + 1}"
    sys.exit(f"ERROR: --part must be patch|minor|X.Y.Z, got {part}")


def set_json_version(path: Path, version: str, *, lock: bool = False) -> bool:
    """Set the version keeping the file bytes otherwise untouched (no reformatting)."""
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    data = json.loads(text)
    if json.dumps(data, indent=2, ensure_ascii=False) + "\n" == text:
        data["version"] = version
        if lock and isinstance(data.get("packages"), dict) and "" in data["packages"]:
            data["packages"][""]["version"] = version
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    else:
        path.write_text(re.sub(r'("version"\s*:\s*")[^"]+(")', rf"\g<1>{version}\g<2>", text, count=1),
                        encoding="utf-8")
    return True


def cmd_bump(args: argparse.Namespace) -> int:
    name = args.unit
    package = ROOT / "packages" / name
    versions = json.loads(PUBLICATION_VERSIONS.read_text(encoding="utf-8"))
    if name == "planner" or name == "umbrella":
        sys.exit("ERROR: planner follows the umbrella version; bump it with `skiller release` (CHANGELOG heading)")
    if (package / "package.json").is_file():
        current = json.loads((package / "package.json").read_text(encoding="utf-8"))["version"]
        target = next_version(current, args.part)
        touched = [rel for rel, lock in (("package.json", False), ("package-lock.json", True),
                                         (".claude-plugin/plugin.json", False),
                                         (".codex-plugin/plugin.json", False))
                   if set_json_version(package / rel, target, lock=lock)]
        print(f"{name}: {current} -> {target} ({', '.join(touched)})")
    elif name in versions.get("units", {}) or name == "default":
        current = versions["units"][name]
        target = next_version(current, args.part)
        versions["units"][name] = target
        PUBLICATION_VERSIONS.write_text(json.dumps(versions, indent=2, ensure_ascii=False) + "\n",
                                        encoding="utf-8")
        touched = ["packages/skiller/configs/publication-versions.json"]
        static = Path("packages/skiller") / name / ".claude-plugin/plugin.json"  # hand-kept plugin manifest
        if set_json_version(ROOT / static, target):
            touched.append(str(static))
        print(f"{name}: {current} -> {target} ({', '.join(touched)})")
    else:
        sys.exit(f"ERROR: unknown unit {name}")
    print("next: skiller registry, then version-guard.py status")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    status.add_argument("--since", help="baseline tag (default: latest releases/v*.json)")
    status.add_argument("--installed", action="store_true", help="also compare installed Claude Code plugin caches")
    status.add_argument("--all", action="store_true", help="also list already-bumped units")
    status.set_defaults(func=cmd_status)
    bump = sub.add_parser("bump")
    bump.add_argument("unit")
    bump.add_argument("--part", default="patch")
    bump.set_defaults(func=cmd_bump)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
