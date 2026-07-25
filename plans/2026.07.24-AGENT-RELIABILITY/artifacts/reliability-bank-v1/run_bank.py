#!/usr/bin/env python3
"""run_bank.py — the sole executable owner of the frozen Reliability Bank v1.

Owner item: plans/2026.07.24-AGENT-RELIABILITY P0.3 (D10/D15/D30/D50/D53/D59).

The bank is a static paired task bank in the sense of `findings/05-external-practices.md`
(Anthropic agent-eval method: task + graders + transcript/outcome + harness). Everything
here is deterministic and stdlib-only: no LLM judge exists in this file, and a judge may
never override a deterministic critical assertion (D15).

Layers of baseline, named explicitly so nothing silently upgrades its proof class:

  layer 1 — the *declared* baseline frozen by this item. Each case carries a recorded
            pre-change behaviour whose provenance is machine-verified: either it is
            observed in the committed source-evidence bundle (`corpus-observed`,
            `bundle-observed`), or it is derived from a control that provably does not
            exist in the repository yet (`absent-control-derived`), proven by executable
            absence/presence probes over repo bytes.
  layer 2 — the *live paired* baseline, produced later (P3.3) by re-running the same
            cases and graders on the pre-plan tree (`artifacts/P0.1/pre-plan-sha.txt`,
            D45). Relative floors (Δ first-pass success, context input, owner
            intervention) resolve only against layer 2; layer 1 never substitutes for it.

Commands
--------
  baseline   validate bank, run probes, grade layer-1 baseline, write results + manifest
  verify     re-check manifest hashes, re-grade (byte-identical results gate), report probes
  candidate  grade a candidate transcript file with the same graders and check floors
  sample     print the deterministic manifest-seed sample of cases

Exit code 0 = green; 1 = any failure. Silent skip is not a possible outcome.
"""

import argparse
import fnmatch
import hashlib
import json
import math
import re
import statistics
import sys
from pathlib import Path

BANK_DIR = Path(__file__).resolve().parent
REPO_ROOT = BANK_DIR.parents[3]
SCHEMA_VERSION = "reliability-bank/v1"

# ---------------------------------------------------------------------------
# closed vocabularies
# ---------------------------------------------------------------------------
CASE_KINDS = {"critical", "control"}
PROVENANCE = {"corpus-observed", "bundle-observed", "absent-control-derived"}
PROBE_KINDS = {"absent_pattern", "present_pattern", "present_path"}
EVENT_TYPES = {
    "read", "contract_compiled", "pre_mutation_check", "block", "mutation",
    "owner_question", "premature_stop", "redundant_approval", "audit_round",
    "finding", "final_response", "handoff_emitted", "consumer_check",
    "route_declared", "capability_probe", "identity_resolution", "hook_invocation",
    "publication", "portability_check", "trace_emitted",
}
OPERATORS = {
    "event_present", "event_absent", "event_order", "event_count_max",
    "event_count_min", "outcome_field_equals", "outcome_list_contains",
    "outcome_list_excludes",
}
ASSERTION_TAGS = {
    "requirement_retention", "no_premature_stop", "no_redundant_approval",
    "public_acceptance", "identity_uniqueness", "hook_resolution",
    "route_compliance", "portability", "loop_budget", "provider_neutrality",
    "control_no_false_block",
}
MIN_CASES, MAX_CASES = 20, 50


