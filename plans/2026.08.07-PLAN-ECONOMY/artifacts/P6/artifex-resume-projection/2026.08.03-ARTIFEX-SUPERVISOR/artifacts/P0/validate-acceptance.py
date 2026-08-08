#!/usr/bin/env python3
"""Independent validator for the frozen Artifex P0 acceptance rubric."""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any


RUBRIC_IDS = (
    "REL-ACCEPTED-SCOPE",
    "REL-RECOVERY",
    "REL-IDEMPOTENCY",
    "REL-VALIDATION",
    "REL-BUDGET",
    "SEC-AUTHORITY",
    "SEC-PRIVACY",
    "SEC-WORKTREE",
    "SEC-HOOK-INTEGRITY",
    "EVD-SOURCE-HASHES",
    "EVD-INDEPENDENT-ADJUDICATOR",
    "EVD-UNKNOWN-PRESERVATION",
    "PRV-PARITY-SCOPE",
    "ECO-MATCHED-SCOPE",
    "ECO-D14-BRANCH-1",
    "ECO-D14-BRANCH-2",
)
COMMON_FLOOR_IDS = RUBRIC_IDS[:12]
REQUIRED_P1 = {f"P1.{index}" for index in range(1, 6)}
ALLOWED_P4 = {f"P4.{index}" for index in range(1, 6)}
ALLOWED_P5 = {f"P5.{index}" for index in range(1, 5)}
FLOOR_STATES = {"pass", "fail", "unknown"}
PROVIDER_STATES = {"supported", "degraded", "unsupported", "unknown"}


class ValidationError(Exception):
    pass


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValidationError(f"{path}: cannot load JSON: {exc}") from exc


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def deep_merge(base: Any, override: Any) -> Any:
    if isinstance(base, dict) and isinstance(override, dict):
        result = copy.deepcopy(base)
        for key, value in override.items():
            result[key] = deep_merge(result[key], value) if key in result else copy.deepcopy(value)
        return result
    return copy.deepcopy(override)


def fraction_text(value: Fraction) -> str:
    return f"{value.numerator}/{value.denominator}"


