#!/usr/bin/env python3
"""Pre-release check: every version surface of the repository agrees before a tag is made.

  release-check.py vX.Y.Z [--fix] [--full]

Checks (exit 1 on any finding):
  - the top released CHANGELOG heading is X.Y.Z and `[Unreleased]` is empty;
  - `version-guard.py status` reports no unit that changed without a bump;
  - per package: `unit.json` = `package.json` = the plugin manifests (`.claude-plugin`, `.codex-plugin`);
  - `planner` (follows the umbrella): its unit, manifests, golden fixtures, grok lock and
    `configs/command-routing.json` carry X.Y.Z;
  - `lib/<id>/__init__.py` `__version__` = `unit.json`; planner projections are rendered (`render-provider-commands.py`);
  - the version table of `docs/architecture/ownership.md` matches `unit.json`;
  - `releases/vX.Y.Z.json` exists (`skiller attest`);
  - `skiller registry` changes nothing that is not already in the working tree.
--fix writes the mechanical surfaces (unit.json, planner surfaces, ownership table) and re-checks.
--full also runs `affected-tests.py --tier all --run`.
Nothing here creates or pushes a tag.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")
PLANNER = "packages/planner"
PLANNER_SURFACES = (
    "unit.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json",
    "tests/fixtures_data/claude-command-golden/plugin.json",
    "adapters/grok/publication-lock.json",
)
OWNERSHIP = "docs/architecture/ownership.md"


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def set_version(path: Path, key: str, value: str) -> bool:
    """Replace the first top-level `"key": "..."` textually, keeping the file's formatting."""
    text = path.read_text(encoding="utf-8")
    new, count = re.subn(rf'("{key}"\s*:\s*")[^"]*(")', rf"\g<1>{value}\g<2>", text, count=1)
    if count and new != text:
        path.write_text(new, encoding="utf-8")
        return True
    return False


