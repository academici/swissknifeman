#!/usr/bin/env python3
"""Validate the frozen continue-first acceptance bank without candidate runtime imports."""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any


SCHEMA = "urn:swissknifeman:task:continue-first-acceptance:v1"
SCHEMA_VERSION = "1.0.0"
PLAN_ID = "2026.08.12-№1-TASK-RESILIENCE"
REQUIREMENT_IDS = tuple([f"R{index}" for index in range(1, 9)] + [f"O{index}" for index in range(1, 15)])
PHASES = {f"P{index}" for index in range(1, 7)}
INPUT_CLASSES = {
    "active-plan-layout",
    "audit-trigger",
    "comment-reference",
    "external-block-candidate",
    "identity",
    "local-reversible-defect",
    "perplexity-gate",
    "phase-acceptance",
    "plan-anchor",
    "provider-final",
    "roadmap-batch",
    "route-evidence",
    "terminal-block-candidate",
    "terminal-handoff",
    "views-history-command",
}
ACTIONS = {
    "accept",
    "continue",
    "create-tag",
    "emit-receipt",
    "gather-rag",
    "keep-active",
    "local-repair",
    "rag-pending",
    "refuse",
    "refuse-final",
    "retire-v1-execution",
    "reuse-audit",
    "rollout-registered",
    "terminal-block",
}
STATUSES = {"unchanged", "in-progress", "terminal", "blocked"}
RAG_STATUSES = {"not-required", "missing", "pending", "verified"}
RAG_PROVIDERS = {"none", "perplexity-web"}
REVIEW_CONTEXTS = {"none", "isolated-child-return"}
REVIEW_VERDICTS = {
    "none",
    "JUSTIFIED",
    "AVOIDABLE",
    "INSUFFICIENT_EVIDENCE",
    "OUT_OF_SCOPE",
    "MALFORMED",
}
RECEIPT_RECOMMENDATIONS = {"not-applicable", "exact-persisted-next"}
RECEIPT_RESULTS = {"absent", "present", "rejected"}

TOP_KEYS = {"$schema", "schema_version", "plan_id", "required_requirement_ids", "cases"}
CASE_KEYS = {"id", "requirement_id", "owning_phase", "input_class", "given", "expected"}
EXPECTED_KEYS = {"action", "status", "attempt_delta", "rag", "review", "receipt"}
RAG_KEYS = {"required", "status", "provider", "evidence_min"}
REVIEW_KEYS = {"required", "count", "context", "verdict", "actor_distinct"}
RECEIPT_KEYS = {"required", "terminal", "recommendation", "result"}


class AcceptanceError(ValueError):
    """One or more closed-bank invariants failed."""


