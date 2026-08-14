#!/usr/bin/env python3
"""Own and validate the frozen Layout-v1 fleet migration policy."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path


PLAN_DIR = Path(__file__).resolve().parents[2]
REPOSITORY = PLAN_DIR.parents[1]
INVENTORY = PLAN_DIR / "artifacts" / "P1" / "active-layout-inventory-v1.json"
POLICY = PLAN_DIR / "artifacts" / "P1" / "layout-v1-migration-policy-v1.json"
SCHEMA = REPOSITORY / "packages" / "task" / "configs" / "layout-v1-migration-policy-v1.schema.json"
SCHEMA_ID = "urn:swissknifeman:task:layout-v1-migration-policy:v1"
sys.path.insert(0, str(REPOSITORY / "packages" / "task" / "lib"))

from task import plan_layout, plan_migrate  # noqa: E402

BASE_CLASSES = ("current-state-import", "read-budget-carrier", "semantic-handoff")

CLASS_CONTRACT = {
    "routing-normalization": (
        "Keep legal item/range tokens as ordered single-token Routing rows; omit only policy-recorded non-item metadata.",
        "Every active Routing Items cell matches the closed v2 item/range grammar.",
    ),
    "current-state-import": (
        "Archive legacy journal bytes, emit one canonical row per terminal item, and reset unproven legacy in-progress flags to resumable not-started.",
        "Terminal position and every source status remain explicit without fabricating an active attempt or chronology.",
    ),
    "decision-id-map": (
        "Map noncanonical source decision rows to ordered Dn files and record the reversible ID map; preserve zero rows as zero.",
        "Decision text is archived byte-exact and no decision is invented.",
    ),
    "skeleton-preservation": (
        "Project an empty legacy phase as a marked, nonterminal Layout-v2 skeleton index.",
        "No work item or terminal outcome is invented.",
    ),
    "read-budget-carrier": (
        "Install the frozen policy read-budget contract verbatim.",
        "Every preview evaluates the same stage-aware D2 threshold.",
    ),
    "semantic-handoff": (
        "Recompute Next from projected current state: first runnable item, first skeleton, or terminal archive.",
        "Handoff never claims terminal state while work remains.",
    ),
    "already-v2-admission": (
        "Rebuild a preview-only current-state projection from the archived v1 preimage and move legacy volatile Meta rows to v2 carriers; keep the source tree byte-identical.",
        "The preview satisfies v2 Meta ownership and no apply write is proposed for a target already converted by its owning repository.",
    ),
}
ROLLBACK = "Restore the byte-exact preimage from artifacts/migration-source-v1 before advancing."
READ_BUDGET = """# Layout v2 read-budget contract

**Version:** `1.1.0`

```text
pass_item(i) = estimated_required_read_tokens(i) <= 100000
```
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tree_sha256(path: Path) -> str:
    records = []
    for member in sorted(path.rglob("*")):
        relative = member.relative_to(path).as_posix()
        if ".git" in member.relative_to(path).parts:
            continue
        if member.is_symlink():
            records.append((relative, "symlink", os.readlink(member)))
        elif member.is_file():
            records.append((relative, "file", sha256(member)))
    payload = json.dumps(records, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def classes_for(target: Path) -> tuple[str, ...]:
    if plan_layout.layout_version(target) == "v2":
        return (*BASE_CLASSES, "already-v2-admission")
    classes = list(BASE_CLASSES)
    source = (target / "plan.md").read_text(encoding="utf-8")
    routing = plan_migrate._section(source, "3. Routing")
    try:
        normalized = plan_migrate._normalize_routing_rows(routing)
    except plan_migrate.MigrationError:
        normalized = None
    if normalized != routing:
        classes.append("routing-normalization")
    try:
        plan_migrate._decision_rows(source)
    except plan_migrate.MigrationError:
        classes.append("decision-id-map")
    skeleton = False
    for phase_path in sorted((target / "phases").glob("P*.md")):
        try:
            plan_migrate._phase_source(phase_path)
        except plan_migrate.MigrationError:
            compatible = plan_migrate._phase_source(phase_path, compatibility=True)
            if compatible["items"]:
                raise
            skeleton = True
    if skeleton:
        classes.append("skeleton-preservation")
    return tuple(classes)


def expected_policy() -> dict:
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))
    targets = [Path(value).resolve() for value in inventory["migration_order"]]
    rows = []
    for target in targets:
        if not target.is_dir() or not (target / "plan.md").is_file():
            raise ValueError(f"target unavailable: {target}")
        source_digest = tree_sha256(target)
        plan_digest = sha256(target / "plan.md")
        for defect_class in classes_for(target):
            transform, invariant = CLASS_CONTRACT[defect_class]
            rows.append({
                "target": str(target),
                "source_digest": source_digest,
                "source_plan_sha256": plan_digest,
                "defect_class": defect_class,
                "transform": transform,
                "semantic_invariant": invariant,
                "rollback": ("No write: verify the frozen source digest and return already-v2 no-op."
                             if defect_class == "already-v2-admission" else ROLLBACK),
            })
    return {
        "$schema": SCHEMA_ID,
        "version": "1.0.0",
        "generated_at": "2026-08-12",
        "inventory_sha256": sha256(INVENTORY),
        "read_budget_contract": READ_BUDGET,
        "rows": rows,
    }


def validate_structure(policy: dict) -> None:
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    if schema.get("$id") != SCHEMA_ID:
        raise ValueError("package schema ID drift")
    required = set(schema["required"])
    if set(policy) != required or policy.get("$schema") != SCHEMA_ID or policy.get("version") != "1.0.0":
        raise ValueError("policy root does not match closed schema")
    row_required = set(schema["properties"]["rows"]["items"]["required"])
    allowed_classes = set(schema["properties"]["rows"]["items"]["properties"]["defect_class"]["enum"])
    if not isinstance(policy.get("rows"), list) or not policy["rows"]:
        raise ValueError("policy rows missing")
    for row in policy["rows"]:
        if set(row) != row_required or row.get("defect_class") not in allowed_classes:
            raise ValueError("policy row does not match closed schema")
        if any(not isinstance(value, str) or not value for value in row.values()):
            raise ValueError("policy row contains an empty/non-string value")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true",
                        help="rewrite the owned frozen manifest from current exact preimages")
    args = parser.parse_args(argv)
    expected = expected_policy()
    if args.refresh:
        POLICY.write_text(json.dumps(expected, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        actual = json.loads(POLICY.read_text(encoding="utf-8"))
        validate_structure(actual)
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"POLICY-INVALID: {exc}", file=sys.stderr)
        return 1
    if actual != expected:
        print("POLICY-INVALID: manifest/preimage drift; use --refresh only during authorized policy authoring",
              file=sys.stderr)
        return 1
    targets = len({row["target"] for row in actual["rows"]})
    print(f"POLICY-OK targets={targets} rows={len(actual['rows'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
