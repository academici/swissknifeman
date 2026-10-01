#!/usr/bin/env python3
"""Interplane reconciliation Files: which paths touch items from DIFFERENT plans.

Stage software gate B (see plans/README.md § «Program: stages A–D»).
Surface ownership map derived from phase and row headers Routing, —
guess; the proof gives only the intersection of actual fields `**Files:**`.

A limitation that the tool calls itself: skeleton-item carries `Files: —`,
therefore the non-detailed phase does NOT fall into the intersections and creates a blind
zone. The report always prints how much items passed the check for this
reason to «0 conflicts» could not be read as «no conflicts».

stdlib-only. Usage:
    python3 packages/task/scripts/cross-plan-files.py                # all live plans
    python3 packages/task/scripts/cross-plan-files.py <ID> <ID> ...  # named only
    python3 packages/task/scripts/cross-plan-files.py --strict       # baseline-mode (see below)

`--strict` — baseline/Ratchet mode (payload D, stage audit C F9): full report is printed
always; exit 1 only if among the live intersections there was at least one NOT from
`packages/task/configs/cross-plan-known-intersections.json` (new or unowned). Intersections already captured
in this list (owner+the order is named in the technical specifications of both ends - verified by the audit of the stage C), green
`--strict` does not require them to be closed. Update the list when available/closing the intersection -
manual, with the same commit that changes `Files`.
"""
from __future__ import annotations

import collections
import glob
import importlib
import json
import os
import re
import sys

REPO_ROOT = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
PLANS_DIR = os.path.join(REPO_ROOT, "plans")
SKELETON = "SKELETON — not detailed"
ITEM_RE = re.compile(r"^### (P\d+\.\d+)\s+—", re.M)
BACKTICK_RE = re.compile(r"`([^`]+)`")
# bare paths (FOREMAN writes Files without backticks, through `;`)
BARE_RE = re.compile(r"(?<![`\w/])((?:[\w.-]+/)+[\w.-]+)")
STATUS_RE = re.compile(r"^\|\s*Status\s*\|\s*(\S+)", re.M)
ITEM_STATUS_RE = re.compile(r"^\*\*Status:\*\*\s*(\S+)", re.M)
TERMINAL = ("\U0001f7e2", "\U0001f7e0", "\u26d4")  # Done / Done with deviations / Skipped
KNOWN_INTERSECTIONS_FILE = os.path.join(
    REPO_ROOT, "packages", "task", "configs", "cross-plan-known-intersections.json")
# \u043a\u043e\u0440\u043d\u0435\u0432\u044b\u0435 \u043d\u043e\u0441\u0438\u0442\u0435\u043b\u0438 \u0431\u0435\u0437 "/" \u0432 \u043f\u0443\u0442\u0438 (\u04185) \u2014 \u043c\u0430\u0448\u0438\u043d\u043d\u043e\u043c\u0443 \u0433\u0435\u0439\u0442\u0443 \u0438\u043d\u0430\u0447\u0435 \u043d\u0435\u0432\u0438\u0434\u0438\u043c\u044b, \u0441\u043c. plans/README.md
# \u00a7 \u00ab\u0414\u0438\u0441\u0446\u0438\u043f\u043b\u0438\u043d\u0430 \u0441\u043e\u043f\u0440\u043e\u0432\u043e\u0436\u0434\u0435\u043d\u0438\u044f\u00bb / \u00a7 \u00ab\u0410\u0443\u0434\u0438\u0442 \u044d\u0442\u0430\u043f\u0430 C\u00bb \u04247.
ROOT_VISIBLE_FILES = {"CLAUDE.md", "AGENTS.md", "CHANGELOG.md", "config.json"}


def phase_files(plan_id: str) -> list[str]:
    """Resolve phase carriers through task instead of maintaining two glob layouts."""
    task_lib = os.path.join(REPO_ROOT, "packages", "task", "lib")
    if task_lib not in sys.path:
        sys.path.insert(0, task_lib)
    plan_dir = os.path.join(PLANS_DIR, plan_id)
    try:
        resolver = importlib.import_module("task.plan_layout")
        return [str(path) for path in resolver.phase_paths(plan_dir).values()]
    except (ImportError, ValueError, OSError):
        return []


def live_plans() -> list[str]:
    out = []
    for path in sorted(glob.glob(os.path.join(PLANS_DIR, "*", "plan.md"))):
        plan_id = os.path.basename(os.path.dirname(path))
        if plan_id in ("archive", "tools"):  # tools/ — legacy directory, if left
            continue
        out.append(plan_id)
    return out


def normalize(token: str) -> str | None:
    """Path from cell Files → normalized form, or None if this is not the path."""
    t = token.strip()
    for cut in (" (", " —"):
        if cut in t:
            t = t.split(cut)[0]
    t = t.strip().rstrip("/")
    if t in ROOT_VISIBLE_FILES:
        return t
    if "/" not in t or t.startswith("http") or t.endswith(":"):
        return None
    # cut off the scraps (regex based on the bare text catches tails like "code/hooks/..."):
    # the first segment must exist in the root of the repo
    root = REPO_ROOT
    if not os.path.exists(os.path.join(root, t.split("/")[0])):
        return None
    return t


