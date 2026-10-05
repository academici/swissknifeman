#!/usr/bin/env python3
"""Temporary config-driven migration inventory and guarded cleanup."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1] / "lib"))
from task.plan import check, store, views

MANIFEST = HERE / "inventory.json"
DONE = {"migrated", "already_current"}


def project_path(config: Path, record: dict) -> Path:
    raw = os.path.expanduser(record["local_path"])
    path = Path(raw)
    return (path if path.is_absolute() else config.parent / path).resolve()


def active_plans(root: Path) -> list[Path]:
    plans = root / "plans"
    if not plans.is_dir():
        return []
    return sorted(path for path in plans.iterdir()
                  if path.is_dir() and path.name != "archive" and not path.name.startswith(".")
                  and ((path / "plan.json").is_file() or (path / "plan.md").is_file()))


def verify(root: Path) -> None:
    plan = store.load_plan(root)
    errors = [issue for issue in check.check(plan) if issue.level == "error"]
    if errors:
        raise ValueError(errors)
    if views.render_all(plan, check=True):
        raise ValueError(f"{root.name}: human views are stale")
    names = ("index.md", "plan.md", "roadmap.md", "status.md", "handoff.md", "open-questions.md",
             "session-routing.md", "journal.jsonl", "AGENTS.md", "CLAUDE.md")
    carriers = [root / name for name in names]
    for folder in ("phases", "brief", "decisions"):
        carriers += list((root / folder).glob("**/*.md"))
    if any(path.exists() for path in carriers):
        raise ValueError(f"{root.name}: old active carriers still exist")
    for name in (".ignore", ".cursorignore"):
        text = (root / name).read_text(encoding="utf-8") if (root / name).is_file() else ""
        if "*.md" not in text.splitlines():
            raise ValueError(f"{root.name}: {name} does not exclude generated Markdown")


def _old_status(old: dict, name: str, root: Path, plan: str, unique: dict[str, int]) -> str | None:
    candidates = [entry for entry in old.get("plans", []) if entry.get("plan") == plan]
    exact = [entry for entry in candidates if entry.get("project") == name
             or Path(str(entry.get("project", ""))).name.casefold() == root.name.casefold()
             or entry.get("local_path") == str(root)]
    selected = exact[0] if exact else (candidates[0] if unique.get(plan) == 1 and len(candidates) == 1 else None)
    status = selected.get("status") if selected else None
    return "already_current" if status == "done" else status


def scan(config: Path, old: dict) -> dict:
    config = config.resolve()
    records = json.loads(config.read_text(encoding="utf-8")).get("projects", [])
    discovered: list[tuple[dict, Path, list[Path]]] = []
    counts: dict[str, int] = {}
    for record in records:
        root = project_path(config, record)
        found = active_plans(root) if root.is_dir() else []
        discovered.append((record, root, found))
        for plan in found:
            counts[plan.name] = counts.get(plan.name, 0) + 1

    projects, plans, current_keys = [], [], set()
    for index, (record, root, found) in enumerate(discovered, 1):
        name = record.get("name") or record.get("id") or f"project-{index}"
        if not root.is_dir():
            projects.append({"name": name, "local_path": record["local_path"], "resolved_path": str(root),
                             "status": "unavailable", "active_plans": 0})
            continue
        statuses = []
        for plan in found:
            fmt = "json" if (plan / "plan.json").is_file() else "markdown"
            status = _old_status(old, name, root, plan.name, counts)
            if fmt == "json":
                try:
                    verify(plan)
                except Exception:
                    status = "unresolved"
                else:
                    status = status if status in DONE else "already_current"
            else:
                status = status if status == "migrated" else "pending"
            plans.append({"project": name, "local_path": str(root), "plan": plan.name, "path": str(plan),
                          "format": fmt, "scope": "config", "status": status})
            statuses.append(status)
            current_keys.add((name, plan.name))
        if not found:
            project_status = "no_active_plans"
        elif any(status == "unresolved" for status in statuses):
            project_status = "unresolved"
        elif any(status == "pending" for status in statuses):
            project_status = "pending"
        elif all(status == "already_current" for status in statuses):
            project_status = "already_current"
        else:
            project_status = "migrated"
        projects.append({"name": name, "local_path": record["local_path"], "resolved_path": str(root),
                         "status": project_status, "active_plans": len(found)})

    for entry in old.get("plans", []):
        key = (entry.get("project"), entry.get("plan"))
        same_plan = any(plan["plan"] == entry.get("plan") and plan["scope"] == "config" for plan in plans)
        if key not in current_keys and not same_plan:
            plans.append({**entry, "scope": "out_of_config",
                          "scope_note": "Preserved from the previous filesystem inventory; not registered in config.json."})
    plans.sort(key=lambda row: (row.get("scope", ""), row.get("project", ""), row.get("plan", "")))
    return {"format": "task-json-migration/v2", "config": str(config), "projects": projects, "plans": plans}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["discover", "complete"])
    parser.add_argument("config", type=Path)
    parser.add_argument("project", nargs="?")
    parser.add_argument("plan", nargs="?")
    args = parser.parse_args()
    old = json.loads(MANIFEST.read_text(encoding="utf-8")) if MANIFEST.exists() else {"plans": []}
    inventory = scan(args.config, old)
    if args.action == "complete":
        if not args.project or not args.plan:
            parser.error("complete needs config project-name plan-id")
        matches = [entry for entry in inventory["plans"] if entry.get("scope") == "config"
                   and entry["project"].casefold() == args.project.casefold() and entry["plan"] == args.plan]
        if len(matches) != 1:
            raise ValueError("plan is outside the config-driven live inventory or is ambiguous")
        verify(Path(matches[0]["path"]))
        matches[0]["status"] = "migrated"
        for project in inventory["projects"]:
            if project["name"] == matches[0]["project"]:
                statuses = [entry["status"] for entry in inventory["plans"]
                            if entry.get("scope") == "config" and entry["project"] == project["name"]]
                project["status"] = "migrated" if statuses and all(status in DONE for status in statuses) else "pending"
    MANIFEST.write_text(json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    in_scope = [entry for entry in inventory["plans"] if entry.get("scope") == "config"]
    pending = [entry for entry in in_scope if entry["status"] not in DONE]
    unavailable = [project for project in inventory["projects"] if project["status"] in {"unavailable", "unresolved"}]
    print(json.dumps({"projects": len(inventory["projects"]), "plans": len(in_scope),
                      "pending": len(pending), "unavailable": len(unavailable)}))
    if args.action == "complete" and in_scope and not pending and not unavailable:
        for entry in in_scope:
            verify(Path(entry["path"]))
        if HERE.name != "migration" or HERE.parent.name != "docs":
            raise ValueError("unexpected cleanup location")
        shutil.rmtree(HERE)
        print("All config projects and active plans verified; temporary migration directory removed.")


if __name__ == "__main__":
    main()