def _closed_object(value: Any, expected_keys: set[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise AcceptanceError(f"{where}: expected object")
    actual_keys = set(value)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        raise AcceptanceError(f"{where}: closed keys mismatch; missing={missing}; extra={extra}")
    return value


def _nonempty_string(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise AcceptanceError(f"{where}: expected non-empty string")
    return value


def _enum(value: Any, allowed: set[str], where: str) -> str:
    checked = _nonempty_string(value, where)
    if checked not in allowed:
        raise AcceptanceError(f"{where}: unsupported value {checked!r}")
    return checked


def validate_bank(bank: Any) -> None:
    root = _closed_object(bank, TOP_KEYS, "bank")
    if root["$schema"] != SCHEMA:
        raise AcceptanceError("bank.$schema: unexpected schema")
    if root["schema_version"] != SCHEMA_VERSION:
        raise AcceptanceError("bank.schema_version: unexpected version")
    if root["plan_id"] != PLAN_ID:
        raise AcceptanceError("bank.plan_id: unexpected plan")

    required_ids = root["required_requirement_ids"]
    if not isinstance(required_ids, list) or required_ids != list(REQUIREMENT_IDS):
        raise AcceptanceError("bank.required_requirement_ids: exact ordered requirement set required")

    cases = root["cases"]
    if not isinstance(cases, list) or not cases:
        raise AcceptanceError("bank.cases: non-empty array required")

    case_ids: set[str] = set()
    covered_requirements: list[str] = []
    for index, raw_case in enumerate(cases):
        where = f"bank.cases[{index}]"
        case = _closed_object(raw_case, CASE_KEYS, where)
        case_id = _nonempty_string(case["id"], f"{where}.id")
        if case_id in case_ids:
            raise AcceptanceError(f"{where}.id: duplicate {case_id!r}")
        case_ids.add(case_id)

        requirement_id = _nonempty_string(case["requirement_id"], f"{where}.requirement_id")
        if requirement_id not in REQUIREMENT_IDS:
            raise AcceptanceError(f"{where}.requirement_id: unknown {requirement_id!r}")
        covered_requirements.append(requirement_id)
        _enum(case["owning_phase"], PHASES, f"{where}.owning_phase")
        input_class = _enum(case["input_class"], INPUT_CLASSES, f"{where}.input_class")
        if not isinstance(case["given"], dict) or not case["given"]:
            raise AcceptanceError(f"{where}.given: non-empty object required")

        expected = _closed_object(case["expected"], EXPECTED_KEYS, f"{where}.expected")
        _enum(expected["action"], ACTIONS, f"{where}.expected.action")
        _enum(expected["status"], STATUSES, f"{where}.expected.status")
        if type(expected["attempt_delta"]) is not int or expected["attempt_delta"] not in {0, 1}:
            raise AcceptanceError(f"{where}.expected.attempt_delta: expected 0 or 1")

        rag = _closed_object(expected["rag"], RAG_KEYS, f"{where}.expected.rag")
        if type(rag["required"]) is not bool:
            raise AcceptanceError(f"{where}.expected.rag.required: expected boolean")
        rag_status = _enum(rag["status"], RAG_STATUSES, f"{where}.expected.rag.status")
        rag_provider = _enum(rag["provider"], RAG_PROVIDERS, f"{where}.expected.rag.provider")
        if type(rag["evidence_min"]) is not int or rag["evidence_min"] < 0:
            raise AcceptanceError(f"{where}.expected.rag.evidence_min: expected non-negative integer")

        external = input_class in {"external-block-candidate", "perplexity-gate"}
        if external and not rag["required"]:
            raise AcceptanceError(f"{where}: external case must require RAG")
        if external and rag_provider != "perplexity-web":
            raise AcceptanceError(f"{where}: external case must name perplexity-web")
        if external and rag_status == "verified" and rag["evidence_min"] < 1:
            raise AcceptanceError(f"{where}: verified external case needs evidence")
        if not rag["required"] and (rag_status != "not-required" or rag_provider != "none" or rag["evidence_min"] != 0):
            raise AcceptanceError(f"{where}: non-RAG case must use the exact not-required predicate")

        review = _closed_object(expected["review"], REVIEW_KEYS, f"{where}.expected.review")
        if type(review["required"]) is not bool or type(review["actor_distinct"]) is not bool:
            raise AcceptanceError(f"{where}.expected.review: boolean predicates required")
        if type(review["count"]) is not int or review["count"] not in {0, 1}:
            raise AcceptanceError(f"{where}.expected.review.count: expected 0 or 1")
        review_context = _enum(review["context"], REVIEW_CONTEXTS, f"{where}.expected.review.context")
        review_verdict = _enum(review["verdict"], REVIEW_VERDICTS, f"{where}.expected.review.verdict")
        if review["required"]:
            if review["count"] != 1 or review_context != "isolated-child-return" or not review["actor_distinct"]:
                raise AcceptanceError(f"{where}: required review must be one distinct isolated-child-return")
        elif review["count"] != 0 or review_context != "none" or review_verdict != "none" or review["actor_distinct"]:
            raise AcceptanceError(f"{where}: non-review case must use exact absent predicate")

        receipt = _closed_object(expected["receipt"], RECEIPT_KEYS, f"{where}.expected.receipt")
        if type(receipt["required"]) is not bool or type(receipt["terminal"]) is not bool:
            raise AcceptanceError(f"{where}.expected.receipt: boolean predicates required")
        _enum(receipt["recommendation"], RECEIPT_RECOMMENDATIONS, f"{where}.expected.receipt.recommendation")
        _enum(receipt["result"], RECEIPT_RESULTS, f"{where}.expected.receipt.result")

    missing = [requirement_id for requirement_id in REQUIREMENT_IDS if requirement_id not in covered_requirements]
    if missing:
        raise AcceptanceError(f"bank.cases: missing requirement coverage {missing}")


def _assert_rejected(bank: dict[str, Any], mutation: str) -> None:
    try:
        validate_bank(bank)
    except AcceptanceError:
        return
    raise AcceptanceError(f"negative mutation accepted: {mutation}")


def validate_negative_mutations(bank: dict[str, Any]) -> None:
    deleted_case = copy.deepcopy(bank)
    target_requirement = REQUIREMENT_IDS[0]
    deleted_case["cases"] = [
        case for case in deleted_case["cases"] if case["requirement_id"] != target_requirement
    ]
    _assert_rejected(deleted_case, "deleted required case")

    external_without_rag = copy.deepcopy(bank)
    external_case = next(
        case
        for case in external_without_rag["cases"]
        if case["input_class"] in {"external-block-candidate", "perplexity-gate"}
    )
    external_case["expected"]["rag"] = {
        "required": False,
        "status": "not-required",
        "provider": "none",
        "evidence_min": 0,
    }
    _assert_rejected(external_without_rag, "external case without RAG predicate")


def main() -> int:
    default_bank = Path(__file__).with_name("continue-first-acceptance-v1.json")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bank", nargs="?", type=Path, default=default_bank)
    args = parser.parse_args()
    try:
        bank = json.loads(args.bank.read_text(encoding="utf-8"))
        validate_bank(bank)
        validate_negative_mutations(bank)
    except (OSError, json.JSONDecodeError, AcceptanceError) as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {len(bank['cases'])} cases; full requirement coverage; negative mutations rejected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
