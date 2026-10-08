"""eval — behavioral testing of registry skills (eval-first authoring).

Why: until now, skills were checked ONLY structurally (`validate.sh`: frontmatter,
diagrams, links, graphs and provider projections). Not
was the answer to the main question - *does the skill even work and work properly?*
This module closes the gap: format eval-cases, software (deterministic)
output evaluation, run with-skill vs baseline, pressure-tests «temptation to miss
skill», metrics aggregate and trigger accuracy optimization `description`.

Adapted (methodology, not code) from anthropic `skill-creator` (evals.json /
benchmark / iteration-loop / description-optimization) and obra/superpowers
`writing-skills` (pressure-tests - TDD for documentation). Licenses of those skills -
demo/MIT; here is our own implementation under the registry conventions.

The layer is spaced intentionally:
  • PURE logic (grader, unit, scoring/selection descriptions, schema validation,
    scaffold, viewer, resolve) — offline and deterministic → covered unit-tests,
    is chasing in CI without network.
  • RUNNER (`run_case` via `claude -p`) — online, opt-in. No `claude` in PATH →
    command softly degrades (scaffold + offline validation), CI does not crash.

Package conventions: stdlib-only, `Env` explicit, atomic record (`core.io`), messages
in Russian. Token math is NOT here (single source `budget.py`)."""
import hashlib
import json
import math
import os
import re
import shutil
import statistics
import subprocess
import tempfile
import time
from fractions import Fraction
from pathlib import Path

from core import (atomic_write_json, atomic_write_text, die, parse_args,
                  safe_load_json, warn)

from ..common import is_within

# --- constants ----------------------------------------------------------------
# Assertion types - deterministic ONLY (without LLM-judge), to grade was
# reproduced in CI. LLM-judge — separate online-mode, not for gate.
ASSERTION_TYPES = {"contains", "not_contains", "regex", "not_regex",
                   "file_exists", "file_absent", "min_words"}
# Trigger description (tier-0) hold ≤150 char. - the same rule as in lean-canon.
DESC_MAX = 150
DEFAULT_TIMEOUT = 180          # sec per run `claude -p`
EVALS_SUBDIR = "evals"
# Overridden command builder claude — skill injection flag verified by
# `claude --help` local installation (see build_run_cmd / docs/guide/evals.md).
CLAUDE_BIN_ENV = "SKM_CLAUDE_BIN"


# ============================================================================ #
# GRADER (offline, deterministic)                                          #
# ============================================================================ #
def grade_assertion(assertion, output, workspace):
    """Evaluate one assertion against run output. → (ok: bool, detail: str).

    assertion = {"type": <ASSERTION_TYPES>, "value": <str|int>, "flags"?: {...}}.
    Text comparisons are case insensitive by default (flags.case_sensitive=true
    disables) — natural language is more robust this way. file_*-assertions resolve value
    regarding workspace (run directory)."""
    atype = assertion.get("type", "")
    value = assertion.get("value", "")
    flags = assertion.get("flags", {}) or {}
    ci = not flags.get("case_sensitive", False)
    text = output or ""
    hay = text.lower() if ci else text
    needle = str(value).lower() if ci else str(value)
    reflags = re.IGNORECASE if ci else 0

    if atype == "contains":
        ok = needle in hay
        return ok, f"contains {value!r}: {'found' if ok else 'NOT found'}"
    if atype == "not_contains":
        ok = needle not in hay
        return ok, f"not_contains {value!r}: {'missing' if ok else 'FOUND (bad)'}"
    if atype == "regex":
        ok = re.search(str(value), text, reflags) is not None
        return ok, f"regex {value!r}: {'matched' if ok else 'did NOT match'}"
    if atype == "not_regex":
        ok = re.search(str(value), text, reflags) is None
        return ok, f"not_regex {value!r}: {'no matches' if ok else 'MATCHED (bad)'}"
    if atype in ("file_exists", "file_absent"):
        if not workspace:
            return False, f"{atype} {value!r}: no workspace"
        cand = Path(workspace) / str(value)
        # value is taken from evals.json (may also be external/upstream skills) — '../'
        # should not escape the run directory. fail-closed: path out workspace → broken.
        if not is_within(cand, workspace):
            return False, f"{atype} {value!r}: path out workspace (traversal prohibited)"
        exists = cand.exists()
        ok = exists if atype == "file_exists" else not exists
        return ok, f"{atype} {value!r}: {'ok' if ok else 'broken'}"
    if atype == "min_words":
        try:
            need = int(value)
        except (TypeError, ValueError):
            return False, f"min_words: value is not a number ({value!r})"
        got = len(text.split())
        return got >= need, f"min_words {need}: received {got}"
    return False, f"unknown assertion type: {atype!r}"


def grade_case(case, output, workspace=None):
    """Rate case (set of assertions) vs output. → dict.

    {id, passed: bool|None, checks: [{type, ok, detail}]}. Case without assertions →
    passed=None (not rated) — these don't go to pass_rate (nothing to check)."""
    asserts = case.get("assertions", []) or []
    checks = []
    for a in asserts:
        ok, detail = grade_assertion(a, output, workspace)
        checks.append({"type": a.get("type", ""), "ok": ok, "detail": detail})
    passed = None if not checks else all(c["ok"] for c in checks)
    return {"id": case.get("id"), "passed": passed, "checks": checks}


# ============================================================================ #
# SCHEME VALIDATION (offline)                                                     #
# ============================================================================ #
def _validate_cases(cases, label, *, kind):
    errors = []
    if not isinstance(cases, list) or not cases:
        return [f"{label}: '{kind}' must be a non-empty array"]
    seen = set()
    for i, c in enumerate(cases):
        where = f"{label}[{i}]"
        if not isinstance(c, dict):
            errors.append(f"{where}: case must be an object")
            continue
        cid = c.get("id")
        if cid is None:
            errors.append(f"{where}: no field id")
        elif cid in seen:
            errors.append(f"{where}: duplicate id {cid!r}")
        else:
            seen.add(cid)
        if not c.get("prompt"):
            errors.append(f"{where}: no non-empty prompt")
        asserts = c.get("assertions", [])
        if not isinstance(asserts, list):
            errors.append(f"{where}: assertions must be an array")
            asserts = []
        for j, a in enumerate(asserts):
            if not isinstance(a, dict):
                errors.append(f"{where}.assertions[{j}]: must be an object")
                continue
            at = a.get("type", "")
            if at not in ASSERTION_TYPES:
                errors.append(f"{where}.assertions[{j}]: type {at!r} not from "
                              f"{sorted(ASSERTION_TYPES)}")
            if "value" not in a:
                errors.append(f"{where}.assertions[{j}]: no field value")
    return errors