def fail(message):
    print(f"ОШИБКА: {message}", file=sys.stderr)
    raise SystemExit(1)


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def content_hash(payload):
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_json(path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        fail(f"файл не найден: {path}")
    except json.JSONDecodeError as exc:
        fail(f"невалидный JSON {path}: {exc}")


def write_json(path, payload):
    text = json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    Path(path).write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# schema validation (structural, before anything is graded)
# ---------------------------------------------------------------------------
def validate_graders(graders):
    errors = []
    if graders.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"graders.schema_version != {SCHEMA_VERSION}")
    policy = graders.get("policy") or {}
    if policy.get("llm_judge_allowed") is not False:
        errors.append("policy.llm_judge_allowed must be false (D15: no opaque critical grader)")
    if policy.get("judge_override_of_deterministic") != "forbidden":
        errors.append("policy.judge_override_of_deterministic must be 'forbidden'")
    seen = set()
    for i, g in enumerate(graders.get("graders") or []):
        gid = g.get("id")
        if not gid or gid in seen:
            errors.append(f"graders[{i}]: missing or duplicate id {gid!r}")
        seen.add(gid)
        if g.get("operator") not in OPERATORS:
            errors.append(f"graders[{i}]: operator {g.get('operator')!r} not in {sorted(OPERATORS)}")
        if g.get("type") not in {"transcript", "outcome"}:
            errors.append(f"graders[{i}]: type must be transcript|outcome")
        if not g.get("description"):
            errors.append(f"graders[{i}]: empty description")
    if not seen:
        errors.append("graders: empty grader list")
    return errors, seen


def validate_cases(cases_doc, grader_ids):
    errors = []
    if cases_doc.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"cases.schema_version != {SCHEMA_VERSION}")
    cases = cases_doc.get("cases") or []
    if not MIN_CASES <= len(cases) <= MAX_CASES:
        errors.append(f"cases: {len(cases)} вне диапазона {MIN_CASES}–{MAX_CASES} (D10)")
    seen = set()
    for c in cases:
        cid = c.get("case_id", "?")
        where = f"case {cid}"
        if not cid or cid in seen:
            errors.append(f"{where}: missing or duplicate case_id")
        seen.add(cid)
        if c.get("kind") not in CASE_KINDS:
            errors.append(f"{where}: kind must be critical|control")
        for field in ("family", "requirement", "forbidden", "public_acceptance", "input"):
            if not c.get(field):
                errors.append(f"{where}: empty required field {field}")
        if not isinstance(c.get("owner_gate_required"), bool):
            errors.append(f"{where}: owner_gate_required must be boolean")
        asserts = c.get("assertions") or []
        if not asserts:
            errors.append(f"{where}: no assertions (an ungraded case cannot enter a bank)")
        aseen = set()
        for a in asserts:
            aid = a.get("id", "?")
            if not aid or aid in aseen:
                errors.append(f"{where}: missing or duplicate assertion id {aid!r}")
            aseen.add(aid)
            if a.get("grader") not in grader_ids:
                errors.append(f"{where}.{aid}: unknown grader {a.get('grader')!r}")
            if not isinstance(a.get("expect"), bool):
                errors.append(f"{where}.{aid}: expect must be boolean")
            for tag in a.get("tags") or []:
                if tag not in ASSERTION_TAGS:
                    errors.append(f"{where}.{aid}: unknown tag {tag!r}")
        base = c.get("baseline") or {}
        if base.get("provenance") not in PROVENANCE:
            errors.append(f"{where}: baseline.provenance must be one of {sorted(PROVENANCE)}")
        if not base.get("refs"):
            errors.append(f"{where}: baseline.refs is empty (a record without provenance is not evidence)")
        if not base.get("probes"):
            errors.append(f"{where}: baseline.probes is empty (provenance must be executable)")
        for p in base.get("probes") or []:
            if p.get("kind") not in PROBE_KINDS:
                errors.append(f"{where}: probe kind {p.get('kind')!r} not in {sorted(PROBE_KINDS)}")
        transcript = base.get("transcript") or []
        if not transcript:
            errors.append(f"{where}: baseline.transcript is empty")
        for ev in transcript:
            if ev.get("type") not in EVENT_TYPES:
                errors.append(f"{where}: event type {ev.get('type')!r} not in the closed set")
        seqs = [ev.get("seq") for ev in transcript]
        if seqs != sorted(seqs) or len(set(seqs)) != len(seqs):
            errors.append(f"{where}: baseline.transcript seq must be strictly increasing")
        outcome = base.get("outcome") or {}
        if outcome.get("declared_status") not in {"success", "blocked", "escalated", "failed"}:
            errors.append(f"{where}: outcome.declared_status invalid")
    if not errors:
        critical = sum(1 for c in cases if c["kind"] == "critical")
        control = len(cases) - critical
        if critical < 1 or control < 1:
            errors.append("bank must contain both critical and control cases")
    return errors


