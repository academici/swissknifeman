"""eval — the `skiller eval` command and the registry-bound part of skill evaluation.

The evaluation itself (grader, benchmark builders, runner, result context `eval-context/v1`,
viewer, scaffold) lives in `aicore.content.eval`; its names are re-exported here under the
historical module path. What stays here reads the skill registry (`env.root`) or prints the CLI:
`resolve_skill`, `cmd_eval` and its offline report.

Package conventions: stdlib-only, `Env` explicit, atomic record (`core.io`), messages
in Russian."""
import json
import time

from core import atomic_write_json, atomic_write_text, die, parse_args, safe_load_json, warn

from aicore.content.eval import (  # noqa: F401 (re-export under the historical names)
    ASSERTION_TYPES,
    CLAUDE_BIN_ENV,
    DEFAULT_TIMEOUT,
    DESC_MAX,
    EVALS_SUBDIR,
    GRADER_VERSION,
    SYSTEM_OPERATORS,
    _fmt_frac,
    _sqrt_fraction,
    _stringify_fractions,
    aggregate_runs,
    apply_system_operator,
    build_benchmark,
    build_run_cmd,
    build_system_benchmark,
    claude_bin,
    classify_portability_tier,
    codex_bin,
    compare_eval_context,
    compute_system_metrics,
    eval_context,
    evals_coverage,
    grade_assertion,
    grade_case,
    grade_system_case,
    pair_system_metric,
    provider_capability_matrix,
    render_html,
    render_markdown,
    run_case,
    run_suite,
    runner_context,
    scaffold_evals,
    score_description,
    seeded_system_sample,
    select_best_description,
    skill_eval_context,
    validate_evals,
    validate_pressure,
    validate_system_cases,
    validate_system_graders,
    validate_triggers,
)


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
    # schema_version — spaced (not naked "3"): same benchmark.json-family
    # holds and the build_system_benchmark artifact with his "system-bank-
    # benchmark/v2" — two incomparable version dictionaries under the same short
    # name would be a defect. v3 adds `context` (eval-context/v1): the skill digest,
    # the fixtures, the grader and the runner actually observed.
    bench["schema_version"] = "skill-benchmark/v3"
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
    observed_models = [m for r in with_runs + (base_runs or []) for m in r.get("models", [])]
    bench["context"] = skill_eval_context(
        skill_dir, f"{skill_dir.parent.name}/{skill_name}",
        runner_context(claude, observed_models))
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
