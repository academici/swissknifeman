# Catalog of work flow pathologies

Run Claude Code may «work», but bad: running the same file in circles, cheating
haiku-agent thinking instead of text, quietly fanning scope, edit the generated file, which
next sync will be erased. This is a catalog of such patterns - **workflow pathologies** — with detector (if
it is), formula/threshold, severity and specific remediation.

Source of Truth Codes/formulas/thresholds/severity — **[`analyst/pathology.py`](https://github.com/academici/swissknifeman/blob/main/packages/analyst/lib/analyst/pathology.py)**
(clean `detect(run_report) -> [finding]`, without I/O and watch, never quits). This document is
his Russian-language showcase + mapping to a minimal list of classes «Workflow Pathology Catalog»
(§12 draft master plan - local design-document not tracked in the repo, hence no path/links).
Thresholds - **heuristics NOT calibrated** by field false-positive-rate (same principle as
[Tuning parameters](./tuning) `analyst`): values are selected according to the signal shape, they change only in
source module.

## Layers

```
harness-hook (SessionEnd)        analyst/pathology.py              consumers route
run-report SCHEMA=2       ──▶   detect(run_report)       ──▶   maind analyze  — attention → reasons
(usage/reads/error_loops/                                                       (verdict ATTENTION);
 retrieval/protected_writes)                                                    info → section «Efficiency»
                                                                 analyst digest — relapse ≥2 out of 5
                                                                   last sessions → candidate-lesson
```

Hook **collects** raw run slices (tool calls, readings, error-series, retrieval, protected-writes,
usage-tokens) in `<project>/.claude/runs/<sid>.json`. `pathology.detect()` **evaluates** this slice
detectors below and gives a flat list of findings - he himself does not write anything or solve anything. Next
finds **route** consumers: `maind analyze` — to the verdict of the current run (read-only
parsing «did everything work?»), `analyst digest` — in the candidate lesson, if the pathology is not one-time (see
«Relapse rule» below). The same clean list of finds is at the entrance to both.

Both connections are implemented and covered by tests (plan SKM-MASTER-002, phase P3, items P3.1–P3.3):

- **`maind analyze`** (`packages/maind/lib/maind/analyze.py`, `pathology_slice()`) unfolds
  finds by severity: `attention` leaves **lines evidence** (without code) in `reasons` verdict
  via `compute_verdict(..., pathology_attention=...)` — goes where pack-drift/dirty
  tree/token-anomalies; `info` goes to `rep["efficiency"]` and is printed in human-readable output
  as a separate block `code: evidence` under the title **«Efficiency»**. Import `analyst.pathology`
  unconditional - like the others `from core import ...` in `maind`/`analyst`/`harness` (none
  wrapped in `try/except ImportError`; degradation «core/ not on PYTHONPATH» — launcher care/
  `validate.sh`, not every import in place). Formally diverges from literal wording Code
  Guidance item P3.2 («import from ImportError-fallback»), but follows the actual repo convention.
- **`analyst digest`** (`packages/analyst/lib/analyst/digest.py`, `extract_pathologies()`) drives away
  `detect()` according to the latest `PATHOLOGY_WINDOW=5` run-report'project am (reads them directly from disk
  `<project>/.claude/runs/*.json`, not via trend file) and creates a candidate lesson only if the code
  finds **relapsed** (see below) — single extractor digest, which needs
  real project path, not just the current one `run_report` (deliberate exclusion from «extractors -
  pure functions», see docstring module).

## Detect ≠ Gate

Pathology detection is not the same as blocking. `severity` in find - only `info` or
`attention`, none `critical`/`fail`: thresholds are not calibrated and therefore not trustworthy
level «run stop». Separation by location in the report `maind analyze`:

| Severity | What does it mean? | Where does it go? `maind analyze` |
|:--|:--|:--|
| `info` | weak signal - look during scheduled analysis, action is not necessary | section **«Efficiency»** (does not affect the verdict) |
| `attention` | probable pathology - worth examining | list **reasons** → verdict **ATTENTION** |
| — | **RED is impossible from pathologies for any number of findings** | RED — only failed test/lint/work flow (see `compute_verdict` in `analyze.py`) |

