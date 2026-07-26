# HANDOFF — 2026-07-26 — after P3.3

**Next:** /task:plan-run 2026.07.24-AGENT-RELIABILITY P3.4

| Параметр | Значение |
|:--|:--|
| Model class | `implementation` |
| Effort | `high` |
| Capabilities | `manual` |
| Context | `continue (/clear) — ручной item` |
| Model | Claude Sonnet 5 |
| Thinking | `high` |
| Суть | Выполнить disposable-worktree self-host canary (P3.4): шесть фиксированных кейсов в одном detached worktree на `CANDIDATE_SHA`, коммит/патч/трасса на кейс, rollback-репетиция на `PRE_PLAN_SHA` (D45, единственный источник — `artifacts/P0.1/pre-plan-sha.txt`), парные canary-метрики, чистое удаление worktree — §3 Routing предписывает `implementation/high`, `Exec = manual`, roadmap помечает solo (нельзя объединить: disposable worktree, native trials and rollback); используй `plan-run` (текущая сессия уже Sonnet/high, ритуал `/model`+`/effort` не нужен), НЕ `plan-exec` |

```
/task:plan-run 2026.07.24-AGENT-RELIABILITY P3.4
```

**Done:**

- **P3.3 закрыт 🟢 Done** (item-commit `f2d693bc`) — `skiller.quality.eval` gains a system-bank
  adapter: eight deterministic transcript/outcome operators (`apply_system_operator`) matching
  `reliability-acceptance-v1.md` § Graders exactly, distinct from the existing per-skill
  `ASSERTION_TYPES`; `grade_system_case`, `validate_system_graders`/`validate_system_cases`
  (generic structural validation of any `reliability-bank/v1`-shaped doc); `compute_system_metrics`
  — an independent reimplementation (not an import) of the frozen bank's own
  `run_bank.py::compute_metrics`; `seeded_system_sample`; `provider_capability_matrix`
  (presence-only Claude/Codex probe); `classify_portability_tier` (cites
  `task.task_contract.classify_tier` via optional import); `pair_system_metric` (mirrors
  `analyst.metrics.pair_metric`'s discipline); `build_system_benchmark` (orchestrator).
- **Cross-check (the core proof):** `build_system_benchmark` run against the real, untouched
  31-case frozen bank reproduces `bank-manifest.json::layer1_metrics` **byte-identically** across
  all ten metrics plus `same_finding_loop_depth`, and the seeded-sample selection reproduces
  `bank-manifest.json::sample.selected` exactly (the same five control cases) — see
  `plans/2026.07.24-AGENT-RELIABILITY/artifacts/P3.3/benchmark-manifest.json::cross_check`
  (`result: "byte-identical"`).
- `packages/skiller/tests/test_eval.py` — 56 tests green (32 pre-existing + 24 new,
  `PYTHONPATH=packages/skiller/lib:packages/skiller python3 -m unittest discover -s
  packages/skiller/tests -p 'test_eval.py'`, on `f2d693bc`). Two new fixtures
  (`packages/skiller/tests/fixtures_data/system-reliability-{bank,graders}-v1.json`).
- `bash packages/skiller/scripts/validate.sh`: 468 tests OK (444 on parent `b75b8766` — delta 24,
  exactly this item's new tests), 0 new WARN/ERROR.
- `plan.md` §0 Meta v1.16.8 → **1.16.9**; §4 Status Board P3 → `2/5`; §6 Update Log row.
- **Known Deviations (process, both recorded in `phases/P3.md` P3.3):** (a) the item's own
  literal Validation string for `test_eval.py` fails with `ModuleNotFoundError: No module named
  'tests'` — confirmed pre-existing (predates this item's diff, K=0), the working equivalent adds
  `packages/skiller` to `PYTHONPATH` (matches `scripts/test.sh`'s own convention); (b) the
  plan-exec.md step-3 start journal entry was appended after implementation rather than before —
  sequencing slip, both entries present in `journal.jsonl`.

**Remaining:**

- **P3.4–P3.5** ⬜ — disposable-worktree self-host canary, fresh terminal audit.
  **P4** ⬜ waits for terminal P3.

**Sources of truth:**

- `plan.md` — §0 Meta (v1.16.9), §4 Status Board (P3 = `2/5`, `🟡 In progress`), §6 Update Log.
- `phases/P3.md` — `## Phase Status` (P3.3 row `🟢 Done`), P3.3 item block (Completion
  Notes/Known Deviations carry the full record).
- `packages/skiller/lib/skiller/quality/eval.py` — the system-bank adapter P3.4 may reuse for its
  own canary trace/grading (not required by P3.4's own Files, but the same deterministic
  vocabulary).
- `plans/2026.07.24-AGENT-RELIABILITY/artifacts/P3.3/benchmark-manifest.json` — exact source-file
  hashes (`cases.json`/`graders.json`/`bank-manifest.json`) P3.4's own Pending Work references
  ("P3.4 uses exact manifest hashes").
- `journal.jsonl` — this item's start/final pair (`plan-run`, `item_id=P3.3`).

**Open risks:**

- **Layer-2 (live paired) F6/F8/F9/F10 still have no live number** — producing them needs a
  harness that turns a live `claude -p`/Codex invocation into a typed-event transcript the
  adapter can grade; the bank's cases assume multi-round session state and typed event emission
  that `run_case`/`run_suite`'s one-shot prompt/response model does not produce. This gap is named
  (not fabricated) in `benchmark-manifest.json::layer2_live_paired`; P3.4's six self-host canary
  cases are the plan's actual live-dispatch producer, but nothing in its own Files wires their
  traces into this adapter's floor evaluation — a future item, not silently assumed here.
- **`analyst`/`harness` package-API minor bumps still owed** (`0.1.0`→`0.2.0`, `0.3.0`→`0.4.0`,
  owed since P3.1/P3.2) — untouched again, `package.json` outside this item's `Files` too.
- **`skiller eval` CLI wiring for the system bank not added** — `cli.py` is outside this item's
  declared `Files` (same pattern P3.2 recorded for `analyst`'s CLI).
- **Predecessor items unchanged:** P0 phase-index row owner (`task:plan-close … P0`) and the
  P1.4 Update Log WARN remain open from earlier handoffs, untouched by P3.3.

**Workarounds / Deferred / Open questions:**

- **`trace-record-missing` residual (P2.5/P2.8)** — still owned by a live-dispatch/typed-transcript
  producer; this item built the grading/pairing/sampling adapter and proved it byte-identical
  against the frozen bank, it did not run a live paired bank pass.
- **`docs-sync` follow-up** (`packages/task/CLAUDE.md` compiler/enforcement seam description) —
  still owned by P3.1's original note; not touched by this item (out of `Files`), carried forward.
- **FOREMAN re-scope marker condition** — both terminal-condition phases (P2.1, P3.1) are already
  terminal; the marker lives in `2026.07.18-FOREMAN`'s own files (И2 boundary), flagged for that
  plan's own bookkeeping, unchanged by this item.
