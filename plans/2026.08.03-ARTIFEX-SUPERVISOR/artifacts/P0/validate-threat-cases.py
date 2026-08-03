#!/usr/bin/env python3
"""Validate the independent Artifex threat/failure case bank."""

from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path


REQUIRED_COVERAGE = {
    "d22_crash_after_durable_append",
    "d22_crash_after_public_boundary",
    "d22_duplicate_delivery",
    "d22_orphan_worker",
    "d22_timeout",
    "d22_quota_failure",
    "d22_approval_failure",
    "d22_journal_corrupted",
    "d22_journal_truncated",
    "d22_journal_reordered",
    "d22_plan_drift",
    "d22_source_drift",
    "d22_budget_exhaustion",
    "d22_out_of_scope_merge_conflict",
    "prompt_injection",
    "path_escape",
    "symlink_escape",
    "journal_tamper",
    "orphan_worker",
    "budget_evasion",
    "provider_schema_drift",
    "foreign_dirty_delta",
    "unknown_third_state",
    "sandbox_success_insufficient",
    "model_confidence_insufficient",
    "widening_mandate_insufficient",
    "worker_tests_passed_insufficient",
}
ALLOWED_STATES = {
    "intent_durable",
    "validating",
    "rolled_back",
    "owner_attention",
    "budget_exhausted",
    "provider_unavailable",
    "refused",
    "incident",
}
ALLOWED_OWNERS = {
    "P1.1",
    "P1.2",
    "P1.3",
    "P1.4",
    "P1.5",
    "P4.1",
    "P4.2",
    "P4.3",
    "P4.4",
    "P4.5",
    "P5.1",
    "P5.2",
    "P5.3",
    "P5.4",
}
STRING_FIELDS = {
    "id",
    "title",
    "boundary",
    "precondition",
    "action",
    "expected_fail_closed_state",
    "rollback_reconcile",
    "owner_item",
}
LIST_FIELDS = {"coverage", "assets", "detection", "evidence", "mitigation"}
INSUFFICIENT_EVIDENCE = {
    "sandbox_success_insufficient",
    "model_confidence_insufficient",
    "widening_mandate_insufficient",
    "worker_tests_passed_insufficient",
}


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def load_bank(path: Path) -> dict[str, object]:
    with path.open(encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError("root must be an object")
    return value


def validate(bank: dict[str, object]) -> tuple[list[str], dict[str, int]]:
    errors: list[str] = []
    if bank.get("schema_version") != "threat-cases-v1":
        fail(errors, "schema_version must equal threat-cases-v1")
    if not isinstance(bank.get("scope"), str) or not bank["scope"].strip():
        fail(errors, "scope must be a non-empty string")

    cases = bank.get("cases")
    if not isinstance(cases, list) or not cases:
        return errors + ["cases must be a non-empty list"], {}

    seen_ids: set[str] = set()
    observed_coverage: set[str] = set()
    owner_phases: Counter[str] = Counter()
    for index, raw_case in enumerate(cases, start=1):
        where = f"cases[{index}]"
        if not isinstance(raw_case, dict):
            fail(errors, f"{where} must be an object")
            continue
        case = raw_case
        missing = (STRING_FIELDS | LIST_FIELDS) - case.keys()
        extra = case.keys() - (STRING_FIELDS | LIST_FIELDS)
        if missing:
            fail(errors, f"{where} missing fields: {sorted(missing)}")
        if extra:
            fail(errors, f"{where} extra fields: {sorted(extra)}")
        for field in STRING_FIELDS:
            value = case.get(field)
            if not isinstance(value, str) or not value.strip():
                fail(errors, f"{where}.{field} must be a non-empty string")
        for field in LIST_FIELDS:
            value = case.get(field)
            if (
                not isinstance(value, list)
                or not value
                or any(not isinstance(entry, str) or not entry.strip() for entry in value)
            ):
                fail(errors, f"{where}.{field} must be a non-empty string list")

        case_id = case.get("id")
        if isinstance(case_id, str):
            if not re.fullmatch(r"THR-\d{3}", case_id):
                fail(errors, f"{where}.id has invalid stable format: {case_id!r}")
            if case_id in seen_ids:
                fail(errors, f"duplicate case id: {case_id}")
            seen_ids.add(case_id)

        coverage = case.get("coverage")
        if isinstance(coverage, list):
            observed_coverage.update(entry for entry in coverage if isinstance(entry, str))

        state = case.get("expected_fail_closed_state")
        if isinstance(state, str) and state not in ALLOWED_STATES:
            fail(errors, f"{where} has non-fail-closed state: {state!r}")
        if state in {"allow", "allowed", "accepted"}:
            fail(errors, f"{where} may not accept a threat case")
        if isinstance(coverage, list) and "unknown_third_state" in coverage and state != "incident":
            fail(errors, f"{where} unknown third state must be incident, got {state!r}")

        owner = case.get("owner_item")
        if isinstance(owner, str):
            if owner not in ALLOWED_OWNERS:
                fail(errors, f"{where} owner must be a P1/P4/P5 item, got {owner!r}")
            else:
                owner_phases[owner.split(".", 1)[0]] += 1

    expected_ids = {f"THR-{number:03d}" for number in range(1, len(cases) + 1)}
    if seen_ids != expected_ids:
        fail(errors, "case IDs must be unique and consecutive from THR-001")

    missing_coverage = REQUIRED_COVERAGE - observed_coverage
    if missing_coverage:
        fail(errors, f"missing required coverage: {sorted(missing_coverage)}")
    if not INSUFFICIENT_EVIDENCE <= observed_coverage:
        fail(errors, "all four insufficient-evidence negative cases are required")
    if set(owner_phases) != {"P1", "P4", "P5"}:
        fail(errors, "the bank must assign at least one case to each of P1, P4, and P5")

    metrics = {
        "cases": len(cases),
        "coverage_labels": len(observed_coverage),
        "required_coverage": len(REQUIRED_COVERAGE),
        "owners_p1": owner_phases["P1"],
        "owners_p4": owner_phases["P4"],
        "owners_p5": owner_phases["P5"],
        "unknown_third_state_allow": sum(
            1
            for case in cases
            if isinstance(case, dict)
            and "unknown_third_state" in case.get("coverage", [])
            and case.get("expected_fail_closed_state") in {"allow", "allowed", "accepted"}
        ),
    }
    return errors, metrics


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print("usage: validate-threat-cases.py THREAT_CASES.json", file=sys.stderr)
        return 2
    path = Path(argv[1])
    try:
        bank = load_bank(path)
        errors, metrics = validate(bank)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"threat-cases: invalid input: {exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"threat-cases: FAIL ({len(errors)} errors)", file=sys.stderr)
        return 1
    print(
        "threat-cases: OK "
        f"({metrics['cases']} cases; {metrics['required_coverage']}/"
        f"{metrics['required_coverage']} required classes; owners "
        f"P1={metrics['owners_p1']}, P4={metrics['owners_p4']}, "
        f"P5={metrics['owners_p5']}; unknown-third-state allow="
        f"{metrics['unknown_third_state_allow']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
