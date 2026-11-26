"""``verify``: load the plans of a folder through the planner store and compare their ``check`` errors with a baseline.

A plan is *loaded* when ``store.load_plan`` reports no ``problems``. The errors of ``plan.py check`` (``check.check``, the
same engine; external plugins are not asked) are compared as sets of ``(code, where)``: a plan that is red before the
migration stays the same red, an error the baseline does not have is new. Warnings are not compared.

A folder outside a checkout (the staging of ``apply``, a plan of the workspace) is checked *unbound* when asked for: no
checkout means that the existence of repository paths is not verified (the planner says so as a warning), so the copy can
only have fewer errors than its source, never errors that come from the place it is checked at.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional, Tuple

import partners


def plan_folders(plans_root: Path) -> List[Tuple[str, Path]]:
    """``(name, folder)`` of every plan folder (with ``plan.json``) of ``plans_root`` and ``plans_root/archive``; the name
    is the POSIX path relative to ``plans_root``."""
    store = partners.planner_engine("plan.store")
    found = []
    for folder in store.plan_dirs(plans_root):
        if (folder / "plan.json").is_file():
            found.append((folder.relative_to(plans_root).as_posix(), folder))
    return found


def check_plan(folder: Path, unbound: bool = False) -> Dict[str, object]:
    """``{loaded, problems, errors}`` of one plan folder: ``problems`` are ``(file, message)`` pairs of the store,
    ``errors`` the sorted ``(code, where)`` pairs of ``check``. A refusal of the planner is a problem of ``plan.json``."""
    store, check = partners.planner_engine("plan.store", "plan.check")
    try:
        plan = store.load_plan(folder)
        if unbound:
            plan.__dict__["source_root"] = None  # cached_property: the plan has no checkout
        issues = check.check(plan)
    except store.PlanError as exc:
        return {"loaded": False, "problems": [("plan.json", f"{exc.code}: {exc.message}")], "errors": []}
    errors = sorted({(issue.code, issue.where) for issue in issues if issue.level == "error"})
    return {"loaded": not plan.problems, "problems": [tuple(item) for item in plan.problems], "errors": errors}


def new_errors(baseline: Dict[str, object], copy: Dict[str, object]) -> List[Tuple[str, str]]:
    seen = set(baseline["errors"])
    return [pair for pair in copy["errors"] if pair not in seen]


def _pairs(errors) -> List[Dict[str, str]]:
    return [{"code": code, "where": where} for code, where in errors]


def compare_roots(plans_root: Path, baseline_root: Optional[Path], unbound: bool = False,
                  baseline_unbound: bool = False) -> Dict[str, object]:
    """The ``verify`` answer for the plans of ``plans_root``; with ``baseline_root`` every plan is compared with the plan
    of the same name there (a plan the baseline lacks is not compared)."""
    rows = []
    ok = True
    for name, folder in plan_folders(plans_root):
        result = check_plan(folder, unbound)
        row: Dict[str, object] = {"name": name, "loaded": result["loaded"],
                                  "problems": [{"file": file, "message": message} for file, message in result["problems"]],
                                  "check_codes": _pairs(result["errors"])}
        ok = ok and bool(result["loaded"]) and not result["problems"]
        if baseline_root is not None and (baseline_root / name / "plan.json").is_file():
            base = check_plan(baseline_root / name, baseline_unbound)
            fresh = new_errors(base, result)
            row["new_errors"] = _pairs(fresh)
            ok = ok and not fresh
        rows.append(row)
    return {"ok": ok, "plans": rows}
