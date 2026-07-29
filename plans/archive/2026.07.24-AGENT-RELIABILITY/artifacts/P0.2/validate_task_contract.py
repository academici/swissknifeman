#!/usr/bin/env python3
"""P0.2 — Task Contract v1 validator (stdlib-only).

Owner item: plans/2026.07.24-AGENT-RELIABILITY P0.2 (D5/D8/D26/D30).

Three jobs, no more:

1. Validate every declared example contract against the committed JSON schema
   `root/contracts/task-contract-v1.schema.json` (a deterministic subset
   interpreter — no third-party jsonschema).
2. Run the two checked boundaries the contract exists for — the pre-mutation
   predicate and the pre-final predicate — and compare the produced typed
   reason code with the expectation declared in the examples file. A negative
   example that fails for the WRONG reason is a failure, not a pass.
3. Prove the P0.1 corpus coverage claim: every `kind == "critical"` case in the
   committed corpus is mapped to an exact contract field AND an exact check,
   and the single `control` case is declared as a control (never scored as a
   failure).

The contract is generated/validated state: `version.content_hash` is recomputed
from the canonical payload, never trusted as written. `--rehash` is the
authoring mode that writes the recomputed hashes back into the examples file.

Exit code 0 = every assertion holds. Any failure prints `FAIL: ...` lines and
exits 1. No network, no writes outside the examples file (and only under
`--rehash`).
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys

SCHEMA_VERSION = "task-contract/v1"
EXAMPLES_SCHEMA_VERSION = "task-contract-examples/v1"

# Ordered ladders. Index = rank; a lower index wins a conflict.
CARRIER_PRECEDENCE = [
    "owner-instruction",
    "plan-decision",
    "item-spec",
    "package-canon",
    "handoff-carrier",
    "incidental-diagnostic",
]
MODEL_CLASS_ORDER = ["economy", "implementation", "frontier"]
EFFORT_ORDER = ["low", "medium", "high", "xhigh", "max"]

# Evidence proof classes that may satisfy a deterministic acceptance predicate
# (D30: `pinned-not-recomputable`/`unknown` may ground a hypothesis, never a
# deterministic acceptance predicate).
DETERMINISTIC_PROOF_CLASSES = {"recomputed", "cross-checked"}

# Keys partitioned between the root supervisory session and a subagent slice.
SLICE_PARTITION_KEYS = {
    "goal",
    "must",
    "never",
    "done",
    "authority",
    "next",
    "route",
    "version",
    "evidence",
    "portability",
    "conflicts",
}
SLICE_SUBAGENT_REQUIRED = {"goal", "must", "never", "done", "authority", "next", "route", "version"}
SLICE_ROOT_ONLY_REQUIRED = {"evidence", "portability", "conflicts"}

# A repo-relative, committed-or-produced execution input. Anything else is a
# provenance string and may never be an execution input (D25/D26).
NON_PORTABLE_PREFIXES = ("/", "~", "../", "tmp/")
NON_PORTABLE_SUBSTRINGS = ("/../", "/tmp/", "://")

CHECK_ID_RE = re.compile(r"^(pre-mutation|pre-final|schema):[A-Z_]+$")


# --------------------------------------------------------------------------
# Minimal JSON Schema subset interpreter
# --------------------------------------------------------------------------


def _type_ok(value, type_name: str) -> bool:
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    if type_name == "null":
        return value is None
    raise ValueError("unsupported schema type: %s" % type_name)


def _resolve(root: dict, ref: str) -> dict:
    if not ref.startswith("#/"):
        raise ValueError("unsupported $ref (only local pointers): %s" % ref)
    node = root
    for part in ref[2:].split("/"):
        node = node[part]
    return node


def validate_schema(instance, schema: dict, root: dict, path: str = "$") -> list:
    """Return a list of human-readable violations (empty list = valid)."""
    errors = []

    if "$ref" in schema:
        return validate_schema(instance, _resolve(root, schema["$ref"]), root, path)

    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            if not validate_schema(instance, branch, root, path):
                return []
        return ["%s: matches no anyOf branch" % path]

    if "const" in schema and instance != schema["const"]:
        errors.append("%s: expected const %r, got %r" % (path, schema["const"], instance))

    if "enum" in schema and instance not in schema["enum"]:
        errors.append("%s: %r not in enum %r" % (path, instance, schema["enum"]))

    if "type" in schema:
        declared = schema["type"]
        names = declared if isinstance(declared, list) else [declared]
        if not any(_type_ok(instance, name) for name in names):
            errors.append("%s: expected type %r, got %s" % (path, declared, type(instance).__name__))
            return errors

    if isinstance(instance, str):
        pattern = schema.get("pattern")
        if pattern and not re.search(pattern, instance):
            errors.append("%s: %r does not match %s" % (path, instance, pattern))
        min_length = schema.get("minLength")
        if min_length is not None and len(instance) < min_length:
            errors.append("%s: shorter than minLength %d" % (path, min_length))

    if isinstance(instance, int) and not isinstance(instance, bool):
        minimum = schema.get("minimum")
        if minimum is not None and instance < minimum:
            errors.append("%s: %d below minimum %d" % (path, instance, minimum))

    if isinstance(instance, list):
        min_items = schema.get("minItems")
        if min_items is not None and len(instance) < min_items:
            errors.append("%s: %d items, minItems %d" % (path, len(instance), min_items))
        item_schema = schema.get("items")
        if item_schema is not None:
            for index, element in enumerate(instance):
                errors.extend(validate_schema(element, item_schema, root, "%s[%d]" % (path, index)))

    if isinstance(instance, dict):
        for key in schema.get("required", []):
            if key not in instance:
                errors.append("%s: missing required key %r" % (path, key))
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            for key in instance:
                if key not in properties:
                    errors.append("%s: unexpected key %r" % (path, key))
        for key, sub_schema in properties.items():
            if key in instance:
                errors.extend(validate_schema(instance[key], sub_schema, root, "%s.%s" % (path, key)))

    return errors


# --------------------------------------------------------------------------
# Contract identity
# --------------------------------------------------------------------------


def canonical_payload(contract: dict) -> dict:
    """The hashed payload: the contract minus its own declared hash."""
    payload = copy.deepcopy(contract)
    payload.get("version", {}).pop("content_hash", None)
    return payload


def content_hash(contract: dict) -> str:
    blob = json.dumps(canonical_payload(contract), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Checked boundaries
# --------------------------------------------------------------------------


def _rank(order: list, value: str) -> int:
    return order.index(value)


def pre_mutation(contract: dict):
    """Ordered pre-mutation predicate. Returns None (allow) or a typed code."""
    if contract["version"]["content_hash"] != content_hash(contract):
        return "VERSION_HASH_MISMATCH"

    for conflict in contract["conflicts"]:
        if conflict["resolution"] == "unknown":
            return "CONFLICT_UNRESOLVED"

    for conflict in contract["conflicts"]:
        winner = _rank(CARRIER_PRECEDENCE, conflict["winner"]["carrier_class"])
        loser = _rank(CARRIER_PRECEDENCE, conflict["loser"]["carrier_class"])
        if winner >= loser:
            return "CONFLICT_PRECEDENCE_VIOLATION"

    nxt = contract["next"]
    if nxt["origin"] == "diagnostic":
        return "NEXT_CHANGED_WITHOUT_TRANSITION"
    if nxt["origin"] == "typed-finding" and nxt["changed_by"] is None:
        return "NEXT_CHANGED_WITHOUT_TRANSITION"
    if nxt["origin"] == "approved-goal" and nxt["changed_by"] is not None:
        return "NEXT_CHANGED_WITHOUT_TRANSITION"

    portability = contract["portability"]
    provenance_only = set(portability["provenance_only"])
    for entry in portability["execution_inputs"]:
        path = entry["path"]
        if path in provenance_only:
            return "PORTABILITY_EXTERNAL_INPUT"
        if path.startswith(NON_PORTABLE_PREFIXES) or any(part in path for part in NON_PORTABLE_SUBSTRINGS):
            return "PORTABILITY_EXTERNAL_INPUT"
        if entry["kind"] == "produced-by-predecessor" and not entry["producer"]:
            return "PORTABILITY_INPUT_MISSING"

    if portability["tier"] == "committed-bundle" and not portability["execution_inputs"]:
        return "PORTABILITY_INPUT_MISSING"

    route = contract["route"]
    if _rank(MODEL_CLASS_ORDER, route["actual"]["model_class"]) < _rank(
        MODEL_CLASS_ORDER, route["required"]["model_class"]
    ):
        return "ROUTE_UNDERSHOOT"
    if _rank(EFFORT_ORDER, route["actual"]["effort"]) < _rank(EFFORT_ORDER, route["required"]["effort"]):
        return "ROUTE_UNDERSHOOT"

    for capability in route["capabilities"]:
        if capability["support"] not in ("native", "adapted"):
            return "CAPABILITY_UNSUPPORTED"

    authority = contract["authority"]
    if authority["observed_rounds"] > authority["loop_budget"]["audit_rounds_max"]:
        return "LOOP_BUDGET_EXCEEDED"
    if authority["class"] == "owner-gate" and not authority["granted"]:
        return "AUTHORITY_BOUNDARY"

    subagent = set(contract["slice"]["subagent_keys"])
    root_only = set(contract["slice"]["root_only_keys"])
    if subagent & root_only:
        return "SLICE_INCOMPLETE"
    if subagent | root_only != SLICE_PARTITION_KEYS:
        return "SLICE_INCOMPLETE"
    if not SLICE_SUBAGENT_REQUIRED <= subagent:
        return "SLICE_INCOMPLETE"
    if not SLICE_ROOT_ONLY_REQUIRED <= root_only:
        return "SLICE_INCOMPLETE"

    evidence_ids = {item["id"] for item in contract["evidence"]}
    cold_start = contract["cold_start"]
    if not set(cold_start["reads"]) <= evidence_ids:
        return "COLD_START_INCOMPLETE"
    if cold_start["carrier"] != nxt["carrier"]:
        return "COLD_START_INCOMPLETE"

    return None


def pre_final(contract: dict):
    """Ordered pre-final predicate. Returns None (allow) or a typed code."""
    acceptance = contract["done"]["public_acceptance"]
    if not any(entry["scope"] == "public" for entry in acceptance):
        return "ACCEPTANCE_NOT_PUBLIC"

    by_id = {item["id"]: item for item in contract["evidence"]}
    for entry in acceptance:
        if entry["evidence_ref"] not in by_id:
            return "EVIDENCE_REF_UNKNOWN"

    for entry in acceptance:
        if entry["scope"] != "public":
            continue
        proof_class = by_id[entry["evidence_ref"]]["proof_class"]
        if proof_class not in DETERMINISTIC_PROOF_CLASSES:
            return "EVIDENCE_PROOF_CLASS_INSUFFICIENT"

    return None


# --------------------------------------------------------------------------
# Examples
# --------------------------------------------------------------------------


def merge_patch(target, patch):
    """RFC 7386 JSON merge patch: a null value deletes the key."""
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    if not isinstance(target, dict):
        target = {}
    result = copy.deepcopy(target)
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
        else:
            result[key] = merge_patch(result.get(key), value)
    return result


def materialize(document: dict) -> dict:
    """Return {case_id: contract} for every declared example and mutation."""
    cases = {}
    for example in document["examples"]:
        cases[example["id"]] = copy.deepcopy(example["contract"])
    for mutation in document["mutations"]:
        base = cases.get(mutation["base"])
        if base is None:
            raise SystemExit("FAIL: mutation %r references unknown base %r" % (mutation["id"], mutation["base"]))
        cases[mutation["id"]] = merge_patch(base, mutation["patch"])
    return cases


def declared_cases(document: dict) -> list:
    """Ordered [(id, expectation, pinned_bad_hash)] over examples + mutations."""
    ordered = []
    for example in document["examples"]:
        ordered.append((example["id"], example["expect"], bool(example.get("pinned_bad_hash"))))
    for mutation in document["mutations"]:
        ordered.append((mutation["id"], mutation["expect"], bool(mutation.get("pinned_bad_hash"))))
    return ordered


def rehash(document: dict, examples_path: str) -> int:
    """Authoring mode: write recomputed content hashes back into examples."""
    cases = materialize(document)
    pinned = {case_id for case_id, _, bad in declared_cases(document) if bad}
    updated = 0

    for example in document["examples"]:
        if example["id"] in pinned:
            continue
        digest = content_hash(example["contract"])
        if example["contract"]["version"]["content_hash"] != digest:
            example["contract"]["version"]["content_hash"] = digest
            updated += 1

    for mutation in document["mutations"]:
        if mutation["id"] in pinned:
            continue
        materialized = cases[mutation["id"]]
        if not isinstance(materialized, dict) or "version" not in materialized:
            continue
        digest = content_hash(materialized)
        declared = materialized.get("version", {}).get("content_hash")
        if declared != digest:
            patch_version = mutation["patch"].setdefault("version", {})
            patch_version["content_hash"] = digest
            updated += 1

    with open(examples_path, "w", encoding="utf-8") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")
    print("rehash: %d content hashes written to %s" % (updated, examples_path))
    return 0


# --------------------------------------------------------------------------
# Runner
# --------------------------------------------------------------------------


def run(corpus_path: str, schema_path: str, examples_path: str) -> int:
    with open(schema_path, encoding="utf-8") as handle:
        schema = json.load(handle)
    with open(examples_path, encoding="utf-8") as handle:
        document = json.load(handle)
    with open(corpus_path, encoding="utf-8") as handle:
        corpus = json.load(handle)

    failures = []

    if document.get("schema_version") != EXAMPLES_SCHEMA_VERSION:
        failures.append("examples: schema_version %r, expected %r" % (document.get("schema_version"), EXAMPLES_SCHEMA_VERSION))
    if schema.get("properties", {}).get("schema_version", {}).get("const") != SCHEMA_VERSION:
        failures.append("schema: contract schema_version const is not %r" % SCHEMA_VERSION)

    cases = materialize(document)
    seen_codes = set()
    checked = 0

    for case_id, expect, _pinned in declared_cases(document):
        contract = cases[case_id]
        errors = validate_schema(contract, schema, schema, "$")
        schema_valid = not errors

        if expect["schema_valid"] != schema_valid:
            failures.append(
                "%s: expected schema_valid=%s, got %s (%s)"
                % (case_id, expect["schema_valid"], schema_valid, "; ".join(errors[:3]) or "no violations")
            )
            continue

        if not schema_valid:
            seen_codes.add("CONTRACT_SCHEMA_INVALID")
            checked += 1
            continue

        code = pre_mutation(contract)
        observed = "allow" if code is None else "block:%s" % code
        if observed != expect["pre_mutation"]:
            failures.append("%s: pre-mutation expected %s, got %s" % (case_id, expect["pre_mutation"], observed))
            continue
        if code is not None:
            seen_codes.add(code)

        if code is None:
            final_code = pre_final(contract)
            observed_final = "allow" if final_code is None else "block:%s" % final_code
            if final_code is not None:
                seen_codes.add(final_code)
        else:
            observed_final = "n/a"
        if observed_final != expect["pre_final"]:
            failures.append("%s: pre-final expected %s, got %s" % (case_id, expect["pre_final"], observed_final))
            continue

        checked += 1

    # Every typed reason code the contract declares must be exercised by at
    # least one declared case — an unreachable code is an unproven claim.
    declared_codes = set(document["reason_codes"])
    unexercised = sorted(declared_codes - seen_codes)
    if unexercised:
        failures.append("reason codes declared but never exercised: %s" % ", ".join(unexercised))
    undeclared = sorted(seen_codes - declared_codes)
    if undeclared:
        failures.append("reason codes produced but not declared: %s" % ", ".join(undeclared))

    # P0.1 corpus coverage.
    coverage = {row["case_id"]: row for row in document["case_coverage"]}
    for case in corpus["cases"]:
        case_id = case["case_id"]
        row = coverage.get(case_id)
        if row is None:
            failures.append("corpus case %s has no coverage row" % case_id)
            continue
        if case["kind"] == "control":
            if not row.get("control") or row.get("scored") is not False:
                failures.append("corpus control case %s must be declared control with scored=false" % case_id)
            continue
        if not row.get("contract_field"):
            failures.append("corpus case %s: empty contract_field" % case_id)
        check = row.get("check", "")
        if not CHECK_ID_RE.match(check):
            failures.append("corpus case %s: check %r is not a typed check id" % (case_id, check))
        elif check.split(":", 1)[1] not in declared_codes:
            failures.append("corpus case %s: check %r references an undeclared reason code" % (case_id, check))
        if row.get("example_id") not in cases:
            failures.append("corpus case %s: example_id %r does not exist" % (case_id, row.get("example_id")))

    extra = sorted(set(coverage) - {case["case_id"] for case in corpus["cases"]})
    if extra:
        failures.append("coverage rows for unknown corpus cases: %s" % ", ".join(extra))

    if failures:
        for line in failures:
            print("FAIL: %s" % line)
        return 1

    critical = sum(1 for case in corpus["cases"] if case["kind"] == "critical")
    print(
        "task contract v1 validated: %d cases checked, %d reason codes exercised, "
        "%d/%d critical corpus cases mapped to a field and a check"
        % (checked, len(seen_codes), critical, critical)
    )
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Validate Task Contract v1 schema, examples and corpus coverage.")
    parser.add_argument("--corpus", required=True, help="committed P0.1 corpus.json")
    parser.add_argument("--schema", required=True, help="task-contract-v1.schema.json")
    parser.add_argument("--examples", required=True, help="task-contract-examples.json")
    parser.add_argument("--rehash", action="store_true", help="authoring mode: rewrite recomputed content hashes")
    args = parser.parse_args(argv)

    if args.rehash:
        with open(args.examples, encoding="utf-8") as handle:
            document = json.load(handle)
        return rehash(document, args.examples)

    return run(args.corpus, args.schema, args.examples)


if __name__ == "__main__":
    sys.exit(main())
