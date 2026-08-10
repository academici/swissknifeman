# Bounded field canary protocol for P1.2

Дата: 2026-08-10.

## Sources and selectors

P1.2 does not preload whole journals, changelog, reference ledger or foreign plans. From repository
root it captures bounded command output into `findings/P1.2-field-canary.md`:

1. `git log --oneline --decorate -- plans/2026.08.10-TASK-LEAN-AUTONOMY` — this plan's committed
   execution trajectory.
2. `python3 packages/task/scripts/plan-views.py history --item P0.1 --stdout --plan-dir plans/2026.08.10-TASK-LEAN-AUTONOMY`
   and the same command for P0.2/P1.1/P1.2 — bounded journal projections.
3. `rg -n 'audit|review|reopen|routing|blocked|owner' plans/2026.08.10-TASK-LEAN-AUTONOMY/journal.jsonl`
   — event index, never the full journal body in initial context.
4. Read-only `rg -n` over the named ARTIFEX/PROVIDER/roadmap cases only when a scorecard row needs
   a comparison; record path, line, git/worktree state and result, but do not edit or bundle them.
5. Run every exact Validation command in P1.2 and record exit/status/tree anchor.

## GO predicates

- four owning items used the exact package/root cwd carriers;
- no routine status-only close/audit/reopen cycle was required after the independent design audit;
- minor in-scope defects were repaired locally; every material/authority stop has a D3/D8 carrier;
- affected package validations, provider generators, plan views, lint and citations are green;
- no package/product or foreign carrier appears in the P1.2 diff;
- the canary report and `[Unreleased]` entry are reproducible on committed anchors.

Any red or unknown predicate yields ADJUST per D8. ADJUST does not edit the owning package: it
materializes one owner DecisionRequest naming the exact package cwd, files, validation and
continuation, then keeps P1.2 nonterminal. RAG:— (repo-grounded: D3/D5/D7/D8 and audit F5/F9/F10).

