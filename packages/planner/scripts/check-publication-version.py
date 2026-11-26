#!/usr/bin/env python3
"""Fail closed when planner publication version drifts from umbrella + manifests."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main() -> int:
    root = Path(sys.argv[1]).resolve()
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    headings = re.findall(r"^## \[(\d+\.\d+\.\d+)\]", changelog, re.M)
    if not headings:
        print("FAIL: CHANGELOG has no released umbrella version", file=sys.stderr)
        return 1
    umbrella = headings[0]
    policy = json.loads((root / "configs/release-units.json").read_text(encoding="utf-8"))
    planner_rule = policy.get("plugins", {}).get("planner", {})
    if planner_rule.get("version_owner") != "umbrella":
        print("FAIL: planner version_owner must be umbrella", file=sys.stderr)
        return 1
    routing = json.loads(
        (root / "packages/planner/configs/command-routing.json").read_text(encoding="utf-8"))
    plugin_version = routing.get("plugin_version")
    errors: list[str] = []
    if plugin_version != umbrella:
        errors.append(
            f"command-routing plugin_version={plugin_version} != umbrella {umbrella}")
    for rel in (
        "packages/planner/.codex-plugin/plugin.json",
        "packages/planner/.claude-plugin/plugin.json",
    ):
        manifest = json.loads((root / rel).read_text(encoding="utf-8"))
        if manifest.get("version") != umbrella:
            errors.append(f"{rel} version={manifest.get('version')} != umbrella {umbrella}")
    for line in errors:
        print("FAIL:", line, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
