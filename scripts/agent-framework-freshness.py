#!/usr/bin/env python3
"""Framework canon freshness: Skiller's «pack → version» table vs Harness pack.json.

`packages/skiller/docs/agent-framework/framework-overview.md` is declared as the INPUT
of the next framework-audit — and was already 36 days behind the tree once: the auditor
received seven «🔜 in progress» with the finished implementation and in good faith
offered to build an already standing (docs/audits/2026-07-29-harness-agnostic — meta
find). A manual «update review» reminder did not catch this class of failure, so the
freshness of the input is kept by the machine. Same class as the registry drift gate:
neither network nor git history nor calendar thresholds — reconciliation of ANNOUNCED
versions with the `pack.json` of each pack.

Cross-package check, so it lives at the repository root (moved from Skiller's
validate.sh; algorithm and messages unchanged). Usage:
  python3 scripts/agent-framework-freshness.py [--overview FILE] [--packs DIR]
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERVIEW = ROOT / "packages/skiller/docs/agent-framework/framework-overview.md"
PACKS_DIR = ROOT / "packages/harness/configs/claude-code/agent-packs"

# Anchor format closed: header «| Pack | Version |», delimiter, lines
# «| <pack> | <x.y.z> |». There are no heuristics - what doesn’t fit into the form, then ERROR with fix.
HEADER = re.compile(r"^\|\s*Pack\s*\|\s*Version\s*\|\s*$")
SEP = re.compile(r"^\|[\s:|-]+\|\s*$")
ROW = re.compile(r"^\|\s*([A-Za-z0-9_][A-Za-z0-9_.-]*)\s*\|\s*(\d+\.\d+\.\d+)\s*\|\s*$")


def check(overview, packs_dir):
    """Return (errors, note). `note` is the skip/OK line; errors fail the gate."""
    if packs_dir is None or not Path(packs_dir).is_dir():
        return [], ("framework canon: packages/harness/configs/claude-code/agent-packs not found "
                    "(standalone-layout) — freshness gate missed")
    if not Path(overview).is_file():
        return [], ("framework canon: docs/agent-framework/framework-overview.md no - "
                    "freshness gate missed")

    errors = []
    declared = {}
    in_table = False
    for ln, line in enumerate(Path(overview).read_text(encoding="utf-8").splitlines(), 1):
        if HEADER.match(line):
            in_table = True
            continue
        if not in_table:
            continue
        if SEP.match(line):
            continue
        if not line.startswith("|"):
            in_table = False
            continue
        m = ROW.match(line)
        if not m:
            errors.append(f"docs/agent-framework/framework-overview.md:{ln}: table row "
                          f"«pack → version» not in format `| <pack> | <x.y.z> |`: {line.strip()}")
            continue
        declared[m.group(1)] = m.group(2)

    if not declared and not errors:
        errors.append("docs/agent-framework/framework-overview.md: no table «pack → version» "
                      "(header `| Pack | Version |`) — she is the machine anchor of the freshness gate")

    actual = {}
    for pj in sorted(Path(packs_dir).glob("*/pack.json")):
        name = pj.parent.name
        try:
            data = json.loads(pj.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            errors.append(f"agent-packs/{name}/pack.json: invalid JSON: {e}")
            continue
        version = data.get("version")
        if not isinstance(version, str):
            errors.append(f"agent-packs/{name}/pack.json: no string field version")
            continue
        actual[name] = version

    for name in sorted(actual):
        if name not in declared:
            errors.append(f"pack `{name}` is not declared in canon - update the table in "
                          f"`framework-overview.md`: `{name}` `{actual[name]}`")
        elif declared[name] != actual[name]:
            errors.append(f"pack `{name}`: canon announces `{declared[name]}`, pack.json carries "
                          f"`{actual[name]}` — update the table in `framework-overview.md`: "
                          f"`{name}` `{actual[name]}`")
    for name in sorted(declared):
        if name not in actual:
            errors.append(f"string `{name}` is superfluous in canon (pack is not in "
                          f"packages/harness/configs/claude-code/agent-packs) — remove line from "
                          f"tables in `framework-overview.md`")
    return errors, f"framework canon: table «pack → version» matches pack.json ({len(actual)} packs)"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--overview", type=Path, default=OVERVIEW)
    parser.add_argument("--packs", type=Path, default=PACKS_DIR)
    args = parser.parse_args(argv)
    errors, note = check(args.overview, args.packs)
    if errors:
        print(f"ERROR: frame canon has fallen behind the tree ({len(errors)}) — "
              f"`framework-overview.md` is declared as the input of the following audit:", file=sys.stderr)
        for e in errors:
            print("  " + e, file=sys.stderr)
        return 1
    print(note)
    return 0


if __name__ == "__main__":
    sys.exit(main())