# ---------------------------------------------------------------------------
# probes — provenance is executable, not asserted
# ---------------------------------------------------------------------------
def _iter_files(globs, exclude_globs):
    seen = []
    for pattern in globs:
        for path in sorted(REPO_ROOT.glob(pattern)):
            if not path.is_file():
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if any(fnmatch.fnmatch(rel, ex) for ex in exclude_globs or []):
                continue
            if rel not in seen:
                seen.append(rel)
    return seen


def run_probe(probe):
    kind = probe["kind"]
    if kind == "present_path":
        path = REPO_ROOT / probe["path"]
        ok = path.exists()
        return ok, f"present_path {probe['path']}: {'есть' if ok else 'НЕТ'}"
    rx = re.compile(probe["pattern"])
    files = _iter_files(probe.get("globs") or [], probe.get("exclude_globs"))
    hits = []
    for rel in files:
        try:
            text = (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if rx.search(text):
            hits.append(rel)
    if kind == "absent_pattern":
        ok = not hits
        return ok, (f"absent_pattern /{probe['pattern']}/ по {len(files)} файлам: "
                    f"{'совпадений нет' if ok else 'НАЙДЕНО в ' + ', '.join(hits[:3])}")
    ok = bool(hits)
    return ok, (f"present_pattern /{probe['pattern']}/ по {len(files)} файлам: "
                f"{'найдено в ' + hits[0] if ok else 'НЕ найдено'}")


def run_probes(cases):
    report, failures = {}, []
    for case in cases:
        rows = []
        for probe in case["baseline"]["probes"]:
            ok, detail = run_probe(probe)
            rows.append({"kind": probe["kind"], "ok": ok, "detail": detail})
            if not ok:
                failures.append(f"{case['case_id']}: {detail}")
        report[case["case_id"]] = rows
    return report, failures


# ---------------------------------------------------------------------------
# grading engine — deterministic operators only
# ---------------------------------------------------------------------------
def _matches(event, where):
    for key, value in (where or {}).items():
        if event.get(key) != value:
            return False
    return True


def _select(transcript, spec):
    return [e for e in transcript
            if e.get("type") == spec.get("type") and _matches(e, spec.get("where"))]


def _dig(outcome, path):
    node = outcome
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def apply_operator(operator, args, transcript, outcome):
    if operator == "event_present":
        hits = _select(transcript, args)
        return bool(hits), f"event_present {args.get('type')}: {len(hits)}"
    if operator == "event_absent":
        hits = _select(transcript, args)
        return not hits, f"event_absent {args.get('type')}: {len(hits)}"
    if operator == "event_order":
        before, after = args["before"], args["after"]
        afters = _select(transcript, after)
        if not afters:
            return True, f"event_order: нет событий {after.get('type')} — порядок не нарушен"
        befores = _select(transcript, before)
        ok = all(any(b["seq"] < a["seq"] for b in befores) for a in afters)
        return ok, (f"event_order {before.get('type')}→{after.get('type')}: "
                    f"{'соблюдён' if ok else 'НАРУШЕН'} ({len(befores)}/{len(afters)})")
    if operator == "event_count_max":
        hits = _select(transcript, args)
        ok = len(hits) <= args["max"]
        return ok, f"event_count_max {args.get('type')} ≤ {args['max']}: {len(hits)}"
    if operator == "event_count_min":
        hits = _select(transcript, args)
        ok = len(hits) >= args["min"]
        return ok, f"event_count_min {args.get('type')} ≥ {args['min']}: {len(hits)}"
    if operator == "outcome_field_equals":
        got = _dig(outcome, args["path"])
        ok = got == args["value"]
        return ok, f"outcome.{args['path']} == {args['value']!r}: получено {got!r}"
    if operator in ("outcome_list_contains", "outcome_list_excludes"):
        got = _dig(outcome, args["path"])
        items = got if isinstance(got, list) else []
        present = args["value"] in items
        ok = present if operator == "outcome_list_contains" else not present
        return ok, f"{operator} outcome.{args['path']} {args['value']!r}: {'ок' if ok else 'нарушено'}"
    return False, f"неизвестный оператор: {operator!r}"


def grade_case(case, graders_by_id, transcript, outcome):
    checks = []
    for a in case["assertions"]:
        grader = graders_by_id[a["grader"]]
        ok, detail = apply_operator(grader["operator"], a.get("args") or {}, transcript, outcome)
        satisfied = (ok == a["expect"])
        checks.append({"id": a["id"], "grader": a["grader"], "expect": a["expect"],
                       "observed": ok, "ok": satisfied, "detail": detail,
                       "tags": a.get("tags") or []})
    return {"case_id": case["case_id"], "kind": case["kind"], "family": case["family"],
            "passed": all(c["ok"] for c in checks), "checks": checks}


# ---------------------------------------------------------------------------
# metrics — every value below is recomputed from graded records
# ---------------------------------------------------------------------------
def _p95(values):
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, math.ceil(0.95 * len(ordered)) - 1)
    return ordered[idx]


