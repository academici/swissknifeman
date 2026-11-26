#!/usr/bin/env python3
"""Mechanical project steps of UPGRADE.md (4-7): config move, plugin rename, leftovers.

  upgrade-project.py PROJECT [--apply]

Without --apply it only prints what would change. Moves `.swissknife.json` providers and the
`.claude/*.env.ini` hook modes into `.swissknifeman/config.toml`, renames the `task` plugin to `planner`
in `.claude/settings*.json`, and removes `*.bak` files under `.claude/` plus `CLAUDE.md.bak`. Keeps
`review-gate.env.ini` (the hook still reads REVIEW_GATE_CMD from it). Run `harness hooks sync` afterwards.
Checks that need judgement (docs that mention `/task:`) are only listed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# env.ini file -> (config section, {INI key: config key})
HOOKS = {
    "auto-approve": ("harness.hooks.auto_approve", {"MODE": "mode"}),
    "memory": ("harness.hooks.memory", {"MODE": "mode"}),
    "review-gate": ("harness.hooks.review_gate", {"REVIEW_GATE_MODE": "mode"}),
    "agent-router": ("harness.hooks.agent_router", {"POLICY": "policy"}),
    "run-report": ("harness.hooks.run_report", {"ENABLED": "enabled", "RUNS_KEEP": "runs_keep"}),
}
DELETE_INI = {"auto-approve", "memory", "agent-router", "run-report"}


def read_ini(path: Path) -> dict[str, str]:
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith(("#", ";")) and "=" in line:
            key, _, value = line.partition("=")
            rows[key.strip()] = value.strip().strip('"')
    return rows


def toml_value(value: str) -> str:
    return value if value.isdigit() else json.dumps(value)


def wanted_sections(root: Path) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    legacy = root / ".swissknife.json"
    if legacy.is_file():
        selection = json.loads(legacy.read_text()).get("providers", {}).get("selection", {})
        for name, row in selection.items():
            sections[f"aicore.providers.selection.{name}"] = {"enabled": "true" if row.get("enabled", True) else "false"}
    for stem, (section, keys) in HOOKS.items():
        ini = root / ".claude" / f"{stem}.env.ini"
        if ini.is_file():
            values = read_ini(ini)
            row = {keys[k]: toml_value(v) for k, v in values.items() if k in keys}
            if row:
                sections[section] = row
    return sections


def merge_config(root: Path, apply: bool) -> None:
    target = root / ".swissknifeman" / "config.toml"
    text = target.read_text(encoding="utf-8") if target.is_file() else "schema_version = 1\n"
    additions = []
    for section, row in wanted_sections(root).items():
        if re.search(rf"^\[{re.escape(section)}\]", text, re.M):
            continue  # the section exists: judgement stays with the person
        body = "\n".join(f"{k} = {v if v in ('true', 'false') or v.isdigit() or v.startswith(chr(34)) else json.dumps(v)}"
                         for k, v in row.items())
        additions.append(f"\n[{section}]\n{body}\n")
    print(f"config.toml: {len(additions)} section(s) to add")
    if additions and apply:
        target.parent.mkdir(exist_ok=True)
        target.write_text(text.rstrip("\n") + "\n" + "".join(additions), encoding="utf-8")


def rename_plugin(root: Path, apply: bool) -> None:
    for path in sorted((root / ".claude").glob("settings*.json")):
        text = path.read_text(encoding="utf-8")
        new = text.replace('"task@swissknifeman"', '"planner@swissknifeman"')
        if new != text:
            print(f"{path.relative_to(root)}: task -> planner")
            if apply:
                path.write_text(new, encoding="utf-8")


def remove_leftovers(root: Path, apply: bool) -> None:
    doomed = [root / ".swissknife.json", root / "CLAUDE.md.bak"]
    doomed += sorted((root / ".claude").rglob("*.bak"))
    doomed += [root / ".claude" / f"{stem}.env.ini" for stem in DELETE_INI]
    for path in doomed:
        if path.is_file() or path.is_symlink():
            print(f"remove {path.relative_to(root)}")
            if apply:
                path.unlink()


def list_mentions(root: Path) -> None:
    pattern = re.compile(r"/task:|packages/task\b|task@swissknifeman")
    skip = {"vendor", "node_modules", ".git", "plans", "releases", ".agents", ".swissknifeman"}
    for path in root.rglob("*"):
        if skip & set(path.relative_to(root).parts) or not path.is_file() or path.suffix not in (".md", ".json", ".sh"):
            continue
        try:
            if pattern.search(path.read_text(encoding="utf-8")):
                print(f"mentions task: {path.relative_to(root)}")
        except (OSError, UnicodeDecodeError):
            continue


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    root, apply = Path(args[0]).resolve(), "--apply" in argv
    merge_config(root, apply)
    rename_plugin(root, apply)
    remove_leftovers(root, apply)
    list_mentions(root)
    print("applied" if apply else "dry-run: nothing changed; add --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
