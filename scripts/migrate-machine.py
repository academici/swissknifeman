#!/usr/bin/env python3
"""One-off machine step of UPGRADE.md: the legacy hub node file -> [maind] settings + registry.json.

  migrate-machine.py [--apply]

Reads config.json at the hub root (the legacy node file). Dry-run prints what moves. With --apply writes the
settings the schema knows into the machine config file ([maind]) and the registry into
<state>/maind/registry.json (both with the usual backups); the legacy file is left in place for the person to delete.
Also copies safe-dirs.json into <config>/harness/. Run once per computer, after install.sh.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for unit in ("aicore", "maind"):
    sys.path.insert(0, str(ROOT / "packages" / unit / "lib"))

from aicore.state import machine_locations  # noqa: E402
from maind import config as mc  # noqa: E402
from maind.common import Env  # noqa: E402
from maind.projects import write_registry  # noqa: E402


def flatten(tree: dict, prefix: str = "") -> dict:
    out = {}
    for key, value in tree.items():
        dotted = f"{prefix}{key}"
        if isinstance(value, dict) and value:
            out.update(flatten(value, dotted + "."))
        else:
            out[dotted] = value
    return out


def main(argv: list[str]) -> int:
    apply = "--apply" in argv
    legacy = ROOT / "config.json"
    if not legacy.is_file():
        print("no config.json at the hub root: nothing to migrate")
        return 0
    doc = json.loads(legacy.read_text(encoding="utf-8"))
    env = Env(str(ROOT), "migrate")
    settings = flatten(mc._prune(mc.settings_schema(), mc._normalize_legacy_settings(doc)))
    registry = mc.registry_of(doc)
    print(f"settings: {len(settings)} key(s) -> [maind]; registry keys: {sorted(registry)}; projects: {len(doc.get('projects', []))}")
    safe = ROOT / "safe-dirs.json"
    target = machine_locations().config / "harness" / "safe-dirs.json"
    print(f"safe-dirs: {safe} -> {target}" if safe.is_file() else "safe-dirs: none")
    if not apply:
        print("dry-run: add --apply")
        return 0
    mc.write_settings(env, settings)
    print("registry:", write_registry(env, doc, new_file=True))
    if safe.is_file() and not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(safe, target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
