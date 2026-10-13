#!/usr/bin/env python3
"""The tests a change needs, and no others: modules touched by the changed paths and the units that depend on them.

    affected-tests.py [--base REF] [--paths P ...] [--tier fast|full|all] [--with-tools] [--run] [-j N] [--json]

Changed paths come from ``git status`` (the working tree), or from ``git diff --name-only REF`` with ``--base``, or from
``--paths``. Each path belongs to the unit whose folder is its longest prefix (``packages/<id>``, ``bridges/<id>``); other
paths belong to the hub. The affected set is the touched units plus the units that require a touched one (a bridge follows
its partners); a change of the foundation (``aicore``) affects every unit. A *tool* (``standalone.tools`` of
``configs/ecosystem-units.json``, e.g. ``maind``) is tested only when its own files changed or ``--with-tools`` is given: it
never joins the tests of the core because a core module changed.

Tiers: ``fast`` runs ``dev.test`` of the affected units (and the cheap hub checks when a hub path changed); ``full`` adds
``dev.validate``; ``all`` is every unit that is not a tool — the full pass for the end of a phase. Without ``--run`` the
commands are only printed (one per line, ``<folder>: <command>``), ``--json`` prints them as a document.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HUB_CHECKS = [["python3", "scripts/ecosystem-units.py", "check"], ["python3", "scripts/public-hygiene.py"]]


def units() -> dict:
    found = {}
    for pattern in ("packages/*/unit.json", "bridges/*/unit.json"):
        for path in sorted(ROOT.glob(pattern)):
            doc = json.loads(path.read_text(encoding="utf-8"))
            found[path.parent.relative_to(ROOT).as_posix()] = doc
    return found


def changed_paths(args) -> list:
    if args.paths:
        return list(args.paths)
    if args.base:
        out = subprocess.run(["git", "diff", "--name-only", args.base], cwd=ROOT, capture_output=True, text=True, check=True).stdout
        return [line for line in out.splitlines() if line]
    out = subprocess.run(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all"], cwd=ROOT, capture_output=True,
                         text=True, check=True).stdout.split("\0")
    paths, index = [], 0
    while index < len(out):
        entry = out[index]
        index += 1
        if not entry:
            continue
        if entry[0] in "RC":
            index += 1
        paths.append(entry[3:])
    return paths


def select(all_units: dict, foundation: str, tools: set, paths: list, tier: str, with_tools: bool) -> tuple:
    """``(folders to test, hub touched)``."""
    ids = {folder: doc.get("id", folder.split("/")[-1]) for folder, doc in all_units.items()}
    by_id = {value: folder for folder, value in ids.items()}
    if tier == "all":
        return sorted(f for f in all_units if f.split("/")[-1] not in tools or with_tools), True
    touched, hub = set(), False
    for path in paths:
        owner = max((f for f in all_units if path == f or path.startswith(f + "/")), key=len, default=None)
        if owner:
            touched.add(owner)
        else:
            hub = True
    chosen = set(touched)
    if any(ids[f] == foundation for f in touched):  # the foundation: everything depends on it
        chosen |= set(all_units)
    changed = True
    while changed:  # whoever requires an affected unit is affected too
        changed = False
        for folder, doc in all_units.items():
            required = {r.get("unit") for r in doc.get("requires") or () if isinstance(r, dict)}
            if folder not in chosen and any(by_id.get(r) in chosen for r in required):
                chosen.add(folder)
                changed = True
    kept = {f for f in chosen if f.split("/")[-1] not in tools or f in touched or with_tools}
    return sorted(kept), hub


def commands(all_units: dict, folders: list, hub: bool, tier: str) -> list:
    plan = []
    for folder in folders:
        dev = all_units[folder].get("dev") or {}
        names = ("test",) if tier == "fast" else ("test", "validate")
        plan += [(folder, dev[name]) for name in names if dev.get(name)]
    if hub or tier == "all":
        plan += [("hub", argv) for argv in HUB_CHECKS]
    return plan


def bridge_env() -> dict:
    """The partners a bridge finds through the environment, wired from the hub layout (as scripts/test-bridges.sh does)."""
    env = dict(os.environ)
    packages = ROOT / "packages"
    env.update({"PLANNER_ROOT": str(packages / "planner"), "PLANNER_PLAN_PY": str(packages / "planner/scripts/plan.py"),
                "SKM_ORCH_ROOT": str(packages / "orch"), "SKM_SKILLER_ROOT": str(packages / "skiller"),
                "SKM_HARNESS_ROOT": str(packages / "harness"), "AICORE_ROOT": str(packages / "aicore")})
    return env


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base")
    parser.add_argument("--paths", nargs="*")
    parser.add_argument("--tier", choices=["fast", "full", "all"], default="fast")
    parser.add_argument("--with-tools", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("-j", "--jobs", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    config = json.loads((ROOT / "configs" / "ecosystem-units.json").read_text(encoding="utf-8"))
    tools = set((config.get("standalone") or {}).get("tools") or ())
    all_units = units()
    folders, hub = select(all_units, (config.get("foundation") or {}).get("id", "aicore"), tools,
                          [] if args.tier == "all" else changed_paths(args), args.tier, args.with_tools)
    plan = commands(all_units, folders, hub, args.tier)
    if args.json:
        print(json.dumps({"tier": args.tier, "units": folders, "hub": hub,
                          "commands": [{"folder": f, "argv": a} for f, a in plan]}, indent=2))
    else:
        for folder, command in plan:
            print(f"{folder}: {' '.join(command)}")
    if not args.run:
        return 0

    def run(item):
        folder, command = item
        cwd = ROOT if folder == "hub" else ROOT / folder
        done = subprocess.run(command, cwd=cwd, capture_output=True, text=True,
                              env=bridge_env() if folder.startswith("bridges/") else dict(os.environ))
        return folder, command, done

    failed = 0
    with ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for folder, command, done in pool.map(run, plan):
            state = "ok" if done.returncode == 0 else "FAIL"
            print(f"[{state}] {folder}: {' '.join(command)}", flush=True)
            if done.returncode:
                failed += 1
                sys.stderr.write((done.stdout + done.stderr)[-3000:])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
