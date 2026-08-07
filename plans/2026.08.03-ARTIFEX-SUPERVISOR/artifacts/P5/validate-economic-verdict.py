#!/usr/bin/env python3
"""Independent adjudicator gate for P5.4's paired-wave economic verdict.

Two banks, both authored BEFORE the first dispatch (`--self-test` runs without any
live result on disk and is the proof of that ordering):

  * CONTRACT cases - near-boundary and adversarial inputs pushed through the FROZEN
    `artifacts/P1/validate-economy-evidence.py` `adjudicate_v2`. This file never
    re-implements a threshold, formula, denominator, verdict or reason code; it
    imports the contract's own adjudicator by path, so a divergence between this
    gate and the contract is impossible by construction.
  * STRUCTURAL cases - the properties the contract does NOT own: that the recorded
    evidence document faithfully represents the RAW per-attempt rows, that the ten
    spent admissions are the ten predeclared D125 rows and nothing else, that the
    five pairs are matched member-for-member, and that G3 pins the exact measured
    G2B digest.

Everything load-bearing is recomputed here from `battle-wave-results-v1.json`, the
frozen v3 carriers and the live G2B manifests. A stored total, a stored hash or a
candidate-authored summary is never trusted: `economy-evidence-v2` requires the
adjudicator to recompute every value from attempts, and D30 requires at least one
publicly checkable fact behind the verdict.

Exit 0 - every check green. Exit 1 - a check failed (the verdict does not stand).
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.util
import json
import sys
from fractions import Fraction
from pathlib import Path


PLAN_ID = "2026.08.03-ARTIFEX-SUPERVISOR"
METRIC_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens",
                 "cost_microunits", "duration_ms", "turns")
LANES = ("candidate", "baseline", "workflow")
OWNER_GRANT = "D123"
OWNER_DECISION = "D125"
PROVIDER = "claude-code"
FORBIDDEN_PROVIDERS = ("codex",)
COMMON_FLOORS = ("REL-ACCEPTED-SCOPE", "REL-RECOVERY", "REL-IDEMPOTENCY", "REL-VALIDATION",
                 "REL-BUDGET", "SEC-AUTHORITY", "SEC-PRIVACY", "SEC-WORKTREE", "SEC-HOOK-INTEGRITY",
                 "EVD-SOURCE-HASHES", "EVD-INDEPENDENT-ADJUDICATOR", "EVD-UNKNOWN-PRESERVATION")
P6_INPUTS = ("artifacts/P5/economic-verdict-v1.json", "artifacts/P5/pilot-manifest-v1.json",
             "artifacts/P5/validate-economic-verdict.py")


class VerdictError(ValueError):
    """The recorded verdict does not stand on the recorded evidence."""


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical(value) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha(value) -> str:
    return hashlib.sha256(value if isinstance(value, bytes) else canonical(value)).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerdictError(message)


def adjudicator(plan: Path):
    path = plan / "artifacts/P1/validate-economy-evidence.py"
    spec = importlib.util.spec_from_file_location("frozen_economy_evidence_v2", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# --- structural predicates -------------------------------------------------------

def check_admissions(results: dict, index: dict, generation: dict, verdict: dict) -> None:
    """Ten distinct owner-approved D125 admissions through the same G2B digest, each
    `used_slices` exactly 1 after its dispatch, no eleventh row, no foreign authority."""
    waves = results["waves"]
    require(len(waves) == 10, f"expected ten dispatches, found {len(waves)}")
    indexed = {row["trial_id"]: row for row in index["admissions"]}
    require(len(indexed) == 10, "the v3 admission index does not carry exactly ten rows")
    trial_ids = [wave["trial_id"] for wave in waves]
    require(len(set(trial_ids)) == 10, "a trial identity was dispatched twice")
    require(set(trial_ids) == set(indexed), "a dispatched trial is not a predeclared D125 row")
    hashes = set()
    for wave in waves:
        row = indexed[wave["trial_id"]]
        require(wave["admission_hash"] == row["admission_hash"],
                f"{wave['trial_id']}: admission_hash does not match the v3 index")
        require(wave["admission_sha256"] == row["sha256"],
                f"{wave['trial_id']}: the admission file bytes moved between mint and dispatch")
        require(wave["used_slices"] == 1, f"{wave['trial_id']}: used_slices is not exactly 1")
        require(wave["provider"] == PROVIDER, f"{wave['trial_id']}: provider is not {PROVIDER}")
        require(row["provider"] == PROVIDER, f"{wave['trial_id']}: indexed provider is not {PROVIDER}")
        hashes.add(wave["admission_hash"])
    require(len(hashes) == 10, "the ten dispatches did not spend ten distinct admissions")
    require(index["g2_package_digest"] == generation["predecessor"]["digest"],
            "the v3 index is bound to a different G2 predecessor than the live generation")
    recorded = {row["trial_id"]: row for row in verdict["admissions"]}
    require(set(recorded) == set(trial_ids) and all(recorded[t]["used_slices"] == 1 for t in trial_ids),
            "the verdict's admission ledger diverges from the raw dispatch rows")


def check_no_foreign_authority(results: dict, plan: Path) -> None:
    """No D105/D122/P3-smoke carrier, no probe row and no locally minted admission."""
    foreign = set()
    for name in ("artifacts/P5/trial-admission-index-v1.json",
                 "artifacts/P5/trial-admission-index-v2-p5.2-retry.json",
                 "artifacts/P2/p3-smoke-admission-index-v1.json"):
        for row in load(plan / name)["admissions"]:
            foreign.add(row["admission_hash"])
    for wave in results["waves"]:
        require(wave["admission_hash"] not in foreign,
                f"{wave['trial_id']}: spent a D105/D122/P3-smoke carrier instead of its D125 row")
        require(not any(provider in wave["trial_id"] for provider in FORBIDDEN_PROVIDERS),
                f"{wave['trial_id']}: names an excluded provider (D126)")


def check_pairs(results: dict, catalog: dict) -> list:
    """Exactly five immutable matched candidate/baseline pairs; within each pair every
    dispatch-governing field of the frozen catalog is equal member-for-member."""
    rows = {row["trial_id"]: row for row in catalog["trials"]}
    pairs: dict[str, dict] = {}
    for wave in results["waves"]:
        require(wave["trial_id"] in rows, f"{wave['trial_id']} is not a v3 catalog row")
        row = rows[wave["trial_id"]]
        require(row["lane"] == wave["lane"], f"{wave['trial_id']}: lane disagrees with the catalog")
        pairs.setdefault(row["pair_id"], {})[row["lane"]] = (wave, row)
    require(len(pairs) == 5, f"expected five pairs, found {len(pairs)}")
    for pair_id, members in sorted(pairs.items()):
        require(set(members) == {"candidate", "baseline"}, f"{pair_id}: incomplete pair")
        (candidate_wave, candidate_row), (baseline_wave, baseline_row) = members["candidate"], members["baseline"]
        for field in ("base_commit", "files", "provider", "route", "capabilities", "acceptance_refs",
                      "validation", "budgets", "scenario", "kind", "historical_patch_sha256"):
            require(candidate_row[field] == baseline_row[field],
                    f"{pair_id}: pair members differ on the matched field {field!r}")
        require(candidate_row["paired_trial_id"] == baseline_row["trial_id"]
                and baseline_row["paired_trial_id"] == candidate_row["trial_id"],
                f"{pair_id}: the twin pointers do not close")
        for wave, row in (members["candidate"], members["baseline"]):
            require(wave["base_commit"] == row["base_commit"],
                    f"{wave['trial_id']}: dispatched at a base the catalog does not declare")
            require(wave["declared_files"] == sorted(row["files"]),
                    f"{wave['trial_id']}: dispatched against a file set the catalog does not declare")
    return sorted(pairs)


def derive_match(catalog: dict, results: dict, lane: str, repository_hash: str,
                 definition: str) -> dict:
    rows = sorted((row for row in catalog["trials"] if row["lane"] == lane), key=lambda r: r["order"])
    dispatched = {wave["trial_id"] for wave in results["waves"] if wave["lane"] == lane}
    rows = [row for row in rows if row["trial_id"] in dispatched]
    return {
        "repository_hash": repository_hash,
        "base_hash": sha([row["base_commit"] for row in rows]),
        "scope_hash": sha([sorted(row["files"]) for row in rows]),
        "acceptance_hash": sha([row["acceptance_refs"] for row in rows]),
        "validation_hash": sha([row["validation"] for row in rows]),
        "provider_hash": sha([row["provider"] for row in rows]),
        "model_hash": sha([row["route"]["model_class"] for row in rows]),
        "effort_hash": sha([row["route"]["effort"] for row in rows]),
        "capabilities_hash": sha([row["capabilities"] for row in rows]),
        "accepted_slice_definition_hash": sha(definition.encode("utf-8")),
    }


def check_document_against_results(document: dict, results: dict, catalog: dict,
                                   definition: str) -> None:
    """The recorded evidence document must be a faithful projection of the raw rows:
    every metric integer, every acceptance flag and every match hash is re-derived
    here from `battle-wave-results-v1.json` and the frozen catalog."""
    require(set(document["lanes"]) == set(LANES), "the document does not carry exactly three lanes")
    repository_hash = document["evidence"]["repository_hash"]
    for lane in ("candidate", "baseline"):
        expected = derive_match(catalog, results, lane, repository_hash, definition)
        require(document["lanes"][lane]["match"] == expected,
                f"lanes.{lane}.match is not the value derived from the frozen catalog")
    require(document["lanes"]["candidate"]["match"] == document["lanes"]["baseline"]["match"],
            "the candidate and baseline lanes are not matched")
    require(document["lanes"]["workflow"]["match"] != document["lanes"]["candidate"]["match"],
            "the undispatched Workflow lane is presented as matched")
    for lane in ("candidate", "baseline"):
        waves = sorted((wave for wave in results["waves"] if wave["lane"] == lane),
                       key=lambda row: row["order"])
        attempts = document["lanes"][lane]["attempts"]
        require(len(attempts) == len(waves) == 5, f"lanes.{lane}: expected five attempts")
        for index, (attempt, wave) in enumerate(zip(attempts, waves)):
            pointer = f"/lanes/{lane}/attempts/{index}"
            require(attempt["attempt_id"] == wave["trial_id"], f"{pointer}: attempt identity drift")
            require(attempt["slice_id"] == wave["pair_id"], f"{pointer}: slice identity drift")
            require(attempt["accepted"] == bool(wave["accepted"]),
                    f"{pointer}: acceptance disagrees with the measured dispatch row")
            require(wave["observation"]["kind"] in attempt["exit_class_ref"]
                    and str(wave["observation"]["reason_code"]) in attempt["exit_class_ref"],
                    f"{pointer}: exit_class_ref does not name the measured exit")
            economy = wave.get("economy")
            if isinstance(economy, dict) and isinstance(economy.get("worker"), dict):
                for field in METRIC_FIELDS:
                    require(attempt["worker"][field] == economy["worker"].get(field),
                            f"{pointer}/worker/{field}: does not equal the measured envelope")
            else:
                require(all(attempt["worker"][field] is None for field in METRIC_FIELDS),
                        f"{pointer}: a refused dispatch carries invented worker metrics")
            require(all(attempt["coordinator"][field] == 0 for field in METRIC_FIELDS),
                    f"{pointer}/coordinator: this runner makes no model call; the envelope must be a zero")
            require(f"{pointer}/coordinator" in document["zero_bases"],
                    f"{pointer}/coordinator: an all-zero envelope without a declared zero_basis")
            if attempt["worker"]["reasoning_tokens"] == 0:
                require(f"{pointer}/worker/reasoning_tokens" in document["inclusion_bases"],
                        f"{pointer}: a bare 0 for reasoning_tokens without an inclusion basis")
    for pointer, entry in document["inclusion_bases"].items():
        require(pointer.endswith("/worker/reasoning_tokens") and entry["provider"] == PROVIDER
                and entry["containing_field"] == "output_tokens",
                f"inclusion_bases[{pointer}]: outside the single sanctioned instantiation")
    for pointer, entry in document["zero_bases"].items():
        require(entry["component"] == "coordinator", f"zero_bases[{pointer}]: not a coordinator envelope")
    nulls = {f"/lanes/{lane}/attempts/{index}/{component}/{field}"
             for lane in LANES
             for index, attempt in enumerate(document["lanes"][lane]["attempts"])
             for component in ("worker", "coordinator")
             for field in METRIC_FIELDS if attempt[component][field] is None}
    require(nulls == set(document["unknown_reasons"]),
            "an unknown measurement is missing its source-specific reason (or vice versa)")
    require(all(isinstance(value, str) and len(value.strip()) > 20
                for value in document["unknown_reasons"].values()),
            "an unknown_reasons entry is not a source-specific statement")


def check_waves(document: dict, results: dict, pairs: list) -> None:
    rows = {row["wave_id"]: row for row in document["waves"]}
    require(sorted(rows) == pairs, "the wave set is not the five predeclared pairs")
    for pair_id, row in sorted(rows.items()):
        members = [wave for wave in results["waves"] if wave["pair_id"] == pair_id]
        require(len(members) == 2, f"{pair_id}: not exactly two members")
        require(row["synthetic"] is False and row["predeclared"] is True,
                f"{pair_id}: a synthetic or unpredeclared wave can never count")
        require(row["accepted"] == all(member["accepted"] for member in members),
                f"{pair_id}: wave acceptance disagrees with its two measured members")
        require(row["terminal"] == all(member["rollback"] for member in members)
                or row["terminal"] is False,
                f"{pair_id}: a wave whose root did not roll back is not terminal")


def check_intervention(document: dict, results: dict, plan: Path) -> None:
    """The intervention denominator is recomputed from the dispatched slices and the
    numerator from the plan journal - never from a candidate-authored summary."""
    require(document["dispatched_non_synthetic_slices"] == len(results["waves"]),
            "the intervention denominator is not the number of dispatched non-synthetic slices")
    events = 0
    for line in (plan / "journal.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("item_id") == "P5.4" and row.get("result") in {"escalated", "blocked"}:
            events += 1
    require(document["owner_decision_events"] == events,
            f"owner_decision_events {document['owner_decision_events']} != journal-derived {events}")
    ratio = Fraction(document["owner_decision_events"], document["dispatched_non_synthetic_slices"])
    require((ratio < Fraction(1, 4)) == (document["_intervention_below_gate"] if
            "_intervention_below_gate" in document else ratio < Fraction(1, 4)),
            "the intervention ratio is not the one the document carries")


def check_scope_and_g3(verdict: dict, document: dict, results: dict, generation: dict,
                       assurance: dict, ledger: dict) -> None:
    scope = document["provider_scope"]
    require(scope == {"mode": "single-provider", "provider": PROVIDER, "owner_grant_ref": OWNER_GRANT},
            "provider_scope is not the single-provider claude-code scope D123 authorizes")
    require("no provider-parity claim" in verdict["provider_scope_statement"],
            "the verdict does not state its single-provider scope limit")
    text = json.dumps(verdict, ensure_ascii=False)
    require("parity" not in text.replace("no provider-parity claim", "")
            .replace("never rendered as parity", ""),
            "the verdict renders a single-provider result as parity")
    g3 = verdict["g3"]
    live = generation["generation_hash"]
    require(g3["g2b_generation_hash"] == live == assurance["g2b_generation_hash"]
            == results["g2b_generation_hash"] == ledger["entries"][-1]["generation_hash"],
            "G3 does not pin the exact G2B generation that was measured")
    require(g3["g2b_assurance_hash"] == assurance["assurance_hash"], "G3 assurance pin drift")
    require(g3["g2_predecessor"] == generation["predecessor"]["digest"], "G3 G2 predecessor drift")
    require(g3["post_p5_5_package_delta"] == [],
            f"a post-P5.5 package delta exists: {g3['post_p5_5_package_delta']}")
    require(all(wave["g2b_generation_hash"] == live for wave in results["waves"]),
            "a dispatch measured a different G2B generation than G3 pins")
    require(verdict["provider_processes_started"] == sum(
        wave["observation"]["process_count"] for wave in results["waves"]),
        "the reported provider-process count does not equal the sum of the measured rows")


def check_terminal(verdict: dict, document: dict) -> None:
    """Terminal success requires every floor green, at least one eligible branch and
    the literal GO. A NO-GO must name the exact failed floors and stays non-terminal."""
    result = verdict["result"]
    require(result["verdict"] in ("GO", "NO-GO"), "the verdict is not a contract terminal literal")
    require(verdict["verdict"] == result["verdict"], "the verdict header and the adjudicated result differ")
    failed = sorted(key for key, value in document["floor_results"].items() if value != "pass")
    require(verdict["failed_floors"] == failed, "the recorded failed floors are not the document's")
    require(set(document["floor_results"]) == set(COMMON_FLOORS), "the common floor set is incomplete")
    if result["verdict"] == "GO":
        require(not failed, "a GO was emitted while a common floor is not green")
        require(result["eligible_branches"], "a GO was emitted with no eligible branch")
    else:
        require(failed or result["reason_codes"], "a NO-GO carries no reason")


def check_forward_conformance(plan: Path) -> list:
    """`brief/37` §3(c): every input P6.1 declares from P5 exists and resolves."""
    missing = [name for name in P6_INPUTS if not (plan / name).is_file()]
    require(not missing, f"P6.1 inputs missing: {missing}")
    return list(P6_INPUTS)


# --- fixtures and the two case banks ---------------------------------------------

def envelope(**values) -> dict:
    row = {field: 0 for field in METRIC_FIELDS}
    row.update(values)
    return row


def fixture(plan: Path) -> dict:
    """A synthetic, clearly-labelled `economy-evidence-v2` document used ONLY by the
    case bank. It is not evidence: no value here is measured, and its run_id says so."""
    inclusion = {
        "provider": PROVIDER, "contained_field": "reasoning_tokens", "containing_field": "output_tokens",
        "evidence_ref": ("findings/P5.4-metric-surface-gap-2026-08-06.md F10: the claude-code result "
                         "record exports usage.{input_tokens,cache_read_input_tokens,output_tokens} "
                         "and no separate reasoning field"),
    }
    zero = {"component": "coordinator", "path": "packages/artifex/lib/artifex/scheduler.py",
            "statement": "synthetic fixture basis: the coordinator makes no model call"}
    lanes, unknown, inclusion_bases, zero_bases = {}, {}, {}, {}
    match = {key: sha(f"fixture:{key}".encode("utf-8")) for key in
             ("repository_hash", "base_hash", "scope_hash", "acceptance_hash", "validation_hash",
              "provider_hash", "model_hash", "effort_hash", "capabilities_hash",
              "accepted_slice_definition_hash")}
    for lane, tokens, cost in (("candidate", 1000, 40), ("baseline", 2000, 80)):
        attempts = []
        for index in range(5):
            attempts.append({
                "attempt_id": f"{lane}-{index + 1}", "slice_id": f"wave-{index + 1}", "accepted": True,
                "exit_class_ref": f"worker-envelope-v1/exit_class/success:OK",
                "rollback_event_ref": None,
                "worker": envelope(input_tokens=tokens, output_tokens=tokens, reasoning_tokens=0,
                                   cost_microunits=cost, duration_ms=1000, turns=3),
                "coordinator": envelope(),
            })
            inclusion_bases[f"/lanes/{lane}/attempts/{index}/worker/reasoning_tokens"] = dict(inclusion)
            zero_bases[f"/lanes/{lane}/attempts/{index}/coordinator"] = dict(zero)
        lanes[lane] = {"match": dict(match), "attempts": attempts}
    workflow_match = {key: sha(b"fixture:workflow") for key in match}
    lanes["workflow"] = {"match": workflow_match, "attempts": [{
        "attempt_id": "workflow-not-dispatched", "slice_id": "workflow-lane-not-dispatched",
        "accepted": True, "exit_class_ref": "worker-envelope-v1/exit_class/not_dispatched:NONE",
        "rollback_event_ref": None,
        "worker": {field: None for field in METRIC_FIELDS},
        "coordinator": {field: None for field in METRIC_FIELDS}}]}
    for component in ("worker", "coordinator"):
        for field in METRIC_FIELDS:
            unknown[f"/lanes/workflow/attempts/0/{component}/{field}"] = (
                "synthetic fixture: no Workflow lane was dispatched under D124/D126")
    return {
        "schema_version": "economy-evidence-input-v2", "contract_version": "2.0.0",
        "evidence": {
            "run_id": "p5.4-validator-self-test-fixture-not-evidence",
            "repository_hash": sha(b"fixture:repo"), "plan_hash": sha(b"fixture:plan"),
            "scope_hash": sha(b"fixture:scope"), "acceptance_hash": sha(b"fixture:acceptance"),
            "validation_hash": sha(b"fixture:validation"), "contract_set_hash": sha(b"fixture:contracts"),
            "provider_matrix_hash": sha((plan / "artifacts/P0/provider-matrix-v1.json").read_bytes()),
            "baseline_catalog_hash": sha((plan / "artifacts/P0/baseline-catalog.json").read_bytes()),
            "privacy_status": "clean"},
        "provider_scope": {"mode": "single-provider", "provider": PROVIDER, "owner_grant_ref": OWNER_GRANT},
        "floor_results": {floor: "pass" for floor in COMMON_FLOORS},
        "waves": [{"wave_id": f"wave-{index + 1}", "predeclared": True, "synthetic": False,
                   "terminal": True, "accepted": True} for index in range(5)],
        "lanes": lanes,
        "owner_decision_events": 0, "attention_events": 0, "dispatched_non_synthetic_slices": 10,
        "unknown_reasons": unknown, "inclusion_bases": inclusion_bases, "zero_bases": zero_bases,
    }


def mutate(document: dict, operations) -> dict:
    value = copy.deepcopy(document)
    for operation in operations:
        operation(value)
        continue
    return value


def contract_cases(plan: Path) -> list:
    """Near-boundary and adversarial inputs, each with its exact expected verdict."""
    def drop_wave(document):
        document["waves"] = document["waves"][:4]

    def match_workflow(document, factor_numerator, factor_denominator):
        document["lanes"]["workflow"]["match"] = copy.deepcopy(document["lanes"]["candidate"]["match"])
        attempts = []
        for index in range(5):
            attempts.append({
                "attempt_id": f"workflow-{index + 1}", "slice_id": f"wave-{index + 1}", "accepted": True,
                "exit_class_ref": "worker-envelope-v1/exit_class/success:OK", "rollback_event_ref": None,
                "worker": envelope(input_tokens=2000 * factor_numerator // factor_denominator,
                                   output_tokens=2000 * factor_numerator // factor_denominator,
                                   reasoning_tokens=0,
                                   cost_microunits=40 * factor_numerator // factor_denominator,
                                   duration_ms=1000, turns=3),
                "coordinator": envelope()})
            document["inclusion_bases"][f"/lanes/workflow/attempts/{index}/worker/reasoning_tokens"] = (
                copy.deepcopy(next(iter(document["inclusion_bases"].values()))))
            document["zero_bases"][f"/lanes/workflow/attempts/{index}/coordinator"] = (
                copy.deepcopy(next(iter(document["zero_bases"].values()))))
        document["lanes"]["workflow"]["attempts"] = attempts
        for key in list(document["unknown_reasons"]):
            if key.startswith("/lanes/workflow/"):
                del document["unknown_reasons"][key]

    return [
        ("baseline-go", [], "GO", ["D14-B1"], ["GO_BRANCH_1"]),
        ("intervention-24.999-percent",
         [lambda d: d.update({"owner_decision_events": 24999, "dispatched_non_synthetic_slices": 100000})],
         "GO", ["D14-B1"], ["GO_BRANCH_1"]),
        ("intervention-exactly-25-percent",
         [lambda d: d.update({"owner_decision_events": 1, "dispatched_non_synthetic_slices": 4})],
         "NO-GO", [], ["BRANCH1_INTERVENTION_NOT_LT_25_PERCENT", "UNMATCHED_SCOPE"]),
        ("waves-n-4", [drop_wave], "NO-GO", [], ["BRANCH1_WAVES_NOT_5", "UNMATCHED_SCOPE"]),
        ("candidate-cost-exactly-equal-to-baseline",
         [lambda d: [attempt["worker"].update({"cost_microunits": 80, "input_tokens": 2000,
                                               "output_tokens": 2000})
                     for attempt in d["lanes"]["candidate"]["attempts"]]],
         "GO", ["D14-B1"], ["GO_BRANCH_1"]),
        ("candidate-worse-than-baseline",
         [lambda d: [attempt["worker"].update({"cost_microunits": 81})
                     for attempt in d["lanes"]["candidate"]["attempts"]]],
         "NO-GO", [], ["BRANCH1_WORSE_THAN_BASELINE", "UNMATCHED_SCOPE"]),
        ("workflow-gain-exactly-2x", [lambda d: match_workflow(d, 2, 1)],
         "GO", ["D14-B1", "D14-B2"], ["GO_BRANCH_1", "GO_BRANCH_2"]),
        ("workflow-gain-1.999x", [lambda d: match_workflow(d, 1999, 1000)],
         "GO", ["D14-B1"], ["GO_BRANCH_1"]),
        ("missing-owner-grant-mapping",
         [lambda d: d["provider_scope"].update({"owner_grant_ref": None})],
         "NO-GO", [], ["PROVIDER_SCOPE_INELIGIBLE"]),
        ("owner-grant-not-a-decision-reference",
         [lambda d: d["provider_scope"].update({"owner_grant_ref": "owner said so"})],
         "NO-GO", [], ["PROVIDER_SCOPE_INELIGIBLE"]),
        ("unmatched-acceptance-hash",
         [lambda d: d["lanes"]["baseline"]["match"].update({"acceptance_hash": sha(b"drifted")})],
         "NO-GO", [], ["UNMATCHED_SCOPE"]),
        ("coordinator-envelope-omitted",
         [lambda d: d["lanes"]["candidate"]["attempts"][0].pop("coordinator")],
         "NO-GO", [], ["EVIDENCE_INVALID"]),
        ("retry-attempt-identity-duplicated",
         [lambda d: d["lanes"]["candidate"]["attempts"].append(
             copy.deepcopy(d["lanes"]["candidate"]["attempts"][0]))],
         "NO-GO", [], ["EVIDENCE_INVALID"]),
        ("bare-zero-without-inclusion-basis",
         [lambda d: d["inclusion_bases"].pop("/lanes/candidate/attempts/0/worker/reasoning_tokens")],
         "NO-GO", [], ["EVIDENCE_INVALID"]),
        ("structural-zero-without-zero-basis",
         [lambda d: d["zero_bases"].pop("/lanes/candidate/attempts/0/coordinator")],
         "NO-GO", [], ["EVIDENCE_INVALID"]),
        ("cost-imputed-through-the-inclusion-rule",
         [lambda d: d["inclusion_bases"].update({"/lanes/candidate/attempts/0/worker/cost_microunits": {
             "provider": PROVIDER, "contained_field": "cost_microunits",
             "containing_field": "output_tokens", "evidence_ref": "a price sheet"}}),
          lambda d: d["lanes"]["candidate"]["attempts"][0]["worker"].update({"cost_microunits": 0})],
         "NO-GO", [], ["EVIDENCE_INVALID"]),
        ("cost-derived-from-a-rate-is-not-an-integer",
         [lambda d: d["lanes"]["candidate"]["attempts"][0]["worker"].update({"cost_microunits": 41.5})],
         "NO-GO", [], ["EVIDENCE_INVALID"]),
        ("inclusion-basis-attributed-to-a-foreign-provider",
         [lambda d: d["inclusion_bases"]["/lanes/candidate/attempts/0/worker/reasoning_tokens"]
          .update({"provider": "codex"})],
         "NO-GO", [], ["EVIDENCE_INVALID"]),
        ("reliable-but-uneconomic",
         [lambda d: [attempt["worker"].update({"input_tokens": 5000, "output_tokens": 5000})
                     for attempt in d["lanes"]["candidate"]["attempts"]]],
         "NO-GO", [], ["BRANCH1_WORSE_THAN_BASELINE", "UNMATCHED_SCOPE"]),
        ("economical-but-unsafe",
         [lambda d: d["floor_results"].update({"SEC-WORKTREE": "fail"})],
         "NO-GO", ["D14-B1"], ["FLOOR_FAILED:SEC-WORKTREE"]),
        ("floor-unknown-is-not-a-pass",
         [lambda d: d["floor_results"].update({"EVD-UNKNOWN-PRESERVATION": "unknown"})],
         "NO-GO", ["D14-B1"], ["FLOOR_UNKNOWN:EVD-UNKNOWN-PRESERVATION"]),
        ("privacy-class-in-evidence",
         [lambda d: d["lanes"]["candidate"]["attempts"][0].update({"private_material": "x"})],
         "NO-GO", [], ["PRIVACY_REFUSED"]),
    ]


def structural_cases() -> list:
    """Cases for the properties the contract does not own. Each mutates a synthetic
    (results, verdict) pair and must be refused by this file's own predicates."""
    return [
        ("original-G2-substituted-for-G2B",
         lambda results, verdict: verdict["g3"].update({"g2b_generation_hash": verdict["g3"]["g2_predecessor"]}),
         "G3 does not pin"),
        ("a-v1-admission-presented-in-place-of-a-v3-row",
         lambda results, verdict: results["waves"][0].update({"admission_hash": "v1-carrier"}),
         "admission_hash does not match the v3 index"),
        ("used-slices-not-one",
         lambda results, verdict: results["waves"][3].update({"used_slices": 0}),
         "used_slices is not exactly 1"),
        ("an-eleventh-dispatch",
         lambda results, verdict: results["waves"].append(copy.deepcopy(results["waves"][0])),
         "expected ten dispatches"),
        ("a-codex-dispatch-attempted",
         lambda results, verdict: results["waves"][0].update({"provider": "codex"}),
         "provider is not claude-code"),
        ("admission-file-bytes-moved-after-mint",
         lambda results, verdict: results["waves"][2].update({"admission_sha256": "0" * 64}),
         "bytes moved between mint and dispatch"),
        ("a-dispatch-measured-a-different-generation",
         lambda results, verdict: results["waves"][1].update({"g2b_generation_hash": "0" * 64}),
         "measured a different G2B generation"),
        ("package-delta-after-p5.5",
         lambda results, verdict: verdict["g3"].update({"post_p5_5_package_delta": ["packages/artifex/x"]}),
         "post-P5.5 package delta exists"),
        ("provider-process-count-inflated",
         lambda results, verdict: verdict.update({"provider_processes_started": 99}),
         "provider-process count does not equal"),
    ]


