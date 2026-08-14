#!/usr/bin/env python3
"""Build and validate the registered active-plan layout inventory."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


SCRIPT = Path(__file__).resolve()
ROOT = SCRIPT.parents[4]
PLAN_DIR = SCRIPT.parents[2]
INVENTORY = SCRIPT.with_name("active-layout-inventory-v1.json")
TASK_LIB = ROOT / "packages" / "task" / "lib"
sys.path.insert(0, str(TASK_LIB))

from task import plan_layout  # noqa: E402


class InventoryError(RuntimeError):
    """The registry or inventory cannot be classified deterministically."""


def run(command: list[str]) -> str:
    result = subprocess.run(
        command,
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        detail = (result.stderr or result.stdout).strip()
        raise InventoryError(f"command failed ({result.returncode}): {' '.join(command)}: {detail}")
    return result.stdout


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def registered_paths() -> tuple[list[dict], list[dict]]:
    skiller_command = [str(ROOT / "packages" / "skiller" / "bin" / "skiller"), "list"]
    maind_command = [str(ROOT / "packages" / "maind" / "bin" / "maind"),
                     "projects", "list", "--json"]
    skiller_output = run(skiller_command)
    maind_output = run(maind_command)

    skiller_lines = skiller_output.splitlines()
    if not skiller_lines or skiller_lines[0].split() != [
            "STATE", "CHANNEL", "PROFILE", "UPDATED", "PATH"]:
        raise InventoryError("skiller list has an unknown header")
    skiller_rows = []
    for line_number, line in enumerate(skiller_lines[1:], start=2):
        if not line.strip():
            continue
        cells = line.split(maxsplit=4)
        if len(cells) != 5:
            raise InventoryError(f"skiller list row {line_number} is malformed: {line!r}")
        candidate = Path(os.path.expanduser(cells[4]))
        if not candidate.is_absolute():
            raise InventoryError(
                f"skiller list row {line_number} has a relative path: {cells[4]!r}")
        if cells[3] != "-" and not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", cells[3]):
            raise InventoryError(f"skiller list row has an unknown UPDATED value: {line!r}")
        skiller_rows.append(cells[4])
    try:
        maind_rows = json.loads(maind_output)
    except json.JSONDecodeError as exc:
        raise InventoryError(f"maind projects list --json is invalid: {exc}") from exc
    if not isinstance(maind_rows, list):
        raise InventoryError("maind projects list --json did not return a list")
    maind_paths = []
    for index, row in enumerate(maind_rows):
        if not isinstance(row, dict):
            raise InventoryError(f"maind project row {index} is not an object")
        raw_path = row.get("local_path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            raise InventoryError(f"maind project row {index} has no local_path")
        candidate = Path(os.path.expanduser(raw_path))
        if not candidate.is_absolute():
            raise InventoryError(
                f"maind project row {index} has a relative local_path: {raw_path!r}")
        maind_paths.append(raw_path)

    raw = [("repository", str(ROOT))]
    raw.extend(("skiller", path) for path in skiller_rows)
    raw.extend(("maind", path) for path in maind_paths)
    roots: dict[str, dict] = {}
    for source, raw_path in raw:
        if not raw_path:
            continue
        expanded = Path(os.path.expanduser(raw_path))
        resolved = expanded.resolve(strict=False)
        key = str(resolved)
        record = roots.setdefault(key, {
            "path": key,
            "exists": resolved.is_dir(),
            "sources": [],
        })
        if source not in record["sources"]:
            record["sources"].append(source)
    for record in roots.values():
        record["sources"].sort()

    sources = [
        {
            "id": "repository",
            "command": "pwd",
            "records": 1,
            "output_sha256": sha256_text(str(ROOT) + "\n"),
        },
        {
            "id": "skiller",
            "command": "packages/skiller/bin/skiller list",
            "records": len(skiller_rows),
            "output_sha256": sha256_text(skiller_output),
        },
        {
            "id": "maind",
            "command": "packages/maind/bin/maind projects list --json",
            "records": len(maind_rows),
            "output_sha256": sha256_text(maind_output),
        },
    ]
    return sources, sorted(roots.values(), key=lambda row: row["path"])


def git_dirty_summary(root: Path) -> dict:
    result = subprocess.run(
        ["git", "-C", str(root), "status", "--short", "--", "plans"],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        return {"available": False, "entries": []}
    entries = [line for line in result.stdout.splitlines() if line]
    return {"available": True, "entries": entries}


def active_pointer(plans_dir: Path, root: Path) -> tuple[set[str], str | None]:
    path = plans_dir / "ACTIVE.md"
    if not os.path.lexists(path):
        return set(), None
    try:
        mode = path.lstat().st_mode
        if not stat.S_ISREG(mode) or path.is_symlink() or not within(path, root):
            return set(), "ACTIVE.md is not a regular in-root non-symlink file"
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return set(), f"ACTIVE.md is unreadable: {exc}"
    active = set()
    in_active_list = False
    for line in text.splitlines():
        match = re.fullmatch(r"\*\*Active:\*\*\s+([^\s]+)\s*", line)
        if match:
            active_id = match.group(1).strip("`")
            if active_id != "—":
                active.add(active_id)
            in_active_list = False
            continue
        if line.strip() == "**Active:**":
            in_active_list = True
            continue
        if in_active_list and (line.startswith("**") or line.startswith("#")):
            in_active_list = False
        if in_active_list:
            list_match = re.match(r"^-\s+([^\s]+)(?:\s+—|\s*$)", line)
            if list_match:
                active_id = list_match.group(1).strip("`")
                if active_id != "—":
                    active.add(active_id)
    return active, None


def within(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=False))
    except ValueError:
        return False
    return True


def invalid_record(path: Path, root: Path, diagnostic: str, *, plan_id: str | None = None) -> dict:
    return {
        "plan_id": plan_id or path.name,
        "path": str(path.absolute()),
        "root": str(root),
        "classification": "invalid",
        "declared_layout": None,
        "active_pointer_match": False,
        "migration_disposition": "blocks-removal",
        "diagnostic": diagnostic,
    }


def carrier_boundary_error(plan_dir: Path, root: Path) -> str | None:
    plan_path = plan_dir / "plan.md"
    try:
        if plan_path.is_symlink() or not stat.S_ISREG(plan_path.lstat().st_mode):
            return "plan.md is not a regular non-symlink file"
    except OSError as exc:
        return f"plan.md is unreadable: {exc}"
    if not within(plan_path, root):
        return "plan.md resolves outside registered root"
    phases = plan_dir / "phases"
    if os.path.lexists(phases):
        try:
            if phases.is_symlink() or not stat.S_ISDIR(phases.lstat().st_mode):
                return "phases is not a directory or is a symlink"
        except OSError as exc:
            return f"phases is unreadable: {exc}"
        for directory, dirnames, filenames in os.walk(phases, followlinks=False):
            base = Path(directory)
            for name in [*dirnames, *filenames]:
                carrier = base / name
                if carrier.is_symlink() and not within(carrier, root):
                    return f"phase carrier resolves outside registered root: {carrier}"
    return None


def declared_layout_for_history(plan_dir: Path) -> str | None:
    """Read an archive label without resolving it as an executable layout."""
    try:
        text = (plan_dir / "plan.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise InventoryError(f"plan.md is unreadable: {exc}") from exc
    for line in text.splitlines():
        match = re.match(r"^\|\s*Layout\s*\|\s*([^|]+)\|", line)
        if match:
            return match.group(1).strip()
    # A missing declaration is retired v1 in historical evidence only.  This
    # preserves the pre-cutover inventory label without making it executable.
    return "v1"


def classify_plan(plan_dir: Path, root: Path, active_ids: set[str], *, archived: bool) -> dict:
    resolved = plan_dir.resolve(strict=False)
    record = {
        "plan_id": plan_dir.name,
        "path": str(resolved),
        "root": str(root),
        "classification": "invalid",
        "declared_layout": None,
        "active_pointer_match": not archived and plan_dir.name in active_ids,
        "migration_disposition": "blocks-removal",
        "diagnostic": None,
    }
    if plan_dir.is_symlink() or not within(plan_dir, root):
        record["diagnostic"] = "candidate is a symlink or resolves outside registered root"
        return record
    boundary_error = carrier_boundary_error(plan_dir, root)
    if boundary_error:
        record["diagnostic"] = boundary_error
        return record
    if archived:
        try:
            record["declared_layout"] = declared_layout_for_history(plan_dir)
        except (InventoryError, UnicodeError) as exc:
            record["diagnostic"] = str(exc)
            return record
        record.update(classification="archive", migration_disposition="inert-history")
        return record
    try:
        declared = plan_layout._meta_layout(plan_dir)
        resolved_layout = plan_layout.layout_version(plan_dir)
        if resolved_layout == "v1":
            phase_carriers = []
            try:
                phase_entries = list((plan_dir / "phases").iterdir())
            except OSError as exc:
                raise plan_layout.PlanLayoutError(
                    "Layout v1 has no readable regular phases/Pn.md carriers") from exc
            for path in phase_entries:
                if not re.fullmatch(r"P\d+\.md", path.name):
                    continue
                try:
                    if (not path.is_symlink() and stat.S_ISREG(path.lstat().st_mode)
                            and within(path, root)):
                        phase_carriers.append(path)
                except OSError:
                    continue
            if not phase_carriers:
                raise plan_layout.PlanLayoutError("Layout v1 has no regular phases/Pn.md carriers")
    except (OSError, UnicodeError, plan_layout.PlanLayoutError) as exc:
        record["diagnostic"] = str(exc)
        return record
    record["declared_layout"] = declared
    if resolved_layout == "v2":
        record.update(classification="v2", migration_disposition="none")
    else:
        record.update(classification="v1-active", migration_disposition="migrate-before-removal")
    return record


def archive_records(container: Path, root: Path, active_ids: set[str]) -> tuple[list[dict], list[str]]:
    records, discovered = [], []
    walk_errors = []
    for directory, dirnames, filenames in os.walk(
            container, followlinks=False, onerror=walk_errors.append):
        base = Path(directory)
        for name in list(dirnames):
            candidate = base / name
            if candidate.is_symlink():
                discovered.append(str(candidate.absolute()))
                records.append(invalid_record(
                    candidate, root, "archive directory symlink is not traversed", plan_id=name))
                dirnames.remove(name)
        if "plan.md" not in filenames:
            continue
        plan_dir = base
        discovered.append(str(plan_dir.resolve(strict=False)))
        records.append(classify_plan(plan_dir, root, active_ids, archived=True))
    for error in walk_errors:
        path = Path(error.filename or container)
        discovered.append(str(path.absolute()))
        records.append(invalid_record(path, root, f"archive path is unreadable: {error}"))
    return records, discovered


def scan_root(root_record: dict) -> tuple[dict, list[dict], list[str]]:
    root = Path(root_record["path"])
    record = dict(root_record)
    if not root_record["exists"]:
        record["classification"] = "unreachable"
        record["dirty"] = {"available": False, "entries": []}
        return record, [], []
    record["classification"] = "reachable"
    record["dirty"] = git_dirty_summary(root)
    plans_dir = root / "plans"
    if not os.path.lexists(plans_dir):
        return record, [], []
    if plans_dir.is_symlink() or not within(plans_dir, root):
        return record, [{
            "plan_id": "*",
            "path": str(plans_dir.resolve(strict=False)),
            "root": str(root),
            "classification": "invalid",
            "declared_layout": None,
            "active_pointer_match": False,
            "migration_disposition": "blocks-removal",
            "diagnostic": "plans directory is a symlink or resolves outside registered root",
        }], [str(plans_dir.resolve(strict=False))]
    active_ids, pointer_error = active_pointer(plans_dir, root)
    plans, discovered = [], []
    direct_candidate_ids = set()
    if pointer_error:
        pointer_path = plans_dir / "ACTIVE.md"
        discovered.append(str(pointer_path.resolve(strict=False)))
        plans.append(invalid_record(pointer_path, root, pointer_error, plan_id="ACTIVE"))
    try:
        children = sorted(plans_dir.iterdir(), key=lambda path: path.name)
    except OSError as exc:
        discovered.append(str(plans_dir.resolve(strict=False)))
        plans.append(invalid_record(plans_dir, root, f"plans directory is unreadable: {exc}", plan_id="*"))
        return record, plans, discovered
    for child in children:
        try:
            child_mode = child.lstat().st_mode
        except OSError as exc:
            direct_candidate_ids.add(child.name)
            discovered.append(str(child.absolute()))
            invalid = invalid_record(child, root, f"direct plans child is unreadable: {exc}")
            invalid["active_pointer_match"] = child.name in active_ids
            plans.append(invalid)
            continue
        if child.name.lower() in {"archive", "archives"}:
            if stat.S_ISLNK(child_mode) or not stat.S_ISDIR(child_mode):
                discovered.append(str(child.resolve(strict=False)))
                plans.append(invalid_record(child, root, "archive container is not a directory or is a symlink"))
                continue
            archived, archived_discovered = archive_records(child, root, active_ids)
            plans.extend(archived)
            discovered.extend(archived_discovered)
            continue
        if stat.S_ISLNK(child_mode):
            discovered.append(str(child.absolute()))
            direct_candidate_ids.add(child.name)
            invalid = invalid_record(child, root, "direct plans child is a symlink")
            invalid["active_pointer_match"] = child.name in active_ids
            plans.append(invalid)
            continue
        if not stat.S_ISDIR(child_mode):
            continue
        plan_carrier = child / "plan.md"
        try:
            child_entries = {entry.name for entry in child.iterdir()}
        except OSError as exc:
            direct_candidate_ids.add(child.name)
            discovered.append(str(child.resolve(strict=False)))
            invalid = invalid_record(child, root, f"direct plans child is unreadable: {exc}")
            invalid["active_pointer_match"] = child.name in active_ids
            plans.append(invalid)
            continue
        if "plan.md" in child_entries:
            direct_candidate_ids.add(child.name)
            discovered.append(str(child.resolve(strict=False)))
            plans.append(classify_plan(child, root, active_ids, archived=False))
    for active_id in sorted(active_ids - direct_candidate_ids):
        candidate = plans_dir / active_id
        discovered.append(str(candidate.absolute()))
        invalid = invalid_record(
            candidate,
            root,
            "ACTIVE.md target is not a direct executable plans/<ID>/plan.md candidate",
            plan_id=active_id,
        )
        invalid["active_pointer_match"] = True
        plans.append(invalid)
    return record, plans, discovered


def build_inventory() -> dict:
    sources, registered = registered_paths()
    roots, plans, discovered = [], [], []
    for root in registered:
        root_record, root_plans, root_discovered = scan_root(root)
        roots.append(root_record)
        plans.extend(root_plans)
        discovered.extend(root_discovered)
    roots.sort(key=lambda row: row["path"])
    plans.sort(key=lambda row: (row["root"], row["path"]))
    counts = Counter(row["classification"] for row in plans)
    counts["unreachable"] += sum(row["classification"] == "unreachable" for row in roots)
    migration_order = [row["path"] for row in plans if row["classification"] == "v1-active"]
    classified = [row["path"] for row in plans]
    unclassified = sorted(set(discovered) - set(classified))
    return {
        "$schema": "urn:swissknifeman:task:active-layout-inventory:v1",
        "schema_version": "1.0.0",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "repository": str(ROOT),
        "sources": sources,
        "roots": roots,
        "plans": plans,
        "migration_order": migration_order,
        "summary": {
            "registered_records": sum(source["records"] for source in sources),
            "unique_roots": len(roots),
            "reachable_roots": sum(row["classification"] == "reachable" for row in roots),
            "classifications": {key: counts.get(key, 0) for key in
                                ("v2", "v1-active", "archive", "invalid", "unreachable")},
            "candidate_count": len(discovered),
            "classified_count": len(classified),
            "unclassified": len(unclassified),
            "unclassified_paths": unclassified,
        },
    }


def stable_projection(inventory: dict) -> dict:
    projection = json.loads(json.dumps(inventory))
    projection.pop("generated_at", None)
    for root in projection.get("roots", []):
        dirty = root.get("dirty")
        if isinstance(dirty, dict):
            # Exact porcelain entries are point-in-time evidence. Comparing
            # them would make the committed snapshot fail on a clean checkout
            # merely because its own carriers stopped being dirty.
            dirty["entries"] = []
    return projection


def validate(expected: dict, observed: dict) -> None:
    if expected.get("$schema") != "urn:swissknifeman:task:active-layout-inventory:v1":
        raise InventoryError("unexpected inventory schema")
    summary = expected.get("summary", {})
    if summary.get("unclassified") != 0 or summary.get("unclassified_paths") != []:
        raise InventoryError("inventory contains unclassified candidates")
    allowed = {"v2", "v1-active", "archive", "invalid"}
    if any(row.get("classification") not in allowed for row in expected.get("plans", [])):
        raise InventoryError("inventory contains an unknown plan classification")
    migration = [row["path"] for row in expected["plans"]
                 if row["classification"] == "v1-active"]
    if expected.get("migration_order") != migration:
        raise InventoryError("migration_order is not the deterministic v1-active order")
    if summary.get("candidate_count") != len(expected.get("plans", [])):
        raise InventoryError("candidate denominator does not equal classified plan records")
    if summary.get("classified_count") != len(expected.get("plans", [])):
        raise InventoryError("classified count does not equal plan records")
    plan_paths = [row.get("path") for row in expected.get("plans", [])]
    if len(plan_paths) != len(set(plan_paths)):
        raise InventoryError("inventory contains duplicate plan paths")
    for root in expected.get("roots", []):
        dirty = root.get("dirty")
        if root.get("classification") == "reachable" and not (
                isinstance(dirty, dict) and isinstance(dirty.get("available"), bool)
                and isinstance(dirty.get("entries"), list)):
            raise InventoryError(f"root dirty summary is malformed: {root.get('path')}")
    if stable_projection(expected) != stable_projection(observed):
        raise InventoryError("inventory drifted from current repository/skiller/maind registries")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="materialize the current snapshot")
    args = parser.parse_args()
    try:
        observed = build_inventory()
        if args.write:
            INVENTORY.write_text(
                json.dumps(observed, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        expected = json.loads(INVENTORY.read_text(encoding="utf-8"))
        validate(expected, observed)
    except (InventoryError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    summary = expected["summary"]
    classes = summary["classifications"]
    print(
        "OK: "
        f"sources={len(expected['sources'])} registered={summary['registered_records']} "
        f"roots={summary['unique_roots']} reachable={summary['reachable_roots']} "
        f"plans={len(expected['plans'])} candidates={summary['candidate_count']} "
        + " ".join(f"{key}={value}" for key, value in classes.items())
        + " unclassified=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
