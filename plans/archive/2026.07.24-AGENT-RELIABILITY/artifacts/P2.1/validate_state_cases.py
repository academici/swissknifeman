#!/usr/bin/env python3
"""P2.1 — execution state machine / review budget / portability validator (stdlib-only).

Owner item: plans/2026.07.24-AGENT-RELIABILITY P2.1 (D51/D64-D68).

Five jobs, no more:

1. Prove the transition matrix **total by construction**: enumerate the cartesian
   product of the declared states and events in code and assert every cell is
   covered exactly once by either a declared transition or a declared
   impossibility. Counting entries is not a proof, so entries are consumed from
   a generated set instead of counted.
2. Prove every guarded cell partitions its guard's declared value set exactly
   (disjoint and exhaustive) — a wildcard/default branch has no representation
   in this format and an incomplete partition fails.
3. Prove both projections total: every state maps to exactly one of the six
   canonical plan statuses (`DONE` taking the declared `material_deviation`
   attribute as projection input), and every one of the eight journal
   `RESULT_VALUES` is reached by at least one declared transition.
4. Prove the deterministic decision function `decide(state, event, payload,
   profile)` is a pure lookup over that matrix, that all six declared outputs
   are reachable, and that every declared positive routine case yields
   `continue-next` (F14 false-block gate: a contract that blocks everything is
   formally total and practically useless).
5. Prove doc<->data equality: each declared set appears verbatim in exactly one
   contract inside a fenced block preceded by `<!-- declared-set: <name> -->`,
   each referenced (not re-minted) set is cited by its owner's `file:line` in
   that contract's `## Frozen upstream` section, and the declared mutations each
   FAIL for their declared reason (failing for the wrong reason is a failure).

This script reads only the paths given on its command line, writes nothing and
opens no network connection. It intentionally does NOT import
`artifacts/P0.2/validate_task_contract.py`: that artifact is frozen, so the
~40 lines of duplicated helper shape here are the accepted price of
independence (item P2.1 Code Guidance).

Exit code 0 = every assertion holds. Any failure prints `FAIL: <CODE>: ...`
lines and exits 1.
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys

CASES_SCHEMA_VERSION = "state-transition-cases/v1"

# Typed failure codes this validator emits. They are the `new_reason_codes` of
# the three P2.1 contracts: each names a condition none of the fifteen P0.2
# codes already names, and each carries a `distinct_from` justification in the
# cases document (checked below).
CODE_MATRIX = "TRANSITION_UNDECLARED"
CODE_PROJECTION = "PROJECTION_UNREACHABLE"
CODE_FINDING_ID = "FINDING_IDENTITY_UNSTABLE"
CODE_REOPEN = "REOPEN_WITHOUT_PRODUCT_FINDING"
CODE_TIER = "PORTABILITY_TIER_MISCLASSIFIED"
CODE_PROFILE = "AUTHORITY_PROFILE_UNDECLARED"
CODE_SET_DRIFT = "DECLARED_SET_DRIFT"
CODE_FALSE_BLOCK = "FALSE_BLOCK"

# Structural codes: a malformed document that cannot even be interpreted as the
# matrix. They are not contract reason codes and are not declared as such.
CODE_DOCUMENT = "DOCUMENT_MALFORMED"

CHECK_ID_RE = re.compile(r"^(pre-mutation|pre-final|schema):[A-Z_]+$")
DECLARED_SET_RE = re.compile(
    r"<!--\s*declared-set:\s*(?P<name>[a-z0-9_]+)\s*-->\s*\n```(?:text)?\n(?P<body>.*?)```",
    re.DOTALL,
)
BOOLEAN_VALUES = ["false", "true"]


# --------------------------------------------------------------------------
# Loading
# --------------------------------------------------------------------------


def load_json(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def load_contracts(contracts_dir: str, names: list) -> dict:
    bodies = {}
    for name in names:
        path = contracts_dir.rstrip("/") + "/" + name
        with open(path, encoding="utf-8") as handle:
            bodies[name] = handle.read()
    return bodies


# --------------------------------------------------------------------------
# The declared machine
# --------------------------------------------------------------------------


def guard_values(doc: dict, key: str):
    """Declared value list of one guard key, or None if the key is undeclared."""
    for entry in doc["guard_keys"]:
        if entry["key"] != key:
            continue
        if entry["kind"] == "predicate":
            return list(entry["values"])
        return list(doc["declared_sets"][entry["set"]])
    return None


def cell_index(doc: dict) -> dict:
    """{(state, event): cell} — duplicates are reported by the caller."""
    index = {}
    for cell in doc["cells"]:
        index.setdefault((cell["state"], cell["event"]), []).append(cell)
    return index


def branches_of(cell: dict) -> list:
    """Ordered [(when_values, branch)] of a cell; unguarded cells yield one."""
    if cell["kind"] != "transition":
        return []
    guard = cell.get("guard")
    if guard is None:
        return [(None, cell)]
    return [(branch["when"], branch) for branch in guard["branches"]]


def decide(doc: dict, index: dict, state: str, event: str, payload: dict, profile: str):
    """Pure deterministic decision function: (state, event, payload, profile) -> output.

    No clock, no filesystem, no randomness: the result is a lookup over the
    declared matrix. A cell declared impossible returns the uniform output
    `escalate-design` together with that cell's OWN declared reason — the
    observation of an event the matrix declares impossible is a spec<->reality
    divergence whose owner is `plan-design`. That is not a default/wildcard
    rule: every such cell carries its own reason string, and no cell is left
    uncovered for it to absorb.
    """
    cells = index.get((state, event))
    if not cells or len(cells) != 1:
        raise KeyError("undeclared or duplicated cell: (%s, %s)" % (state, event))
    cell = cells[0]
    if cell["kind"] == "impossible":
        return "escalate-design", cell["to"] if "to" in cell else state, cell["reason"]

    guard = cell.get("guard")
    if guard is None:
        return cell["decision"], cell["to"], None

    key = guard["key"]
    value = profile if key == "profile" else payload.get(key)
    value = str(value).lower() if isinstance(value, bool) else value
    for branch in guard["branches"]:
        if value in branch["when"]:
            return branch["decision"], branch["to"], None
    raise KeyError("guard %r of cell (%s, %s) has no branch for %r" % (key, state, event, value))


# --------------------------------------------------------------------------
# Checks
# --------------------------------------------------------------------------


def check_sets(doc: dict, failures: list) -> None:
    declared = doc["declared_sets"]
    referenced = doc["referenced_sets"]

    overlap = sorted(set(declared) & set(referenced))
    if overlap:
        failures.append((CODE_SET_DRIFT, "set declared and referenced at once: %s" % ", ".join(overlap)))

    for name, values in declared.items():
        if len(values) != len(set(values)):
            failures.append((CODE_SET_DRIFT, "declared set %s carries duplicates" % name))

    for name, entry in referenced.items():
        if not entry.get("owner") or not entry.get("source"):
            failures.append((CODE_SET_DRIFT, "referenced set %s without owner/source" % name))
        if not entry.get("cited_in"):
            failures.append((CODE_SET_DRIFT, "referenced set %s names no citing contract" % name))

    # Sizes the item's spec declares literally (D65): a silent widening of any of
    # them would make the 135-cell totality claim describe a different machine.
    for name, size in doc["declared_set_sizes"].items():
        actual = len(declared.get(name, referenced.get(name, {}).get("values", [])))
        if actual != size:
            failures.append(
                (CODE_SET_DRIFT, "set %s: declared size %d, actual %d" % (name, size, actual))
            )


def check_new_reason_codes(doc: dict, failures: list) -> None:
    frozen = set(doc["referenced_sets"]["pre_mutation_reason_codes"]["values"])
    frozen |= set(doc["referenced_sets"]["pre_final_reason_codes"]["values"])
    emitted = {
        CODE_MATRIX, CODE_PROJECTION, CODE_FINDING_ID, CODE_REOPEN,
        CODE_TIER, CODE_PROFILE, CODE_SET_DRIFT, CODE_FALSE_BLOCK,
    }
    declared = {row["code"]: row for row in doc["new_reason_codes"]}

    if set(declared) != emitted:
        failures.append(
            (
                CODE_SET_DRIFT,
                "new reason codes declared %s, emitted by this validator %s"
                % (sorted(declared), sorted(emitted)),
            )
        )
    for code, row in declared.items():
        if code in frozen:
            failures.append((CODE_SET_DRIFT, "%s re-mints a frozen P0.2 code" % code))
        if row.get("distinct_from") not in frozen:
            failures.append(
                (CODE_SET_DRIFT, "%s: distinct_from %r is not a frozen P0.2 code" % (code, row.get("distinct_from")))
            )
        if not row.get("justification"):
            failures.append((CODE_SET_DRIFT, "%s: empty distinct_from justification" % code))


def check_matrix(doc: dict, failures: list) -> dict:
    """Totality by construction. Returns the cell index for later checks."""
    states = doc["declared_sets"]["states"]
    events = doc["declared_sets"]["events"]

    expected = set()
    for state in states:
        for event in events:
            expected.add((state, event))

    index = cell_index(doc)
    for key, cells in sorted(index.items()):
        if len(cells) > 1:
            failures.append((CODE_MATRIX, "cell (%s, %s) declared %d times" % (key[0], key[1], len(cells))))
        if key not in expected:
            failures.append((CODE_MATRIX, "cell (%s, %s) is outside the declared product" % key))
        expected.discard(key)
    for key in sorted(expected):
        failures.append((CODE_MATRIX, "cell (%s, %s) is not covered" % key))

    outputs = set(doc["declared_sets"]["decision_outputs"])
    state_set = set(states)

    for cell in doc["cells"]:
        where = "(%s, %s)" % (cell["state"], cell["event"])
        if cell["kind"] == "impossible":
            if not cell.get("reason"):
                failures.append((CODE_MATRIX, "%s: impossibility without a reason" % where))
            if not cell.get("impossibility_class"):
                failures.append((CODE_MATRIX, "%s: impossibility without a declared class" % where))
            continue
        if cell["kind"] != "transition":
            failures.append((CODE_MATRIX, "%s: unknown cell kind %r" % (where, cell["kind"])))
            continue

        guard = cell.get("guard")
        if guard is None:
            branch_list = [cell]
        else:
            values = guard_values(doc, guard["key"])
            if values is None:
                failures.append((CODE_MATRIX, "%s: guard key %r is not declared" % (where, guard["key"])))
                continue
            seen = []
            for branch in guard["branches"]:
                seen.extend(branch["when"])
            if sorted(seen) != sorted(set(seen)):
                failures.append((CODE_MATRIX, "%s: guard branches overlap" % where))
            if set(seen) != set(values):
                failures.append(
                    (
                        CODE_MATRIX,
                        "%s: guard %s covers %s, declared set is %s"
                        % (where, guard["key"], sorted(set(seen)), sorted(values)),
                    )
                )
            branch_list = guard["branches"]

        for branch in branch_list:
            if branch["to"] not in state_set:
                failures.append((CODE_MATRIX, "%s: target %r is not a declared state" % (where, branch["to"])))
            if branch["decision"] not in outputs:
                failures.append((CODE_MATRIX, "%s: decision %r is not a declared output" % (where, branch["decision"])))
            journal = branch.get("journal")
            if journal is not None and journal not in doc["referenced_sets"]["journal_result_values"]["values"]:
                failures.append((CODE_MATRIX, "%s: journal %r is not a journal RESULT_VALUE" % (where, journal)))

    return index


def check_deny_class_partition(doc: dict, failures: list) -> None:
    """The four deny classes must partition the twelve frozen P0.2 codes exactly."""
    codes = doc["referenced_sets"]["pre_mutation_reason_codes"]["values"]
    mapping = doc["deny_class_codes"]
    if sorted(mapping) != sorted(doc["declared_sets"]["deny_classes"]):
        failures.append((CODE_MATRIX, "deny_class_codes keys differ from the declared deny_classes set"))
    flat = []
    for values in mapping.values():
        flat.extend(values)
    if sorted(flat) != sorted(set(flat)):
        failures.append((CODE_MATRIX, "deny classes overlap on a reason code"))
    if set(flat) != set(codes):
        missing = sorted(set(codes) - set(flat))
        extra = sorted(set(flat) - set(codes))
        failures.append(
            (CODE_MATRIX, "deny classes do not partition the P0.2 codes (missing %s, extra %s)" % (missing, extra))
        )


def check_projections(doc: dict, index: dict, failures: list) -> tuple:
    states = doc["declared_sets"]["states"]
    statuses = doc["referenced_sets"]["canonical_statuses"]["values"]
    journal_values = doc["referenced_sets"]["journal_result_values"]["values"]
    projection = doc["projection"]["state_to_status"]
    attributed = doc["projection"]["attribute_projected_states"]

    projected = 0
    for state in states:
        entry = projection.get(state)
        if entry is None:
            failures.append((CODE_PROJECTION, "state %s projects to no canonical status" % state))
            continue
        if state in attributed:
            branches = entry if isinstance(entry, dict) else {}
            if sorted(branches) != sorted(BOOLEAN_VALUES):
                failures.append(
                    (
                        CODE_PROJECTION,
                        "state %s is attribute-projected on %s and must carry both boolean branches"
                        % (state, doc["projection"]["projection_attribute"]),
                    )
                )
                continue
            unknown = [value for value in branches.values() if value not in statuses]
            if unknown:
                failures.append((CODE_PROJECTION, "state %s projects to unknown status %s" % (state, unknown)))
                continue
        else:
            if not isinstance(entry, str):
                failures.append((CODE_PROJECTION, "state %s must project to exactly one status" % state))
                continue
            if entry not in statuses:
                failures.append((CODE_PROJECTION, "state %s projects to unknown status %r" % (state, entry)))
                continue
        projected += 1

    reached_status = set()
    for state, entry in projection.items():
        if isinstance(entry, dict):
            reached_status.update(entry.values())
        else:
            reached_status.add(entry)
    for status in statuses:
        if status not in reached_status:
            failures.append((CODE_PROJECTION, "canonical status %r is reached by no state" % status))

    reached_journal = set()
    for cell in doc["cells"]:
        for _when, branch in branches_of(cell):
            if branch.get("journal"):
                reached_journal.add(branch["journal"])
    unreachable = [value for value in journal_values if value not in reached_journal]
    for value in unreachable:
        failures.append((CODE_PROJECTION, "journal RESULT_VALUE %r is reached by no transition" % value))

    return projected, len(journal_values) - len(unreachable)


def check_decision_function(doc: dict, index: dict, failures: list) -> None:
    outputs = set(doc["declared_sets"]["decision_outputs"])
    produced = set()
    for cell in doc["cells"]:
        if cell["kind"] == "impossible":
            produced.add("escalate-design")
            continue
        for _when, branch in branches_of(cell):
            produced.add(branch["decision"])
    unreachable = sorted(outputs - produced)
    for value in unreachable:
        failures.append((CODE_PROJECTION, "decision output %r is produced by no transition" % value))


def check_reopen_rule(doc: dict, failures: list) -> None:
    """Only a product/blocker/acceptance-invalidating finding may reopen product."""
    reopen_states = set(doc["review_policy"]["states_that_may_reopen_product"])
    for cell in doc["cells"]:
        if cell["event"] != "typed-finding" or cell["kind"] != "transition":
            continue
        for when, branch in branches_of(cell):
            if branch["to"] == cell["state"] or branch["to"] not in reopen_states:
                continue  # staying inside a repair state is not a reopen
            if when is None or "true" not in when or "false" in when:
                failures.append(
                    (
                        CODE_REOPEN,
                        "cell (%s, typed-finding) reopens product on a branch that is not guarded by "
                        "reopens_product=true" % cell["state"],
                    )
                )


def check_finding_identity(doc: dict, failures: list) -> None:
    identity = doc["review_policy"]["finding_identity"]
    if identity.get("derived_from") != "seam":
        failures.append(
            (CODE_FINDING_ID, "finding_id is derived from %r, not from the defect's seam" % identity.get("derived_from"))
        )
    if not identity.get("seam_fields"):
        failures.append((CODE_FINDING_ID, "finding_id declares no seam fields"))
    if not identity.get("forbidden_sources"):
        failures.append((CODE_FINDING_ID, "finding_id declares no forbidden derivation sources"))


def check_authority_profiles(doc: dict, index: dict, failures: list) -> None:
    profiles = doc["declared_sets"]["authority_profiles"]
    declared = doc["review_policy"]["cap_subject_by_profile"]
    if sorted(declared) != sorted(profiles):
        failures.append((CODE_PROFILE, "cap subject declared for %s, profiles are %s" % (sorted(declared), sorted(profiles))))
    for profile, row in declared.items():
        if not row.get("subject") or not row.get("source"):
            failures.append((CODE_PROFILE, "profile %s declares no cap subject/source" % profile))

    cells = index.get(("INCIDENT", "escalation-trigger"), [])
    if len(cells) != 1:
        failures.append((CODE_PROFILE, "the cap-resolution cell (INCIDENT, escalation-trigger) is not declared once"))
        return
    guard = cells[0].get("guard")
    if guard is None or guard["key"] != "profile":
        failures.append(
            (
                CODE_PROFILE,
                "the cap-resolution cell (INCIDENT, escalation-trigger) is not guarded by the authority profile: "
                "hardcoding either subject breaks the other (D68)",
            )
        )


def check_portability(doc: dict, failures: list) -> None:
    """Recompute every declared tier from the classification rule (D26/D47)."""
    tiers = doc["referenced_sets"]["portability_tiers"]["values"]
    bundle, brief = tiers[1], tiers[0]
    for case in doc["portability_cases"]:
        work = case["work"]
        expected = bundle if (
            work["sessions"] == "multi" or work["risk"] == "high" or work["handoff"] or work["audit"]
        ) else brief
        if case["tier"] != expected:
            failures.append(
                (
                    CODE_TIER,
                    "portability case %s declares tier %r, the classification rule yields %r"
                    % (case["case_id"], case["tier"], expected),
                )
            )
        if case["tier"] == bundle and not case["execution_inputs"]:
            failures.append(
                (CODE_TIER, "portability case %s is %s with no execution input" % (case["case_id"], bundle))
            )
        for path in case["execution_inputs"]:
            if path in case.get("provenance_only", []):
                failures.append(
                    (CODE_TIER, "portability case %s lists %r as both execution input and provenance" % (case["case_id"], path))
                )
        if case.get("role_rule") != "by-role":
            failures.append(
                (
                    CODE_TIER,
                    "portability case %s does not classify by the path's ROLE (a substring match on tmp/ is "
                    "explicitly not the rule, D47)" % case["case_id"],
                )
            )


def check_positive_cases(doc: dict, index: dict, failures: list) -> tuple:
    """F14: routine continuations the machine MUST let through."""
    cases = doc["positive_cases"]
    minimum = doc["review_policy"]["positive_case_minimum"]
    if len(cases) < minimum:
        failures.append(
            (CODE_FALSE_BLOCK, "%d positive routine cases declared, the F14 floor is %d" % (len(cases), minimum))
        )
    passing = 0
    for case in cases:
        try:
            decision, to, _reason = decide(
                doc, index, case["state"], case["event"], case.get("payload", {}), case.get("profile", "self-host")
            )
        except KeyError as error:
            failures.append((CODE_FALSE_BLOCK, "positive case %s: %s" % (case["case_id"], error)))
            continue
        if decision != "continue-next":
            failures.append(
                (
                    CODE_FALSE_BLOCK,
                    "positive case %s yields %r, not continue-next: a contract that blocks a routine "
                    "continuation is not a green contract (F14, reliability-acceptance-v1.md:89-93)"
                    % (case["case_id"], decision),
                )
            )
            continue
        if to != case["expect_state"]:
            failures.append(
                (CODE_FALSE_BLOCK, "positive case %s lands in %r, expected %r" % (case["case_id"], to, case["expect_state"]))
            )
            continue
        passing += 1
    return passing, len(cases)


def check_corpus(doc: dict, index: dict, corpus: dict, failures: list) -> tuple:
    selected = doc["corpus_selection"]
    available = {case["case_id"]: case for case in corpus["cases"]}
    missing = [case_id for case_id in selected if case_id not in available]
    for case_id in missing:
        failures.append((CODE_DOCUMENT, "selected corpus case %s is absent from the committed corpus" % case_id))

    rows = {row["case_id"]: row for row in doc["corpus_mapping"]}
    extra = sorted(set(rows) - set(selected))
    if extra:
        failures.append((CODE_DOCUMENT, "mapping rows for unselected corpus cases: %s" % ", ".join(extra)))

    codes = set(doc["referenced_sets"]["pre_mutation_reason_codes"]["values"])
    codes |= set(doc["referenced_sets"]["pre_final_reason_codes"]["values"])

    mapped = 0
    for case_id in selected:
        row = rows.get(case_id)
        if row is None:
            failures.append((CODE_DOCUMENT, "selected corpus case %s has no mapping row" % case_id))
            continue
        case = available.get(case_id)
        if case is None:
            continue
        if case["kind"] == "control":
            if not row.get("control") or row.get("scored") is not False:
                failures.append(
                    (CODE_DOCUMENT, "corpus control case %s must be declared control with scored=false" % case_id)
                )
            else:
                mapped += 1
            continue
        key = (row.get("state"), row.get("event"))
        if key not in index:
            failures.append((CODE_DOCUMENT, "corpus case %s maps to undeclared cell %s" % (case_id, key)))
            continue
        check = row.get("check", "")
        if not CHECK_ID_RE.match(check):
            failures.append((CODE_DOCUMENT, "corpus case %s: check %r is not a typed check id" % (case_id, check)))
            continue
        if check.split(":", 1)[1] not in codes:
            failures.append(
                (CODE_DOCUMENT, "corpus case %s: check %r references a code outside the frozen P0.2 enums" % (case_id, check))
            )
            continue
        mapped += 1
    return mapped, len(selected)


def check_contracts(doc: dict, bodies: dict, failures: list) -> int:
    """doc<->data equality plus the structural sections each contract owes."""
    required_headings = doc["contract_required_headings"]
    for name, body in bodies.items():
        for heading in required_headings:
            if heading not in body:
                failures.append((CODE_SET_DRIFT, "%s: missing required section %r" % (name, heading)))

    blocks = {}
    for name, body in bodies.items():
        for match in DECLARED_SET_RE.finditer(body):
            set_name = match.group("name")
            values = [line.strip() for line in match.group("body").strip().splitlines() if line.strip()]
            if set_name in blocks:
                failures.append(
                    (CODE_SET_DRIFT, "declared set %s is marked in two contracts (%s and %s)" % (set_name, blocks[set_name][0], name))
                )
                continue
            blocks[set_name] = (name, values)

    declared = doc["declared_sets"]
    for set_name, values in declared.items():
        if set_name not in blocks:
            failures.append((CODE_SET_DRIFT, "declared set %s has no marked block in any contract" % set_name))
            continue
        contract, doc_values = blocks[set_name]
        if doc_values != list(values):
            failures.append(
                (
                    CODE_SET_DRIFT,
                    "declared set %s differs between %s and the cases file (%s vs %s)"
                    % (set_name, contract, doc_values, list(values)),
                )
            )
    for set_name in sorted(set(blocks) - set(declared)):
        failures.append(
            (
                CODE_SET_DRIFT,
                "contract %s marks %s as a declared set, but P2.1 does not own it "
                "(a referenced set is cited, never re-minted)" % (blocks[set_name][0], set_name),
            )
        )

    for set_name, entry in doc["referenced_sets"].items():
        contract = entry.get("cited_in")
        body = bodies.get(contract)
        if body is None:
            failures.append((CODE_SET_DRIFT, "referenced set %s cites unknown contract %r" % (set_name, contract)))
            continue
        frozen = body.split("## Frozen upstream", 1)
        if len(frozen) < 2:
            failures.append((CODE_SET_DRIFT, "%s has no `## Frozen upstream` section" % contract))
            continue
        section = frozen[1].split("\n## ", 1)[0]
        if entry["source"] not in section:
            failures.append(
                (
                    CODE_SET_DRIFT,
                    "%s: `## Frozen upstream` does not cite %s at %s" % (contract, set_name, entry["source"]),
                )
            )
    return len(blocks)


# --------------------------------------------------------------------------
# Full run + mutations
# --------------------------------------------------------------------------


def run_checks(doc: dict, corpus: dict, bodies: dict) -> tuple:
    failures = []
    stats = {}

    if doc.get("schema_version") != CASES_SCHEMA_VERSION:
        failures.append((CODE_DOCUMENT, "schema_version %r, expected %r" % (doc.get("schema_version"), CASES_SCHEMA_VERSION)))
        return failures, stats

    check_sets(doc, failures)
    check_new_reason_codes(doc, failures)
    index = check_matrix(doc, failures)
    check_deny_class_partition(doc, failures)
    projected, journal_reached = check_projections(doc, index, failures)
    check_decision_function(doc, index, failures)
    check_reopen_rule(doc, failures)
    check_finding_identity(doc, failures)
    check_authority_profiles(doc, index, failures)
    check_portability(doc, failures)
    positive_ok, positive_total = check_positive_cases(doc, index, failures)
    mapped, selected = check_corpus(doc, index, corpus, failures)
    marked = check_contracts(doc, bodies, failures)

    stats.update(
        cells=len(doc["cells"]),
        expected_cells=len(doc["declared_sets"]["states"]) * len(doc["declared_sets"]["events"]),
        transitions=sum(1 for cell in doc["cells"] if cell["kind"] == "transition"),
        impossibilities=sum(1 for cell in doc["cells"] if cell["kind"] == "impossible"),
        states_projected=projected,
        states_total=len(doc["declared_sets"]["states"]),
        journal_reached=journal_reached,
        journal_total=len(doc["referenced_sets"]["journal_result_values"]["values"]),
        corpus_mapped=mapped,
        corpus_selected=selected,
        positive_ok=positive_ok,
        positive_total=positive_total,
        marked_sets=marked,
    )
    return failures, stats


def apply_mutation(doc: dict, mutation: dict) -> dict:
    """Declared, auditable mutation operations — no free-form patching."""
    mutated = copy.deepcopy(doc)
    op = mutation["op"]
    args = mutation["args"]

    if op == "drop-cell":
        mutated["cells"] = [
            cell for cell in mutated["cells"]
            if not (cell["state"] == args["state"] and cell["event"] == args["event"])
        ]
    elif op == "duplicate-cell":
        for cell in list(mutated["cells"]):
            if cell["state"] == args["state"] and cell["event"] == args["event"]:
                mutated["cells"].append(copy.deepcopy(cell))
                break
    elif op == "drop-branch":
        for cell in mutated["cells"]:
            if cell["state"] == args["state"] and cell["event"] == args["event"]:
                cell["guard"]["branches"] = [
                    branch for branch in cell["guard"]["branches"] if args["when"] not in branch["when"]
                ]
    elif op == "drop-guard":
        for cell in mutated["cells"]:
            if cell["state"] == args["state"] and cell["event"] == args["event"]:
                branch = cell["guard"]["branches"][0]
                cell.pop("guard")
                cell["to"] = branch["to"]
                cell["decision"] = branch["decision"]
                cell["journal"] = branch.get("journal")
    elif op == "retarget-branch":
        for cell in mutated["cells"]:
            if cell["state"] == args["state"] and cell["event"] == args["event"]:
                if "guard" in cell:
                    for branch in cell["guard"]["branches"]:
                        if args["when"] in branch["when"]:
                            branch["to"] = args["to"]
                            branch["decision"] = args["decision"]
                else:
                    cell["to"] = args["to"]
                    cell["decision"] = args["decision"]
    elif op == "clear-journal":
        for cell in mutated["cells"]:
            for _when, branch in branches_of(cell):
                if branch.get("journal") == args["journal"]:
                    branch["journal"] = None
    elif op == "set-path":
        node = mutated
        parts = args["path"].split(".")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = args["value"]
    elif op == "drop-path":
        node = mutated
        parts = args["path"].split(".")
        for part in parts[:-1]:
            node = node[part]
        node.pop(parts[-1], None)
    else:
        raise SystemExit("FAIL: %s: unknown mutation op %r" % (CODE_DOCUMENT, op))
    return mutated


def run_mutations(doc: dict, corpus: dict, bodies: dict, failures: list) -> tuple:
    passed = 0
    for mutation in doc["mutations"]:
        mutated = apply_mutation(doc, mutation)
        try:
            produced, _stats = run_checks(mutated, corpus, bodies)
        except Exception as error:  # a mutation must fail as a typed code, never as a traceback
            failures.append((CODE_DOCUMENT, "mutation %s raised %r instead of a typed failure" % (mutation["id"], error)))
            continue
        codes = {code for code, _detail in produced}
        if not produced:
            failures.append((mutation["expect"], "mutation %s did not fail at all" % mutation["id"]))
            continue
        if mutation["expect"] not in codes:
            failures.append(
                (
                    mutation["expect"],
                    "mutation %s failed for the WRONG reason: expected %s, got %s"
                    % (mutation["id"], mutation["expect"], ", ".join(sorted(codes))),
                )
            )
            continue
        passed += 1
    return passed, len(doc["mutations"])


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the P2.1 execution state machine, review budget and portability layer."
    )
    parser.add_argument("--corpus", required=True, help="committed P0.1 corpus.json")
    parser.add_argument("--cases", required=True, help="artifacts/P2.1/state-transition-cases.json")
    parser.add_argument("--contracts-dir", required=True, help="root/contracts directory of this plan")
    args = parser.parse_args(argv)

    doc = load_json(args.cases)
    corpus = load_json(args.corpus)
    bodies = load_contracts(args.contracts_dir, doc["contracts"])

    failures, stats = run_checks(doc, corpus, bodies)
    mutations_ok, mutations_total = (0, len(doc.get("mutations", [])))
    if not failures:
        mutations_ok, mutations_total = run_mutations(doc, corpus, bodies, failures)

    if failures:
        for code, detail in failures:
            print("FAIL: %s: %s" % (code, detail))
        return 1

    print(
        "execution state machine v1 validated: %d/%d cells (%d transitions, %d declared impossibilities), "
        "%d/%d states projected, %d/%d journal results reachable, %d/%d corpus cases mapped, "
        "%d/%d positive routine cases pass, %d/%d mutations failed for their declared reason, "
        "%d declared sets proven doc<->data"
        % (
            stats["cells"], stats["expected_cells"], stats["transitions"], stats["impossibilities"],
            stats["states_projected"], stats["states_total"],
            stats["journal_reached"], stats["journal_total"],
            stats["corpus_mapped"], stats["corpus_selected"],
            stats["positive_ok"], stats["positive_total"],
            mutations_ok, mutations_total,
            stats["marked_sets"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
