#!/usr/bin/env python3
"""Compare every module contract with a git revision, in process.

    schema-compat-all.py [--base REF] [--repo DIR] [--json]

Walks ``packages/*/unit.json`` and ``bridges/*/unit.json``. Each ``provides.contracts[]`` entry whose ``path`` is
``schemas/<contract>/v<N>`` is compared by one in-process call of ``aicore.util.schemacompat.main`` per module, with
``--root`` set to that module's ``schemas`` directory (the contract directory itself is not a root: the comparator
looks for ``<root>/*/v*/*.schema.json``). A path without ``v<N>`` is legacy and is not compared.

Exit 0 when every compared contract is free of ``severity: error``. Exit 1 when a change is an error, a declared
contract is missing from the report (``SCHEMA_COMPAT_UNCOVERED``), or the comparator fails (``SCHEMA_COMPAT_FAILED``).
Exit 2 is usage. ``bin/aicore`` is not executed.
"""
from __future__ import annotations

import argparse
import json
import sys
from io import StringIO
from pathlib import Path

HUB = Path(__file__).resolve().parents[1]
CONTRACT_PATH = __import__("re").compile(r"^schemas/([^/]+)/(v[0-9]+)$")


def _units(repo: Path) -> list:
    found = []
    for pattern in ("packages/*/unit.json", "bridges/*/unit.json"):
        found.extend(sorted(repo.glob(pattern)))
    return found


def _declared(unit: dict) -> tuple:
    """``(versioned, legacy)`` from ``provides.contracts``."""
    versioned, legacy = [], []
    for contract in (unit.get("provides") or {}).get("contracts") or ():
        if not isinstance(contract, dict):
            continue
        path = contract.get("path")
        if not isinstance(path, str):
            continue
        match = CONTRACT_PATH.fullmatch(path)
        if match is None:
            legacy.append({"path": path, "status": "legacy"})
        else:
            versioned.append((match.group(1), match.group(2)))
    return versioned, legacy


def _compare_unit(repo: Path, unit_path: Path, base: str) -> dict:
    """One module: comparator report, uncovered contracts and legacy paths."""
    sys.path.insert(0, str(HUB / "packages" / "aicore" / "lib"))
    from aicore.util import schemacompat

    try:
        unit = json.loads(unit_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"unit": unit_path.parent.name, "root": "", "contracts": [], "uncovered": [], "legacy": [],
                "failed": f"SCHEMA_COMPAT_FAILED: {unit_path.parent.name}: cannot read unit.json: {exc}"}
    name = unit.get("id") if isinstance(unit.get("id"), str) else unit_path.parent.name
    versioned, legacy = _declared(unit if isinstance(unit, dict) else {})
    root = unit_path.parent / "schemas"
    entry = {"unit": name, "root": root.relative_to(repo).as_posix() if root.is_dir() else "",
             "contracts": [], "uncovered": [], "legacy": [{"unit": name, **item} for item in legacy]}
    if not versioned:
        return entry
    missing_dirs = [f"{contract}/{version}" for contract, version in versioned
                    if not (root / contract / version).is_dir()]
    if not root.is_dir():
        entry["uncovered"] = [f"{contract}/{version}" for contract, version in versioned]
        entry["failed"] = f"SCHEMA_COMPAT_UNCOVERED: {name}: {', '.join(entry['uncovered'])}"
        return entry
    out, err = StringIO(), StringIO()
    rc = schemacompat.main(["compat", "--base", base, "--root", str(root), "--unit", str(unit_path), "--json"],
                           cwd=repo, out=out, err=err)
    if rc == 2 or not out.getvalue().strip():
        detail = err.getvalue().strip().splitlines()
        entry["failed"] = f"SCHEMA_COMPAT_FAILED: {name}: {detail[0] if detail else 'no report'}"
        return entry
    try:
        report = json.loads(out.getvalue())
    except ValueError as exc:
        entry["failed"] = f"SCHEMA_COMPAT_FAILED: {name}: cannot parse report: {exc}"
        return entry
    entry["contracts"] = report.get("contracts") or []
    seen = {(item.get("contract"), item.get("version")) for item in entry["contracts"]}
    entry["uncovered"] = [f"{contract}/{version}" for contract, version in versioned if (contract, version) not in seen]
    if missing_dirs:
        for label in missing_dirs:
            if label not in entry["uncovered"]:
                entry["uncovered"].append(label)
    if entry["uncovered"]:
        entry["failed"] = f"SCHEMA_COMPAT_UNCOVERED: {name}: {', '.join(entry['uncovered'])}"
    return entry


def run(repo: Path, base: str) -> dict:
    units = []
    for unit_path in _units(repo):
        units.append(_compare_unit(repo, unit_path, base))
    errors = []
    for entry in units:
        if entry.get("failed"):
            errors.append(entry["failed"])
        for contract in entry["contracts"]:
            for change in contract.get("changes") or ():
                if change.get("severity") == "error":
                    label = f"{entry['unit']}: {contract.get('contract')}/{contract.get('version')}"
                    errors.append(f"SCHEMA_COMPAT_ERROR: {label}: {change.get('rule')}: {change.get('message')}")
    return {"ok": not errors, "units": [{key: value for key, value in entry.items() if key != "failed"}
                                        for entry in units],
            "_errors": errors}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Compare every module contract with a git revision.")
    parser.add_argument("--base", default="HEAD", help="git revision to compare with (default: HEAD)")
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="repository root (default: cwd)")
    parser.add_argument("--json", action="store_true", help="machine-readable summary on stdout")
    args = parser.parse_args(argv)
    repo = args.repo.resolve()
    if not (repo / ".git").exists() and not (repo / "packages").is_dir():
        print(f"SCHEMA_COMPAT_FAILED: {repo}: not a repository", file=sys.stderr)
        return 2
    summary = run(repo, args.base)
    errors = summary.pop("_errors")
    if args.json:
        json.dump(summary, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        for entry in summary["units"]:
            print(f"{entry['unit']}: {len(entry['contracts'])} compared, "
                  f"{len(entry['uncovered'])} uncovered, {len(entry['legacy'])} legacy")
    for message in errors:
        print(message, file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