This is a direct consequence of the master plan principle §5 «Detect ≠ Gate» and solutions D9 plan SKM-MASTER-002:
RED is reserved for an objectively failed check, not for a heuristic. Even ten
`attention`-finds in one run will not raise the verdict higher ATTENTION.

## Relapse rule ≥2 out of 5 (for lessons)

One run with a find is a signal for *this* run (`maind analyze`), is not a reason to immediately write a lesson:
one-time pathology - noise, and `analyst` teaches only what is sustainable. `analyst digest`
(`extract_pathologies()` in `digest.py`) takes a candidate lesson from pathology only if **same code**
finds were found at least in `PATHOLOGY_MIN_HITS=2` from **latest `PATHOLOGY_WINDOW=5`**
run-report'ov of the project (current run enters the window; history - files `.claude/runs/*.json`,
fresh by mtime first, without new state-file). Relapse is considered according to `code` finds
(`file-reread`, `protected-write`, …), and not by text `evidence` — otherwise two runs with different
numbers will never collapse into one pattern. Test «one-time pathology does NOT create a lesson»
(`test_single_occurrence_out_of_five_no_lesson` in `test_digest.py`) — acceptance part item P3.3. This
same anti-noise instinct as man-gate curated: `digest` doesn't guess the insight one by one
observation.

**Second filter, separate from relapse: not every relapse code becomes a lesson.** `digest` leads
explicit dictionary `_PATHOLOGY_REMEDIATIONS` — only code with a READY specific action is included in
lesson pipeline, even with persistent relapse. On 2026-07-02 in the dictionary **4 code**:

| Code | Class §12 | Literal `action` candidate-lesson |
|:--|:--|:--|
| `file-reread` | 4. repeated file rereads | «keep the read card; use notes to refer back/plan, not re-read» |
| `tool-error-loop` | out §12 (add. detector) | «after 2 identical tool failures, change the approach, don’t hammer» |
| `protected-write` | 8. protected asset mutation attempts | «generated-do not edit pack files - overrides in `.claude/rules/*-overrides.md`» |
| `no-verify` | 10. missing acceptance boundaries | «changed the code - run tests before the session ends» |

Other codes (`no-op-run`, `overthinking`, `cache-miss`, `retrieval-stuffing`, `static-context`,
`fanout`, `no-verify-devloop`) — **signals only for `maind analyze`** (reasons/«Efficiency»),
in `analyst digest` are not involved even with stable relapse: «no specific what to do - learn
agent nothing» (docstring `digest.py`). Test for this filter -
`test_code_without_remediation_stays_signal_even_if_recurring` (5 out of 5 alarms `no-op-run` all
still does not create a lesson).

## Catalog: 10 classes from §12

The order and wording of the classes is the same as in the draft master plan. «Detectability status»:
**is being detected now** (detector exists and covers the class) / **partially** (there is a detector, but it catches
symptom or subset only) / **NOT detectable deterministically** (no detector - indicated,
what kind of data is missing). Column «→ digest» — whether the code is involved in the recurrence rule (see above):
**yes** (in `_PATHOLOGY_REMEDIATIONS`) / **no** (only `maind analyze`) / **—** (no detector).

| # | Class (§12) | Code(s) | Severity | → digest | Status |
|:-:|:--|:--|:--|:-:|:--|
| 1 | repeated re-planning | no | — | — | NOT detectable - repeat count TodoWrite (phase 2) |
| 2 | no-op execution | `no-op-run` | info | no | is being detected now |
| 3 | overthinking on cheap agents | `overthinking` | info | no | is being detected now |
| 4 | repeated file rereads | `file-reread` | attention | yes | is being detected now |
| 5 | hidden scope expansion | no | — | — | NOT detectable - declared-scope from plans/-protocol |
| 6 | stack-pack ↔ project type mismatch | no | — | — | NOT detectable here - `harness agent-packs doctor` |
| 7 | invalid handoff after context reset | no | — | — | NOT detectable - cross-run correlation |
| 8 | protected asset mutation attempts | `protected-write` | attention | yes | is being detected now |
| 9 | prompt bloat from overlapping rules | `static-context` | info | no | partially (symptom, not cause) |
| 10 | missing acceptance boundaries | `no-verify` / `no-verify-devloop` | attention / info | yes / no | partially (absence proxy verify) |