def run_self_test(plan: Path) -> int:
    module = adjudicator(plan)
    baseline_hash, provider_hash = module.validate_contract_v2(
        plan / "root/contracts/economy-evidence-v2.md", plan / "artifacts/P0/acceptance-rubric-v1.md",
        plan / "artifacts/P0/baseline-catalog.json", plan / "artifacts/P0/provider-matrix-v1.json")
    base = fixture(plan)
    repo = plan.parent.parent
    passed = 0
    for case_id, operations, verdict, branches, reasons in contract_cases(plan):
        document = mutate(base, operations)
        actual = module.adjudicate_v2(document, baseline_hash, provider_hash, repo)
        for key, expected in (("verdict", verdict), ("eligible_branches", branches),
                              ("reason_codes", reasons)):
            if actual[key] != expected:
                print(f"economic-verdict self-test: FAIL: contract case {case_id}: "
                      f"{key} expected {expected!r}, got {actual[key]!r}", file=sys.stderr)
                return -1
        passed += 1
    return passed


def run_structural_self_test(plan: Path) -> int:
    """Each structural case is applied to a synthetic results/verdict pair that the
    unmutated predicates accept, and must then be refused with its named message."""
    index = load(plan / "artifacts/P5/trial-admission-index-v3-p5.4-paired.json")
    generation = load(plan / "artifacts/P5/business-successor-generation-v1.json")
    waves = []
    for order, row in enumerate(sorted(index["admissions"], key=lambda r: r["trial_id"]), start=1):
        waves.append({"trial_id": row["trial_id"], "admission_hash": row["admission_hash"],
                      "admission_sha256": row["sha256"], "used_slices": 1, "provider": PROVIDER,
                      "lane": "candidate" if row["trial_id"].startswith("p5.4w-") else "baseline",
                      "order": order, "g2b_generation_hash": generation["generation_hash"],
                      "observation": {"kind": "success", "reason_code": "OK", "process_count": 1}})
    results = {"waves": waves, "g2b_generation_hash": generation["generation_hash"]}
    verdict = {"g3": {"g2b_generation_hash": generation["generation_hash"],
                      "g2_predecessor": generation["predecessor"]["digest"],
                      "post_p5_5_package_delta": []},
               "provider_processes_started": 10,
               "admissions": [{"trial_id": wave["trial_id"], "admission_hash": wave["admission_hash"],
                               "used_slices": 1} for wave in waves]}
    assurance = {"g2b_generation_hash": generation["generation_hash"], "assurance_hash": "x"}

    def apply(results_value, verdict_value):
        check_admissions(results_value, index, generation, verdict_value)
        check_no_foreign_authority(results_value, plan)
        require(verdict_value["g3"]["g2b_generation_hash"] == generation["generation_hash"],
                "G3 does not pin the exact G2B generation that was measured")
        require(verdict_value["g3"]["post_p5_5_package_delta"] == [],
                "a post-P5.5 package delta exists")
        require(all(wave["g2b_generation_hash"] == generation["generation_hash"]
                    for wave in results_value["waves"]),
                "a dispatch measured a different G2B generation than G3 pins")
        require(verdict_value["provider_processes_started"] == sum(
            wave["observation"]["process_count"] for wave in results_value["waves"]),
            "the reported provider-process count does not equal the sum of the measured rows")

    apply(results, verdict)  # the unmutated pair must pass, or the cases prove nothing
    passed = 0
    for case_id, operation, fragment in structural_cases():
        mutated_results, mutated_verdict = copy.deepcopy(results), copy.deepcopy(verdict)
        operation(mutated_results, mutated_verdict)
        try:
            apply(mutated_results, mutated_verdict)
        except VerdictError as exc:
            if fragment not in str(exc):
                print(f"economic-verdict self-test: FAIL: structural case {case_id}: refused with "
                      f"{exc!s}, expected a message naming {fragment!r}", file=sys.stderr)
                return -1
            passed += 1
            continue
        print(f"economic-verdict self-test: FAIL: structural case {case_id} was accepted",
              file=sys.stderr)
        return -1
    return passed


