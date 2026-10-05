"""Portable JSON graph export/import. No source-format conversion belongs in runtime."""
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import shutil
import tempfile

from . import check, store, views
from .model import PlanError

TABLES = {"phase": "phases", "item": "items", "unit": "units", "decision": "decisions", "document": "documents"}


def export(plan: store.Plan) -> dict:
    return {"$schema": "urn:swissknifeman:task:plan:snapshot:v1", "plan": copy.deepcopy(plan.plan),
            "brief": copy.deepcopy(plan.brief),
            **{table: copy.deepcopy(list(getattr(plan, table).values())) for table in TABLES.values()},
            "events": store.read_log(plan.root)}


def _graph(root: Path, value: dict) -> store.Plan:
    store.check_doc(value, "snapshot", "snapshot")
    plan = store.Plan(root=root, plan=copy.deepcopy(value["plan"]), brief=copy.deepcopy(value["brief"]))
    for kind, table in TABLES.items():
        target = getattr(plan, table)
        for doc in value[table]:
            key = f"{doc['item']}/{doc['id']}" if kind == "unit" else doc["id"]
            if key in target:
                raise PlanError("ID_DUPLICATE", f"duplicate {kind} {key}")
            target[key] = copy.deepcopy(doc)
    errors = [i for i in check.check(plan) if i.level == "error"]
    if errors:
        raise PlanError("PLAN_INVALID", "; ".join(f"{i.where}: {i.message}" for i in errors), errors)
    for event in value["events"]:
        if event.get("item") and event["item"] not in plan.items:
            raise PlanError("PLAN_INVALID", f"event references unknown item {event['item']}")
        if event.get("phase") and event["phase"] not in plan.phases:
            raise PlanError("PLAN_INVALID", f"event references unknown phase {event['phase']}")
    return plan


def import_snapshot(root: str | Path, value: dict, *, replace: bool = False) -> store.Plan:
    """Validate and stage a complete current-format snapshot, then publish with rollback.

    Supporting files survive replacement. Historical dates and evidence are copied exactly.
    Existing JSON requires explicit `replace`; non-JSON data is never interpreted.
    """
    root = Path(root).resolve()
    # Validation is read-only and happens before creating even the publication lock.
    proposed = _graph(root, value)
    root.parent.mkdir(parents=True, exist_ok=True)
    with store.PlanLock(root.parent):
        if (root / "plan.json").exists() and not replace:
            raise PlanError("PLAN_EXISTS", f"{root} already has a JSON plan; pass --replace to restore it")
        short_id = proposed.plan["short_id"]
        for candidate in store.plan_dirs(root.parent):
            if short_id is not None and candidate != root and store.short_id_of(candidate) == short_id:
                raise PlanError("PLAN_AMBIGUOUS", f"{short_id} already belongs to {candidate.name}")
        with tempfile.TemporaryDirectory(prefix=".snapshot-", dir=root.parent) as directory:
            staging, backup = Path(directory) / root.name, Path(directory) / "previous"
            if root.exists():
                shutil.copytree(root, staging)
            else:
                staging.mkdir()
            if (root / "plan.json").exists():
                previous = store.load_plan(root)
                for kind, table in TABLES.items():
                    for key in getattr(previous, table):
                        (staging / previous.path(kind, key).relative_to(root)).unlink(missing_ok=True)
            staged = copy.deepcopy(proposed)
            staged.root = staging
            for kind in ("plan", "brief"):
                store.atomic_write(staged.path(kind), store.canonical_dump(getattr(staged, kind), kind))
            for kind, table in TABLES.items():
                for key, doc in getattr(staged, table).items():
                    store.atomic_write(staged.path(kind, key), store.canonical_dump(doc, kind))
            events = "".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in value["events"])
            store.atomic_write(staging / store.LOG, events)
            for name, required in ((".ignore", store.SEARCH_IGNORE), (".cursorignore", store.SEARCH_IGNORE),
                                   (".gitignore", "context/\n.lock\nviews/\n")):
                path = staging / name
                previous = path.read_text(encoding="utf-8") if path.is_file() else ""
                added = [line for line in required.splitlines() if line not in previous.splitlines()]
                updated = previous + ("\n" if previous and not previous.endswith("\n") else "")
                updated += "".join(line + "\n" for line in added)
                store.atomic_write(path, updated)
            views.render_all(staged)
            errors = [i for i in check.check(store.load_plan(staging)) if i.level == "error"]
            if errors:
                raise PlanError("PLAN_INVALID", "; ".join(f"{i.where}: {i.message}" for i in errors), errors)
            moved = False
            try:
                if root.exists():
                    os.replace(root, backup)
                    moved = True
                os.replace(staging, root)
            except BaseException:
                if moved:
                    os.replace(backup, root)
                raise
    return store.load_plan(root)