def compute_metrics(cases, graded, layer, records):
    """`records` maps case_id → {transcript, outcome} of the run being measured.

    It is passed explicitly so a candidate run is never scored against the frozen
    layer-1 records: every event-derived metric below reads the run under test.
    """
    grade_by_id = {g["case_id"]: g for g in graded}
    critical = [c for c in cases if c["kind"] == "critical"]
    control = [c for c in cases if c["kind"] == "control"]

    def transcript(case_id):
        return records[case_id]["transcript"]

    def outcome(case_id):
        return records[case_id]["outcome"]

    retained = 0
    for c in critical:
        tagged = [ch for ch in grade_by_id[c["case_id"]]["checks"]
                  if "requirement_retention" in ch["tags"]]
        if tagged and all(ch["ok"] for ch in tagged):
            retained += 1
    premature = [c["case_id"] for c in critical
                 if _select(transcript(c["case_id"]), {"type": "premature_stop"})]
    redundant = [c["case_id"] for c in critical
                 if _select(transcript(c["case_id"]), {"type": "redundant_approval"})]
    unneeded_owner = [c["case_id"] for c in cases
                      if not c["owner_gate_required"]
                      and _select(transcript(c["case_id"]), {"type": "owner_question"})]
    depths = []
    for c in cases:
        counts = {}
        for ev in _select(transcript(c["case_id"]), {"type": "finding"}):
            fid = ev.get("finding_id")
            counts[fid] = counts.get(fid, 0) + 1
        if counts:
            depths.append(max(counts.values()))
    overrun = []
    for c in cases:
        budget = (c.get("environment") or {}).get("audit_rounds_max", 2)
        if len(_select(transcript(c["case_id"]), {"type": "audit_round"})) > budget:
            overrun.append(c["case_id"])
    routed = [c for c in cases if _select(transcript(c["case_id"]), {"type": "route_declared"})]
    compliant = [c for c in routed
                 if not _select(transcript(c["case_id"]),
                                {"type": "route_declared", "where": {"undershoot": True}})]
    escapes = []
    for c in critical:
        tagged = [ch for ch in grade_by_id[c["case_id"]]["checks"]
                  if "requirement_retention" in ch["tags"]]
        if any(not ch["ok"] for ch in tagged) and outcome(c["case_id"]).get("declared_status") == "success":
            escapes.append(c["case_id"])
    false_blocks = [c["case_id"] for c in control
                    if _select(transcript(c["case_id"]), {"type": "block"})]

    def ratio(num, den):
        return round(num / den, 4) if den else None

    return {
        "layer": layer,
        "counts": {"cases": len(cases), "critical": len(critical), "control": len(control)},
        "critical_requirement_retention": ratio(retained, len(critical)),
        "premature_stop_count": len(premature),
        "premature_stop_cases": premature,
        "redundant_approval_count": len(redundant),
        "redundant_approval_cases": redundant,
        "first_pass_success": ratio(sum(1 for g in graded if g["passed"]), len(graded)),
        "first_pass_success_critical": ratio(
            sum(1 for g in graded if g["passed"] and g["kind"] == "critical"), len(critical)),
        "owner_intervention_rate": ratio(len(unneeded_owner), len(cases)),
        "owner_intervention_cases": unneeded_owner,
        "same_finding_loop_depth": {
            "samples": len(depths),
            "median": statistics.median(depths) if depths else 0,
            "p95": _p95(depths) if depths else 0,
            "note": "samples=0 означает «находок не было»: глубина повтора 0, а не неизвестна",
        },
        "audit_loop_overrun_count": len(overrun),
        "audit_loop_overrun_cases": overrun,
        "routing_compliance": ratio(len(compliant), len(routed)),
        "critical_regression_escape": len(escapes),
        "critical_regression_escape_cases": escapes,
        "false_block_rate": ratio(len(false_blocks), len(control)),
        "deferred": {
            "trace_completeness":
                "instrument is produced by P3.1/P3.2 (unified trace); not measurable on a "
                "layer-1 declared baseline — reported deferred, never green",
            "context_input_per_success":
                "requires the layer-2 live paired run (P3.3); the committed dedup token "
                "totals are pinned-not-recomputable and are context only (D30/D59)",
        },
    }


