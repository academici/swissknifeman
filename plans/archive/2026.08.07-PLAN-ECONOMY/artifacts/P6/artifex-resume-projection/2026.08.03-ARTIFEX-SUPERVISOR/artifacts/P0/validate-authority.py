#!/usr/bin/env python3
"""Validate the P0.2 authority freeze and its independent decision cases."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


DECLARED_CLASSES = {"AUTO", "AUTO-FIX", "OWNER"}
EXPECTED_PROTECTED = {
    "security",
    "destructive",
    "irreversible",
    "external",
    "public-contract",
    "dependency",
    "package-topology",
    "third-state",
    "unknown-capability",
    "same-level-conflict",
    "unresolved-routine-choice",
    "exhausted-budget",
}
EXPECTED_NARROWING_CODES = {
    "MANDATE_WIDENS_FILES",
    "MANDATE_WIDENS_TOOLS",
    "MANDATE_WIDENS_PROVIDER",
    "MANDATE_WIDENS_MODEL",
    "MANDATE_WIDENS_EFFORT",
    "MANDATE_WIDENS_BUDGET",
    "MANDATE_WEAKENS_VALIDATION",
    "MANDATE_WIDENS_ACTION_CLASS",
}
EXPECTED_BOUNDARY_CODES = {
    "PROTECTED_SECURITY",
    "PROTECTED_DESTRUCTIVE",
    "PROTECTED_IRREVERSIBLE",
    "PROTECTED_EXTERNAL",
    "PROTECTED_PUBLIC_CONTRACT",
    "PROTECTED_DEPENDENCY",
    "PROTECTED_PACKAGE_TOPOLOGY",
    "THIRD_STATE",
    "UNKNOWN_CAPABILITY",
    "SAME_LEVEL_CONFLICT",
    "ROUTINE_CHOICE_UNRESOLVED",
    "RETRY_BUDGET_EXHAUSTED",
}


class ValidationError(Exception):
    """A deterministic contract or fixture failure."""


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValidationError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValidationError(f"{path}: root must be an object")
    return value


def canonical_hash(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def validate_mandate(mandate: dict[str, Any], repo_root: Path) -> None:
    require(mandate.get("schema_version") == 1, "mandate schema_version must be 1")
    require(mandate.get("status") == "unsigned-input", "mandate must remain unsigned-input")
    require(mandate.get("signature") is None, "P0.2 must not sign a production mandate")

    precedence = mandate.get("precedence")
    require(isinstance(precedence, list), "precedence must be a list")
    require([row.get("level") for row in precedence] == [1, 2, 3, 4, 5], "precedence must be total across levels 1..5")

    source_set = mandate.get("source_set", {})
    require(source_set.get("hash_algorithm") == "sha256", "source hash algorithm must be sha256")
    sources = source_set.get("sources")
    require(isinstance(sources, list) and sources, "source_set.sources must be non-empty")
    source_ids: set[str] = set()
    source_paths: set[str] = set()
    for source in sources:
        source_id = source.get("id")
        source_path = source.get("path")
        expected = source.get("sha256")
        require(isinstance(source_id, str) and source_id not in source_ids, f"duplicate/invalid source id: {source_id!r}")
        require(isinstance(source_path, str) and source_path not in source_paths, f"duplicate/invalid source path: {source_path!r}")
        require(source.get("level") in {2, 3, 4}, f"invalid source level for {source_id}")
        require(isinstance(expected, str) and len(expected) == 64, f"invalid source hash for {source_id}")
        resolved = repo_root / source_path
        require(resolved.is_file(), f"frozen source missing: {source_path}")
        require(file_hash(resolved) == expected, f"frozen source hash mismatch: {source_path}")
        source_ids.add(source_id)
        source_paths.add(source_path)

    envelope = mandate.get("envelope", {})
    for key in ("files", "tools", "providers", "model_classes", "efforts", "required_validations", "action_classes"):
        require(isinstance(envelope.get(key), list) and envelope[key], f"envelope.{key} must be non-empty")
    require(set(envelope["action_classes"]) == DECLARED_CLASSES, "action class set must be AUTO/AUTO-FIX/OWNER")
    budget = envelope.get("budget_max")
    require(isinstance(budget, dict) and set(budget) == {"attempts", "parallel_writers", "parallel_readers"}, "budget_max fields are not closed")
    require(all(isinstance(value, int) and value >= 0 for value in budget.values()), "budget maxima must be non-negative integers")
    require(set(mandate.get("protected_boundaries", [])) == EXPECTED_PROTECTED, "protected boundary taxonomy is incomplete")

    retry = mandate.get("retry_policy", {})
    require(retry.get("same_finding_max") == 2, "same_finding_max must remain 2")
    require(retry.get("audit_rounds_max") == 2, "audit_rounds_max must remain 2")
    require(retry.get("fresh_worker") is True, "retry must use a fresh worker")
    require(retry.get("finding_identity_must_match") is True, "AUTO-FIX finding identity must match")
    require(retry.get("acceptance_must_match") is True, "AUTO-FIX acceptance must match")

    reason_schema = mandate.get("decision_reason_schema", {})
    required = reason_schema.get("required")
    require(isinstance(required, list) and len(required) == len(set(required)), "decision reason fields must be unique")
    require(reason_schema.get("pre_side_effect_required") is True, "decision evidence must precede side effects")


def decision(
    case: dict[str, Any],
    mandate: dict[str, Any],
    source_set_hash: str,
    mandate_hash: str,
) -> dict[str, Any]:
    case_id = case["id"]
    requested = case["requested_class"]
    data = case["input"]
    envelope = mandate["envelope"]

    def result(resolved: str, allowed: bool, code: str, sources: list[str], selected: str | None = None) -> dict[str, Any]:
        alternatives = [row["id"] for row in data.get("alternatives", [])]
        return {
            "decision_id": case_id,
            "requested_class": requested,
            "resolved_class": resolved,
            "allowed": allowed,
            "reason_code": code,
            "controlling_sources": sources,
            "source_set_hash": source_set_hash,
            "mandate_hash": mandate_hash,
            "selected_alternative": selected,
            "rejected_alternatives": [item for item in alternatives if item != selected],
            "intent_sequence": f"pre-side-effect:{case_id}",
        }

    if requested not in set(envelope["action_classes"]):
        return result("OWNER", False, "MANDATE_WIDENS_ACTION_CLASS", ["owner-mandate-input"])
    if not set(data.get("files", [])).issubset(envelope["files"]):
        return result("OWNER", False, "MANDATE_WIDENS_FILES", ["root-instructions", "owner-refinements"])
    if not set(data.get("tools", [])).issubset(envelope["tools"]):
        return result("OWNER", False, "MANDATE_WIDENS_TOOLS", ["owner-mandate-input"])
    if data.get("provider", envelope["providers"][0]) not in envelope["providers"]:
        return result("OWNER", False, "MANDATE_WIDENS_PROVIDER", ["owner-mandate-input"])
    if data.get("model_class", envelope["model_classes"][0]) not in envelope["model_classes"]:
        return result("OWNER", False, "MANDATE_WIDENS_MODEL", ["owner-mandate-input"])
    if data.get("effort", envelope["efforts"][0]) not in envelope["efforts"]:
        return result("OWNER", False, "MANDATE_WIDENS_EFFORT", ["owner-mandate-input"])
    budget = data.get("budget", {})
    if any(not isinstance(value, int) or value < 0 or value > envelope["budget_max"][key] for key, value in budget.items() if key in envelope["budget_max"]):
        return result("OWNER", False, "MANDATE_WIDENS_BUDGET", ["owner-mandate-input", "risk-review-loop-budget"])
    if set(budget) - set(envelope["budget_max"]):
        return result("OWNER", False, "MANDATE_WIDENS_BUDGET", ["owner-mandate-input", "risk-review-loop-budget"])
    if "validations" in data and not set(envelope["required_validations"]).issubset(data["validations"]):
        return result("OWNER", False, "MANDATE_WEAKENS_VALIDATION", ["owner-mandate-input"])

    authority_sources = data.get("authority_sources", [])
    if authority_sources:
        top_level = min(row["level"] for row in authority_sources)
        controlling = [row for row in authority_sources if row["level"] == top_level]
        directives = {row["directive"] for row in controlling}
        if len(directives) > 1:
            return result("OWNER", False, "SAME_LEVEL_CONFLICT", [row["id"] for row in controlling])
        if directives == {"OWNER"}:
            return result("OWNER", False, "HIGHER_PRECEDENCE_OWNER", [row["id"] for row in controlling])

    boundary_checks = (
        (data.get("security"), "PROTECTED_SECURITY", ["root-instructions", "authority-policy"]),
        (data.get("destructive"), "PROTECTED_DESTRUCTIVE", ["root-instructions", "authority-policy"]),
        (data.get("external"), "PROTECTED_EXTERNAL", ["owner-intent", "authority-policy"]),
        (data.get("public_contract"), "PROTECTED_PUBLIC_CONTRACT", ["owner-intent", "authority-policy"]),
        (data.get("dependency_change"), "PROTECTED_DEPENDENCY", ["root-instructions", "authority-policy"]),
        (data.get("package_topology_change"), "PROTECTED_PACKAGE_TOPOLOGY", ["root-instructions", "authority-policy"]),
        (data.get("state") == "third", "THIRD_STATE", ["owner-intent", "execution-state-machine"]),
        (data.get("capability") == "unknown", "UNKNOWN_CAPABILITY", ["authority-policy"]),
    )
    for condition, code, sources in boundary_checks:
        if condition:
            return result("OWNER", False, code, sources)
    if data.get("reversible", True) is not True:
        return result("OWNER", False, "PROTECTED_IRREVERSIBLE", ["owner-intent", "authority-policy"])
    if requested == "OWNER":
        return result("OWNER", False, "OWNER_REQUIRED_BY_MANDATE", ["owner-brief"])

    if requested == "AUTO-FIX":
        if data.get("finding_id") != data.get("prior_finding_id"):
            return result("OWNER", False, "FINDING_IDENTITY_CHANGED", ["risk-review-loop-budget"])
        if data.get("acceptance_hash") != data.get("prior_acceptance_hash"):
            return result("OWNER", False, "ACCEPTANCE_CHANGED", ["authority-policy"])
        if data.get("retry_count", 0) >= mandate["retry_policy"]["same_finding_max"]:
            return result("OWNER", False, "RETRY_BUDGET_EXHAUSTED", ["risk-review-loop-budget"])
        return result("AUTO-FIX", True, "AUTO_FIX_BOUNDED", ["authority-policy", "risk-review-loop-budget"])

    alternatives = data.get("alternatives", [])
    if alternatives:
        ranked = sorted((tuple(row["rank"]), row["id"]) for row in alternatives)
        if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
            return result("OWNER", False, "ROUTINE_CHOICE_UNRESOLVED", ["authority-policy"])
        return result("AUTO", True, "ROUTINE_CHOICE_SELECTED", ["authority-policy"], ranked[0][1])
    return result("AUTO", True, "AUTO_LEGAL", ["authority-policy", "root-instructions"])


def validate_cases(cases_doc: dict[str, Any], mandate: dict[str, Any]) -> list[dict[str, Any]]:
    require(cases_doc.get("schema_version") == 1, "cases schema_version must be 1")
    require(cases_doc.get("mandate_id") == mandate.get("mandate_id"), "case bank mandate_id mismatch")
    cases = cases_doc.get("cases")
    require(isinstance(cases, list) and cases, "cases must be non-empty")
    case_ids = [case.get("id") for case in cases]
    require(all(isinstance(case_id, str) and case_id for case_id in case_ids), "every case needs a non-empty id")
    require(len(case_ids) == len(set(case_ids)), "case ids must be unique")

    source_set_hash = canonical_hash(mandate["source_set"])
    mandate_hash = canonical_hash(mandate)
    decisions: list[dict[str, Any]] = []
    expected_codes: set[str] = set()
    class_polarity: set[tuple[str, str]] = set()
    for case in cases:
        require(case.get("polarity") in {"positive", "negative"}, f"{case['id']}: invalid polarity")
        require(isinstance(case.get("input"), dict), f"{case['id']}: input must be an object")
        require(isinstance(case.get("expected"), dict), f"{case['id']}: expected must be an object")
        actual = decision(case, mandate, source_set_hash, mandate_hash)
        expected = case["expected"]
        for key in ("resolved_class", "allowed", "reason_code", "controlling_sources", "selected_alternative"):
            require(actual[key] == expected.get(key), f"{case['id']}: {key} expected {expected.get(key)!r}, got {actual[key]!r}")
        require(set(actual) == set(mandate["decision_reason_schema"]["required"]), f"{case['id']}: decision reason schema mismatch")
        require(actual["intent_sequence"].startswith("pre-side-effect:"), f"{case['id']}: decision is not pre-side-effect")
        expected_codes.add(expected["reason_code"])
        if case["requested_class"] in DECLARED_CLASSES:
            class_polarity.add((case["requested_class"], case["polarity"]))
        decisions.append(actual)

    require(class_polarity == {(action, polarity) for action in DECLARED_CLASSES for polarity in ("positive", "negative")}, "positive/negative fixtures must cover every action class")
    require(EXPECTED_NARROWING_CODES.issubset(expected_codes), "narrowing fixture coverage is incomplete")
    require(EXPECTED_BOUNDARY_CODES.issubset(expected_codes), "protected/refusal fixture coverage is incomplete")
    require("HIGHER_PRECEDENCE_OWNER" in expected_codes, "cross-level precedence fixture is missing")
    require("ROUTINE_CHOICE_SELECTED" in expected_codes, "positive routine-choice fixture is missing")
    require("FINDING_IDENTITY_CHANGED" in expected_codes and "ACCEPTANCE_CHANGED" in expected_codes, "AUTO-FIX identity/acceptance fixtures are incomplete")
    return decisions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mandate", required=True, type=Path)
    parser.add_argument("--cases", required=True, type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        mandate = load_json(args.mandate)
        cases_doc = load_json(args.cases)
        repo_root = Path.cwd().resolve()
        validate_mandate(mandate, repo_root)
        decisions = validate_cases(cases_doc, mandate)
    except ValidationError as exc:
        print(f"authority-validation: FAIL: {exc}", file=sys.stderr)
        return 1
    counts = {name: sum(row["resolved_class"] == name for row in decisions) for name in sorted(DECLARED_CLASSES)}
    print(
        "authority-validation: OK "
        f"({len(decisions)} cases; AUTO={counts['AUTO']}; AUTO-FIX={counts['AUTO-FIX']}; "
        f"OWNER={counts['OWNER']}; narrowing/protected/conflict/retry coverage complete)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
