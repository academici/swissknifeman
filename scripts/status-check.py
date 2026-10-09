#!/usr/bin/env python3
"""Verification docs/status.md: maturity from dictionary, non-empty Evidence, known package, no duplicates.

Layer-by-layer revalidation (P8.5): reads ONE file docs/status.md + os.path.isdir by named
packages; bypass docs/**, parsing VitePress-config and launch CLI packages are not produced.
"""
import os
import re
import sys

# Conscious vocabulary double - keep in sync with plan-protocol § Statuses
# (packages/skiller/skills/general/plan-protocol/SKILL.md), sample discipline - validate.sh
# vs core.project.PROJECT_TYPES.
MATURITY_VALUES = {"available", "experimental", "behind-gate", "disabled", "superseded"}

# Package name in matrix -> directory whose existence is checked against the repo root.
PACKAGE_DIRS = {
    "swissknifeman (router)": ".",
    "skiller": "packages/skiller",
    "harness": "packages/harness",
    "maind": "packages/maind",
    "analyst": "packages/analyst",
    "planner": "packages/planner",
    "core": "core",
    "aicore": "packages/aicore",
}

ROW_RE = re.compile(r"^\|(.+)\|$")


def parse_rows(text):
    rows = []
    in_matrix = False
    for lineno, line in enumerate(text.splitlines(), start=1):
        if line.strip() == "## Matrix":
            in_matrix = True
            continue
        if in_matrix and line.startswith("## "):
            break
        if not in_matrix:
            continue
        m = ROW_RE.match(line.rstrip())
        if not m:
            continue
        cells = [c.strip() for c in m.group(1).split("|")]
        if len(cells) != 4:
            continue
        if cells[0] == "Package":
            continue
        if set(cells[0]) <= {"-", ":"}:
            continue
        rows.append((lineno, *cells))
    return rows


def check(path, repo_root):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    rows = parse_rows(text)
    errors = []
    seen = set()
    for lineno, package, capability, maturity, evidence in rows:
        if maturity not in MATURITY_VALUES:
            errors.append(f"string {lineno}: «Maturity» = «{maturity}» not from the dictionary")
        if not evidence:
            errors.append(f"string {lineno}: Evidence empty")
        pkg_dir = PACKAGE_DIRS.get(package)
        if pkg_dir is None:
            errors.append(f"string {lineno}: package «{package}» unknown")
        elif not os.path.isdir(os.path.join(repo_root, pkg_dir)):
            errors.append(f"string {lineno}: package directory «{package}» not found")
        key = (package, capability)
        if key in seen:
            errors.append(f"string {lineno}: take ({package}, {capability})")
        seen.add(key)
    return rows, errors


def main(argv):
    if len(argv) != 2:
        print("usage: status-check.py <path/to/status.md>", file=sys.stderr)
        return 2
    path = argv[1]
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rows, errors = check(path, repo_root)
    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print(f"status-check: {len(rows)} lines(and), 0 errors")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