def validate_rubric(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    found = re.findall(r"<!-- RUBRIC-ID: ([A-Z0-9-]+) -->", text)
    require(len(found) == len(set(found)), f"{path}: duplicate RUBRIC-ID marker")
    require(tuple(found) == RUBRIC_IDS, f"{path}: rubric IDs/order differ from frozen v1 set")
    for literal in ("< 1/4", ">= 2", "exactly `N=5`", "Unknown is not zero", "Owner D#"):
        require(literal in text, f"{path}: missing frozen policy literal {literal!r}")
    return set(found)


def derive_crosswalk_path(rubric_path: Path) -> Path:
    try:
        plan_dir = rubric_path.resolve().parents[2]
    except IndexError as exc:
        raise ValidationError(f"{rubric_path}: cannot derive plan root") from exc
    return plan_dir / "research" / "09-p0-freeze-crosswalk.md"


def validate_crosswalk(path: Path, rubric_ids: set[str], threat_ids: set[str]) -> None:
    text = path.read_text(encoding="utf-8")
    rows: dict[str, list[str]] = {}
    for line in text.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if cells and cells[0] in rubric_ids:
            require(cells[0] not in rows, f"{path}: duplicate row for {cells[0]}")
            require(len(cells) == 5, f"{path}: {cells[0]} row must have five cells")
            rows[cells[0]] = cells
    require(set(rows) == rubric_ids, f"{path}: missing/extra rubric rows")

    seen_p1: set[str] = set()
    seen_threats: set[str] = set()
    for rubric_id, cells in rows.items():
        p1 = set(re.findall(r"\bP1\.[1-5]\b", cells[1]))
        p4 = set(re.findall(r"\bP4\.[1-5]\b", cells[2]))
        p5 = set(re.findall(r"\bP5\.[1-4]\b", cells[2]))
        require(p1, f"{path}: {rubric_id} has no P1 consumer")
        require(p4 and p5, f"{path}: {rubric_id} needs both P4 and P5 evidence owners")
        require(p4 <= ALLOWED_P4 and p5 <= ALLOWED_P5, f"{path}: invalid evidence owner")
        seen_p1.update(p1)
        seen_threats.update(re.findall(r"\bTHR-\d{3}\b", cells[3]))
    require(seen_p1 == REQUIRED_P1, f"{path}: P1.1-P1.5 consumer coverage incomplete")
    require(seen_threats == threat_ids, f"{path}: threat coverage differs from threat bank")


def validate_baseline(data: Any, path: Path) -> None:
    require(isinstance(data, dict), f"{path}: root must be object")
    require(data.get("schema_version") == "artifex-baseline-catalog/v1", f"{path}: schema")
    candidates = data.get("candidates")
    require(isinstance(candidates, list) and candidates, f"{path}: candidates must be non-empty")
    ids = [row.get("id") for row in candidates if isinstance(row, dict)]
    require(len(ids) == len(candidates) == len(set(ids)), f"{path}: candidate IDs must be unique")
    require(any(row.get("eligible_for_matching") is True for row in candidates),
            f"{path}: no measured matching seed")
    for row in candidates:
        metrics = row.get("metrics")
        unknown = row.get("unknown_reason")
        require(isinstance(metrics, dict) and isinstance(unknown, dict), f"{path}: metrics/unknown")
        for key, value in metrics.items():
            if value is None:
                reason = unknown.get(key)
                require(isinstance(reason, str) and reason.strip(),
                        f"{path}: {row.get('id')} null metric {key} lacks unknown_reason")


def validate_providers(data: Any, path: Path) -> set[str]:
    require(isinstance(data, dict) and data.get("schema_version") == "provider-matrix-v1",
            f"{path}: schema")
    rows = data.get("providers")
    require(isinstance(rows, list) and rows, f"{path}: providers must be non-empty")
    ids = [row.get("provider") for row in rows if isinstance(row, dict)]
    require(len(ids) == len(rows) == len(set(ids)), f"{path}: provider IDs must be unique")
    for row in rows:
        capabilities = row.get("capabilities")
        require(isinstance(capabilities, dict) and capabilities, f"{path}: capabilities missing")
        require(set(capabilities.values()) <= PROVIDER_STATES,
                f"{path}: unknown capability state for {row.get('provider')}")
    return set(ids)


def validate_threats(data: Any, path: Path) -> set[str]:
    require(isinstance(data, dict) and data.get("schema_version") == "threat-cases-v1",
            f"{path}: schema")
    cases = data.get("cases")
    require(isinstance(cases, list) and cases, f"{path}: cases must be non-empty")
    ids = [row.get("id") for row in cases if isinstance(row, dict)]
    require(len(ids) == len(cases) == len(set(ids)), f"{path}: threat IDs must be unique")
    require(all(re.fullmatch(r"THR-\d{3}", value or "") for value in ids),
            f"{path}: malformed threat ID")
    for row in cases:
        owner = row.get("owner_item")
        require(isinstance(owner, str) and re.fullmatch(r"P[145]\.\d+", owner),
                f"{path}: {row.get('id')} has invalid owner_item")
    return set(ids)


def lane_metrics(name: str, lane: Any, unknown_reason: dict[str, Any]) -> tuple[dict[str, Fraction], bool]:
    require(isinstance(lane, dict), f"lane {name}: must be object")
    accepted = lane.get("accepted_slices")
    attempts = lane.get("attempts")
    require(isinstance(accepted, int) and accepted > 0, f"lane {name}: accepted_slices must be >0")
    require(isinstance(attempts, list) and attempts, f"lane {name}: attempts must be non-empty")

    totals: dict[str, int] = {"tokens": 0, "cost_microunits": 0}
    complete = True
    for index, attempt in enumerate(attempts):
        require(isinstance(attempt, dict), f"lane {name}: attempt {index} must be object")
        require(set(attempt) == {"tokens", "cost_microunits"},
                f"lane {name}: attempt {index} keys must be closed")
        for field in ("tokens", "cost_microunits"):
            value = attempt[field]
            if value is None:
                key = f"lanes.{name}.attempts[{index}].{field}"
                reason = unknown_reason.get(key)
                require(isinstance(reason, str) and reason.strip(), f"{key}: missing unknown_reason")
                complete = False
            else:
                require(isinstance(value, int) and value >= 0, f"lane {name}: invalid {field}")
                totals[field] += value

    metrics = {
        f"{name}_total_tokens": Fraction(totals["tokens"], 1),
        f"{name}_total_cost": Fraction(totals["cost_microunits"], 1),
        f"{name}_tokens_per_accepted_slice": Fraction(totals["tokens"], accepted),
        f"{name}_cost_per_accepted_slice": Fraction(totals["cost_microunits"], accepted),
    }
    return metrics, complete


def evaluate_case(case_input: Any, provider_ids: set[str]) -> dict[str, Any]:
    require(isinstance(case_input, dict), "case input must be object")
    floor_results = case_input.get("floor_results")
    require(isinstance(floor_results, dict), "floor_results must be object")
    require(set(floor_results) == set(COMMON_FLOOR_IDS), "floor_results IDs differ from rubric")
    require(set(floor_results.values()) <= FLOOR_STATES, "invalid floor state")

    blockers: list[str] = []
    for rubric_id in COMMON_FLOOR_IDS:
        state = floor_results[rubric_id]
        if state == "fail":
            blockers.append(f"FLOOR_FAILED:{rubric_id}")
        elif state == "unknown":
            blockers.append(f"FLOOR_UNKNOWN:{rubric_id}")

    provider_scope = case_input.get("provider_scope")
    require(isinstance(provider_scope, dict), "provider_scope must be object")
    mode = provider_scope.get("mode")
    provider_ok = mode == "parity"
    if mode == "single-provider":
        provider_ok = (
            provider_scope.get("owner_grant") is True
            and provider_scope.get("provider") in provider_ids
        )
    elif mode != "parity":
        provider_ok = False
    if not provider_ok:
        blockers.append("PROVIDER_SCOPE_INELIGIBLE")

    matched = case_input.get("matched_scope") is True
    if not matched:
        blockers.append("UNMATCHED_SCOPE")

    unknown_reason = case_input.get("unknown_reason")
    lanes = case_input.get("lanes")
    require(isinstance(unknown_reason, dict), "unknown_reason must be object")
    require(isinstance(lanes, dict) and set(lanes) == {"candidate", "baseline", "workflow"},
            "lanes must contain candidate, baseline, workflow")

    metrics: dict[str, Fraction] = {}
    completeness: dict[str, bool] = {}
    for name in ("candidate", "baseline", "workflow"):
        lane_result, completeness[name] = lane_metrics(name, lanes[name], unknown_reason)
        metrics.update(lane_result)

    owner_events = case_input.get("owner_decision_events")
    dispatched = case_input.get("dispatched_non_synthetic_slices")
    require(isinstance(owner_events, int) and owner_events >= 0, "owner_decision_events invalid")
    require(isinstance(dispatched, int) and dispatched > 0, "dispatch denominator invalid")
    metrics["owner_intervention_ratio"] = Fraction(owner_events, dispatched)

    branch1_failures: list[str] = []
    if case_input.get("waves") != 5:
        branch1_failures.append("BRANCH1_WAVES_NOT_5")
    if metrics["owner_intervention_ratio"] >= Fraction(1, 4):
        branch1_failures.append("BRANCH1_INTERVENTION_NOT_LT_25_PERCENT")
    if not completeness["candidate"] or not completeness["baseline"]:
        branch1_failures.append("BRANCH1_UNKNOWN")
    elif (
        metrics["candidate_tokens_per_accepted_slice"] > metrics["baseline_tokens_per_accepted_slice"]
        or metrics["candidate_cost_per_accepted_slice"] > metrics["baseline_cost_per_accepted_slice"]
    ):
        branch1_failures.append("BRANCH1_WORSE_THAN_BASELINE")

    branch2_failures: list[str] = []
    candidate_tokens = metrics["candidate_tokens_per_accepted_slice"]
    candidate_cost = metrics["candidate_cost_per_accepted_slice"]
    if not completeness["candidate"] or not completeness["workflow"] or candidate_tokens == 0 or candidate_cost == 0:
        branch2_failures.append("BRANCH2_UNKNOWN")
    else:
        metrics["workflow_token_gain"] = metrics["workflow_tokens_per_accepted_slice"] / candidate_tokens
        metrics["workflow_cost_gain"] = metrics["workflow_cost_per_accepted_slice"] / candidate_cost
        if metrics["workflow_token_gain"] < 2 or metrics["workflow_cost_gain"] < 2:
            branch2_failures.append("BRANCH2_GAIN_LT_2X")

    eligible: list[str] = []
    if matched and provider_ok and not branch1_failures:
        eligible.append("D14-B1")
    if matched and provider_ok and not branch2_failures:
        eligible.append("D14-B2")

    if blockers:
        verdict = "NO-GO"
        reasons = blockers
    elif eligible:
        verdict = "GO"
        reasons = []
        if "D14-B1" in eligible:
            reasons.append("GO_BRANCH_1")
        if "D14-B2" in eligible:
            reasons.append("GO_BRANCH_2")
    else:
        verdict = "NO-GO"
        reasons = branch1_failures + branch2_failures

    return {
        "verdict": verdict,
        "eligible_branches": eligible,
        "reason_codes": reasons,
        "metrics": {key: fraction_text(value) for key, value in metrics.items()},
    }


def validate_cases(data: Any, provider_ids: set[str], path: Path) -> int:
    require(isinstance(data, dict), f"{path}: root must be object")
    require(data.get("schema_version") == "acceptance-cases-v1", f"{path}: schema")
    require(tuple(data.get("rubric_ids", [])) == RUBRIC_IDS, f"{path}: rubric IDs/order")
    base = data.get("base_input")
    cases = data.get("cases")
    require(isinstance(base, dict), f"{path}: base_input")
    require(isinstance(cases, list) and cases, f"{path}: cases")
    case_ids = [row.get("id") for row in cases if isinstance(row, dict)]
    require(len(case_ids) == len(cases) == len(set(case_ids)), f"{path}: case IDs must be unique")

    required_boundaries = {
        "branch1-intervention-just-under-25-percent",
        "branch1-intervention-equals-25-percent",
        "branch1-four-waves",
        "branch1-five-waves",
        "branch2-gain-1-point-999x",
        "branch2-gain-exactly-2x",
        "cheaper-but-recovery-red",
        "reliable-but-worse-economy",
        "unknown-candidate-cost-disables-both-branches",
        "weakened-acceptance",
        "unmatched-scope",
        "single-provider-without-owner-grant",
    }
    require(required_boundaries <= set(case_ids), f"{path}: required adversarial boundaries missing")

    for case in cases:
        require(set(case) == {"id", "description", "overrides", "expected"},
                f"{path}: {case.get('id')} has extra/missing keys")
        require(isinstance(case["description"], str) and case["description"].strip(),
                f"{path}: {case['id']} description")
        actual = evaluate_case(deep_merge(base, case["overrides"]), provider_ids)
        expected = case["expected"]
        require(isinstance(expected, dict), f"{path}: {case['id']} expected")
        for key in ("verdict", "eligible_branches", "reason_codes"):
            require(actual[key] == expected.get(key),
                    f"{path}: {case['id']} {key}: expected {expected.get(key)!r}, got {actual[key]!r}")
        expected_metrics = expected.get("metrics")
        require(isinstance(expected_metrics, dict), f"{path}: {case['id']} metrics")
        for key, value in expected_metrics.items():
            require(actual["metrics"].get(key) == value,
                    f"{path}: {case['id']} metric {key}: expected {value!r}, got {actual['metrics'].get(key)!r}")
    return len(cases)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rubric", type=Path, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--providers", type=Path, required=True)
    parser.add_argument("--threats", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        rubric_ids = validate_rubric(args.rubric)
        baseline = load_json(args.baseline)
        providers = load_json(args.providers)
        threats = load_json(args.threats)
        cases = load_json(args.cases)
        validate_baseline(baseline, args.baseline)
        provider_ids = validate_providers(providers, args.providers)
        threat_ids = validate_threats(threats, args.threats)
        validate_crosswalk(derive_crosswalk_path(args.rubric), rubric_ids, threat_ids)
        case_count = validate_cases(cases, provider_ids, args.cases)
    except (OSError, UnicodeError, ValidationError) as exc:
        print(f"acceptance: ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        "acceptance: OK "
        f"({len(rubric_ids)} clauses, {case_count} cases, "
        f"{len(threat_ids)} threats, {len(REQUIRED_P1)} P1 consumers)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
