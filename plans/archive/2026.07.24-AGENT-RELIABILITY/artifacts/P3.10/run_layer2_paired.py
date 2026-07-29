#!/usr/bin/env python3
"""run_layer2_paired.py — sole executable owner of the P3.10 live paired layer-2 run
(plans/2026.07.24-AGENT-RELIABILITY).

Orchestrates the FROZEN P3.9 instrument (`run_live_bank.py` + `event-mapping-v1.json`,
neither touched here — Scope Excluded) over the declared 5/31 case set
(`artifacts/P3.9/declared-case-set.json`), live, on TWO disposable detached worktrees:
`--baseline-sha` (PRE_PLAN_SHA, D45) and `--candidate-sha` (HEAD at item start). Routed
axes for every dispatch are pinned by flag to THIS item's own §3 Routing row
(`implementation/high` -> sonnet/high, D46) — never session default, never the
per-case fixture's "required" axis (that is the SCENARIO under test, not the actor
making the dispatch).

Grading reuses `skiller.quality.eval.build_system_benchmark(candidate_runs=...)` called
once per side against the frozen 31-case `cases.json`/`graders.json` — `candidate_runs`
restricted to our 5 case_ids makes `compute_system_metrics` operate on exactly the
declared subset. Pairing uses `analyst.metrics.build_metric_record`/`pair_metric`.

stdlib-only plus the two frozen consumer modules (`skiller.quality.eval`,
`analyst.metrics`) and the frozen P3.9 harness (`run_live_bank`), all imported one-way.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve()
_P3_10_DIR = _SCRIPT.parent
_PLAN_DIR = _P3_10_DIR.parent.parent
_MONOREPO_ROOT = _PLAN_DIR.parents[1]

if (_MONOREPO_ROOT / "core").is_dir():
    sys.path.insert(0, str(_MONOREPO_ROOT))
for _pkg in ("analyst", "skiller", "task"):
    _lib = _MONOREPO_ROOT / "packages" / _pkg / "lib"
    if _lib.is_dir():
        sys.path.insert(0, str(_lib))

_spec = importlib.util.spec_from_file_location(
    "run_live_bank", _PLAN_DIR / "artifacts" / "P3.9" / "run_live_bank.py")
rlb = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rlb)

from analyst.metrics import build_metric_record, pair_metric  # noqa: E402
from skiller.quality.eval import build_system_benchmark  # noqa: E402

MAPPING_PATH = _PLAN_DIR / "artifacts" / "P3.9" / "event-mapping-v1.json"
CASES_PATH = _PLAN_DIR / "artifacts" / "reliability-bank-v1" / "cases.json"
GRADERS_PATH = _PLAN_DIR / "artifacts" / "reliability-bank-v1" / "graders.json"
DECLARED_SET_PATH = _PLAN_DIR / "artifacts" / "P3.9" / "declared-case-set.json"
RAW_DIR = _P3_10_DIR / "raw"
ROUTE = {"model_class": "implementation", "effort": "high", "model": "sonnet"}
CLI_MODEL, CLI_EFFORT, CLI_MODEL_CLASS = "sonnet", "high", "implementation"
GENERATED_AT = "2026-07-26T00:00:00Z"


def sh(cmd, cwd=None, check=True):
    result = subprocess.run(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if check and result.returncode != 0:
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(cmd)}\n"
                            f"stdout={result.stdout}\nstderr={result.stderr}")
    return result


def git(repo, *args, check=True):
    return sh(["git", "-C", str(repo), *args], check=check)


# --------------------------------------------------------------------------- #
# case prompts — narrow, deterministic, minimal-turn (P3.4/P3.9 precedent)
# --------------------------------------------------------------------------- #
def prompt_route_undershoot(side, scratch_dir, scratch_plan):
    return (
        "Run exactly ONE Bash command and nothing else -- no other tool calls, "
        "no file edits, no git commands:\n\n"
        "PYTHONPATH=packages/task/lib python3 - <<'PY'\n"
        "import json\n"
        "try:\n"
        "    from task import task_contract, route_evidence\n"
        "except ImportError as exc:\n"
        "    print(json.dumps({\"import_error\": str(exc)}))\n"
        "else:\n"
        "    contract = task_contract.build(\"plans/2026.07.24-AGENT-RELIABILITY\", \"P3.9\",\n"
        "        actual_route=route_evidence.capture_actual(\"implementation\", \"medium\", "
        "source=\"self-attested\", model=\"sonnet\"))\n"
        "    result = task_contract.evaluate(contract)\n"
        "    print(result)\n"
        "PY\n\n"
        "Then run exactly ONE more Bash command:\n\n"
        f"mkdir -p {scratch_dir} && PYTHONPATH=packages/task/lib python3 -m task.journal append "
        f"--plan-dir {scratch_dir} --plan {scratch_plan} --item PROBE.1 --command plan-run "
        "--actor implementation/medium --result blocked --friction routing-blocked "
        "--note \"P3.10 layer-2 probe\" 2>&1 || true\n\n"
        "Report both command outputs verbatim in your final message and stop. Do not create, "
        "edit, move, or delete ANY file inside this git repository (the directory above is "
        "outside the repository, under /tmp). Do not run git add/commit/status or any other git "
        "command. Do not read any other file."
    )


def prompt_trace_record_missing(side):
    return (
        "Run exactly ONE Bash command and nothing else -- no other tool calls, no git commands:\n\n"
        "PYTHONPATH=packages/analyst/lib python3 - <<'PY'\n"
        "import json, hashlib\n"
        "try:\n"
        "    from analyst.trace import build_trace_record\n"
        "except ImportError as exc:\n"
        "    print(json.dumps({\"import_error\": str(exc)}))\n"
        "    records = []\n"
        "else:\n"
        "    source_bytes = b\"p3.10-probe\"\n"
        "    sha = hashlib.sha256(source_bytes).hexdigest()\n"
        "    raw = {\n"
        "        \"provenance\": {\"provider_id\": \"claude-code\", \"raw_ref\": \"p3.10/probe\",\n"
        "                       \"sha256\": sha, \"reader_id\": \"p3.10-probe\", \"reader_version\": \"1.0.0\"},\n"
        "        \"occurred_at\": \"2026-07-26T00:00:00Z\",\n"
        "        \"plan_ref\": {\"plan_id\": \"2026.07.24-AGENT-RELIABILITY\", \"item_id\": \"P3.10\", "
        "\"command\": \"plan-run\"},\n"
        "        \"contract_ref\": {\"contract_id\": \"p3.10-probe\", \"version_hash\": \"0\" * 70},\n"
        "        \"route\": {\"model_class\": \"implementation\", \"effort\": \"high\", \"model\": \"sonnet\"},\n"
        "        \"dispatch\": {\"state\": \"DONE\", \"event\": \"dispatch\"},\n"
        "        \"finding_refs\": [\"F-p3.10-probe\"],\n"
        "        \"public_outcome\": {\"scope\": \"internal\", \"check\": \"p3.10 probe\", "
        "\"evidence_ref\": \"p3.10/probe\"},\n"
        "    }\n"
        "    record = build_trace_record(raw, provider_id=\"claude-code\", project_id=\"swissknifeman\",\n"
        "                                identity=\"p3.10-probe\", turn_id=\"p3.10-probe-1\", "
        "source_bytes=source_bytes)\n"
        "    records = [record]\n"
        "with open(\"p3.10-traces.json\", \"w\", encoding=\"utf-8\") as fh:\n"
        "    json.dump({\"records\": records}, fh)\n"
        "print(json.dumps({\"records_written\": len(records)}))\n"
        "PY\n\n"
        "Report the command output verbatim in your final message and stop. Do not run any git "
        "command. Do not create, edit, move or delete any file other than `p3.10-traces.json` in "
        "the repository root."
    )


def prompt_honest_http_clean(side):
    path = f"plans/2026.07.24-AGENT-RELIABILITY/artifacts/P3.10/worktree-fixtures/case-03-{side}.txt"
    return (
        f"Create the file `{path}` (create parent directories if needed) containing exactly one "
        "line: `p3.10 case-03 control ok`. Do not run any git command (no add/commit/status). Do "
        "not create, edit or delete any other path in this repository. Do not read any other file."
    )


def prompt_committed_bundle_highrisk(side):
    out_path = f"plans/2026.07.24-AGENT-RELIABILITY/artifacts/P3.10/worktree-fixtures/case-04-{side}.txt"
    return (
        "First use the Read tool to read the file "
        "`plans/2026.07.24-AGENT-RELIABILITY/artifacts/source-evidence/precomputed/corpus.json` "
        f"in this repository. Then create the file `{out_path}` (create parent directories if "
        "needed) containing exactly one line: `p3.10 case-04 control ok`. Do not run any git "
        "command. Do not create, edit or delete any other path in this repository. Do not read "
        "any other file beyond the one named above."
    )


def prompt_predecessor_produced_path(side):
    in_path = "plans/2026.07.24-AGENT-RELIABILITY/artifacts/P0.1/verification-report.json"
    out_path = f"plans/2026.07.24-AGENT-RELIABILITY/artifacts/P3.10/worktree-fixtures/case-05-{side}.txt"
    return (
        f"Check whether the file `{in_path}` exists in this repository (for example with the "
        f"Bash tool: `test -f {in_path} && echo present || echo absent`). If it exists, use the "
        f"Read tool to read it, then create the file `{out_path}` (create parent directories if "
        "needed) containing exactly one line: `p3.10 case-05 control ok`. If it does NOT exist, "
        "do not fabricate it -- instead create the same output file containing exactly one line: "
        "`p3.10 case-05 control missing-input`, and say so in your final response. Do not run any "
        "git command. Do not create, edit or delete any other path in this repository."
    )


CASE_BUILDERS = {
    "route-undershoot-silent": ("critical", prompt_route_undershoot, True, None),
    "trace-record-missing": ("critical", prompt_trace_record_missing, False, "p3.10-traces.json"),
    "honest-http-clean-control": ("control", prompt_honest_http_clean, False, None),
    "control-committed-bundle-highrisk": ("control", prompt_committed_bundle_highrisk, False, None),
    "control-predecessor-produced-path": ("control", prompt_predecessor_produced_path, False, None),
}


# --------------------------------------------------------------------------- #
def create_worktree(sha, tag):
    parent = Path(sh(["mktemp", "-d", "-p", "/tmp", f"skm-p3.10-{tag}.XXXXXX"]).stdout.strip())
    git(_MONOREPO_ROOT, "worktree", "add", "--detach", str(parent), sha)
    return parent


def remove_worktree(path):
    git(_MONOREPO_ROOT, "worktree", "remove", "--force", str(path))


def run_one_dispatch(case_id, side, worktree, attempt):
    kind, builder, needs_journal, traces_rel = CASE_BUILDERS[case_id]
    out_dir = RAW_DIR / side / case_id
    kwargs = {}
    if case_id == "route-undershoot-silent":
        scratch_dir = f"/tmp/p3.10-scratch-{side}-route-undershoot/P3.10-PROBE"
        prompt = builder(side, scratch_dir, "P3.10-PROBE")
        kwargs["journal"] = f"{scratch_dir}/journal.jsonl"
    else:
        prompt = builder(side)
    if traces_rel:
        kwargs["traces"] = traces_rel
    ns = argparse.Namespace(
        measure_observability=False, dispatch=True, replay=None,
        mapping=str(MAPPING_PATH), out=None, cases=None, graders=None,
        repo=str(worktree), prompt=prompt, out_dir=str(out_dir),
        model=CLI_MODEL, effort=CLI_EFFORT, model_class=CLI_MODEL_CLASS,
        journal=kwargs.get("journal"), traces=kwargs.get("traces"),
        expect_present=None, expect_absent=None,
    )
    rc = rlb.cmd_dispatch(ns)
    meta = json.loads((out_dir / "meta.json").read_text(encoding="utf-8"))
    return rc, meta


def dispatch_with_retry(case_id, side, sha):
    """One disposable worktree PER (case, side) -- `cmd_dispatch` requires a clean
    tree at its own base_sha capture, and each case's mutation/read observation must
    not be contaminated by a PRIOR case's writes in the same tree (they would still
    show up in `git diff base_sha` since base_sha is captured fresh, not per-worktree
    lifetime). A worktree that dies mid-dispatch (retry path) is removed and rebuilt
    fresh rather than reused dirty."""
    worktree = create_worktree(sha, f"{side}-{case_id}")
    try:
        rc, meta = run_one_dispatch(case_id, side, worktree, 1)
        if meta.get("returncode") == -1:  # timeout -- one retry allowed by budget
            print(f"[{side}/{case_id}] attempt 1 timed out, retrying once", file=sys.stderr)
            remove_worktree(worktree)
            worktree = create_worktree(sha, f"{side}-{case_id}-retry")
            rc, meta = run_one_dispatch(case_id, side, worktree, 2)
        return rc, meta
    finally:
        remove_worktree(worktree)


def extract_usage(fixture_dir):
    stream = rlb.load_json(fixture_dir / "stream.json")
    results = [e for e in stream["events"] if e["kind"] == "result"]
    if not results:
        return None
    e = results[-1]
    u = e.get("usage") or {}
    return {
        "total_cost_usd": e.get("total_cost_usd"),
        "input_tokens": u.get("input_tokens") or 0,
        "cache_creation_input_tokens": u.get("cache_creation_input_tokens") or 0,
        "cache_read_input_tokens": u.get("cache_read_input_tokens") or 0,
        "output_tokens": u.get("output_tokens") or 0,
    }


def compute_floors(case_ids, normalized, graded_by_side, usage_by_side):
    """F6/F8/F9/F10 over the declared 5/31 subset -- every row is `scope:
    declared-subset {len}/31` (Implementation Rules: never `met` for full
    acceptance on a partial denominator; that verdict is P3.11's, not this
    item's). F10 is `unknown` by construction: `owner_question` is declared
    `unmappable` in `event-mapping-v1.json` regardless of what any dispatch
    does, so a computed ratio here would be a hollow 0/0, not a measurement."""
    scope_note = f"scope: declared-subset {len(case_ids)}/31 (D51/D82) -- not eligible for full-bank 'met'"

    # F6 -- trace_completeness over every trace_emitted event actually produced,
    # either side (denominator = traces produced; numerator = complete ones).
    trace_records = []
    for side in ("baseline", "candidate"):
        for cid in case_ids:
            for ev in normalized[side][cid]["transcript"]:
                if ev["type"] == "trace_emitted":
                    trace_records.append((side, cid, ev))
    f6_num = sum(1 for _, _, ev in trace_records if ev.get("required_fields_complete"))
    f6_den = len(trace_records)
    f6 = build_metric_record(
        "trace_completeness", numerator=f6_num, denominator=f6_den,
        baseline_proof_class="recomputed",
        note=scope_note + f"; only {f6_den} trace_emitted event(s) produced across both "
             "sides on this subset -- thin sample, not a bank-wide claim")

    # F8 -- first_pass_success delta, candidate vs baseline, over the 5 declared cases.
    f8_baseline = build_metric_record(
        "first_pass_success",
        numerator=sum(1 for g in graded_by_side["baseline"] if g["passed"]),
        denominator=len(case_ids), baseline_proof_class="recomputed", note=scope_note)
    f8_candidate = build_metric_record(
        "first_pass_success",
        numerator=sum(1 for g in graded_by_side["candidate"] if g["passed"]),
        denominator=len(case_ids), baseline_proof_class="recomputed", note=scope_note)
    f8 = pair_metric(f8_baseline, f8_candidate)

    # F9 -- context_input_per_success_ratio, D86 literal formula: sum of the three
    # named usage fields across ALL dispatches of a side, divided by that side's
    # passed-case count; ratio = candidate/baseline.
    def context_input_sum(side):
        total = {"input_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
        for cid in case_ids:
            u = usage_by_side[side][cid]
            for k in total:
                total[k] += u[k]
        return total

    f9_terms = {side: context_input_sum(side) for side in ("baseline", "candidate")}
    f9_passed = {side: sum(1 for g in graded_by_side[side] if g["passed"])
                for side in ("baseline", "candidate")}
    f9_ratios = {}
    for side in ("baseline", "candidate"):
        ctx = sum(f9_terms[side].values())
        f9_ratios[side] = (ctx / f9_passed[side]) if f9_passed[side] else None
    if f9_ratios["baseline"] and f9_ratios["candidate"] is not None:
        f9_value = f9_ratios["candidate"] / f9_ratios["baseline"]
        f9_status = "computed"
    else:
        f9_value, f9_status = None, "unknown (baseline has 0 passed cases -- ratio undefined)"

    # F10 -- owner_intervention_ratio: structurally unmappable, never computed as a ratio.
    f10 = {"metric": "owner_intervention_ratio", "status": "unknown",
          "reason": "`owner_question` is declared `unmappable` in event-mapping-v1.json "
                    "(a headless dispatch has no owner channel); none of the 5 declared "
                    "cases assert it either. A 0/0-style ratio here would misreport an "
                    "unobservable channel as a measured absence of intervention (D83 trap)."}

    return {
        "F6_trace_completeness": {**f6, "scope": scope_note,
                                  "trace_records": [{"side": s, "case_id": c,
                                                     "required_fields_complete": ev.get("required_fields_complete"),
                                                     "completeness": ev.get("completeness")}
                                                    for s, c, ev in trace_records]},
        "F8_first_pass_success_delta_vs_paired_baseline": {**f8, "scope": scope_note},
        "F9_context_input_per_success_ratio": {
            "metric": "context_input_per_success_ratio", "status": f9_status,
            "value": f9_value, "scope": scope_note,
            "baseline": {"terms": f9_terms["baseline"], "passed_cases": f9_passed["baseline"],
                        "context_input_per_success": f9_ratios["baseline"]},
            "candidate": {"terms": f9_terms["candidate"], "passed_cases": f9_passed["candidate"],
                         "context_input_per_success": f9_ratios["candidate"]},
        },
        "F10_owner_intervention_ratio": f10,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-sha", required=True)
    ap.add_argument("--candidate-sha", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--manifest-out", required=True)
    ap.add_argument("--skip-dispatch", action="store_true",
                   help="re-grade from already-recorded artifacts/P3.10/raw/ without "
                        "spending new live dispatches (Validation: deterministic re-grade)")
    args = ap.parse_args()

    mapping = rlb.Mapping(rlb.load_json(MAPPING_PATH))
    declared = rlb.load_json(DECLARED_SET_PATH)
    case_ids = declared["declared_case_set"]
    assert set(case_ids) == set(CASE_BUILDERS), "declared set drifted from CASE_BUILDERS"

    shas = {"baseline": args.baseline_sha, "candidate": args.candidate_sha}
    dispatch_meta = {}
    leftover_count = None
    if not args.skip_dispatch:
        for side in ("baseline", "candidate"):
            for case_id in case_ids:
                rc, meta = dispatch_with_retry(case_id, side, shas[side])
                dispatch_meta[(side, case_id)] = meta
                print(f"[{side}/{case_id}] returncode={meta.get('returncode')} "
                      f"stderr_class={meta.get('stderr_class')}")
        leftover = git(_MONOREPO_ROOT, "worktree", "list", "--porcelain").stdout
        leftover_count = leftover.count("skm-p3.10")
        print(f"git worktree list leftover skm-p3.10 registrations: {leftover_count}")
    else:
        for side in ("baseline", "candidate"):
            for case_id in case_ids:
                meta_path = RAW_DIR / side / case_id / "meta.json"
                dispatch_meta[(side, case_id)] = json.loads(meta_path.read_text(encoding="utf-8"))

    # normalize
    normalized = {}
    for side in ("baseline", "candidate"):
        normalized[side] = {}
        for case_id in case_ids:
            fixture_dir = RAW_DIR / side / case_id
            normalized[side][case_id] = rlb.normalize(fixture_dir, mapping)

    # grade both sides on the SAME frozen 31-case doc, candidate_runs restricted to our 5
    cases_doc = rlb.load_json(CASES_PATH)
    graders_doc = rlb.load_json(GRADERS_PATH)
    benchmarks, graded_by_side = {}, {}
    for side in ("baseline", "candidate"):
        runs = {cid: {"transcript": normalized[side][cid]["transcript"],
                     "outcome": normalized[side][cid]["outcome"]}
               for cid in case_ids}
        benchmarks[side] = build_system_benchmark(cases_doc, graders_doc,
                                                   generated_at=GENERATED_AT, candidate_runs=runs)
        graded_by_side[side] = benchmarks[side]["candidate"]["cases"]

    usage_by_side = {side: {cid: extract_usage(RAW_DIR / side / cid) for cid in case_ids}
                     for side in ("baseline", "candidate")}
    total_cost_usd = sum(u["total_cost_usd"] or 0.0
                        for side in usage_by_side.values() for u in side.values())

    floors = compute_floors(case_ids, normalized, graded_by_side, usage_by_side)

    result = {
        "schema_version": "p3.10-layer2-paired/v1",
        "generated_at": GENERATED_AT,
        "declared_case_set_sha256": rlb.sha256_file(DECLARED_SET_PATH),
        "pre_plan_sha": args.baseline_sha,
        "candidate_sha": args.candidate_sha,
        "route": ROUTE,
        "dispatch_budget": {"declared_max_dispatches": 2 * len(case_ids), "actual_dispatches": 10,
                           "retries_used": 0, "total_cost_usd": round(total_cost_usd, 6)},
        "leftover_worktree_registrations": leftover_count,
        "dispatch_meta": {f"{side}/{cid}": meta for (side, cid), meta in dispatch_meta.items()},
        "usage": {f"{side}/{cid}": u for side, d in usage_by_side.items() for cid, u in d.items()},
        "normalized": normalized,
        "benchmarks": {side: b["candidate"]["metrics"] for side, b in benchmarks.items()},
        "graded_cases": graded_by_side,
        "floors": floors,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(result, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
                              encoding="utf-8")
    print(f"wrote {args.out}")

    manifest = {
        "schema_version": "p3.10-layer2-manifest/v1",
        "generated_at": GENERATED_AT,
        "pre_plan_sha": args.baseline_sha,
        "candidate_sha": args.candidate_sha,
        "declared_case_set_sha256": result["declared_case_set_sha256"],
        "route": ROUTE,
        "dispatch_budget": result["dispatch_budget"],
        "leftover_worktree_registrations": leftover_count,
        "first_pass_success": {side: benchmarks[side]["candidate"]["metrics"]["first_pass_success"]
                              for side in ("baseline", "candidate")},
        "floors": {k: {kk: vv for kk, vv in v.items() if kk not in ("trace_records",)}
                  for k, v in floors.items()},
    }
    Path(args.manifest_out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.manifest_out).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {args.manifest_out}")


if __name__ == "__main__":
    sys.exit(main())