# ---------------------------------------------------------------------------
# floors
# ---------------------------------------------------------------------------
def check_floor_hygiene(floors, pinned_ids):
    """A frozen floor may never rest on a pinned-not-recomputable quantity (D30/D59)."""
    errors = []
    for f in floors:
        for ref in f.get("pinned_inputs") or []:
            errors.append(f"floor {f['id']}: pinned input {ref!r} — запрещено D30/D59")
        src = f.get("baseline_source")
        if src not in {"bank-layer-1", "bank-layer-2-live-paired", "item-measurement", "none"}:
            errors.append(f"floor {f['id']}: baseline_source {src!r} вне закрытого списка")
        for ref in f.get("evidence_refs") or []:
            if ref in pinned_ids:
                errors.append(f"floor {f['id']}: evidence_ref {ref!r} имеет proof class "
                              f"pinned-not-recomputable — запрещено D30/D59")
    return errors


def evaluate_floors(floors, metrics):
    rows = []
    for f in floors:
        if f["measurement_owner"] != "bank" or f.get("baseline_source") != "bank-layer-1":
            rows.append({"id": f["id"], "status": "deferred",
                         "owner": f["measurement_owner"], "detail": f["metric"]})
            continue
        value = metrics.get(f["metric"])
        if isinstance(value, dict):
            value = value.get(f.get("metric_key"))
        if value is None:
            rows.append({"id": f["id"], "status": "unknown", "owner": "bank",
                         "detail": f"метрика {f['metric']} не вычислена"})
            continue
        op, target = f["comparator"], f["value"]
        ok = {"==": value == target, "<=": value <= target, ">=": value >= target}[op]
        rows.append({"id": f["id"], "status": "met" if ok else "not-met", "owner": "bank",
                     "observed": value, "comparator": op, "target": target})
    return rows


# ---------------------------------------------------------------------------
# deterministic seeded sample
# ---------------------------------------------------------------------------
def seeded_sample(seed, case_ids, size):
    ranked = sorted(case_ids, key=lambda cid: hashlib.sha256(
        f"{seed}|{cid}".encode("utf-8")).hexdigest())
    return ranked[:size]


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------
def load_bank(args):
    graders_doc = load_json(args.graders)
    cases_doc = load_json(args.cases)
    gerrors, grader_ids = validate_graders(graders_doc)
    cerrors = validate_cases(cases_doc, grader_ids)
    if gerrors or cerrors:
        for e in gerrors + cerrors:
            print(f"  СХЕМА: {e}", file=sys.stderr)
        fail(f"банк невалиден: {len(gerrors) + len(cerrors)} нарушений схемы")
    return graders_doc, cases_doc