def validate_evals(data, label="evals.json"):
    """Structural validation evals.json. → list of errors (empty = valid)."""
    if not isinstance(data, dict):
        return [f"{label}: root must be an object"]
    errors = []
    if not data.get("skill"):
        errors.append(f"{label}: no field skill")
    errors += _validate_cases(data.get("cases"), label, kind="cases")
    return errors


def validate_pressure(data, label="pressure.json"):
    """Structural validation pressure.json (temptation scenarios). → list of errors.

    Scenario - the same grade contract (assertions), plus field `tempts` (that agent
    is tempting to do it, skipping the skill) for readability. Optional field
    `triggers` — list of strings `should_trigger` from triggers.json, which
    script covers; the form is checked here, the completeness of coverage is checked in validate.sh
    (cross-file verification with the same skill triggers.json)."""
    if not isinstance(data, dict):
        return [f"{label}: root must be an object"]
    errors = []
    if not data.get("skill"):
        errors.append(f"{label}: no field skill")
    scenarios = data.get("scenarios")
    errors += _validate_cases(scenarios, label, kind="scenarios")
    if isinstance(scenarios, list):
        for i, sc in enumerate(scenarios):
            if not isinstance(sc, dict) or "triggers" not in sc:
                continue
            t = sc["triggers"]
            if not isinstance(t, list) or any(not isinstance(x, str) or not x.strip() for x in t):
                errors.append(f"{label}.scenarios[{i}].triggers: must be an array "
                              f"non-empty lines")
    return errors


def validate_triggers(data, label="triggers.json"):
    """Validation triggers.json to optimize the description. → list of errors."""
    if not isinstance(data, dict):
        return [f"{label}: root must be an object"]
    errors = []
    for key in ("should_trigger", "should_not"):
        v = data.get(key)
        if not isinstance(v, list) or not v:
            errors.append(f"{label}: '{key}' must be a non-empty query array")
        elif any(not isinstance(q, str) or not q.strip() for q in v):
            errors.append(f"{label}: '{key}' contains empty/non-string query")
    return errors


# ============================================================================ #
# UNIT BENCHMARK (offline)                                                   #
# ============================================================================ #
# P8.9: metrics hold `fractions.Fraction` up to the very edge of the record - exact
# arithmetic (no intermediate `round()`-distortion), none float even
# transitive (√ — via `math.isqrt`, not `math.sqrt`). Render by line - one
# function `_fmt_frac`, applied recursively `_stringify_fractions` exactly one
# times, before `atomic_write_json` (see cmd_eval). Downstream-consumers (viewer)
# read via `float(x)` — works with Fraction (tests pull build_benchmark
# directly), and with the line (real `cmd_eval`-path).
def _sqrt_fraction(value, ndigits=9):
    """√(Fraction ≥ 0) → Fraction-approaching with `ndigits` fractional digits, integer
    (`math.isqrt`) — without float even transitively. value<=0 → Fraction(0)."""
    fr = value if isinstance(value, Fraction) else Fraction(value)
    if fr <= 0:
        return Fraction(0)
    scale = Fraction(10) ** (2 * ndigits)
    scaled = fr * scale
    root = math.isqrt(scaled.numerator * scaled.denominator) // scaled.denominator
    return Fraction(root, 10 ** ndigits)


def _fmt_frac(value, ndigits=3):
    """Fraction|int|None → fixed precision string (round-half-up on the exact
    fractions, without float). None → None (nothing to measure)."""
    if value is None:
        return None
    fr = value if isinstance(value, Fraction) else Fraction(value)
    sign = "-" if fr < 0 else ""
    fr = abs(fr)
    scale = Fraction(10) ** ndigits
    scaled = fr * scale
    q, r = divmod(scaled.numerator, scaled.denominator)
    if 2 * r >= scaled.denominator:
        q += 1
    s = str(q).rjust(ndigits + 1, "0")
    return f"{sign}{s[:-ndigits]}.{s[-ndigits:]}"