### 1. repeated re-planning

**Detector:** no. **Formula/threshold:** no. **Severity:** —.

**Remediation:** narrow down task item by plan-protocol (`task:plan-*`/`general/spec-interview`) to one
atomic target BEFORE execution starts. Repeated rescheduling is a reason for an obvious escalation in
`plan-protocol §8` («the plan diverged from the code - do not improvise»), and not for quietly substituting a plan.
The reason for re-planning should be recorded in Decision Log plan, and not lose it between calls.

**Status: NOT deterministic detectable.** Data acquisition: repetition counter `TodoWrite` with one and
the same shape/target between tool calls (phase 2 - a separate log is needed TodoWrite-calls to
hook, which is not currently available run-report SCHEMA=2; `pathology.py` only sees run aggregates, not
sequence of plan edits within it).

### 2. no-op execution

**Detector:** `no-op-run`. **Formula:** `tools.total ≥ NOOP_MIN_TOOLS(20)` and `files_changed=[]` and
`bash.tests=[]` and `retrieval.calls==0`. **Severity:** `info`.

**Remediation:** if it was intentional read-only reconnaissance - signal does not require action (that's why
`info`, not `attention`). If the task involved editing, check if the plan was lost/scope
between tool calls (see `session-handoff`), is the model stuck on reading without writing.

**Status: being detected now** (→ `maind analyze`, section «Efficiency»). **→ digest: no** —
no entry in `_PATHOLOGY_REMEDIATIONS`, lesson is not created even with a stable relapse (no
specific action that can be taught).

### 3. overthinking on cheap agents

**Detector:** `overthinking`. **Formula:** subagent with `model` containing `haiku`;
`thinking_chars / (thinking_chars + text_chars) > OVERTHINKING_RATIO(0.6)`. **Severity:** `info`.

**Remediation:** review model routing for this step - the task seems to be beyond haiku-shooting gallery
(raise to sonnet) or the prompt for a cheap model is not narrowed down to a checklist. Check if there is any leakage in
cheap subagent open reasoning instead of a specific instruction (see `Reasoning policy` master plan §4).

**Status: being detected now** (→ `maind analyze`, section «Efficiency»). **→ digest: no** —
like `no-op-run`, code not in `_PATHOLOGY_REMEDIATIONS`.

### 4. repeated file rereads

**Detector:** `file-reread`. **Formula:** `total ≥ REREAD_MIN_TOTAL(10)`;
`(total − unique) / total > REREAD_RATIO_MAX(0.4)`. **Severity:** `attention`.

**Remediation:** repeated reads of the same file - context is not retained between steps. Reduce to
alone `Read` and work in-memory; for symbolic/structured search use code graph
(Serena) instead of repeating `grep`/`Read`; if it breaks when context-reset — check completeness
handoff-artifact (class 7).

**Status: being detected now** (→ `maind analyze`, verdict ATTENTION). **→ digest: yes** — when
relapse ≥2/5 `analyst digest` creates a lesson literally with action «keep the read card; for
re-apply use notes/plan, not re-read» (see «Relapse rule» above).

### 5. hidden scope expansion

**Detector:** no. **Formula/threshold:** no. **Severity:** —.

**Remediation:** declare scope clearly in the plan/task item (`Scope Included`/`Scope Excluded`) BEFORE the start
execution. Expansion diff'and beyond what is stated is a reason for an obvious escalation, not for a silent
«also corrected this».