def cmd_baseline(args):
    graders_doc, cases_doc = load_bank(args)
    graders_by_id = {g["id"]: g for g in graders_doc["graders"]}
    cases = cases_doc["cases"]

    probe_report, probe_failures = run_probes(cases)
    if probe_failures:
        for f in probe_failures:
            print(f"  ПРОБА: {f}", file=sys.stderr)
        fail("declared baseline provenance больше не держится — банк требует новой версии "
             "(D15: коррекция версионирует банк и переигрывает обе стороны)")

    graded = [grade_case(c, graders_by_id, c["baseline"]["transcript"], c["baseline"]["outcome"])
              for c in cases]
    metrics = compute_metrics(cases, graded, layer="layer-1-declared",
                              records={c["case_id"]: c["baseline"] for c in cases})

    source_baseline = load_json(args.source_baseline)
    pinned = {
        "journals.classified_lifecycle_events": source_baseline["journals"]["classified_lifecycle_events"],
        "journals.outcomes": source_baseline["journals"]["outcomes"],
        "dedup_correction.corrected": source_baseline["dedup_correction"]["corrected"],
    }

    results = {
        "schema_version": SCHEMA_VERSION,
        "layer": "layer-1-declared",
        "owner": "plans/2026.07.24-AGENT-RELIABILITY P0.3",
        "note": ("Layer-1 grades the declared pre-change behaviour of every case; its "
                 "provenance is machine-verified by the probes below. Relative floors "
                 "resolve only against the layer-2 live paired run (P3.3)."),
        "probes": probe_report,
        "cases": graded,
        "metrics": metrics,
        "pinned_context_only": {
            "reason": "retained as labelled context; may never supply a floor, expected "
                      "value or GREEN predicate (D30/D59)",
            "values": pinned,
        },
    }
    write_json(args.results, results)

    floors = load_json(args.floors) if args.floors else cases_doc["floors"]
    verification = load_json(args.verification_report) if args.verification_report else None
    pinned_ids = set()
    if verification:
        pinned_ids = set(verification["summary"]["by_proof_class"].get("pinned-not-recomputable", []))
    hygiene = check_floor_hygiene(floors, pinned_ids)
    if hygiene:
        for e in hygiene:
            print(f"  FLOOR: {e}", file=sys.stderr)
        fail("floors нарушают правило proof class (D30/D59)")
    floor_rows = evaluate_floors(floors, metrics)

    sample = seeded_sample(cases_doc["sample_seed"],
                           [g["case_id"] for g in graded if g["passed"]], 5)
    manifest_payload = {
        "schema_version": SCHEMA_VERSION,
        "bank_version": cases_doc["bank_version"],
        "grader_version": graders_doc["grader_version"],
        "frozen_at": cases_doc["frozen_at"],
        "owner_item": "plans/2026.07.24-AGENT-RELIABILITY P0.3",
        "decisions": ["D10", "D15", "D16", "D26", "D30", "D50", "D53", "D59"],
        "frozen_reference_tree": Path(REPO_ROOT, args.pre_plan_sha).read_text(
            encoding="utf-8").strip() if args.pre_plan_sha else None,
        "files": {
            "cases.json": file_hash(args.cases),
            "graders.json": file_hash(args.graders),
            "baseline-results.json": file_hash(args.results),
            "run_bank.py": file_hash(__file__),
        },
        "source_inputs": {
            "artifacts/source-evidence/precomputed/corpus.json": file_hash(args.corpus),
            "artifacts/source-evidence/precomputed/baseline.json": file_hash(args.source_baseline),
            "artifacts/P0.1/verification-report.json":
                file_hash(args.verification_report) if args.verification_report else None,
        },
        "counts": {
            "cases": len(cases),
            "critical": sum(1 for c in cases if c["kind"] == "critical"),
            "control": sum(1 for c in cases if c["kind"] == "control"),
            "assertions": sum(len(c["assertions"]) for c in cases),
            "probes": sum(len(c["baseline"]["probes"]) for c in cases),
            "families": len({c["family"] for c in cases}),
        },
        "baseline_layers": {
            "layer-1-declared": {
                "status": "frozen by P0.3",
                "results": "baseline-results.json",
                "provenance_classes": sorted(PROVENANCE),
            },
            "layer-2-live-paired": {
                "status": "required before any relative floor is claimed",
                "producer": "P3.3 paired run on artifacts/P0.1/pre-plan-sha.txt (D45)",
            },
        },
        "layer1_metrics": metrics,
        "floors": floors,
        "diagnostics": cases_doc.get("diagnostics", []),
        "floor_status_layer1": floor_rows,
        "imported_proof_classes": (verification["summary"]["by_proof_class"]
                                   if verification else None),
        "pinned_context_only": sorted(pinned.keys()),
        "sample": {"seed": cases_doc["sample_seed"], "size": len(sample),
                   "method": "sha256(seed|case_id) ascending over baseline-passing cases",
                   "selected": sample},
        "correction_rule": ("любая правка кейса/грейдера версионирует банк (bank_version, "
                            "grader_version) и требует переигровки ОБЕИХ сторон; "
                            "candidate-only правка порога запрещена (D15)"),
    }
    manifest_payload["content_hash"] = content_hash(manifest_payload)
    write_json(args.manifest, manifest_payload)

    deferred = sum(1 for r in floor_rows if r["status"] == "deferred")
    not_met = [r["id"] for r in floor_rows if r["status"] == "not-met"]
    print(f"bank baseline: {len(cases)} cases "
          f"({manifest_payload['counts']['critical']} critical / "
          f"{manifest_payload['counts']['control']} control), "
          f"{manifest_payload['counts']['assertions']} assertions, "
          f"{manifest_payload['counts']['probes']} probes green")
    print(f"layer-1 first-pass success: {metrics['first_pass_success']} "
          f"(critical {metrics['first_pass_success_critical']}, "
          f"retention {metrics['critical_requirement_retention']})")
    print(f"floors: {len(floors)} frozen — {deferred} deferred to later measurement owners, "
          f"layer-1 not-met: {', '.join(not_met) if not_met else '—'} "
          f"(ожидаемо: layer-1 = поведение ДО ремонта)")
    print(f"manifest: {args.manifest} content_hash={manifest_payload['content_hash'][:16]}…")
    return 0