def run(*argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(argv, cwd=ROOT, capture_output=True, text=True, timeout=1800)  # noqa: S603


def changelog(version: str) -> list[str]:
    text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    found = []
    headings = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", text, re.M)
    if not headings or headings[0] != version:
        found.append(f"CHANGELOG top released heading is {headings[0] if headings else 'missing'}, expected {version}")
    unreleased = re.search(r"^## \[Unreleased\]\s*\n(.*?)(?=^## \[)", text, re.M | re.S)
    if unreleased and unreleased.group(1).strip():
        found.append("CHANGELOG [Unreleased] is not empty: it is not part of the release")
    return found


def packages() -> list[Path]:
    return sorted(path.parent for path in (ROOT / "packages").glob("*/unit.json"))


def module_surfaces(fix: bool) -> list[str]:
    found = []
    for folder in packages():
        name = folder.name
        if name == "planner" or not (folder / "package.json").is_file():
            continue
        wanted = read_json(folder / "package.json").get("version")
        for relative in ("unit.json", ".claude-plugin/plugin.json", ".codex-plugin/plugin.json"):
            path = folder / relative
            if path.is_file() and read_json(path).get("version") != wanted:
                if fix and set_version(path, "version", wanted):
                    continue
                found.append(f"{path.relative_to(ROOT)}: {read_json(path).get('version')} != package.json {wanted}")
    return found


def library_versions(fix: bool) -> list[str]:
    """`__version__` of `lib/<id>/__init__.py` follows `unit.json`."""
    found = []
    for folder in packages():
        init = folder / "lib" / folder.name / "__init__.py"
        if not init.is_file() or "__version__" not in init.read_text(encoding="utf-8"):
            continue
        wanted = read_json(folder / "unit.json")["version"]
        text = init.read_text(encoding="utf-8")
        have = re.search(r'^__version__\s*=\s*"([^"]*)"', text, re.M)
        if have and have.group(1) != wanted:
            if fix:
                init.write_text(re.sub(r'^(__version__\s*=\s*")[^"]*(")', rf"\g<1>{wanted}\g<2>", text, count=1, flags=re.M),
                                encoding="utf-8")
            else:
                found.append(f"{init.relative_to(ROOT)}: {have.group(1)} != unit.json {wanted}")
    return found


def planner_projections(fix: bool) -> list[str]:
    """Planner command projections (command-routing, provider commands) are rendered, never hand-edited."""
    argv = [sys.executable, f"{PLANNER}/scripts/render-provider-commands.py", "--root", "."]
    done = run(*argv, "--write", "--repair-owned") if fix else run(*argv, "--check")
    return [] if done.returncode == 0 else ["planner projections diverged: " + (done.stdout + done.stderr).strip()[-300:]]


def planner_surfaces(version: str, fix: bool) -> list[str]:
    found = []
    for relative in PLANNER_SURFACES:
        path = ROOT / PLANNER / relative
        if path.is_file() and read_json(path).get("version") != version:
            if fix and set_version(path, "version", version):
                continue
            found.append(f"{path.relative_to(ROOT)}: {read_json(path).get('version')} != {version}")
    routing = ROOT / PLANNER / "configs/command-routing.json"
    if read_json(routing).get("plugin_version") != version:
        found.append(f"{routing.relative_to(ROOT)}: plugin_version != {version} (run `skiller release`)")
    return found


def ownership(fix: bool) -> list[str]:
    path = ROOT / OWNERSHIP
    text = path.read_text(encoding="utf-8")
    found = []
    for folder in [*packages(), *sorted((ROOT / "bridges").glob("*/unit.json"))]:
        folder = folder.parent if folder.name == "unit.json" else folder
        unit = read_json(folder / "unit.json")
        row = re.compile(rf"^(\| {re.escape(unit['id'])} \| [a-z]+ \| )(\S+)( \|)", re.M)
        match = row.search(text)
        if match and match.group(2) != unit["version"]:
            if fix:
                text = row.sub(rf"\g<1>{unit['version']}\g<3>", text, count=1)
            else:
                found.append(f"{OWNERSHIP}: {unit['id']} {match.group(2)} != unit.json {unit['version']}")
    if fix:
        path.write_text(text, encoding="utf-8")
    return found


def registry_drift() -> list[str]:
    def state() -> str:
        return hashlib.sha256((run("git", "status", "--short").stdout + run("git", "diff").stdout).encode()).hexdigest()

    before = state()
    done = run("skiller", "registry")
    if done.returncode:
        return [f"skiller registry failed: {(done.stderr or done.stdout).strip()[-300:]}"]
    return [] if state() == before else ["skiller registry changed files: commit them with the release"]


def check(version: str, fix: bool) -> list[str]:
    bare = version.lstrip("v")
    found = changelog(bare)
    found += module_surfaces(fix) + library_versions(fix) + planner_surfaces(bare, fix) + planner_projections(fix) + ownership(fix)
    if not (ROOT / "releases" / f"v{bare}.json").is_file():
        found.append(f"releases/v{bare}.json is missing: run `skiller attest --release v{bare} --previous <tag>`")
    guard = run(sys.executable, "scripts/version-guard.py", "status")
    if guard.returncode:
        found.append("version-guard: " + " | ".join(line.strip() for line in guard.stdout.splitlines()
                                                   if "NOT-BUMPED" in line))
    for label, argv in (("ecosystem-units", ("scripts/ecosystem-units.py", "check")), ("golden", ("scripts/golden.py", "check"))):
        done = run(sys.executable, *argv)
        if done.returncode:
            found.append(f"{label}: " + " | ".join((done.stdout + done.stderr).strip().splitlines()[-4:])
                         + " (dependency ranges `^0.N` of bridges follow the minor of the module; "
                           "`golden.py capture --only <generator> --reason ...` after a version change)")
    return found + registry_drift()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("version", help="vX.Y.Z of the release")
    parser.add_argument("--fix", action="store_true", help="write the mechanical version surfaces first")
    parser.add_argument("--full", action="store_true", help="also run affected-tests --tier all --run")
    args = parser.parse_args()
    if not SEMVER.match(args.version.lstrip("v")):
        parser.error("version must look like vX.Y.Z")
    found = check(args.version, args.fix)
    for line in found:
        print(f"FAIL {line}")
    if not found and args.full:
        done = subprocess.run([sys.executable, "scripts/affected-tests.py", "--tier", "all", "--run"], cwd=ROOT)  # noqa: S603
        if done.returncode:
            return 1
    print("release-check: " + (f"{len(found)} finding(s)" if found else "ok"))
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