**Status: NOT deterministic detectable.** Data acquisition: declared-scope from plans/-protocol -
need a list of declared paths/files task item as a reference to compare with the actual
`files_changed` run-report'a. `analyst/pathology.py` sees only WHAT was actually changed during the run, without
standard «what was stated» — has nothing to compare with.

### 6. mismatch between stack-pack and project type

**Detector:** no (not in run-telemetry). **Formula/threshold:** no. **Severity:** —.

**Remediation:** `harness agent-packs doctor` (or `harness doctor`) — checking the pack with the project type
at stage provisioning/sync. For Laravel-packages (not app) — target solution for a separate package
`laravel-package` (master plan §14, plan SKM-MASTER-002 phase P6/F).

**Status: NOT detectable here.** This is a static diagnostic of the project configuration at the stage
installations/stack-pack signal, not a single-run signal - lives in `harness agent-packs doctor`, not in
`analyst/pathology.py`: thresholds/detectors of this file operate only run-report'om session.

### 7. invalid handoff after context reset

**Detector:** no. **Formula/threshold:** no. **Severity:** —.

**Remediation:** validate handoff-artifact (master plan §8/P4 «Context Reset Handoff Standard»)
to the minimum sufficiency BEFORE the start of the next session; record explicit acceptance-step «handoff
is readable and consistent with the current state of the plan».

**Status: NOT deterministic detectable.** Data acquisition: cross-run correlation - necessary
match handoff-artifact of the PREVIOUS run with the actual starting state of the NEXT run.
`analyst/pathology.py detect()` sees one run-report at a time (without memory of the neighboring session) — this is in
basically a different login form, not just one pathology inside the report.

### 8. protected asset mutation attempts

**Detector:** `protected-write`. **Formula:** `len(protected_writes) > 0` (threshold 0 - any non-empty
entry). **Severity:** `attention` (always, regardless of volume).

**Remediation:** edit in managed-paths (vendor-skills/generated-files agent-pack) transfer to
override/extension-zone (base+overlay, master plan §13/P9, solution D11) and restore
generated file (`harness agent-packs render`). Generated files cannot be edited manually
never - they will be overwritten by the next one `sync`.

**Status: being detected now** (→ `maind analyze`, verdict ATTENTION). **→ digest: yes** — when
relapse ≥2/5 action lesson literally «generated-do not edit pack files - overrides in
`.claude/rules/*-overrides.md`».

### 9. prompt bloat from overlapping rules

**Detector:** `static-context` (partially). **Formula:** for agent `label=="main"` (fallback —
first agent usage-slice), when `msgs ≥ STATIC_MIN_MSGS(3)`: `avg_in = (in + cache_read) / msgs`;
`share = avg_in / CONTEXT_WINDOW_TOKENS(200_000) > STATIC_WINDOW_SHARE(0.7)` **and**
`tools.total < STATIC_MAX_TOOLS(15)`. **Severity:** `info`.

**Remediation:** revision of resident buckets/MCP-issues (`skiller budget`); remove intersections
rules between bucket'ami/stack-pack'ami/project overrides (master plan §11/P7 bucket-audit); translate
rarely needed rules from always-on in on-demand retrieval.

**Status: partially** (symptom, not cause; → `maind analyze`, section «Efficiency»). `static-context`
detects SYMPTOM - bloated resident input with a small amount of tool work (fat buckets/MCP-output
put pressure on every call), but not the REASON. Attribution «what rules exactly/buckets intersect» requires
static P7 bucket-audit (inventory overlap bucket↔stack-pack↔override, §11), and not
run-telemetry of one run. **→ digest: no** — code not in `_PATHOLOGY_REMEDIATIONS`.

### 10. missing acceptance boundaries

**Detectors:** `no-verify` (edits without verification) and `no-verify-devloop` (dev-loop without result).
**Formulas:** `no-verify`: `files_changed` is non-empty and `bash.tests == []` → `attention` (threshold 0).
`no-verify-devloop`: `devloop` present (non-empty dict), but without keys `verify`/`results` →
`info` (threshold 0). **Severity:** `attention` / `info` respectively.

