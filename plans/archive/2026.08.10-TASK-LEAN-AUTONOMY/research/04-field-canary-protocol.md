# Bounded field canary protocol for P1.2

Дата: 2026-08-10.

## Sources and selectors

P1.2 does not preload whole journals, changelog, reference ledger or foreign plans. From repository
root it captures bounded command output into `findings/P1.2-field-canary.md`:

Before this list, one D9+D13 pre-exec owner prerequisite requires all six exact official-source
URLs from those decisions in committed `HEAD:docs/reference.md`. An uncommitted row is not
evidence. P1.2 neither reads nor commits the foreign dirty diff; a red prerequisite yields one
structural waiting Next before the item starts.

1. `git log --oneline --decorate -- plans/2026.08.10-TASK-LEAN-AUTONOMY` — this plan's committed
   execution trajectory.
2. `python3 packages/task/scripts/plan-views.py history --item P0.1 --stdout --plan-dir plans/2026.08.10-TASK-LEAN-AUTONOMY`
   and the same command for P0.2/P1.1/P1.2 — bounded journal projections.
3. `rg -n 'audit|review|reopen|routing|blocked|owner' plans/2026.08.10-TASK-LEAN-AUTONOMY/journal.jsonl`
   — event index, never the full journal body in initial context.
4. Read-only `rg -n` over the named ARTIFEX/PROVIDER/roadmap cases only when a scorecard row needs
   a comparison; record path, line, git/worktree state and result, but do not edit or bundle them.
5. Run every exact Validation command in P1.2 and record exit/status/tree anchor.
6. For historical baseline, enumerate only JSON paths first with
   `find <repo> -path '*/.claude/runs/*.json' -type f`; aggregate selected scalar fields through
   one `jq -s` pass. Do not bundle raw reports or transcripts. Record directory count, report
   count, tool failures, error loops, turns/output and coverage caveat.
7. For the new path, join P0.1/P0.2/P1.1 journal `session_id`/`run_id` to available root
   run-report identity. A missing optional SessionEnd report is `coverage-limited (<reason>)`,
   never fabricated GREEN/RED; missing required journal identity is ADJUST.

## Historical baseline snapshot

This snapshot is descriptive and calibrates the scorecard; it is not a hard numeric budget:

| Project | Journals | Audit/blocked/retry | Run evidence | Known control-plane pathology |
|:--|:--|:--|:--|:--|
| Agelto | 775 events / 5 canonical journals | 38 audits; 10 blocked (9 routing); 37 retry | 46 reports / 6 dirs / 134 tool failures / 0 error loops | at least 16/49 hard stops procedural; 45 duplicate closes |
| Swiss Knife Man | 1,412 events / 12 journals | 103 audits; 33 blocked (≥23 procedural); 119 retry | 43 reports / 8 dirs / 73 tool failures / 0 error loops | 84 repeated audit events; journal↔run join 0 |

Exact cases, lower-bound caveats and fail-closed counterexamples live in
`findings/06-cross-project-execution-telemetry.md`; P1.2 references, not recopies, that evidence.

## Real observation window and no-event values

Единственный real post-P1.1 canary — текущий фактический запуск
`task:plan-run 2026.08.10-TASK-LEAN-AUTONOMY P1.2`: от pre-mutation admission через journal
start, state/view regeneration и bounded validations до pre-final/handoff. Read-only replay в
пункте 4 помогает сравнению, но не считается исполнением обновлённого runtime и не подменяет
этот window.

Scorecard записывает ровно по одному значению для каждого условного события:

- `local_repair: observed (<fingerprint>; <repair evidence>)` либо
  `local_repair: not-observed (no eligible local failure fingerprint in the P1.2 live run)`;
- `material_review: observed (<D3 trigger>; <verdict/reuse evidence>)` либо
  `material_review: not-observed (no D3 material trigger: scope/SHA/risk remained stable)`.

Exact `not-observed` не является red/unknown: оно подтверждает, что событие не возникло и runtime
не создал искусственный repair/review loop. Любое иное/пустое значение — ADJUST. RAG:—
(repo-grounded: D3/D5/D8/D10 and audit F17).

Additional required rows:

- `procedural_terminalization: 0` — procedural/transient/dependency-not-ready/unrelated signals
  may be observed, but none writes terminal product status;
- `routing_preflight_mutations: 0`;
- `duplicate_terminal_appends: 0`;
- `untriggered_audit_or_reopen: 0`;
- `journal_identity: <eligible start/terminal pairs joined>/<eligible pairs>; <exceptions>`;
- `run_report_join: <joined>/<available>; <coverage-limited reasons>`;
- `same_attempt_recovery: observed (<class/fingerprint/evidence>)` либо exact
  `not-observed (no eligible recoverable signal in the live path)`;
- `material_stop_preserved: observed (<class/evidence>)` либо exact
  `not-observed (no acceptance/safety/authority trigger in the live path)`.

Every observed error/stop also has one compact D12 row: `signal_class · reproduction · scope/delta
· action · outcome`. Tool failure count without this causal row is not acceptance evidence.

## GO predicates

- four owning items used the exact package/root cwd carriers;
- no routine status-only close/audit/reopen cycle was required after the independent design audit;
- final design audit repaired the non-material index freshness defect in the same attempt, without
  a fifth audit/design pass/root, and P1.1 protects the same D11 transition with a paired
  non-material/material regression;
- `local_repair` и `material_review` несут exact observed/not-observed значения выше; observed
  событие имеет evidence, а отсутствие trigger не провоцирует synthetic fault или новый audit;
- D12 additional rows above are complete; only reproduced acceptance/safety/authority may be
  terminal, while an unknown non-idempotent write remains fail-closed until reconciled;
- D13 has zero routing preflight mutations, duplicate terminal appends and untriggered audits;
  required journal identities join, optional run-report gaps are named without blocking product;
- affected package validations, provider generators, plan views, lint and citations are green;
- no package/product or foreign carrier appears in the P1.2 diff;
- the canary report is reproducible on committed anchors; factual `[Unreleased]` entry уже
  committed P1.1 и не зависит от D9 либо canary verdict.

Any red or unknown predicate yields ADJUST per D8. ADJUST does not edit the owning package or
`CHANGELOG.md`: it materializes one owner DecisionRequest naming the exact package cwd, files,
validation and continuation, then keeps P1.2 nonterminal. Factual P1.1 ledger остаётся; если
remediation меняет release-visible смысл, owning follow-up обновляет ту же `[Unreleased]` запись
до своего handoff. RAG:— (repo-grounded: D3/D5/D7/D8/D10 and audit F5/F9/F10/F17/F18).
