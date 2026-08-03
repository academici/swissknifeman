#!/usr/bin/env python3
"""Independent stdlib conformance check for slice-manifest-v1."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from pathlib import Path


SCHEMA_VERSION = "slice-manifest-v1"
CONTRACT_VERSION = "1.0.0"
HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
ITEM_RE = re.compile(r"^P[0-9]+\.[0-9]+$")

TOP_KEY_ORDER = (
    "schema_version", "manifest_version", "slice_id", "plan_id", "item_id",
    "revision", "content_hash", "supersedes", "lifecycle", "source_hashes",
    "task_contract", "run", "scope", "dependencies", "route", "references",
    "budgets", "execution",
)
TOP_KEYS = set(TOP_KEY_ORDER)
SOURCE_KEYS = {
    "repository_root", "base_commit", "plan", "phase", "item", "handoff",
    "task_contract", "execution_policy",
}
TASK_KEYS = {"schema_version", "content_hash", "pre_mutation", "public_acceptance_ids"}
RUN_KEYS = {
    "contract_id", "contract_version", "contract_hash", "run_id", "attempt",
    "idempotency_key",
}
SCOPE_KEYS = {"required_reads", "files", "validation", "deliverables", "evidence_refs"}
DEPENDENCY_KEYS = {"item_id", "required_lifecycle", "manifest_hash"}
ROUTE_KEYS = {"model_class", "effort", "exec", "capabilities"}
CAPABILITY_KEYS = {"id", "support"}
REFERENCE_KEYS = {
    "authority_contract_id", "authority_contract_version", "authority_contract_hash",
    "output_contract_id", "output_contract_version", "output_contract_hash",
}
BUDGET_KEYS = {
    "max_attempts", "max_auto_fix_attempts", "max_parallel_workers",
    "timeout_seconds", "token_limit", "token_limit_unknown_reason",
}
EXECUTION_KEYS = {"operations", "writer_mode", "worktree_mode", "integration_mode"}

LIFECYCLE = (
    "pending", "dispatched", "observed", "accepted", "refused", "superseded",
)
OPERATIONS = (
    "compile_slice", "supersede_pending", "dispatch_worker", "validate_result",
    "integrate_owned_delta", "project_plan_bookkeeping",
)
REFUSAL_REASONS = (
    "UNKNOWN_SCHEMA_VERSION", "UNKNOWN_MANIFEST_KEY", "MANIFEST_HASH_MISMATCH",
    "SKELETON_ITEM", "TASK_CONTRACT_BLOCKED", "TASK_CONTRACT_HASH_MISMATCH",
    "DEPENDENCY_UNKNOWN", "DEPENDENCY_NOT_TERMINAL", "DEPENDENCY_HASH_MISMATCH",
    "DEPENDENCY_CYCLE", "ROUTE_UNRESOLVED", "ROUTE_EXEC_MISMATCH",
    "SLICE_INPUT_MISSING", "SLICE_INPUT_EXTERNAL", "SOURCE_DRIFT",
    "CAPABILITY_UNSUPPORTED", "BUDGET_INVALID", "PARALLEL_CEILING_EXCEEDED",
    "WRITER_MODE_UNSAFE", "REPLAN_NON_PENDING", "REPLAN_SUPERSEDES_REQUIRED",
)
MODEL_ORDER = ("economy", "implementation", "frontier")
EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max")
EXTERNAL_PREFIXES = ("/", "~", "../", "tmp/")
EXTERNAL_SUBSTRINGS = ("/../", "/tmp/", "://")


class Refusal(ValueError):
    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def canonical_bytes(value):
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")


def manifest_hash(manifest):
    payload = copy.deepcopy(manifest)
    payload.pop("content_hash", None)
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()


def declared_set(text, name):
    pattern = rf"<!-- declared-set: {re.escape(name)} -->\s*```text\n(.*?)\n```"
    match = re.search(pattern, text, re.DOTALL)
    if not match:
        raise ValueError(f"contract: missing declared set {name}")
    values = tuple(line.strip() for line in match.group(1).splitlines() if line.strip())
    if len(values) != len(set(values)):
        raise ValueError(f"contract: duplicate value in {name}")
    return values


def closed(value, keys):
    return isinstance(value, dict) and set(value) == set(keys)


def nonempty_unique_strings(value):
    return (
        isinstance(value, list) and bool(value)
        and all(isinstance(item, str) and item for item in value)
        and len(value) == len(set(value))
    )


def external_path(path):
    return path.startswith(EXTERNAL_PREFIXES) or any(token in path for token in EXTERNAL_SUBSTRINGS)


def validate_closed_shape(manifest):
    if not closed(manifest, TOP_KEYS):
        raise Refusal("UNKNOWN_MANIFEST_KEY")
    nested = (
        (manifest["source_hashes"], SOURCE_KEYS),
        (manifest["task_contract"], TASK_KEYS),
        (manifest["run"], RUN_KEYS),
        (manifest["scope"], SCOPE_KEYS),
        (manifest["route"], ROUTE_KEYS),
        (manifest["references"], REFERENCE_KEYS),
        (manifest["budgets"], BUDGET_KEYS),
        (manifest["execution"], EXECUTION_KEYS),
    )
    if any(not closed(value, keys) for value, keys in nested):
        raise Refusal("UNKNOWN_MANIFEST_KEY")
    if not isinstance(manifest["dependencies"], list):
        raise Refusal("UNKNOWN_MANIFEST_KEY")
    if any(not closed(row, DEPENDENCY_KEYS) for row in manifest["dependencies"]):
        raise Refusal("UNKNOWN_MANIFEST_KEY")
    capabilities = manifest["route"]["capabilities"]
    if not isinstance(capabilities, list) or any(
        not closed(row, CAPABILITY_KEYS) for row in capabilities
    ):
        raise Refusal("UNKNOWN_MANIFEST_KEY")


def validate_manifest(manifest, context, fleet_cap):
    validate_closed_shape(manifest)
    if manifest["schema_version"] != SCHEMA_VERSION or manifest["manifest_version"] != CONTRACT_VERSION:
        raise Refusal("UNKNOWN_SCHEMA_VERSION")
    if manifest["content_hash"] != manifest_hash(manifest):
        raise Refusal("MANIFEST_HASH_MISMATCH")
    if not context.get("item_ready"):
        raise Refusal("SKELETON_ITEM")

    task_contract = manifest["task_contract"]
    if task_contract["pre_mutation"] != "allow":
        raise Refusal("TASK_CONTRACT_BLOCKED")
    if (
        task_contract["schema_version"] != "task-contract/v1"
        or task_contract["content_hash"] != manifest["source_hashes"]["task_contract"]
        or not nonempty_unique_strings(task_contract["public_acceptance_ids"])
    ):
        raise Refusal("TASK_CONTRACT_HASH_MISMATCH")

    run = manifest["run"]
    references = manifest["references"]
    if (
        run["contract_id"] != "supervisor-run-v1"
        or run["contract_version"] != CONTRACT_VERSION
        or not isinstance(run["attempt"], int) or isinstance(run["attempt"], bool)
        or run["attempt"] < 1 or not run["run_id"]
        or references["authority_contract_id"] != "authority-policy-v1"
        or references["authority_contract_version"] != CONTRACT_VERSION
        or references["output_contract_id"] != "worker-envelope-v1"
        or references["output_contract_version"] != CONTRACT_VERSION
    ):
        raise Refusal("UNKNOWN_SCHEMA_VERSION")

    known = context.get("known_dependencies", {})
    seen_dependencies = set()
    for dependency in manifest["dependencies"]:
        item_id = dependency["item_id"]
        if item_id in seen_dependencies or item_id not in known:
            raise Refusal("DEPENDENCY_UNKNOWN")
        seen_dependencies.add(item_id)
        observed = known[item_id]
        if dependency["required_lifecycle"] != "accepted" or observed.get("lifecycle") != "accepted":
            raise Refusal("DEPENDENCY_NOT_TERMINAL")
        if dependency["manifest_hash"] != observed.get("manifest_hash"):
            raise Refusal("DEPENDENCY_HASH_MISMATCH")

    route = manifest["route"]
    if (
        route["model_class"] not in MODEL_ORDER
        or route["effort"] not in EFFORT_ORDER
        or route["exec"] not in ("manual", "plan-exec")
    ):
        if route["exec"] == "plan-design":
            raise Refusal("ROUTE_EXEC_MISMATCH")
        raise Refusal("ROUTE_UNRESOLVED")
    derived_manual = (
        MODEL_ORDER.index(route["model_class"]) > MODEL_ORDER.index("implementation")
        or EFFORT_ORDER.index(route["effort"]) > EFFORT_ORDER.index("medium")
    )
    if derived_manual and route["exec"] != "manual":
        raise Refusal("ROUTE_EXEC_MISMATCH")

    scope = manifest["scope"]
    for key in ("required_reads", "files", "validation", "deliverables", "evidence_refs"):
        if not nonempty_unique_strings(scope[key]):
            raise Refusal("SLICE_INPUT_MISSING")
    if scope["evidence_refs"] != task_contract["public_acceptance_ids"]:
        raise Refusal("SLICE_INPUT_MISSING")
    execution_paths = scope["required_reads"] + scope["files"]
    if any(external_path(path) for path in execution_paths):
        raise Refusal("SLICE_INPUT_EXTERNAL")
    available = set(context.get("available_paths", []))
    if any(path not in available for path in execution_paths):
        raise Refusal("SLICE_INPUT_MISSING")

    source_hashes = manifest["source_hashes"]
    actual_hashes = context.get("actual_source_hashes", {})
    if (
        set(source_hashes) != SOURCE_KEYS
        or any(not isinstance(value, str) or not HEX64_RE.fullmatch(value) for value in source_hashes.values())
        or source_hashes != actual_hashes
    ):
        raise Refusal("SOURCE_DRIFT")
    capability_ids = [row["id"] for row in route["capabilities"]]
    if (
        not capability_ids or len(capability_ids) != len(set(capability_ids))
        or any(not row["id"] or row["support"] not in ("native", "adapted")
               for row in route["capabilities"])
    ):
        raise Refusal("CAPABILITY_UNSUPPORTED")

    budgets = manifest["budgets"]
    positive = ("max_attempts", "max_parallel_workers", "timeout_seconds")
    if any(not isinstance(budgets[key], int) or isinstance(budgets[key], bool) or budgets[key] < 1 for key in positive):
        raise Refusal("BUDGET_INVALID")
    auto_fix = budgets["max_auto_fix_attempts"]
    if (
        not isinstance(auto_fix, int) or isinstance(auto_fix, bool) or auto_fix < 0
        or auto_fix >= budgets["max_attempts"]
        or (budgets["token_limit"] is None and not budgets["token_limit_unknown_reason"])
        or (budgets["token_limit"] is not None and (
            not isinstance(budgets["token_limit"], int) or budgets["token_limit"] < 1
        ))
    ):
        raise Refusal("BUDGET_INVALID")
    if budgets["max_parallel_workers"] > fleet_cap:
        raise Refusal("PARALLEL_CEILING_EXCEEDED")

    execution = manifest["execution"]
    if tuple(execution["operations"]) != OPERATIONS:
        raise Refusal("UNKNOWN_MANIFEST_KEY")
    if (
        execution["writer_mode"] != "one-writer"
        or execution["worktree_mode"] != "current-or-owned-linked"
        or execution["integration_mode"] != "serialized"
    ):
        raise Refusal("WRITER_MODE_UNSAFE")

    if manifest["lifecycle"] not in LIFECYCLE:
        raise Refusal("UNKNOWN_SCHEMA_VERSION")
    if context.get("requested_replan"):
        if manifest["lifecycle"] != "pending":
            raise Refusal("REPLAN_NON_PENDING")
        if (
            manifest["revision"] <= 1
            or manifest["supersedes"] != context.get("prior_manifest_hash")
            or not HEX64_RE.fullmatch(manifest["supersedes"] or "")
        ):
            raise Refusal("REPLAN_SUPERSEDES_REQUIRED")
    elif manifest["revision"] != 1 or manifest["supersedes"] is not None:
        raise Refusal("REPLAN_SUPERSEDES_REQUIRED")

    for value in (
        manifest["content_hash"], manifest["run"]["contract_hash"],
        manifest["run"]["idempotency_key"],
        manifest["references"]["authority_contract_hash"],
        manifest["references"]["output_contract_hash"],
    ):
        if not isinstance(value, str) or not HEX64_RE.fullmatch(value):
            raise Refusal("UNKNOWN_SCHEMA_VERSION")
    if not ITEM_RE.fullmatch(manifest["item_id"]):
        raise Refusal("UNKNOWN_SCHEMA_VERSION")
    return "allow"


def set_path(root, path, value):
    target = root
    for token in path[:-1]:
        target = target[token]
    target[path[-1]] = value


def apply_mutations(manifest, context, mutations):
    for mutation in mutations:
        if mutation.get("op") != "set":
            raise ValueError(f"unsupported fixture mutation: {mutation!r}")
        root = manifest if mutation.get("target") == "manifest" else context
        set_path(root, mutation["path"], copy.deepcopy(mutation["value"]))


def topological_order(graph):
    if not isinstance(graph, dict) or any(not isinstance(value, list) for value in graph.values()):
        raise Refusal("DEPENDENCY_UNKNOWN")
    nodes = set(graph)
    if any(dependency not in nodes for dependencies in graph.values() for dependency in dependencies):
        raise Refusal("DEPENDENCY_UNKNOWN")
    indegree = {node: len(set(graph[node])) for node in nodes}
    consumers = {node: [] for node in nodes}
    for node, dependencies in graph.items():
        for dependency in set(dependencies):
            consumers[dependency].append(node)
    ready = sorted(node for node, degree in indegree.items() if degree == 0)
    ordered = []
    while ready:
        node = ready.pop(0)
        ordered.append(node)
        for consumer in sorted(consumers[node]):
            indegree[consumer] -= 1
            if indegree[consumer] == 0:
                ready.append(consumer)
                ready.sort()
    if len(ordered) != len(nodes):
        raise Refusal("DEPENDENCY_CYCLE")
    return ordered


def validate_cases(data, fleet_cap):
    base_manifest = data["base_manifest"]
    if base_manifest["content_hash"] != manifest_hash(base_manifest):
        raise ValueError("base_manifest content_hash is stale")
    observed = set()
    for case in data["compile_cases"]:
        manifest = copy.deepcopy(base_manifest)
        context = copy.deepcopy(data["base_context"])
        apply_mutations(manifest, context, case["mutations"])
        manifest["content_hash"] = manifest_hash(manifest)
        if case.get("tamper_hash"):
            manifest["content_hash"] = "0" * 64
        try:
            result = validate_manifest(manifest, context, fleet_cap)
        except Refusal as exc:
            result = exc.reason
        if result != case["expected"]:
            raise ValueError(f"{case['id']}: expected {case['expected']}, observed {result}")
        if result != "allow":
            observed.add(result)
    graph_refusals = set()
    for case in data["dependency_graph_cases"]:
        try:
            result = topological_order(case["graph"])
        except Refusal as exc:
            result = exc.reason
            graph_refusals.add(result)
        if result != case["expected"]:
            raise ValueError(f"{case['id']}: expected {case['expected']}, observed {result}")
    observed |= graph_refusals
    missing = set(REFUSAL_REASONS) - observed
    if missing:
        raise ValueError(f"refusal coverage incomplete: {sorted(missing)}")
    return len(data["compile_cases"]), len(data["dependency_graph_cases"]), len(observed)


def load_fleet_cap(policy):
    if set(policy) != {
        "policy_version", "spawn_threshold", "max_parallel_agents",
        "allowed_agent_roles", "delegation_contract",
    }:
        raise ValueError("execution policy top-level shape drifted")
    cap = policy["max_parallel_agents"]["fleet_cap"]
    if cap.get("applies_to") != "session-agent-tool" or not isinstance(cap.get("value"), int):
        raise ValueError("execution policy fleet cap is unresolved")
    return cap["value"]


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", required=True)
    parser.add_argument("--cases", required=True)
    parser.add_argument("--execution-policy", required=True)
    args = parser.parse_args(argv)
    try:
        contract_text = Path(args.contract).read_text(encoding="utf-8")
        data = json.loads(Path(args.cases).read_text(encoding="utf-8"))
        policy = json.loads(Path(args.execution_policy).read_text(encoding="utf-8"))
        if data.get("schema_version") != "slice-manifest-cases-v1":
            raise ValueError("cases: unknown schema_version")
        if data.get("contract_version") != CONTRACT_VERSION:
            raise ValueError("cases: contract_version is not frozen v1")
        if declared_set(contract_text, "manifest_keys") != TOP_KEY_ORDER:
            raise ValueError("contract manifest key declaration differs from validator")
        if declared_set(contract_text, "lifecycle") != LIFECYCLE:
            raise ValueError("contract lifecycle declaration differs from validator")
        if declared_set(contract_text, "operations") != OPERATIONS:
            raise ValueError("contract operation declaration differs from validator")
        if declared_set(contract_text, "refusal_reasons") != REFUSAL_REASONS:
            raise ValueError("contract refusal declaration differs from validator")
        fleet_cap = load_fleet_cap(policy)
        compile_count, graph_count, refusal_count = validate_cases(data, fleet_cap)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        print(f"slice-manifest: FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        "slice-manifest: OK "
        f"({compile_count} compile cases; {graph_count} dependency graphs; "
        f"{refusal_count} refusal classes; fleet cap {fleet_cap})"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
