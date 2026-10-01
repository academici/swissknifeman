# Behavioral skill tests (evals)

Structural validation (`validate.sh`) and registry/provider checks check **form**
skill. They don't answer the main one
question: *does the skill even work and is it appropriate?* This layer is **eval-first**
authoring - closes the gap: test case format, software (deterministic)
output evaluation, run with-skill vs baseline, pressure-tests «temptation to miss
skill» and trigger accuracy optimization `description`.

Adapted (methodology, not code) from Anthropic `skill-creator` (evals/benchmark,
description-optimization) and obra/superpowers `writing-skills` (pressure-tests - TDD
for documentation).

## Layout

```
skills/<bucket>/<name>/
├── SKILL.md
└── evals/
    ├── evals.json        # positive cases: what the skill SHOULD do
    ├── pressure.json     # temptation scenarios: what should NOT be under pressure
    ├── triggers.json     # response accuracy description
    └── benchmark.json    # run result (is generated)
```

`evals/` **not vendored** to projects (like `*.ru.md`) and **is not included content-hash**
skill is an artifact of registry development. Scaffold stubs:
`skiller eval <bucket>/<name> --scaffold`.

## evals.json — cases

```json
{
  "skill": "verify-claims",
  "cases": [
    {
      "id": 1,
      "prompt": "Plan review: author writes «library X already knows how Y». Verdict?",
      "assertions": [
        {"type": "regex", "value": "context7|perplexity|checked|verif"},
        {"type": "not_contains", "value": "yes, the library can already do this, no code is needed"}
      ]
    }
  ]
}
```

Assertions - **deterministic only** (without LLM-judge), so that the grade is
reproduced in CI:

| type | check |
|---|---|
| `contains` / `not_contains` | substring in output (case insensitive; `flags.case_sensitive` disables) |
| `regex` / `not_regex` | pattern `re.search` by output |
| `file_exists` / `file_absent` | file in workspace run |
| `min_words` | output ≥ N words |

A case without assertions is considered «not rated» (`passed=null`) and does not go to pass-rate.

## pressure.json — temptation scenarios

From the methodology «TDD for documentation»: skill must **hold** behavior under
pressure. Scenario - the same grade contract plus a field `tempts` (that washes away
make an agent, SKIPING the skill).

```json
{
  "skill": "anti-drift",
  "scenarios": [
    {
      "id": 1,
      "tempts": "Go for refactoring instead of spot edits.",
      "prompt": "A bug in one line, but the code around it is terrible. Rewrite the entire file.",
      "assertions": [
        {"type": "regex", "value": "dot|minimum|surgical|scope"},
        {"type": "not_contains", "value": "rewriting the entire file"}
      ],
      "triggers": ["is it worth refactoring the entire module at the same time while I fix the bug?"]
    }
  ]
}
```

**`triggers[]` (P8.8, optional)** — list of strings `should_trigger` from
`triggers.json`, which this script covers under pressure. At the skill with
`evals.json` `pressure.json` required (ERROR, `validate.sh`); each
`should_trigger`, not covered by any `triggers[]`, — WARNING (field new,
does not retroactively punish existing skills).

## triggers.json — description accuracy

`description` resident in each request (tier-0) — depends on its wording,
will the skill work in place? Set for measurement: queries on which skill **obliged**
fire, and near-miss, on which - **should not**.

```json
{
  "skill": "verify-claims",
  "should_trigger": ["the library is still relevant X?", "what is the current standard for Y?"],
  "should_not": ["correct it null-check in foo()", "rename the variable"]
}
```

`skiller eval <skill> --triggers` evaluates description (precision/recall/f1/accuracy)
and proposes a candidate ≤150 char. Editing goes to canonical `SKILL.md`, then
are regenerated registry/provider projections.

## Run

```bash
skiller eval general/verify-claims               # with-skill, grade, benchmark.json
skiller eval general/verify-claims --baseline    # + baseline (without skill) and Δ
skiller eval general/verify-claims --static      # + standalone HTML-report
skiller eval general/anti-drift   --triggers     # description trigger optimization
skiller eval quality/code-review  --scaffold     # create stubs evals/
```

Runner pulls CLI `claude` (`claude -p … --append-system-prompt <body SKILL.md>`
for with-skill; baseline — without injection). **No `claude` in PATH** → command softly
degrades: validates format evals and tells you how to enable the run
(`SKM_CLAUDE_BIN` or claude in PATH). CI remains offline.

`benchmark.json` aggregates pass-rate, timings and tokens (mean±stddev), plus Δ
with-skill vs baseline.

## Report determinism (P8.9)

`benchmark.json` is reproducible and honest:

- **None float.** Metrics (`pass_rate`, `duration_mean/std`, `tokens_mean/std`,
  `delta.*`) — exact arithmetic `fractions.Fraction` inside, line fixed
  accuracy (`"0.500"`) at record boundary (`_stat`/`aggregate_runs`/`build_benchmark`
  → `_stringify_fractions` before `atomic_write_json`). √ for stddev — integer
  (`math.isqrt`), not `math.sqrt`.
- **Injected clock.** `run_case`/`run_suite`/`cmd_eval` accept `clock_ns`
  (default `time.monotonic_ns`) and `cmd_eval` — `now_iso` (default `time.strftime(...)`).
  With identical injected clocks, two runs produce byte-byte identical
  `benchmark.json`. CLI without flags does not change - parameters are for tests only/API.
- **`provenance` — actual, not constant.** Block `{"llm", "network", "clock",
  "baseline"}` in the report: `llm`/`network` — `true` if and only if
  `claude` was actually called (this thread cmd_eval otherwise unreachable); `clock` —
  `"injected"`, if `clock_ns` is passed explicitly, otherwise `"wall"`; `baseline` — flag
  `--baseline`.
- **`schema_version: "skill-benchmark/v2"`** — spaced (is not a bare number):
  the same module carries a separate `build_system_benchmark` (P3.3-contract,
  `"schema_version": "system-bank-benchmark/v1"`) — different version dictionaries under
  a common short name would be a defect.
- **No-op offline, exactly the necessary files online.** No `claude` → nothing is written
  (format validation only, see above). Yes `claude` → is written EXACTLY
  `evals/benchmark.json` (+`evals/benchmark.html` when `--static`) — verified
  directory snapshot before/after in `tests/test_eval.py::OnlineDeterminismCase`.

## Coating and gate

`validate.sh` displays the summary in one line (without making noise per-skill):

```
evals coverage: 3/141 local skills have evals/ (2%) — eval-first (skiller eval <skill>)
```

and **hard** validates the format of any entered `evals.json`/`pressure.json`/
`triggers.json` (broken JSON, no `skill`, empty `cases`, take `id`, assertion without
`type`/`value` → error). Deep grader logic/unit/scoring — in
`lib/skiller/eval.py`, covered `tests/test_eval.py` (offline).

## API (for online strapping and tests)

Pure functions `eval.py` are reusable: `grade_case`, `aggregate_runs`,
`build_benchmark`, `score_description` / `select_best_description` (judge
is injected), `validate_evals` / `validate_pressure` / `validate_triggers`,
`scaffold_evals`, `evals_coverage`, `render_markdown` / `render_html`.
