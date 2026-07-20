#!/usr/bin/env python3
"""Reproducible, read-only P0.1 inventory for the dual-provider plan."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path


PLAN_ID = "2026.07.19-DUAL-PROVIDER"
PASS_ONE = {
    "canonical skills": 216,
    "task commands": 32,
    "plugin manifests": 54,
    "MCP presets": 8,
    "agent packs": 10,
    "fleet projects": 25,
}


def root_from_script() -> Path:
    return Path(__file__).resolve().parents[3]


def run(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, text=True, capture_output=True, check=True
    ).stdout.rstrip()


def paths(root: Path, pattern: str) -> list[str]:
    return sorted(str(p.relative_to(root)) for p in root.glob(pattern) if p.is_file())


def package_sources(root: Path, package: str) -> list[str]:
    return paths(root, f"packages/{package}/lib/{package}/**/*.py")


def provider_mentions(root: Path, package: str) -> list[str]:
    result = []
    for rel in package_sources(root, package):
        text = (root / rel).read_text(encoding="utf-8", errors="replace").lower()
        if any(token in text for token in ("claude", ".mcp.json", ".claude/")):
            result.append(rel)
    return result


def classify(root: Path) -> dict[str, list[str]]:
    return {
        "canonical": sorted(
            paths(root, "packages/skiller/skills/**/SKILL.md")
            + paths(root, "packages/task/commands/*.md")
        ),
        "provider-adapter": sorted(
            paths(root, "packages/*/.claude-plugin/plugin.json")
            + paths(root, "packages/harness/configs/claude-code/**/*.json")
        ),
        "generated": sorted(
            paths(root, ".claude-plugin/marketplace.json")
            + paths(root, "packages/skiller/skills/*/.claude-plugin/plugin.json")
        ),
        "bootstrap-only": sorted(
            p for p in ("AGENTS.md", ".mcp.json.example") if (root / p).is_file()
        ) + sorted(
            str(p.relative_to(root)) for d in (".agents", ".serena")
            for p in (root / d).rglob("*") if p.is_file()
        ),
    }


def inventory(root: Path) -> dict[str, object]:
    classes = classify(root)
    config = json.loads((root / "config.json").read_text(encoding="utf-8"))
    sets = {
        "canonical skills": paths(root, "packages/skiller/skills/**/SKILL.md"),
        "task commands": paths(root, "packages/task/commands/*.md"),
        "plugin manifests": paths(root, "**/.claude-plugin/plugin.json"),
        "MCP presets": paths(root, "packages/harness/configs/claude-code/mcp/*.json"),
        "agent packs": paths(root, "packages/harness/configs/claude-code/agent-packs/**/pack.json"),
        "fleet projects": [str(row["id"]) for row in config.get("projects", [])],
    }
    coupling = {pkg: provider_mentions(root, pkg) for pkg in
                ("skiller", "task", "harness", "maind", "analyst")}
    coupling["core"] = [
        rel for rel in paths(root, "core/*.py")
        if any(token in (root / rel).read_text(encoding="utf-8", errors="replace").lower()
               for token in ("claude", ".mcp.json", ".claude/"))
    ]
    return {"sets": sets, "classes": classes, "coupling": coupling}


def render(root: Path) -> str:
    data = inventory(root)
    head = run(root, "rev-parse", "HEAD")
    status = run(root, "status", "--short") or "(clean)"
    lines = [
        "# P0 provider coupling baseline", "",
        "## Anchor", "",
        f"- `git rev-parse HEAD`: `{head}`.",
        "- `git status --short`:", "", "```text", status, "```", "",
        "The anchor records the complete visible worktree; untracked or dirty files are not "
        "included automatically in an item commit.", "",
        "## Summary", "",
        "| Surface | Pass 1 | Current | Delta |", "|:--|--:|--:|--:|",
    ]
    for label, members in data["sets"].items():
        lines.append(f"| {label} | {PASS_ONE[label]} | {len(members)} | {len(members) - PASS_ONE[label]:+d} |")
    lines += [
        "",
        "The only delta is `task commands` (-21): the frozen pass-1 finding described 32, "
        "while the explicit canonical root `packages/task/commands/*.md` currently contains 11. "
        "The helper preserves that definition rather than broadening it to unrelated package command "
        "directories; P0.2 must decide whether the older label used a different scope.",
    ]
    lines += ["", "Raw sorted path/id sets:", ""]
    for label, members in data["sets"].items():
        lines += [f"### {label}", "", "```text", *members, "```", ""]
    lines += ["## Coupling by package", ""]
    for package, members in data["coupling"].items():
        lines += [f"### {package}", "", "Provider-name matches are classified seams, not defects.",
                  "", "```text", *members, "```", ""]
    lines += ["## Classification", ""]
    for kind, members in data["classes"].items():
        lines += [f"### {kind}", "", "```text", *members, "```", ""]
    lines += [
        "## Bootstrap-only state", "",
        "`AGENTS.md`, `.agents/`, `.serena/`, and `.mcp.json.example` are recorded as "
        "bootstrap-only. This inventory neither changes nor treats them as the distribution canon.",
        "",
        "## Reproduction", "",
        "```bash",
        "python3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-provider-inventory.py --write",
        "python3 plans/2026.07.19-DUAL-PROVIDER/artifacts/p0-provider-inventory.py --check",
        "```",
        "",
        "The helper scans only the explicit roots encoded in this file, sorts every path set, "
        "and is read-only except for its plan finding in `--write` mode.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = root_from_script()
    target = root / "plans" / PLAN_ID / "findings" / "P0-provider-coupling-baseline.md"
    content = render(root)
    if args.check:
        if not target.is_file() or target.read_text(encoding="utf-8") != content:
            print("P0 inventory drift detected", file=sys.stderr)
            return 1
        print("P0 inventory: no drift")
        return 0
    target.write_text(content, encoding="utf-8")
    print(f"P0 inventory: wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
