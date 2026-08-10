#!/usr/bin/env python3
"""Independent stdlib conformance check for authority-policy-v1."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path


CONTRACT_VERSION = "1.0.0"
OPERATIONS = (
    "compile_slice",
    "supersede_pending",
    "dispatch_worker",
    "validate_result",
    "integrate_owned_delta",
    "project_plan_bookkeeping",
)
ACTION_CLASSES = ("AUTO", "AUTO-FIX", "OWNER")
ATTENTION_CLASSES = ("none", "batched", "immediate")
COMMON_PREDICATES = (
    "scope_exact",
    "reversible",
    "capability_known",
    "acceptance_deterministic",
    "source_set_current",
    "preimage_exact",
    "budget_available",
)
PROTECTED_PREDICATES = (
    "security",
    "destructive",
    "irreversible",
    "external",
    "public_contract",
    "dependency_change",
    "package_topology_change",
    "third_state",
    "unknown_capability",
    "same_level_conflict",
    "unresolved_routine_choice",
)
NARROWING_DIMENSIONS = (
    "files",
    "tools",
    "provider",
    "model_class",
    "effort",
    "budget",
    "validations",
    "action_class",
)
OPERATION_REQUIREMENTS = {
    "compile_slice": ("task_contract_allow", "dependency_ready", "input_hashes_current"),
    "supersede_pending": ("prior_pending", "supersedes_hash_exact"),
    "dispatch_worker": ("intent_durable", "route_frozen"),
    "validate_result": ("observation_durable", "validation_argv_frozen"),
    "integrate_owned_delta": ("owned_delta", "backup_verified", "serialized_writer"),
    "project_plan_bookkeeping": ("acceptance_durable", "projection_exact"),
}
OPERATION_PREDICATES = tuple(
    f"{operation}:{predicate}"
    for operation in OPERATIONS
    for predicate in OPERATION_REQUIREMENTS[operation]
)
REASON_CODES = (
    "AUTO_LEGAL",
    "ROUTINE_CHOICE_SELECTED",
    "AUTO_FIX_BOUNDED",
    "OWNER_REQUIRED_BY_MANDATE",
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
    "HIGHER_PRECEDENCE_OWNER",
    "ROUTINE_CHOICE_UNRESOLVED",
    "FINDING_IDENTITY_CHANGED",
    "ACCEPTANCE_CHANGED",
    "RETRY_BUDGET_EXHAUSTED",
    "MANDATE_WIDENS_FILES",
    "MANDATE_WIDENS_TOOLS",
    "MANDATE_WIDENS_PROVIDER",
    "MANDATE_WIDENS_MODEL",
    "MANDATE_WIDENS_EFFORT",
    "MANDATE_WIDENS_BUDGET",
    "MANDATE_WEAKENS_VALIDATION",
    "MANDATE_WIDENS_ACTION_CLASS",
    "SCOPE_NOT_EXACT",
    "ACCEPTANCE_NOT_DETERMINISTIC",
    "SOURCE_DRIFT",
    "PREIMAGE_MISMATCH",
    "BUDGET_EXHAUSTED",
    "OPERATION_CLASS_FORBIDDEN",
    "OPERATION_PRECONDITION_FAILED",
    "UNKNOWN_OPERATION",
)
DECISION_KEYS = {
    "decision_id",
    "operation",
    "requested_class",
    "resolved_class",
    "allowed",
    "reason_code",
    "attention",
    "controlling_sources",
    "source_set_hash",
    "mandate_hash",
    "selected_alternative",
    "rejected_alternatives",
    "intent_sequence",
    "side_effect_authorized",
    "blast_radius",
    "rollback",
    "affected_slices",
    "no_decision_consequence",
    "blocking_dependencies",
}
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")

REASON_SOURCES = {
    "AUTO_LEGAL": ["authority-policy", "root-instructions"],
    "ROUTINE_CHOICE_SELECTED": ["authority-policy"],
    "AUTO_FIX_BOUNDED": ["authority-policy", "risk-review-loop-budget"],
    "OWNER_REQUIRED_BY_MANDATE": ["owner-brief"],
    "PROTECTED_SECURITY": ["root-instructions", "authority-policy"],
    "PROTECTED_DESTRUCTIVE": ["root-instructions", "authority-policy"],
    "PROTECTED_IRREVERSIBLE": ["owner-intent", "authority-policy"],
    "PROTECTED_EXTERNAL": ["owner-intent", "authority-policy"],
    "PROTECTED_PUBLIC_CONTRACT": ["owner-intent", "authority-policy"],
    "PROTECTED_DEPENDENCY": ["root-instructions", "authority-policy"],
    "PROTECTED_PACKAGE_TOPOLOGY": ["root-instructions", "authority-policy"],
    "THIRD_STATE": ["owner-intent", "execution-state-machine"],
    "UNKNOWN_CAPABILITY": ["authority-policy"],
    "ROUTINE_CHOICE_UNRESOLVED": ["authority-policy"],
    "FINDING_IDENTITY_CHANGED": ["risk-review-loop-budget"],
    "ACCEPTANCE_CHANGED": ["authority-policy"],
    "RETRY_BUDGET_EXHAUSTED": ["risk-review-loop-budget"],
    "MANDATE_WIDENS_FILES": ["root-instructions", "owner-refinements"],
    "MANDATE_WIDENS_TOOLS": ["owner-mandate-input"],
    "MANDATE_WIDENS_PROVIDER": ["owner-mandate-input"],
    "MANDATE_WIDENS_MODEL": ["owner-mandate-input"],
    "MANDATE_WIDENS_EFFORT": ["owner-mandate-input"],
    "MANDATE_WIDENS_BUDGET": ["owner-mandate-input", "risk-review-loop-budget"],
    "MANDATE_WEAKENS_VALIDATION": ["owner-mandate-input"],
    "MANDATE_WIDENS_ACTION_CLASS": ["owner-mandate-input"],
    "SCOPE_NOT_EXACT": ["authority-policy", "slice-manifest-v1"],
    "ACCEPTANCE_NOT_DETERMINISTIC": ["authority-policy", "acceptance-rubric-v1"],
    "SOURCE_DRIFT": ["authority-policy", "slice-manifest-v1"],
    "PREIMAGE_MISMATCH": ["authority-policy", "supervisor-run-v1"],
    "BUDGET_EXHAUSTED": ["authority-policy", "risk-review-loop-budget"],
    "OPERATION_CLASS_FORBIDDEN": ["authority-policy", "slice-manifest-v1"],
    "OPERATION_PRECONDITION_FAILED": ["authority-policy", "slice-manifest-v1"],
    "UNKNOWN_OPERATION": ["authority-policy", "slice-manifest-v1"],
}
IMMEDIATE_REASONS = {
    "PROTECTED_SECURITY", "PROTECTED_DESTRUCTIVE", "PROTECTED_IRREVERSIBLE",
}


def canonical_bytes(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def digest(value):
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def declared_set(text, name):
    pattern = rf"<!-- declared-set: {re.escape(name)} -->\s*```text\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise ValueError(f"contract: missing declared set {name}")
    values = tuple(line.strip() for line in match.group(1).splitlines() if line.strip())
    if len(values) != len(set(values)):
        raise ValueError(f"contract: duplicate value in {name}")
    return values


def set_path(root, path, value):
    target = root
    for token in path[:-1]:
        target = target[token]
    target[path[-1]] = copy.deepcopy(value)


def mutate(base, mutations):
    value = copy.deepcopy(base)
    for mutation in mutations:
        set_path(value, mutation["path"], mutation["value"])
    return value


def normalize_legacy(base, case):
    value = copy.deepcopy(base)
    requested = case["requested_class"]
    default_operation = {
        "AUTO": "validate_result",
        "AUTO-FIX": "integrate_owned_delta",
        "OWNER": "project_plan_bookkeeping",
    }.get(requested, "validate_result")
    value["operation"] = default_operation
    value["requested_class"] = requested
    for key, item in case.get("input", {}).items():
        value[key] = copy.deepcopy(item)
    return value


def controlling_sources(reason, authority_sources=None):
    if reason == "SAME_LEVEL_CONFLICT":
        return [row["id"] for row in authority_sources or []]
    if reason == "HIGHER_PRECEDENCE_OWNER":
        levels = [row["level"] for row in authority_sources or []]
        strongest = min(levels)
        return [
            row["id"] for row in authority_sources or []
            if row["level"] == strongest and row["directive"] == "OWNER"
        ]
    return list(REASON_SOURCES[reason])


def decision(value, mandate, decision_id, reason, selected=None, rejected=None):
    allowed = reason in {"AUTO_LEGAL", "ROUTINE_CHOICE_SELECTED", "AUTO_FIX_BOUNDED"}
    resolved = value["requested_class"] if allowed else "OWNER"
    attention = "none" if allowed else ("immediate" if reason in IMMEDIATE_REASONS else "batched")
    sources = controlling_sources(reason, value.get("authority_sources"))
    return {
        "decision_id": decision_id,
        "operation": value.get("operation"),
        "requested_class": value.get("requested_class"),
        "resolved_class": resolved,
        "allowed": allowed,
        "reason_code": reason,
        "attention": attention,
        "controlling_sources": sources,
        "source_set_hash": digest(mandate["source_set"]),
        "mandate_hash": digest(mandate),
        "selected_alternative": selected,
        "rejected_alternatives": list(rejected or []),
        "intent_sequence": value.get("intent_sequence"),
        "side_effect_authorized": allowed,
        "blast_radius": value.get("blast_radius", f"operation:{value.get('operation', 'unknown')}"),
        "rollback": value.get("rollback", "owner-directed" if not allowed else "not-required"),
        "affected_slices": list(value.get("affected_slices", [])),
        "no_decision_consequence": value.get("no_decision_consequence", "side-effect-refused" if not allowed else "none"),
        "blocking_dependencies": list(value.get("blocking_dependencies", [])),
    }


def evaluate(value, mandate, decision_id):
    operation = value.get("operation")
    requested = value.get("requested_class")
    if operation not in OPERATIONS:
        return decision(value, mandate, decision_id, "UNKNOWN_OPERATION")
    if requested not in ACTION_CLASSES:
        return decision(value, mandate, decision_id, "MANDATE_WIDENS_ACTION_CLASS")

    authority_sources = value.get("authority_sources", [])
    if authority_sources:
        strongest = min(row["level"] for row in authority_sources)
        controlling = [row for row in authority_sources if row["level"] == strongest]
        directives = {row["directive"] for row in controlling}
        if len(directives) != 1:
            value = copy.deepcopy(value)
            value["authority_sources"] = controlling
            return decision(value, mandate, decision_id, "SAME_LEVEL_CONFLICT")
        if directives == {"OWNER"}:
            value = copy.deepcopy(value)
            value["authority_sources"] = controlling
            return decision(value, mandate, decision_id, "HIGHER_PRECEDENCE_OWNER")

    protected = (
        (value.get("security") is True, "PROTECTED_SECURITY"),
        (value.get("destructive") is True, "PROTECTED_DESTRUCTIVE"),
        (value.get("reversible") is not True, "PROTECTED_IRREVERSIBLE"),
        (value.get("external") is True, "PROTECTED_EXTERNAL"),
        (value.get("public_contract") is True, "PROTECTED_PUBLIC_CONTRACT"),
        (value.get("dependency_change") is True, "PROTECTED_DEPENDENCY"),
        (value.get("package_topology_change") is True, "PROTECTED_PACKAGE_TOPOLOGY"),
        (value.get("state") != "known", "THIRD_STATE"),
        (
            value.get("capability") != "known" or value.get("capability_known") is not True,
            "UNKNOWN_CAPABILITY",
        ),
    )
    for applies, reason in protected:
        if applies:
            return decision(value, mandate, decision_id, reason)

    envelope = mandate["envelope"]
    if not set(value.get("files", [])).issubset(envelope["files"]):
        return decision(value, mandate, decision_id, "MANDATE_WIDENS_FILES")
    if not set(value.get("tools", [])).issubset(envelope["tools"]):
        return decision(value, mandate, decision_id, "MANDATE_WIDENS_TOOLS")
    if value.get("provider") not in envelope["providers"]:
        return decision(value, mandate, decision_id, "MANDATE_WIDENS_PROVIDER")
    if value.get("model_class") not in envelope["model_classes"]:
        return decision(value, mandate, decision_id, "MANDATE_WIDENS_MODEL")
    if value.get("effort") not in envelope["efforts"]:
        return decision(value, mandate, decision_id, "MANDATE_WIDENS_EFFORT")
    budget = value.get("budget")
    maxima = envelope["budget_max"]
    if (
        not isinstance(budget, dict)
        or set(budget) != set(maxima)
        or any(not isinstance(budget[key], int) or budget[key] < 0 for key in maxima)
        or any(budget[key] > maxima[key] for key in maxima)
    ):
        return decision(value, mandate, decision_id, "MANDATE_WIDENS_BUDGET")
    if not set(envelope["required_validations"]).issubset(value.get("validations", [])):
        return decision(value, mandate, decision_id, "MANDATE_WEAKENS_VALIDATION")

    common = (
        (value.get("scope_exact") is not True, "SCOPE_NOT_EXACT"),
        (value.get("acceptance_deterministic") is not True, "ACCEPTANCE_NOT_DETERMINISTIC"),
        (value.get("source_set_current") is not True, "SOURCE_DRIFT"),
        (value.get("preimage_exact") is not True, "PREIMAGE_MISMATCH"),
        (value.get("budget_available") is not True, "BUDGET_EXHAUSTED"),
    )
    for applies, reason in common:
        if applies:
            return decision(value, mandate, decision_id, reason)

    operation_context = value.get("operation_context", {})
    if any(operation_context.get(name) is not True for name in OPERATION_REQUIREMENTS[operation]):
        return decision(value, mandate, decision_id, "OPERATION_PRECONDITION_FAILED")

    alternatives = value.get("alternatives", [])
    selected = None
    rejected = []
    if alternatives:
        if (
            not all(isinstance(row.get("id"), str) and isinstance(row.get("rank"), list) for row in alternatives)
            or len({row["id"] for row in alternatives}) != len(alternatives)
        ):
            return decision(value, mandate, decision_id, "ROUTINE_CHOICE_UNRESOLVED")
        best_rank = min(tuple(row["rank"]) for row in alternatives)
        best = [row for row in alternatives if tuple(row["rank"]) == best_rank]
        if len(best) != 1:
            return decision(value, mandate, decision_id, "ROUTINE_CHOICE_UNRESOLVED")
        selected = best[0]["id"]
        rejected = [row["id"] for row in alternatives if row["id"] != selected]

    if requested == "OWNER":
        return decision(value, mandate, decision_id, "OWNER_REQUIRED_BY_MANDATE")
    if requested == "AUTO-FIX" and operation != "integrate_owned_delta":
        return decision(value, mandate, decision_id, "OPERATION_CLASS_FORBIDDEN")
    if requested == "AUTO-FIX":
        if value.get("finding_id") != value.get("prior_finding_id"):
            return decision(value, mandate, decision_id, "FINDING_IDENTITY_CHANGED")
        if value.get("acceptance_hash") != value.get("prior_acceptance_hash"):
            return decision(value, mandate, decision_id, "ACCEPTANCE_CHANGED")
        retry_count = value.get("retry_count")
        if not isinstance(retry_count, int) or retry_count < 0 or retry_count >= 2:
            return decision(value, mandate, decision_id, "RETRY_BUDGET_EXHAUSTED")
        return decision(
            value, mandate, decision_id,
            "ROUTINE_CHOICE_SELECTED" if selected else "AUTO_FIX_BOUNDED",
            selected, rejected,
        )
    return decision(
        value, mandate, decision_id,
        "ROUTINE_CHOICE_SELECTED" if selected else "AUTO_LEGAL",
        selected, rejected,
    )


def validate_decision(record):
    if set(record) != DECISION_KEYS:
        raise ValueError(f"decision record keys drifted: {sorted(set(record) ^ DECISION_KEYS)}")
    if record["resolved_class"] not in ACTION_CLASSES:
        raise ValueError("decision resolved_class is unknown")
    if record["attention"] not in ATTENTION_CLASSES:
        raise ValueError("decision attention is unknown")
    if record["reason_code"] not in REASON_CODES:
        raise ValueError("decision reason_code is unknown")
    if not HEX64_RE.fullmatch(record["source_set_hash"]):
        raise ValueError("decision source_set_hash is invalid")
    if not HEX64_RE.fullmatch(record["mandate_hash"]):
        raise ValueError("decision mandate_hash is invalid")
    if not isinstance(record["intent_sequence"], int) or record["intent_sequence"] < 1:
        raise ValueError("decision intent_sequence is invalid")
    if record["allowed"] != record["side_effect_authorized"]:
        raise ValueError("decision side-effect flag differs from allowed")
    if record["resolved_class"] == "OWNER" and record["side_effect_authorized"]:
        raise ValueError("OWNER decision authorizes a side effect")
    if (not isinstance(record["blast_radius"], str) or not record["blast_radius"]
            or not isinstance(record["rollback"], str) or not record["rollback"]
            or not isinstance(record["affected_slices"], list)
            or any(not isinstance(item, str) or not item for item in record["affected_slices"])
            or not isinstance(record["no_decision_consequence"], str)
            or not record["no_decision_consequence"]
            or not isinstance(record["blocking_dependencies"], list)
            or any(not isinstance(item, str) or not item for item in record["blocking_dependencies"])):
        raise ValueError("decision attention-packet fields are invalid")


def compare(case_id, record, expected):
    validate_decision(record)
    for key, value in expected.items():
        if record.get(key) != value:
            raise ValueError(f"{case_id}: {key}: expected {value!r}, observed {record.get(key)!r}")


def run_case(base, mandate, case_id, mutations, expected):
    value = mutate(base, mutations)
    record = evaluate(value, mandate, case_id)
    expected_record = expected if isinstance(expected, dict) else {"reason_code": expected}
    if not record["allowed"] and "allowed" not in expected_record:
        expected_record = {**expected_record, "resolved_class": "OWNER", "allowed": False}
    compare(case_id, record, expected_record)
    return record["reason_code"]


def validate_cases(data, mandate, p0_data):
    base = data["base_input"]
    observed_reasons = set()
    decision_count = 0

    expected_pairs = {(operation, action) for operation in OPERATIONS for action in ACTION_CLASSES}
    observed_pairs = {(row["operation"], row["requested_class"]) for row in data["operation_class_cases"]}
    if observed_pairs != expected_pairs or len(data["operation_class_cases"]) != len(expected_pairs):
        raise ValueError("operation/action-class cartesian coverage is incomplete")
    for row in data["operation_class_cases"]:
        mutations = [
            {"path": ["operation"], "value": row["operation"]},
            {"path": ["requested_class"], "value": row["requested_class"]},
        ]
        observed_reasons.add(run_case(base, mandate, row["id"], mutations, row["expected"]))
        decision_count += 1

    routine_operations = {row["operation"] for row in data["routine_positive_cases"]}
    if routine_operations != set(OPERATIONS) or len(data["routine_positive_cases"]) != len(OPERATIONS):
        raise ValueError("positive routine coverage must contain every operation exactly once")
    for row in data["routine_positive_cases"]:
        selected = row["selected"]
        alternatives = [
            {"id": selected, "rank": [1, 0, 0, 0, 0, -3, 20]},
            {"id": f"new-{row['operation']}", "rank": [2, 1, 0, 0, 1, -2, 30]},
        ]
        mutations = [
            {"path": ["operation"], "value": row["operation"]},
            {"path": ["requested_class"], "value": "AUTO"},
            {"path": ["alternatives"], "value": alternatives},
        ]
        expected = {
            "resolved_class": "AUTO", "allowed": True,
            "reason_code": "ROUTINE_CHOICE_SELECTED", "attention": "none",
            "selected_alternative": selected,
        }
        observed_reasons.add(run_case(base, mandate, row["id"], mutations, expected))
        decision_count += 1

    expected_predicates = set(COMMON_PREDICATES) | set(PROTECTED_PREDICATES)
    observed_predicates = {row["predicate"] for row in data["predicate_cases"]}
    if observed_predicates != expected_predicates or len(data["predicate_cases"]) != len(expected_predicates):
        raise ValueError("common/protected predicate coverage is incomplete or duplicated")
    for row in data["predicate_cases"]:
        for operation in OPERATIONS:
            for action in ACTION_CLASSES:
                case_id = f"{row['id']}:{operation}:{action}"
                mutations = row["mutations"] + [
                    {"path": ["operation"], "value": operation},
                    {"path": ["requested_class"], "value": action},
                ]
                observed_reasons.add(run_case(base, mandate, case_id, mutations, row["expected"]))
                decision_count += 1

    observed_dimensions = {row["dimension"] for row in data["narrowing_cases"]}
    if observed_dimensions != set(NARROWING_DIMENSIONS) or len(data["narrowing_cases"]) != len(NARROWING_DIMENSIONS):
        raise ValueError("narrowing coverage is incomplete or duplicated")
    for row in data["narrowing_cases"]:
        for operation in OPERATIONS:
            for action in ACTION_CLASSES:
                mutations = list(row["mutations"])
                mutations.append({"path": ["operation"], "value": operation})
                if row["dimension"] != "action_class":
                    mutations.append({"path": ["requested_class"], "value": action})
                case_id = f"{row['id']}:{operation}:{action}"
                observed_reasons.add(run_case(base, mandate, case_id, mutations, row["expected"]))
                decision_count += 1

    observed_operation_predicates = {
        f"{row['operation']}:{row['predicate']}" for row in data["operation_predicate_cases"]
    }
    if (
        observed_operation_predicates != set(OPERATION_PREDICATES)
        or len(data["operation_predicate_cases"]) != len(OPERATION_PREDICATES)
    ):
        raise ValueError("operation predicate coverage is incomplete or duplicated")
    for row in data["operation_predicate_cases"]:
        for action in ACTION_CLASSES:
            mutations = [
                {"path": ["operation"], "value": row["operation"]},
                {"path": ["requested_class"], "value": action},
                {"path": ["operation_context", row["predicate"]], "value": False},
            ]
            case_id = f"{row['id']}:{action}"
            observed_reasons.add(run_case(base, mandate, case_id, mutations, "OPERATION_PRECONDITION_FAILED"))
            decision_count += 1

    for row in data["auto_fix_cases"]:
        mutations = [
            {"path": ["operation"], "value": "integrate_owned_delta"},
            {"path": ["requested_class"], "value": "AUTO-FIX"},
        ] + row["mutations"]
        observed_reasons.add(run_case(base, mandate, row["id"], mutations, row["expected"]))
        decision_count += 1

    for row in data["precedence_cases"]:
        mutations = [{"path": ["authority_sources"], "value": row["sources"]}]
        observed_reasons.add(run_case(base, mandate, row["id"], mutations, row["expected"]))
        decision_count += 1

    for section in ("precedence_multifault_cases", "unknown_cases"):
        for row in data[section]:
            observed_reasons.add(run_case(base, mandate, row["id"], row["mutations"], row["expected"]))
            decision_count += 1

    for case in p0_data["cases"]:
        value = normalize_legacy(base, case)
        record = evaluate(value, mandate, f"legacy:{case['id']}")
        compare(case["id"], record, case["expected"])
        observed_reasons.add(record["reason_code"])
        decision_count += 1

    missing_reasons = set(REASON_CODES) - observed_reasons
    if missing_reasons:
        raise ValueError(f"reason coverage incomplete: {sorted(missing_reasons)}")
    return decision_count, len(p0_data["cases"]), len(observed_reasons)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--p0-cases", required=True)
    args = parser.parse_args(argv)
    try:
        contract_text = Path(args.contract).read_text(encoding="utf-8")
        data = json.loads(Path(args.cases).read_text(encoding="utf-8"))
        p0_path = Path(args.p0_cases)
        p0_data = json.loads(p0_path.read_text(encoding="utf-8"))
        mandate = json.loads(p0_path.with_name(data["legacy_mandate_file"]).read_text(encoding="utf-8"))
        if data.get("schema_version") != "authority-policy-cases-v1":
            raise ValueError("cases: unknown schema_version")
        if data.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("cases: contract_version is not frozen v1")
        if p0_data.get("schema_version") != 1:
            raise ValueError("P0 cases: unknown schema_version")
        if mandate.get("schema_version") != 1 or mandate.get("status") != "unsigned-input":
            raise ValueError("P0 mandate: unexpected schema or status")
        declared = {
            "operations": OPERATIONS,
            "action_classes": ACTION_CLASSES,
            "attention_classes": ATTENTION_CLASSES,
            "common_predicates": COMMON_PREDICATES,
            "protected_predicates": PROTECTED_PREDICATES,
            "narrowing_dimensions": NARROWING_DIMENSIONS,
            "operation_predicates": OPERATION_PREDICATES,
            "reason_codes": REASON_CODES,
        }
        for name, expected in declared.items():
            if declared_set(contract_text, name) != expected:
                raise ValueError(f"contract declared set differs from validator: {name}")
        decision_count, legacy_count, reason_count = validate_cases(data, mandate, p0_data)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"authority-policy: FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "authority-policy: OK "
        f"({decision_count} decisions; {legacy_count} P0 compatibility cases; "
        f"{reason_count} reason classes; {len(OPERATIONS)} operations)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
