"""task_contract — Task Contract v1 compiler (P2.2, plans/2026.07.24-AGENT-RELIABILITY).

The single checked seam `packages/task/commands/plan-*.md` call at the pre-mutation and
pre-final boundaries instead of restating the rule in prose. It owns exactly what the
frozen contracts assign it and nothing else:

  * content-hash recomputation and the precedence/conflict resolution ladder
    (`root/contracts/task-contract-v1.md` §Version / §Precedence, P0.2, frozen);
  * the twelve ordered pre-mutation reason codes and the three ordered pre-final reason
    codes of the same contract (frozen; reused verbatim, never re-minted);
  * the slice-partition and cold-start checks of the same contract (frozen);
  * the portability tier classification and lint predicate of
    `plans/2026.07.24-AGENT-RELIABILITY/root/contracts/plan-portability-v1.md` (P2.1),
    including the one new reason code that layer adds
    (`PORTABILITY_TIER_MISCLASSIFIED`, `artifacts/P2.1/state-transition-cases.json`
    `new_reason_codes`).

Authoring pattern reused from
`plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.2/validate_task_contract.py` (a frozen
plan artifact, never imported or modified — the item's Required Reads name it as the
pattern to follow, not a library to import); this module is the first executable version
that lives in the package and is called by name from the canonical plan commands.

stdlib-only.
"""
from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

SCHEMA_VERSION = "task-contract/v1"

# Ordered ladders — index = rank, a lower index outranks a higher one
# (task-contract-v1.md §Precedence ladder / §Route, frozen P0.2 enums).
CARRIER_PRECEDENCE = (
    "owner-instruction",
    "plan-decision",
    "item-spec",
    "package-canon",
    "handoff-carrier",
    "incidental-diagnostic",
)
MODEL_CLASS_ORDER = ("economy", "implementation", "frontier")
EFFORT_ORDER = ("low", "medium", "high", "xhigh", "max")

# task-contract-v1.md §Public acceptance — proof classes that may satisfy a deterministic
# acceptance predicate (D30): `pinned-not-recomputable`/`unknown` never do.
DETERMINISTIC_PROOF_CLASSES = ("recomputed", "cross-checked")

# task-contract-v1.md §Root/subagent slice — the eleven payload keys, partitioned exactly.
SLICE_PARTITION_KEYS = frozenset({
    "goal", "must", "never", "done", "authority", "next", "route", "version",
    "evidence", "portability", "conflicts",
})
SLICE_SUBAGENT_REQUIRED = frozenset(
    {"goal", "must", "never", "done", "authority", "next", "route", "version"})
SLICE_ROOT_ONLY_REQUIRED = frozenset({"evidence", "portability", "conflicts"})

# task-contract-v1.md §Portability — an execution input that is absolute, `~`-rooted,
# parent-escaping, `tmp/`-rooted or URL-shaped is external BY CONSTRUCTION once its ROLE
# (execution input vs provenance) is already decided — this is the frozen P0.2 string test
# over an ALREADY-CLASSIFIED input, not the D47 role test itself. The role test (which path
# even belongs in `execution_inputs` in the first place) lives upstream of this compiler, in
# whatever builds the `portability` block (root supervisor / `plan_lint`'s tiered-portability
# check) — it is a POSITIONAL test (does the item read this path in Inputs/Required
# Reads/Validation), never a substring match on `tmp/` (D47, plan-portability-v1.md
# §Provenance vs execution input).
_EXTERNAL_PREFIXES = ("/", "~", "../", "tmp/")
_EXTERNAL_SUBSTRINGS = ("/../", "/tmp/", "://")


def canonical_payload(contract: dict) -> dict:
    """The hashed payload: the contract minus its own declared hash
    (task-contract-v1.md §Version, content_hash is recomputed, never trusted as written)."""
    payload = copy.deepcopy(contract)
    payload.get("version", {}).pop("content_hash", None)
    return payload