def _stringify_fractions(obj, ndigits=3):
    """Recursively replace Fraction-leaves in rows (`_fmt_frac`) — invariant «neither
    one float/Fraction in JSON-report» at record boundary (not before: internal
    calculations remain accurate until this step)."""
    if isinstance(obj, Fraction):
        return _fmt_frac(obj, ndigits)
    if isinstance(obj, dict):
        return {k: _stringify_fractions(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_stringify_fractions(v, ndigits) for v in obj]
    return obj


def _stat(values):
    """(mean, stddev) like Fraction|None by list of numbers; None/bool filtered.
    mean — exact mean; stddev — √(population variance) via
    `_sqrt_fraction` (integer). stddev=Fraction(0) when <2 values."""
    nums = [Fraction(v) for v in values
           if isinstance(v, (int, float, Fraction)) and not isinstance(v, bool)]
    if not nums:
        return None, None
    n = len(nums)
    mean = sum(nums, Fraction(0)) / n
    if n > 1:
        var = sum((x - mean) ** 2 for x in nums) / n
        sd = _sqrt_fraction(var)
    else:
        sd = Fraction(0)
    return mean, sd


def aggregate_runs(case_results):
    """Reduce the list of case runs into set metrics.

    case_results: [{passed: bool|None, duration_s?, tokens?}]. →
    {total, graded, passed, pass_rate, duration_mean, duration_std,
     tokens_mean, tokens_std} — numeric metrics Fraction|None (exact arithmetic,
     see _stat); string rendering - at the record boundary (cmd_eval). pass_rate=None,
     if there is nothing to evaluate."""
    total = len(case_results)
    graded = [r for r in case_results if r.get("passed") is not None]
    passed = sum(1 for r in graded if r["passed"])
    d_mean, d_std = _stat([r.get("duration_s") for r in case_results])
    t_mean, t_std = _stat([r.get("tokens") for r in case_results])
    return {
        "total": total,
        "graded": len(graded),
        "passed": passed,
        "pass_rate": Fraction(passed, len(graded)) if graded else None,
        "duration_mean": d_mean, "duration_std": d_std,
        "tokens_mean": t_mean, "tokens_std": t_std,
    }


def build_benchmark(skill, with_skill_runs, baseline_runs=None):
    """Collect benchmark from runs with-skill (and opt. baseline). Pure function:
    without time/IO (is deterministic for tests; generated_at/provenance/
    schema_version puts cmd_eval). Numeric metrics - Fraction|None."""
    bench = {"skill": skill, "with_skill": aggregate_runs(with_skill_runs)}
    if baseline_runs is not None:
        base = aggregate_runs(baseline_runs)
        bench["baseline"] = base
        ws, bs = bench["with_skill"], base
        delta = {}
        if ws["pass_rate"] is not None and bs["pass_rate"] is not None:
            delta["pass_rate"] = ws["pass_rate"] - bs["pass_rate"]
        if ws["tokens_mean"] is not None and bs["tokens_mean"] is not None:
            delta["tokens_mean"] = ws["tokens_mean"] - bs["tokens_mean"]
        bench["delta"] = delta
    return bench


# ============================================================================ #
# TRIGGER - DESCRIPTION PRECISION (logic offline; judge is injected)               #
# ============================================================================ #
def score_description(description, trigger_set, judge):
    """Assess how `description` works appropriately and not falsely.

    trigger_set = {"should_trigger": [q...], "should_not": [q...]}.
    judge(description, query) -> bool — prediction «will the skill work?». Online
    judge = model call; a deterministic fake is injected into tests.
    → {tp, fp, fn, tn, precision, recall, f1, accuracy, len, over_limit}."""
    st = trigger_set.get("should_trigger", []) or []
    sn = trigger_set.get("should_not", []) or []
    tp = sum(1 for q in st if judge(description, q))
    fn = len(st) - tp
    fp = sum(1 for q in sn if judge(description, q))
    tn = len(sn) - fp
    total = tp + fn + fp + tn
    # Fraction — exact relationships, not round()-distortion; Fraction completely
    # is ordered, select_best_description sorts by it without changes.
    precision = Fraction(tp, tp + fp) if (tp + fp) else Fraction(0)
    recall = Fraction(tp, tp + fn) if (tp + fn) else Fraction(0)
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) else Fraction(0))
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision, "recall": recall, "f1": f1,
        "accuracy": Fraction(tp + tn, total) if total else Fraction(0),
        "len": len(description), "over_limit": len(description) > DESC_MAX,
    }


def select_best_description(candidates, trigger_set, judge, *, max_len=DESC_MAX):
    """Select the best description candidate based on the trigger set.

    Candidates are longer max_len or empty ones are rejected (rule ≤150 char.
    tier-0 indestructible). Ranking: f1 → accuracy → in short. →
    {best, score, ranked: [...], rejected: [...]}; best=None, if all are discarded."""
    rejected = [c for c in candidates if not c.strip() or len(c) > max_len]
    pool = [c for c in candidates if c.strip() and len(c) <= max_len]
    scored = [(c, score_description(c, trigger_set, judge)) for c in pool]
    scored.sort(key=lambda cs: (cs[1]["f1"], cs[1]["accuracy"], -cs[1]["len"]),
                reverse=True)
    best = scored[0] if scored else None
    return {
        "best": best[0] if best else None,
        "score": best[1] if best else None,
        "ranked": [{"description": c, "score": s} for c, s in scored],
        "rejected": rejected,
    }


# ============================================================================ #
# RUNNER (online, opt-in)                                                      #
# ============================================================================ #
def claude_bin():
    """Path to CLI `claude`: env-override SKM_CLAUDE_BIN → PATH. None, if not."""
    override = os.environ.get(CLAUDE_BIN_ENV)
    if override:
        p = Path(os.path.expanduser(override))
        return str(p) if p.exists() else None
    found = shutil.which("claude")
    return found


def build_run_cmd(claude, prompt, skill_text=None):
    """Collect argv for `claude -p`. The skill is injected via
    --append-system-prompt (flag checked by `claude --help` installations). Output -
    JSON (--output-format json) to extract result+usage."""
    cmd = [claude, "-p", prompt, "--output-format", "json"]
    if skill_text:
        cmd += ["--append-system-prompt", skill_text]
    return cmd


def _parse_claude_json(stdout):
    """(text, tokens) from JSON-output `claude -p`. Not parsed → (stdout, None)."""
    try:
        data = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):
        return stdout, None
    text = data.get("result", "") if isinstance(data, dict) else stdout
    tokens = None
    usage = data.get("usage") if isinstance(data, dict) else None
    if isinstance(usage, dict):
        tokens = (usage.get("input_tokens", 0) or 0) + \
                 (usage.get("output_tokens", 0) or 0) or None
    return text, tokens


