#!/usr/bin/env python3
"""Real copied-input mutations for the P0 recovery-gate checker."""
from __future__ import annotations

import argparse
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


def mutate_table_cell(path: Path, row_prefix: str, column: int, value: str) -> None:
    lines = path.read_text(encoding="utf-8").splitlines()
    row_index = next(index for index, line in enumerate(lines) if line.startswith(row_prefix))
    cells = [cell.strip() for cell in lines[row_index].strip("|").split("|")]
    cells[column] = value
    lines[row_index] = "| " + " | ".join(cells) + " |"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


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

        for gate in checker.REQUIRED_OBLIGATIONS:
            candidate = root / f"weaken-{gate}.md"
            shutil.copy2(contract, candidate)
            mutate_table_cell(candidate, f"| O-{gate} | {gate} |", 3, "allow")
            if not rejected(lambda: checker.validate_contract(candidate, PREDECESSORS, status="frozen")):
                raise AssertionError(f"nonempty obligation weakening accepted: {gate}")

        for gate_index, gate in enumerate(checker.REQUIRED_GATES):
            for field_index, field in enumerate(checker.RECOVERY_HEADERS):
                if field == "Gate":
                    continue
                candidate = root / f"nonsense-{gate}-{field_index}.md"
                shutil.copy2(contract, candidate)
                mutate_table_cell(candidate, f"| {gate} |", field_index, f"nonsense-{gate_index}-{field_index}")
                if not rejected(lambda: checker.validate_contract(candidate, PREDECESSORS, status="frozen")):
                    raise AssertionError(f"nonempty recovery weakening accepted: {gate} {field}")

        verifier_attacks = {
            "negated": "do not run `task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE P2`",
            "self-asserted": "P2 producer declares itself independently verified",
            "future-cycle": "`task:plan-audit 2026.08.02-PROVIDER-CONTRACT-LOCALE P7`",
        }
        for name, verifier in verifier_attacks.items():
            candidate = root / f"verifier-{name}.md"
            shutil.copy2(contract, candidate)
            mutate_table_cell(candidate, "| R03 |", 3, verifier)
            if not rejected(lambda: checker.validate_contract(candidate, PREDECESSORS, status="frozen")):
                raise AssertionError(f"verifier attack accepted: {name}")

        privacy_attacks = (
            "/home/example/private-target",
            r"C:\Users\example\private-target",
            "account_identifier=user-123456789",
            "api_key=abcdefghijklmnop",
            "ghp_abcdefghijklmnopqrstuvwxyz123456",
            "eyJabcdefghijk.abcdefghijklmnop.abcdefghijklmnop",
        )
        for index, payload in enumerate(privacy_attacks):
            leaked_matrix = root / f"matrix-{index}.md"
            shutil.copy2(matrix, leaked_matrix)
            leaked_matrix.write_text(
                leaked_matrix.read_text(encoding="utf-8") + f"\n{payload}\n",
                encoding="utf-8",
            )
            if not rejected(lambda: checker.require_matrix(leaked_matrix)):
                raise AssertionError(f"privacy leak accepted: {payload}")

        forged = root / "D67-forged.md"
        forged.write_text(
            "---\nstatus: accepted\ntype: contract_freeze_decision\n"
            "contract_version: v1.0.1\ncontract_sha256: sha256:" + "0" * 64 + "\n---\n",
            encoding="utf-8",
        )
        if not rejected(lambda: checker.require_freeze_decision(root, "D67", contract)):
            raise AssertionError("wrong decision hash accepted")

        spoofed = root / "D68-body-spoof.md"
        spoofed.write_text(
            "---\nid: D68\nstatus: rejected\ntype: observation\nitem: P0.6\n"
            "contract_version: v1.0.1\ncontract_sha256: sha256:" + "0" * 64 + "\n---\n"
            "status: accepted\ntype: contract_freeze_decision\nitem: P0.6\n"
            f"contract_version: v1.0.1\ncontract_sha256: {checker.sha(contract)}\n",
            encoding="utf-8",
        )
        if not rejected(lambda: checker.require_freeze_decision(root, "D68", contract)):
            raise AssertionError("decision body spoof accepted")

        wrong_type = root / "D69-wrong-type.md"
        source_decision = PLAN / "decisions" / "D67-p0-recovery-gates-v1.0.1-freeze.md"
        shutil.copy2(source_decision, wrong_type)
        mutate(wrong_type, "id: D67", "id: D69")
        mutate(wrong_type, "type: contract_freeze_decision", "type: observation")
        if not rejected(lambda: checker.require_freeze_decision(root, "D69", contract)):
            raise AssertionError("wrong decision type accepted")

        evidence_copy = root / "recovery-gates-check.json"
        shutil.copy2(HERE / "P0.3" / "recovery-gates-check.json", evidence_copy)
        arguments = argparse.Namespace(
            manifest=str(HERE / "P0.1" / "evidence" / "manifest.json"),
            classification=str(HERE / "P0-provider-fleet-classification.json"),
            contract=str(contract),
            action_matrix=str(matrix),
            predecessor_dir=str(PREDECESSORS),
            decision_dir=str(PLAN / "decisions"),
            evidence=str(evidence_copy),
        )
        checker.check(arguments)
        changed = json.loads(evidence_copy.read_text(encoding="utf-8"))
        changed["result"] = "pass-but-unverified"
        evidence_copy.write_text(json.dumps(changed, sort_keys=True) + "\n", encoding="utf-8")
        if not rejected(lambda: checker.check(arguments)):
            raise AssertionError("evidence digest mutation accepted")

    print(
        f"allow: {len(cases)} declared copied-input mutations plus exhaustive "
        "mapping/recovery/privacy/decision/evidence negatives"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