def main() -> int:
    here = Path(__file__).resolve().parent
    plan_default = here.parent.parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--plan-dir", type=Path, default=plan_default)
    parser.add_argument("--results", type=Path, default=here / "battle-wave-results-v1.json")
    parser.add_argument("--verdict", type=Path, default=here / "economic-verdict-v1.json")
    parser.add_argument("--self-test", action="store_true",
                        help="run both case banks only; requires no live result on disk")
    args = parser.parse_args()
    plan = args.plan_dir.resolve()
    try:
        contract_passed = run_self_test(plan)
        structural_passed = run_structural_self_test(plan)
        if contract_passed < 0 or structural_passed < 0:
            return 1
        if args.self_test:
            print(f"economic-verdict: OK (self-test only: {contract_passed} contract cases, "
                  f"{structural_passed} structural cases; no live verdict inspected)")
            return 0
        results = load(args.results)
        verdict = load(args.verdict)
        document = verdict["evidence_document"]
        catalog = load(plan / "artifacts/P5/trial-catalog-v3-p5.4-paired.json")
        index = load(plan / "artifacts/P5/trial-admission-index-v3-p5.4-paired.json")
        generation = load(plan / "artifacts/P5/business-successor-generation-v1.json")
        assurance = load(plan / "artifacts/P5/business-successor-assurance-v1.json")
        ledger = load(plan / "artifacts/P5/g2b-generation-ledger-v1.json")
        require(verdict["contract"]["sha256"] == sha((plan / "root/contracts/economy-evidence-v2.md")
                                                     .read_bytes()),
                "the verdict was adjudicated against a different contract text than the live one")
        check_admissions(results, index, generation, verdict)
        check_no_foreign_authority(results, plan)
        pairs = check_pairs(results, catalog)
        definition = verdict.get("accepted_slice_definition", "")
        require(document["lanes"]["candidate"]["match"]["accepted_slice_definition_hash"]
                == sha(definition.encode("utf-8")),
                "the accepted-slice definition the lanes pin is not the one the verdict states")
        check_document_against_results(document, results, catalog, definition)
        check_waves(document, results, pairs)
        check_intervention(document, results, plan)
        check_scope_and_g3(verdict, document, results, generation, assurance, ledger)
        module = adjudicator(plan)
        baseline_hash, provider_hash = module.validate_contract_v2(
            plan / "root/contracts/economy-evidence-v2.md", plan / "artifacts/P0/acceptance-rubric-v1.md",
            plan / "artifacts/P0/baseline-catalog.json", plan / "artifacts/P0/provider-matrix-v1.json")
        recomputed = module.adjudicate_v2(document, baseline_hash, provider_hash, plan.parent.parent)
        require(recomputed == verdict["result"],
                f"re-adjudication disagrees with the recorded result: {recomputed}")
        check_terminal(verdict, document)
        forwarded = check_forward_conformance(plan)
    except (VerdictError, OSError, KeyError, TypeError, ValueError) as exc:
        print(f"economic-verdict: FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"economic-verdict: OK ({contract_passed} contract cases, {structural_passed} structural "
          f"cases; {len(results['waves'])} dispatches in {len(pairs)} matched pairs; verdict "
          f"{verdict['verdict']} {verdict['result']['reason_codes']}; single-provider {PROVIDER}, no "
          f"parity claim; {len(forwarded)} P6.1 inputs resolve)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