def run_case(skill_dir, case, *, with_skill, workspace, timeout=DEFAULT_TIMEOUT,
             claude=None, clock_ns=time.monotonic_ns):
    """One run of the case through `claude -p` in the catalog workspace.

    with_skill=True → body SKILL.md is mixed into the system promt (baseline without
    him - skill effect isolation). case.files[] (if available) are written in workspace
    before the run. `clock_ns` — injected clock (default `time.monotonic_ns`);
    tests substitute a deterministic counter ⇒ the report is reproduced byte by byte.
    duration_s — accurate `Fraction(ns, 10**9)`, not float. →
    {id, output, returncode, duration_s, tokens, error?}."""
    claude = claude or claude_bin()
    if not claude:
        raise RuntimeError("CLI `claude` not found - runner unavailable (offline)")
    ws = Path(workspace)
    ws.mkdir(parents=True, exist_ok=True)
    for f in case.get("files", []) or []:
        fp = ws / f.get("path", "")
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text(f.get("content", ""), encoding="utf-8")
    skill_text = None
    if with_skill:
        md = Path(skill_dir) / "SKILL.md"
        skill_text = md.read_text(encoding="utf-8") if md.is_file() else None
    cmd = build_run_cmd(claude, case["prompt"], skill_text)
    start_ns = clock_ns()
    try:
        proc = subprocess.run(cmd, cwd=str(ws), capture_output=True, text=True,
                              timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        return {"id": case.get("id"), "output": "", "returncode": -1,
                "duration_s": Fraction(clock_ns() - start_ns, 10 ** 9), "tokens": None,
                "error": f"timeout {timeout}s"}
    text, tokens = _parse_claude_json(proc.stdout)
    return {"id": case.get("id"), "output": text, "returncode": proc.returncode,
            "duration_s": Fraction(clock_ns() - start_ns, 10 ** 9), "tokens": tokens}


def run_suite(skill_dir, cases, *, with_skill, timeout=DEFAULT_TIMEOUT,
              claude=None, clock_ns=time.monotonic_ns):
    """Run a set of cases (each in its own temporary workspace) and evaluate.
    → [{...run_case, **grade_case}]. Online. `clock_ns` — see run_case."""
    results = []
    for case in cases:
        with tempfile.TemporaryDirectory(prefix="skiller-eval-") as ws:
            run = run_case(skill_dir, case, with_skill=with_skill, workspace=ws,
                           timeout=timeout, claude=claude, clock_ns=clock_ns)
            grade = grade_case(case, run.get("output", ""), ws)
        results.append({**run, **grade})
    return results


# ============================================================================ #
# SYSTEM BANK ADAPTER — deterministic structured graders #
# ============================================================================ #
# The frozen P0.3 reliability bank (
# artifacts/reliability-bank-v1/`) grades a case by a TRANSCRIPT (ordered typed
# events) + OUTCOME (dict) record, not a single free-text string — a different
# vocabulary from ASSERTION_TYPES above (which grades one string). Its own
# `run_bank.py` is the sole executable owner of THAT frozen case set (schema/
# probes/floors/manifest) and stays untouched — but the deterministic GRADING
# ALGORITHM itself is exactly what this item ports into skiller, so the eval
# seam survives the plan's own archival (`plans/<ID>/` is not a durable
# dependency surface for a package). Reimplemented here, not imported — cited
# in the trace-metrics contract's own docstring convention ("each contract
# owns its own closed enum rather than sharing a runtime module across an
# unrelated boundary"). No LLM judge anywhere in this path.
SYSTEM_OPERATORS = {"event_present", "event_absent", "event_order", "event_count_max",
                   "event_count_min", "outcome_field_equals", "outcome_list_contains",
                   "outcome_list_excludes"}


def _system_matches(event, where):
    return all(event.get(k) == v for k, v in (where or {}).items())


def _system_select(transcript, spec):
    return [e for e in transcript
           if e.get("type") == spec.get("type") and _system_matches(e, spec.get("where"))]


def _system_dig(outcome, path):
    node = outcome
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def apply_system_operator(operator, args, transcript, outcome):
    """One deterministic operator over a structured transcript/outcome record.
    → (observed: bool, detail: str). Vocabulary/semantics match
    `reliability-acceptance-v1.md` § Graders exactly (eight operators, no
    model call anywhere)."""
    args = args or {}
    if operator == "event_present":
        hits = _system_select(transcript, args)
        return bool(hits), f"event_present {args.get('type')}: {len(hits)}"
    if operator == "event_absent":
        hits = _system_select(transcript, args)
        return not hits, f"event_absent {args.get('type')}: {len(hits)}"
    if operator == "event_order":
        before, after = args["before"], args["after"]
        afters = _system_select(transcript, after)
        if not afters:
            return True, f"event_order: no {after.get('type')} events — vacuously ok"
        befores = _system_select(transcript, before)
        ok = all(any(b["seq"] < a["seq"] for b in befores) for a in afters)
        return ok, (f"event_order {before.get('type')}->{after.get('type')}: "
                   f"{'ok' if ok else 'VIOLATED'}")
    if operator == "event_count_max":
        hits = _system_select(transcript, args)
        ok = len(hits) <= args["max"]
        return ok, f"event_count_max {args.get('type')} <= {args['max']}: {len(hits)}"
    if operator == "event_count_min":
        hits = _system_select(transcript, args)
        ok = len(hits) >= args["min"]
        return ok, f"event_count_min {args.get('type')} >= {args['min']}: {len(hits)}"
    if operator == "outcome_field_equals":
        got = _system_dig(outcome, args["path"])
        return got == args["value"], f"outcome.{args['path']} == {args['value']!r}: got {got!r}"
    if operator in ("outcome_list_contains", "outcome_list_excludes"):
        got = _system_dig(outcome, args["path"])
        items = got if isinstance(got, list) else []
        present = args["value"] in items
        ok = present if operator == "outcome_list_contains" else not present
        return ok, f"{operator} outcome.{args['path']} {args['value']!r}: {'ok' if ok else 'violated'}"
    return False, f"unknown system operator: {operator!r}"


def grade_system_case(case, graders_by_id, transcript, outcome):
    """Grade one system-bank case (assertions bound to graders by id) against a
    transcript/outcome record. → {case_id, passed, checks}. `checks` carry each
    assertion's `tags` through unchanged — `compute_system_metrics` below reads
    them (e.g. `requirement_retention`) rather than re-deriving case semantics."""
    checks = []
    for a in case.get("assertions", []) or []:
        grader = graders_by_id.get(a.get("grader"))
        if grader is None:
            checks.append({"id": a.get("id"), "grader": a.get("grader"), "ok": False,
                          "tags": a.get("tags") or [],
                          "detail": f"unknown grader {a.get('grader')!r}"})
            continue
        observed, detail = apply_system_operator(grader["operator"], a.get("args"),
                                                  transcript, outcome)
        ok = observed == a.get("expect", True)
        checks.append({"id": a.get("id"), "grader": a.get("grader"), "expect": a.get("expect"),
                       "observed": observed, "ok": ok, "detail": detail,
                       "tags": a.get("tags") or []})
    return {"case_id": case.get("case_id"),
           "passed": all(c["ok"] for c in checks) if checks else None, "checks": checks}


def validate_system_graders(data, label="graders.json"):
    """Structural validation of a system-bank graders document (`reliability-
    bank/v1` shape): no-LLM-judge policy, operator closure. → errors (empty =
    valid). Generic — validates ANY system-bank-shaped doc, not only the frozen
     one (its own `run_bank.py` keeps ownership of THAT bank's schema)."""
    if not isinstance(data, dict):
        return [f"{label}: root must be an object"]
    errors = []
    policy = data.get("policy") or {}
    if policy.get("llm_judge_allowed") is not False:
        errors.append(f"{label}: policy.llm_judge_allowed must be false (D15)")
    seen = set()
    for i, g in enumerate(data.get("graders") or []):
        gid = g.get("id")
        if not gid or gid in seen:
            errors.append(f"{label}.graders[{i}]: missing or duplicate id {gid!r}")
        seen.add(gid)
        if g.get("operator") not in SYSTEM_OPERATORS:
            errors.append(f"{label}.graders[{i}]: operator {g.get('operator')!r} not in "
                          f"{sorted(SYSTEM_OPERATORS)}")
    if not seen:
        errors.append(f"{label}: empty grader list")
    return errors


def validate_system_cases(data, grader_ids, label="cases.json"):
    """Structural validation of a system-bank cases document. → errors (empty =
    valid). Deliberately does not enforce the frozen bank's own D10 20–50 case-
    count range — that range is a property of ONE specific frozen bank, not of
    this generic adapter."""
    if not isinstance(data, dict):
        return [f"{label}: root must be an object"]
    errors = []
    cases = data.get("cases")
    if not isinstance(cases, list) or not cases:
        errors.append(f"{label}: 'cases' must be a non-empty array")
        cases = []
    seen = set()
    for c in cases:
        cid = c.get("case_id")
        where = f"{label} case {cid!r}"
        if not cid or cid in seen:
            errors.append(f"{where}: missing or duplicate case_id")
        seen.add(cid)
        if c.get("kind") not in ("critical", "control"):
            errors.append(f"{where}: kind must be critical|control")
        asserts = c.get("assertions") or []
        if not asserts:
            errors.append(f"{where}: no assertions")
        for a in asserts:
            if a.get("grader") not in grader_ids:
                errors.append(f"{where}: unknown grader {a.get('grader')!r}")
        base = c.get("baseline") or {}
        if not base.get("transcript"):
            errors.append(f"{where}: baseline.transcript is empty")
        if "declared_status" not in (base.get("outcome") or {}):
            errors.append(f"{where}: baseline.outcome.declared_status missing")
    return errors


def compute_system_metrics(cases, graded, records):
    """Deterministic bank-level metrics from graded cases plus their
    `{transcript, outcome}` records. Same computation the frozen bank's own
    `run_bank.py::compute_metrics` owns for ITS 31 cases — reimplemented here
    (not imported, see module-level note) so skiller's regression surface does
    not depend on plan-scoped code. Cross-checked byte-for-byte against the
    frozen bank's own published `bank-manifest.json::layer1_metrics` numbers
    (see `test_eval.py`/Completion Notes) as a reproducibility proof, not a
    silent parallel reimplementation."""
    grade_by_id = {g["case_id"]: g for g in graded}
    critical = [c for c in cases if c.get("kind") == "critical"]
    control = [c for c in cases if c.get("kind") == "control"]

    def transcript(cid):
        return records[cid]["transcript"]

    def outcome(cid):
        return records[cid]["outcome"]

    retained = 0
    for c in critical:
        tagged = [ch for ch in grade_by_id[c["case_id"]]["checks"]
                 if "requirement_retention" in (ch.get("tags") or [])]
        if tagged and all(ch["ok"] for ch in tagged):
            retained += 1
    premature = [c["case_id"] for c in critical
                if _system_select(transcript(c["case_id"]), {"type": "premature_stop"})]
    redundant = [c["case_id"] for c in critical
                if _system_select(transcript(c["case_id"]), {"type": "redundant_approval"})]
    unneeded_owner = [c["case_id"] for c in cases
                     if not c.get("owner_gate_required")
                     and _system_select(transcript(c["case_id"]), {"type": "owner_question"})]
    depths = []
    for c in cases:
        counts = {}
        for e in _system_select(transcript(c["case_id"]), {"type": "finding"}):
            fid = e.get("finding_id")
            counts[fid] = counts.get(fid, 0) + 1
        if counts:
            depths.append(max(counts.values()))
    overrun = []
    for c in cases:
        budget = (c.get("environment") or {}).get("audit_rounds_max", 2)
        if len(_system_select(transcript(c["case_id"]), {"type": "audit_round"})) > budget:
            overrun.append(c["case_id"])
    routed = [c for c in cases
             if _system_select(transcript(c["case_id"]), {"type": "route_declared"})]
    compliant = [c for c in routed
                if not _system_select(transcript(c["case_id"]),
                                      {"type": "route_declared", "where": {"undershoot": True}})]
    escapes = []
    for c in critical:
        tagged = [ch for ch in grade_by_id[c["case_id"]]["checks"]
                 if "requirement_retention" in (ch.get("tags") or [])]
        if (any(not ch["ok"] for ch in tagged)
                and outcome(c["case_id"]).get("declared_status") == "success"):
            escapes.append(c["case_id"])
    false_blocks = [c["case_id"] for c in control
                   if _system_select(transcript(c["case_id"]), {"type": "block"})]

    def ratio(num, den):
        return round(num / den, 4) if den else None

    def _p95(values):
        if not values:
            return 0
        ordered = sorted(values)
        idx = max(0, math.ceil(0.95 * len(ordered)) - 1)
        return ordered[idx]

    critical_ids = {c["case_id"] for c in critical}
    graded_critical = [g for g in graded if g["case_id"] in critical_ids]

    return {
        "counts": {"cases": len(cases), "critical": len(critical), "control": len(control)},
        "critical_requirement_retention": ratio(retained, len(critical)),
        "premature_stop_count": len(premature),
        "premature_stop_cases": premature,
        "redundant_approval_count": len(redundant),
        "redundant_approval_cases": redundant,
        "first_pass_success": ratio(sum(1 for g in graded if g["passed"]), len(graded)),
        "first_pass_success_critical": ratio(
            sum(1 for g in graded_critical if g["passed"]), len(graded_critical)),
        "owner_intervention_rate": ratio(len(unneeded_owner), len(cases)),
        "owner_intervention_cases": unneeded_owner,
        "same_finding_loop_depth": {
            "samples": len(depths),
            "median": statistics.median(depths) if depths else 0,
            "p95": _p95(depths) if depths else 0,
        },
        "audit_loop_overrun_count": len(overrun),
        "audit_loop_overrun_cases": overrun,
        "routing_compliance": ratio(len(compliant), len(routed)),
        "critical_regression_escape": len(escapes),
        "critical_regression_escape_cases": escapes,
        "false_block_rate": ratio(len(false_blocks), len(control)),
    }


def seeded_system_sample(seed, case_ids, size):
    """Deterministic seeded sample: `sha256(seed|case_id)` ascending, first
    `size`. Same method `reliability-acceptance-v1.md` § sample specifies for
    the frozen bank — kept here so skiller's own gate can reproduce a small
    sample of ANY system-bank-shaped case set without depending on the plan-
    scoped `run_bank.py`."""
    ranked = sorted(case_ids, key=lambda cid: hashlib.sha256(
        f"{seed}|{cid}".encode("utf-8")).hexdigest())
    return ranked[:size]


# --- provider capability matrix --------------------------------------------- #
def codex_bin():
    """Path to the Codex CLI, if present. Mirrors `claude_bin()`'s env-override
    (`SKM_CODEX_BIN`) then PATH lookup."""
    override = os.environ.get("SKM_CODEX_BIN")
    if override:
        p = Path(os.path.expanduser(override))
        return str(p) if p.exists() else None
    return shutil.which("codex")


def provider_capability_matrix(*, claude_lookup=claude_bin, codex_lookup=codex_bin):
    """Presence-only provider capability probe for `{claude, codex}`: `native`
    when the CLI binary resolves, `unsupported` otherwise. Deliberately narrow
    (binary presence, not a live flag/version check) — a probe claiming more
    than this would itself be an unverified capability claim; D46 requires an
    unconfirmed capability to fail closed, never assume `native`."""
    return {
        "claude": {"capability": "native" if claude_lookup() else "unsupported"},
        "codex": {"capability": "native" if codex_lookup() else "unsupported"},
    }


# --- portability tier (`plan-portability-v1.md` § Classification rule) --- #
def classify_portability_tier(work):
    """Classify a case's portability tier from the four symptoms of `work`:
    `sessions` (`"single"`/`"multi"`), `risk` (`"low"`/`"high"`), `handoff` (bool),
    `audit` (bool). → `(tier, reason)`; `reason` is always `None` — the rule is local,
    so no optional package import can fail."""
    if (work.get("sessions") == "multi" or work.get("risk") == "high"
            or work.get("handoff") or work.get("audit")):
        return "committed-bundle", None
    return "brief-acceptance", None


# --- paired baseline/candidate ---------------------------------------------- #
def pair_system_metric(baseline, candidate):
    """Pair one baseline metric (`{metric, value, baseline_proof_class}`) with
    an optional live candidate. `candidate=None` → `status: 'deferred'` (never
    a silent zero). A baseline whose proof class is not `recomputed`/`cross-
    checked` can never ground a comparison — mirrors
    the trace-metrics `pair_metric` discipline, cited rather than imported
    (cross-package rationale in that module's own docstring)."""
    comparable = {"recomputed", "cross-checked"}
    if candidate is None:
        return {"metric": baseline["metric"], "status": "deferred",
                "baseline": baseline, "candidate": None, "delta": None}
    if baseline.get("baseline_proof_class") not in comparable:
        raise ValueError(
            f"SYSTEM_METRIC_PINNED_BASELINE_FORBIDDEN: {baseline['metric']!r} baseline is "
            f"{baseline.get('baseline_proof_class')!r}; cannot ground a comparison (D30)")
    delta = None
    if baseline.get("value") is not None and candidate.get("value") is not None:
        delta = candidate["value"] - baseline["value"]
    return {"metric": baseline["metric"], "status": "paired",
            "baseline": baseline, "candidate": candidate, "delta": delta}


def build_system_benchmark(cases_doc, graders_doc, *, generated_at, sample_size=5,
                           candidate_runs=None, provider_matrix=None):
    """Grade a system-bank case set against its own declared baseline transcripts
    (`case['baseline']['transcript'/'outcome']`) and, if `candidate_runs`
    (`{case_id: {transcript, outcome}}`) is supplied, pair the resulting
    `first_pass_success` metric against it; omitted → the pair is `deferred`
    (no live paired run yet exists — never fabricated, Execution Rules: "zero
    and silent skip are prohibited"). → the benchmark artifact shape."""
    graders_by_id = {g["id"]: g for g in graders_doc.get("graders", [])}
    cases = cases_doc.get("cases", [])
    baseline_records = {c["case_id"]: c["baseline"] for c in cases}
    baseline_graded = [grade_system_case(c, graders_by_id,
                                         c["baseline"]["transcript"], c["baseline"]["outcome"])
                      for c in cases]
    baseline_metrics = compute_system_metrics(cases, baseline_graded, baseline_records)
    candidate_graded, candidate_metrics = None, None
    if candidate_runs is not None:
        candidate_cases = [c for c in cases if c["case_id"] in candidate_runs]
        candidate_graded = [grade_system_case(c, graders_by_id,
                                              candidate_runs[c["case_id"]]["transcript"],
                                              candidate_runs[c["case_id"]]["outcome"])
                           for c in candidate_cases]
        candidate_metrics = compute_system_metrics(candidate_cases, candidate_graded,
                                                    candidate_runs)
    baseline_metric = {"metric": "first_pass_success",
                       "value": baseline_metrics["first_pass_success"],
                       "baseline_proof_class": "recomputed"}
    candidate_metric = ({"metric": "first_pass_success",
                        "value": candidate_metrics["first_pass_success"]}
                       if candidate_metrics is not None else None)
    # Sampled from baseline-PASSING cases only — same selection rule the frozen
    # bank's own manifest uses (a case whose declared baseline already
    # fails is not a representative "smoke" sample of steady-state behaviour).
    passing_ids = [g["case_id"] for g in baseline_graded if g["passed"]]
    sample = seeded_system_sample(
        cases_doc.get("sample_seed", "system-bank/default"),
        passing_ids, min(sample_size, len(passing_ids)))
    return {
        "schema_version": "system-bank-benchmark/v1",
        "generated_at": generated_at,
        "bank_version": cases_doc.get("bank_version"),
        "grader_version": graders_doc.get("grader_version"),
        "counts": {"cases": len(cases)},
        "baseline": {"cases": baseline_graded, "metrics": baseline_metrics},
        "candidate": ({"cases": candidate_graded, "metrics": candidate_metrics}
                     if candidate_graded is not None else None),
        "pair": pair_system_metric(baseline_metric, candidate_metric),
        "sample": {"seed": cases_doc.get("sample_seed"), "size": len(sample), "selected": sample},
        "provider_capability": provider_matrix or provider_capability_matrix(),
    }


# ============================================================================ #
#  VIEWER (markdown / standalone HTML)                                          #
# ============================================================================ #
def _fmt_rate(r):
    """String fraction (or Fraction — when called directly build_benchmark in tests;
    or None) → '50%' for display (P8.9: reading string rendering metrics)."""
    return "—" if r is None else f"{float(r) * 100:.0f}%"


def render_markdown(benchmark):
    """Human readable markdown-report on benchmark. Metrics - Fraction (direct
    call build_benchmark) or string (real benchmark.json from disk, P8.9) —
    both are read via float()."""
    b = benchmark
    ws = b.get("with_skill", {})
    out = [f"# Eval: {b.get('skill', '?')}", "",
           "| Set | pass@ | cases | current (μ±σ) | sec (μ±σ) |",
           "|---|--:|--:|--:|--:|"]

    def row(label, a):
        tok = "—" if a.get("tokens_mean") is None else \
            f"{float(a['tokens_mean']):.0f}±{float(a.get('tokens_std', 0)):.0f}"
        dur = "—" if a.get("duration_mean") is None else \
            f"{float(a['duration_mean']):.1f}±{float(a.get('duration_std', 0)):.1f}"
        return (f"| {label} | {_fmt_rate(a.get('pass_rate'))} | "
                f"{a.get('passed', 0)}/{a.get('graded', 0)} | {tok} | {dur} |")

    out.append(row("with-skill", ws))
    if b.get("baseline") is not None:
        out.append(row("baseline", b["baseline"]))
    if b.get("delta"):
        d = b["delta"]
        parts = []
        if "pass_rate" in d:
            parts.append(f"pass@ {float(d['pass_rate']) * 100:+.0f}pp")
        if "tokens_mean" in d:
            parts.append(f"current {float(d['tokens_mean']):+.0f}")
        out += ["", f"**Δ skill vs baseline:** {', '.join(parts) or '—'}"]
    return "\n".join(out) + "\n"


def render_html(benchmark):
    """Standalone HTML-report (--static) — markdown in <pre>, without dependencies."""
    md = render_markdown(benchmark).replace("&", "&amp;").replace("<", "&lt;")
    skill = benchmark.get("skill", "eval")
    return (f"<!doctype html><html lang=ru><meta charset=utf-8>"
            f"<title>eval: {skill}</title>"
            f"<body style='font:14px/1.5 system-ui;max-width:48rem;margin:2rem auto'>"
            f"<pre style='white-space:pre-wrap'>{md}</pre></body></html>\n")


# ============================================================================ #
# SCAFFOLD + RESOLUTION                                                            #
# ============================================================================ #
def _stub_evals(skill_name):
    return {"skill": skill_name, "cases": [{
        "id": 1,
        "prompt": "Real user request in the language of the ecosystem "
                  "(specifics: paths, names). Replace with yours.",
        "assertions": [
            {"type": "contains", "value": "expected-substring"},
            {"type": "not_contains", "value": "forbidden-substring"},
        ],
    }]}


def _stub_pressure(skill_name):
    return {"skill": skill_name, "scenarios": [{
        "id": 1,
        "tempts": "What an agent is tempted to do, MISSING a skill "
                  "(for example: write code immediately instead of checking the fact).",
        "prompt": "Temptation scenario under pressure. Replace with yours.",
        "assertions": [
            {"type": "contains", "value": "skill-compliance-sign"},
            {"type": "not_contains", "value": "violation-sign"},
        ],
    }]}


def _stub_triggers(skill_name):
    return {"skill": skill_name,
            "should_trigger": ["request on which the skill MUST work (1)",
                               "same topic in other words (2)"],
            "should_not": ["close, but NOT about this skill request (1)",
                           "one more near-miss (2)"]}


def scaffold_evals(skill_dir, skill_name=None):
    """Create stubs evals/{evals,pressure,triggers}.json (without overwriting
    existing). → list of created paths. Atomically (core.io)."""
    skill_dir = Path(skill_dir)
    skill_name = skill_name or skill_dir.name
    evals_dir = skill_dir / EVALS_SUBDIR
    created = []
    for fname, builder in (("evals.json", _stub_evals),
                           ("pressure.json", _stub_pressure),
                           ("triggers.json", _stub_triggers)):
        path = evals_dir / fname
        if path.exists():
            continue
        atomic_write_json(path, builder(skill_name))
        created.append(path)
    return created


def resolve_skill(env, ref):
    """Skill catalog by ref ('bucket/name' or 'name'). die, if not found/is ambiguous."""
    skills_root = env.root / "skills"
    ref = ref.strip().strip("/")
    if "/" in ref:
        cand = skills_root / ref
        if (cand / "SKILL.md").is_file():
            return cand
        die(f"skill not found: skills/{ref}/SKILL.md")
    matches = [p.parent for p in skills_root.glob(f"*/{ref}/SKILL.md")]
    if not matches:
        die(f"skill '{ref}' not found in the registry (indicate bucket/name)")
    if len(matches) > 1:
        rels = ", ".join(str(m.relative_to(skills_root)) for m in matches)
        die(f"ambiguous '{ref}' — is in several buckets: {rels}")
    return matches[0]


def evals_coverage(root):
    """(skills_with_evals, local_skills) by registry - for summary in validate/status.
    Local = without upstream.json (eval-standard for author's skills)."""
    skills_root = Path(root) / "skills"
    local, with_evals = 0, 0
    for skill_md in sorted(skills_root.glob("*/*/SKILL.md")):
        d = skill_md.parent
        if (d / "upstream.json").exists():
            continue
        local += 1
        if (d / EVALS_SUBDIR / "evals.json").exists():
            with_evals += 1
    return with_evals, local


# ============================================================================ #
#  CLI                                                                          #
# ============================================================================ #
_USAGE = (
    "skiller eval <bucket/skill | skill> [--baseline] [--triggers]\n"
    "             [--scaffold] [--static] [--json] [--timeout N]\n"
    "  Behavioral skill run: with-skill vs baseline, software assertions,\n"
    "  pressure-tests, benchmark.json. --triggers — trigger accuracy optimization\n"
    "  descriptions. --scaffold — create stubs evals/. Runner requires CLI `claude`\n"
    "  (not in PATH → offline validation + scaffold, no fall).")


def _offline_report(skill_dir):
    """Offline branch (no `claude`): validate existing evals and give me a hint."""
    evals_dir = skill_dir / EVALS_SUBDIR
    problems = []
    for fname, validator in (("evals.json", validate_evals),
                             ("pressure.json", validate_pressure),
                             ("triggers.json", validate_triggers)):
        data = safe_load_json(evals_dir / fname)
        if data is not None:
            problems += validator(data, fname)
    if problems:
        for p in problems:
            print(f"  SCHEMA ERROR: {p}")
    else:
        print("  diagram evals/ is valid")
    warn("CLI `claude` not found - run skipped (offline). Put claude "
         "or ask SKM_CLAUDE_BIN, to run with-skill vs baseline.")


def cmd_eval(env, argv, *, clock_ns=None, now_iso=None):
    """CLI entry point `skiller eval`. `clock_ns`/`now_iso` — injection point
    injected clock for deterministic tests (byte reproducibility
    benchmark.json); default `None` → real time, `provenance.clock: "wall"`.
    Behavior CLI without flags does not change (backwards compatible)."""
    opts, pos = parse_args(argv, {
        "--baseline": "bool", "--triggers": "bool", "--scaffold": "bool",
        "--static": "bool", "--json": "bool", "--timeout": "str",
    }, max_pos=1)
    if opts["help"] or not pos:
        print(_USAGE)
        return
    skill_dir = resolve_skill(env, pos[0])
    skill_name = skill_dir.name
    evals_dir = skill_dir / EVALS_SUBDIR

    if opts["scaffold"]:
        created = scaffold_evals(skill_dir, skill_name)
        if created:
            print(f"Stubs created: {', '.join(p.name for p in created)} "
                  f"in {evals_dir.relative_to(env.root)}")
        else:
            print("Stubs evals/ already exists - nothing created")
        return

    if not (evals_dir / "evals.json").exists():
        created = scaffold_evals(skill_dir, skill_name)
        print(f"No evals.json — created stubs ({', '.join(p.name for p in created)}). "
              f"Fill out the cases and restart `skiller eval {pos[0]}`.")
        return

    claude = claude_bin()
    timeout = int(opts["timeout"]) if opts.get("timeout") else DEFAULT_TIMEOUT

    # --- optimization of trigger precision description --------------------------------
    if opts["triggers"]:
        triggers = safe_load_json(evals_dir / "triggers.json")
        if triggers is None:
            scaffold_evals(skill_dir, skill_name)
            print("No triggers.json — created stab. Fill in should_trigger / "
                  "should_not and restart with --triggers.")
            return
        errs = validate_triggers(triggers, "triggers.json")
        if errs:
            die("triggers.json is invalid:\n  " + "\n  ".join(errs))
        if not claude:
            warn("CLI `claude` not found - description optimization requires model "
                 "(candidate generation + judge). Offline not available.")
            return
        # Online-candidate generation thread/judge moved out of the gate CI; implementation
        # pulls `claude -p`. Here is the framework: scoring/selection below are clean and
        # are covered with tests, the online runner is connected in the environment with the model.
        warn("Online-description optimization (--triggers) runs in an environment with "
             "model; scoring/selection available as API (score_description / "
             "select_best_description). See The docs/guide/evals.md.")
        return

    # --- run eval + pressure -----------------------------------------------
    if not claude:
        print(f"━━━ EVAL {skill_name} (offline) ━━━")
        _offline_report(skill_dir)
        return

    evals = safe_load_json(evals_dir / "evals.json") or {}
    errs = validate_evals(evals, "evals.json")
    pressure = safe_load_json(evals_dir / "pressure.json")
    if pressure is not None:
        errs += validate_pressure(pressure, "pressure.json")
    if errs:
        die("evals are invalid:\n  " + "\n  ".join(errs))

    cases = list(evals.get("cases", []))
    if pressure:
        cases += list(pressure.get("scenarios", []))

    _clock_ns = clock_ns if clock_ns is not None else time.monotonic_ns
    with_runs = run_suite(skill_dir, cases, with_skill=True, timeout=timeout,
                          claude=claude, clock_ns=_clock_ns)
    base_runs = None
    if opts["baseline"]:
        base_runs = run_suite(skill_dir, cases, with_skill=False, timeout=timeout,
                              claude=claude, clock_ns=_clock_ns)
    bench = build_benchmark(skill_name, with_runs, base_runs)
    # schema_version — spaced (not naked "2"): same benchmark.json-family
    # holds and P3.3-artifact build_system_benchmark with his "system-bank-
    # benchmark/v1" — two incomparable version dictionaries under the same short
    # name would be a defect (reconsult 2026-07-26, D52/`plan.md` §1).
    bench["schema_version"] = "skill-benchmark/v2"
    bench["generated_at"] = now_iso if now_iso is not None else \
        time.strftime("%Y-%m-%dT%H:%M:%S")
    # provenance — ACTUAL, not constant: this branch is only reachable when
    # `claude` is really resolved and `run_suite` really called him (gate `if not
    # claude` above) — real OR fake (SKM_CLAUDE_BIN) binary is the same
    # "lies" for llm/network (the very fact that the subprocess claude was started;
    # distinguish «real» model from a local fake at this level there is nothing).
    bench["provenance"] = {
        "llm": True,
        "network": True,
        "clock": "injected" if clock_ns is not None else "wall",
        "baseline": bool(opts["baseline"]),
    }
    bench["cases"] = [{"id": r.get("id"), "passed": r.get("passed"),
                       "checks": r.get("checks", [])} for r in with_runs]
    bench = _stringify_fractions(bench)
    atomic_write_json(evals_dir / "benchmark.json", bench)

    if opts["static"]:
        out = evals_dir / "benchmark.html"
        atomic_write_text(out, render_html(bench))
        print(f"HTML-report: {out.relative_to(env.root)}")
    if opts["json"]:
        print(json.dumps(bench, indent=2, ensure_ascii=False))
    else:
        print(render_markdown(bench))