def content_hash(contract: dict) -> str:
    blob = json.dumps(canonical_payload(contract), sort_keys=True,
                      separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _rank(order: tuple, value: str) -> int:
    return order.index(value)


def classify_tier(work: dict) -> str:
    """plan-portability-v1.md §Classification rule (D26) — `tier(work)`.

    `work` carries the four признаки: `sessions` (`"single"`/`"multi"`), `risk`
    (`"low"`/`"high"`), `handoff` (bool), `audit` (bool)."""
    if (work.get("sessions") == "multi" or work.get("risk") == "high"
            or work.get("handoff") or work.get("audit")):
        return "committed-bundle"
    return "brief-acceptance"


def is_external_path(path: str) -> bool:
    """task-contract-v1.md §Portability — string test over a path ALREADY known to be an
    execution input (role decided elsewhere). Not the D47 role test."""
    return path.startswith(_EXTERNAL_PREFIXES) or any(s in path for s in _EXTERNAL_SUBSTRINGS)


def portability_lint(portability: dict, *, work: dict | None = None) -> str | None:
    """plan-portability-v1.md §Classification rule + §Lint predicate — ordered check over
    an already-compiled `portability` block. Returns `None` (allow) or a typed reason code:
    `PORTABILITY_TIER_MISCLASSIFIED` (P2.1, new — `artifacts/P2.1/state-transition-cases.json`
    `new_reason_codes`) · `PORTABILITY_INPUT_MISSING` / `PORTABILITY_EXTERNAL_INPUT`
    (P0.2, `task-contract-v1.md` §Pre-mutation predicate #5-6, reused verbatim).

    Order, exactly as declared in plan-portability-v1.md §Classification rule:
    (1) tier contradicts the rule for the declared `work` · (2) `committed-bundle` with no
    `execution_inputs` · (3) a path listed as both execution input and provenance ·
    (4) a host-bound input · (5) a `produced-by-predecessor` input without a producer."""
    tier = portability["tier"]
    if work is not None and classify_tier(work) != tier:
        return "PORTABILITY_TIER_MISCLASSIFIED"

    execution_inputs = portability["execution_inputs"]
    if tier == "committed-bundle" and not execution_inputs:
        return "PORTABILITY_INPUT_MISSING"

    provenance_only = set(portability["provenance_only"])
    for entry in execution_inputs:
        path = entry["path"]
        if path in provenance_only:
            return "PORTABILITY_TIER_MISCLASSIFIED"
        if is_external_path(path):
            return "PORTABILITY_EXTERNAL_INPUT"
        if entry["kind"] == "produced-by-predecessor" and not entry["producer"]:
            return "PORTABILITY_INPUT_MISSING"

    return None


def pre_mutation(contract: dict, *, work: dict | None = None) -> str | None:
    """task-contract-v1.md §Pre-mutation predicate — ordered, first failure wins.
    Returns `None` (allow) or a typed reason code.

    `work` — optional признаки for the portability tier-classification sub-check (rank
    5-6 of the frozen table); omitted when the contract's own declared tier is trusted
    as-is (e.g. re-checking an already-classified contract)."""
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

    portability_code = portability_lint(contract["portability"], work=work)
    if portability_code:
        return portability_code

    route = contract["route"]
    if (_rank(MODEL_CLASS_ORDER, route["actual"]["model_class"])
            < _rank(MODEL_CLASS_ORDER, route["required"]["model_class"])):
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


def pre_final(contract: dict) -> str | None:
    """task-contract-v1.md §Pre-final predicate — ordered, first failure wins.
    Returns `None` (allow) or a typed reason code. Caller is responsible for the `n/a`
    branch (task-contract-v1.md: evaluated only when pre-mutation allowed)."""
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


def evaluate(contract: dict, *, work: dict | None = None) -> dict:
    """Run both boundaries in the canonical order and return a compact typed result —
    the shape a plan command reports verbatim (journal/handoff/subagent slice, P2.2
    Code Guidance): `{"pre_mutation": "allow"|"block:<CODE>", "pre_final":
    "allow"|"block:<CODE>"|"n/a", "content_hash": <sha256>}`."""
    mutation_code = pre_mutation(contract, work=work)
    if mutation_code is None:
        final_code = pre_final(contract)
        final = "allow" if final_code is None else f"block:{final_code}"
    else:
        final = "n/a"
    return {
        "pre_mutation": "allow" if mutation_code is None else f"block:{mutation_code}",
        "pre_final": final,
        "content_hash": content_hash(contract),
    }


# --------------------------------------------------------------------------
# CLI — `python3 -m task.task_contract check --contract <path> [--work <path>]`
# --------------------------------------------------------------------------

def _load_json(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main(argv=None) -> int:
    import argparse
    import sys

    parser = argparse.ArgumentParser(
        description="Task Contract v1 compiler — evaluate pre-mutation/pre-final.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    check = sub.add_parser("check", help="evaluate a compiled contract JSON file")
    check.add_argument("--contract", required=True, help="path to a Task Contract v1 JSON payload")
    check.add_argument("--work", default=None,
                       help="optional JSON {sessions,risk,handoff,audit} for the portability "
                            "tier-classification sub-check")
    args = parser.parse_args(argv)

    if args.cmd != "check":  # pragma: no cover - argparse already gates choices
        return 1
    contract = _load_json(args.contract)
    work = _load_json(args.work) if args.work else None
    result = evaluate(contract, work=work)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["pre_mutation"] == "allow" else 1



# --------------------------------------------------------------------------
# Review/loop-budget policy hook (P2.3) — the one extension point
# `root/contracts/risk-review-loop-budget-v1.md`'s Contribution gate names:
# this compiler owns the pre-mutation/pre-final boundaries above and nothing
# about what happens to an item BETWEEN them when a typed finding is raised
# against it. `task.review_policy` owns that lifecycle; this function is the
# only place this module knows the module exists — a lazy import, so
# `pre_mutation`/`pre_final`/`evaluate` above stay untouched and this
# compiler's own test suite never needs `review_policy` importable.
# --------------------------------------------------------------------------

def evaluate_finding(state: str, finding: dict, *, budget=None, profile: str) -> dict:
    """Delegates one `typed-finding` event to `task.review_policy.review_transition`
    (P2.3). `budget` defaults to a fresh `LoopBudget` when the caller tracks no
    cross-finding state of its own; passing the same `LoopBudget` across calls is
    what lets `same_finding_max` count occurrences across an item's fix rounds."""
    from task.review_policy import LoopBudget, review_transition
    return review_transition(state, finding, budget=budget or LoopBudget(), profile=profile)


if __name__ == "__main__":
    import sys
    sys.exit(main())
