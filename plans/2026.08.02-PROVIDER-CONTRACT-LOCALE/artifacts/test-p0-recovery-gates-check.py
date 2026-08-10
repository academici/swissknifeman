#!/usr/bin/env python3
"""Real copied-input mutations for the P0 recovery-gate checker."""
from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
from pathlib import Path


HERE = Path(__file__).resolve().parent
PLAN = HERE.parent
REPO = PLAN.parents[1]
PREDECESSORS = REPO / "plans" / "archive" / "2026.07.19-DUAL-PROVIDER" / "root" / "contracts"
FIXTURES = HERE / "P0.6" / "fixtures" / "mutations.json"
spec = importlib.util.spec_from_file_location("checker", HERE / "p0-recovery-gates-check.py")
checker = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(checker)


def rejected(callable_) -> bool:
    try:
        callable_()
    except (OSError, ValueError, json.JSONDecodeError):
        return True
    return False


def mutate(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"fixture anchor missing: {old!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def main() -> int:
    cases = json.loads(FIXTURES.read_text(encoding="utf-8"))["cases"]
    contract = PLAN / "root" / "contracts" / "provider-recovery-gates-v1.md"
    matrix = HERE / "P0-security-trust-action-matrix.md"
    checker.validate_contract(contract, PREDECESSORS, status="frozen")
    checker.require_matrix(matrix)

    with tempfile.TemporaryDirectory(prefix="p0.6-recovery-") as directory:
        root = Path(directory)
        for case in cases:
            target_root = root / case["id"]
            target_root.mkdir()
            candidate = target_root / "contract.md"
            copied_predecessors = target_root / "predecessors"
            shutil.copy2(contract, candidate)
            shutil.copytree(PREDECESSORS, copied_predecessors)
            if case["target"] == "contract":
                mutate(candidate, case["old"], case["new"])
            else:
                mutate(copied_predecessors / case["target"], case["old"], case["new"])
            if not rejected(lambda: checker.validate_contract(candidate, copied_predecessors, status="frozen")):
                raise AssertionError(f"mutation accepted: {case['id']}")

        for field in checker.RECOVERY_HEADERS:
            if field == "Gate":
                continue
            candidate = root / f"empty-{field.replace(' ', '-').lower()}.md"
            shutil.copy2(contract, candidate)
            lines = candidate.read_text(encoding="utf-8").splitlines()
            row_index = next(index for index, line in enumerate(lines) if line.startswith("| R04 |"))
            cells = [cell.strip() for cell in lines[row_index].strip("|").split("|")]
            cells[checker.RECOVERY_HEADERS.index(field)] = ""
            lines[row_index] = "| " + " | ".join(cells) + " |"
            candidate.write_text("\n".join(lines) + "\n", encoding="utf-8")
            if not rejected(lambda: checker.validate_contract(candidate, PREDECESSORS, status="frozen")):
                raise AssertionError(f"empty field accepted: {field}")

        leaked_matrix = root / "matrix.md"
        shutil.copy2(matrix, leaked_matrix)
        leaked_matrix.write_text(
            leaked_matrix.read_text(encoding="utf-8") + "\n/home/example/private-target\n",
            encoding="utf-8",
        )
        if not rejected(lambda: checker.require_matrix(leaked_matrix)):
            raise AssertionError("privacy leak accepted")

        forged = root / "D67-forged.md"
        forged.write_text(
            "---\nstatus: accepted\ntype: contract_freeze_decision\n"
            "contract_version: v1.0.1\ncontract_sha256: sha256:" + "0" * 64 + "\n---\n",
            encoding="utf-8",
        )
        if not rejected(lambda: checker.require_freeze_decision(root, "D67", contract)):
            raise AssertionError("wrong decision hash accepted")

    print(f"allow: {len(cases)} copied-input mutations plus field/privacy/decision negatives")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