def plan_status(plan_id: str) -> str:
    text = open(os.path.join(PLANS_DIR, plan_id, "plan.md"), encoding="utf-8").read()
    m = STATUS_RE.search(text)
    return m.group(1) if m else "?"


def collect(plan_id: str):
    """→ (owners: path -> {item}, skeleton_items: int, sized_items: int)"""
    owners: dict[str, set[str]] = collections.defaultdict(set)
    skeleton = sized = 0
    for phase in sorted(phase_files(plan_id)):
        text = open(phase, encoding="utf-8").read()
        is_skeleton = SKELETON in text
        blocks = ITEM_RE.split(text)
        # blocks: [preamble, id, body, id, body, ...]
        for i in range(1, len(blocks), 2):
            item, body = blocks[i], blocks[i + 1]
            files_line = ""
            for line in body.splitlines():
                if line.startswith("**Files:**"):
                    files_line = line
                    break
            raw = BACKTICK_RE.findall(files_line) + BARE_RE.findall(files_line)
            paths = {p for p in (normalize(x) for x in raw) if p}
            # paths within the plan's own directory are not a conflict
            paths = {p for p in paths if not p.startswith(f"plans/{plan_id}/")}
            if not paths and is_skeleton:
                skeleton += 1
                continue
            sized += 1
            st = ITEM_STATUS_RE.search(body)
            closed = bool(st and st.group(1) in TERMINAL)
            tag = f"{plan_id}:{item}" + (" [closed]" if closed else "")
            for p in paths:
                owners[p].add(tag)
    return owners, skeleton, sized


def load_known_intersections() -> set[str]:
    if not os.path.exists(KNOWN_INTERSECTIONS_FILE):
        return set()
    with open(KNOWN_INTERSECTIONS_FILE, encoding="utf-8") as fh:
        data = json.load(fh)
    return set(data["paths"])


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    strict = "--strict" in sys.argv
    plans = args or live_plans()

    all_owners: dict[str, set[str]] = collections.defaultdict(set)
    blind = 0
    statuses = {p: plan_status(p) for p in plans}
    live = {p for p, st in statuses.items() if st not in TERMINAL}
    json_mode = "--json" in sys.argv
    if json_mode:
        for plan_id in plans:
            owners, skeleton, _sized = collect(plan_id)
            blind += skeleton
            for path, items in owners.items():
                all_owners[path] |= items
        shared = {}
        for path, items in all_owners.items():
            open_plans = {i.split(":")[0] for i in items if "[closed]" not in i}
            if len(open_plans & live) > 1:
                shared[path] = sorted(items)
        print(json.dumps({"plans": plans, "shared": shared, "blind_items": blind}, ensure_ascii=False))
        return 0
    print(f"Reconciliation Files by {len(plans)} plans\n")
    for plan_id in plans:
        owners, skeleton, sized = collect(plan_id)
        blind += skeleton
        mark = "alive" if plan_id in live else "TERMINAL (historical)"
        print(f"  {plan_id} [{statuses[plan_id]} {mark}]: items with Files {sized} · skeletons without Files {skeleton} · paths {len(owners)}")
        for path, items in owners.items():
            all_owners[path] |= items

    shared, historical = {}, {}
    for path, items in all_owners.items():
        owners_p = {i.split(":")[0] for i in items}
        if len(owners_p) < 2:
            continue
        # live conflict = OPEN items from ≥2 open plans
        open_plans = {i.split(":")[0] for i in items if "[closed]" not in i}
        if len(open_plans & live) > 1:
            shared[path] = items
        else:
            historical[path] = items
    print(f"\nTotal paths: {len(all_owners)}")
    print(f"LIVE intersections (≥2 open plans): {len(shared)}")
    print(f"historical (intersection with terminal plan only): {len(historical)}")
    if blind:
        print(
            f"BLIND SPOT: {blind} items — skeletons without Files. "
            "An empty intersection list does NOT mean there are no conflicts, "
            "while these items not detailed."
        )
    print()
    for path in sorted(shared):
        print(f"  {path}")
        for item in sorted(shared[path]):
            print(f"      {item}")
    if not shared:
        print("  (no live intersections found)")

    if not strict:
        return 0

    known = load_known_intersections()
    uncovered = {p: items for p, items in shared.items() if p not in known}
    print(f"\n--strict (baseline-mode): known intersections in the list {len(known)}")
    if uncovered:
        print(f"UNCOATED (new/ownerless) intersections: {len(uncovered)}")
        for path in sorted(uncovered):
            print(f"  {path}")
            for item in sorted(uncovered[path]):
                print(f"      {item}")
        return 1
    print("All live intersections are covered with a list of new ones/there are no ownerless ones.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