**Remediation:** commit acceptance-criteria/Definition of Done in terms of BEFORE execution
(`general/task-brief-template`, `plan-protocol §7 Reporting Schema`); drive away `validate.sh`/tests
before the end of the cut; dev-loop must write `verify`/`results`, rather than leaving the slice total
uncommitted.

**Status: partially** (absence proxy verify; → `maind analyze` for both codes). Detectors catch
MISSING verify-trace as a proxy for lack of acceptance boundaries (edits without checking, or slice
without total recorded), but do not check whether acceptance-criteria are generally FORMULAR in the plan
before the start - the same addition as for class 5: a standard is needed «what should have been checked» from
plans/-protocol, and not just the fact that there was no run. **→ digest:** only `no-verify` (`attention`)
— yes, action literally «changed the code - run tests before the session ends» for relapse ≥2/5;
`no-verify-devloop` (`info`) in `_PATHOLOGY_REMEDIATIONS` not included - no.

## Detectors outside the minimum list §12

`analyst/pathology.py` implements more detectors than the minimum list §12 (industrial
heuristics LLM-agent observability — see [docs/reference.md](/reference)). For completeness SSOT — they
here, without reference to a specific draft class:

| Code | What it catches | Formula/threshold | Severity | → digest |
|:--|:--|:--|:--|:-:|
| `tool-error-loop` | series of similar errors from one tool in a row - retry without changing approach | `len(loop) ≥ ERROR_LOOP_INFO_LEN(3)` → info; `≥ ERROR_LOOP_ATTENTION_LEN(5)` → attention | info/attention | **yes** — relapse ≥2/5 → action «after 2 identical tool failures, change the approach, don’t hammer» |
| `cache-miss` | low proportion of cache reads with a large input - unstable system prompt breaks prompt-cache | `cache_hit < CACHE_HIT_LOW(0.4)` and input volume `> CACHE_MISS_MIN_TOKENS(200_000)` current | info | no |
| `retrieval-stuffing` | retrieval-output takes up a noticeable share of input - raw materials are poured into context instead of synthesis | `retrieval_tokens/in > RETRIEVAL_IN_SHARE(0.25)`; `attention` when `repeated_queries ≥ RETRIEVAL_REPEATED_MIN(2)` | info/attention | no |
| `fanout` | wide fan-out subagents with modest output from files | `agents > FANOUT_MIN_AGENTS(8)` and `files_changed < FANOUT_MAX_FILES(5)` | info | no |

`tool-error-loop` — the only one «unlisted» detectors with ready-made remediation in
`_PATHOLOGY_REMEDIATIONS`: although it is not included in the minimum list §12 (is closest in spirit to class 1
«repeated re-planning» — both are about getting stuck without changing approach, but `tool-error-loop` — about the tool
within ONE run, and not about the plan between runs), upon relapse, it also becomes a lesson candidate.

## See also

- [`analyst/pathology.py`](https://github.com/academici/swissknifeman/blob/main/packages/analyst/lib/analyst/pathology.py) —
  detector code (SSOT formulas/thresholds/severity).
- [`packages/maind/lib/maind/analyze.py`](https://github.com/academici/swissknifeman/blob/main/packages/maind/lib/maind/analyze.py)
  (`pathology_slice`) · [`packages/analyst/lib/analyst/digest.py`](https://github.com/academici/swissknifeman/blob/main/packages/analyst/lib/analyst/digest.py)
  (`extract_pathologies`, `_PATHOLOGY_REMEDIATIONS`) — routing finds to verdict/lessons.
- [Tuning parameters](./tuning) — same principle «change the threshold only in the source module», for
  confidence-arithmetic `analyst`.
- [CLI and commands](./cli) · [Lesson life cycle](./lifecycle) — where the lesson candidate lands from
  recurrent pathology after `digest`.
- — phase introducing pathology catalog (items P3.1–P3.4).