def cmd_verify(args):
    graders_doc, cases_doc = load_bank(args)
    manifest = load_json(args.manifest)
    problems = []
    for name, path in (("cases.json", args.cases), ("graders.json", args.graders),
                       ("run_bank.py", __file__), ("baseline-results.json", args.results)):
        expected = manifest["files"].get(name)
        got = file_hash(path)
        if expected != got:
            problems.append(f"{name}: hash {got[:16]}… != manifest {str(expected)[:16]}…")
    payload = {k: v for k, v in manifest.items() if k != "content_hash"}
    if content_hash(payload) != manifest["content_hash"]:
        problems.append("manifest content_hash не сходится с телом манифеста")

    graders_by_id = {g["id"]: g for g in graders_doc["graders"]}
    graded = [grade_case(c, graders_by_id, c["baseline"]["transcript"], c["baseline"]["outcome"])
              for c in cases_doc["cases"]]
    stored = load_json(args.results)
    if canonical(stored["cases"]) != canonical(graded):
        problems.append("перегрейд не воспроизводит baseline-results.json побайтно")

    _, probe_failures = run_probes(cases_doc["cases"])
    if probe_failures:
        note = ("дрейф проб ОЖИДАЕМ после P2 (появление seam'а) и означает: layer-1 "
                "исторический, перегенерация baseline запрещена без версии банка")
        print(f"probes: {len(probe_failures)} дрейфующих — {note}")
        for f in probe_failures:
            print(f"  ПРОБА: {f}")
        if args.strict_probes:
            problems.append(f"strict-probes: {len(probe_failures)} проб не держатся")
    else:
        print("probes: все держатся на текущем дереве")

    if problems:
        for p in problems:
            print(f"  ОШИБКА: {p}", file=sys.stderr)
        fail(f"verify: {len(problems)} расхождений")
    print(f"verify ok: hashes, content_hash, перегрейд {len(graded)} кейсов воспроизводим")
    return 0


