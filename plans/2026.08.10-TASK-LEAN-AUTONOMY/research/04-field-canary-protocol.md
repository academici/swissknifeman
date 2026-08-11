# Bounded field canary protocol for P1.2

Дата: 2026-08-10.

## Sources and selectors

P1.2 does not preload whole journals, changelog, reference ledger or foreign plans. From repository
root it captures bounded command output into `findings/P1.2-field-canary.md`:

Before this list, D9 is a pre-exec owner prerequisite: both exact official-source URLs must exist
in committed `HEAD:docs/reference.md`. An uncommitted row is not evidence. P1.2 neither reads nor
commits the foreign dirty diff; a red prerequisite yields a structural waiting Next before the
item starts.

1. `git log --oneline --decorate -- plans/2026.08.10-TASK-LEAN-AUTONOMY` — this plan's committed
   execution trajectory.
2. `python3 packages/task/scripts/plan-views.py history --item P0.1 --stdout --plan-dir plans/2026.08.10-TASK-LEAN-AUTONOMY`
   and the same command for P0.2/P1.1/P1.2 — bounded journal projections.
3. `rg -n 'audit|review|reopen|routing|blocked|owner' plans/2026.08.10-TASK-LEAN-AUTONOMY/journal.jsonl`
   — event index, never the full journal body in initial context.
4. Read-only `rg -n` over the named ARTIFEX/PROVIDER/roadmap cases only when a scorecard row needs
   a comparison; record path, line, git/worktree state and result, but do not edit or bundle them.
5. Run every exact Validation command in P1.2 and record exit/status/tree anchor.

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

## GO predicates

- four owning items used the exact package/root cwd carriers;
- no routine status-only close/audit/reopen cycle was required after the independent design audit;
- `local_repair` и `material_review` несут exact observed/not-observed значения выше; observed
  событие имеет evidence, а отсутствие trigger не провоцирует synthetic fault или новый audit;
- affected package validations, provider generators, plan views, lint and citations are green;
- no package/product or foreign carrier appears in the P1.2 diff;
- the canary report is reproducible on committed anchors; factual `[Unreleased]` entry уже
  committed P1.1 и не зависит от D9 либо canary verdict.

Any red or unknown predicate yields ADJUST per D8. ADJUST does not edit the owning package or
`CHANGELOG.md`: it materializes one owner DecisionRequest naming the exact package cwd, files,
validation and continuation, then keeps P1.2 nonterminal. Factual P1.1 ledger остаётся; если
remediation меняет release-visible смысл, owning follow-up обновляет ту же `[Unreleased]` запись
до своего handoff. RAG:— (repo-grounded: D3/D5/D7/D8/D10 and audit F5/F9/F10/F17/F18).