def cmd_candidate(args):
    if Path(args.results).resolve() == (BANK_DIR / "baseline-results.json").resolve():
        fail("candidate: --results указывает на замороженный baseline-results.json — "
             "укажи отдельный путь; кандидатский прогон не перезаписывает layer-1")
    graders_doc, cases_doc = load_bank(args)
    graders_by_id = {g["id"]: g for g in graders_doc["graders"]}
    runs = load_json(args.transcripts)
    by_case = {r["case_id"]: r for r in runs.get("runs", [])}
    missing = [c["case_id"] for c in cases_doc["cases"] if c["case_id"] not in by_case]
    if missing:
        fail(f"candidate: нет прогонов для {len(missing)} кейсов ({', '.join(missing[:5])}…) — "
             "частичный прогон банка не считается результатом")
    graded = [grade_case(c, graders_by_id, by_case[c["case_id"]]["transcript"],
                         by_case[c["case_id"]]["outcome"]) for c in cases_doc["cases"]]
    metrics = compute_metrics(cases_doc["cases"], graded, layer=runs.get("layer", "candidate"),
                              records=by_case)
    manifest = load_json(args.manifest)
    rows = evaluate_floors(manifest["floors"], metrics)
    write_json(args.results, {"schema_version": SCHEMA_VERSION, "layer": metrics["layer"],
                              "cases": graded, "metrics": metrics, "floor_status": rows})
    not_met = [r["id"] for r in rows if r["status"] == "not-met"]
    deferred = [r["id"] for r in rows if r["status"] in ("deferred", "unknown")]
    print(f"candidate: {len(graded)} кейсов, first-pass {metrics['first_pass_success']}, "
          f"floors not-met: {', '.join(not_met) if not_met else '—'}, "
          f"deferred/unknown: {', '.join(deferred) if deferred else '—'}")
    return 1 if not_met else 0


def cmd_sample(args):
    cases_doc = load_json(args.cases)
    results = load_json(args.results)
    passing = [g["case_id"] for g in results["cases"] if g["passed"]]
    for cid in seeded_sample(cases_doc["sample_seed"], passing, args.size):
        print(cid)
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description="Reliability Bank v1 — детерминированный раннер")
    sub = parser.add_subparsers(dest="command", required=True)

    def common(p):
        p.add_argument("--cases", default=str(BANK_DIR / "cases.json"))
        p.add_argument("--graders", default=str(BANK_DIR / "graders.json"))
        p.add_argument("--results", default=str(BANK_DIR / "baseline-results.json"))
        p.add_argument("--manifest", default=str(BANK_DIR / "bank-manifest.json"))

    p_base = sub.add_parser("baseline")
    common(p_base)
    p_base.add_argument("--source-baseline", required=True)
    p_base.add_argument("--corpus", required=True)
    p_base.add_argument("--verification-report",
                        default=str(BANK_DIR.parent / "P0.1" / "verification-report.json"))
    p_base.add_argument("--pre-plan-sha",
                        default="plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.1/pre-plan-sha.txt")
    p_base.add_argument("--floors", default=None)
    p_base.set_defaults(func=cmd_baseline)

    p_ver = sub.add_parser("verify")
    common(p_ver)
    p_ver.add_argument("--strict-probes", action="store_true")
    p_ver.set_defaults(func=cmd_verify)

    p_cand = sub.add_parser("candidate")
    common(p_cand)
    p_cand.add_argument("--transcripts", required=True)
    p_cand.set_defaults(func=cmd_candidate)

    p_sample = sub.add_parser("sample")
    common(p_sample)
    p_sample.add_argument("--size", type=int, default=5)
    p_sample.set_defaults(func=cmd_sample)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
